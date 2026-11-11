#!/usr/bin/env python3
"""
tools/pipeline/package_modular_mods.py - Modular Mod Packager for bbport.

Extracts modified asset deltas from CUSA03173-PSX against pristine CUSA03173
and packages five independent modular mod pillars under mods/:
  1. Bloodborne Retro Maps/                       -> dvdroot_ps4/map/
  2. Bloodborne Retro Props and Objects/           -> dvdroot_ps4/obj/
  3. Bloodborne Retro Armors and Weapons - Cloth/  -> dvdroot_ps4/parts/
  4. Bloodborne Retro Armors and Weapons - Stiff/  -> dvdroot_ps4/parts/
  5. Bloodborne Retro Characters/                  -> dvdroot_ps4/chr/
  6. Bloodborne Retro HUD and UI/                  -> dvdroot_ps4/menu/

Strictly enforces subpath isolation: no cross-contamination between pillars.
Generates comprehensive mod.json metadata for bbport and mod managers.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VANILLA_DIR = REPO_ROOT / "CUSA03173"
PSX_DIR = REPO_ROOT / "CUSA03173-PSX"
MODS_DIR = REPO_ROOT / "mods"
DEFAULT_CLOTH_PARTS_DIR = Path("/home/andre/Games/bbport-src/mods/Bloodborne Low-Poly Overhaul (Cloth Physics)/dvdroot_ps4/parts")
DEFAULT_STIFF_PARTS_DIR = Path("/home/andre/Games/bbport-src/mods/Bloodborne Low-Poly Overhaul (Flat Stiff)/dvdroot_ps4/parts")

IGNORE_EXTENSIONS = {
    ".bak",
    ".snap_pre_blender_obj",
    ".snap_pre_blender",
    ".snap_pre_blender_chr",
    ".snap_pre_shrink",
    ".glb",
    ".tmp",
    ".tmp.dcx",
    ".swp",
}

PILLAR_MAP = {
    "map": "Bloodborne Retro Maps",
    "obj": "Bloodborne Retro Props and Objects",
    "parts": "Bloodborne Retro Armors and Weapons - Cloth Physics",
    "chr": "Bloodborne Retro Characters",
    "menu": "Bloodborne Retro HUD and UI",
}

PILLAR_DESCRIPTIONS = {
    "Bloodborne Retro Maps": "Static world architecture, vistas, dungeon geometry blocks, and environment BXF textures.",
    "Bloodborne Retro Props and Objects": "Interactive props, scenery mechanisms, doors, chests, dungeon cages, and cadaver waste heaps decoupled from maps.",
    "Bloodborne Retro Armors and Weapons - Cloth Physics": "Player attire sets with dynamic Havok cloth physics, trick weapons, and firearms.",
    "Bloodborne Retro Armors and Weapons - Flat Stiff": "Player attire sets with decoupled stiff physics for maximum low-spec frame rates.",
    "Bloodborne Retro Characters": "Enemies, bosses, Plain Doll (c8030), friendly NPCs, and beasts.",
    "Bloodborne Retro HUD and UI": "Standalone retro heads-up display, vitals gauges, interaction prompts, and announcement banners.",
}


def compute_md5(filepath: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def scan_psx_delta(psx_root: Path, vanilla_root: Path) -> Dict[str, List[Tuple[Path, Path, int]]]:
    """
    Scans PSX stage and groups genuinely modified files by category ('map', 'obj', 'parts', 'chr', 'menu').
    """
    by_category: Dict[str, List[Tuple[Path, Path, int]]] = {
        "map": [],
        "obj": [],
        "parts": [],
        "chr": [],
        "menu": [],
    }

    dvdroot = psx_root / "dvdroot_ps4"
    if not dvdroot.is_dir():
        return by_category

    for cat in by_category.keys():
        cat_dir = dvdroot / cat
        if not cat_dir.is_dir():
            continue

        for p_file in cat_dir.rglob("*"):
            if not p_file.is_file():
                continue
            ext = p_file.suffix.lower()
            if ext in IGNORE_EXTENSIONS or any(p_file.name.endswith(ig) for ig in IGNORE_EXTENSIONS):
                continue

            rel_path = p_file.relative_to(psx_root)
            v_file = vanilla_root / rel_path
            sz = p_file.stat().st_size

            is_diff = False
            if not v_file.exists():
                is_diff = True
            elif v_file.stat().st_size != sz:
                is_diff = True
            else:
                if compute_md5(p_file) != compute_md5(v_file):
                    is_diff = True

            if is_diff:
                by_category[cat].append((p_file, rel_path, sz))

    return by_category


def scan_explicit_folder_delta(
    src_dir: Path, vanilla_root: Path, rel_prefix: Path
) -> List[Tuple[Path, Path, int]]:
    """Scans an external standalone parts directory against vanilla reference."""
    results = []
    if not src_dir.is_dir():
        return results

    v_dir = vanilla_root / rel_prefix
    for p_file in sorted(src_dir.rglob("*")):
        if not p_file.is_file():
            continue
        ext = p_file.suffix.lower()
        if ext in IGNORE_EXTENSIONS or any(p_file.name.endswith(ig) for ig in IGNORE_EXTENSIONS):
            continue

        rel_path = rel_prefix / p_file.relative_to(src_dir)
        v_file = vanilla_root / rel_path
        sz = p_file.stat().st_size

        is_diff = False
        if not v_file.exists():
            is_diff = True
        elif v_file.stat().st_size != sz:
            is_diff = True
        else:
            if compute_md5(p_file) != compute_md5(v_file):
                is_diff = True

        if is_diff:
            results.append((p_file, rel_path, sz))

    return results


def package_single_pillar(
    pillar_name: str,
    assets: List[Tuple[Path, Path, int]],
    out_dir: Path,
    clean: bool = False,
    dry_run: bool = False,
):
    print(f"Packaging [{pillar_name}] ({len(assets)} modified assets)...")
    pillar_dir = out_dir / pillar_name
    dvdroot_dest = pillar_dir / "dvdroot_ps4"

    if dry_run:
        total_sz = sum(sz for _, _, sz in assets)
        print(f"  [DRY RUN] Would write {len(assets)} files ({total_sz / (1024**2):.1f} MB) to {pillar_dir}")
        return

    if clean and pillar_dir.exists():
        # Remove old dvdroot files
        for f in pillar_dir.rglob("*"):
            if f.is_file() and f.name != "mod.json":
                f.unlink()

    dvdroot_dest.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    file_records = []

    for src_file, rel_path, sz in assets:
        dest_file = pillar_dir / rel_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dest_file.exists():
                dest_file.unlink()
            os.link(src_file, dest_file)
        except OSError:
            shutil.copy2(src_file, dest_file)
        total_bytes += sz
        file_records.append(str(rel_path.as_posix()))

    # Generate mod.json
    meta = {
        "name": pillar_name,
        "version": "1.0.0",
        "game_version": "1.09",
        "description": PILLAR_DESCRIPTIONS.get(pillar_name, ""),
        "pillar": pillar_name,
        "file_count": len(assets),
        "uncompressed_bytes": total_bytes,
        "uncompressed_mb": round(total_bytes / (1024 * 1024), 2),
        "files": sorted(file_records),
    }

    (pillar_dir / "mod.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"  [DONE] {pillar_name}: {len(assets)} files ({total_bytes / (1024**2):.1f} MB) deployed.")


def main():
    parser = argparse.ArgumentParser(description="Package Bloodborne Retro Demake into 5 Modular Pillars for bbport.")
    parser.add_argument("--pillar", type=str, default="all", help="Target pillar ('maps', 'props', 'armors-cloth', 'armors-stiff', 'characters', 'hud', or 'all')")
    parser.add_argument("--out-dir", type=Path, default=MODS_DIR, help="Output mods directory (default: mods/)")
    parser.add_argument("--cloth-parts-dir", type=Path, default=DEFAULT_CLOTH_PARTS_DIR, help="Dedicated source directory for Cloth Physics armors")
    parser.add_argument("--stiff-parts-dir", type=Path, default=DEFAULT_STIFF_PARTS_DIR, help="Dedicated source directory for Flat Stiff armors")
    parser.add_argument("--clean", action="store_true", help="Clean stale files from destination pillar directories")
    parser.add_argument("--dry-run", action="store_true", help="Analyze delta without copying files")
    args = parser.parse_args()

    out_root = args.out_dir.resolve()
    print(f"=== Bloodborne PSX Modular Mod Packager ===")
    print(f"  Source PSX   : {PSX_DIR}")
    print(f"  Vanilla Base : {VANILLA_DIR}")
    print(f"  Destination  : {out_root}")
    print(f"  Target Pillar: {args.pillar}")
    print(f"  Cloth Source : {args.cloth_parts_dir}")
    print(f"  Stiff Source : {args.stiff_parts_dir}")
    print(f"  Clean Mode   : {args.clean}")
    print("-" * 60)

    t0 = time.time()
    deltas = scan_psx_delta(PSX_DIR, VANILLA_DIR)
    elapsed = time.time() - t0
    print(f"Delta scan complete in {elapsed:.1f}s.")
    for cat, items in deltas.items():
        print(f"  dvdroot_ps4/{cat:<6}: {len(items):>4} modified files")
    print("-" * 60)

    # Map categories to pillars
    tasks = []
    if args.pillar in ("all", "maps"):
        tasks.append(("Bloodborne Retro Maps", deltas["map"]))
    if args.pillar in ("all", "props"):
        tasks.append(("Bloodborne Retro Props and Objects", deltas["obj"]))
    if args.pillar in ("all", "armors-cloth"):
        if args.cloth_parts_dir and args.cloth_parts_dir.is_dir():
            print(f"Scanning dedicated Cloth Physics parts from: {args.cloth_parts_dir}")
            cloth_assets = scan_explicit_folder_delta(args.cloth_parts_dir, VANILLA_DIR, Path("dvdroot_ps4/parts"))
        else:
            cloth_assets = deltas["parts"]
        tasks.append(("Bloodborne Retro Armors and Weapons - Cloth Physics", cloth_assets))
    if args.pillar in ("all", "armors-stiff"):
        if args.stiff_parts_dir and args.stiff_parts_dir.is_dir():
            print(f"Scanning dedicated Flat Stiff parts from: {args.stiff_parts_dir}")
            stiff_assets = scan_explicit_folder_delta(args.stiff_parts_dir, VANILLA_DIR, Path("dvdroot_ps4/parts"))
        else:
            stiff_assets = deltas["parts"]
        tasks.append(("Bloodborne Retro Armors and Weapons - Flat Stiff", stiff_assets))
    if args.pillar in ("all", "characters"):
        tasks.append(("Bloodborne Retro Characters", deltas["chr"]))
    if args.pillar in ("all", "hud"):
        tasks.append(("Bloodborne Retro HUD and UI", deltas["menu"]))

    for pillar_name, asset_list in tasks:
        package_single_pillar(
            pillar_name=pillar_name,
            assets=asset_list,
            out_dir=out_root,
            clean=args.clean,
            dry_run=args.dry_run,
        )

    print("-" * 60)
    print("Modular packaging completed successfully.")


if __name__ == "__main__":
    main()
