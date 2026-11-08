#!/usr/bin/env python3
"""
demake_parts_textures.py - Retro Demake & PBR Stripper Engine for Player Equipment Textures (parts/).

Applies:
1. Albedo (_a): 15-bit RGB555 color palette quantization & 128x128 pixel-space downscaling.
2. Normal Maps (_n): Neutralized with flat normal blocks (BC5 [128, 128] / BC1 [128, 128, 255]) to eliminate modern micro-wrinkles.
3. Specular (_r, _s): Zeroed out (b"\x00") to eliminate shiny oily PBR gloss and enforce authentic matte retro surfaces.

Usage:
    uv run python tools/pipeline/demake_parts_textures.py --only "*9000*" --deploy
    uv run python tools/pipeline/demake_parts_textures.py --only "wp_a_1001*" --deploy
    uv run python tools/pipeline/demake_parts_textures.py --all --deploy
"""

import argparse
import fnmatch
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import soulstruct_patch  # noqa: E402
from soulstruct.containers import Binder  # noqa: E402
from demake_color_engine import (  # noqa: E402
    demake_texture_pixel_space,
    FLAT_NORMAL_BC1,
    FLAT_NORMAL_BC5_UNORM,
)

VANILLA_PARTS_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "parts"
SANDBOX_PARTS_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "parts"


def process_single_tpf_bytes(tpf_bytes: bytes, target_dim: int = 128) -> bytearray:
    """Processes in-memory TPF archive, flattening normals, killing specular, and demaking albedos."""
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b"TPF\x00":
        return tpf

    tex_count = int.from_bytes(tpf[8:12], "little")
    for i in range(tex_count):
        e = tpf[0x10 + i * 36 : 0x10 + (i + 1) * 36]
        tex_off = int.from_bytes(e[0:4], "little")
        tex_sz = int.from_bytes(e[4:8], "little")
        unk1 = int.from_bytes(e[8:12], "little")
        unk2 = int.from_bytes(e[12:16], "little")
        str_off = int.from_bytes(e[24:28], "little")

        curr = str_off
        while curr < len(tpf) - 1:
            if tpf[curr] == 0 and tpf[curr + 1] == 0:
                break
            curr += 2
        name = tpf[str_off:curr].decode("utf-16le", errors="ignore")
        width = unk2 & 0xFFFF
        height = (unk2 >> 16) & 0xFFFF
        fmt = unk1 & 0xFF
        bpb = 16 if fmt in (0x66, 0x6A, 0x6C, 0x6D) else 8

        base = name[:-2] if name.endswith("_l") else name
        low_base = base.lower()

        # 1. Normal Maps (_n): Flatten to neutral vector
        if low_base.endswith("_n"):
            if fmt == 0x6C:  # BC5
                tiles = (tex_sz + 15) // 16
                tpf[tex_off : tex_off + tex_sz] = (FLAT_NORMAL_BC5_UNORM * tiles)[:tex_sz]
            elif fmt == 0x00:  # BC1
                tiles = (tex_sz + 7) // 8
                tpf[tex_off : tex_off + tex_sz] = (FLAT_NORMAL_BC1 * tiles)[:tex_sz]
            # Other formats: leave untouched to avoid corruption

        # 2. Specular reflectance & gloss (_r, _s): Zero out to eliminate PBR shine
        elif low_base.endswith("_r") or low_base.endswith("_s"):
            if fmt in (0x00, 0x67):  # BC1, BC4
                tpf[tex_off : tex_off + tex_sz] = b"\x00" * tex_sz

        # 3. Albedo (_a or default): Downsample & quantize to 15-bit RGB555
        elif low_base.endswith("_a") or not any(low_base.endswith(x) for x in ["_n", "_r", "_s", "_m"]):
            if fmt == 0x00:  # BC1
                orig = bytes(tpf[tex_off : tex_off + tex_sz])
                demade_bytes = demake_texture_pixel_space(
                    orig, width, height, bpb=bpb, target_dim=target_dim, tex_name=name
                )
                if len(demade_bytes) == tex_sz:
                    tpf[tex_off : tex_off + tex_sz] = demade_bytes

    return tpf


def process_parts_container(filename: str, target_dim: int, deploy: bool) -> tuple[str, bool, str]:
    """Processes a single .partsbnd.dcx container."""
    vanilla_path = VANILLA_PARTS_DIR / filename
    sandbox_path = SANDBOX_PARTS_DIR / filename

    if not vanilla_path.exists():
        return filename, False, "Vanilla file missing"

    source_path = sandbox_path if sandbox_path.exists() else vanilla_path
    try:
        binder = Binder.from_path(str(source_path))
        modified_count = 0
        for entry in binder.entries:
            if entry.name.lower().endswith(".tpf"):
                orig_data = entry.get_uncompressed_data()
                new_data = process_single_tpf_bytes(orig_data, target_dim=target_dim)
                entry.set_uncompressed_data(bytes(new_data))
                modified_count += 1

        if modified_count == 0:
            return filename, True, "No TPF found"

        if deploy:
            sandbox_path.parent.mkdir(parents=True, exist_ok=True)
            binder.write(str(sandbox_path))
            return filename, True, f"Deployed {modified_count} retro TPF(s)"
        else:
            return filename, True, f"Dry-run {modified_count} retro TPF(s)"

    except Exception as e:
        return filename, False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Retro Demake & PBR Stripper for Player Equipment Textures")
    parser.add_argument("--all", action="store_true", help="Process all player equipment files")
    parser.add_argument("--only", type=str, default="", help="Glob filter (e.g. '*9000*', 'wp_a_1001*')")
    parser.add_argument("--dim", type=int, default=128, help="Target texture dimension (default: 128)")
    parser.add_argument("--deploy", action="store_true", help="Deploy directly to CUSA03173-PSX")
    args = parser.parse_args()

    files = sorted([f.name for f in VANILLA_PARTS_DIR.glob("*.partsbnd.dcx")])
    if args.only:
        files = [f for f in files if fnmatch.fnmatch(f, args.only)]
    elif not args.all:
        print("Specify --all or --only '<pattern>'")
        sys.exit(1)

    print(f"Demaking textures for {len(files)} player equipment archives (target_dim={args.dim}px, deploy={args.deploy})...")
    start_t = time.time()
    successes = 0

    for f in files:
        fname, ok, msg = process_parts_container(f, target_dim=args.dim, deploy=args.deploy)
        if ok:
            successes += 1
            print(f"  [OK] {fname}: {msg}")
        else:
            print(f"  [ERROR] {fname}: {msg}")

    dt = time.time() - start_t
    print(f"Finished {successes}/{len(files)} archives in {dt:.1f}s.")


if __name__ == "__main__":
    main()
