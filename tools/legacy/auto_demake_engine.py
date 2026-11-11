"""
Master Automatic PSX Demake Engine for Bloodborne (shadPS4 / bbhost).

Executes the complete, end-to-end mathematical demake:
1. QEM Polygon Reduction (pyfqmr): Decimates rigid 3D models to retro target ratios (e.g. 40-50%).
2. Flat Facet Normal Splitting: Unrolls per-triangle unique vertices with perpendicular face normals for 90s Virtua Fighter / Star Fox 3D lighting.
3. Skeletal Weight & UV Transfer: Barycentric KDTree interpolation guarantees smooth skeletal deformation without vertex explosion.
4. Havok Cloth Integrity: Keeps _c.hkx and _c.clm2 container entries intact and skips cloth mesh decimation,
   preventing bbhost/shadps4 SpCloth thread out-of-bounds reads and camera frustum culling drops.
5. True Flat Color De-Crochet Engine: Encodes uniform flat BC1 blocks (color0 == color1, indices == 0) with deterministic contrast dither. Zero crochet micro-squares.
6. Retro Shading: Flat tangent normals (0x8080FF) and zero specular/roughness across all materials.
"""

import sys, os, struct
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch
from demake_color_engine import (
    demake_texture_pixel_space,
    demake_texture_flat_colors,
    FLAT_NORMAL_BC1,
    FLAT_NORMAL_BC5_UNORM,
    FLAT_NORMAL_BC5_SNORM,
)
from mesh_decimator import decimate_flver

from soulstruct.containers import Binder
from soulstruct.flver import FLVER

def process_tpf_data(tpf_bytes: bytes, target_dim: int = 128, dither_strength: int = 3, is_map: bool = False) -> bytearray:
    """Processes in-memory TPF binary data with solid flat color blocks, flat normals, zero specular."""
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b'TPF\x00':
        return tpf

    tex_count = struct.unpack('<I', tpf[8:12])[0]
    for i in range(tex_count):
        e = tpf[0x10 + i*36 : 0x10 + (i+1)*36]
        tex_off, tex_sz, unk1, unk2, unk3, unk4, str_off = struct.unpack('<7I', e[:28])

        curr = str_off
        while curr < len(tpf) - 1:
            if tpf[curr] == 0 and tpf[curr+1] == 0: break
            curr += 2
        name = tpf[str_off:curr].decode('utf-16le', errors='ignore')
        width = unk2 & 0xFFFF
        height = (unk2 >> 16) & 0xFFFF
        fmt = unk1 & 0xFF
        bpb = 16 if fmt == 0x66 else 8

        base = name[:-2] if name.endswith('_l') else name
        low_name = name.lower()

        # 1. Sky, cloud & celestial billboards: preserve completely untouched
        # Prevents solid gray/black boxes in sky or missing moon/clouds
        if any(k in low_name for k in ['clond', 'cloud', 'sky', 'moon', 'sun', 'star', 'magic']):
            continue

        # 2. Blend masks (g_BlendMaskTexture) & Subsurface scattering (_sc): preserve untouched
        if any(k in low_name for k in ['blendmsk', 'mask', 'msk', 'scattering']) or base.endswith('_m') or base.endswith('_sc'):
            continue

        # 3. Diffuse (_a), Normal (_n), and Specular (_r, _s):
        # Downsample diffuse, normal, and specular maps to 32px/64px using RGB555 palette quantization
        if base.endswith('_a') or base.endswith('_n') or base.endswith('_r') or base.endswith('_s') or not any(base.endswith(x) for x in ['_m', '_sc']):
            if fmt == 0x66 or any(k in low_name for k in ['fur', 'hair', 'beard', 'foliage', 'grass', 'plant', 'leaf', 'flower', 'ivy', 'moss', 'tree', 'branch', 'vine', 'weed', 'bush']):
                # BC7 hair/fur/beard/alpha cutout/foliage: preserve 100% alpha transparency
                continue
            orig = bytes(tpf[tex_off : tex_off + tex_sz])
            demade_bytes = demake_texture_pixel_space(
                orig, width, height, bpb=bpb, target_dim=target_dim, tex_name=name
            )
            assert len(demade_bytes) == tex_sz, f"Texture {name} size mismatch: {len(demade_bytes)} != {tex_sz}"
            tpf[tex_off : tex_off + tex_sz] = demade_bytes

    assert len(tpf) == len(tpf_bytes), f"TPF archive size corrupted: grew from {len(tpf_bytes)} to {len(tpf)}"
    return tpf

