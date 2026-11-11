#!/usr/bin/env python3
"""
tools/pipeline/bone_transform_utils.py - Model-Space Bone Hierarchy Accumulator.

Implements exact FromSoftware bone hierarchy accumulation and bounding box derivation
per Section 29 of BB_PSX_DEMAKE_MATH_AND_FINDINGS.md:
  M_i = M_parent(i) * M_local,i
Accumulates bone matrices using FromSoftware XZY Euler rotation order,
recomputes submesh world-space coordinates, and updates mesh and flver AABBs.
"""

from typing import List, Tuple
import numpy as np
from soulstruct.utilities.maths import Vector3


def euler_xzy_to_rotation_matrix(rot: Tuple[float, float, float]) -> np.ndarray:
    """
    Constructs a 3x3 rotation matrix using FromSoftware Euler convention:
    rotations applied in order X, then Z, then Y: R = Ry * Rz * Rx.
    """
    rx, ry, rz = rot[0], rot[1], rot[2]

    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)

    Rx = np.array([
        [1.0, 0.0, 0.0],
        [0.0, cx, -sx],
        [0.0, sx, cx],
    ], dtype=np.float64)

    Ry = np.array([
        [cy, 0.0, sy],
        [0.0, 1.0, 0.0],
        [-sy, 0.0, cy],
    ], dtype=np.float64)

    Rz = np.array([
        [cz, -sz, 0.0],
        [sz, cz, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)

    return Ry @ Rz @ Rx


def compute_bone_world_matrices(bones) -> List[np.ndarray]:
    """
    Computes 4x4 world transformation matrix for every bone in FLVER skeleton.
    M_i = M_parent(i) * M_local(i).
    """
    num_bones = len(bones)
    world_matrices = [np.eye(4, dtype=np.float64) for _ in range(num_bones)]

    for bi, b in enumerate(bones):
        rot = (float(b.rotate.x), float(b.rotate.y), float(b.rotate.z))
        R = euler_xzy_to_rotation_matrix(rot)

        scale = np.array([float(b.scale.x), float(b.scale.y), float(b.scale.z)], dtype=np.float64)
        RS = R * scale  # column scaling

        trans = np.array([float(b.translate.x), float(b.translate.y), float(b.translate.z)], dtype=np.float64)

        M_local = np.eye(4, dtype=np.float64)
        M_local[:3, :3] = RS
        M_local[:3, 3] = trans

        parent_idx = int(b.parent_bone_index)
        if parent_idx >= 0 and parent_idx < num_bones:
            world_matrices[bi] = world_matrices[parent_idx] @ M_local
        else:
            world_matrices[bi] = M_local

    return world_matrices


def update_flver_bounding_boxes(flv):
    """
    Updates mesh.bounding_box and flver.bounding_box for all submeshes
    using accumulated bone hierarchy matrices.
    """
    if not flv.bones:
        return

    world_matrices = compute_bone_world_matrices(flv.bones)

    overall_min = np.array([float("inf"), float("inf"), float("inf")], dtype=np.float32)
    overall_max = np.array([float("-inf"), float("-inf"), float("-inf")], dtype=np.float32)

    for m in flv.meshes:
        if not m.vertex_arrays or len(m.vertex_arrays[0].array) == 0:
            continue

        pos_local = m.vertex_arrays[0].array["position"].astype(np.float64)
        has_skin = "bone_indices" in (m.vertex_arrays[0].array.dtype.names or ())

        if has_skin:
            pos_world = pos_local
        else:
            def_bone = int(m.default_bone_index)
            if 0 <= def_bone < len(world_matrices):
                M = world_matrices[def_bone]
                R = M[:3, :3]
                T = M[:3, 3]
                # P_world = P_local * R^T + T
                pos_world = (pos_local @ R.T) + T
            else:
                pos_world = pos_local

        sub_min = pos_world.min(axis=0).astype(np.float32)
        sub_max = pos_world.max(axis=0).astype(np.float32)

        m.bounding_box.min = Vector3(tuple(sub_min))
        m.bounding_box.max = Vector3(tuple(sub_max))

        overall_min = np.minimum(overall_min, sub_min)
        overall_max = np.maximum(overall_max, sub_max)

    if not np.isinf(overall_min[0]):
        flv.bounding_box.min = Vector3(tuple(overall_min))
        flv.bounding_box.max = Vector3(tuple(overall_max))
