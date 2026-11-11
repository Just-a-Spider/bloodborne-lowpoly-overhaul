#!/usr/bin/env python3
"""
Master Batch PSX Demake Engine for All Bloodborne Environment Maps (m20..m36, including Chalice Dungeons m29_*).

Core Capabilities:
1. All-Maps & Multi-Block Discovery (--map all):
   - Automatically discovers all campaign, DLC, and modular Chalice Dungeon (m29_*) geometry blocks and BXF binders.
2. True LOD0 Material & Texture Source Enforcement:
   - Synchronizes demade LOD0 textures (_a.tpf.dcx) directly into distant LOD slots (_a_l.tpf.dcx) so the engine
     never swaps to muddy low-tier distant material sheets.
   - Supports --lod 0 (Direct QEM decimation on true LOD0 FaceSet 0 geometry) as well as Hybrid Native LOD1/LOD2.
3. Zero-Bloat In-Place BXF Slot Overwrite & Test 24 Binder Safety:
   - Protects m21 secondary ambient binders (m21_0001..0003) by default while processing all multi-part architectural
     binders (0000..0003) on urban/dungeon maps (m20, m22..m36).
   - Uses Btrfs reflink-aware restoration (--clean) for instant, zero-disk-cost sandbox resets.
"""

import sys
import os
import re
import glob
import argparse
import time
import struct
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch  # noqa: E402
from soulstruct.bloodborne.models import FLVER  # noqa: E402
from soulstruct.dcx import decompress, compress  # noqa: E402
from auto_demake_engine import auto_demake_file  # noqa: E402
from mesh_decimator import decimate_flver  # noqa: E402
from demake_color_engine import (  # noqa: E402
    FLAT_NORMAL_BC5_UNORM,
    FLAT_NORMAL_BC1,
    get_mip_sizes,
    decode_bc1_to_rgba,
    encode_rgba_to_bc1,
    decode_bc4,
    encode_bc4,
)
from ps4_swizzle import deswizzle_level, swizzle_level  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VANILLA_ROOT = REPO_ROOT / "CUSA03173" / "dvdroot_ps4"
SANDBOX_ROOT = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4"

# Environment textures that must remain 100% byte-identical to vanilla
CELESTIAL_LIGHTMAP_KEYWORDS = (
    "clond", "cloud", "cirrus", "sky", "moon", "sun", "star", "magic", "cosmos",
    "blendmsk", "mask", "msk", "gi_", "envmap", "lightmap", "dol", "lut", "sfx",
)

FOLIAGE_KEYWORDS = (
    "foliage", "grass", "plant", "tree", "leaf", "ivy", "branch",
    "flower", "moss", "vine", "weed", "bush", "fern", "shrub",
)

# A keyword only counts at the START of a word (not preceded by a letter): 'tree_01' / 'm22_tree' match,
# 'streetlight' (contains 'tree') and 'tweed' (contains 'weed') no longer do.
_CELESTIAL_RE = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(k) for k in CELESTIAL_LIGHTMAP_KEYWORDS) + ")")
_FOLIAGE_RE = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(k) for k in FOLIAGE_KEYWORDS) + ")")


def is_celestial_or_lightmap(low_name: str) -> bool:
    return bool(_CELESTIAL_RE.search(low_name))


def is_foliage_name(low_name: str) -> bool:
    return bool(_FOLIAGE_RE.search(low_name))


def protected_keyword(low_name: str):
    m = _CELESTIAL_RE.search(low_name)
    return m.group(0) if m else None


SKY_FLVER_KEYWORDS = ("sky", "cloud", "clond", "moon", "sun", "star", "cosmo", "nebula", "celest", "bg_")

# The last word of every 36-byte TPF entry is the real DXGI format (verified on chr TPFs: the size math
# agreed with it on 32/32 textures). The format byte at unk1&0xFF is NOT reliable: 0x6C is BC1 on some
# files and BC5 on others. Only these kinds are ever re-encoded; BC3/BC6H/BC7/unknown stay byte-identical.
DXGI_KIND = {71: "bc1", 72: "bc1", 80: "bc4", 81: "bc4", 83: "bc5", 84: "bc5"}


def tpf_entry_info(tpf):
    """First texture entry of a TPF: (tex_off, tex_sz, unk1, w, h, dxgi)."""
    tex_off, tex_sz, unk1, unk2 = struct.unpack("<4I", bytes(tpf[0x10:0x20]))
    dxgi = struct.unpack("<I", bytes(tpf[0x10 + 32:0x10 + 36]))[0]
    return tex_off, tex_sz, unk1, unk2 & 0xFFFF, (unk2 >> 16) & 0xFFFF, dxgi


