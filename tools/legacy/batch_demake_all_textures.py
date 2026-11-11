#!/usr/bin/env python3
"""
tools/batch_demake_all_textures.py: Upgraded Universal Texture Demake Engine for Bloodborne PSX.

Key Upgrades & Mathematical Safeguards:
1. PBR Normal & Specular Protection: Leaves normal maps (_n), specular gloss (_r, _s), and BC6H face maps 
   byte-identical across characters (chr/) and equipment (parts/) to prevent pitch-black metal/skin artifacts (Test 30).
2. Semantic Resolution Scaling: Automatically scales target dimensions by category (chr/parts: 256px, obj: 64px, menu: 128px).
3. Hair & Alpha Cutout Safety: Strictly protects BC7 hair, fur, and 1-bit alpha lace from corruption (Test 12).
4. Strict Invariant: TEXTURES ONLY. Zero mesh, cloth, or collision changes.
"""

import sys
import os
import glob
import time
import shutil
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch  # noqa: E402
from soulstruct.containers import Binder  # noqa: E402
from demake_color_engine import demake_texture_pixel_space  # noqa: E402

VANILLA_ROOT = Path("CUSA03173/dvdroot_ps4")
SANDBOX_ROOT = Path("CUSA03173-PSX/dvdroot_ps4")

# Special preservation rules: Plain Doll has custom reconstructed textures.
SKIP_CHR_FILES = {"c8030.chrbnd.dcx"}


def process_safe_tpf_data(tpf_bytes: bytes, target_dim: int = 256, is_char_or_part: bool = True) -> bytearray:
    """
    Safely processes TPF binary data:
    - Downsamples diffuse albedos (_a) using 15-bit RGB555 pixel-space quantization.
    - STRICTLY PRESERVES normal maps (_n), specular maps (_r, _s), HDR face maps (BC6H 0x6A),
      sky/celestial billboards, blend masks, and hair/fur/beard BC7 textures.
    """
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b'TPF\x00':
        return tpf

    tex_count = int.from_bytes(tpf[8:12], 'little')
    for i in range(tex_count):
        e = tpf[0x10 + i * 36 : 0x10 + (i + 1) * 36]
        tex_off = int.from_bytes(e[0:4], 'little')
        tex_sz = int.from_bytes(e[4:8], 'little')
        unk1 = int.from_bytes(e[8:12], 'little')
        unk2 = int.from_bytes(e[12:16], 'little')
        str_off = int.from_bytes(e[24:28], 'little')

        curr = str_off
        while curr < len(tpf) - 1:
            if tpf[curr] == 0 and tpf[curr + 1] == 0:
                break
            curr += 2
        name = tpf[str_off:curr].decode('utf-16le', errors='ignore')
        width = unk2 & 0xFFFF
        height = (unk2 >> 16) & 0xFFFF
        fmt = unk1 & 0xFF
        bpb = 16 if fmt in (0x66, 0x6A, 0x6C, 0x6D) else 8

        base = name[:-2] if name.endswith('_l') else name
        low_name = name.lower()

        # 1. Sky, cloud & celestial billboards: preserve untouched
        if any(k in low_name for k in ['cloud', 'sky', 'moon', 'sun', 'star', 'magic', 'cosmos']):
            continue

        # 2. Blend masks & subsurface scattering: preserve untouched
        if any(k in low_name for k in ['blendmsk', 'mask', 'msk', 'scattering']) or base.endswith('_m') or base.endswith('_sc'):
            continue

        # 3. For characters (chr/) and equipment (parts/): ONLY demake diffuse albedos (_a or non-suffix).
        # STRICTLY PRESERVE normal maps (_n), specular gloss (_r, _s), and BC6H face maps (0x6A) to prevent black faces/metals.
        if is_char_or_part:
            if not base.endswith('_a') and any(base.endswith(x) for x in ['_n', '_r', '_s', '_m']):
                continue
            if fmt in (0x66, 0x6A) or any(k in low_name for k in ['fur', 'hair', 'beard', 'foliage', 'grass', 'skin_n']):
                continue

        orig = bytes(tpf[tex_off : tex_off + tex_sz])
        demade_bytes = demake_texture_pixel_space(
            orig, width, height, bpb=bpb, target_dim=target_dim, tex_name=name
        )
        if len(demade_bytes) == tex_sz:
            tpf[tex_off : tex_off + tex_sz] = demade_bytes

    assert len(tpf) == len(tpf_bytes), f"TPF archive size corrupted: grew from {len(tpf_bytes)} to {len(tpf)}"
    return tpf


def demake_container_textures(task: tuple[str, str, int, bool]) -> tuple[str, bool, str, float]:
    """Worker function to demake textures inside a container (.chrbnd.dcx, .partsbnd.dcx, .objbnd.dcx)."""
    vanilla_path, sandbox_path, target_dim, is_char_part = task
    filename = os.path.basename(vanilla_path)
    start_t = time.time()

    try:
        assert "CUSA03173/" not in str(Path(sandbox_path).resolve()).replace("CUSA03173-PSX", ""), \
            f"Safety check: attempted write to pristine base game {sandbox_path}"

        Path(sandbox_path).parent.mkdir(parents=True, exist_ok=True)
        base_container_path = sandbox_path if os.path.exists(sandbox_path) else vanilla_path
        binder = Binder.from_path(base_container_path)
        van_binder = Binder.from_path(vanilla_path)
        van_tpfs = {e.name: e.get_uncompressed_data() for e in van_binder.entries if e.name.endswith(".tpf")}

        modified_tpfs = 0

        for entry in binder.entries:
            if entry.name.endswith(".tpf") and entry.name in van_tpfs:
                raw_tpf = van_tpfs[entry.name]
                demade_tpf = process_safe_tpf_data(raw_tpf, target_dim=target_dim, is_char_or_part=is_char_part)
                entry.set_uncompressed_data(bytes(demade_tpf))
                modified_tpfs += 1

        if modified_tpfs > 0:
            binder.write(sandbox_path)
            elapsed = time.time() - start_t
            return (filename, True, f"{modified_tpfs} TPF(s) demade ({target_dim}px)", elapsed)
        else:
            shutil.copy2(vanilla_path, sandbox_path)
            elapsed = time.time() - start_t
            return (filename, True, "Copied (0 TPFs)", elapsed)

    except Exception as e:
        elapsed = time.time() - start_t
        return (filename, False, str(e), elapsed)


