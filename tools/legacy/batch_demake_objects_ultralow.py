#!/usr/bin/env python3
"""
batch_demake_objects_ultralow.py — Ultra-Low-Poly Demake & Texture Shrink Engine for Interactive Objects (obj/).

Processes all 1,880 world props and breakables (oXXXXXX.objbnd.dcx):
- QEM edge-collapse polygon decimation (~0.35 ratio, ~65% triangle reduction) via mesh_decimator.py.
- Lossless top-level mip slicing for embedded TPF textures (diffuse/normal/specular <= 256px).
- Byte-for-byte preservation of Havok collision (.hkx), animation (.anibnd), and dummies.
- Phantom model generation (o299921, o299935, o299936, o299937, o299942) cloned from demade o299902.
- Zero modifications to pristine CUSA03173/ or user save files.

Usage:
    uv run python tools/batch_demake_objects_ultralow.py --only 'o000100*'             # dry-run single object
    uv run python tools/batch_demake_objects_ultralow.py --only 'o000100*' --deploy    # deploy single object
    uv run python tools/batch_demake_objects_ultralow.py --all --deploy --workers 12   # batch deploy all
"""

import argparse
import fnmatch
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import soulstruct_patch  # noqa: E402
from soulstruct.containers import Binder  # noqa: E402
from soulstruct.flver import FLVER  # noqa: E402
from mesh_decimator import decimate_flver  # noqa: E402
from shrink_chr_textures import shrink_tpf  # noqa: E402

VANILLA_OBJ_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "obj"
SANDBOX_OBJ_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "obj"
STAGE_DIR = Path("/tmp/obj_ultralow_stage")
PHANTOM_IDS = ["o299921", "o299935", "o299936", "o299937", "o299942"]


def process_single_object(
    filename: str,
    ratio: float,
    tex_target: int,
    deploy: bool,
) -> Tuple[str, bool, int, int, int, int, str]:
    """
    Processes a single objbnd.dcx archive.
    Returns (filename, success, orig_tris, new_tris, orig_tex_b, new_tex_b, msg).
    """
    vanilla_path = VANILLA_OBJ_DIR / filename
    sandbox_path = SANDBOX_OBJ_DIR / filename
    stage_path = STAGE_DIR / filename

    if not vanilla_path.exists():
        return filename, False, 0, 0, 0, 0, f"Vanilla file {vanilla_path} does not exist"

    try:
        b = Binder.from_path(str(vanilla_path))
        orig_tris = 0
        new_tris = 0
        orig_tex_b = 0
        new_tex_b = 0

        # Step 1: Process FLVER entries
        for entry in b.entries:
            if entry.name.endswith(".flver") and len(entry.get_uncompressed_data()) > 0x100:
                raw_flv = entry.get_uncompressed_data()
                flv = FLVER.from_bytes(raw_flv)

                t_orig = sum(len(m.face_sets[0].vertex_indices) for m in flv.meshes if m.face_sets)
                orig_tris += t_orig

                if t_orig > 0:
                    decimate_flver(
                        flv,
                        target_ratio=ratio,
                        flat_normals=False,
                        disable_cloth=False,
                        preserve_border=False,
                        filename=filename,
                    )
                    t_new = sum(len(m.face_sets[0].vertex_indices) for m in flv.meshes if m.face_sets)
                    new_tris += t_new
                else:
                    new_tris += t_orig

                entry.set_uncompressed_data(flv.to_bytes())

        # Step 2: Process TPF entries (lossless mip slicing)
        for entry in b.entries:
            if entry.name.endswith(".tpf"):
                raw_tpf = entry.get_uncompressed_data()
                orig_tex_b += len(raw_tpf)
                try:
                    shrunk, _ = shrink_tpf(raw_tpf, want=lambda n: True, target=tex_target)
                    new_tex_b += len(shrunk)
                    entry.set_uncompressed_data(shrunk)
                except Exception:
                    # Keep raw TPF if layout doesn't support slicing
                    new_tex_b += len(raw_tpf)

        target_path = sandbox_path if deploy else stage_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        b.write(str(target_path))

        return filename, True, orig_tris, new_tris, orig_tex_b, new_tex_b, "OK"

    except Exception as ex:
        return filename, False, 0, 0, 0, 0, str(ex)


