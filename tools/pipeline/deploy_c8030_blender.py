#!/usr/bin/env python3
"""
Bloodborne PSX Demake: End-to-End Blender Low-Poly Pipeline for Plain Doll (c8030).
Extracts pristine FLVER, runs headless Blender retro decimation & cloth decoupling,
compiles dual-buffer FLVER, strips Havok cloth files (_c.hkx), and deploys to CUSA03173-PSX.
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PIPELINE_DIR))

import soulstruct_patch
from soulstruct.containers import Binder
from soulstruct.flver.core import FLVER
from rigged_gltf_to_flver import compile_glb_to_flver


def deploy_c8030(preset: str = "authentic", dry_run: bool = False):
    vanilla_chr = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"
    psx_chr_dir = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr"
    psx_chr = psx_chr_dir / "c8030.chrbnd.dcx"

    if not vanilla_chr.exists():
        print(f"Error: Pristine vanilla archive not found at {vanilla_chr}")
        sys.exit(1)

    psx_chr_dir.mkdir(parents=True, exist_ok=True)

    tmp_rigged_glb = Path("/tmp/c8030_rigged.glb")
    tmp_demade_glb = Path("/tmp/c8030_demade.glb")

    print(f"=== STEP 1: Exporting Rigged glTF from Vanilla c8030 ===")
    cmd_export = [
        "uv",
        "run",
        "python",
        str(PIPELINE_DIR / "flver_to_rigged_gltf.py"),
        str(vanilla_chr),
        str(tmp_rigged_glb),
    ]
    subprocess.run(cmd_export, check=True)
    print(f"Rigged glTF exported to {tmp_rigged_glb} ({tmp_rigged_glb.stat().st_size} bytes)")

    print(f"=== STEP 2: Headless Blender Retro Processing ({preset} preset) ===")
    cmd_blender = [
        "/usr/bin/blender",
        "-b",
        "-P",
        str(PIPELINE_DIR / "blender_process_c8030.py"),
        "--",
        str(tmp_rigged_glb),
        str(tmp_demade_glb),
        preset,
    ]
    subprocess.run(cmd_blender, check=True)
    print(f"Blender processing completed -> {tmp_demade_glb} ({tmp_demade_glb.stat().st_size} bytes)")

    print(f"=== STEP 3: Compiling glTF to Bloodborne FLVER2 ===")
    b_vanilla = Binder.from_path(vanilla_chr)
    flv_entry = next(e for e in b_vanilla.entries if e.name.endswith(".flver"))
    base_flver = FLVER.from_bytes(flv_entry.data)

    compiled_flv = compile_glb_to_flver(tmp_demade_glb, base_flver, decouple_cloth=True)
    new_flv_bytes = compiled_flv.to_bytes()
    print(f"Compiled FLVER: {len(new_flv_bytes)} bytes (was {len(flv_entry.data)} bytes)")

    print(f"=== STEP 4: Assembling Clean PSX Binder (Decoupling Havok Cloth) ===")
    # Create new Binder entries
    # Keep TPF (100) and ragdoll HKX (300).
    # Replace FLVER (200).
    # EXCLUDE Havok cloth simulation: 700 (c8030_c.hkx) and 1200 (c8030_c.clm2).
    new_binder = Binder()
    new_binder.v4_info = b_vanilla.v4_info
    new_binder.flags = b_vanilla.flags
    new_binder.big_endian = b_vanilla.big_endian
    new_binder.bit_big_endian = b_vanilla.bit_big_endian
    new_binder.dcx_type = b_vanilla.dcx_type

    for e in b_vanilla.entries:
        if e.name.endswith(".flver"):
            e.data = new_flv_bytes
            new_binder.add_entry(e)
            print(f"  [INJECT] {e.entry_id}: {e.name} ({len(e.data)} bytes)")
        elif "_c.hkx" in e.name.lower() or "_c.clm2" in e.name.lower():
            print(f"  [STRIP]  {e.entry_id}: {e.name} (Havok Cloth Solver Decoupled)")
        else:
            new_binder.add_entry(e)
            print(f"  [KEEP]   {e.entry_id}: {e.name} ({len(e.data)} bytes)")

    if dry_run:
        print("Dry run requested. Not deploying to sandbox.")
        return

    print(f"=== STEP 5: Deploying to Sandbox: {psx_chr} ===")
    # Snapshot existing sandbox archive if present
    if psx_chr.exists():
        snap_path = psx_chr.with_suffix(".chrbnd.dcx.snap_pre_blender")
        if not snap_path.exists():
            shutil.copy2(psx_chr, snap_path)
            print(f"Created fallback snapshot: {snap_path}")

    new_bnd_bytes = new_binder.to_bytes()
    psx_chr.write_bytes(new_bnd_bytes)
    print(f"Successfully deployed {len(new_bnd_bytes)} bytes to {psx_chr}!")

    # Flush Vulkan pipeline cache
    cache_pattern = Path(os.path.expanduser("~/.local/share/bbhost/data/bbhost"))
    if cache_pattern.exists():
        for bin_file in cache_pattern.glob("*.bin"):
            try:
                bin_file.unlink()
                print(f"Cleared Vulkan cache: {bin_file.name}")
            except OSError:
                pass

    print("=== PLAIN DOLL BLENDER DEMAKE COMPLETE ===")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deploy Blender Demake for Plain Doll (c8030)")
    parser.add_argument("--preset", choices=["authentic", "aggressive"], default="authentic",
                        help="Decimation preset: authentic (~10K tris) or aggressive (~3.5K tris)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing to sandbox")
    args = parser.parse_args()

    deploy_c8030(preset=args.preset, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
