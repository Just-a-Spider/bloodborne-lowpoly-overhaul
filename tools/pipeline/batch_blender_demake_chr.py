#!/usr/bin/env python3
"""
Bloodborne PSX Demake: Multi-Threaded Blender Demake Engine for Enemies & Bosses (chr/).

Processes all 244 enemy and boss character archives through headless Blender 5.2.3:
  1. Exports each FLVER in chrbnd to rigged Binary glTF 2.0 (.glb)
  2. Runs headless Blender 5.2.3 retro decimation (COLLAPSE modifier + shade_smooth + influence prune <= 4)
  3. Recompiles FLVER2 with FromSoftware-aligned tangent frames (tdir + det_UV handedness)
  4. Decouples Havok cloth: swaps *_Cloth.mtd to *_e.mtd and strips _c.hkx / _c.clm2
  5. Optimizes fur shell overdraw on beasts while preserving silhouette contours
  6. Preserves low-res sandbox TPF textures if already present
  7. Plain Doll (c8030) is strictly protected and never touched

Usage:
    uv run python tools/pipeline/batch_blender_demake_chr.py --only 'c2020*'              # dry run Gascoigne
    uv run python tools/pipeline/batch_blender_demake_chr.py --only 'c2020*' --deploy   # deploy Gascoigne
    uv run python tools/pipeline/batch_blender_demake_chr.py --only 'c1000*' --deploy   # deploy Werewolf
    uv run python tools/pipeline/batch_blender_demake_chr.py --all --workers 12 --deploy  # full batch pass
    uv run python tools/pipeline/batch_blender_demake_chr.py --all --restore             # rollback to snapshots
"""

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
PIPELINE_DIR = TOOLS_DIR / "pipeline"

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PIPELINE_DIR))

import soulstruct_patch  # noqa: E402
from soulstruct.containers import Binder  # noqa: E402
from soulstruct.flver.core import FLVER  # noqa: E402

from flver_to_rigged_gltf import flver_to_rigged_glb  # noqa: E402
from rigged_gltf_to_flver import compile_glb_to_flver  # noqa: E402

VANILLA_CHR_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "chr"
SANDBOX_CHR_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr"
STAGE_DIR = Path("/tmp/chr_blender_stage")
SNAP_SUFFIX = ".snap_pre_blender_chr"

# Protected characters: never touch Plain Doll (c8030)
PROTECTED_STEMS = {"c8030"}


def process_single_chr_archive(
    filename: str,
    default_ratio: float,
    deploy: bool,
    snapshot: bool,
) -> Tuple[str, bool, int, int, str]:
    """Processes a single character archive through Blender, returning (filename, success, orig_tris, new_tris, msg)."""
    vanilla_path = VANILLA_CHR_DIR / filename
    sandbox_path = SANDBOX_CHR_DIR / filename
    stage_path = STAGE_DIR / filename

    if not vanilla_path.exists():
        return filename, False, 0, 0, f"Vanilla file {vanilla_path} does not exist"

    stem = filename.split(".")[0].lower()
    if stem in PROTECTED_STEMS:
        return filename, True, 0, 0, "PROTECTED (Plain Doll bypassed)"

    worker_temp = Path(tempfile.mkdtemp(prefix=f"bb_blender_chr_{stem}_"))

    try:
        b_vanilla = Binder.from_path(str(vanilla_path))

        # Preserve existing sliced TPF from sandbox if present
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
            except Exception:
                pass

        total_orig_tris = 0
        total_new_tris = 0
        flver_count = 0

        for entry in b_vanilla.entries:
            if not entry.name.lower().endswith(".flver"):
                continue
            if len(entry.get_uncompressed_data()) <= 0x100:
                continue

            raw_orig = entry.get_uncompressed_data()
            try:
                flv_orig = FLVER.from_bytes(raw_orig)
            except Exception:
                continue

            tris_orig = sum(len(m.face_sets[0].vertex_indices) for m in flv_orig.meshes if m.face_sets)
            total_orig_tris += tris_orig

            if tris_orig == 0:
                total_new_tris += 0
                continue

            flver_count += 1
            flv_stem = Path(entry.name).stem
            in_glb = worker_temp / f"{flv_stem}_in.glb"
            out_glb = worker_temp / f"{flv_stem}_out.glb"

            # 1. Export FLVER to rigged Binary glTF
            glb_data = flver_to_rigged_glb(flv_orig)
            in_glb.write_bytes(glb_data)

            # 2. Run Headless Blender 5.2.3 Decimation & Shading
            cmd_blender = [
                "/usr/bin/blender",
                "-b",
                "-P",
                str(PIPELINE_DIR / "blender_process_chr.py"),
                "--",
                str(in_glb),
                str(out_glb),
                str(default_ratio),
                stem,
            ]
            res = subprocess.run(cmd_blender, capture_output=True, text=True)
            if res.returncode != 0 or not out_glb.exists():
                return filename, False, total_orig_tris, total_new_tris, f"Blender failed on {flv_stem}: {res.stderr[-300:]}"

            # 3. Recompile demade glTF to native Bloodborne FLVER with Havok cloth decoupling
            c_flv = compile_glb_to_flver(out_glb, flv_orig, decouple_cloth=True)
            tris_new = sum(len(m.face_sets[0].vertex_indices) for m in c_flv.meshes if m.face_sets)
            total_new_tris += tris_new

            # Replace FLVER in binder
            entry.set_uncompressed_data(c_flv.to_bytes())

        # Strip Havok cloth solver files (_c.hkx and _c.clm2)
        b_vanilla.entries = [
            e for e in b_vanilla.entries
            if not (e.name.lower().endswith("_c.hkx") or e.name.lower().endswith("_c.clm2"))
        ]

        if flver_count == 0:
            return filename, True, total_orig_tris, total_new_tris, "No active FLVERs (empty binder)"

        # Write output (snapshotting first if deploying)
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

    finally:
        shutil.rmtree(worker_temp, ignore_errors=True)


