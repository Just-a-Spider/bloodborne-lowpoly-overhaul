#!/usr/bin/env python3
"""
batch_demake_parts_ultralow.py — Ultra-Low-Poly PSX Demake Engine for Hunter Equipment & Weapons.

Applies authentic retro polygon decimation across player armors (bd_, hd_, am_, lg_) and
trick weapons (wp_):
  - Rigid armor: 0.22 target ratio (cuts rigid body to ~2,000–2,500 tris, angular retro look)
  - Trick weapons: 0.30 target ratio with relaxed border decimation and bridge face preservation
  - Havok cloth physics (_Cloth.mtd / _cloth.mtd): 100% PRESERVED to prevent Havok crashes
  - Bone AABBs: strictly identical to vanilla baseline to prevent GPU occlusion culling drops
  - Bone weights: strictly normalized (float sum == 1.0, byte sum == 255)
  - Sliced textures: preserves already-sliced low-res TPFs from CUSA03173-PSX (zero VRAM re-inflation)
  - Facegen & hair (fc_, fg_, hr_): 100% bypassed to preserve facial morphs and alpha cards

Usage:
    uv run --no-project python tools/batch_demake_parts_ultralow.py --only '*9000*'              # dry-run Hunter set
    uv run --no-project python tools/batch_demake_parts_ultralow.py --only '*9000*' --deploy   # deploy Hunter set
    uv run --no-project python tools/batch_demake_parts_ultralow.py --all --deploy             # deploy all parts
    uv run --no-project python tools/batch_demake_parts_ultralow.py --all --restore            # restore from snapshots
"""

import argparse
import fnmatch
import glob
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import soulstruct_patch  # noqa: E402
from mesh_decimator import decimate_flver  # noqa: E402

from soulstruct.containers import Binder  # noqa: E402
from soulstruct.flver import FLVER  # noqa: E402

VANILLA_PARTS_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "parts"
SANDBOX_PARTS_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "parts"
STAGE_DIR = Path("/tmp/parts_ultralow_stage")
SNAP_SUFFIX = ".snap_pre_ultralow"

# Categories to process
ALLOWED_PREFIXES = ("bd_", "hd_", "am_", "lg_", "wp_")
EXCLUDED_PREFIXES = ("fc_", "fg_", "hr_")


def validate_flver_invariants(flv_orig: FLVER, flv_dec: FLVER, filename: str) -> Tuple[bool, str]:
    """Strictly validates Havok cloth, bone AABB, and bone weight invariants."""
    # 1. Bone AABB matching
    if len(flv_orig.bones) != len(flv_dec.bones):
        return False, "Bone count mismatch"
    for bi, (bo, bd) in enumerate(zip(flv_orig.bones, flv_dec.bones)):
        if bo.bounding_box.min != bd.bounding_box.min or bo.bounding_box.max != bd.bounding_box.max:
            return False, f"Bone {bi} AABB mismatch"

    # 2. Havok Cloth & Bone Weight Check
    if len(flv_orig.meshes) != len(flv_dec.meshes):
        return False, "Mesh count mismatch"

    for mi, (mo, md) in enumerate(zip(flv_orig.meshes, flv_dec.meshes)):
        mat_name = md.material.name.lower() if md.material else ""
        mtd_name = md.material.mat_def_name.lower() if md.material else ""
        is_cloth = "cloth" in mat_name or "_cloth" in mtd_name

        to = len(mo.face_sets[0].vertex_indices) if mo.face_sets else 0
        td = len(md.face_sets[0].vertex_indices) if md.face_sets else 0
        vo = len(mo.vertex_arrays[0].array) if mo.vertex_arrays else 0
        vd = len(md.vertex_arrays[0].array) if md.vertex_arrays else 0

        if is_cloth:
            if to != td or vo != vd:
                return False, f"Mesh {mi} ({mat_name}) is CLOTH but geometry changed: {to}->{td} tris, {vo}->{vd} verts"

        if md.vertex_arrays:
            arr = md.vertex_arrays[0].array
            if "bone_weights" in arr.dtype.names:
                bw = arr["bone_weights"]
                if len(bw) > 0:
                    bsums = np.sum(np.round(bw * 255.0).astype(int), axis=1)
                    if not np.all(bsums == 255):
                        # If vanilla itself had non-255 sums (e.g. special shaders with zero weights), allow matching vanilla
                        arr_o = mo.vertex_arrays[0].array if mo.vertex_arrays else None
                        if arr_o is not None and "bone_weights" in arr_o.dtype.names:
                            bw_o = arr_o["bone_weights"]
                            bsums_o = np.sum(np.round(bw_o * 255.0).astype(int), axis=1)
                            if np.sum(bsums_o != 255) == len(bw_o):
                                pass
                            else:
                                bad_cnt = int(np.sum(bsums != 255))
                                return False, f"Mesh {mi} has {bad_cnt} vertices with invalid bone weight sums != 255"
                        else:
                            bad_cnt = int(np.sum(bsums != 255))
                            return False, f"Mesh {mi} has {bad_cnt} vertices with invalid bone weight sums != 255"

            # Check index bounds
            for fs in md.face_sets:
                if len(fs.vertex_indices) > 0:
                    if fs.vertex_indices.max() >= vd:
                        return False, f"Mesh {mi} FaceSet index {fs.vertex_indices.max()} >= num_verts {vd}"

    return True, "OK"


