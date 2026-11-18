#!/usr/bin/env python3
"""
Automated verification test for Lady Maria (set 9300) hat and garb.
Verifies both Cloth Physics edition and Flat Stiff edition:
- Cloth mode: ensures Havok solver files (_c.hkx, _c.clm2) and _Cloth.mtd are present,
  and simulation dummy bones are anchored to character roots (Head, Spine2).
- Stiff mode: ensures all cloth submeshes have valid default_bone_indices matching
  character roots (Head for hat feathers, Spine2/Neck for mantle/scarves) and zero
  unparented dummy bones.
"""

from pathlib import Path
from soulstruct.containers import Binder
from soulstruct.flver.core import FLVER

REPO_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_PARTS = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "parts"
CLOTH_PARTS = REPO_ROOT / "mods" / "Bloodborne Retro Armors and Weapons - Cloth Physics" / "dvdroot_ps4" / "parts"
STIFF_PARTS = REPO_ROOT / "mods" / "Bloodborne Retro Armors and Weapons - Flat Stiff" / "dvdroot_ps4" / "parts"

MARIA_FILES = [
    "hd_f_9300.partsbnd.dcx",
    "hd_m_9300.partsbnd.dcx",
    "bd_f_9300.partsbnd.dcx",
    "bd_m_9300.partsbnd.dcx",
]


def test_maria_cloth_physics_edition():
    print("Testing Lady Maria Cloth Physics files (in Cloth Mod & Sandbox)...")
    for base_dir, label in [(CLOTH_PARTS, "Cloth Mod"), (SANDBOX_PARTS, "Sandbox")]:
        for fname in MARIA_FILES:
            file_path = base_dir / fname
            assert file_path.exists(), f"[{label}] Missing {fname}"

            b = Binder.from_path(file_path)
            entries = [e.name for e in b.entries]

            # Verify Havok physics packages
            assert any(e.endswith("_c.hkx") for e in entries), f"[{label}] {fname} missing _c.hkx"
            assert any(e.endswith("_c.clm2") for e in entries), f"[{label}] {fname} missing _c.clm2"

            flv_e = next(e for e in b.entries if e.name.endswith(".flver"))
            flv = FLVER.from_bytes(flv_e.get_uncompressed_data())

            # Verify _Cloth.mtd is retained on cloth submeshes
            cloth_mtds = [
                m.material.mat_def_name for m in flv.meshes
                if "cloth" in (m.material.mat_def_name or "").lower() or "cloth" in (m.material.name or "").lower()
            ]
            assert len(cloth_mtds) > 0, f"[{label}] {fname} missing _Cloth.mtd submeshes"

            # Verify dummy bones are parented to skeleton
            if fname.startswith("hd_"):
                head_idx = next(i for i, bn in enumerate(flv.bones) if bn.name == "Head")
                for bn in flv.bones:
                    if "feather" in bn.name.lower():
                        assert bn.parent_bone_index == head_idx, (
                            f"[{label}] {fname} bone {bn.name} parent is {bn.parent_bone_index}, expected Head ({head_idx})"
                        )
            else:
                spine2_idx = next(i for i, bn in enumerate(flv.bones) if bn.name == "Spine2")
                for bn in flv.bones:
                    if "mantle" in bn.name.lower() or "scarf" in bn.name.lower():
                        assert bn.parent_bone_index == spine2_idx, (
                            f"[{label}] {fname} bone {bn.name} parent is {bn.parent_bone_index}, expected Spine2 ({spine2_idx})"
                        )

            print(f"  [{label}] {fname}: OK (HKX present, cloth MTDs={len(cloth_mtds)}, bones parented)")


def test_maria_flat_stiff_edition():
    print("Testing Lady Maria Flat Stiff files (in Stiff Mod)...")
    for fname in MARIA_FILES:
        file_path = STIFF_PARTS / fname
        assert file_path.exists(), f"[Stiff Mod] Missing {fname}"

        b = Binder.from_path(file_path)
        flv_e = next(e for e in b.entries if e.name.endswith(".flver"))
        flv = FLVER.from_bytes(flv_e.get_uncompressed_data())

        if fname.startswith("hd_"):
            head_idx = next(i for i, bn in enumerate(flv.bones) if bn.name == "Head")
            # Feathers submeshes must be assigned to Head bone
            assert flv.meshes[1].default_bone_index == head_idx, (
                f"[Stiff Mod] {fname} mesh 1 default bone is {flv.meshes[1].default_bone_index}, expected Head ({head_idx})"
            )
            assert flv.meshes[2].default_bone_index == head_idx, (
                f"[Stiff Mod] {fname} mesh 2 default bone is {flv.meshes[2].default_bone_index}, expected Head ({head_idx})"
            )
            for bn in flv.bones:
                if "feather" in bn.name.lower():
                    assert bn.parent_bone_index == head_idx, (
                        f"[Stiff Mod] {fname} bone {bn.name} parent is {bn.parent_bone_index}, expected {head_idx}"
                    )
        else:
            spine2_idx = next(i for i, bn in enumerate(flv.bones) if bn.name == "Spine2")
            neck_idx = next(i for i, bn in enumerate(flv.bones) if bn.name == "Neck")
            # Mantle submeshes must be assigned to Spine2
            for mi in [2, 3, 4, 5]:
                assert flv.meshes[mi].default_bone_index == spine2_idx, (
                    f"[Stiff Mod] {fname} mesh {mi} default bone is {flv.meshes[mi].default_bone_index}, expected {spine2_idx}"
                )
            # Scarf submeshes must be assigned to Neck
            for mi in [6, 7, 8]:
                assert flv.meshes[mi].default_bone_index == neck_idx, (
                    f"[Stiff Mod] {fname} mesh {mi} default bone is {flv.meshes[mi].default_bone_index}, expected {neck_idx}"
                )
            for bn in flv.bones:
                if "mantle" in bn.name.lower() or "scarf" in bn.name.lower():
                    assert bn.parent_bone_index == spine2_idx, (
                        f"[Stiff Mod] {fname} bone {bn.name} parent is {bn.parent_bone_index}, expected {spine2_idx}"
                    )

        print(f"  [Stiff Mod] {fname}: OK (Rigid submeshes and bones anchored to Head/Spine2/Neck)")


if __name__ == "__main__":
    test_maria_cloth_physics_edition()
    test_maria_flat_stiff_edition()
    print("All Lady Maria cloth & hat tests passed successfully!")
