#!/usr/bin/env python3
"""
Bloodborne PSX Demake: Multi-Threaded Batch Blender Demake Engine for Player Equipment & Weapons (parts/).

Processes all eligible player armor (bd_, hd_, am_, lg_) and weapons (wp_) through headless Blender 5.2.3:
  1. Exports each FLVER in partsbinder to rigged Binary glTF 2.0 (.glb)
  2. Runs headless Blender 5.2.3 retro decimation (COLLAPSE modifier + shade_smooth + influence prune <= 4)
  3. Recompiles FLVER2 with FromSoftware-aligned tangent frames (tdir + det_UV handedness)
  4. Decouples Havok cloth on armor: swaps *_Cloth.mtd to *_e.mtd and strips _c.hkx / _c.clm2
  5. Preserves 100% of weapon Dummy attach points and multi-FLVER transformation states
  6. Preserves low-res sandbox TPF textures if already present

Usage:
    uv run python tools/pipeline/batch_blender_demake_parts.py --only '*9000*'              # dry run Hunter set
    uv run python tools/pipeline/batch_blender_demake_parts.py --only '*9000*' --deploy   # deploy Hunter set
    uv run python tools/pipeline/batch_blender_demake_parts.py --only 'wp_a_1001*' --deploy # deploy Saw Cleaver
    uv run python tools/pipeline/batch_blender_demake_parts.py --all --workers 12 --deploy  # full batch pass
    uv run python tools/pipeline/batch_blender_demake_parts.py --all --restore             # rollback to snapshots
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
from demake_parts_textures import process_single_tpf_bytes  # noqa: E402

VANILLA_PARTS_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "parts"
SANDBOX_PARTS_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "parts"
STAGE_DIR = Path(tempfile.gettempdir()) / "parts_blender_stage"
SNAP_SUFFIX = ".snap_pre_blender"

ALLOWED_PREFIXES = ("bd_", "hd_", "am_", "lg_", "wp_")
EXCLUDED_PREFIXES = ("fc_", "fg_", "hr_")


def process_single_parts_archive(
    filename: str,
    ratio_armor: float,
    ratio_weapon: float,
    deploy: bool,
    snapshot: bool,
    keep_cloth: bool = False,
    out_dir: Optional[str] = None,
    demake_textures: bool = True,
) -> Tuple[str, bool, int, int, str]:
    """Processes a single partsbinder file through Blender, returning (filename, success, orig_tris, new_tris, msg)."""
    vanilla_path = VANILLA_PARTS_DIR / filename
    sandbox_path = SANDBOX_PARTS_DIR / filename
    stage_path = STAGE_DIR / filename

    if not vanilla_path.exists():
        return filename, False, 0, 0, f"Vanilla file {vanilla_path} does not exist"

    fn_lower = filename.lower()
    is_weapon = fn_lower.startswith("wp_")
    category = "weapon" if is_weapon else "armor"
    target_ratio = ratio_weapon if is_weapon else ratio_armor

    # Create worker-isolated temp directory
    worker_temp = Path(tempfile.mkdtemp(prefix=f"bb_blender_{fn_lower[:8]}_"))

    try:
        b_vanilla = Binder.from_path(str(vanilla_path))

        # Preserve existing sliced TPF from sandbox if present and not re-demaking textures
        if not demake_textures and sandbox_path.exists():
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

        for entry_idx, entry in enumerate(b_vanilla.entries):
            if not entry.name.lower().endswith(".flver"):
                continue
            if len(entry.get_uncompressed_data()) <= 0x100:
                continue

            raw_orig = entry.get_uncompressed_data()
            try:
                flv_orig = FLVER.from_bytes(raw_orig)
            except Exception as e:
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
            keep_cloth_flag = "true" if (keep_cloth and not is_weapon) else "false"
            cmd_blender = [
                "/usr/bin/blender",
                "-b",
                "-P",
                str(PIPELINE_DIR / "blender_process_parts.py"),
                "--",
                str(in_glb),
                str(out_glb),
                str(target_ratio),
                category,
                keep_cloth_flag,
            ]
            res = subprocess.run(cmd_blender, capture_output=True, text=True)
            if res.returncode != 0 or not out_glb.exists():
                return filename, False, total_orig_tris, total_new_tris, f"Blender failed on {flv_stem}: {res.stderr[-300:]}"

            # 3. Recompile demade glTF to native Bloodborne FLVER (preserving Blender flat split normals)
            decouple = not is_weapon and not keep_cloth
            c_flv = compile_glb_to_flver(
                out_glb,
                flv_orig,
                decouple_cloth=decouple,
                use_gltf_normals=True,
                keep_cloth=keep_cloth and not is_weapon,
            )
            tris_new = sum(len(m.face_sets[0].vertex_indices) for m in c_flv.meshes if m.face_sets)
            total_new_tris += tris_new

            # Replace FLVER in binder
            entry.set_uncompressed_data(c_flv.to_bytes())

        # If armor and decoupling cloth, strip Havok cloth physics files (_c.hkx and _c.clm2)
        if not is_weapon and not keep_cloth:
            b_vanilla.entries = [
                e for e in b_vanilla.entries
                if not (e.name.lower().endswith("_c.hkx") or e.name.lower().endswith("_c.clm2"))
            ]

        # In-place texture demaking (albedo quantization, normal map neutralizing, specular killing)
        if demake_textures:
            for entry in b_vanilla.entries:
                if entry.name.lower().endswith(".tpf"):
                    try:
                        raw_tpf = entry.get_uncompressed_data()
                        tpf_demade = process_single_tpf_bytes(raw_tpf, target_dim=128)
                        entry.set_uncompressed_data(bytes(tpf_demade))
                    except Exception as e:
                        print(f"Warning: TPF processing failed for {entry.name} in {filename}: {e}")

        # Write output (snapshotting first if deploying to sandbox)
        if out_dir:
            target_write_path = Path(out_dir) / filename
        elif deploy:
            target_write_path = sandbox_path
        else:
            target_write_path = stage_path

        target_write_path.parent.mkdir(parents=True, exist_ok=True)

        if not out_dir and deploy and snapshot and sandbox_path.exists():
            snap_path = sandbox_path.with_name(sandbox_path.name + SNAP_SUFFIX)
            if not snap_path.exists():
                shutil.copy2(sandbox_path, snap_path)

        b_vanilla.write(str(target_write_path))
        msg = "OK (empty/dummy binder)" if flver_count == 0 else "OK"
        return filename, True, total_orig_tris, total_new_tris, msg

    except Exception as ex:
        return filename, False, 0, 0, str(ex)

    finally:
        shutil.rmtree(worker_temp, ignore_errors=True)


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
    parser = argparse.ArgumentParser(description="Multi-Threaded Blender Demake Engine for Player Equipment & Weapons")
    parser.add_argument("--all", action="store_true", help="Process all player equipment and weapon files")
    parser.add_argument("--armors-only", action="store_true", help="Process only armor archives (bd_, hd_, am_, lg_)")
    parser.add_argument("--cloth-only", action="store_true", help="Process only armor archives containing Havok cloth (_c.hkx)")
    parser.add_argument("--only", type=str, default="", help="Glob pattern filter (e.g. '*9000*', 'wp_a_1001*')")
    parser.add_argument("--ratio-armor", type=float, default=0.08, help="Decimation ratio for armor (default: 0.08)")
    parser.add_argument("--ratio-weapon", type=float, default=0.20, help="Decimation ratio for weapons (default: 0.20)")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel worker processes (default: 8)")
    parser.add_argument("--deploy", action="store_true", help="Deploy directly to CUSA03173-PSX (default: dry run to /tmp)")
    parser.add_argument("--snapshot", action="store_true", default=True, help="Create snapshot before overwriting sandbox")
    parser.add_argument("--restore", action="store_true", help="Restore all snapshots from *.snap_pre_blender")
    parser.add_argument("--keep-cloth", action="store_true", help="Preserve Havok cloth physics (do not decouple cloth or strip .hkx)")
    parser.add_argument("--out-dir", type=str, default="", help="Custom output directory for processed files")
    parser.add_argument("--no-demake-textures", action="store_true", help="Skip in-place texture demaking")

    args = parser.parse_args()

    if args.restore:
        restore_snapshots(args.only)
        return

    if not args.all and not args.only and not args.armors_only and not args.cloth_only:
        parser.error("Specify --all, --armors-only, --cloth-only, or --only (e.g. --only '*9000*')")

    prefixes = ("bd_", "hd_", "am_", "lg_") if (args.armors_only or args.cloth_only) else ALLOWED_PREFIXES

    candidate_files = []
    for prefix in prefixes:
        for p in VANILLA_PARTS_DIR.glob(f"{prefix}*.partsbnd.dcx"):
            candidate_files.append(p.name)

    candidate_files = [
        f for f in candidate_files
        if not any(f.lower().startswith(ex) for ex in EXCLUDED_PREFIXES)
    ]

    if args.only:
        candidate_files = [f for f in candidate_files if fnmatch.fnmatch(f, args.only)]

    if args.cloth_only:
        print("Filtering candidate files for Havok cloth physics (_c.hkx)...")
        cloth_files = []
        for f in candidate_files:
            try:
                b = Binder.from_path(str(VANILLA_PARTS_DIR / f))
                if any(e.name.lower().endswith("_c.hkx") for e in b.entries):
                    cloth_files.append(f)
            except Exception:
                pass
        candidate_files = cloth_files

    candidate_files.sort()

    if not candidate_files:
        print("No files matched filter. Exiting.")
        sys.exit(1)

    if args.out_dir:
        mode = f"OUTPUT -> {args.out_dir}"
        Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    elif args.deploy:
        mode = "DEPLOY -> CUSA03173-PSX"
    else:
        mode = f"DRY RUN -> {STAGE_DIR}"
        STAGE_DIR.mkdir(parents=True, exist_ok=True)

    cloth_mode = "HAVOK CLOTH PHYSICS PRESERVED" if args.keep_cloth else "CLOTH DECOUPLED (STIFF)"
    tex_mode = "TEXTURE DEMAKE ENABLED" if not args.no_demake_textures else "TEXTURE DEMAKE DISABLED"

    print(f"=== Multi-Threaded Blender Parts Demake ({len(candidate_files)} files) [{mode}] ===")
    print(f"  Mode         : {cloth_mode} | {tex_mode}")
    print(f"  Armor Ratio  : {args.ratio_armor}")
    print(f"  Weapon Ratio : {args.ratio_weapon}")
    print(f"  Workers      : {args.workers}")

    t0 = time.time()
    success_count = 0
    fail_count = 0
    total_orig = 0
    total_new = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_single_parts_archive,
                fname,
                args.ratio_armor,
                args.ratio_weapon,
                args.deploy,
                args.snapshot,
                args.keep_cloth,
                args.out_dir,
                not args.no_demake_textures,
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
                    print(f"  [OK] {filename:<32}: {o_tris:>6} -> {n_tris:>6} tris ({pct:>5.1f}%)")
                else:
                    fail_count += 1
                    print(f"  [FAIL] {filename:<30}: {msg}")
            except Exception as e:
                fail_count += 1
                print(f"  [EXC] {fname:<31}: {e}")

    dt = time.time() - t0
    saved = total_orig - total_new
    overall_pct = (total_new / total_orig * 100) if total_orig > 0 else 0

    print(f"\n=== Blender Parts Demake Completed in {dt:.1f}s ===")
    print(f"  Processed : {success_count} / {len(candidate_files)} (Failed: {fail_count})")
    print(f"  Triangles : {total_orig:,} -> {total_new:,} ({overall_pct:.1f}%, saved {saved:,} tris)")

    if not args.deploy and not args.out_dir:
        print("\nDry run complete. Use --deploy or --out-dir to write output files.")


if __name__ == "__main__":
    main()