def clone_phantoms(deploy: bool) -> None:
    """Clones demade o299902 to phantom objects referenced by Central Yharnam MSB."""
    base_name = "o299902.objbnd.dcx"
    target_dir = SANDBOX_OBJ_DIR if deploy else STAGE_DIR
    base_path = target_dir / base_name

    if not base_path.exists():
        base_path = VANILLA_OBJ_DIR / base_name
        if not base_path.exists():
            return

    for pid in PHANTOM_IDS:
        dst = target_dir / f"{pid}.objbnd.dcx"
        shutil.copy2(base_path, dst)
    print(f"[PHANTOMS] Cloned {len(PHANTOM_IDS)} phantom objects from {base_name} into {target_dir}")


def main():
    parser = argparse.ArgumentParser(description="Ultra-Low-Poly Demake Engine for Interactive Objects")
    parser.add_argument("--all", action="store_true", help="Process all 1,880 object archives")
    parser.add_argument("--only", type=str, default="", help="Glob filter (e.g. 'o000100*', 'o29*')")
    parser.add_argument("--ratio", type=float, default=0.35, help="QEM target decimation ratio (default: 0.35)")
    parser.add_argument("--target", type=int, default=256, help="Texture mip slice dimension target (default: 256px)")
    parser.add_argument("--workers", type=int, default=12, help="Number of parallel workers (default: 12)")
    parser.add_argument("--deploy", action="store_true", help="Deploy directly to CUSA03173-PSX/dvdroot_ps4/obj")
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

    print(f"=== OBJECT DEMAKE ENGINE: {len(target_files)} archives ===")
    print(f"Ratio: {args.ratio} | Tex Target: {args.target}px | Workers: {args.workers} | Deploy: {args.deploy}")

    if not args.deploy:
        STAGE_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [(f, args.ratio, args.target, args.deploy) for f in target_files]
    succeeded = 0
    failed = 0
    total_van_tris = 0
    total_psx_tris = 0
    total_van_tex = 0
    total_psx_tex = 0

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_single_object, *t): t[0] for t in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            fname, ok, v_tris, p_tris, v_tex, p_tex, msg = fut.result()
            if ok:
                succeeded += 1
                total_van_tris += v_tris
                total_psx_tris += p_tris
                total_van_tex += v_tex
                total_psx_tex += p_tex
            else:
                failed += 1
                print(f"  [FAIL] {fname}: {msg}")

            if i % 100 == 0 or i == len(tasks):
                print(f"  [{i}/{len(tasks)}] Done... (succeeded: {succeeded}, failed: {failed})", flush=True)

    elapsed = time.time() - t0
    print("\n=================================================================")
    print(f"Processing Complete in {elapsed:.1f}s")
    print(f"Archives: {succeeded} succeeded, {failed} failed")
    if total_van_tris > 0:
        tri_drop = (1.0 - total_psx_tris / total_van_tris) * 100
        print(f"Triangles: {total_van_tris:,} -> {total_psx_tris:,} (-{tri_drop:.1f}%, cut {total_van_tris - total_psx_tris:,} tris)")
    if total_van_tex > 0:
        tex_drop = (1.0 - total_psx_tex / total_van_tex) * 100
        print(f"Embedded Textures: {total_van_tex / (1024*1024):.1f} MB -> {total_psx_tex / (1024*1024):.1f} MB (-{tex_drop:.1f}%)")
    print("=================================================================")

    # Handle phantoms
    clone_phantoms(args.deploy)


if __name__ == "__main__":
    main()

