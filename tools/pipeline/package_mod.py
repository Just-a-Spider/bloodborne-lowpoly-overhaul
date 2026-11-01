#!/usr/bin/env python3
"""
package_mod.py - Extract Bloodborne: Low-Poly Overhaul asset delta into a clean standalone bbport mod.

Reads:
  - Base game: CUSA03173/ (read-only reference)
  - PSX stage: CUSA03173-PSX/ (read-only reference)

Writes:
  - Destination mod folder: ../bbport-src/mods/Bloodborne Low-Poly Overhaul/
    (or custom destination via --out)

Filters:
  - Ignores *.bak, *.snap_*, *.glb, and unchanged base game files.
  - Copies ONLY genuinely modified low-poly models and downscaled textures.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

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


def compute_md5(filepath: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Package Bloodborne: Low-Poly Overhaul into a bbport mod.")
    parser.add_argument(
        "--vanilla",
        type=Path,
        default=Path("CUSA03173"),
        help="Path to pristine vanilla CUSA03173 directory (read-only)",
    )
    parser.add_argument(
        "--psx",
        type=Path,
        default=Path("CUSA03173-PSX"),
        help="Path to CUSA03173-PSX directory (read-only)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../bbport-src/mods/Bloodborne Low-Poly Overhaul"),
        help="Output mod directory path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze delta and print statistics without writing files",
    )
    args = parser.parse_args()

    vanilla_dir = args.vanilla.resolve()
    psx_dir = args.psx.resolve()
    out_dir = args.out.resolve()

    if not vanilla_dir.is_dir():
        print(f"Error: Vanilla directory not found: {vanilla_dir}", file=sys.stderr)
        sys.exit(1)
    if not psx_dir.is_dir():
        print(f"Error: PSX directory not found: {psx_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Vanilla source: {vanilla_dir} (read-only)")
    print(f"PSX source:     {psx_dir} (read-only)")
    print(f"Mod target:     {out_dir}")
    if args.dry_run:
        print("[DRY RUN MODE: No files will be written]")
    print("-" * 60)

    start_time = time.time()
    candidates = []

    # 1. Scan PSX folder for candidate files
    print("Scanning CUSA03173-PSX...")
    for root, _, files in os.walk(psx_dir):
        for f in files:
            p_path = Path(root) / f
            # Ignore development snapshots and backups
            ext = p_path.suffix.lower()
            if ext in IGNORE_EXTENSIONS:
                continue
            if any(p_path.name.endswith(ig) for ig in IGNORE_EXTENSIONS):
                continue
            
            rel_path = p_path.relative_to(psx_dir)
            v_path = vanilla_dir / rel_path

            candidates.append((p_path, v_path, rel_path))

    print(f"Total candidate asset files scanned: {len(candidates)}")
    print("Comparing asset byte content against pristine vanilla...")

    modified_files = []
    total_bytes = 0
    by_folder = {}

    for p_path, v_path, rel_path in candidates:
        is_diff = False
        sz = p_path.stat().st_size

        if not v_path.exists():
            is_diff = True
        elif v_path.stat().st_size != sz:
            is_diff = True
        else:
            # Check content hash if size is identical
            if compute_md5(p_path) != compute_md5(v_path):
                is_diff = True

        if is_diff:
            modified_files.append((p_path, rel_path, sz))
            total_bytes += sz
            parts = rel_path.parts
            top_dir = parts[1] if len(parts) > 1 else parts[0]
            by_folder[top_dir] = by_folder.get(top_dir, 0) + 1

    elapsed = time.time() - start_time
    print(f"Comparison finished in {elapsed:.1f}s.")
    print("-" * 60)
    print(f"Strictly modified PSX assets: {len(modified_files)} files")
    print(f"Total uncompressed mod size:   {total_bytes / (1024**2):.1f} MB ({total_bytes / (1024**3):.2f} GB)")
    print("Breakdown by folder:")
    for folder, count in sorted(by_folder.items(), key=lambda x: -x[1]):
        print(f"  dvdroot_ps4/{folder}: {count} files")
    print("-" * 60)

    if args.dry_run:
        print("Dry run complete. Exiting.")
        return

    # 2. Copy files to destination mod folder
    print(f"Copying {len(modified_files)} delta assets to {out_dir}...")
    copied_count = 0
    for p_path, rel_path, sz in modified_files:
        dest_path = out_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p_path, dest_path)
        copied_count += 1
        if copied_count % 500 == 0 or copied_count == len(modified_files):
            print(f"  Progress: {copied_count}/{len(modified_files)} files copied...")

    # 3. Create metadata and readme inside mod directory
    meta = {
        "name": "Bloodborne: Low-Poly Overhaul",
        "version": "1.0.0",
        "game_version": "1.09",
        "description": "Comprehensive low-poly asset overhaul for Bloodborne on PC (ultra-performance and retro aesthetic)",
        "file_count": len(modified_files),
        "uncompressed_bytes": total_bytes,
        "folders": by_folder,
    }
    (out_dir / "mod.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    readme = """Bloodborne: Low-Poly Overhaul
=============================
Standalone loose-file performance and retro overhaul mod for bbport.

Installation:
1. Place this 'Bloodborne Low-Poly Overhaul' directory inside your bbport mods folder:
   ~/.local/share/bbhost/mods/Bloodborne Low-Poly Overhaul/
   (or <bbport-src>/mods/Bloodborne Low-Poly Overhaul/)
2. Enable the mod in mods.json or via the bbport launcher UI.
3. In bbport.ini, enable retro graphics options (optional):
   retro_mode = 1
   retro_dither = 1
   retro_point_filter = 1
   retro_vertex_snap = 1
   retro_affine = 1
"""
    (out_dir / "README.txt").write_text(readme, encoding="utf-8")

    # 4. Verify parity of copied files
    print("Verifying mod file integrity...")
    verify_errors = 0
    for p_path, rel_path, sz in modified_files:
        dest_path = out_dir / rel_path
        if not dest_path.exists() or dest_path.stat().st_size != sz:
            print(f"Verification error on {rel_path}!", file=sys.stderr)
            verify_errors += 1

    if verify_errors == 0:
        print(f"SUCCESS: 100% of {len(modified_files)} assets verified.")
        print(f"Mod successfully packaged into: {out_dir}")
    else:
        print(f"WARNING: {verify_errors} verification errors detected!", file=sys.stderr)


if __name__ == "__main__":
    main()
