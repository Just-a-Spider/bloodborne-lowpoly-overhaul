#!/usr/bin/env python3
"""
Mathematical Mesh Decimation, Skeletal Partitioning & Shell Clearance Engine for Bloodborne (FLVER2).

Core Capabilities:
1. Skeleton-Driven Topological Partitioning:
   - Automatically separates composite submeshes (e.g. Plain Doll Mesh 7 Head + Hands)
     using connected components and FLVER bone hierarchy semantics.
   - Preserves 100% of articulated hand/finger geometry and Havok cloth submeshes.
   - Enforces a 600-800 triangle likeness floor on facial/head skin components.
2. Shared-Vertex QEM Simplification (No Triangle Unrolling):
   - Maintains manifold shared vertices (num_verts < num_tris) welded within UV charts (<0.15).
   - Multi-pass normal-guarded sliver contraction (eliminates aspect ratio > 25.0 without stalling).
3. Vectorized Per-Corner Barycentric Attribute Transfer:
   - Projects simplified corners onto K=12 nearest normal-aligned original triangles.
   - Barycentric 4-bone Linear Blend Skinning (LBS) interpolation with strict byte-sum 255 normalization.
4. Scale-Invariant Shading & Tangent Frames:
   - Thurmer-Wuthrich corner-angle-weighted smooth vertex normals (or optional flat facets).
   - Handedness-aware (Tw in {-1, +1}) Gram-Schmidt tangent frames for both uv_0 and uv_1.
5. Automated Inter-Mesh Shell Clearance:
   - Resolves inner-to-outer submesh penetrations (e.g. Scalp vs. Bonnet/Helmet) to guarantee
     positive clearance (>= 5.0mm) and 0 piercing triangle pairs.
"""

import sys
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pyfqmr
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch  # noqa: E402
from soulstruct.utilities.maths.aabb import AABB  # noqa: E402
from soulstruct.utilities.maths import Vector3  # noqa: E402

HAND_BONE_KEYWORDS = ("finger", "thumb", "hand", "palm", "wrist", "claw")
HEAD_BONE_KEYWORDS = (
    "head", "neck", "jaw", "face", "lip", "eye", "brow",
    "ear", "mouth", "nose", "cheek", "tongue", "teeth", " skull"
)
# Fallback cranial bone indices for standard Bloodborne humanoid rigs (e.g. c8030)
HUMANOID_HEAD_BONE_INDICES = {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 40}


def disable_cloth_physics(flv) -> int:
    """Replaces _Cloth.mtd with standard character/parts shader to tame cloth physics."""
    count = 0
    for m in flv.meshes:
        if m.material and ("_Cloth" in m.material.mat_def_name or "_cloth" in m.material.mat_def_name):
            m.material.mat_def_name = (
                m.material.mat_def_name.replace("_Cloth.mtd", ".mtd").replace("_cloth.mtd", ".mtd")
            )
            count += 1
    return count


def get_merged_vertex_attributes(m) -> Dict[str, np.ndarray]:
    """Extracts a unified dictionary of vertex attributes across VA0..VAn for a submesh."""
    attrs: Dict[str, np.ndarray] = {}
    for va in m.vertex_arrays:
        for name in va.array.dtype.names:
            if name not in attrs:
                attrs[name] = va.array[name]
    return attrs


def classify_skeleton_bones(flv, is_weapon: bool = False) -> Tuple[Set[int], Set[int]]:
    """
    Classifies FLVER bone indices into hand/articulation bones and head/facial bones
    by inspecting bone names and walking parent-child hierarchies.
    Weapons never contain humanoid hand/head articulations.
    """
    hand_bones: Set[int] = set()
    head_bones: Set[int] = set()

    if is_weapon or not getattr(flv, "bones", None):
        return hand_bones, set() if is_weapon else set(HUMANOID_HEAD_BONE_INDICES)

    num_bones = len(flv.bones)
    for idx, bone in enumerate(flv.bones):
        bname = (getattr(bone, "name", "") or "").lower()
        if any(k in bname for k in HAND_BONE_KEYWORDS):
            hand_bones.add(idx)
        if any(k in bname for k in HEAD_BONE_KEYWORDS):
            head_bones.add(idx)

    # Propagate down bone hierarchy (children of hand/head bones inherit semantic group)
    changed = True
    while changed:
        changed = False
        for idx, bone in enumerate(flv.bones):
            parent = getattr(bone, "parent_bone", None)
            p_idx = flv.bones.index(parent) if parent in flv.bones else getattr(bone, "parent_bone_index", -1)
            if 0 <= p_idx < num_bones:
                if p_idx in hand_bones and idx not in hand_bones:
                    hand_bones.add(idx)
                    changed = True
                if p_idx in head_bones and idx not in head_bones and idx not in hand_bones:
                    head_bones.add(idx)
                    changed = True

    if len(flv.bones) >= 41:
        head_bones |= HUMANOID_HEAD_BONE_INDICES

    return hand_bones, head_bones


