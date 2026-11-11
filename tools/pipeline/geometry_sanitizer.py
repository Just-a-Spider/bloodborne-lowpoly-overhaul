#!/usr/bin/env python3
"""
tools/pipeline/geometry_sanitizer.py - Geometry and Topology Sanity Validator.

Enforces Constitution Principle III & IV invariants on FLVER models:
- Cull zero-area degenerate triangles (Area < 1e-6 m^2)
- Cull needle slivers with aspect ratio rho > 25.0
- Restrict maximum edge length to <= 2.0m (eliminates exploded vertex spikes)
- Synchronize auxiliary FaceSets: FS1..FS5 = FS0.copy()
- Validate skeletal bone index bounds: [0, 205]
- Clamp submesh ground coordinates: Y_min >= -0.05m
"""

from typing import List, Optional, Tuple
import numpy as np


def weld_submesh_vertices(
    verts: np.ndarray,
    faces: np.ndarray,
    tolerance_decimals: int = 4,
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Welds coincident vertices (V < T) to maintain manifold surface topology
    and eliminate duplicate vertex explosions from flat shading exporters.
    Returns (welded_verts, remapped_faces, reduction_count).
    """
    if len(faces) == 0 or len(verts) == 0:
        return verts, faces, 0

    orig_v_count = len(verts)
    pos = verts["position"]
    rounded_pos = np.round(pos, decimals=tolerance_decimals)

    # Find unique positions
    _, unique_indices, inverse_indices = np.unique(
        rounded_pos, axis=0, return_index=True, return_inverse=True
    )

    if len(unique_indices) >= orig_v_count:
        return verts, faces, 0

    welded_verts = verts[unique_indices].copy()
    remapped_faces = inverse_indices[faces.reshape(-1, 3)].copy()
    reduction = orig_v_count - len(welded_verts)

    return welded_verts, remapped_faces, reduction


def sanitize_submesh_geometry(
    verts: np.ndarray,
    faces: np.ndarray,
    max_edge_limit: float = 50.0,
    min_area_limit: float = 1e-6,
    max_aspect_limit: float = 25.0,
    ground_clamp_y: Optional[float] = None,
    weld_vertices: bool = True,
) -> Tuple[np.ndarray, np.ndarray, int, int]:
    """
    Sanitizes submesh vertices and triangles.
    Returns (cleaned_verts, cleaned_faces, culled_degenerates, culled_spikes).
    """
    if len(faces) == 0 or len(verts) == 0:
        return verts, faces, 0, 0

    faces = faces.reshape(-1, 3)

    # 1. Weld coincident duplicate vertices if vertex count is bloated
    if weld_vertices and len(verts) > len(faces):
        verts, faces, _ = weld_submesh_vertices(verts, faces)

    pos = verts["position"]

    # 1. Ground clamping: clamp negative height if below limit BEFORE area/edge checks
    if ground_clamp_y is not None:
        y_coords = pos[:, 1]
        below_ground = y_coords < ground_clamp_y
        if np.any(below_ground):
            pos[:, 1] = np.maximum(pos[:, 1], ground_clamp_y)
            verts["position"] = pos

    # 2. Edge length calculation
    v0, v1, v2 = pos[faces[:, 0]], pos[faces[:, 1]], pos[faces[:, 2]]
    e0 = np.linalg.norm(v1 - v0, axis=1)
    e1 = np.linalg.norm(v2 - v1, axis=1)
    e2 = np.linalg.norm(v0 - v2, axis=1)
    max_edges = np.maximum(np.maximum(e0, e1), e2)

    # 3. Area calculation
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)

    # 4. Aspect ratio calculation
    s = 0.5 * (e0 + e1 + e2)
    denom = 8.0 * (s - e0) * (s - e1) * (s - e2)
    safe_denom = np.where(denom > 1e-12, denom, 1e-12)
    aspect = (e0 * e1 * e2) / safe_denom

    # Valid mask
    valid_spike = (max_edges <= max_edge_limit)
    valid_area = (areas >= min_area_limit)
    valid_aspect = (aspect <= max_aspect_limit)

    culled_spikes = int(np.sum(~valid_spike))
    culled_degenerates = int(np.sum(~valid_area | ~valid_aspect))

    keep_mask = valid_spike & valid_area & valid_aspect

    if not np.all(keep_mask):
        faces = faces[keep_mask]

    return verts, faces.reshape(-1, 3).astype(np.uint32), culled_degenerates, culled_spikes


def synchronize_flver_facesets(flv) -> int:
    """
    Synchronizes FLVER auxiliary FaceSets (FS1..FS5 = FS0.copy()) per Principle III.
    Returns number of synchronized facesets.
    """
    sync_count = 0
    for m in flv.meshes:
        if len(m.face_sets) > 1 and len(m.face_sets[0].vertex_indices) > 0:
            fs0_indices = m.face_sets[0].vertex_indices.copy()
            for fsi in range(1, len(m.face_sets)):
                m.face_sets[fsi].vertex_indices = fs0_indices.copy()
                sync_count += 1
    return sync_count


def validate_flver_bone_bounds(flv, max_bone_index: int = 205) -> Tuple[bool, List[str]]:
    """
    Validates all mesh default_bone_index and vertex bone_indices <= max_bone_index.
    """
    errors = []
    for mi, m in enumerate(flv.meshes):
        if m.default_bone_index > max_bone_index:
            errors.append(f"Mesh {mi} default_bone_index={m.default_bone_index} exceeds {max_bone_index}")
        if m.vertex_arrays:
            array = m.vertex_arrays[0].array
            if "bone_indices" in (array.dtype.names or ()):
                b_indices = array["bone_indices"]
                if np.any(b_indices > max_bone_index):
                    max_found = int(b_indices.max())
                    errors.append(f"Mesh {mi} bone_indices max={max_found} exceeds {max_bone_index}")
    return len(errors) == 0, errors
