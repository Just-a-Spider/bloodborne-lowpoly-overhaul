#!/usr/bin/env python3
"""
Bloodborne PSX Demake: High-Fidelity World Maps Demake Engine (map/).

Implements the user-approved "Keep Rendered, Reduce Detail" fidelity architecture:
  1. Foreground & Walkable Architecture (chunk ID < 8000):
     - 100% Pristine FromSoftware LOD0 Geometry directly from CUSA03173.
     - Preserves all Gothic arches, railings, stone cornices, banisters, and stairs.
     - Zero normal distortion, zero flat box collapse, zero plastic specular sheen.
  2. Distant Vista & Background Chunks (chunk ID >= 8000):
     - Gentle native LOD1 promotion with a strict 50% triangle floor.
     - If LOD1 is unavailable or collapses below 50%, keeps pristine LOD0.
     - DOL lightmaps and secondary face sets strictly preserved.
  3. Sliced Retro Textures (Already Sliced -85% to -98%):
     - Keeps all 256px/128px BXF archives in dvdroot_ps4/map/mXX/, preserving low VRAM and fillrate.

Usage:
    uv run python tools/pipeline/batch_demake_maps_fidelity.py --map m22           # dry run Central Yharnam
    uv run python tools/pipeline/batch_demake_maps_fidelity.py --map m22 --deploy  # deploy Central Yharnam
    uv run python tools/pipeline/batch_demake_maps_fidelity.py --all --deploy      # deploy all world maps
"""

import argparse
import fnmatch
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
PIPELINE_DIR = TOOLS_DIR / "pipeline"

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PIPELINE_DIR))
os.environ["HOME"] = "/tmp"

import numpy as np  # noqa: E402
import soulstruct_patch  # noqa: E402
from soulstruct.flver.core import FLVER  # noqa: E402

VANILLA_MAP_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "map"
SANDBOX_MAP_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "map"
STAGE_DIR = REPO_ROOT / "build" / "stage_map"


def process_single_map_flver(
    rel_path: str,
    deploy: bool,
) -> Tuple[str, bool, str, int, int]:
    """
    Processes a single map FLVER file.
    Returns: (rel_path, success, mode, orig_tris, final_tris)
    """
    vanilla_file = VANILLA_MAP_DIR / rel_path
    sandbox_file = SANDBOX_MAP_DIR / rel_path
    stage_file = STAGE_DIR / rel_path
    dest_file = sandbox_file if deploy else stage_file

    if not vanilla_file.exists():
        return rel_path, False, "vanilla missing", 0, 0

    stem = vanilla_file.stem.replace(".flver", "")
    suffix = stem.split("_")[-1]
    is_numeric = suffix.isdigit()
    chunk_num = int(suffix) if is_numeric else 0

    # 1. Foreground Architecture & Walkable Geometry (< 8000):
    # Strictly preserve 100% pristine vanilla LOD0 geometry to eliminate plastic boxes
    # and prevent stairs/railings mesh collapse (chunks 000000..007999 are playable city/level)
    if chunk_num < 8000:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vanilla_file, dest_file)
        return rel_path, True, "foreground-pristine", 0, 0

    # 2. Distant Background & Vista Chunks (>= 8000):
    # Gentle native LOD1 promotion with 50% floor exclusively on distant horizon/cliffs
    try:
        flv = FLVER.from_path(vanilla_file)
        orig_tris = 0
        final_tris = 0
        modified = False

        for m in flv.meshes:
            if not m.face_sets or len(m.vertex_arrays) == 0:
                continue

            fs0 = m.face_sets[0]
            m_orig = len(fs0.vertex_indices) // 3
            orig_tris += m_orig

            # Find native LOD1 face set (flags == 1)
            lod1_fs = None
            for fs in m.face_sets[1:]:
                # Check for LOD1 (flags 1)
                flags = int(getattr(fs, "flags", 0))
                if flags == 1 and len(fs.vertex_indices) > 0:
                    lod1_fs = fs
                    break

            if lod1_fs is not None:
                lod1_tris = len(lod1_fs.vertex_indices) // 3
                # Strict 50% floor to prevent collapsing architectural silhouettes
                if lod1_tris >= max(24, int(m_orig * 0.50)):
                    fs0.vertex_indices = np.array(lod1_fs.vertex_indices, copy=True)
                    final_tris += lod1_tris
                    modified = True
                    continue

            final_tris += m_orig

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        if modified:
            dest_file.write_bytes(flv.to_bytes())
            return rel_path, True, "vista-lod1", orig_tris, final_tris
        else:
            shutil.copy2(vanilla_file, dest_file)
            return rel_path, True, "vista-pristine", orig_tris, orig_tris

    except Exception as e:
        # Fallback to pristine copy if parsing fails
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vanilla_file, dest_file)
        return rel_path, True, f"fallback-pristine ({e})", 0, 0


