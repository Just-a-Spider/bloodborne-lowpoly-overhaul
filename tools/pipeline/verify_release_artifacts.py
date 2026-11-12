#!/usr/bin/env python3
"""
tools/pipeline/verify_release_artifacts.py - Automated Release Quality Gate & Manifest Generator.

Audits all release .patch artifacts in dist/ against pristine CUSA03173:
  1. Validates container header magic (BBLPO01\x00) and metadata JSON integrity.
  2. Verifies contiguous payload offset layout and exact container file sizing.
  3. Enforces strict modular pillar path confinement and anti-leakage rules.
  4. Executes fast in-memory streaming XOR delta reconstruction with 100% SHA256 validation.
  5. Generates authoritative dist/SHA256SUMS.txt cryptographic checksum manifest.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "pipeline"))

from apply_patch import MAGIC, xor_bytes  # noqa: E402

PILLAR_SUBPATH_RULES: Dict[str, Set[str]] = {
    "bloodborne_retro_maps.patch": {"map"},
    "bloodborne_retro_props.patch": {"obj"},
    "bloodborne_retro_armors_cloth.patch": {"parts"},
    "bloodborne_retro_armors_stiff.patch": {"parts"},
    "bloodborne_retro_characters.patch": {"chr"},
    "bloodborne_retro_hud.patch": {"menu"},
}

FORBIDDEN_HUD_PATHS = {"script", "msg"}


@dataclass
class PatchAuditResult:
    patch_path: Path
    file_size: int
    sha256: str
    total_files: int
    mod_name: str
    structure_valid: bool
    reconstruction_valid: bool
    errors: List[str]
    elapsed: float


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def audit_single_patch_entry(
    entry: dict,
    patch_file: Path,
    payload_start: int,
    vanilla_dir: Path,
) -> Tuple[bool, Optional[str]]:
    """Verifies in-memory XOR delta reconstruction of a single asset without writing to disk."""
    rel_path = Path(entry["path"])
    try:
        with open(patch_file, "rb") as pf:
            pf.seek(payload_start + entry["offset"])
            delta_data = pf.read(entry["length"])

        if entry["type"] == "xor_delta":
            v_path = vanilla_dir / rel_path
            if not v_path.is_file():
                return False, f"Missing base game file: {v_path}"

            v_bytes = v_path.read_bytes()
            if entry.get("vanilla_sha256"):
                v_sha = hashlib.sha256(v_bytes).hexdigest()
                if v_sha != entry["vanilla_sha256"]:
                    return False, f"Vanilla SHA256 mismatch on {rel_path}"

            reconstructed = xor_bytes(delta_data, v_bytes)
        else:
            reconstructed = delta_data

        if len(reconstructed) != entry["target_size"]:
            return False, f"Size mismatch on {rel_path} (expected {entry['target_size']}, got {len(reconstructed)})"

        target_sha = hashlib.sha256(reconstructed).hexdigest()
        if target_sha != entry["target_sha256"]:
            return False, f"Target SHA256 mismatch on {rel_path}"

        return True, None

    except Exception as exc:
        return False, f"Exception verifying {rel_path}: {exc}"


def audit_patch_container(
    patch_file: Path,
    vanilla_dir: Path,
    check_structure: bool,
    workers: int,
) -> PatchAuditResult:
    start_time = time.time()
    errors: List[str] = []
    file_size = patch_file.stat().st_size
    patch_sha = compute_file_sha256(patch_file)

    # 1. Header & Manifest Checks
    try:
        with open(patch_file, "rb") as pf:
            magic = pf.read(8)
            if magic != MAGIC:
                errors.append(f"Invalid magic: {magic!r} != {MAGIC!r}")
                return PatchAuditResult(
                    patch_path=patch_file,
                    file_size=file_size,
                    sha256=patch_sha,
                    total_files=0,
                    mod_name="",
                    structure_valid=False,
                    reconstruction_valid=False,
                    errors=errors,
                    elapsed=time.time() - start_time,
                )

            meta_len = struct.unpack("<I", pf.read(4))[0]
            meta_json_bytes = pf.read(meta_len)
            meta = json.loads(meta_json_bytes.decode("utf-8"))
            payload_start = pf.tell()

    except Exception as exc:
        errors.append(f"Header/JSON parse failure: {exc}")
        return PatchAuditResult(
            patch_path=patch_file,
            file_size=file_size,
            sha256=patch_sha,
            total_files=0,
            mod_name="",
            structure_valid=False,
            reconstruction_valid=False,
            errors=errors,
            elapsed=time.time() - start_time,
        )

    entries = meta.get("files", [])
    total_files = len(entries)
    mod_name = meta.get("mod_name", "")

    # 2. Check payload offset layout and file boundaries
    expected_offset = 0
    for idx, entry in enumerate(entries):
        if entry["offset"] != expected_offset:
            errors.append(f"Entry {idx} ({entry['path']}) offset mismatch: expected {expected_offset}, got {entry['offset']}")
            break
        expected_offset += entry["length"]

    expected_file_size = payload_start + expected_offset
    if file_size != expected_file_size:
        errors.append(f"Container file size mismatch: header expects {expected_file_size} B, file is {file_size} B")

    # 3. Structure and subpath isolation checks
    structure_valid = True
    if check_structure:
        patch_fname = patch_file.name.lower()
        if patch_fname in PILLAR_SUBPATH_RULES:
            allowed_subpaths = PILLAR_SUBPATH_RULES[patch_fname]
            for entry in entries:
                rel = Path(entry["path"])
                parts = rel.parts
                if len(parts) >= 2 and parts[0] == "dvdroot_ps4":
                    subpath = parts[1]
                    if subpath not in allowed_subpaths:
                        errors.append(f"Pillar violation: {rel} (subpath '{subpath}' not in {allowed_subpaths})")
                        structure_valid = False
                elif rel.name not in ("mod.json", "README.txt"):
                    errors.append(f"Unexpected root file: {rel}")
                    structure_valid = False

        if patch_fname == "bloodborne_retro_hud.patch":
            for entry in entries:
                rel = Path(entry["path"])
                if any(f_part in rel.parts for f_part in FORBIDDEN_HUD_PATHS):
                    errors.append(f"HUD corruption: forbidden path component in {rel}")
                    structure_valid = False

    # 4. In-memory roundtrip reconstruction
    reconstruction_valid = True
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_entry = {
            executor.submit(
                audit_single_patch_entry, entry, patch_file, payload_start, vanilla_dir
            ): entry["path"]
            for entry in entries
        }

        for future in concurrent.futures.as_completed(future_to_entry):
            path_str = future_to_entry[future]
            try:
                ok, err = future.result()
                if not ok:
                    errors.append(f"{path_str}: {err}")
                    reconstruction_valid = False
            except Exception as exc:
                errors.append(f"{path_str}: {exc}")
                reconstruction_valid = False

    return PatchAuditResult(
        patch_path=patch_file,
        file_size=file_size,
        sha256=patch_sha,
        total_files=total_files,
        mod_name=mod_name,
        structure_valid=structure_valid,
        reconstruction_valid=reconstruction_valid and (len(errors) == 0),
        errors=errors,
        elapsed=time.time() - start_time,
    )


def generate_checksum_manifest(
    results: List[PatchAuditResult],
    apply_patch_script: Path,
    manifest_out: Path,
):
    """Writes standard sha256sum manifest with header metadata."""
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Bloodborne: Low-Poly Overhaul - Distribution SHA256 Checksums",
        f"# Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "# Verify using: sha256sum -c SHA256SUMS.txt",
        "",
    ]

    for res in sorted(results, key=lambda r: r.patch_path.name):
        lines.append(f"{res.sha256}  {res.patch_path.name}")

    if apply_patch_script.is_file():
        script_sha = compute_file_sha256(apply_patch_script)
        lines.append(f"{script_sha}  apply_patch.py")

    apply_patch_exe = manifest_out.parent / "apply_patch.exe"
    if apply_patch_exe.is_file():
        exe_sha = compute_file_sha256(apply_patch_exe)
        lines.append(f"{exe_sha}  apply_patch.exe")

    manifest_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Checksum manifest written to: {manifest_out}")


def main():
    parser = argparse.ArgumentParser(
        description="Verify all release patch containers and generate cryptographic manifest."
    )
    parser.add_argument(
        "--vanilla",
        "-v",
        type=Path,
        default=Path("CUSA03173"),
        help="Path to pristine vanilla CUSA03173 directory (strictly read-only)",
    )
    parser.add_argument(
        "--dist",
        "-d",
        type=Path,
        default=Path("dist"),
        help="Directory containing compiled .patch files",
    )
    parser.add_argument(
        "--manifest",
        "-m",
        type=Path,
        default=Path("dist/SHA256SUMS.txt"),
        help="Path for generated SHA256SUMS.txt manifest",
    )
    parser.add_argument(
        "--check-structure",
        action="store_true",
        default=True,
        help="Enforce modular pillar isolation rules",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=os.cpu_count() or 4,
        help="Verification worker concurrency",
    )
    args = parser.parse_args()

    vanilla_dir = args.vanilla.resolve()
    dist_dir = args.dist.resolve()
    manifest_file = args.manifest.resolve()
    apply_script = REPO_ROOT / "apply_patch.py"

    if not vanilla_dir.is_dir():
        print(f"Error: Vanilla directory not found: {vanilla_dir}", file=sys.stderr)
        sys.exit(1)
    if not dist_dir.is_dir():
        print(f"Error: Dist directory not found: {dist_dir}", file=sys.stderr)
        sys.exit(1)

    patch_files = sorted(dist_dir.glob("*.patch"))
    if not patch_files:
        print(f"Error: No .patch files found in {dist_dir}", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("Bloodborne: Low-Poly Overhaul - Release Artifact Verification")
    print("=" * 70)
    print(f"Vanilla Reference: {vanilla_dir} (strictly read-only)")
    print(f"Dist Directory:    {dist_dir}")
    print(f"Manifest File:     {manifest_file}")
    print(f"Workers:           {args.workers}")
    print(f"Total Patches:     {len(patch_files)}")
    print("-" * 70)

    results: List[PatchAuditResult] = []
    overall_pass = True

    for p in patch_files:
        print(f"Auditing {p.name:<45} ... ", end="", flush=True)
        res = audit_patch_container(
            patch_file=p,
            vanilla_dir=vanilla_dir,
            check_structure=args.check_structure,
            workers=args.workers,
        )
        results.append(res)

        if res.reconstruction_valid and res.structure_valid and not res.errors:
            print(f"PASS ({res.total_files} files, {res.file_size / (1024**2):.1f} MB, {res.elapsed:.2f}s)")
        else:
            print(f"FAIL ({len(res.errors)} errors, {res.elapsed:.2f}s)")
            for err in res.errors[:5]:
                print(f"    - {err}")
            if len(res.errors) > 5:
                print(f"    ... and {len(res.errors) - 5} more errors.")
            overall_pass = False

    print("-" * 70)
    print("Release Artifacts Inventory:")
    print(f"{'Artifact Name':<42} {'Size':>10}  {'SHA256 Digest':<64}")
    print("-" * 120)
    for res in sorted(results, key=lambda r: r.patch_path.name):
        size_str = f"{res.file_size / (1024**2):.1f} MB"
        print(f"{res.patch_path.name:<42} {size_str:>10}  {res.sha256}")

    if apply_script.is_file():
        script_sha = compute_file_sha256(apply_script)
        script_size = f"{apply_script.stat().st_size / 1024:.1f} KB"
        print(f"{'apply_patch.py':<42} {script_size:>10}  {script_sha}")

    print("-" * 120)

    if overall_pass:
        generate_checksum_manifest(results, apply_script, manifest_file)
        print("=" * 70)
        print("SUCCESS: 100% of release artifacts validated with zero errors.")
        print("Ready for distribution.")
        print("=" * 70)
        sys.exit(0)
    else:
        print("=" * 70, file=sys.stderr)
        print("FAILURE: Release artifacts contain validation errors.", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
