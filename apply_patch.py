#!/usr/bin/env python3
"""
apply_patch.py - Standalone client-side generator for Bloodborne: Low-Poly Overhaul.

Reconstructs the complete standalone 'Bloodborne: Low-Poly Overhaul' mod (2,669 files, 1.26 GB)
from a legal retail copy of Bloodborne (CUSA03173) and a unified .patch container.

Zero external dependencies required: runs on standard Python 3.9+ using only the
standard library (hashlib, struct, json, pathlib, concurrent.futures).
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path

MAGIC = b"BBLPO01\x00"


def xor_bytes(a: bytes, b: bytes) -> bytes:
    """Fast integer-vectorized XOR in pure Python."""
    min_len = min(len(a), len(b))
    if min_len == 0:
        return a
    a_int = int.from_bytes(a[:min_len], "little")
    b_int = int.from_bytes(b[:min_len], "little")
    xor_int = a_int ^ b_int
    return xor_int.to_bytes(min_len, "little") + a[min_len:]


def patch_single_file(entry, patch_file_path: Path, payload_start: int, game_dir: Path, out_dir: Path, verify_sha: bool):
    """Reconstruct a single asset file from patch data (streaming on-demand read)."""
    rel_path = Path(entry["path"])
    dest_path = out_dir / rel_path

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


def find_default_patch() -> Path | None:
    candidates = [
        Path("bloodborne_lowpoly_overhaul.patch"),
        Path("dist/bloodborne_lowpoly_overhaul.patch"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


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
        default=Path("Bloodborne Low-Poly Overhaul"),
        help="Destination directory for reconstructed mod (default: 'Bloodborne Low-Poly Overhaul')",
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
    patch_path = args.patch or find_default_patch()
    if not patch_path:
        print("Error: No .patch file specified and no default patch file found in '.' or 'dist/'.", file=sys.stderr)
        print("Please supply --patch <path/to/bloodborne_lowpoly_overhaul.patch>", file=sys.stderr)
        sys.exit(1)

    patch_file = patch_path.resolve()
    out_dir = args.out.resolve()

    if not game_dir.is_dir():
        print(f"Error: Game directory not found: {game_dir}", file=sys.stderr)
        sys.exit(1)
    if not (game_dir / "dvdroot_ps4").is_dir():
        print(
            f"Error: Invalid game directory. 'dvdroot_ps4' not found inside {game_dir}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not patch_file.is_file():
        print(f"Error: Patch file not found: {patch_file}", file=sys.stderr)
        sys.exit(1)

    print("=" * 65)
    print("Bloodborne: Low-Poly Overhaul - Standalone Mod Reconstructor")
    print("=" * 65)
    print(f"Base Game:         {game_dir} (read-only)")
    print(f"Patch File:        {patch_file}")
    print(f"Destination:       {out_dir}")
    print(f"Parallel Workers:  {args.workers}")
    print(f"Engine:            Pure Python XOR Differential (Zero Dependencies)")
    print("-" * 65)

    start_time = time.time()

    # 1. Read patch header
    print("Reading patch manifest...")
    with open(patch_file, "rb") as pf:
        header_magic = pf.read(8)
        if header_magic != MAGIC:
            print(f"Error: Invalid patch file magic: {header_magic!r}", file=sys.stderr)
            sys.exit(1)

        meta_len = struct.unpack("<I", pf.read(4))[0]
        meta_json_bytes = pf.read(meta_len)
        meta = json.loads(meta_json_bytes.decode("utf-8"))
        payload_start = pf.tell()

        total_files = len(meta["files"])
        print(f"Mod version:       {meta.get('version', '1.0.0')}")
        print(f"Vanilla title:     {meta.get('vanilla_title', 'Bloodborne')}")
        print(f"Total delta files: {total_files}")
        print("-" * 65)

    # 2. Extract and apply patches in parallel
    print(f"Reconstructing {total_files} mod assets...")
    errors = []
    completed = 0
    verify_sha = not args.no_verify

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
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
                    errors.append((path_str, err_msg))
            except Exception as exc:
                errors.append((path_str, str(exc)))

            if completed % 500 == 0 or completed == total_files:
                print(f"  Progress: {completed}/{total_files} files reconstructed ({completed*100/total_files:.1f}%)...", flush=True)

    elapsed = time.time() - start_time
    print("-" * 65)

    if errors:
        print(f"ERROR: {len(errors)} files failed reconstruction:", file=sys.stderr)
        for path_str, err_msg in errors[:10]:
            print(f"  - {path_str}: {err_msg}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors.", file=sys.stderr)
        sys.exit(1)

    print(f"SUCCESS: 100% of {total_files} assets successfully reconstructed in {elapsed:.2f}s.")
    print(f"Mod folder ready at: {out_dir}")
    print()
    print("Installation Instructions:")
    print(f"1. Move or symlink '{out_dir.name}' to your bbport mods folder:")
    print(f"   ~/.local/share/bbhost/mods/{out_dir.name}/")
    print(f"   (or <bbport-src>/mods/{out_dir.name}/)")
    print(f"2. Enable '{out_dir.name}' in the bbport launcher or mods.json.")
    print("3. In bbport.ini, enable retro graphics options (optional):")
    print("   retro_mode = 1")
    print("=" * 65)


if __name__ == "__main__":
    main()