def process_single_file(
    filename: str,
    ratio_armor: float,
    ratio_weapon: float,
    deploy: bool,
    snapshot: bool,
) -> Tuple[str, bool, int, int, str]:
    """Processes a single partsbinder file, returning (filename, success, orig_tris, new_tris, msg)."""
    vanilla_path = VANILLA_PARTS_DIR / filename
    sandbox_path = SANDBOX_PARTS_DIR / filename
    stage_path = STAGE_DIR / filename

    if not vanilla_path.exists():
        return filename, False, 0, 0, f"Vanilla file {vanilla_path} does not exist"

    try:
        # Step A: Load pristine vanilla binder
        b_vanilla = Binder.from_path(str(vanilla_path))

        # Step B: Preserve existing demade / sliced TPFs from sandbox if present
        if sandbox_path.exists():
            try:
                b_sandbox = Binder.from_path(str(sandbox_path))
                psx_tpfs = {
                    e.name: e.get_uncompressed_data()
                    for e in b_sandbox.entries
                    if e.name.endswith(".tpf")
                }
                for entry in b_vanilla.entries:
                    if entry.name in psx_tpfs:
                        entry.set_uncompressed_data(psx_tpfs[entry.name])
            except Exception as e:
                # If sandbox file corrupted, continue with vanilla TPF
                pass

        fn_lower = filename.lower()
        is_weapon = fn_lower.startswith("wp_")
        target_ratio = ratio_weapon if is_weapon else ratio_armor

        total_orig_tris = 0
        total_new_tris = 0

        # Step C: Decimate all FLVER entries in binder
        for entry in b_vanilla.entries:
            if entry.name.endswith(".flver") and len(entry.get_uncompressed_data()) > 0x100:
                raw_orig = entry.get_uncompressed_data()
                flv_orig = FLVER.from_bytes(raw_orig)
                flv_dec = FLVER.from_bytes(raw_orig)

                for m in flv_orig.meshes:
                    if m.face_sets:
                        total_orig_tris += len(m.face_sets[0].vertex_indices)

                decimate_flver(
                    flv_dec,
                    target_ratio=target_ratio,
                    flat_normals=False,
                    disable_cloth=False,
                    preserve_border=False,
                    filename=filename,
                )

                for m in flv_dec.meshes:
                    if m.face_sets:
                        total_new_tris += len(m.face_sets[0].vertex_indices)

                # Step D: Strict Invariant Audit
                valid, msg = validate_flver_invariants(flv_orig, flv_dec, filename)
                if not valid:
                    return filename, False, total_orig_tris, total_new_tris, msg

                entry.set_uncompressed_data(flv_dec.to_bytes())

        # Step E: Write output (snapshotting first if deploying)
        target_write_path = sandbox_path if deploy else stage_path
        target_write_path.parent.mkdir(parents=True, exist_ok=True)

        if deploy and snapshot and sandbox_path.exists():
            snap_path = sandbox_path.with_name(sandbox_path.name + SNAP_SUFFIX)
            if not snap_path.exists():
                shutil.copy2(sandbox_path, snap_path)

        b_vanilla.write(str(target_write_path))
        return filename, True, total_orig_tris, total_new_tris, "OK"

    except Exception as ex:
        return filename, False, 0, 0, str(ex)


