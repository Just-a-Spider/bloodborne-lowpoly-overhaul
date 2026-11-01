#!/usr/bin/env python3
"""
demake_c8030_ultralow.py — Ultra-Low-Poly PSX push on Plain Doll (c8030).

Targets the absolute practical floor given Havok cloth constraints:
  - Cloth submeshes (0,1,2,10,11): 100% preserved (cannot touch, Test 11)
  - Head skin (Mesh 7, HEAD_SKIN component): 300 tris (down from 700)
  - Rigid submeshes: ~10-15% of original (down from ~45%)

Usage:
    uv run python tools/demake_c8030_ultralow.py            # dry-run to /tmp
    uv run python tools/demake_c8030_ultralow.py --deploy   # write to CUSA03173-PSX
    uv run python tools/demake_c8030_ultralow.py --restore  # restore from .snap_pre_ultralow

Fallback:
    The pre-ultralow state is snapshotted at:
    CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx.snap_pre_ultralow
"""

import sys
import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import numpy as np
from scipy.spatial import cKDTree

try:
    import soulstruct_patch
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER
    from soulstruct.containers.tpf import TPF
    from soulstruct.utilities.maths.aabb import AABB
    from soulstruct.utilities.maths import Vector3
except ImportError as e:
    print(f"[FATAL] Soulstruct import error: {e}", file=sys.stderr)
    sys.exit(1)

from mesh_decimator import decimate_flver, calc_triangle_aspect

VANILLA_DCX = REPO_ROOT / "CUSA03173"      / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"
PSX_DCX     = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"
SNAP        = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx.snap_pre_ultralow"
STAGE       = Path("/tmp/c8030_ultralow.chrbnd.dcx")

# ---------------------------------------------------------------------------
# Moderate-low targets  (v2 — after ultralow caused shared=False & SET_PREDICATION drops)
# ---------------------------------------------------------------------------
# Root causes of v1 failure:
#   - shared=False: target so low that UV seam verts > tris (unrolling artifact)
#   - SET_PREDICATION culling: Bonnet AABB collapsed too small, GPU dropped draw calls
#   - Floor rule: each mesh needs ~20-25% of original to keep welded manifold topology
#
# Mesh index → target triangle count (rigid submeshes only)
# Reference baseline from normal demake: {3:220, 4:850, 5:1100, 6:100, 8:200, 9:1000, 12:120}
ULTRALOW_SUBMESH_TARGETS = {
    # Mesh 3 (Collar) kept at vanilla 921 tris.
    # Its lace UV topology creates 27 slivers post-QEM that invert the shared=True invariant
    # regardless of target count. Not worth the crash risk for a small collar.
    3: 921,   # Collar — preserve vanilla (lace UV incompatible with extreme decimation)
    4: 500,   # Bonnet      11008 orig -> 500  (~4.5%)
    5: 800,   # Dress       14444 orig -> 800  (~5.5%) — 600 produced unrolled mesh
    6:  80,   # Cuffs         350 orig -> 80   (~23%)
    8: 120,   # HairBase     1394 orig -> 120  (~9%)
    9: 500,   # Legs/Boots  15002 orig -> 500  (~3%)
    12: 80,   # Ribbon        950 orig -> 80   (~8%)
}
# Submesh indices to preserve 100% intact (beyond cloth)
PRESERVE_INDICES = {3}  # Collar: lace UV topology incompatible with extreme decimation
ULTRALOW_HEAD_TRIS  = 650   # HEAD_SKIN: was 400; raised to give landmark zone more budget after zone fix (Test 45)
ULTRALOW_RATIO      = 0.15  # fallback ratio for any rigid submesh not in dict


def audit_mesh(flv, label: str) -> None:
    """Print per-submesh triangle and vertex counts for inspection."""
    print(f"\n--- {label} ---")
    total_tris = 0
    total_verts = 0
    for mi, m in enumerate(flv.meshes):
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue
        faces = m.face_sets[0].vertex_indices.reshape(-1, 3)
        pos   = m.vertex_arrays[0].array["position"]
        arr   = m.vertex_arrays[0].array
        bw    = arr["bone_weights"] if "bone_weights" in arr.dtype.names else None
        mat   = m.material.name if m.material else "?"
        ntris = len(faces)
        nverts = len(pos)
        total_tris  += ntris
        total_verts += nverts

        bad_w = 0
        if bw is not None:
            byte_sums = np.sum(np.round(bw * 255.0).astype(int), axis=1)
            bad_w = int(np.sum(byte_sums != 255))

        _, asp, _, _, _ = calc_triangle_aspect(pos, faces)
        slivers = int(np.sum(asp > 25.0))
        shared  = nverts < ntris

        print(
            f"  Mesh {mi:2d} ({mat:22s}): {ntris:5d} tris  {nverts:5d} verts"
            f"  shared={shared!s:5s}  slivers={slivers:3d}  bad_weights={bad_w}"
        )
    print(f"  TOTAL: {total_tris} tris, {total_verts} verts")


