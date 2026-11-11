#!/usr/bin/env python3
"""
apply_patch.py - Standalone client-side reconstructor for Bloodborne: Low-Poly Overhaul.

Reconstructs standalone Bloodborne mod pillars (or full overhauls) from a legal retail
copy of Bloodborne (CUSA03173) and unified .patch containers.

Zero external dependencies required: runs on standard Python 3.9+ using only the
standard library (hashlib, struct, json, pathlib, shutil, concurrent.futures).
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import struct
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MAGIC = b"BBLPO01\x00"

FILENAME_TO_MOD_DIR: Dict[str, str] = {
    "bloodborne_retro_hud.patch": "Bloodborne Retro HUD and UI",
    "bloodborne_retro_maps.patch": "Bloodborne Retro Maps",
    "bloodborne_retro_props.patch": "Bloodborne Retro Props and Objects",
    "bloodborne_retro_armors_cloth.patch": "Bloodborne Retro Armors and Weapons - Cloth Physics",
    "bloodborne_retro_armors_stiff.patch": "Bloodborne Retro Armors and Weapons - Flat Stiff",
    "bloodborne_retro_characters.patch": "Bloodborne Retro Characters",
    "bloodborne_lowpoly_overhaul_cloth.patch": "Bloodborne Low-Poly Overhaul (Cloth Physics)",
    "bloodborne_lowpoly_overhaul_stiff.patch": "Bloodborne Low-Poly Overhaul (Flat Stiff)",
    "bloodborne_lowpoly_overhaul.patch": "Bloodborne Low-Poly Overhaul",
}


def infer_mod_dir_name(patch_file: Path, meta: Optional[dict] = None) -> str:
    """Infer the canonical output directory name from patch metadata or filename."""
    if meta and meta.get("mod_name"):
        return meta["mod_name"]

    name_lower = patch_file.name.lower()
    for pattern, dir_name in FILENAME_TO_MOD_DIR.items():
        if pattern == name_lower:
            return dir_name

    # Fuzzy matches
    if "hud" in name_lower:
        return "Bloodborne Retro HUD and UI"
    if "props" in name_lower or "obj" in name_lower:
        return "Bloodborne Retro Props and Objects"
    if "maps" in name_lower or "map" in name_lower:
        return "Bloodborne Retro Maps"
    if "armors_cloth" in name_lower:
        return "Bloodborne Retro Armors and Weapons - Cloth Physics"
    if "armors_stiff" in name_lower:
        return "Bloodborne Retro Armors and Weapons - Flat Stiff"
    if "characters" in name_lower or "chr" in name_lower:
        return "Bloodborne Retro Characters"
    if "overhaul_cloth" in name_lower:
        return "Bloodborne Low-Poly Overhaul (Cloth Physics)"
    if "overhaul_stiff" in name_lower:
        return "Bloodborne Low-Poly Overhaul (Flat Stiff)"

    return "Bloodborne Low-Poly Overhaul"


def xor_bytes(a: bytes, b: bytes) -> bytes:
    """Fast integer-vectorized XOR in pure Python."""
    min_len = min(len(a), len(b))
    if min_len == 0:
        return a
    a_int = int.from_bytes(a[:min_len], "little")
    b_int = int.from_bytes(b[:min_len], "little")
    xor_int = a_int ^ b_int
    return xor_int.to_bytes(min_len, "little") + a[min_len:]


def patch_single_file(
    entry: dict,
    patch_file_path: Path,
    payload_start: int,
    game_dir: Path,
    out_dir: Path,
    verify_sha: bool,
) -> Tuple[bool, Optional[str]]:
    """Reconstruct a single asset file from patch data (streaming on-demand read)."""
    rel_path = Path(entry["path"])
    dest_path = out_dir / rel_path

    try:
        with open(patch_file_path, "rb") as pf:
            pf.seek(payload_start + entry["offset"])
            delta_data = pf.read(entry["length"])

        if entry["type"] == "xor_delta":
            src_path = game_dir / rel_path
            if not src_path.is_file():
                return False, f"Missing base game file: {src_path}"

            v_bytes = src_path.read_bytes()

            # Check vanilla hash if specified
            if verify_sha and entry.get("vanilla_sha256"):
                v_sha = hashlib.sha256(v_bytes).hexdigest()
                if v_sha != entry["vanilla_sha256"]:
                    return (
                        False,
                        f"Base game hash mismatch on {rel_path} (Expected {entry['vanilla_sha256']}, got {v_sha})",
                    )

            reconstructed = xor_bytes(delta_data, v_bytes)
        else:
            # Standalone full file
            reconstructed = delta_data

        # Verify target hash
        if verify_sha and entry.get("target_sha256"):
            target_sha = hashlib.sha256(reconstructed).hexdigest()
            if target_sha != entry["target_sha256"]:
                return (
                    False,
                    f"Reconstructed hash mismatch on {rel_path} (Expected {entry['target_sha256']}, got {target_sha})",
                )

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(reconstructed)
        return True, None

    except Exception as exc:
        return False, f"I/O failure on {rel_path}: {exc}"


def find_default_patch() -> Optional[Path]:
    candidates = [
        Path("bloodborne_lowpoly_overhaul.patch"),
        Path("dist/bloodborne_lowpoly_overhaul.patch"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def read_patch_metadata(patch_file: Path) -> Tuple[dict, int]:
    """Reads header magic and metadata JSON, returning (metadata_dict, payload_start_offset)."""
    with open(patch_file, "rb") as pf:
        header_magic = pf.read(8)
        if header_magic != MAGIC:
            raise ValueError(f"Invalid patch file magic in {patch_file}: {header_magic!r}")

        meta_len = struct.unpack("<I", pf.read(4))[0]
        meta_json_bytes = pf.read(meta_len)
        meta = json.loads(meta_json_bytes.decode("utf-8"))
        payload_start = pf.tell()
        return meta, payload_start


def check_disk_space(dest_dir: Path, required_bytes: int):
    """Verifies sufficient disk space is available at dest_dir."""
    target_parent = dest_dir.parent if not dest_dir.exists() else dest_dir
    try:
        total, used, free = shutil.disk_usage(target_parent)
        buffer_bytes = 50 * 1024 * 1024  # 50 MB safety margin
        if free < (required_bytes + buffer_bytes):
            req_mb = required_bytes / (1024**2)
            free_mb = free / (1024**2)
            raise OSError(
                f"Insufficient disk space on target volume ({target_parent}). "
                f"Required: {req_mb:.1f} MB, Available: {free_mb:.1f} MB."
            )
    except (FileNotFoundError, PermissionError):
        pass


def apply_single_patch(
    patch_file: Path,
    game_dir: Path,
    out_dir: Path,
    workers: int,
    verify_sha: bool,
) -> bool:
    """Applies a single patch file to destination folder."""
    print("=" * 65)
    print("Bloodborne: Low-Poly Overhaul - Standalone Mod Reconstructor")
    print("=" * 65)
    print(f"Base Game:         {game_dir} (read-only)")
    print(f"Patch File:        {patch_file}")
    print(f"Destination:       {out_dir}")
    print(f"Parallel Workers:  {workers}")
    print(f"Engine:            Pure Python XOR Differential (Zero Dependencies)")
    print("-" * 65)

    start_time = time.time()

    # 1. Read patch header
    print("Reading patch manifest...")
    try:
        meta, payload_start = read_patch_metadata(patch_file)
    except Exception as exc:
        print(f"Error reading patch file: {exc}", file=sys.stderr)
        return False

    total_files = len(meta["files"])
    print(f"Mod name:          {meta.get('mod_name', out_dir.name)}")
    print(f"Mod version:       {meta.get('version', '1.0.0')}")
    print(f"Vanilla title:     {meta.get('vanilla_title', 'Bloodborne')}")
    print(f"Total delta files: {total_files}")

    # Check disk space
    total_target_bytes = sum(entry.get("target_size", entry["length"]) for entry in meta["files"])
    try:
        check_disk_space(out_dir, total_target_bytes)
    except OSError as o_err:
        print(f"Error: {o_err}", file=sys.stderr)
        return False

    print("-" * 65)

    # 2. Extract and apply patches in parallel
    print(f"Reconstructing {total_files} mod assets...")
    errors: List[Tuple[str, str]] = []
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {
            executor.submit(
                patch_single_file, entry, patch_file, payload_start, game_dir, out_dir, verify_sha
            ): entry["path"]
            for entry in meta["files"]
        }

        for future in concurrent.futures.as_completed(future_to_file):
            path_str = future_to_file[future]
            completed += 1
            try:
                success, err_msg = future.result()
                if not success:
                    errors.append((path_str, err_msg or "Unknown error"))
            except Exception as exc:
                errors.append((path_str, str(exc)))

            if completed % 500 == 0 or completed == total_files:
                print(
                    f"  Progress: {completed}/{total_files} files reconstructed ({completed*100/total_files:.1f}%)...",
                    flush=True,
                )

    elapsed = time.time() - start_time
    print("-" * 65)

    if errors:
        print(f"ERROR: {len(errors)} files failed reconstruction:", file=sys.stderr)
        for path_str, err_msg in errors[:10]:
            print(f"  - {path_str}: {err_msg}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors.", file=sys.stderr)
        return False

    print(f"SUCCESS: 100% of {total_files} assets successfully reconstructed in {elapsed:.2f}s.")
    print(f"Reconstructed mod output: {out_dir}")
    print("=" * 65)
    return True


def discover_patches(search_dir: Path) -> List[Path]:
    """Discover all .patch files in directory."""
    if not search_dir.is_dir():
        return []
    return sorted(search_dir.glob("*.patch"))


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct Bloodborne: Low-Poly Overhaul mod from vanilla game and .patch file."
    )
    parser.add_argument(
        "--game",
        "-g",
        type=Path,
        required=True,
        help="Path to retail Bloodborne directory (e.g. /path/to/CUSA03173)",
    )
    parser.add_argument(
        "--patch",
        "-p",
        type=Path,
        default=None,
        help="Path to .patch container file (default: auto-detected in current directory or dist/)",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        required=True,
        help="Destination directory for reconstructed mod (required; for --all-patches, base directory where mod folders will be placed)",
    )
    parser.add_argument(
        "--mods-dir",
        "-m",
        type=Path,
        default=None,
        help="Alias for --out (base directory for mod reconstruction)",
    )
    parser.add_argument(
        "--all-patches",
        "-a",
        action="store_true",
        help="Batch reconstruct all .patch files found in patch directory into dedicated subfolders",
    )
    parser.add_argument(
        "--patch-dir",
        type=Path,
        default=None,
        help="Directory to search for patch files (default: dist/ or current directory)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=os.cpu_count() or 4,
        help="Parallel worker threads (default: CPU core count)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip SHA256 integrity verification (faster on slow CPUs)",
    )
    args = parser.parse_args()

    game_dir = args.game.resolve()
    if not game_dir.is_dir():
        print(f"Error: Game directory not found: {game_dir}", file=sys.stderr)
        sys.exit(1)
    if not (game_dir / "dvdroot_ps4").is_dir():
        print(
            f"Error: Invalid game directory. 'dvdroot_ps4' not found inside {game_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    verify_sha = not args.no_verify

    # Handle batch reconstruction mode
    if args.all_patches:
        search_dirs = [args.patch_dir] if args.patch_dir else [Path("dist"), Path(".")]
        patches_found: List[Path] = []
        for s_dir in search_dirs:
            if s_dir and s_dir.is_dir():
                for p in discover_patches(s_dir):
                    if p not in patches_found:
                        patches_found.append(p)

        if not patches_found:
            print("Error: No .patch files found to batch reconstruct.", file=sys.stderr)
            sys.exit(1)

        base_out_dir = (args.out or args.mods_dir).resolve()
        base_out_dir.mkdir(parents=True, exist_ok=True)

        print(f"Batch reconstructing {len(patches_found)} patch containers into {base_out_dir}...")
        all_passed = True
        for p in patches_found:
            try:
                meta, _ = read_patch_metadata(p)
            except Exception:
                meta = {}
            target_subfolder = infer_mod_dir_name(p, meta)
            target_out = base_out_dir / target_subfolder

            success = apply_single_patch(
                patch_file=p,
                game_dir=game_dir,
                out_dir=target_out,
                workers=args.workers,
                verify_sha=verify_sha,
            )
            if not success:
                all_passed = False

        if not all_passed:
            print("Batch reconstruction encountered errors.", file=sys.stderr)
            sys.exit(1)
        print("All batch patches successfully reconstructed.")
        sys.exit(0)

    # Handle single patch reconstruction
    patch_path = args.patch or find_default_patch()
    if not patch_path:
        print(
            "Error: No .patch file specified and no default patch file found in '.' or 'dist/'.",
            file=sys.stderr,
        )
        print("Please supply --patch <path/to/mod.patch>", file=sys.stderr)
        sys.exit(1)

    patch_file = patch_path.resolve()
    if not patch_file.is_file():
        print(f"Error: Patch file not found: {patch_file}", file=sys.stderr)
        sys.exit(1)

    # Determine destination directory
    try:
        meta, _ = read_patch_metadata(patch_file)
    except Exception:
        meta = {}

    out_dir = (args.out or args.mods_dir).resolve()

    success = apply_single_patch(
        patch_file=patch_file,
        game_dir=game_dir,
        out_dir=out_dir,
        workers=args.workers,
        verify_sha=verify_sha,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
