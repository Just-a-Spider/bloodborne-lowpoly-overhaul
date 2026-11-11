#!/usr/bin/env python3
"""
tools/pipeline/modular_structure_validator.py - Modular Mod Architecture Validator.

Enforces five-pillar modular architecture rules under mods/:
1. Bloodborne Retro Maps/                       -> dvdroot_ps4/map/
2. Bloodborne Retro Props and Objects/           -> dvdroot_ps4/obj/
3. Bloodborne Retro Armors and Weapons - Cloth/  -> dvdroot_ps4/parts/
4. Bloodborne Retro Characters/                  -> dvdroot_ps4/chr/
5. Bloodborne Retro HUD and UI/                  -> dvdroot_ps4/menu/

Ensures zero path cross-contamination, valid mod.json manifests, and standalone toggle safety.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple
import json


PILLAR_SPECS: Dict[str, Dict] = {
    "Bloodborne Retro Maps": {
        "allowed_subpaths": {"map"},
        "forbidden_subpaths": {"obj", "parts", "chr", "menu"},
        "allowed_extensions": {".flver.dcx", ".tpfbdt", ".tpfbhd", ".msb.dcx"},
    },
    "Bloodborne Retro Props and Objects": {
        "allowed_subpaths": {"obj"},
        "forbidden_subpaths": {"map", "parts", "chr", "menu"},
        "allowed_extensions": {".objbnd.dcx", ".tpf.dcx"},
    },
    "Bloodborne Retro Armors and Weapons - Cloth Physics": {
        "allowed_subpaths": {"parts"},
        "forbidden_subpaths": {"map", "obj", "chr", "menu"},
        "allowed_extensions": {".partsbnd.dcx", ".tpf.dcx"},
    },
    "Bloodborne Retro Armors and Weapons - Flat Stiff": {
        "allowed_subpaths": {"parts"},
        "forbidden_subpaths": {"map", "obj", "chr", "menu"},
        "allowed_extensions": {".partsbnd.dcx", ".tpf.dcx"},
    },
    "Bloodborne Retro Characters": {
        "allowed_subpaths": {"chr"},
        "forbidden_subpaths": {"map", "obj", "parts", "menu"},
        "allowed_extensions": {".chrbnd.dcx", ".tpf.dcx"},
    },
    "Bloodborne Retro HUD and UI": {
        "allowed_subpaths": {"menu", "msg", "script"},
        "forbidden_subpaths": {"map", "obj", "parts", "chr"},
        "allowed_extensions": {".tpf.dcx", ".msgbnd.dcx", ".talkesdbnd.dcx"},
    },
}


@dataclass
class PillarValidationResult:
    pillar_name: str
    exists: bool
    has_mod_json: bool
    file_count: int
    violations: List[str]

    @property
    def passed(self) -> bool:
        return self.exists and self.has_mod_json and len(self.violations) == 0


def validate_pillar_directory(mod_dir: Path, pillar_name: str) -> PillarValidationResult:
    spec = PILLAR_SPECS.get(pillar_name)
    if not spec:
        return PillarValidationResult(
            pillar_name=pillar_name,
            exists=False,
            has_mod_json=False,
            file_count=0,
            violations=[f"Unknown pillar specification: {pillar_name}"],
        )

    if not mod_dir.is_dir():
        return PillarValidationResult(
            pillar_name=pillar_name,
            exists=False,
            has_mod_json=False,
            file_count=0,
            violations=[f"Directory does not exist: {mod_dir}"],
        )

    violations = []
    mod_json_path = mod_dir / "mod.json"
    has_mod_json = mod_json_path.exists()
    if not has_mod_json:
        violations.append(f"Missing mod.json in {mod_dir}")
    else:
        try:
            data = json.loads(mod_json_path.read_text(encoding="utf-8"))
            if "name" not in data or "version" not in data:
                violations.append("mod.json missing mandatory 'name' or 'version' fields")
        except Exception as e:
            violations.append(f"mod.json invalid JSON: {e}")

    dvdroot = mod_dir / "dvdroot_ps4"
    if not dvdroot.is_dir():
        violations.append(f"Missing dvdroot_ps4 directory in {mod_dir}")
        return PillarValidationResult(
            pillar_name=pillar_name,
            exists=True,
            has_mod_json=has_mod_json,
            file_count=0,
            violations=violations,
        )

    file_count = 0
    allowed = spec["allowed_subpaths"]
    forbidden = spec["forbidden_subpaths"]

    for child in dvdroot.iterdir():
        if child.is_dir():
            if child.name in forbidden:
                violations.append(f"Cross-contamination: forbidden folder dvdroot_ps4/{child.name} found in {pillar_name}")
            elif child.name not in allowed:
                violations.append(f"Unrecognized folder dvdroot_ps4/{child.name} in {pillar_name}")

    for file_path in dvdroot.rglob("*"):
        if file_path.is_file():
            file_count += 1
            rel_parts = file_path.relative_to(dvdroot).parts
            if rel_parts and rel_parts[0] in forbidden:
                violations.append(f"Forbidden asset {file_path.relative_to(mod_dir)} inside {pillar_name}")

    # Specific Havok cloth physics validation for armor editions
    if pillar_name == "Bloodborne Retro Armors and Weapons - Cloth Physics":
        test_armor = dvdroot / "parts" / "am_a_5210.partsbnd.dcx"
        if not test_armor.is_file():
            violations.append("Cloth Physics pillar missing reference armor am_a_5210.partsbnd.dcx")
        else:
            sz = test_armor.stat().st_size
            if sz < 250000:
                violations.append(f"Cloth Physics armor am_a_5210 has size {sz} B (< 250 KB); missing Havok cloth solvers (*_c.hkx)")

    elif pillar_name == "Bloodborne Retro Armors and Weapons - Flat Stiff":
        test_armor = dvdroot / "parts" / "am_a_5210.partsbnd.dcx"
        if not test_armor.is_file():
            violations.append("Flat Stiff pillar missing reference armor am_a_5210.partsbnd.dcx")
        else:
            sz = test_armor.stat().st_size
            if sz > 220000:
                violations.append(f"Flat Stiff armor am_a_5210 has size {sz} B (> 220 KB); contains unstripped Havok cloth solvers")

    return PillarValidationResult(
        pillar_name=pillar_name,
        exists=True,
        has_mod_json=has_mod_json,
        file_count=file_count,
        violations=violations,
    )


def validate_all_pillars(mods_root: Path) -> Dict[str, PillarValidationResult]:
    results = {}
    for pillar_name in PILLAR_SPECS.keys():
        pillar_dir = mods_root / pillar_name
        results[pillar_name] = validate_pillar_directory(pillar_dir, pillar_name)
    return results


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Modular Mod Architecture Validator.")
    parser.add_argument("--mods-dir", type=Path, default=Path("mods"), help="Path to mods directory")
    args = parser.parse_args()

    results = validate_all_pillars(args.mods_dir.resolve())
    failed = False
    for name, res in results.items():
        if res.passed:
            print(f"  [PASS] {name}: {res.file_count} assets, 0 violations.")
        else:
            print(f"  [FAIL] {name}: {res.violations}")
            failed = True

    if failed:
        sys.exit(1)
    print("All modular pillars passed structure validation.")
    sys.exit(0)