def restore_snapshot() -> None:
    if not SNAP.exists():
        print(f"[ERROR] Snapshot not found: {SNAP}", file=sys.stderr)
        sys.exit(1)
    shutil.copy2(SNAP, PSX_DCX)
    print(f"[RESTORE] Reverted CUSA03173-PSX doll to snapshot from {SNAP}")

def run_ultralow(deploy: bool, verbose: bool = True) -> None:
    print(f"=== c8030 Ultra-Low-Poly Demake (head={ULTRALOW_HEAD_TRIS} tris, ratio={ULTRALOW_RATIO}) ===")
    print(f"  Source  : {VANILLA_DCX}")
    print(f"  Staging : {STAGE}")
    if deploy:
        print(f"  Deploy  : {PSX_DCX}")

    # 1. Ensure pre-ultralow snapshot exists before touching PSX_DCX
    if PSX_DCX.exists() and not SNAP.exists():
        shutil.copy2(PSX_DCX, SNAP)
        print(f"  [SNAPSHOT] Saved pre-ultralow state to {SNAP}")

    # 2. Load vanilla FLVER geometry baseline (never touch CUSA03173)
    b = Binder.from_path(VANILLA_DCX)
    flv_entry = next(e for e in b.entries if e.name.endswith(".flver"))
    flv = FLVER.from_bytes(flv_entry.get_uncompressed_data())

    # 3. Preserve demade PSX textures (c8030.tpf) from SNAP or PSX_DCX so we don't revert to vanilla 4K!
    tex_source_dcx = SNAP if SNAP.exists() else (PSX_DCX if PSX_DCX.exists() else None)
    if tex_source_dcx is not None:
        b_psx = Binder.from_path(tex_source_dcx)
        psx_tpfs = {e.name: e.get_uncompressed_data() for e in b_psx.entries if e.name.endswith(".tpf")}
        for entry in b.entries:
            if entry.name in psx_tpfs:
                entry.set_uncompressed_data(psx_tpfs[entry.name])
                print(f"  [TEXTURE] Preserved demade PSX texture archive: {entry.name}")

    # Capture vanilla shared flags before decimation
    vanilla_shared: dict[int, bool] = {}
    for mi, m in enumerate(flv.meshes):
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue
        f = m.face_sets[0].vertex_indices.reshape(-1, 3)
        p = m.vertex_arrays[0].array["position"]
        vanilla_shared[mi] = len(p) < len(f)

    audit_mesh(flv, "BEFORE (vanilla)")

    orig_t, new_t = decimate_flver(
        flv,
        target_ratio=ULTRALOW_RATIO,
        flat_normals=False,
        disable_cloth=False,
        preserve_border=True,
        head_target_tris=ULTRALOW_HEAD_TRIS,
        submesh_targets=ULTRALOW_SUBMESH_TARGETS,
        filename="c8030",
    )

    audit_mesh(flv, f"AFTER (ultralow)  {orig_t} -> {new_t} tris ({new_t/max(1,orig_t)*100:.1f}%)")

    # Safety gates
    cloth_indices = {0, 1, 2, 10, 11}
    for mi, m in enumerate(flv.meshes):
        if mi in cloth_indices or not m.face_sets or len(m.vertex_arrays) == 0:
            continue
        faces = m.face_sets[0].vertex_indices.reshape(-1, 3)
        pos   = m.vertex_arrays[0].array["position"]
        ntris = len(faces)
        nverts = len(pos)
        if ntris == 0:
            print(f"[ABORT] Mesh {mi} collapsed to 0 tris — not writing output.", file=sys.stderr)
            sys.exit(1)
        was_shared = vanilla_shared.get(mi, True)
        if was_shared and nverts > ntris:
            print(
                f"[ABORT] Mesh {mi} was shared=True in vanilla but is now unrolled "
                f"({nverts} verts > {ntris} tris). Raise target for this submesh.",
                file=sys.stderr,
            )
            sys.exit(1)

    flv_entry.set_uncompressed_data(flv.to_bytes())
    b.write(STAGE)
    print(f"\n[STAGED] Written to {STAGE}  ({STAGE.stat().st_size / 1024:.1f} KB)")

    if deploy:
        shutil.copy2(STAGE, PSX_DCX)
        bak = PSX_DCX.with_suffix(PSX_DCX.suffix + ".bak")
        if bak.exists():
            bak.unlink()
        print(f"[DEPLOYED] {PSX_DCX}")
        print(f"[FALLBACK] To restore: uv run python tools/demake_c8030_ultralow.py --restore")
    else:
        print(f"\nDry-run complete. Add --deploy to overwrite CUSA03173-PSX.")
if __name__ == "__main__":
    args = sys.argv[1:]
    if "--restore" in args:
        restore_snapshot()
    else:
        deploy = "--deploy" in args
        run_ultralow(deploy=deploy)
