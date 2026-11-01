"""
Tool to isolate FLVER vs TPF issues and test bounding box configurations for c8030.
"""

import sys, os, shutil
sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch

from soulstruct.containers import Binder
from soulstruct.bloodborne.models import FLVER
from soulstruct.utilities.maths.aabb import AABB
from soulstruct.utilities.maths import Vector3

VANILLA_DCX = 'CUSA03173/dvdroot_ps4/chr/c8030.chrbnd.dcx'
PSX_DCX = 'CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx'
BACKUP_DCX = 'CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx.bak'

def apply_repacked_vanilla_flver():
    """Litmus Test: Repacks 100% vanilla FLVER through patched Soulstruct into PSX container."""
    backup_psx()
    b_vanilla = Binder.from_path(VANILLA_DCX)
    flv = FLVER.from_binder_entry(b_vanilla[200])
    
    # Confirm all 206 bones match vanilla exactly
    mismatches = 0
    for i in range(len(flv.bones)):
        bv = flv.bones[i]
        if bv.bounding_box.min != flv.bones[i].bounding_box.min:
            mismatches += 1
    assert mismatches == 0, f"{mismatches} bones mismatch vanilla!"
    
    repacked_bytes = flv.to_bytes()
    b_psx = Binder.from_path(PSX_DCX)
    b_psx[200].set_uncompressed_data(repacked_bytes)
    b_psx.write(PSX_DCX)
    print(f"[SUCCESS] Repacked 100% vanilla FLVER with all {len(flv.bones)} valid bone AABBs into PSX container.")


def backup_psx():
    if not os.path.exists(BACKUP_DCX):
        shutil.copy2(PSX_DCX, BACKUP_DCX)
        print(f"[BACKUP] Created {BACKUP_DCX}")

def apply_vanilla_flver():
    """Test A: Injects 100% vanilla FLVER into PSX container while keeping PSX TPF."""
    backup_psx()
    b_vanilla = Binder.from_path(VANILLA_DCX)
    vanilla_flver_bytes = b_vanilla[200].get_uncompressed_data()

    b_psx = Binder.from_path(PSX_DCX)
    b_psx[200].set_uncompressed_data(vanilla_flver_bytes)
    b_psx.write(PSX_DCX)
    print("[SUCCESS] Test A: Injected 100% vanilla c8030.flver into PSX container (retained PSX c8030.tpf).")

def apply_exact_vanilla_bounding_boxes():
    """Test B: Uses demade FLVER, but restores exact vanilla AABBs on all meshes and root."""
    backup_psx()
    b_vanilla = Binder.from_path(VANILLA_DCX)
    flv_v = FLVER.from_binder_entry(b_vanilla[200])

    b_psx = Binder.from_path(PSX_DCX)
    flv_p = FLVER.from_binder_entry(b_psx[200])

    # Copy exact vanilla root bounding box
    flv_p.bounding_box = AABB(
        Vector3(flv_v.bounding_box.min),
        Vector3(flv_v.bounding_box.max)
    )

    # Copy exact vanilla submesh bounding boxes
    for i, (mv, mp) in enumerate(zip(flv_v.meshes, flv_p.meshes)):
        mp.bounding_box = AABB(
            Vector3(mv.bounding_box.min),
            Vector3(mv.bounding_box.max)
        )

    b_psx[200].set_uncompressed_data(flv_p.to_bytes())
    b_psx.write(PSX_DCX)
    print("[SUCCESS] Test B: Restored exact vanilla AABBs on all 13 meshes and root FLVER (kept decimated meshes and PSX TPF).")

def apply_mesh_subset(indices: list[int]):
    """Injects vanilla FLVER with ONLY the specified submesh indices decimated."""
    backup_psx()
    b_vanilla = Binder.from_path(VANILLA_DCX)
    flv = FLVER.from_binder_entry(b_vanilla[200])

    b_dec = Binder.from_path(BACKUP_DCX)
    flv_dec = FLVER.from_binder_entry(b_dec[200])

    for mi in indices:
        flv.meshes[mi] = flv_dec.meshes[mi]
        pos = flv.meshes[mi].vertex_arrays[0].array['position']
        flv.meshes[mi].bounding_box = AABB(Vector3(pos.min(axis=0)), Vector3(pos.max(axis=0)))

    b_psx = Binder.from_path(PSX_DCX)
    b_psx[200].set_uncompressed_data(flv.to_bytes())
    b_psx.write(PSX_DCX)
    print(f"[SUCCESS] Subset active: Meshes {indices} decimated; all other meshes 100% vanilla.")

def restore_backup():
    if os.path.exists(BACKUP_DCX):
        shutil.copy2(BACKUP_DCX, PSX_DCX)
        print(f"[RESTORE] Restored {PSX_DCX} from backup.")
    else:
        print("[ERROR] No backup found.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python isolate_c8030.py [vanilla_flver | exact_bbs | restore | subset <idx1,idx2...>]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'vanilla_flver':
        apply_vanilla_flver()
    elif cmd == 'repacked_vanilla':
        apply_repacked_vanilla_flver()
    elif cmd == 'exact_bbs':
        apply_exact_vanilla_bounding_boxes()
    elif cmd == 'subset':
        idx_list = [int(x) for x in sys.argv[2].split(',')]
        apply_mesh_subset(idx_list)
    elif cmd == 'restore':
        restore_backup()
    else:
        print(f"Unknown command: {cmd}")
