#!/usr/bin/env python3
"""
test_beast_fur_c1000.py - Experimental fur demake for c1000 (Wolf Beast).

Modes:
  1. strip:
     Completely empties all floating fur card submeshes (m02-m05, m07-m10).
     Tests maximum performance with 0% overdraw (solid retro body).
  2. retro-mane:
     Keeps only the main dorsal/neck silhouette fur (m02, m07), but strips
     the 3 Havok cloth fluttering layers (m03-m05, m08-m10). Keeps the ragged
     silhouette appeal while cutting 80% of fur overdraw and Havok cloth overhead.
  3. opaque-spikes:
     Keeps m02/m07, strips m03-m05/m08-m10, and converts m02/m07 from alpha-tested
     (C[ARSN]_e.mtd) to solid opaque (C[ARSN].mtd). Gives solid chunky retro spikes
     with 100% hardware Early-Z culling.
  4. restore:
     Restores the pre-test snapshot.

Usage:
  uv run python tools/test_beast_fur_c1000.py --mode strip
  uv run python tools/test_beast_fur_c1000.py --mode retro-mane
  uv run python tools/test_beast_fur_c1000.py --mode opaque-spikes
  uv run python tools/test_beast_fur_c1000.py --restore
"""

import argparse
import shutil
import sys
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import soulstruct_patch
from soulstruct.bloodborne.models import FLVER
from soulstruct.containers import Binder

C1000_PATH = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr" / "c1000.chrbnd.dcx"
SNAP_PATH = C1000_PATH.with_suffix(C1000_PATH.suffix + ".snap_fur_test")


def process_c1000(mode: str):
    if not C1000_PATH.exists():
        print(f"[ERROR] {C1000_PATH} not found.")
        return

    # Snapshot before first modification
    if not SNAP_PATH.exists():
        shutil.copy2(C1000_PATH, SNAP_PATH)
        print(f"[SNAPSHOT] Created {SNAP_PATH.name}")

    binder = Binder.from_path(SNAP_PATH)
    flver_entry = None
    for entry in binder.entries:
        if entry.name.endswith(".flver"):
            flver_entry = entry
            break

    if not flver_entry:
        print("[ERROR] No .flver found in c1000.chrbnd.dcx")
        return

    flv = FLVER.from_bytes(flver_entry.get_uncompressed_data())

    print(f"\n=== Processing c1000 (Mode: {mode.upper()}) ===")
    for i, m in enumerate(flv.meshes):
        name = m.material.name.lower()
        mtd_stem = m.material.mat_def_stem.split("\\")[-1]
        tris_before = len(m.face_sets[0].vertex_indices) // 3 if m.face_sets else 0

        if "fur" in name:
            is_cloth = "cloth" in name

            if mode == "strip":
                # Empty all fur submeshes
                for fs in m.face_sets:
                    fs.vertex_indices = np.zeros((0, 3), dtype=np.uint32)
                print(f"  m{i:02d} ({m.material.name}): {tris_before} -> 0 tris [STRIPPED]")

            elif mode == "retro-mane":
                if is_cloth:
                    # Strip secondary cloth flapping layers
                    for fs in m.face_sets:
                        fs.vertex_indices = np.zeros((0, 3), dtype=np.uint32)
                    print(f"  m{i:02d} ({m.material.name}): {tris_before} -> 0 tris [CLOTH FUR STRIPPED]")
                else:
                    # Keep primary silhouette mane
                    print(f"  m{i:02d} ({m.material.name}): {tris_before} tris [KEPT PRIMARY MANE]")

            elif mode == "opaque-spikes":
                if is_cloth:
                    for fs in m.face_sets:
                        fs.vertex_indices = np.zeros((0, 3), dtype=np.uint32)
                    print(f"  m{i:02d} ({m.material.name}): {tris_before} -> 0 tris [CLOTH FUR STRIPPED]")
                else:
                    # Convert to solid opaque material (no alpha discard)
                    m.material.mat_def_name = m.material.mat_def_name.replace("_e.mtd", ".mtd")
                    print(f"  m{i:02d} ({m.material.name}): {tris_before} tris [OPAQUE SOLID SPIKES]")

    flver_entry.set_uncompressed_data(flv.to_bytes())
    C1000_PATH.write_bytes(binder.to_bytes())
    print(f"\n[DEPLOYED] {C1000_PATH.name} updated successfully in CUSA03173-PSX.")


def restore_c1000():
    if not SNAP_PATH.exists():
        print(f"No snapshot found at {SNAP_PATH.name}")
        return
    shutil.copy2(SNAP_PATH, C1000_PATH)
    SNAP_PATH.unlink()
    print(f"[RESTORED] Reverted {C1000_PATH.name} to pre-test state.")


def main():
    parser = argparse.ArgumentParser(description="Pilot fur demake test on c1000")
    parser.add_argument("--mode", choices=["strip", "retro-mane", "opaque-spikes"], default="retro-mane")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    if args.restore:
        restore_c1000()
    else:
        process_c1000(args.mode)


if __name__ == "__main__":
    main()