def demake_menu_textures(target_dim: int = 128) -> tuple[str, bool, str, float]:
    """Processes common.tpf.dcx icon sprite atlases."""
    start_t = time.time()
    try:
        from demake_ui_engine import demake_ui_file
        van_ui = VANILLA_ROOT / "menu" / "common.tpf.dcx"
        out_ui = SANDBOX_ROOT / "menu" / "common.tpf.dcx"
        out_ui.parent.mkdir(parents=True, exist_ok=True)
        if van_ui.exists():
            success = demake_ui_file(van_ui, out_ui, downscale_factor=2, icons_only=True)
            elapsed = time.time() - start_t
            return ("common.tpf.dcx", success, "UI Icons Demade", elapsed)
        return ("common.tpf.dcx", False, "File not found", time.time() - start_t)
    except Exception as e:
        return ("common.tpf.dcx", False, str(e), time.time() - start_t)


def main():
    parser = argparse.ArgumentParser(description="Upgraded Universal Bloodborne PSX Texture Demake Engine")
    parser.add_argument("--categories", nargs="+", choices=["chr", "parts", "obj", "menu", "all"],
                        default=["parts"], help="Categories to process (default: parts)")
    parser.add_argument("--all", action="store_true", help="Process all categories")
    parser.add_argument("--dim", type=int, default=256, help="Target retro texture dimension in px (default: 256)")
    parser.add_argument("--workers", type=int, default=8, help="Parallel worker threads (default: 8)")
    parser.add_argument("--dry-run", action="store_true", help="List files without modifying")

    args = parser.parse_args()
    cats = ["chr", "parts", "obj", "menu"] if args.all or "all" in args.categories else args.categories

    print("=================================================================")
    print(">>> UPGRADED UNIVERSAL BLOODBORNE PSX TEXTURE DEMAKE ENGINE <<<")
    print(f"Categories: {', '.join(cats)} | Base Dim: {args.dim}px | Workers: {args.workers}")
    print("Policy: Safe Diffuse Demake + PBR Normal/Specular Protection.")
    print("=================================================================\n")

    tasks = []

    # 1. Characters (chr/) - Target 256px, PBR protected
    if "chr" in cats:
        chr_files = sorted(glob.glob(str(VANILLA_ROOT / "chr" / "*.chrbnd.dcx")))
        for f in chr_files:
            fn = os.path.basename(f)
            if fn in SKIP_CHR_FILES:
                continue
            dest = str(SANDBOX_ROOT / "chr" / fn)
            tasks.append((f, dest, min(args.dim, 256), True))

    # 2. Equipment & Parts (parts/) - Target 256px, PBR protected
    if "parts" in cats:
        parts_files = sorted(glob.glob(str(VANILLA_ROOT / "parts" / "*.partsbnd.dcx")))
        for f in parts_files:
            fn = os.path.basename(f)
            dest = str(SANDBOX_ROOT / "parts" / fn)
            tasks.append((f, dest, min(args.dim, 256), True))

    # 3. Scenery Objects (obj/) - Target 64px
    if "obj" in cats:
        obj_files = sorted(glob.glob(str(VANILLA_ROOT / "obj" / "*.objbnd.dcx")))
        for f in obj_files:
            fn = os.path.basename(f)
            dest = str(SANDBOX_ROOT / "obj" / fn)
            tasks.append((f, dest, min(args.dim, 64), False))

    print(f"Total container tasks queued: {len(tasks)}")

    if args.dry_run:
        print("[DRY RUN] Exiting without processing files.")
        return

    success_count = 0
    fail_count = 0
    start_total = time.time()

    if tasks:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_task = {executor.submit(demake_container_textures, t): t for t in tasks}
            for idx, future in enumerate(as_completed(future_to_task), 1):
                fn, ok, msg, el = future.result()
                if ok:
                    success_count += 1
                    status = "[OK]"
                else:
                    fail_count += 1
                    status = "[FAIL]"
                if idx % 20 == 0 or idx == len(tasks) or not ok:
                    print(f"[{idx:4d}/{len(tasks):4d}] {status} {fn:30s} | {msg} ({el:.2f}s)")

    # 4. Menu / UI Textures
    if "menu" in cats:
        print("\nProcessing Menu & UI Icons...")
        fn, ok, msg, el = demake_menu_textures(target_dim=128)
        print(f"[{'OK' if ok else 'FAIL'}] {fn} | {msg} ({el:.2f}s)")
        if ok:
            success_count += 1
        else:
            fail_count += 1

    total_time = time.time() - start_total
    print("\n=================================================================")
    print(f"COMPLETED in {total_time:.1f}s: {success_count} succeeded, {fail_count} failed.")
    print(f"Output Sandbox: {SANDBOX_ROOT}")
    print("=================================================================")


if __name__ == "__main__":
    main()