#!/usr/bin/env python3
"""
tools/verify_modular_mods.py - Acceptance Test Harness for Modular Mod Architecture.

Verifies the 5 modular mod pillars under mods/:
  1. Bloodborne Retro Maps/ (map/ only)
  2. Bloodborne Retro Props and Objects/ (obj/ only)
  3. Bloodborne Retro Armors and Weapons - Cloth Physics/ & - Flat Stiff/ (parts/ only)
  4. Bloodborne Retro Characters/ (chr/ only)
  5. Bloodborne Retro HUD and UI/ (menu/ only)

Checks:
  - Directory existence and dvdroot_ps4 layout
  - mod.json manifest completeness (name, version, pillar, file_count, uncompressed_bytes)
  - Zero path cross-contamination (e.g. no obj in maps, no parts in chr)
  - Standalone toggle safety
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "pipeline"))

from modular_structure_validator import validate_all_pillars  # noqa: E402

MODS_DIR = REPO_ROOT / "mods"


def main():
    parser = argparse.ArgumentParser(description="Acceptance Test for 5-Pillar Modular Mod Architecture.")
    parser.add_argument("--mods-dir", type=Path, default=MODS_DIR, help="Path to mods directory (default: mods/)")
    args = parser.parse_args()

    mods_root = args.mods_dir.resolve()
    print(f"[TEST] Validating Modular Mod Architecture under {mods_root}...")

    results = validate_all_pillars(mods_root)
    overall_pass = True

    for name, res in results.items():
        if res.passed:
            print(f"  [PASS] {name}: {res.file_count} assets, mod.json valid, 0 violations.")
        else:
            print(f"  [FAIL] {name}: exists={res.exists}, has_mod_json={res.has_mod_json}, violations={len(res.violations)}")
            for v in res.violations:
                print(f"    - {v}")
            overall_pass = False

    if overall_pass:
        print("[SUCCESS] All 5 modular mod pillars conform to bbport modular delivery standards.")
        sys.exit(0)
    else:
        print("[FAILURE] Modular mod structure has violations.")
        sys.exit(1)


if __name__ == "__main__":
    main()