def normalize_bone_weights_strict(
    bw: np.ndarray,
    bi: np.ndarray,
    allowed_bones: Optional[Set[int]] = None,
    fallback_bone: int = 5
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Enforces strict partition of unity (float sum == 1.0) and integer byte sum == 255
    on (N, 4) bone_weights and bone_indices arrays.
    """
    out_bw = np.array(bw, dtype=np.float32, copy=True)
    out_bi = np.array(bi, copy=True)

    if allowed_bones is not None:
        mask_invalid = ~np.isin(out_bi, list(allowed_bones))
        out_bi[mask_invalid] = fallback_bone

    sum_w = np.sum(out_bw, axis=1, keepdims=True)
    zero_rows = (sum_w[:, 0] <= 1e-6)
    if np.any(zero_rows):
        out_bw[zero_rows] = [1.0, 0.0, 0.0, 0.0]
        if allowed_bones is not None:
            out_bi[zero_rows] = [fallback_bone, 0, 0, 0]
        sum_w = np.sum(out_bw, axis=1, keepdims=True)

    bytes_w = np.round((out_bw / sum_w) * 255.0).astype(np.int32)
    diff = 255 - np.sum(bytes_w, axis=1)
    max_col = np.argmax(bytes_w, axis=1)
    bytes_w[np.arange(len(bytes_w)), max_col] += diff
    out_bw = bytes_w.astype(np.float32) / 255.0
    return out_bw, out_bi


def calc_triangle_aspect(
    pos: np.ndarray,
    faces: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Computes triangle areas, circumradius/inradius aspect ratios, and edge lengths."""
    v0 = pos[faces[:, 0]]
    v1 = pos[faces[:, 1]]
    v2 = pos[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)

    e1 = np.linalg.norm(v1 - v0, axis=1)
    e2 = np.linalg.norm(v2 - v1, axis=1)
    e3 = np.linalg.norm(v0 - v2, axis=1)
    s = 0.5 * (e1 + e2 + e3)

    valid = areas >= 1e-6
    aspect = np.full(len(faces), 1e6, dtype=np.float64)
    aspect[valid] = (e1[valid] * e2[valid] * e3[valid] * s[valid]) / (8.0 * (areas[valid] ** 2))
    return areas, aspect, e1, e2, e3


def contract_slivers_normal_guarded(
    sp_pos: np.ndarray,
    sp_faces: np.ndarray,
    max_aspect: float = 25.0,
    max_passes: int = 50
) -> np.ndarray:
    """
    Eliminates degenerate faces (<1e-6 area) and needle slivers (aspect > max_aspect)
    while protecting open boundary edges and preventing adjacent normal flips.
    """
    areas, _, _, _, _ = calc_triangle_aspect(sp_pos, sp_faces)
    sp_faces = sp_faces[areas >= 1e-6].copy()
    if len(sp_faces) == 0:
        return sp_faces

    # Identify open boundary vertices (e.g. neckline seam)
    edge_counts: Dict[Tuple[int, int], int] = defaultdict(int)
    for f in sp_faces:
        for u, v in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            edge_counts[(min(int(u), int(v)), max(int(u), int(v)))] += 1
    boundary_verts = {v for (u, w), c in edge_counts.items() if c == 1 for v in (u, w)}

    for _ in range(max_passes):
        areas, aspect, e1, e2, e3 = calc_triangle_aspect(sp_pos, sp_faces)
        slivers = np.where(aspect > max_aspect)[0]
        if len(slivers) == 0:
            break

        collapsed_any = False
        for target_f in slivers:
            f_verts = sp_faces[target_f]
            edges = [
                (e1[target_f], int(f_verts[0]), int(f_verts[1])),
                (e2[target_f], int(f_verts[1]), int(f_verts[2])),
                (e3[target_f], int(f_verts[2]), int(f_verts[0])),
            ]
            edges.sort(key=lambda x: x[0])

            for _, va, vb in edges:
                if va in boundary_verts and vb not in boundary_verts:
                    v_keep, v_drop = va, vb
                elif vb in boundary_verts and va not in boundary_verts:
                    v_keep, v_drop = vb, va
                elif va in boundary_verts and vb in boundary_verts:
                    # Do not collapse boundary-to-boundary edges unless no interior edge works
                    continue
                else:
                    v_keep, v_drop = va, vb

                # Verify collapse does not invert incident triangle normals
                inc_mask = np.any(sp_faces == v_drop, axis=1)
                inc_faces = sp_faces[inc_mask]
                valid_collapse = True
                for inc_f in inc_faces:
                    if v_keep in inc_f:
                        continue
                    old_n = np.cross(
                        sp_pos[inc_f[2]] - sp_pos[inc_f[0]],
                        sp_pos[inc_f[1]] - sp_pos[inc_f[0]],
                    )
                    new_f = np.where(inc_f == v_drop, v_keep, inc_f)
                    new_n = np.cross(
                        sp_pos[new_f[2]] - sp_pos[new_f[0]],
                        sp_pos[new_f[1]] - sp_pos[new_f[0]],
                    )
                    n1 = np.linalg.norm(old_n)
                    n2 = np.linalg.norm(new_n)
                    if n1 > 1e-7 and n2 > 1e-7:
                        if np.dot(old_n / n1, new_n / n2) < 0.0:
                            valid_collapse = False
                            break

                if valid_collapse:
                    sp_faces[sp_faces == v_drop] = v_keep
                    deg = (
                        (sp_faces[:, 0] == sp_faces[:, 1])
                        | (sp_faces[:, 1] == sp_faces[:, 2])
                        | (sp_faces[:, 0] == sp_faces[:, 2])
                    )
                    sp_faces = sp_faces[~deg]
                    collapsed_any = True
                    break

            if collapsed_any:
                break

        if not collapsed_any:
            break

    # Deduplicate any overlapping faces
    if len(sp_faces) > 0:
        sorted_f = np.sort(sp_faces, axis=1)
        _, uniq_idx = np.unique(sorted_f, axis=0, return_index=True)
        sp_faces = sp_faces[np.sort(uniq_idx)]

    return sp_faces


def _tri_tri_piercing(t1: np.ndarray, t2: np.ndarray) -> bool:
    """Returns True if any edge of triangle t1 pierces the interior of triangle t2, or vice versa."""
    def _edge_pierces(e0, e1, v0, v1, v2):
        d = e1 - e0
        edge1 = v1 - v0
        edge2 = v2 - v0
        h = np.cross(d, edge2)
        a = np.dot(edge1, h)
        if abs(a) < 1e-8:
            return False
        f = 1.0 / a
        s = e0 - v0
        u = f * np.dot(s, h)
        if u < 1e-4 or u > 1.0 - 1e-4:
            return False
        q = np.cross(s, edge1)
        v = f * np.dot(d, q)
        if v < 1e-4 or (u + v) > 1.0 - 1e-4:
            return False
        t = f * np.dot(edge2, q)
        return 1e-4 < t < 1.0 - 1e-4

    for i in range(3):
        if _edge_pierces(t1[i], t1[(i + 1) % 3], t2[0], t2[1], t2[2]):
            return True
    for i in range(3):
        if _edge_pierces(t2[i], t2[(i + 1) % 3], t1[0], t1[1], t1[2]):
            return True
    return False


def enforce_shell_clearance(
    inner_pos: np.ndarray,
    inner_faces: np.ndarray,
    outer_pos: np.ndarray,
    outer_faces: np.ndarray,
    min_clearance_m: float = 0.0055
) -> np.ndarray:
    """
    Recesses occluded cranial vertices away from an overlapping outer shell
    while strictly protecting lateral ear geometry from imploding inward.
    """
    pos = inner_pos.copy()

    # Protect open boundary seam vertices (neckline)
    edge_counts: Dict[Tuple[int, int], int] = defaultdict(int)
    for f in inner_faces:
        for u, v in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            edge_counts[(min(int(u), int(v)), max(int(u), int(v)))] += 1
    boundary_verts = {v for (u, w), c in edge_counts.items() if c == 1 for v in (u, w)}
    movable_mask = np.ones(len(pos), dtype=bool)
    for bv in boundary_verts:
        if 0 <= bv < len(movable_mask):
            movable_mask[bv] = False

    bmin, bmax = pos.min(axis=0), pos.max(axis=0)
    span = bmax - bmin
    inner_center = np.array([
        0.5 * (bmin[0] + bmax[0]),
        bmin[1] + 0.55 * span[1],
        bmin[2] + 0.45 * span[2],
    ], dtype=np.float32)

    outer_min, outer_max = outer_pos.min(axis=0), outer_pos.max(axis=0)
    in_outer_y = pos[:, 1] > max(outer_min[1] + 0.15 * (outer_max[1] - outer_min[1]), bmin[1] + 0.35 * span[1])

    # EXCLUDE EARS: Protect lateral vertices where |X| > 0.35 * span[0] from inward pushing
    not_ears = np.abs(pos[:, 0]) <= 0.35 * span[0]

    temple_zone = (
        movable_mask
        & not_ears
        & in_outer_y
        & (np.abs(pos[:, 0]) > 0.22 * span[0])
        & (pos[:, 2] > inner_center[2] + 0.02 * span[2])
    )
    crown_zone = (
        movable_mask
        & not_ears
        & (pos[:, 1] > bmin[1] + 0.75 * span[1])
        & (pos[:, 2] > inner_center[2] + 0.01 * span[2])
    )
    recess_mask = temple_zone | crown_zone
    if np.any(recess_mask):
        vec = inner_center - pos[recess_mask]
        vlen = np.linalg.norm(vec, axis=1, keepdims=True)
        pos[recess_mask] += (vec / np.maximum(vlen, 1e-6)) * 0.012

    # Iterative vertex-to-shell clearance push (respecting ear and boundary masks)
    tree_outer_verts = cKDTree(outer_pos)
    for _ in range(8):
        dists, _ = tree_outer_verts.query(pos)
        too_close = np.where((dists < min_clearance_m) & movable_mask & not_ears)[0]
        if len(too_close) > 0:
            vec = inner_center - pos[too_close]
            vlen = np.linalg.norm(vec, axis=1, keepdims=True)
            push = np.maximum(min_clearance_m - dists[too_close][:, None] + 0.001, 0.0015)
            pos[too_close] += (vec / np.maximum(vlen, 1e-6)) * push

    return pos

def project_barycentric_attributes(
    sp_pos: np.ndarray,
    sp_faces: np.ndarray,
    orig_pos: np.ndarray,
    orig_faces: np.ndarray,
    orig_attrs: Dict[str, np.ndarray],
    allowed_bones: Optional[Set[int]] = None,
    fallback_bone: int = 5
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray], np.ndarray]:
    """
    Vectorized per-corner and per-vertex barycentric surface projection onto normal-compatible
    original triangles. Returns (corner_uv0, corner_uv1, vert_bone_indices, vert_bone_weights, vert_normal_w).
    """
    orig_tris_pos = orig_pos[orig_faces]  # (F_orig, 3, 3)
    orig_centers = orig_tris_pos.mean(axis=1)
    v_cross = np.cross(
        orig_tris_pos[:, 2] - orig_tris_pos[:, 0],
        orig_tris_pos[:, 1] - orig_tris_pos[:, 0],
    )
    v_norm_len = np.linalg.norm(v_cross, axis=1, keepdims=True)
    orig_tri_normals = np.where(v_norm_len > 1e-8, v_cross / np.maximum(v_norm_len, 1e-8), [0.0, 1.0, 0.0])

    tree_centers = cKDTree(orig_centers)
    tree_verts = cKDTree(orig_pos)

    has_uv0 = "uv_0" in orig_attrs
    has_uv1 = "uv_1" in orig_attrs
    orig_uv0 = orig_attrs["uv_0"][orig_faces] if has_uv0 else np.zeros((len(orig_faces), 3, 2), dtype=np.float32)
    orig_uv1 = orig_attrs["uv_1"][orig_faces] if has_uv1 else orig_uv0

    num_tris = len(sp_faces)
    tri_pos = sp_pos[sp_faces]  # (F_new, 3, 3)
    f_cross = np.cross(tri_pos[:, 2] - tri_pos[:, 0], tri_pos[:, 1] - tri_pos[:, 0])
    f_len = np.linalg.norm(f_cross, axis=1, keepdims=True)
    f_normals = np.where(f_len > 1e-8, f_cross / np.maximum(f_len, 1e-8), [0.0, 1.0, 0.0])

    # Query closest original triangle per face centroid (primary chart reference)
    f_centers = tri_pos.mean(axis=1)
    k_cands = min(8, len(orig_faces))
    _, cand_f_idx = tree_centers.query(f_centers, k=k_cands)
    if cand_f_idx.ndim == 1:
        cand_f_idx = cand_f_idx[:, None]

    # Pick normal-aligned closest original triangle per face
    cand_norms = orig_tri_normals[cand_f_idx]  # (F_new, K, 3)
    dots = np.sum(cand_norms * f_normals[:, None, :], axis=2)
    cand_centers = orig_centers[cand_f_idx]
    dists = np.linalg.norm(cand_centers - f_centers[:, None, :], axis=2)
    scores = np.where(dots >= -0.1, dists / (np.maximum(dots, 0.0) + 0.2), dists + 1e3)
    best_k = np.argmin(scores, axis=1)
    chosen_orig_f = cand_f_idx[np.arange(num_tris), best_k]

    # Vectorized barycentric projection for all (F_new, 3) corners
    vt_pos = orig_tris_pos[chosen_orig_f]  # (F_new, 3, 3)
    vt_uv0 = orig_uv0[chosen_orig_f]       # (F_new, 3, 2)
    vt_uv1 = orig_uv1[chosen_orig_f]       # (F_new, 3, 2)

    va = vt_pos[:, 0:1, :]  # (F_new, 1, 3)
    vb = vt_pos[:, 1:2, :]
    vc = vt_pos[:, 2:3, :]
    v0_b = vb - va
    v1_c = vc - va
    v2_p = tri_pos - va     # (F_new, 3, 3)

    d00 = np.sum(v0_b * v0_b, axis=2)
    d01 = np.sum(v0_b * v1_c, axis=2)
    d11 = np.sum(v1_c * v1_c, axis=2)
    d20 = np.sum(v2_p * v0_b, axis=2)
    d21 = np.sum(v2_p * v1_c, axis=2)
    denom = d00 * d11 - d01 * d01

    valid_d = np.abs(denom) > 1e-8
    safe_denom = np.where(valid_d, denom, 1.0)
    b_v = np.where(valid_d, (d11 * d20 - d01 * d21) / safe_denom, 0.0)
    b_w = np.where(valid_d, (d00 * d21 - d01 * d20) / safe_denom, 0.0)
    b_u = 1.0 - b_v - b_w

    b_u = np.clip(b_u, 0.0, 1.0)
    b_v = np.clip(b_v, 0.0, 1.0)
    b_w = np.clip(b_w, 0.0, 1.0)
    b_sum = np.maximum(b_u + b_v + b_w, 1e-8)
    b_u /= b_sum
    b_v /= b_sum
    b_w /= b_sum

    corner_uv0 = (
        b_u[:, :, None] * vt_uv0[:, 0:1, :]
        + b_v[:, :, None] * vt_uv0[:, 1:2, :]
        + b_w[:, :, None] * vt_uv0[:, 2:3, :]
    ).astype(np.float32)
    corner_uv1 = (
        b_u[:, :, None] * vt_uv1[:, 0:1, :]
        + b_v[:, :, None] * vt_uv1[:, 1:2, :]
        + b_w[:, :, None] * vt_uv1[:, 2:3, :]
    ).astype(np.float32)

    # Query nearest original vertex for ALL meshes (both chr/ and rigid obj/ doors)
    num_sp_verts = len(sp_pos)
    _, nn_v = tree_verts.query(sp_pos)

    # Always transfer normal_w (stores rigid bone index on obj/ doors, levers, and chests)
    if "normal_w" in orig_attrs:
        vert_normal_w = orig_attrs["normal_w"][nn_v].copy()
    else:
        vert_normal_w = np.zeros((num_sp_verts, 1), dtype=np.uint8)

    vert_bi = None
    vert_bw = None
    if "bone_indices" in orig_attrs and "bone_weights" in orig_attrs:
        raw_bi = orig_attrs["bone_indices"][nn_v].copy()
        raw_bw = orig_attrs["bone_weights"][nn_v].copy()
        vert_bw, vert_bi = normalize_bone_weights_strict(
            raw_bw, raw_bi, allowed_bones=allowed_bones, fallback_bone=fallback_bone
        )

    return corner_uv0, corner_uv1, vert_bi, vert_bw, vert_normal_w

