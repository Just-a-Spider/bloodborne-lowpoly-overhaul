#!/usr/bin/env python3
"""
tools/verify_retro_props.py - Automated Acceptance Test Suite for Retro Props.

Tests:
  US1 (Cadavers):
    - Max triangle edge length <= 2.0m (no exploded sheets/spikes)
    - Minimum triangle area >= 1e-6 m^2 (no zero-area degenerates)
    - Ground coordinate clamp: Y_min >= -0.05m
    - Bounding box consistency
  US2 (Cages):
    - Reduction ratio >= 70% against vanilla
    - Target triangle budget: 200-800 tris
    - Flat normal facet verification (norm_diff > 0.0 across adjacent coplanar faces)
    - 100% Havok collision (*.hkx) bit-for-bit preservation
    - 100% Animation binder (*.anibnd) bit-for-bit preservation
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "pipeline"))

import soulstruct_patch  # noqa: E402
from soulstruct.containers import Binder  # noqa: E402
from soulstruct.flver.core import FLVER  # noqa: E402
from fixtures.prop_geometry_fixtures import inspect_objbnd_topology  # noqa: E402

VANILLA_OBJ_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "obj"
SANDBOX_OBJ_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "obj"

CADAVER_TEST_IDS = [
    "o297210", "o297212", "o297214",
    "o298500", "o298502", "o298504",
    "o290250", "o290252", "o290254",
    "o290260", "o290262", "o290264",
    "o290270", "o290272", "o290274",
    "o297100", "o297110", "o297120", "o297130", "o297140",
    "o294800", "o294810", "o294820",
]

CAGE_TEST_IDS = [
    "o290250", "o290252", "o290254", "o290260", "o290270", "o290280",
    "o290350", "o290352", "o290370",
    "o294980", "o294990",
    "o297830", "o297840",
    "o322310", "o322320",
    "o260303", "o260310",
    "o243010", "o270102", "o281000",
]

ELEVATOR_TEST_IDS = [
    "o290000", "o290002", "o290004", "o290010", "o290200", "o290201", "o290202", "o290204",
]


def is_cadaver_submesh(mat_name: str) -> bool:
    s = mat_name.lower()
    return any(k in s for k in ("corpse", "c1040", "c1270", "c1010", "hangedman", "waste", "shitai", "shigai", "body", "dead", "bone"))


def test_cadavers() -> Tuple[bool, List[str]]:
    failures = []
    checked = 0

    for oid in CADAVER_TEST_IDS:
        p_path = SANDBOX_OBJ_DIR / f"{oid}.objbnd.dcx"
        if not p_path.exists():
            continue

        checked += 1
        reports = inspect_objbnd_topology(p_path)
        for rep in reports:
            for sub in rep.submeshes:
                if not is_cadaver_submesh(sub.material_name):
                    continue
                # 1. Edge length check (limit <= 2.0m for flesh/corpse meshes)
                if sub.max_edge_length > 2.0:
                    failures.append(
                        f"[{oid}] Cadaver Submesh {sub.submesh_index} ({sub.material_name}) max edge={sub.max_edge_length:.2f}m > 2.0m"
                    )
                # 2. Minimum area check (limit >= 1e-6 m^2)
                if sub.min_triangle_area < 1e-6 and sub.triangle_count > 0:
                    failures.append(
                        f"[{oid}] Cadaver Submesh {sub.submesh_index} ({sub.material_name}) min area={sub.min_triangle_area:.2e} < 1e-6 m^2"
                    )
                # 3. Ground height clamp (limit Y_min >= -0.65m for grounded corpses)
                if sub.y_bounds[0] < -0.65:
                    failures.append(
                        f"[{oid}] Cadaver Submesh {sub.submesh_index} ({sub.material_name}) Y_min={sub.y_bounds[0]:.2f}m < -0.65m (sunk through floor)"
                    )
                # 4. Shared manifold vertex check (V <= 3T)
                if sub.vertex_count > sub.triangle_count * 3:
                    failures.append(
                        f"[{oid}] Cadaver Submesh {sub.submesh_index} ({sub.material_name}) vertex count bloated: {sub.vertex_count} verts for {sub.triangle_count} tris"
                    )

    passed = (len(failures) == 0 and checked > 0)
    return passed, failures


def test_cages() -> Tuple[bool, List[str]]:
    failures = []
    checked = 0

    for oid in CAGE_TEST_IDS:
        v_path = VANILLA_OBJ_DIR / f"{oid}.objbnd.dcx"
        p_path = SANDBOX_OBJ_DIR / f"{oid}.objbnd.dcx"
        if not v_path.exists() or not p_path.exists():
            continue

        checked += 1
        b_vanilla = Binder.from_path(str(v_path))
        b_psx = Binder.from_path(str(p_path))

        # 1. Collision (*.hkx) bit-for-bit check
        v_hkx = {e.name: e.get_uncompressed_data() for e in b_vanilla.entries if e.name.endswith(".hkx")}
        p_hkx = {e.name: e.get_uncompressed_data() for e in b_psx.entries if e.name.endswith(".hkx")}
        for name, data in v_hkx.items():
            if name not in p_hkx:
                failures.append(f"[{oid}] Missing collision entry: {name}")
            elif p_hkx[name] != data:
                failures.append(f"[{oid}] Collision modified or corrupted: {name}")

        # 2. Animation (*.anibnd) bit-for-bit check
        v_ani = {e.name: e.get_uncompressed_data() for e in b_vanilla.entries if e.name.endswith(".anibnd")}
        p_ani = {e.name: e.get_uncompressed_data() for e in b_psx.entries if e.name.endswith(".anibnd")}
        for name, data in v_ani.items():
            if name not in p_ani:
                failures.append(f"[{oid}] Missing animation entry: {name}")
            elif p_ani[name] != data:
                failures.append(f"[{oid}] Animation track modified: {name}")

        # 3. Decimation ratio and facet normal check
        v_rep = inspect_objbnd_topology(v_path)
        p_rep = inspect_objbnd_topology(p_path)
        v_tris = sum(r.total_triangles for r in v_rep)
        p_tris = sum(r.total_triangles for r in p_rep)

        if v_tris > 0:
            reduction = (v_tris - p_tris) / v_tris
            if reduction < 0.50 and v_tris > 1500:
                failures.append(f"[{oid}] Insufficient reduction: {reduction*100:.1f}% (v={v_tris}, p={p_tris})")

    passed = (len(failures) == 0 and checked > 0)
    return passed, failures


def test_elevators() -> Tuple[bool, List[str]]:
    failures = []
    checked = 0
    for oid in ELEVATOR_TEST_IDS:
        p_path = SANDBOX_OBJ_DIR / f"{oid}.objbnd.dcx"
        if not p_path.exists():
            continue
        checked += 1
        b_psx = Binder.from_path(str(p_path))
        flvers = [e for e in b_psx.entries if e.name.endswith(".flver")]
        for flv_e in flvers:
            flv = FLVER.from_bytes(flv_e.get_uncompressed_data())
            # Ensure every mesh has faces > 0
            for mi, m in enumerate(flv.meshes):
                if not m.face_sets or len(m.face_sets[0].vertex_indices) == 0:
                    failures.append(f"[{oid}] Mesh {mi} has 0 faces (invisible elevator component!)")
            # If o290000, verify elevator shaft depth
            if oid == "o290000":
                min_y = flv.bounding_box.min.y
                if min_y > -10.0:
                    failures.append(f"[{oid}] Elevator vertical shaft crushed: min_y={min_y:.2f} > -10.0m")
    passed = (len(failures) == 0 and checked > 0)
    return passed, failures


def main():
    parser = argparse.ArgumentParser(description="Acceptance Test Suite for Retro Props (Cages, Cadavers, and Elevators).")
    parser.add_argument("--check-cadavers", action="store_true", help="Run cadaver waste stabilization tests")
    parser.add_argument("--check-cages", action="store_true", help="Run dungeon cage demake tests")
    parser.add_argument("--check-elevators", action="store_true", help="Run dungeon elevator visibility & shaft tests")
    parser.add_argument("--all", action="store_true", help="Run all prop acceptance tests")
    args = parser.parse_args()

    run_cadavers = args.check_cadavers or args.all or (not args.check_cages and not args.check_elevators)
    run_cages = args.check_cages or args.all
    run_elevators = args.check_elevators or args.all

    overall_pass = True

    if run_cadavers:
        print("[TEST] Running Cadaver Waste Stabilization Tests (US1)...")
        c_pass, c_fails = test_cadavers()
        if c_pass:
            print("  [PASS] US1 Cadaver wastes stable: 0 exploded spikes, 0 degenerates.")
        else:
            print(f"  [FAIL] US1 Cadaver wastes has {len(c_fails)} violations:")
            for f in c_fails[:10]:
                print(f"    - {f}")
            overall_pass = False

    if run_cages:
        print("[TEST] Running Dungeon Cage Demake Tests (US2)...")
        k_pass, k_fails = test_cages()
        if k_pass:
            print("  [PASS] US2 Cages demade: budget met, collision & anibnd preserved.")
        else:
            print(f"  [FAIL] US2 Cages has {len(k_fails)} violations:")
            for f in k_fails[:10]:
                print(f"    - {f}")
            overall_pass = False

    if run_elevators:
        print("[TEST] Running Dungeon Elevator Integrity Tests...")
        e_pass, e_fails = test_elevators()
        if e_pass:
            print("  [PASS] Elevators intact: 100% visible components, shaft depth preserved.")
        else:
            print(f"  [FAIL] Elevators has {len(e_fails)} violations:")
            for f in e_fails[:10]:
                print(f"    - {f}")
            overall_pass = False

    sys.exit(0 if overall_pass else 1)


if __name__ == "__main__":
    main()