def restore_snapshots(only_glob: str) -> None:
    """Restores files from snapshot files in sandbox."""
    count = 0
    pattern = f"*{SNAP_SUFFIX}" if not only_glob else f"{only_glob}*{SNAP_SUFFIX}"
    for snap in SANDBOX_PARTS_DIR.glob(pattern):
        dest = snap.with_name(snap.name[: -len(SNAP_SUFFIX)])
        shutil.copy2(snap, dest)
        snap.unlink()
        count += 1
    print(f"[RESTORE] Restored {count} file(s) from {SNAP_SUFFIX} in {SANDBOX_PARTS_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Ultra-Low-Poly PSX Demake Engine for Hunter Equipment & Weapons")
    parser.add_argument("--all", action="store_true", help="Process all player equipment and weapon files")
    parser.add_argument("--only", type=str, default="", help="Glob pattern filter (e.g. '*9000*', 'wp_a_1001*')")
    parser.add_argument("--ratio-armor", type=float, default=0.22, help="Decimation ratio for rigid armor (default: 0.22)")
    parser.add_argument("--ratio-weapon", type=float, default=0.30, help="Decimation ratio for weapons (default: 0.30)")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel worker processes (default: 8)")
    parser.add_argument("--deploy", action="store_true", help="Deploy directly to CUSA03173-PSX (default: dry run to /tmp)")
    parser.add_argument("--snapshot", action="store_true", default=True, help="Create snapshot before overwriting sandbox")
    parser.add_argument("--restore", action="store_true", help="Restore all snapshots from *.snap_pre_ultralow")

    args = parser.parse_args()

    if args.restore:
        restore_snapshots(args.only)
        return

    if not args.all and not args.only:
        parser.error("Specify --all or --only (e.g. --only '*9000*')")

    # Discover candidate files in vanilla parts directory
    candidate_files = []
    for prefix in ALLOWED_PREFIXES:
        for p in VANILLA_PARTS_DIR.glob(f"{prefix}*.partsbnd.dcx"):
            candidate_files.append(p.name)

    # Filter out excluded prefixes
    candidate_files = [
        f for f in sorted(set(candidate_files))
        if not any(f.lower().startswith(ex) for ex in EXCLUDED_PREFIXES)
    ]

    # Apply user glob filter
    if args.only:
        candidate_files = [f for f in candidate_files if fnmatch.fnmatch(f, args.only)]

    if not candidate_files:
        print(f"No files matched filter. Exiting.")
        sys.exit(1)

    mode_str = "DEPLOY -> CUSA03173-PSX" if args.deploy else f"DRY RUN -> {STAGE_DIR}"
    print(f"=== Ultra-Low-Poly Parts Demake ({len(candidate_files)} files) [{mode_str}] ===")
    print(f"  Armor Ratio  : {args.ratio_armor:.2f}")
    print(f"  Weapon Ratio : {args.ratio_weapon:.2f}")
    print(f"  Workers      : {args.workers}")

    if not args.deploy:
        STAGE_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    total_processed = 0
    total_failed = 0
    sum_orig_tris = 0
    sum_new_tris = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_single_file,
                fname,
                args.ratio_armor,
                args.ratio_weapon,
                args.deploy,
                args.snapshot,
            ): fname
            for fname in candidate_files
        }

        for future in as_completed(futures):
            fname, success, orig_t, new_t, msg = future.result()
            if success:
                total_processed += 1
                sum_orig_tris += orig_t
                sum_new_tris += new_t
                pct = (new_t / max(1, orig_t)) * 100
                print(f"  [OK] {fname:32s} : {orig_t:6d} -> {new_t:6d} tris ({pct:5.1f}%)")
            else:
                total_failed += 1
                print(f"  [FAIL] {fname:30s} : {msg}")

    elapsed = time.time() - t0
    print(f"\n=== Parts Demake Completed in {elapsed:.1f}s ===")
    print(f"  Processed : {total_processed} / {len(candidate_files)}")
    print(f"  Failed    : {total_failed}")
    if sum_orig_tris > 0:
        pct_overall = (sum_new_tris / sum_orig_tris) * 100
        saved_tris = sum_orig_tris - sum_new_tris
        print(f"  Triangles : {sum_orig_tris:,} -> {sum_new_tris:,} ({pct_overall:.1f}%, saved {saved_tris:,} tris)")

    if not args.deploy:
        print(f"\nDry run complete. Use --deploy to write directly to CUSA03173-PSX.")
    else:
        print(f"\nDeployed to CUSA03173-PSX. Clear bbhost pipeline cache:")
        print(f"  rm -f ~/.local/share/bbhost/data/bbhost/*.bin")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