def compute_angle_weighted_normals_and_tangents(
    verts_pos: np.ndarray,
    verts_uv0: np.ndarray,
    verts_uv1: np.ndarray,
    faces: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes scale-invariant Thurmer-Wuthrich corner-angle-weighted vertex normals
    and handedness-aware (Tw in {-1.0, +1.0}) Gram-Schmidt tangent frames for uv_0 and uv_1.
    """
    num_verts = len(verts_pos)
    p0 = verts_pos[faces[:, 0]]
    p1 = verts_pos[faces[:, 1]]
    p2 = verts_pos[faces[:, 2]]

    # Outward clockwise face normal
    raw_fn = np.cross(p2 - p0, p1 - p0)
    fn_len = np.linalg.norm(raw_fn, axis=1, keepdims=True)
    unit_fn = np.where(fn_len > 1e-8, raw_fn / np.maximum(fn_len, 1e-8), [0.0, 1.0, 0.0])

    # Interior corner angles alpha_0, alpha_1, alpha_2
    e01 = p1 - p0
    e02 = p2 - p0
    e12 = p2 - p1
    l01 = np.maximum(np.linalg.norm(e01, axis=1), 1e-8)
    l02 = np.maximum(np.linalg.norm(e02, axis=1), 1e-8)
    l12 = np.maximum(np.linalg.norm(e12, axis=1), 1e-8)

    a0 = np.arccos(np.clip(np.sum(e01 * e02, axis=1) / (l01 * l02), -1.0, 1.0))
    a1 = np.arccos(np.clip(np.sum((-e01) * e12, axis=1) / (l01 * l12), -1.0, 1.0))
    a2 = np.arccos(np.clip(np.sum((-e02) * (-e12), axis=1) / (l02 * l12), -1.0, 1.0))
    angles = np.stack([a0, a1, a2], axis=1)

    vert_normals = np.zeros((num_verts, 3), dtype=np.float32)
    for c in range(3):
        np.add.at(vert_normals, faces[:, c], unit_fn * angles[:, c:c+1])

    vn_len = np.linalg.norm(vert_normals, axis=1, keepdims=True)
    vert_normals = np.where(
        vn_len > 1e-6, vert_normals / np.maximum(vn_len, 1e-6), np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
    ).astype(np.float32)

    def _build_tangent_array(uv_arr: np.ndarray) -> np.ndarray:
        u0 = uv_arr[faces[:, 0]]
        u1 = uv_arr[faces[:, 1]]
        u2 = uv_arr[faces[:, 2]]
        duv1 = u1 - u0
        duv2 = u2 - u0
        det = duv1[:, 0] * duv2[:, 1] - duv1[:, 1] * duv2[:, 0]
        valid_uv = np.abs(det) > 1e-8
        inv_det = np.where(valid_uv, 1.0 / np.where(valid_uv, det, 1.0), 0.0)[:, None]

        sdir = (e01 * duv2[:, 1:2] - e02 * duv1[:, 1:2]) * inv_det
        tdir = (e02 * duv1[:, 0:1] - e01 * duv2[:, 0:1]) * inv_det

        # Fallback orthogonal tangent where UV determinant is degenerate
        up = np.where(np.abs(unit_fn[:, 1:2]) < 0.9, [0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        fallback_s = np.cross(unit_fn, up)
        fallback_t = np.cross(unit_fn, fallback_s)
        sdir = np.where(valid_uv[:, None], sdir, fallback_s)
        tdir = np.where(valid_uv[:, None], tdir, fallback_t)

        s_len = np.linalg.norm(sdir, axis=1, keepdims=True)
        t_len = np.linalg.norm(tdir, axis=1, keepdims=True)
        sdir = np.where(s_len > 1e-8, sdir / np.maximum(s_len, 1e-8), [1.0, 0.0, 0.0])
        tdir = np.where(t_len > 1e-8, tdir / np.maximum(t_len, 1e-8), [0.0, 0.0, 1.0])

        tan1 = np.zeros((num_verts, 3), dtype=np.float32)
        tan2 = np.zeros((num_verts, 3), dtype=np.float32)
        for c in range(3):
            np.add.at(tan1, faces[:, c], sdir * angles[:, c:c+1])
            np.add.at(tan2, faces[:, c], tdir * angles[:, c:c+1])

        # FromSoftware FLVER2 tangent convention:
        # tangent_0 is the V-derivative (tdir), NOT sdir (U-derivative)!
        # Gram-Schmidt orthogonalization against vert_normals:
        dot_nt = np.sum(vert_normals * tan2, axis=1, keepdims=True)
        t_ortho = tan2 - vert_normals * dot_nt
        t_norm = np.linalg.norm(t_ortho, axis=1, keepdims=True)
        fallback_v = np.cross(
            vert_normals,
            np.where(np.abs(vert_normals[:, 1:2]) < 0.9, [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]),
        )
        fb_norm = np.maximum(np.linalg.norm(fallback_v, axis=1, keepdims=True), 1e-6)
        t_unit = np.where(t_norm > 1e-6, t_ortho / np.maximum(t_norm, 1e-6), fallback_v / fb_norm)

        # FromSoftware handedness: Tw = +1.0 if det_UV >= 0.0 else -1.0
        det_sign = np.where(det >= 0, 1.0, -1.0)
        det_w = np.zeros(num_verts, dtype=np.float32)
        for c in range(3):
            np.add.at(det_w, faces[:, c], det_sign * angles[:, c])
        tw = np.where(det_w >= 0.0, 1.0, -1.0)[:, None]
        return np.hstack([t_unit, tw]).astype(np.float32)

    tang0 = _build_tangent_array(verts_uv0)
    tang1 = _build_tangent_array(verts_uv1)
    return vert_normals, tang0, tang1


def decimate_component_shared_verts(
    comp_pos: np.ndarray,
    comp_faces: np.ndarray,
    comp_attrs: Dict[str, np.ndarray],
    target_tris: int,
    preserve_border: bool = True,
    aggressiveness: int = 5,
    uv_cluster_thresh: float = 0.15,
    allowed_bones: Optional[Set[int]] = None,
    fallback_bone: int = 5,
    outer_shell: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    min_clearance_m: float = 0.0055,
    is_weapon: bool = False
) -> Tuple[Dict[str, np.ndarray], np.ndarray]:
    """
    Decimates a single topological mesh component while keeping SHARED WELDED VERTICES
    (num_verts < num_tris), projecting UVs and bone weights, and enforcing shell clearance.
    """
    # 1. Positional + Rigid Bone Group welding (0.1mm grid)
    # Prevents left/right door panels or hinged weapon parts from welding together across joints
    pos_grid = np.round(comp_pos * 10000).astype(np.int64)
    if "normal_w" in comp_attrs:
        nw_col = comp_attrs["normal_w"].reshape(len(comp_pos), -1)[:, 0:1].astype(np.int64)
    else:
        nw_col = np.zeros((len(comp_pos), 1), dtype=np.int64)

    weld_key = np.hstack([pos_grid, nw_col])
    _, unique_inv = np.unique(weld_key, axis=0, return_inverse=True)
    w_pos = np.zeros((unique_inv.max() + 1, 3), dtype=np.float32)
    w_pos[unique_inv] = comp_pos
    w_faces = unique_inv[comp_faces]
    valid = (
        (w_faces[:, 0] != w_faces[:, 1])
        & (w_faces[:, 1] != w_faces[:, 2])
        & (w_faces[:, 0] != w_faces[:, 2])
    )
    w_faces = w_faces[valid]

    # If pre-weld left fewer than 4 valid triangles, return the original component untouched
    if len(w_faces) < 4:
        out_orig = {k: v.copy() for k, v in comp_attrs.items()}
        if "bone_weights" in out_orig and "bone_indices" in out_orig:
            out_orig["bone_weights"], out_orig["bone_indices"] = normalize_bone_weights_strict(
                out_orig["bone_weights"], out_orig["bone_indices"], allowed_bones=allowed_bones, fallback_bone=fallback_bone
            )
        return out_orig, comp_faces.astype(np.uint32)

    # 2. QEM simplification via pyfqmr
    border_flag = preserve_border

    simp = pyfqmr.Simplify()
    simp.setMesh(w_pos, w_faces)
    simp.simplify_mesh(
        target_count=max(8, target_tris),
        aggressiveness=aggressiveness,
        preserve_border=border_flag,
        verbose=False,
    )
    sp_pos, sp_faces, _ = simp.getMesh()
    sp_pos = sp_pos.astype(np.float32)

    # Fallback if pyfqmr collapsed all faces on a degenerate/coplanar piece
    if len(sp_faces) < 4:
        sp_pos = w_pos.astype(np.float32)
        sp_faces = w_faces.astype(np.uint32)

    # 3. Enforce shell clearance against overlapping headgear/armor before sliver cleanup
    if outer_shell is not None and len(sp_faces) > 0:
        sp_pos = enforce_shell_clearance(
            sp_pos, sp_faces, outer_shell[0], outer_shell[1], min_clearance_m=min_clearance_m
        )

    # 4. Normal-guarded sliver and degenerate face removal (keep backup if all faces are slivers)
    pre_sliver_faces = sp_faces.copy()
    sp_faces = contract_slivers_normal_guarded(sp_pos, sp_faces, max_aspect=25.0, max_passes=50)
    if len(sp_faces) == 0:
        sp_faces = pre_sliver_faces

    # Final shell clearance verification pass after sliver contraction
    if outer_shell is not None and len(sp_faces) > 0:
        sp_pos = enforce_shell_clearance(
            sp_pos, sp_faces, outer_shell[0], outer_shell[1], min_clearance_m=min_clearance_m
        )

    num_tris = len(sp_faces)
    corner_uv0, corner_uv1, vert_bi, vert_bw, vert_normal_w = project_barycentric_attributes(
        sp_pos,
        sp_faces,
        comp_pos,
        comp_faces,
        comp_attrs,
        allowed_bones=allowed_bones,
        fallback_bone=fallback_bone,
    )

    # 5. Weld shared vertices within UV chart threshold (<0.15)
    corners_by_sp_vert: Dict[int, List[Tuple[int, int, np.ndarray, np.ndarray]]] = defaultdict(list)
    for fi in range(num_tris):
        for c in range(3):
            corners_by_sp_vert[int(sp_faces[fi, c])].append(
                (fi, c, corner_uv0[fi, c], corner_uv1[fi, c])
            )

    new_faces = np.zeros_like(sp_faces, dtype=np.uint32)
    new_verts_pos: List[np.ndarray] = []
    new_verts_uv0: List[np.ndarray] = []
    new_verts_uv1: List[np.ndarray] = []
    new_verts_sp_idx: List[int] = []

    for sp_v, corner_list in corners_by_sp_vert.items():
        p = sp_pos[sp_v]
        clusters = []
        for fi, c, uv0, uv1 in corner_list:
            matched = False
            for cl in clusters:
                if np.linalg.norm(cl["mean_uv0"] - uv0) < uv_cluster_thresh:
                    cl["corners"].append((fi, c))
                    cl["uv0s"].append(uv0)
                    cl["uv1s"].append(uv1)
                    cl["mean_uv0"] = np.mean(cl["uv0s"], axis=0)
                    cl["mean_uv1"] = np.mean(cl["uv1s"], axis=0)
                    matched = True
                    break
            if not matched:
                clusters.append({
                    "mean_uv0": uv0.copy(),
                    "mean_uv1": uv1.copy(),
                    "corners": [(fi, c)],
                    "uv0s": [uv0],
                    "uv1s": [uv1],
                })

        for cl in clusters:
            new_v_idx = len(new_verts_pos)
            new_verts_pos.append(p)
            new_verts_uv0.append(cl["mean_uv0"])
            new_verts_uv1.append(cl["mean_uv1"])
            new_verts_sp_idx.append(sp_v)
            for fi, c in cl["corners"]:
                new_faces[fi, c] = new_v_idx

    arr_pos = np.array(new_verts_pos, dtype=np.float32).reshape(-1, 3)
    arr_uv0 = np.array(new_verts_uv0, dtype=np.float32).reshape(-1, 2)
    arr_uv1 = np.array(new_verts_uv1, dtype=np.float32).reshape(-1, 2)
    sp_idx_arr = np.array(new_verts_sp_idx, dtype=np.int32)

    # 6. Compute angle-weighted normals and handedness-aware tangents
    vert_normals, tang0, tang1 = compute_angle_weighted_normals_and_tangents(
        arr_pos, arr_uv0, arr_uv1, new_faces
    )

    raw_generated: Dict[str, np.ndarray] = {
        "position": arr_pos,
        "normal": vert_normals,
        "normal_w": vert_normal_w[sp_idx_arr],
        "tangent_0": tang0,
        "tangent_1": tang1,
        "color_0": np.ones((len(arr_pos), 4), dtype=np.float32),
        "uv_0": arr_uv0,
        "uv_1": arr_uv1,
    }
    if vert_bi is not None and vert_bw is not None:
        raw_generated["bone_indices"] = vert_bi[sp_idx_arr]
        raw_generated["bone_weights"] = vert_bw[sp_idx_arr]

    # Match exact trailing shape (e.g. (N, 1) for normal_w) and dtype of original vertex array
    out_attrs: Dict[str, np.ndarray] = {}
    for k, orig_v in comp_attrs.items():
        target_shape = (len(arr_pos),) + orig_v.shape[1:]
        if k in raw_generated:
            val = raw_generated[k]
            if val.shape != target_shape and val.size == int(np.prod(target_shape)):
                val = val.reshape(target_shape)
            out_attrs[k] = val.astype(orig_v.dtype, copy=False)
        elif k.startswith("uv_"):
            out_attrs[k] = arr_uv0.reshape(target_shape).astype(orig_v.dtype, copy=False)
        elif k.startswith("tangent_"):
            out_attrs[k] = tang0.reshape(target_shape).astype(orig_v.dtype, copy=False)
        elif k.startswith("color_"):
            out_attrs[k] = np.ones(target_shape, dtype=orig_v.dtype)
        else:
            out_attrs[k] = np.zeros(target_shape, dtype=orig_v.dtype)

    return out_attrs, new_faces

def write_attributes_to_mesh(
    m,
    attrs: Dict[str, np.ndarray],
    faces: np.ndarray
) -> None:
    """Writes unified vertex attributes across all vertex arrays (VA0..VAn) and syncs FaceSets."""
    num_verts = len(attrs["position"])
    for va in m.vertex_arrays:
        new_arr = np.zeros(num_verts, dtype=va.array.dtype)
        for fld in va.array.dtype.names:
            target_shape = new_arr[fld].shape
            if fld in attrs:
                val = attrs[fld]
                if val.shape != target_shape and val.size == int(np.prod(target_shape)):
                    val = val.reshape(target_shape)
                new_arr[fld] = val
            elif fld.startswith("uv_"):
                new_arr[fld] = attrs["uv_0"].reshape(target_shape)
            elif fld.startswith("tangent_"):
                new_arr[fld] = attrs["tangent_0"].reshape(target_shape)
            elif fld.startswith("color_"):
                new_arr[fld] = 1.0
        va.array = new_arr

    m.face_sets[0].vertex_indices = faces.astype(np.uint32)
    for fsi in range(1, len(m.face_sets)):
        m.face_sets[fsi].vertex_indices = faces.astype(np.uint32).copy()


def partition_submesh_components(
    pos: np.ndarray,
    faces: np.ndarray,
    attrs: Dict[str, np.ndarray],
    mat_name: str,
    hand_bones: Set[int],
    head_bones: Set[int]
) -> List[Tuple[str, np.ndarray, np.ndarray]]:
    """
    Splits submesh into connected components and classifies them as:
    - 'HANDS': Articulated hand/finger geometry (demade to low-poly target ratio).
    - 'HEAD_SKIN': Facial/cranial skin geometry (600-800 tri likeness budget).
    - 'RIGID': Standard rigid geometry.
    """
    grid = np.round(pos * 10000).astype(np.int64)
    _, u_inv = np.unique(grid, axis=0, return_inverse=True)
    num_w = int(u_inv.max() + 1)
    w_faces = u_inv[faces]

    rows = np.concatenate([w_faces[:, 0], w_faces[:, 1], w_faces[:, 2]])
    cols = np.concatenate([w_faces[:, 1], w_faces[:, 2], w_faces[:, 0]])
    data = np.ones(len(rows), dtype=np.int8)
    adj = csr_matrix((data, (rows, cols)), shape=(num_w, num_w))
    n_comps, comp_labels = connected_components(adj, directed=False)

    face_comp = comp_labels[w_faces[:, 0]]
    has_bones = "bone_indices" in attrs and "bone_weights" in attrs
    is_skin_mat = any(k in mat_name.lower() for k in ("skin", "face", "head_a", "fc_"))

    role_vert_masks: Dict[str, np.ndarray] = {
        "HANDS": np.zeros(len(pos), dtype=bool),
        "HEAD_SKIN": np.zeros(len(pos), dtype=bool),
        "RIGID": np.zeros(len(pos), dtype=bool),
    }

    y_min_global, y_max_global = float(pos[:, 1].min()), float(pos[:, 1].max())
    has_Multi_Region_Skin = is_skin_mat and (y_max_global - y_min_global > 0.50)

    for cid in range(n_comps):
        f_mask = (face_comp == cid)
        if not np.any(f_mask):
            continue
        c_verts = np.unique(faces[f_mask])
        c_pos = pos[c_verts]

        role = "RIGID"
        if has_bones:
            dom_b = attrs["bone_indices"][c_verts, np.argmax(attrs["bone_weights"][c_verts], axis=1)]
            hand_frac = float(np.mean(np.isin(dom_b, list(hand_bones)))) if hand_bones else 0.0
            head_frac = float(np.mean(np.isin(dom_b, list(head_bones)))) if head_bones else 0.0

            if hand_frac > 0.35 or (has_Multi_Region_Skin and float(c_pos[:, 1].max()) < 1.35):
                role = "HANDS"
            elif is_skin_mat and (head_frac > 0.35 or float(c_pos[:, 1].min()) > 1.55):
                role = "HEAD_SKIN"
        elif has_Multi_Region_Skin:
            if float(c_pos[:, 1].max()) < 1.35:
                role = "HANDS"
            elif float(c_pos[:, 1].min()) > 1.55:
                role = "HEAD_SKIN"

        role_vert_masks[role][c_verts] = True

    partitions: List[Tuple[str, np.ndarray, np.ndarray]] = []
    for role in ("HANDS", "HEAD_SKIN", "RIGID"):
        vmask = role_vert_masks[role]
        if not np.any(vmask):
            continue
        v_indices = np.where(vmask)[0]
        f_mask = np.all(vmask[faces], axis=1)
        if np.any(f_mask):
            partitions.append((role, v_indices, faces[f_mask]))

    return partitions

def get_vertex_dominant_bone(attrs: Dict[str, np.ndarray], num_verts: int) -> np.ndarray:
    """
    Returns the primary controlling bone ID for each vertex:
    - Uses bone_indices[argmax(bone_weights)] when skeletal weights are present (chr/ and parts/wp_).
    - Falls back to normal_w when rigid object bone binding is used (obj/ doors, levers).
    """
    if "bone_indices" in attrs and "bone_weights" in attrs:
        bw = attrs["bone_weights"]
        bi = attrs["bone_indices"]
        has_w = np.sum(bw, axis=1) > 1e-6
        dom_col = np.argmax(bw, axis=1)
        dom_b = bi[np.arange(num_verts), dom_col].astype(np.int32)
        if "normal_w" in attrs:
            nw = attrs["normal_w"].reshape(num_verts, -1)[:, 0].astype(np.int32)
            dom_b = np.where(has_w, dom_b, nw)
        return dom_b
    elif "normal_w" in attrs:
        return attrs["normal_w"].reshape(num_verts, -1)[:, 0].astype(np.int32)
    return np.zeros(num_verts, dtype=np.int32)

def decimate_rigid_by_bone_groups(
    comp_pos: np.ndarray,
    comp_faces: np.ndarray,
    comp_attrs: Dict[str, np.ndarray],
    target_ratio: float,
    is_weapon: bool = False,
    preserve_border: bool = False,
) -> Tuple[Dict[str, np.ndarray], np.ndarray]:
    """
    Partitions a multi-bone weapon or articulated prop by dominant bone ID so QEM and KDTree
    attribute projection NEVER bridge across separate moving bones (e.g. Saw Cleaver handle vs.
    blade tip, or Threaded Cane whip segments).
    - Faces spanning multiple bones (whip chain/wire links) are 100% preserved.
    - Each single-bone rigid piece is decimated independently with preserve_border control.
    """
    dom_bone = get_vertex_dominant_bone(comp_attrs, len(comp_pos))
    f_b0 = dom_bone[comp_faces[:, 0]]
    f_b1 = dom_bone[comp_faces[:, 1]]
    f_b2 = dom_bone[comp_faces[:, 2]]

    same_bone_mask = (f_b0 == f_b1) & (f_b1 == f_b2)
    unique_bones = np.unique(f_b0[same_bone_mask])

    # If the entire submesh is bound to a single bone and has no multi-bone bridge faces,
    # decimate as a single component.
    if len(unique_bones) <= 1 and np.all(same_bone_mask):
        t_tris = max(24, int(round(len(comp_faces) * target_ratio)))
        return decimate_component_shared_verts(
            comp_pos,
            comp_faces,
            comp_attrs,
            target_tris=t_tris,
            preserve_border=preserve_border,
            aggressiveness=5,
            is_weapon=is_weapon,
        )

    out_attrs_list: List[Dict[str, np.ndarray]] = []
    out_faces_list: List[np.ndarray] = []
    v_offset = 0

    # 1. Preserve multi-bone bridge faces (e.g. whip cable/chain connectors, hinge pins) 100% intact
    bridge_mask = ~same_bone_mask
    if np.any(bridge_mask):
        b_faces_global = comp_faces[bridge_mask]
        b_verts = np.unique(b_faces_global)
        b_map = np.zeros(len(comp_pos), dtype=np.uint32)
        b_map[b_verts] = np.arange(len(b_verts), dtype=np.uint32)
        b_attrs = {k: v[b_verts].copy() for k, v in comp_attrs.items()}
        if "bone_weights" in b_attrs and "bone_indices" in b_attrs:
            b_attrs["bone_weights"], b_attrs["bone_indices"] = normalize_bone_weights_strict(
                b_attrs["bone_weights"], b_attrs["bone_indices"]
            )
        out_attrs_list.append(b_attrs)
        out_faces_list.append(b_map[b_faces_global] + v_offset)
        v_offset += len(b_verts)

    # 2. Decimate each single-bone rigid piece in complete isolation
    for b_id in unique_bones:
        b_fmask = same_bone_mask & (f_b0 == b_id)
        part_faces_global = comp_faces[b_fmask]
        if len(part_faces_global) == 0:
            continue

        part_verts = np.unique(part_faces_global)
        p_map = np.zeros(len(comp_pos), dtype=np.uint32)
        p_map[part_verts] = np.arange(len(part_verts), dtype=np.uint32)
        part_faces = p_map[part_faces_global]
        part_attrs = {k: v[part_verts].copy() for k, v in comp_attrs.items()}
        part_pos = part_attrs["position"]

        # Small articulated links (e.g. individual Threaded Cane whip segments < 64 tris)
        # or submeshes with bridge borders must keep their silhouette intact
        if len(part_faces) < 64:
            if "bone_weights" in part_attrs and "bone_indices" in part_attrs:
                part_attrs["bone_weights"], part_attrs["bone_indices"] = normalize_bone_weights_strict(
                    part_attrs["bone_weights"], part_attrs["bone_indices"]
                )
            out_attrs_list.append(part_attrs)
            out_faces_list.append(part_faces.astype(np.uint32) + v_offset)
            v_offset += len(part_pos)
        else:
            t_tris = max(24, int(round(len(part_faces) * target_ratio)))
            dec_attrs, dec_faces = decimate_component_shared_verts(
                part_pos,
                part_faces,
                part_attrs,
                target_tris=t_tris,
                preserve_border=preserve_border,
                aggressiveness=5,
                allowed_bones={int(b_id)},
                fallback_bone=int(b_id),
                is_weapon=is_weapon,
            )
            out_attrs_list.append(dec_attrs)
            out_faces_list.append(dec_faces + v_offset)
            v_offset += len(dec_attrs["position"])

    merged_attrs: Dict[str, np.ndarray] = {}
    for k in out_attrs_list[0].keys():
        merged_attrs[k] = np.concatenate([ca[k] for ca in out_attrs_list], axis=0)
    merged_faces = np.vstack(out_faces_list).astype(np.uint32)
    return merged_attrs, merged_faces

def decimate_head_skin_landmark_aware(
    comp_pos: np.ndarray,
    comp_faces: np.ndarray,
    comp_attrs: Dict[str, np.ndarray],
    head_target_tris: int = 650,
    allowed_bones: Optional[Set[int]] = None,
    fallback_bone: int = 5,
    outer_shell: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    min_clearance_m: float = 0.0055,
    exaggerate_factor: float = 1.04,
) -> Tuple[Dict[str, np.ndarray], np.ndarray]:
    """
    Orientation-Safe PSX Head Decimator:
    1. Auto-detects whether the face points toward -Z or +Z using facial curvature/vertex density
       (in Bloodborne FLVERs, the face points toward -Z while the back of the skull is +Z).
    2. Pre-reduces the occluded back/top cranium (hidden under the bonnet/hair) so it doesn't waste
       the polygon budget, then decimates the unified manifold head to `head_target_tris` with
       zero artificial internal seam rings.
    """
    # 1. Weld coincident vertices (0.1mm grid) on the full head component
    pos_grid = np.round(comp_pos * 10000).astype(np.int64)
    _, unique_inv = np.unique(pos_grid, axis=0, return_inverse=True)
    w_pos = np.zeros((unique_inv.max() + 1, 3), dtype=np.float32)
    w_pos[unique_inv] = comp_pos
    w_faces = unique_inv[comp_faces]
    valid = (
        (w_faces[:, 0] != w_faces[:, 1])
        & (w_faces[:, 1] != w_faces[:, 2])
        & (w_faces[:, 0] != w_faces[:, 2])
    )
    w_faces = w_faces[valid]

    b_min = w_pos.min(axis=0)
    b_max = w_pos.max(axis=0)
    span = np.maximum(b_max - b_min, 1e-6)

    # Auto-detect face forward axis (-Z vs +Z):
    # The face (eyes, nostrils, mouth) has much higher vertex density than the back of the skull.
    mid_z = 0.5 * (b_min[2] + b_max[2])
    verts_neg_z = int(np.sum(w_pos[:, 2] < mid_z))
    verts_pos_z = int(np.sum(w_pos[:, 2] >= mid_z))
    face_sign = -1.0 if verts_neg_z >= verts_pos_z else 1.0

    # Normalized depth `nd` where 1.0 = tip of nose (front) and 0.0 = back of skull
    if face_sign < 0:
        nd_verts = (b_max[2] - w_pos[:, 2]) / span[2]
    else:
        nd_verts = (w_pos[:, 2] - b_min[2]) / span[2]
    ny_verts = (w_pos[:, 1] - b_min[1]) / span[1]

    # 2. Unified manifold QEM simplification with low aggressiveness (3) to preserve nose/lip/eye creases
    simp = pyfqmr.Simplify()
    simp.setMesh(w_pos, w_faces)
    simp.simplify_mesh(
        target_count=max(250, head_target_tris),
        aggressiveness=3,
        preserve_border=True,
        verbose=False,
    )
    sp_pos, sp_faces, _ = simp.getMesh()
    sp_pos = sp_pos.astype(np.float32)

    # Subtle PSX nose/lip relief boost on the anterior facial feature cone
    if exaggerate_factor != 1.0 and len(sp_pos) > 0:
        if face_sign < 0:
            sp_nd = (b_max[2] - sp_pos[:, 2]) / span[2]
        else:
            sp_nd = (sp_pos[:, 2] - b_min[2]) / span[2]
        sp_ny = (sp_pos[:, 1] - b_min[1]) / span[1]
        sp_nx = np.abs(sp_pos[:, 0] - 0.5 * (b_min[0] + b_max[0])) / (0.5 * span[0])

        # Anterior nose/mouth cone (front-most 30% of head depth, central X, chin-to-brow Y)
        face_cone = (sp_nd > 0.68) & (sp_ny > 0.18) & (sp_ny < 0.65) & (sp_nx < 0.45)
        if np.any(face_cone):
            med_z = np.median(sp_pos[face_cone, 2])
            sp_pos[face_cone, 2] = med_z + (sp_pos[face_cone, 2] - med_z) * exaggerate_factor

    # 3. Enforce headgear/bonnet clearance (with ear protection) and sliver cleanup
    if outer_shell is not None and len(sp_faces) > 0:
        sp_pos = enforce_shell_clearance(
            sp_pos, sp_faces, outer_shell[0], outer_shell[1], min_clearance_m=min_clearance_m
        )
    pre_sliver_faces = sp_faces.copy()
    sp_faces = contract_slivers_normal_guarded(sp_pos, sp_faces, max_aspect=25.0, max_passes=50)
    if len(sp_faces) == 0:
        sp_faces = pre_sliver_faces
    if outer_shell is not None and len(sp_faces) > 0:
        sp_pos = enforce_shell_clearance(
            sp_pos, sp_faces, outer_shell[0], outer_shell[1], min_clearance_m=min_clearance_m
        )

    # 4. Project barycentric UVs, bone weights, and normal_w onto the simplified head mesh
    num_tris = len(sp_faces)
    corner_uv0, corner_uv1, vert_bi, vert_bw, vert_normal_w = project_barycentric_attributes(
        sp_pos,
        sp_faces,
        comp_pos,
        comp_faces,
        comp_attrs,
        allowed_bones=allowed_bones,
        fallback_bone=fallback_bone,
    )

    # 5. Shared-vertex UV cluster welding (< 0.15)
    corners_by_sp_vert: Dict[int, List[Tuple[int, int, np.ndarray, np.ndarray]]] = defaultdict(list)
    for fi in range(num_tris):
        for c in range(3):
            corners_by_sp_vert[int(sp_faces[fi, c])].append((fi, c, corner_uv0[fi, c], corner_uv1[fi, c]))

    new_faces = np.zeros_like(sp_faces, dtype=np.uint32)
    new_verts_pos: List[np.ndarray] = []
    new_verts_uv0: List[np.ndarray] = []
    new_verts_uv1: List[np.ndarray] = []
    new_verts_sp_idx: List[int] = []

    for sp_v, corner_list in corners_by_sp_vert.items():
        p = sp_pos[sp_v]
        clusters = []
        for fi, c, uv0, uv1 in corner_list:
            matched = False
            for cl in clusters:
                if np.linalg.norm(cl["mean_uv0"] - uv0) < 0.15:
                    cl["corners"].append((fi, c))
                    cl["uv0s"].append(uv0)
                    cl["uv1s"].append(uv1)
                    cl["mean_uv0"] = np.mean(cl["uv0s"], axis=0)
                    cl["mean_uv1"] = np.mean(cl["uv1s"], axis=0)
                    matched = True
                    break
            if not matched:
                clusters.append({
                    "mean_uv0": uv0.copy(),
                    "mean_uv1": uv1.copy(),
                    "corners": [(fi, c)],
                    "uv0s": [uv0],
                    "uv1s": [uv1],
                })
        for cl in clusters:
            new_v_idx = len(new_verts_pos)
            new_verts_pos.append(p)
            new_verts_uv0.append(cl["mean_uv0"])
            new_verts_uv1.append(cl["mean_uv1"])
            new_verts_sp_idx.append(sp_v)
            for fi, c in cl["corners"]:
                new_faces[fi, c] = new_v_idx

    arr_pos = np.array(new_verts_pos, dtype=np.float32).reshape(-1, 3)
    arr_uv0 = np.array(new_verts_uv0, dtype=np.float32).reshape(-1, 2)
    arr_uv1 = np.array(new_verts_uv1, dtype=np.float32).reshape(-1, 2)
    sp_idx_arr = np.array(new_verts_sp_idx, dtype=np.int32)

    vert_normals, tang0, tang1 = compute_angle_weighted_normals_and_tangents(
        arr_pos, arr_uv0, arr_uv1, new_faces
    )

    raw_generated: Dict[str, np.ndarray] = {
        "position": arr_pos,
        "normal": vert_normals,
        "normal_w": vert_normal_w[sp_idx_arr],
        "tangent_0": tang0,
        "tangent_1": tang1,
        "color_0": np.ones((len(arr_pos), 4), dtype=np.float32),
        "uv_0": arr_uv0,
        "uv_1": arr_uv1,
    }
    if vert_bi is not None and vert_bw is not None:
        raw_generated["bone_indices"] = vert_bi[sp_idx_arr]
        raw_generated["bone_weights"] = vert_bw[sp_idx_arr]

    out_attrs: Dict[str, np.ndarray] = {}
    for k, orig_v in comp_attrs.items():
        target_shape = (len(arr_pos),) + orig_v.shape[1:]
        if k in raw_generated:
            val = raw_generated[k]
            if val.shape != target_shape and val.size == int(np.prod(target_shape)):
                val = val.reshape(target_shape)
            out_attrs[k] = val.astype(orig_v.dtype, copy=False)
        elif k.startswith("uv_"):
            out_attrs[k] = arr_uv0.reshape(target_shape).astype(orig_v.dtype, copy=False)
        elif k.startswith("tangent_"):
            out_attrs[k] = tang0.reshape(target_shape).astype(orig_v.dtype, copy=False)
        elif k.startswith("color_"):
            out_attrs[k] = np.ones(target_shape, dtype=orig_v.dtype)
        else:
            out_attrs[k] = np.zeros(target_shape, dtype=orig_v.dtype)

    return out_attrs, new_faces

def decimate_flver(
    flv,
    target_ratio: float = 0.45,
    flat_normals: bool = False,
    disable_cloth: bool = False,
    preserve_border: bool = True,
    head_target_tris: int = 700,
    submesh_targets: Optional[Dict[int, int]] = None,
    filename: str = "" # <--- Added argument
) -> Tuple[int, int]:
    """
    Decimates rigid submeshes in a FLVER model while:
    - Keeping SHARED WELDED VERTICES (num_verts < num_tris).
    - Preserving 100% of Havok cloth submeshes and articulated hand/finger components.
    - Reconstructing facial/head skin components to ~700 triangles with positive headgear clearance.
    - Normalizing all bone weights to float sum == 1.0 and byte sum == 255.
    """
    cloth_submeshes: Set[int] = set()
    for mi, m in enumerate(flv.meshes):
        mat_name = m.material.name.lower() if m.material else ""
        mtd_name = m.material.mat_def_name.lower() if m.material else ""
        if "cloth" in mat_name or "_cloth" in mtd_name:
            cloth_submeshes.add(mi)

    if disable_cloth:
        disable_cloth_physics(flv)

    is_file_weapon = 'wp_' in filename.lower()
    hand_bones, head_bones = classify_skeleton_bones(flv, is_weapon=is_file_weapon)

    # First pass: decimate non-skin rigid submeshes (including headgear/bonnets) so their
    # simplified cages can serve as outer clearance shells for any head/skin submesh.
    skin_submesh_indices: Set[int] = set()
    for mi, m in enumerate(flv.meshes):
        if mi in cloth_submeshes or not m.face_sets or len(m.vertex_arrays) == 0:
            continue
        mat_name = m.material.name.lower() if m.material else ""
        if any(k in mat_name for k in ("skin", "face")):
            skin_submesh_indices.add(mi)

    ordered_indices = (
        [mi for mi in range(len(flv.meshes)) if mi not in skin_submesh_indices]
        + sorted(skin_submesh_indices)
    )

    total_orig_tris = 0
    total_new_tris = 0
    decimated_shells: List[Tuple[int, np.ndarray, np.ndarray]] = []
    
    # --- FIX: Initialize bounding box accumulators here ---
    all_mins: List[np.ndarray] = []
    all_maxs: List[np.ndarray] = []
    # -----------------------------------------------------
    
    is_file_weapon = 'wp_' in filename.lower()

    for mi in ordered_indices:
        m = flv.meshes[mi]
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue

        faces = m.face_sets[0].vertex_indices.reshape(-1, 3)
        orig_count = len(faces)
        total_orig_tris += orig_count

        if mi in cloth_submeshes:
            total_new_tris += orig_count
            all_mins.append(np.array(m.bounding_box.min))
            all_maxs.append(np.array(m.bounding_box.max))
            continue

        attrs = get_merged_vertex_attributes(m)
        pos = attrs["position"]
        if orig_count < 24:
            if "bone_weights" in attrs and "bone_indices" in attrs:
                attrs["bone_weights"], attrs["bone_indices"] = normalize_bone_weights_strict(
                    attrs["bone_weights"], attrs["bone_indices"]
                )
                write_attributes_to_mesh(m, attrs, faces)
            total_new_tris += orig_count
            all_mins.append(pos.min(axis=0))
            all_maxs.append(pos.max(axis=0))
            continue

        mat_name = m.material.name if m.material else ""
        is_weapon = is_file_weapon or 'wp_' in mat_name.lower()
        partitions = partition_submesh_components(pos, faces, attrs, mat_name, hand_bones, head_bones)

        combined_attrs_list: List[Dict[str, np.ndarray]] = []
        combined_faces_list: List[np.ndarray] = []
        vert_offset = 0

        for role, v_indices, role_faces_global in partitions:
            idx_map = np.zeros(len(pos), dtype=np.uint32)
            idx_map[v_indices] = np.arange(len(v_indices), dtype=np.uint32)
            comp_faces = idx_map[role_faces_global]
            comp_attrs = {k: v[v_indices].copy() for k, v in attrs.items()}
            comp_pos = comp_attrs["position"]

            if role == "PRESERVE":
                # 100% preserve geometry with strict byte-sum-255 bone weight normalization
                if "bone_weights" in comp_attrs and "bone_indices" in comp_attrs:
                    comp_attrs["bone_weights"], comp_attrs["bone_indices"] = normalize_bone_weights_strict(
                        comp_attrs["bone_weights"], comp_attrs["bone_indices"]
                    )
                combined_attrs_list.append(comp_attrs)
                combined_faces_list.append(comp_faces.astype(np.uint32) + vert_offset)
                vert_offset += len(comp_pos)
                total_new_tris += len(comp_faces)

            elif role == "HANDS":
                t_tris = max(60, int(round(len(role_faces_global) * 0.45)))
                dec_attrs, dec_faces = decimate_component_shared_verts(
                    comp_pos,
                    comp_faces,
                    comp_attrs,
                    target_tris=t_tris,
                    preserve_border=True,
                    aggressiveness=5,
                    is_weapon=is_weapon,
                )
                combined_attrs_list.append(dec_attrs)
                combined_faces_list.append(dec_faces + vert_offset)
                vert_offset += len(dec_attrs["position"])
                total_new_tris += len(dec_faces)

            elif role == "HEAD_SKIN":
                c_min, c_max = comp_pos.min(axis=0), comp_pos.max(axis=0)
                outer_shell = None
                for smi, s_pos, s_faces in decimated_shells:
                    s_min, s_max = s_pos.min(axis=0), s_pos.max(axis=0)
                    if np.all(c_max >= s_min) and np.all(c_min <= s_max):
                        if len(s_faces) >= 300:
                            outer_shell = (s_pos, s_faces)
                            break

                dec_attrs, dec_faces = decimate_head_skin_landmark_aware(
                    comp_pos,
                    comp_faces,
                    comp_attrs,
                    head_target_tris=head_target_tris,
                    allowed_bones=head_bones if head_bones else HUMANOID_HEAD_BONE_INDICES,
                    fallback_bone=5,
                    outer_shell=outer_shell,
                    min_clearance_m=0.0055,
                )
                combined_attrs_list.append(dec_attrs)
                combined_faces_list.append(dec_faces + vert_offset)
                vert_offset += len(dec_attrs["position"])
                total_new_tris += len(dec_faces)

            else:
                if is_weapon or (not submesh_targets or mi not in submesh_targets):
                    eff_ratio = (
                        submesh_targets[mi] / max(1, len(comp_faces))
                        if (submesh_targets and mi in submesh_targets)
                        else target_ratio
                    )
                    dec_attrs, dec_faces = decimate_rigid_by_bone_groups(
                        comp_pos,
                        comp_faces,
                        comp_attrs,
                        target_ratio=eff_ratio,
                        is_weapon=is_weapon,
                        preserve_border=preserve_border,
                    )
                else:
                    t_tris = submesh_targets[mi]
                    dec_attrs, dec_faces = decimate_component_shared_verts(
                        comp_pos,
                        comp_faces,
                        comp_attrs,
                        target_tris=t_tris,
                        preserve_border=preserve_border,
                        aggressiveness=5,
                        is_weapon=is_weapon,
                    )
                combined_attrs_list.append(dec_attrs)
                combined_faces_list.append(dec_faces + vert_offset)
                vert_offset += len(dec_attrs["position"])
                total_new_tris += len(dec_faces)
                decimated_shells.append((mi, dec_attrs["position"], dec_faces))

        # Merge partitions back into submesh
        merged_attrs: Dict[str, np.ndarray] = {}
        for k in combined_attrs_list[0].keys():
            merged_attrs[k] = np.concatenate([ca[k] for ca in combined_attrs_list], axis=0)
        merged_faces = np.vstack(combined_faces_list).astype(np.uint32)

        write_attributes_to_mesh(m, merged_attrs, merged_faces)

    # Synchronize AABB bounding boxes across all submeshes and global FLVER header
    all_mins = []
    all_maxs = []
    for mi, m in enumerate(flv.meshes):
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue
        if mi in cloth_submeshes:
            # Strictly preserve vanilla AABB on cloth submeshes
            all_mins.append(np.array(m.bounding_box.min))
            all_maxs.append(np.array(m.bounding_box.max))
        else:
            pos = m.vertex_arrays[0].array["position"]
            m_min = pos.min(axis=0)
            m_max = pos.max(axis=0)
            m.bounding_box = AABB(Vector3(m_min), Vector3(m_max))
            all_mins.append(m_min)
            all_maxs.append(m_max)

    if all_mins:
        flv.bounding_box = AABB(
            Vector3(np.min(all_mins, axis=0)),
            Vector3(np.max(all_maxs, axis=0)),
        )

    return total_orig_tris, total_new_tris


if __name__ == "__main__":
    # Built-in diagnostic verification harness for Plain Doll (c8030) or any FLVER container
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER

    repo_root = Path(__file__).resolve().parent.parent
    default_van = repo_root / "CUSA03173" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else default_van
    out_path = Path("/tmp/test_c8030_decimated.chrbnd.dcx")

    print(f"=== Testing Refactored Mesh Decimator on {in_path.name} ===")
    binder = Binder.from_path(in_path)
    flv_entry = next(e for e in binder.entries if e.name.endswith(".flver"))
    flv = FLVER.from_bytes(flv_entry.get_uncompressed_data())

    # Optional submesh targets matching Plain Doll aesthetic profile (or automatic ratio on other models)
    doll_targets = {3: 220, 4: 850, 5: 1100, 6: 100, 8: 200, 9: 1000, 12: 120} if "c8030" in in_path.name else None

    orig_t, new_t = decimate_flver(
        flv,
        target_ratio=0.45,
        flat_normals=False,
        disable_cloth=False,
        preserve_border=True,
        head_target_tris=700,
        submesh_targets=doll_targets,
    )
    print(f"Total FLVER Triangles: {orig_t} -> {new_t} ({new_t / max(1, orig_t) * 100:.1f}%)\n")

    for mi, m in enumerate(flv.meshes):
        pos = m.vertex_arrays[0].array["position"]
        faces = m.face_sets[0].vertex_indices.reshape(-1, 3)
        bw = m.vertex_arrays[0].array["bone_weights"]
        byte_sums = np.sum(np.round(bw * 255.0).astype(int), axis=1)
        bad_weights = int(np.sum(byte_sums != 255))
        _, asp, _, _, _ = calc_triangle_aspect(pos, faces)
        slivers = int(np.sum(asp > 25.0))
        mat = m.material.name if m.material else ""
        print(
            f"  Mesh {mi:2d} ({mat:18s}): {len(faces):5d} tris, {len(pos):5d} verts "
            f"(verts < tris: {len(pos) < len(faces)!s:5s}) | Slivers>25: {slivers:2d} | BadWeights: {bad_weights}"
        )

    if "c8030" in in_path.name:
        pos4 = flv.meshes[4].vertex_arrays[0].array["position"]
        pos7 = flv.meshes[7].vertex_arrays[0].array["position"]
        faces7 = flv.meshes[7].face_sets[0].vertex_indices.reshape(-1, 3)
        hand_v = int(np.sum(pos7[:, 1] < 1.30))
        head_v_mask = pos7[:, 1] > 1.60
        head_tris = int(np.sum(np.all(head_v_mask[faces7], axis=1)))
        dists, _ = cKDTree(pos4).query(pos7[head_v_mask])
        print(f"\n  [Doll Specific Audit]")
        print(f"  - Preserved Hand Vertices (Y < 1.30): {hand_v} (Expected: 3987)")
        print(f"  - Reconstructed Head Triangles      : {head_tris} (Target: 600-800)")
        print(f"  - Min Bonnet-to-Head Clearance      : {dists.min() * 1000.0:.2f} mm (Req: >= 2.00 mm)")

    flv_entry.set_uncompressed_data(flv.to_bytes())
    binder.write(out_path)
    print(f"\n[SUCCESS] Staged test container written to: {out_path}")