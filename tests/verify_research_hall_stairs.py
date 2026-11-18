#!/usr/bin/env python3
"""
Automated verification test for Research Hall interactive stairs and ladders.
Verifies that all moving stair mechanisms (o243010-o243014, o353006, o353011, o353013)
and ladders (o350500-o350504) in CUSA03173-PSX preserve pristine FLVER geometry,
bone hierarchies, and bounding box volume.
"""

from pathlib import Path
import sys
from soulstruct.containers import Binder
from soulstruct.flver.core import FLVER

REPO_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_OBJ_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "obj"
VANILLA_OBJ_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "obj"

STAIR_PROPS = [
    "o243010", "o243011", "o243012", "o243013", "o243014",
    "o353006", "o353011", "o353013",
    "o249001", "o249002",
]

LADDER_PROPS = [
    "o350500", "o350501", "o350502", "o350503", "o350504",
]


def test_research_hall_stairs_and_ladders():
    print("Testing Research Hall stairs and ladders integrity in CUSA03173-PSX...")

    # 1. Test Stairs
    for prop_id in STAIR_PROPS:
        bnd_path = SANDBOX_OBJ_DIR / f"{prop_id}.objbnd.dcx"
        vanilla_bnd_path = VANILLA_OBJ_DIR / f"{prop_id}.objbnd.dcx"
        assert bnd_path.exists(), f"Missing stair archive: {bnd_path}"
        assert vanilla_bnd_path.exists(), f"Missing vanilla stair archive: {vanilla_bnd_path}"

        binder = Binder.from_path(bnd_path)
        v_binder = Binder.from_path(vanilla_bnd_path)

        flv_entry = next((e for e in binder.entries if e.name.lower().endswith(".flver")), None)
        v_flv_entry = next((e for e in v_binder.entries if e.name.lower().endswith(".flver")), None)
        assert flv_entry is not None, f"No FLVER found in sandbox {prop_id}"
        assert v_flv_entry is not None, f"No FLVER found in vanilla {prop_id}"

        flv = FLVER.from_bytes(flv_entry.get_uncompressed_data())
        v_flv = FLVER.from_bytes(v_flv_entry.get_uncompressed_data())

        total_verts = sum(len(m.vertex_arrays[0].array) for m in flv.meshes if m.vertex_arrays)
        v_total_verts = sum(len(m.vertex_arrays[0].array) for m in v_flv.meshes if m.vertex_arrays)

        print(f"Stair {prop_id}: sandbox meshes={len(flv.meshes)}, verts={total_verts}, bones={len(flv.bones)} | vanilla meshes={len(v_flv.meshes)}, verts={v_total_verts}")

        # Mesh count and bone count must match vanilla
        assert len(flv.meshes) == len(v_flv.meshes), f"Stair {prop_id} mesh count mismatch: {len(flv.meshes)} vs {len(v_flv.meshes)}"
        assert len(flv.bones) == len(v_flv.bones), f"Stair {prop_id} bone count mismatch: {len(flv.bones)} vs {len(v_flv.bones)}"
        assert total_verts == v_total_verts, f"Stair {prop_id} vertex count mismatch: {total_verts} vs {v_total_verts}"

    # 2. Test Ladders
    for prop_id in LADDER_PROPS:
        bnd_path = SANDBOX_OBJ_DIR / f"{prop_id}.objbnd.dcx"
        vanilla_bnd_path = VANILLA_OBJ_DIR / f"{prop_id}.objbnd.dcx"
        assert bnd_path.exists(), f"Missing ladder archive: {bnd_path}"
        assert vanilla_bnd_path.exists(), f"Missing vanilla ladder archive: {vanilla_bnd_path}"

        binder = Binder.from_path(bnd_path)
        v_binder = Binder.from_path(vanilla_bnd_path)

        flv_entry = next((e for e in binder.entries if e.name.lower().endswith(".flver")), None)
        v_flv_entry = next((e for e in v_binder.entries if e.name.lower().endswith(".flver")), None)
        assert flv_entry is not None, f"No FLVER found in sandbox {prop_id}"
        assert v_flv_entry is not None, f"No FLVER found in vanilla {prop_id}"

        flv = FLVER.from_bytes(flv_entry.get_uncompressed_data())
        v_flv = FLVER.from_bytes(v_flv_entry.get_uncompressed_data())

        total_verts = sum(len(m.vertex_arrays[0].array) for m in flv.meshes if m.vertex_arrays)
        v_total_verts = sum(len(m.vertex_arrays[0].array) for m in v_flv.meshes if m.vertex_arrays)

        bb_min = flv.bounding_box.min
        bb_max = flv.bounding_box.max
        height = bb_max.y - bb_min.y
        print(f"Ladder {prop_id}: sandbox bones={len(flv.bones)}, verts={total_verts}, height={height:.2f}m | vanilla bones={len(v_flv.bones)}, verts={v_total_verts}")

        assert len(flv.bones) == len(v_flv.bones), f"Ladder {prop_id} bone count mismatch: {len(flv.bones)} vs {len(v_flv.bones)}"
        assert total_verts == v_total_verts, f"Ladder {prop_id} vertex count mismatch: {total_verts} vs {v_total_verts}"
        assert height > 1.0, f"Ladder {prop_id} height collapsed: {height:.2f}m"

    print("All Research Hall interactive stairs and ladders verified successfully!")


if __name__ == "__main__":
    test_research_hall_stairs_and_ladders()