def get_map_directories(map_args: List[str]) -> List[Path]:
    all_map_dirs = sorted([d for d in VANILLA_MAP_DIR.iterdir() if d.is_dir() and d.name.startswith("m") and "_" in d.name])
    if "all" in map_args:
        return all_map_dirs

    selected = []
    for arg in map_args:
        prefix = arg.strip()
        matched = [d for d in all_map_dirs if d.name.startswith(prefix)]
        selected.extend(matched)
    return sorted(list(set(selected)))


def main():
    parser = argparse.ArgumentParser(description="High-Fidelity World Maps Demake Engine (map/)")
    parser.add_argument("--map", nargs="+", default=["all"], help="Map ID(s) to process, e.g. 'm22', 'm21 m22', or 'all'")
    parser.add_argument("--all", action="store_true", help="Process all world maps")
    parser.add_argument("--deploy", action="store_true", help="Deploy directly to CUSA03173-PSX")
    parser.add_argument("--workers", type=int, default=12, help="Parallel worker threads (default: 12)")
    args = parser.parse_args()

    map_args = ["all"] if args.all else args.map
    map_dirs = get_map_directories(map_args)
    if not map_dirs:
        print(f"No matching map directories found for: {args.map}")
        sys.exit(1)

    all_flver_relpaths = []
    for md in map_dirs:
        flvers = sorted(md.glob("*.flver.dcx"))
        for f in flvers:
            all_flver_relpaths.append(f"{md.name}/{f.name}")

    mode_str = "DEPLOY -> CUSA03173-PSX" if args.deploy else f"DRY RUN -> {STAGE_DIR}"
    print(f"=== High-Fidelity World Maps Demake ({len(map_dirs)} maps, {len(all_flver_relpaths)} FLVERs) [{mode_str}] ===")
    print(f"  Workers: {args.workers}")

    t0 = time.time()
    fg_count = 0
    bg_lod1_count = 0
    bg_pristine_count = 0
    fail_count = 0
    total_orig_bg_tris = 0
    total_final_bg_tris = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_single_map_flver, rp, args.deploy): rp
            for rp in all_flver_relpaths
        }

        for future in as_completed(futures):
            rp = futures[future]
            try:
                rel_path, ok, mode, o_tris, f_tris = future.result()
                if ok:
                    if mode == "foreground-pristine":
                        fg_count += 1
                    elif mode == "vista-lod1":
                        bg_lod1_count += 1
                        total_orig_bg_tris += o_tris
                        total_final_bg_tris += f_tris
                    else:
                        bg_pristine_count += 1
                        total_orig_bg_tris += o_tris
                        total_final_bg_tris += f_tris
                else:
                    fail_count += 1
                    print(f"  [FAIL] {rp}: {mode}")
            except Exception as e:
                fail_count += 1
                print(f"  [EXC] {rp}: {e}")

    dt = time.time() - t0
    total_processed = fg_count + bg_lod1_count + bg_pristine_count

    print(f"\n=== High-Fidelity World Maps Demake Completed in {dt:.1f}s ===")
    print(f"  Total Processed        : {total_processed} / {len(all_flver_relpaths)} (Failed: {fail_count})")
    print(f"  Foreground Pristine    : {fg_count} FLVERs (100% LOD0, 0 plastic collapse)")
    print(f"  Vista Gentle LOD1      : {bg_lod1_count} FLVERs (>= 50% floor)")
    print(f"  Vista Pristine LOD0    : {bg_pristine_count} FLVERs")
    if total_orig_bg_tris > 0:
        saved_tris = total_orig_bg_tris - total_final_bg_tris
        pct = (total_final_bg_tris / total_orig_bg_tris) * 100
        print(f"  Vista Triangles        : {total_orig_bg_tris:,} -> {total_final_bg_tris:,} ({pct:.1f}%, saved {saved_tris:,} tris)")

    if not args.deploy:
        print(f"\nDry run complete. Use --deploy to write directly to CUSA03173-PSX.")


if __name__ == "__main__":
    main()
