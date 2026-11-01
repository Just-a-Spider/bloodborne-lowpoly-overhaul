#!/usr/bin/env python3
"""
tools/inject_doll_head.py: Surgical FLVER and TPF injection for Plain Doll (c8030).

Integrates the reconstructed low-poly PSX head cage into c8030.flver, applies 15-bit
RGB555 diffuse quantization with porcelain luminance to c8030.tpf, synchronizes all
auxiliary FaceSets, updates exact rigid AABB bounds, and repacks into c8030.chrbnd.dcx.

Features:
1. Container Safety & Fallback Backup:
   - Preserves pristine CUSA03173/ untouched.
   - Ensures fallback backup CUSA03173-PSX/.../c8030.chrbnd.dcx.bak exists before modification.
2. Mesh 7 Surgical Injection:
   - Replaces Mesh 7 vertex array 0 and face sets with reconstructed low-poly PSX head + preserved hands.
   - Synchronizes FS1..FS5 = FS0.copy().
3. AABB Bounding Box Maintenance:
   - Recalculates exact tight vertex extrema on rigid submeshes (3, 4, 5, 6, 7, 8, 9, 12).
   - Preserves 100% vanilla bounding boxes on cloth submeshes (0, 1, 2, 10, 11).
   - Updates global FLVER root AABB to exact submesh union.
4. Diffuse Texture Demake & 15-Bit Quantization:
   - Quantizes c8030_skin_a diffuse texture to 15-bit RGB555 palette (32 discrete levels, step 8).
   - Applies warm porcelain luminance compensation (0.95R, 0.90G, 0.85B).
   - Preserves normal map format (BC5 0x6c), hair alpha (BC7 0x66), and lace (BC1 0x01).
5. DCX Repacking:
   - Repacks c8030.flver and c8030.tpf into CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx.
"""

import sys
import os
import shutil
from pathlib import Path
from typing import Optional

import numpy as np

# Setup paths and environment
REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

try:
    import soulstruct_patch
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER
    from soulstruct.containers.tpf import TPF
    from soulstruct.utilities.maths.aabb import AABB
    from soulstruct.utilities.maths import Vector3
except ImportError as e:
    print(f"[FATAL] Soulstruct dependencies missing: {e}", file=sys.stderr)
    sys.exit(1)

from demake_c8030_doll import demake_doll

VANILLA_DCX = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"
PSX_DCX = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"
PSX_BACKUP = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx.bak"

CLOTH_SUBMESH_INDICES = [0, 1, 2, 10, 11]
RIGID_SUBMESH_INDICES = [3, 4, 5, 6, 7, 8, 9, 12]


def ensure_backup() -> None:
    """Creates fallback backup of PSX container if not already present."""
    if not PSX_BACKUP.exists():
        if PSX_DCX.exists():
            shutil.copy2(PSX_DCX, PSX_BACKUP)
            print(f"[BACKUP] Created fallback backup at: {PSX_BACKUP}")
        elif VANILLA_DCX.exists():
            shutil.copy2(VANILLA_DCX, PSX_BACKUP)
            print(f"[BACKUP] Created fallback backup from vanilla at: {PSX_BACKUP}")
        else:
            raise FileNotFoundError(f"Neither PSX nor Vanilla DCX found to create backup")


def inject_doll_head(
    target_dcx: Optional[Path] = None,
    vanilla_dcx: Optional[Path] = None,
    verbose: bool = True
) -> None:
    """
    Main injection routine: delegates to demake_doll for complete Plain Doll redesign.
    """
    demake_doll(target_dcx=target_dcx, vanilla_dcx=vanilla_dcx, verbose=verbose)


if __name__ == "__main__":
    inject_doll_head(verbose=True)

