#!/usr/bin/env python3
"""
repair_objects_clean.py — Restores pristine FLVER geometry for all obj/ archives while preserving lightweight sliced textures.

Fixes exploded doors, chests, gates, and animated rigs:
- FLVER meshes and bone hierarchies are restored 100% byte-for-byte from pristine vanilla (CUSA03173).
- Embedded TPF textures are sliced cleanly to <= 256px (diffuse) and <= 128px (secondary maps).
- Zero geometry decimation to eliminate all vertex rigging and bone index corruption.
- Havok collision (.hkx) and animation (.anibnd) strictly preserved.
- Clones phantom models (o299921 - o299942) from pristine o299902.
"""

import argparse
import fnmatch
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import soulstruct_patch  # noqa: E402
from soulstruct.containers import Binder  # noqa: E402
from shrink_chr_textures import shrink_tpf, TargetResolver  # noqa: E402

VANILLA_OBJ_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "obj"
SANDBOX_OBJ_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "obj"
PHANTOM_IDS = ["o299921", "o299935", "o299936", "o299937", "o299942"]


def repair_single_object(
    filename: str,
    tex_target: int,
    sec_target: int,
) -> Tuple[str, bool, int, int, str]:
    """
    Restores pristine vanilla FLVER geometry and slices embedded TPFs.
    Returns (filename, success, orig_tex_b, new_tex_b, msg).
    """
    vanilla_path = VANILLA_OBJ_DIR / filename
    sandbox_path = SANDBOX_OBJ_DIR / filename

    if not vanilla_path.exists():
        return filename, False, 0, 0, f"Vanilla file {vanilla_path} does not exist"

    try:
        # Step 1: Load pristine vanilla binder (contains pristine FLVERs, bones, and Havok)
        b = Binder.from_path(str(vanilla_path))
        orig_tex_b = 0
        new_tex_b = 0

        resolver = TargetResolver(tex_target, sec_target)

        # Step 2: Slice embedded TPF textures only; FLVERs remain 100% untouched
        for entry in b.entries:
            if entry.name.endswith(".tpf"):
                raw_tpf = entry.get_uncompressed_data()
                orig_tex_b += len(raw_tpf)
                try:
                    shrunk, _ = shrink_tpf(raw_tpf, want=lambda n: True, target=resolver)
                    new_tex_b += len(shrunk)
                    entry.set_uncompressed_data(shrunk)
                except Exception:
                    new_tex_b += len(raw_tpf)

        sandbox_path.parent.mkdir(parents=True, exist_ok=True)
        # Serialize to bytes directly to prevent Soulstruct .bak creation or extension renaming
        packed = b.to_bytes()
        sandbox_path.write_bytes(packed)

        return filename, True, orig_tex_b, new_tex_b, "OK"

    except Exception as ex:
        return filename, False, 0, 0, str(ex)


def clone_phantoms() -> None:
    """Clones repaired o299902 to phantom objects referenced by Central Yharnam MSB."""
    base_name = "o299902.objbnd.dcx"
    base_path = SANDBOX_OBJ_DIR / base_name

    if not base_path.exists():
        base_path = VANILLA_OBJ_DIR / base_name
        if not base_path.exists():
            return

    for pid in PHANTOM_IDS:
        dst = SANDBOX_OBJ_DIR / f"{pid}.objbnd.dcx"
        shutil.copy2(base_path, dst)
    print(f"[PHANTOMS] Cloned {len(PHANTOM_IDS)} phantom objects from {base_name} into {SANDBOX_OBJ_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Restores pristine FLVER geometry for all objects while preserving sliced textures")
    parser.add_argument("--all", action="store_true", help="Process all 1,880 object archives")
    parser.add_argument("--only", type=str, default="", help="Glob filter (e.g. 'o000600*', 'o29*')")
    parser.add_argument("--target", type=int, default=256, help="Texture target dimension for diffuse (default: 256px)")
    parser.add_argument("--secondary-target", type=int, default=128, help="Texture target dimension for secondary maps (default: 128px)")
    parser.add_argument("--workers", type=int, default=12, help="Number of parallel workers (default: 12)")
    args = parser.parse_args()

    all_vanilla = sorted([p.name for p in VANILLA_OBJ_DIR.glob("*.objbnd.dcx")])
    if not all_vanilla:
        sys.exit(f"No objbnd.dcx files found in {VANILLA_OBJ_DIR}")

    if args.all:
        target_files = all_vanilla
    elif args.only:
        pats = [p.strip() for p in args.only.split(",") if p.strip()]
        target_files = [f for f in all_vanilla if any(fnmatch.fnmatch(f, p) for p in pats)]
    else:
        parser.error("Specify --all or --only <glob>")

    print(f"=== OBJECT REPAIR ENGINE: {len(target_files)} archives ===")
    print(f"Pristine FLVERs: 100% | Tex Target: {args.target}px (sec={args.secondary_target}px) | Workers: {args.workers}")

    tasks = [(f, args.target, args.secondary_target) for f in target_files]
    succeeded = 0
    failed = 0
    total_van_tex = 0
    total_psx_tex = 0

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(repair_single_object, *t): t[0] for t in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            fname, ok, v_tex, p_tex, msg = fut.result()
            if ok:
                succeeded += 1
                total_van_tex += v_tex
                total_psx_tex += p_tex
            else:
                failed += 1
                print(f"  [FAIL] {fname}: {msg}")

            if i % 200 == 0 or i == len(tasks):
                print(f"  [{i}/{len(tasks)}] Repaired... (succeeded: {succeeded}, failed: {failed})", flush=True)

    elapsed = time.time() - t0
    print("\n=================================================================")
    print(f"Repair Complete in {elapsed:.1f}s")
    print(f"Archives: {succeeded} succeeded, {failed} failed")
    if total_van_tex > 0:
        tex_drop = (1.0 - total_psx_tex / total_van_tex) * 100
        print(f"Embedded Textures: {total_van_tex / (1024*1024):.1f} MB -> {total_psx_tex / (1024*1024):.1f} MB (-{tex_drop:.1f}%)")
    print("=================================================================")

    # Handle phantoms
    clone_phantoms()


if __name__ == "__main__":
    main()