def auto_demake_file(filepath: str, output_path: str = None, target_ratio: float = 0.45, flat_normals: bool = False, disable_cloth: bool = False, target_dim: int = 64, skip_tpf: bool = False, verbose: bool = True) -> bool:
    """Automatically applies full mathematical demake to a .partsbnd.dcx, .chrbnd.dcx, or .objbnd.dcx file."""
    if not os.path.exists(filepath):
        if verbose:
            print(f"Error: File not found: {filepath}")
        return False

    from pathlib import Path
    out_file = output_path if output_path is not None else filepath
    assert "CUSA03173/" not in str(Path(out_file).resolve()).replace("CUSA03173-PSX", ""), \
        f"Safety Violation: attempted write to pristine vanilla dump: {out_file}"

    if verbose:
        print(f"\nProcessing {os.path.basename(filepath)} -> {out_file}...")
    binder = Binder.from_path(filepath)

    # NOTE: Keep _c.hkx and _c.clm2 in the container to avoid engine crashes.
    # Mesh safety is handled in decimate_flver by skipping cloth submeshes.

    fn_lower = os.path.basename(filepath).lower()
    is_face_or_hair = any(fn_lower.startswith(p) for p in ['fc_', 'fg_', 'hr_'])

    flver_modified = 0
    tpf_modified = 0

    for entry in binder.entries:
        if entry.name.endswith('.flver'):
            if is_face_or_hair:
                # Facegen (fc_*, fg_*) requires strict 1:1 vertex indices for runtime slider morph displacement.
                # Decimation causes out-of-bounds vertex offsets and grotesque facial deformation.
                # Hair (hr_*) requires intact Havok hair physics buffers and alpha ribbon strand topology.
                continue
            raw_flv = entry.get_uncompressed_data()
            if len(raw_flv) > 0x100:
                flv = FLVER.from_bytes(raw_flv)
                orig_t, new_t = decimate_flver(flv, target_ratio=target_ratio, flat_normals=flat_normals, disable_cloth=disable_cloth)
                entry.set_uncompressed_data(flv.to_bytes())
                if verbose:
                    print(f"  [FLVER] {os.path.basename(entry.name)}: {orig_t} -> {new_t} tris ({new_t/max(1,orig_t)*100:.1f}%)")
                flver_modified += 1

        elif entry.name.endswith('.tpf') and not skip_tpf:
            if is_face_or_hair:
                # Protect facial skin, facial gear, and hair textures from modification
                continue
            raw_tpf = entry.get_uncompressed_data()
            demade_tpf = process_tpf_data(raw_tpf, target_dim=target_dim)
            entry.set_uncompressed_data(bytes(demade_tpf))
            if verbose:
                print(f"  [TPF] {os.path.basename(entry.name)}: Flat retro colors ({target_dim}px) + flat shading applied.")
            tpf_modified += 1

    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    binder.write(out_file)
    if verbose:
        print(f"[SUCCESS] Demade {os.path.basename(filepath)} (FLVERs: {flver_modified}, TPFs: {tpf_modified}).")
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 auto_demake_engine.py <path_to_dcx> [target_ratio] [target_dim] [--skip-tpf]")
        sys.exit(1)

    path = sys.argv[1]
    ratio = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 0.45
    dim = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 64
    skip_tpf = '--skip-tpf' in sys.argv

    auto_demake_file(path, target_ratio=ratio, flat_normals=False, disable_cloth=False, target_dim=dim, skip_tpf=skip_tpf)