def restore_snapshots(only_glob: str) -> None:
    """Restores files from snapshot files in sandbox."""
    count = 0
    pattern = f"*{SNAP_SUFFIX}" if not only_glob else f"{only_glob}*{SNAP_SUFFIX}"
    for snap in SANDBOX_CHR_DIR.glob(pattern):
        dest = snap.with_name(snap.name[: -len(SNAP_SUFFIX)])
        shutil.copy2(snap, dest)
        snap.unlink()
        count += 1
    print(f"[RESTORE] Restored {count} file(s) from {SNAP_SUFFIX} in {SANDBOX_CHR_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Threaded Blender Demake Engine for Bloodborne Enemies & Bosses")
    parser.add_argument("--all", action="store_true", help="Process all enemy and boss character files")
    parser.add_argument("--only", type=str, default="", help="Glob pattern filter (e.g. 'c2020*', 'c1000*')")
    parser.add_argument("--ratio", type=float, default=0.22, help="Default decimation ratio (default: 0.22)")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel worker processes (default: 8)")
    parser.add_argument("--deploy", action="store_true", help="Deploy directly to CUSA03173-PSX (default: dry run to /tmp)")
    parser.add_argument("--snapshot", action="store_true", default=True, help="Create snapshot before overwriting sandbox")
    parser.add_argument("--restore", action="store_true", help="Restore all snapshots from *.snap_pre_blender_chr")

    args = parser.parse_args()

    if args.restore:
        restore_snapshots(args.only)
        return

    if not args.all and not args.only:
        parser.error("Specify --all or --only (e.g. --only 'c2020*')")

    candidate_files = [p.name for p in VANILLA_CHR_DIR.glob("*.chrbnd.dcx")]

    if args.only:
        patterns = [p.strip() for p in args.only.split(",") if p.strip()]
        matched = []
        for f in candidate_files:
            if any(fnmatch.fnmatch(f, p) for p in patterns):
                matched.append(f)
        candidate_files = matched

    candidate_files.sort()

    if not candidate_files:
        print("No files matched filter. Exiting.")
        sys.exit(1)

    mode = "DEPLOY -> CUSA03173-PSX" if args.deploy else f"DRY RUN -> {STAGE_DIR}"
    print(f"=== Multi-Threaded Blender Enemies Demake ({len(candidate_files)} files) [{mode}] ===")
    print(f"  Default Ratio: {args.ratio}")
    print(f"  Workers      : {args.workers}")

    t0 = time.time()
    success_count = 0
    fail_count = 0
    total_orig = 0
    total_new = 0

    if not args.deploy:
        STAGE_DIR.mkdir(parents=True, exist_ok=True)

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_single_chr_archive,
                fname,
                args.ratio,
                args.deploy,
                args.snapshot,
            ): fname
            for fname in candidate_files
        }

        for future in as_completed(futures):
            fname = futures[future]
            try:
                filename, ok, o_tris, n_tris, msg = future.result()
                if ok:
                    success_count += 1
                    total_orig += o_tris
                    total_new += n_tris
                    pct = (n_tris / o_tris * 100) if o_tris > 0 else 0
                    print(f"  [OK] {filename:<32}: {o_tris:>6} -> {n_tris:>6} tris ({pct:>5.1f}%) [{msg}]")
                else:
                    fail_count += 1
                    print(f"  [FAIL] {filename:<30}: {msg}")
            except Exception as e:
                fail_count += 1
                print(f"  [EXC] {fname:<31}: {e}")

    dt = time.time() - t0
    saved = total_orig - total_new
    overall_pct = (total_new / total_orig * 100) if total_orig > 0 else 0

    print(f"\n=== Blender Enemies Demake Completed in {dt:.1f}s ===")
    print(f"  Processed : {success_count} / {len(candidate_files)} (Failed: {fail_count})")
    print(f"  Triangles : {total_orig:,} -> {total_new:,} ({overall_pct:.1f}%, saved {saved:,} tris)")

    if not args.deploy:
        print("\nDry run complete. Use --deploy to write directly to CUSA03173-PSX.")


if __name__ == "__main__":
    main()