def copy_reflink(src: Path, dst: Path):
    """Copies files using Btrfs copy-on-write reflinks when supported, falling back to shutil.copy2."""
    res = subprocess.run(
        ["cp", "-a", "--reflink=auto", str(src), str(dst)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if res.returncode != 0:
        if src.is_dir():
            shutil.copytree(src, dst, copy_function=shutil.copy2, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def discover_all_map_ids() -> List[str]:
    """Discovers all unique map IDs (m20, m21, m22, ..., m29, ..., m36) present in VANILLA_ROOT/map."""
    map_dir = VANILLA_ROOT / "map"
    ids = set()
    for p in map_dir.iterdir():
        if p.is_dir() and p.name.startswith("m") and len(p.name) >= 3 and p.name[1:3].isdigit():
            ids.add(p.name[:3])
    return sorted(ids)


def restore_map_sandbox(map_id: str):
    """Restores map FLVERs, BXF texture binders, and map objects back to pristine vanilla via Btrfs reflinks."""
    print(f"\n--- Restoring Map Sandbox for {map_id.upper()} to Pristine Vanilla ---")

    # 1. Map geometry folders (map/mXX_*)
    for van_flv_dir in sorted(VANILLA_ROOT.glob(f"map/{map_id}_*")):
        if not van_flv_dir.is_dir():
            continue
        sand_flv_dir = SANDBOX_ROOT / "map" / van_flv_dir.name
        if sand_flv_dir.exists():
            shutil.rmtree(sand_flv_dir)
        sand_flv_dir.parent.mkdir(parents=True, exist_ok=True)
        copy_reflink(van_flv_dir, sand_flv_dir)
        print(f"  [RESTORED] Geometry Block: {sand_flv_dir.name}")

    # 2. BXF texture archive folder (map/mXX)
    van_map_dir = VANILLA_ROOT / "map" / map_id
    sand_map_dir = SANDBOX_ROOT / "map" / map_id
    if van_map_dir.exists() and van_map_dir.is_dir():
        if sand_map_dir.exists():
            shutil.rmtree(sand_map_dir)
        sand_map_dir.parent.mkdir(parents=True, exist_ok=True)
        copy_reflink(van_map_dir, sand_map_dir)
        print(f"  [RESTORED] Textures: {sand_map_dir.name}")

    # 3. Map objects folder (obj/oXX*.objbnd.dcx)
    prefix = f"o{map_id[1:3]}"
    van_obj_dir = VANILLA_ROOT / "obj"
    sand_obj_dir = SANDBOX_ROOT / "obj"
    sand_obj_dir.mkdir(parents=True, exist_ok=True)
    if van_obj_dir.exists():
        objs = list(van_obj_dir.glob(f"{prefix}*.objbnd.dcx"))
        for p in objs:
            copy_reflink(p, sand_obj_dir / p.name)
        print(f"  [RESTORED] Map objects: {len(objs)} files matching {prefix}*")


def is_sky_or_celestial_flver(flv, filename: str) -> bool:
    """Returns True if a map FLVER is a skybox, cloud dome, moon, or distant celestial backdrop."""
    low_fn = filename.lower()
    if any(k in low_fn for k in ("o210020", "o210021", "moon", "celest")):
        return True
    idx_str = filename.split("_")[-1].split(".")[0]
    if idx_str.isdigit() and int(idx_str) >= 9000:
        return True
    for m in flv.meshes:
        if not m.material:
            continue
        mat_name = (m.material.name or "").lower()
        mtd_name = (m.material.mat_def_name or "").lower()
        if any(k in mat_name or k in mtd_name for k in SKY_FLVER_KEYWORDS):
            return True
        for tex in getattr(m.material, "textures", []):
            tpath = (getattr(tex, "path", "") or "").lower()
            if any(k in tpath for k in SKY_FLVER_KEYWORDS):
                return True
    return False


def _tex_stem(path: str) -> str:
    return re.split(r"[\\/]", path)[-1].split(".")[0].lower()


def collect_map_texture_stems(map_id: str) -> set:
    """Lower-case stems (e.g. 'm21_brick_a') of every texture stored in this map's BXF archives."""
    stems = set()
    for bhd in sorted((VANILLA_ROOT / "map" / map_id).glob("*.tpfbhd")) if (VANILLA_ROOT / "map" / map_id).exists() else []:
        data = bhd.read_bytes()
        count = struct.unpack("<I", data[12:16])[0]
        for i in range(count):
            name_off = struct.unpack("<I", data[0x40 + i * 36 + 32: 0x40 + i * 36 + 36])[0]
            cur = name_off
            while cur < len(data) - 1 and not (data[cur] == 0 and data[cur + 1] == 0):
                cur += 2
            stems.add(data[name_off:cur].decode("utf-16le", errors="ignore").split(".")[0].lower())
    return stems


def force_lod0_material_textures(flv, available=None):
    """
    Rewrites distant low-res texture paths (*_a_l, *_n_l, *_r_l, *_s_l) in FLVER materials to their
    primary LOD0 counterparts (*_a, *_n, *_r, *_s).
    If `available` (set of texture stems present in the map's BXFs) is given, a path is only rewritten
    when the LOD0 target actually exists there; otherwise the material would point at a missing texture
    and render as a hole.
    """
    for m in flv.meshes:
        if not m.material:
            continue
        for tex in getattr(m.material, "textures", []):
            p = getattr(tex, "path", "") or ""
            low_p = p.lower()
            new_p = None
            for suf in ("_a_l", "_n_l", "_r_l", "_s_l"):
                if low_p.endswith(suf):
                    new_p = p[:-2]
                    break
                elif f"{suf}." in low_p:
                    idx = low_p.rfind(f"{suf}.")
                    new_p = p[: idx + 2] + p[idx + 4:]
                    break
            if new_p is None:
                continue
            if available is not None and _tex_stem(new_p) not in available:
                continue
            tex.path = new_p


def decode_bc5_to_rg(linear_bytes: bytes, pad_w: int, pad_h: int) -> Tuple[np.ndarray, np.ndarray]:
    bw, bh = pad_w // 4, pad_h // 4
    num_blocks = bw * bh
    raw = np.frombuffer(linear_bytes, dtype=np.uint8)[: num_blocks * 16].reshape(num_blocks, 16)
    r_blocks = np.ascontiguousarray(raw[:, :8]).tobytes()
    g_blocks = np.ascontiguousarray(raw[:, 8:16]).tobytes()
    return decode_bc4(r_blocks, pad_w, pad_h), decode_bc4(g_blocks, pad_w, pad_h)


def encode_rg_to_bc5(r_img: np.ndarray, g_img: np.ndarray) -> bytes:
    r_blocks = np.frombuffer(encode_bc4(r_img), dtype=np.uint8).reshape(-1, 8)
    g_blocks = np.frombuffer(encode_bc4(g_img), dtype=np.uint8).reshape(-1, 8)
    return np.hstack([r_blocks, g_blocks]).tobytes()


def downsample_env_tpf_same_size(
    tpf_bytes: bytes,
    target_dim: int = 32,
    is_normal: bool = False,
    is_specular_s: bool = False,
    chunky_nearest: bool = True,
    is_foliage: bool = False,
) -> bytearray:
    """
    Downsamples a single-texture environment TPF to target_dim and upsamples back across the
    exact original mip chain so len(tpf_new) == len(tpf_bytes) and header dimensions stay intact.
    """
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b"TPF\x00":
        return tpf

    tex_off, tex_sz, unk1, w0, h0, dxgi = tpf_entry_info(tpf)
    kind = DXGI_KIND.get(dxgi)
    if kind is None:
        return tpf          # BC3 / BC6H / BC7 / unknown: byte-identical

    bpb = 16 if kind == "bc5" else 8
    mips = get_mip_sizes(w0, h0, bpb)
    if not mips or tex_off + mips[0][4] > len(tpf):
        return tpf

    scale = min(1.0, target_dim / max(w0, h0))
    retro_w = max(8, int(round(w0 * scale)))
    retro_h = max(8, int(round(h0 * scale)))

    _, _, pw0, ph0, sz0 = mips[0]
    linear0 = deswizzle_level(bytes(tpf[tex_off : tex_off + sz0]), w0, h0, bpb)

    out_buf = bytearray(tex_sz)
    curr_off = 0
    upscale_filter = Image.Resampling.NEAREST if chunky_nearest else Image.Resampling.BILINEAR

    if kind == "bc5":
        r0, g0 = decode_bc5_to_rg(linear0, pw0, ph0)
        im_r = Image.fromarray(r0[:h0, :w0]).resize((retro_w, retro_h), Image.Resampling.BILINEAR)
        im_g = Image.fromarray(g0[:h0, :w0]).resize((retro_w, retro_h), Image.Resampling.BILINEAR)

        for wi, hi, pwi, phi, szi in mips:
            if curr_off + szi > tex_sz:
                break
            mr = np.array(im_r.resize((wi, hi), Image.Resampling.BILINEAR))
            mg = np.array(im_g.resize((wi, hi), Image.Resampling.BILINEAR))
            pad_r = np.full((phi, pwi), 128, dtype=np.uint8)
            pad_g = np.full((phi, pwi), 128, dtype=np.uint8)
            pad_r[:hi, :wi] = mr
            pad_g[:hi, :wi] = mg
            if pwi > wi:
                pad_r[:hi, wi:pwi] = mr[:, -1:]
                pad_g[:hi, wi:pwi] = mg[:, -1:]
            if phi > hi:
                pad_r[hi:phi, :] = pad_r[hi - 1 : hi, :]
                pad_g[hi:phi, :] = pad_g[hi - 1 : hi, :]

            lin = encode_rg_to_bc5(pad_r, pad_g)
            out_buf[curr_off : curr_off + szi] = swizzle_level(lin, wi, hi, 16)
            curr_off += szi

    elif kind == "bc4":
        gray0 = decode_bc4(linear0, pw0, ph0)[:h0, :w0]
        im_down = Image.fromarray(gray0).resize((retro_w, retro_h), Image.Resampling.BILINEAR)
        im_quant = Image.fromarray((np.array(im_down) >> 3) << 3)

        for wi, hi, pwi, phi, szi in mips:
            if curr_off + szi > tex_sz:
                break
            arr_m = np.array(im_quant.resize((wi, hi), upscale_filter))
            pad_arr = np.zeros((phi, pwi), dtype=np.uint8)
            pad_arr[:hi, :wi] = arr_m
            if pwi > wi:
                pad_arr[:hi, wi:pwi] = arr_m[:, -1:]
            if phi > hi:
                pad_arr[hi:phi, :] = pad_arr[hi - 1 : hi, :]
            out_buf[curr_off : curr_off + szi] = swizzle_level(encode_bc4(pad_arr), wi, hi, 8)
            curr_off += szi

    elif kind == "bc1":
        rgba0 = decode_bc1_to_rgba(linear0, pw0, ph0)[:h0, :w0]
        has_cutout = (rgba0[:, :, 3] < 128).any()
        if has_cutout and not is_foliage:
            return tpf      # 1-bit alpha cutout (grates, banners, ...): keep vanilla unless foliage

        im_down = Image.fromarray(rgba0).resize((retro_w, retro_h), Image.Resampling.BILINEAR)
        arr_down = np.array(im_down)
        if has_cutout and is_foliage:
            # Crisp alpha thresholding for foliage cutout cards
            arr_down[:, :, 3] = np.where(arr_down[:, :, 3] >= 100, 255, 0).astype(np.uint8)

        if is_foliage and not is_normal:
            # Bloodborne vegetation diffuse is naturally very dark (~13% raw brightness).
            # Apply gentle brightness lift so 15-bit quantization doesn't crush foliage into pitch black shadows.
            veg_f = arr_down[:, :, :3].astype(np.float32) * 1.35
            arr_down[:, :, :3] = (np.clip(veg_f, 0, 255).astype(np.uint8) >> 3) << 3
        elif not is_normal:
            arr_down[:, :, :3] = (arr_down[:, :, :3] >> 3) << 3

        im_quant = Image.fromarray(arr_down)

        for wi, hi, pwi, phi, szi in mips:
            if curr_off + szi > tex_sz:
                break
            arr_m = np.array(im_quant.resize((wi, hi), upscale_filter))
            if has_cutout and is_foliage:
                arr_m[:, :, 3] = np.where(arr_m[:, :, 3] >= 100, 255, 0).astype(np.uint8)
            elif not is_normal:
                arr_m[:, :, :3] = (arr_m[:, :, :3] >> 3) << 3

            pad_arr = np.zeros((phi, pwi, 4), dtype=np.uint8)
            pad_arr[:hi, :wi] = arr_m
            if pwi > wi:
                pad_arr[:hi, wi:pwi] = arr_m[:, -1:, :]
            if phi > hi:
                pad_arr[hi:phi, :] = pad_arr[hi - 1 : hi, :]
            out_buf[curr_off : curr_off + szi] = swizzle_level(encode_rgba_to_bc1(pad_arr), wi, hi, 8)
            curr_off += szi
    else:
        return tpf

    if curr_off == tex_sz:
        tpf[tex_off : tex_off + tex_sz] = out_buf
    return tpf


def promote_map_flvers(
    file_list: List[str],
    map_id: str = "m21",
    target_lod: int = 2,
    hybrid: bool = True,
    qem_ratio: float = 0.50,
    dry_run: bool = False,
    lod0_mode: str = "check",
):
    """
    Processes map FLVER geometry while enforcing LOD0 highest-rendered material bindings:
    - Rewrites any *_l distant material texture references to bind the primary LOD0 texture.
    - If target_lod == 0: Decimates the true LOD0 FaceSet[0] geometry using QEM (preserving FaceSets 1..N).
    - If target_lod in (1, 2): Promotes native LodLevel1/LodLevel2 into FaceSet[0] with a 25% triangle floor guard.
    """
    if not file_list:
        return

    mode_str = (
        f"Direct LOD0 QEM ({qem_ratio*100:.0f}%)"
        if target_lod == 0
        else ("Hybrid (Landmarks LOD1, Background LOD2, Sky Vanilla)" if hybrid else f"Uniform LOD{target_lod}")
    )
    print(f"\n--- Processing {len(file_list)} Map FLVER files for {map_id.upper()} ({mode_str}) ---")
    if target_lod == 0:
        print(
            "  [WARNING] --lod 0 runs the character decimator on WORLD geometry. It resets every vertex's color_0 to\n"
            "            white, recomputes normals/tangents and rewrites uv_1+; baked vertex shading, ground blending and\n"
            "            DOL-lit columns (workshop pillars) can break. Native --lod 1/2 only swaps FaceSet indices and is\n"
            "            the path validated in Tests 21-29."
        )

    success_count = 0
    sky_skipped = 0
    total_orig = 0
    total_new = 0
    available = collect_map_texture_stems(map_id) if lod0_mode == "check" else None

    for idx, src_path in enumerate(file_list, 1):
        src_p = Path(src_path)
        block_name = src_p.parent.name
        filename = src_p.name
        dest_dir = SANDBOX_ROOT / "map" / block_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        try:
            flv = FLVER.from_path(src_path)

            if is_sky_or_celestial_flver(flv, filename):
                if not dry_run:
                    copy_reflink(src_p, dest_path)
                tris = sum(len(m.face_sets[0].vertex_indices) // 3 for m in flv.meshes if m.face_sets)
                total_orig += tris
                total_new += tris
                sky_skipped += 1
                success_count += 1
                continue

            # Bind highest-detail LOD0 material texture slots (check = only when the target texture exists)
            if lod0_mode != "off":
                force_lod0_material_textures(flv, available)

            if target_lod == 0:
                # Save original DOL shadow/lightmap FaceSets 1..N before QEM
                saved_aux_fs = [
                    [fs.vertex_indices.copy() for fs in m.face_sets[1:]]
                    for m in flv.meshes
                ]
                file_orig, file_new = decimate_flver(
                    flv,
                    target_ratio=qem_ratio,
                    flat_normals=False,
                    disable_cloth=False,
                    preserve_border=True,
                    filename=filename,
                )
                # Restore auxiliary FaceSets if vertex count permits, otherwise keep synchronized FS0
                for mi, m in enumerate(flv.meshes):
                    max_v = len(m.vertex_arrays[0].array) if m.vertex_arrays else 0
                    for fsi, orig_indices in enumerate(saved_aux_fs[mi], start=1):
                        if fsi < len(m.face_sets) and len(orig_indices) > 0 and orig_indices.max() < max_v:
                            m.face_sets[fsi].vertex_indices = orig_indices
            else:
                file_orig = 0
                file_new = 0

                if map_id == "m21":
                    is_landmark = any(f"0010{x:02d}" in filename for x in range(0, 36)) or "001000" in filename
                else:
                    idx_str = filename.split("_")[-1].split(".")[0]
                    idx_num = int(idx_str) if idx_str.isdigit() else 0
                    is_landmark = idx_num < 8000
                effective_lod = 1 if (hybrid and is_landmark) else target_lod

                for m in flv.meshes:
                    if not m.face_sets or len(m.vertex_arrays) == 0:
                        continue

                    orig_tris = len(m.face_sets[0].vertex_indices) // 3
                    file_orig += orig_tris

                    mat_name = m.material.name.lower() if m.material and m.material.name else ""
                    mtd_name = m.material.mat_def_name.lower() if m.material and m.material.mat_def_name else ""
                    if any(k in mat_name or k in mtd_name for k in SKY_FLVER_KEYWORDS):
                        file_new += orig_tris
                        continue

                    is_foliage = any(k in mat_name or k in mtd_name for k in FOLIAGE_KEYWORDS)
                    # Foliage LOD2 is authored at ~19-20% tris. Buildings/props floor is 25%.
                    floor_pct = 0.15 if is_foliage else 0.25

                    target_fs = None
                    for fs in m.face_sets:
                        if fs.flags == effective_lod and len(fs.vertex_indices) > 0:
                            if len(fs.vertex_indices) // 3 >= max(24, int(orig_tris * floor_pct)):
                                target_fs = fs
                            break
                    if target_fs is None and effective_lod == 2:
                        for fs in m.face_sets:
                            if fs.flags == 1 and len(fs.vertex_indices) > 0:
                                if len(fs.vertex_indices) // 3 >= max(24, int(orig_tris * 0.25)):
                                    target_fs = fs
                                break

                    if target_fs is not None:
                        m.face_sets[0].vertex_indices = target_fs.vertex_indices.copy()
                        file_new += len(target_fs.vertex_indices) // 3
                    else:
                        file_new += orig_tris

            total_orig += file_orig
            total_new += file_new

            if not dry_run:
                # Avoid Soulstruct creating .bak files inside the sandbox
                flv.write(dest_path)
                bak_file = dest_path.with_suffix(dest_path.suffix + ".bak")
                if bak_file.exists():
                    bak_file.unlink()

            success_count += 1
        except Exception as e:
            print(f"[ERROR] Failed {filename}: {e}")

    overall_pct = (total_new / max(1, total_orig)) * 100 if total_orig else 0
    print(
        f"FLVER Summary ({map_id.upper()}): {success_count}/{len(file_list)} passed "
        f"({sky_skipped} sky FLVERs kept vanilla). Overall tris: {total_orig:,} -> {total_new:,} ({overall_pct:.1f}%)"
    )


def demake_bxf_archive_inplace(
    bhd_name: str,
    bdt_name: str,
    map_id: str = "m21",
    target_dim: int = 32,
    downsample_pbr: bool = False,
    chunky_nearest: bool = True,
    dry_run: bool = False,
    demake_foliage: bool = True,
    foliage_dim: int = 64,
):
    """
    Surgically demakes BXF texture archive using zero-bloat in-place slot overwrite.
    Always processes LOD0 textures first so any *_l distant texture slot receives the crisp
    LOD0-derived retro texture rather than doubly-blurred distant mips.
    """
    src_bhd = VANILLA_ROOT / "map" / map_id / bhd_name
    src_bdt = VANILLA_ROOT / "map" / map_id / bdt_name
    dest_bhd = SANDBOX_ROOT / "map" / map_id / bhd_name
    dest_bdt = SANDBOX_ROOT / "map" / map_id / bdt_name
    if not src_bhd.exists() or not src_bdt.exists():
        return
    dest_bhd.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"--- In-Place Demaking BXF Binder: {map_id}/{bhd_name} "
        f"(Albedo: {target_dim}px, Foliage: {foliage_dim}px, Downsample PBR: {downsample_pbr}) ---"
    )
    start_t = time.time()

    bhd_data = bytearray(src_bhd.read_bytes())
    bdt_data = bytearray(src_bdt.read_bytes())
    count = struct.unpack("<I", bhd_data[12:16])[0]

    demade_count = 0
    inplace_count = 0
    append_count = 0
    orig_total_sz = 0
    new_total_sz = 0

    for i in range(count):
        rec_off = 0x40 + i * 36
        name_off = struct.unpack("<I", bhd_data[rec_off + 32 : rec_off + 36])[0]
        curr = name_off
        while curr < len(bhd_data) - 1:
            if bhd_data[curr] == 0 and bhd_data[curr + 1] == 0:
                break
            curr += 2
        name = bhd_data[name_off:curr].decode("utf-16le", errors="ignore")
        low = name.lower()

        if is_celestial_or_lightmap(low) or any(
            low.endswith(x) for x in ("_m.tpf.dcx", "_m_l.tpf.dcx", "_m.tpf.dc", "_m_l.tpf.dc")
        ):
            continue

        is_foliage = is_foliage_name(low)
        if not demake_foliage and is_foliage:
            continue

        is_albedo = any(low.endswith(x) for x in ("_a.tpf.dcx", "_a_l.tpf.dcx", "_a.tpf.dc", "_a_l.tpf.dc"))
        is_normal = any(low.endswith(x) for x in ("_n.tpf.dcx", "_n_l.tpf.dcx", "_n.tpf.dc", "_n_l.tpf.dc"))
        is_specular_r = any(low.endswith(x) for x in ("_r.tpf.dcx", "_r_l.tpf.dcx", "_r.tpf.dc", "_r_l.tpf.dc"))
        is_specular_s = any(low.endswith(x) for x in ("_s.tpf.dcx", "_s_l.tpf.dcx", "_s.tpf.dc", "_s_l.tpf.dc"))
        is_carpet = "carpet" in low

        comp_sz = struct.unpack("<Q", bhd_data[rec_off + 8 : rec_off + 16])[0]
        data_off = struct.unpack("<I", bhd_data[rec_off + 24 : rec_off + 28])[0]
        entry_id = struct.unpack("<I", bhd_data[rec_off + 28 : rec_off + 32])[0]

        recomp = None

        if is_carpet:
            orig_bytes = bytes(bdt_data[data_off : data_off + comp_sz])
            tpf_decomp, dcx_type = decompress(orig_bytes)
            if is_albedo:
                demade = downsample_env_tpf_same_size(tpf_decomp, target_dim=128, is_normal=False, chunky_nearest=False)
                recomp = compress(bytes(demade), dcx_type)
            elif is_normal:
                tpf = bytearray(tpf_decomp)
                tex_off, tex_sz, _u1, _w, _h, dxgi = tpf_entry_info(tpf)
                kind = DXGI_KIND.get(dxgi)
                if kind == "bc5":
                    tpf[tex_off : tex_off + tex_sz] = FLAT_NORMAL_BC5_UNORM * (tex_sz // 16)
                    recomp = compress(bytes(tpf), dcx_type)
                elif kind == "bc1":
                    tpf[tex_off : tex_off + tex_sz] = FLAT_NORMAL_BC1 * (tex_sz // 8)
                    recomp = compress(bytes(tpf), dcx_type)
                # BC7/BC6H/other normals: flat BC1/BC5 blocks would be garbage there -> leave vanilla
            elif is_specular_r or is_specular_s:
                tpf = bytearray(tpf_decomp)
                tex_off, tex_sz, _u1, _w, _h, dxgi = tpf_entry_info(tpf)
                if DXGI_KIND.get(dxgi) in ("bc1", "bc4"):
                    tpf[tex_off : tex_off + tex_sz] = b"\x00" * tex_sz
                    recomp = compress(bytes(tpf), dcx_type)

        elif is_albedo:
            orig_bytes = bytes(bdt_data[data_off : data_off + comp_sz])
            tpf_decomp, dcx_type = decompress(orig_bytes)
            dim_to_use = foliage_dim if is_foliage else target_dim
            demade = downsample_env_tpf_same_size(
                tpf_decomp, target_dim=dim_to_use, is_normal=False, chunky_nearest=chunky_nearest, is_foliage=is_foliage
            )
            recomp = compress(bytes(demade), dcx_type)

        elif downsample_pbr and (is_normal or is_specular_r or is_specular_s):
            orig_bytes = bytes(bdt_data[data_off : data_off + comp_sz])
            tpf_decomp, dcx_type = decompress(orig_bytes)
            demade = downsample_env_tpf_same_size(
                tpf_decomp,
                target_dim=target_dim,
                is_normal=is_normal,
                is_specular_s=is_specular_s,
                chunky_nearest=False,
            )
            recomp = compress(bytes(demade), dcx_type)

        if recomp is not None:
            if len(recomp) <= comp_sz:
                bdt_data[data_off : data_off + len(recomp)] = recomp
                if len(recomp) < comp_sz:
                    bdt_data[data_off + len(recomp) : data_off + comp_sz] = b"\x00" * (comp_sz - len(recomp))
                bhd_data[rec_off + 8 : rec_off + 16] = struct.pack("<Q", len(recomp))
                bhd_data[rec_off + 16 : rec_off + 24] = struct.pack("<Q", len(recomp))
                inplace_count += 1
            else:
                new_data_off = (len(bdt_data) + 15) & ~15
                bdt_data.extend(b"\x00" * (new_data_off - len(bdt_data)))
                bdt_data.extend(recomp)
                bhd_data[rec_off + 8 : rec_off + 16] = struct.pack("<Q", len(recomp))
                bhd_data[rec_off + 16 : rec_off + 24] = struct.pack("<Q", len(recomp))
                bhd_data[rec_off + 24 : rec_off + 32] = struct.pack("<2I", new_data_off, entry_id)
                append_count += 1

            demade_count += 1
            orig_total_sz += comp_sz
            new_total_sz += len(recomp)

    elapsed = time.time() - start_t
    if orig_total_sz > 0:
        pct = (1 - new_total_sz / orig_total_sz) * 100
        print(
            f"  -> Demade {demade_count} textures in {elapsed:.1f}s "
            f"({orig_total_sz/1024/1024:.2f} MB -> {new_total_sz/1024/1024:.2f} MB, -{pct:.1f}%, "
            f"In-place: {inplace_count}, Appends: {append_count})"
        )

    if not dry_run:
        dest_bhd.write_bytes(bhd_data)
        dest_bdt.write_bytes(bdt_data)


def demake_object_binder(src_path, dest_path, ratio: float, dim: int, mesh_mode: str):
    """
    Same as auto_demake_file for obj/*.objbnd.dcx, but with a mesh guard:
      safe (default): FLVERs with more than one bone (doors, ladders, coffins, levers...) keep their vanilla
                      mesh; their bone binding is what exploded when decimated.
      all           : decimate everything (old behaviour)
      none          : textures only
    Returns number of (decimated, kept) FLVERs.
    """
    from auto_demake_engine import process_tpf_data
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER as ObjFLVER

    binder = Binder.from_path(str(src_path))
    done = kept = 0
    for entry in binder.entries:
        if entry.name.endswith(".flver"):
            raw = entry.get_uncompressed_data()
            if len(raw) <= 0x100 or mesh_mode == "none":
                kept += 1
                continue
            flv = ObjFLVER.from_bytes(raw)
            if is_sky_or_celestial_flver(flv, entry.name) or (mesh_mode == "safe" and len(flv.bones) > 1):
                kept += 1
                continue
            decimate_flver(flv, target_ratio=ratio, flat_normals=False, disable_cloth=False)
            entry.set_uncompressed_data(flv.to_bytes())
            done += 1
        elif entry.name.endswith(".tpf"):
            entry.set_uncompressed_data(bytes(process_tpf_data(entry.get_uncompressed_data(), target_dim=dim)))
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    binder.write(str(dest_path))
    return done, kept


def demake_map_objects(map_id: str = "m21", target_ratio: float = 0.50, target_dim: int = 64, dry_run: bool = False,
                       mesh_mode: str = "safe"):
    prefix = f"o{map_id[1:3]}"
    obj_files = sorted(glob.glob(str(VANILLA_ROOT / "obj" / f"{prefix}*.objbnd.dcx")))
    if not obj_files:
        return

    print(f"\n--- Demaking {len(obj_files)} Map Object Binders ({prefix}*.objbnd.dcx) ---")
    dest_dir = SANDBOX_ROOT / "obj"
    dest_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    tot_done = tot_kept = 0
    for src_str in obj_files:
        src_path = Path(src_str)
        dest_path = dest_dir / src_path.name
        if dry_run:
            ok_count += 1
            continue
        try:
            d, k = demake_object_binder(src_path, dest_path, target_ratio, target_dim, mesh_mode)
            tot_done += d
            tot_kept += k
            ok_count += 1
            bak_file = dest_path.with_suffix(dest_path.suffix + ".bak")
            if bak_file.exists():
                bak_file.unlink()
        except Exception as e:
            print(f"  [WARN] Fallback to vanilla for {src_path.name}: {e}")
            copy_reflink(src_path, dest_path)
    print(f"Map Objects Summary ({map_id.upper()}): {ok_count}/{len(obj_files)} processed "
          f"({tot_done} meshes decimated, {tot_kept} kept vanilla; mesh mode: {mesh_mode}).")


def get_safe_binders_for_map(map_id: str, include_secondary_m21: bool = False) -> List[str]:
    """
    Returns BXF binders for map_id.
    Respects Test 24: m21_0001..0003 contain global sky dome ambient lighting and must stay vanilla
    unless explicitly overridden, whereas urban/dungeon maps (m20, m22..m36) store standard architectural
    albedos across all 0000..0003 binders.
    """
    map_folder = VANILLA_ROOT / "map" / map_id
    if not map_folder.exists():
        return []
    if map_id == "m21" and not include_secondary_m21:
        return ["m21_0000"] if (map_folder / "m21_0000.tpfbhd").exists() else []
    return sorted([
        p.stem for p in map_folder.glob(f"{map_id}_*.tpfbhd")
        if "env" not in p.stem.lower() and "gi_" not in p.stem.lower()
    ])


def main():
    parser = argparse.ArgumentParser(description="Master Batch PSX Demake for All Bloodborne Environment Maps")
    parser.add_argument(
        "--map",
        nargs="+",
        default=["all"],
        help="Map ID(s) to demake (e.g. m21 m22 m29, or 'all' for every map in the game; default: all)",
    )
    parser.add_argument("--flvers", action="store_true", help="Process map FLVER geometry & force LOD0 materials")
    parser.add_argument("--textures", action="store_true", help="Demake environment BXF texture archives")
    parser.add_argument("--objects", action="store_true", help="Demake map-specific obj/oXX*.objbnd.dcx props")
    parser.add_argument("--all", action="store_true", help="Run FLVER geometry, BXF textures, and map objects")
    parser.add_argument(
        "--lod",
        type=int,
        choices=[0, 1, 2],
        default=2,
        help="0 = Direct QEM decimation on LOD0 FaceSet 0; 1 = Native LOD1 (~50%%); 2 = Hybrid LOD1/LOD2 (default)",
    )
    parser.add_argument("--qem-ratio", type=float, default=0.50, help="Target ratio when --lod 0 is used (default: 0.50)")
    parser.add_argument("--uniform-lod", action="store_true", help="Disable hybrid LOD when --lod 1 or 2 is used")
    parser.add_argument("--dim", type=int, default=32, help="Texture target dim for architecture (default 32px)")
    parser.add_argument(
        "--downsample-pbr",
        action="store_true",
        help="Also downsample _n/_r/_s maps (auto-enabled on heavy city maps like m22/m24 unless --m21)",
    )
    parser.add_argument("--object-mesh", choices=["safe", "all", "none"], default="safe",
                        help="map objects: safe = keep multi-bone (animated) meshes vanilla, all = decimate everything, "
                             "none = textures only (default: safe)")
    parser.add_argument("--lod0-textures", choices=["check", "always", "off"], default="check",
                        help="rewrite *_l material texture paths to LOD0: check = only if the LOD0 texture exists in the "
                             "map BXFs (default), always = old behaviour, off = never")
    parser.add_argument("--binders", nargs="+", default=None, help="Explicit BXF binders (auto-detected if None)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing files")
    parser.add_argument("--clean", action="store_true", help="Restore target map(s) to pristine vanilla before running")
    parser.add_argument(
        "--demake-foliage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Demake vegetation/foliage/flower diffuse textures and promote foliage LODs (default: True)",
    )
    parser.add_argument(
        "--foliage-dim",
        type=int,
        default=64,
        help="Target dimension for foliage/flower textures (default: 64px to preserve cutout silhouette)",
    )

    args = parser.parse_args()

    target_maps = discover_all_map_ids() if ("all" in args.map) else args.map
    default_run = not (args.flvers or args.textures or args.objects)
    run_flvers = args.all or args.flvers or default_run
    run_textures = args.all or args.textures or default_run
    run_objects = args.all or args.objects

    print("=================================================================")
    print(f">>> MASTER ENVIRONMENT PSX DEMAKE: {len(target_maps)} MAP(S) -> {', '.join(target_maps)} <<<")
    print("=================================================================")

    for map_id in target_maps:
        if args.clean:
            restore_map_sandbox(map_id)

        if run_flvers:
            all_flvers = sorted(glob.glob(str(VANILLA_ROOT / "map" / f"{map_id}_*" / "*.flver.dcx")))
            if all_flvers:
                promote_map_flvers(
                    all_flvers,
                    map_id=map_id,
                    target_lod=args.lod,
                    hybrid=not args.uniform_lod,
                    qem_ratio=args.qem_ratio,
                    dry_run=args.dry_run,
                    lod0_mode=args.lod0_textures,
                )

        if run_textures:
            binders = args.binders if args.binders is not None else get_safe_binders_for_map(map_id)
            # Keep m21 normal maps vanilla so DOL workshop columns never turn black (Test 23),
            # while allowing PBR downsampling on heavy city vistas if requested
            use_pbr_down = args.downsample_pbr and (map_id != "m21")
            for b in binders:
                demake_bxf_archive_inplace(
                    f"{b}.tpfbhd",
                    f"{b}.tpfbdt",
                    map_id=map_id,
                    target_dim=args.dim,
                    downsample_pbr=use_pbr_down,
                    dry_run=args.dry_run,
                    demake_foliage=args.demake_foliage,
                    foliage_dim=args.foliage_dim,
                )

        if run_objects:
            demake_map_objects(map_id=map_id, target_ratio=0.50, target_dim=64, dry_run=args.dry_run,
                               mesh_mode=args.object_mesh)

    # Clear bbhost Vulkan cache and stray .bak files once at the end
    for bak in SANDBOX_ROOT.rglob("*.bak"):
        try:
            bak.unlink()
        except Exception:
            pass

    cache_dir = Path.home() / ".local/share/bbhost/data/bbhost"
    cleared = 0
    for bin_file in cache_dir.glob("*.bin"):
        try:
            bin_file.unlink()
            cleared += 1
        except Exception:
            pass
    print(f"\nCleared {cleared} bbhost Vulkan pipeline caches and removed stray .bak files.")
    print("[ALL ENVIRONMENT TASKS COMPLETED SUCCESSFULLY]")


if __name__ == "__main__":
    main()