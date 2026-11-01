#!/usr/bin/env python3
"""
tools/test_challenger_c8030_stress.py: Empirical Adversarial Challenge Test Harness.

Executes rigorous adversarial stress tests against Plain Doll c8030.chrbnd.dcx:
1. Exhaustive triangle-triangle intersection audit between all triangles of Mesh 4 (bonnet)
   and Mesh 7 head faces (0 intersecting pairs).
2. Minimum distance clearance between Bonnet inner surface and face skin (>= 2.0mm).
3. Degenerate geometry stress check: compute exact areas and aspect ratios for all 314 head
   triangles (zero area < 1e-6, max aspect <= 25.0).
4. Manifold edge check: verify every internal edge is shared by exactly 2 faces,
   boundary edges form closed loops, and 0 non-manifold edges exist.
5. Havok cloth byte-for-byte audit against pristine CUSA03173/dvdroot_ps4/chr/c8030.chrbnd.dcx:
   Meshes 0, 1, 2, 10, 11 vertices and c8030_c.hkx, c8030_c.clm2.
6. Bone weight partition of unity: verify sum w_j == 1.0 within 1e-4 and byte sum == 255
   for 100% of vertices.
"""

import sys
import time
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy.spatial import cKDTree

# Setup paths and environment
REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import soulstruct_patch
from soulstruct.containers import Binder
from soulstruct.flver import FLVER

VANILLA_CHRBND = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"
PSX_CHRBND = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr" / "c8030.chrbnd.dcx"

HEAD_Y_THRESHOLD = 1.60
NECK_SEAM_MAX_Y = 1.82
CLOTH_SUBMESH_INDICES = [0, 1, 2, 10, 11]


def edge_pierces_triangle(e0: np.ndarray, e1: np.ndarray, v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> bool:
    """Möller-Trumbore ray-triangle intersection specialized for finite line segment piercing."""
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


def triangles_pierce(t1: np.ndarray, t2: np.ndarray) -> bool:
    """Exhaustive bidirectional edge-facet piercing test for two triangles in R^3."""
    for i in range(3):
        if edge_pierces_triangle(t1[i], t1[(i + 1) % 3], t2[0], t2[1], t2[2]):
            return True
        if edge_pierces_triangle(t2[i], t2[(i + 1) % 3], t1[0], t1[1], t1[2]):
            return True
    return False


def test_1_exhaustive_triangle_intersections(flv: FLVER) -> dict:
    """Stress Test 1: Exhaustive triangle-triangle intersection audit (Mesh 4 vs Mesh 7 head)."""
    m4 = flv.meshes[4]
    pos4 = m4.vertex_arrays[0].array["position"]
    faces4 = m4.face_sets[0].vertex_indices.reshape(-1, 3)
    tris4 = pos4[faces4]

    m7 = flv.meshes[7]
    pos7 = m7.vertex_arrays[0].array["position"]
    faces7 = m7.face_sets[0].vertex_indices.reshape(-1, 3)
    head_mask = (pos7[faces7[:, 0], 1] > HEAD_Y_THRESHOLD) & \
                (pos7[faces7[:, 1], 1] > HEAD_Y_THRESHOLD) & \
                (pos7[faces7[:, 2], 1] > HEAD_Y_THRESHOLD)
    head_faces7 = faces7[head_mask]
    tris7 = pos7[head_faces7]

    total_possible_pairs = len(tris4) * len(tris7)
    min4, max4 = tris4.min(axis=1), tris4.max(axis=1)
    min7, max7 = tris7.min(axis=1), tris7.max(axis=1)

    intersecting_pairs = []
    candidate_pairs_checked = 0

    for i in range(len(tris7)):
        mask = np.all(max4 >= min7[i], axis=1) & np.all(min4 <= max7[i], axis=1)
        cands = np.where(mask)[0]
        for ci in cands:
            candidate_pairs_checked += 1
            if triangles_pierce(tris7[i], tris4[ci]):
                intersecting_pairs.append((i, ci))

    passed = (len(intersecting_pairs) == 0)
    return {
        "name": "Exhaustive Triangle-Triangle Intersection Audit",
        "passed": passed,
        "total_pairs_space": total_possible_pairs,
        "candidate_pairs_checked": candidate_pairs_checked,
        "intersecting_pairs_count": len(intersecting_pairs),
        "intersecting_pairs": intersecting_pairs,
    }


def test_2_minimum_distance_clearance(flv: FLVER) -> dict:
    """Stress Test 2: Minimum distance clearance between Bonnet inner surface and face skin."""
    m4 = flv.meshes[4]
    pos4 = m4.vertex_arrays[0].array["position"]

    m7 = flv.meshes[7]
    pos7 = m7.vertex_arrays[0].array["position"]
    head_mask = pos7[:, 1] > HEAD_Y_THRESHOLD
    head_pos7 = pos7[head_mask]

    # Global head vertex-to-vertex clearance against Mesh 4
    tree4 = cKDTree(pos4)
    dists_all, _ = tree4.query(head_pos7)
    min_clearance_all_mm = float(dists_all.min()) * 1000.0

    # Face skin specific clearance (Z > 0.02, Y > 1.80)
    face_skin_mask = (head_pos7[:, 2] > 0.02) & (head_pos7[:, 1] > 1.80)
    face_skin_pos = head_pos7[face_skin_mask]
    dists_face, _ = tree4.query(face_skin_pos)
    min_clearance_face_mm = float(dists_face.min()) * 1000.0

    # Bonnet hood/brim specific clearance (bonnet vertices at Y > 1.85, Z > 0.05)
    bonnet_hood_mask = (pos4[:, 1] > 1.85) & (pos4[:, 2] > 0.05)
    bonnet_hood_pos = pos4[bonnet_hood_mask]
    tree_hood = cKDTree(bonnet_hood_pos)
    dists_hood, _ = tree_hood.query(head_pos7)
    min_clearance_hood_mm = float(dists_hood.min()) * 1000.0

    passed = (min_clearance_all_mm >= 2.0)
    return {
        "name": "Minimum Distance Clearance Audit",
        "passed": passed,
        "min_clearance_mesh4_all_mm": min_clearance_all_mm,
        "min_clearance_face_skin_mm": min_clearance_face_mm,
        "min_clearance_bonnet_hood_mm": min_clearance_hood_mm,
        "threshold_mm": 2.0,
    }


def test_3_degenerate_geometry_stress_check(flv: FLVER) -> dict:
    """Stress Test 3: Exact areas and aspect ratios for all 314 head triangles."""
    m7 = flv.meshes[7]
    pos7 = m7.vertex_arrays[0].array["position"]
    faces7 = m7.face_sets[0].vertex_indices.reshape(-1, 3)
    head_mask = (pos7[faces7[:, 0], 1] > HEAD_Y_THRESHOLD) & \
                (pos7[faces7[:, 1], 1] > HEAD_Y_THRESHOLD) & \
                (pos7[faces7[:, 2], 1] > HEAD_Y_THRESHOLD)
    head_faces7 = faces7[head_mask]

    v0 = pos7[head_faces7[:, 0]]
    v1 = pos7[head_faces7[:, 1]]
    v2 = pos7[head_faces7[:, 2]]

    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)

    e1 = np.linalg.norm(v1 - v0, axis=1)
    e2 = np.linalg.norm(v2 - v1, axis=1)
    e3 = np.linalg.norm(v0 - v2, axis=1)
    s = (e1 + e2 + e3) / 2.0

    aspect = (e1 * e2 * e3 * s) / (8.0 * (areas ** 2))

    zero_area_count = int(np.count_nonzero(areas < 1e-6))
    sliver_count = int(np.count_nonzero(aspect > 25.0))
    passed = (len(head_faces7) == 314 and zero_area_count == 0 and sliver_count == 0)

    return {
        "name": "Degenerate Geometry Stress Check",
        "passed": passed,
        "total_head_triangles": len(head_faces7),
        "min_area": float(areas.min()),
        "max_area": float(areas.max()),
        "zero_area_count": zero_area_count,
        "min_aspect_ratio": float(aspect.min()),
        "max_aspect_ratio": float(aspect.max()),
        "sliver_count": sliver_count,
    }


def test_4_manifold_edge_check(flv: FLVER) -> dict:
    """Stress Test 4: Manifold edge check, internal edge share == 2, closed boundary loop."""
    m7 = flv.meshes[7]
    pos7 = m7.vertex_arrays[0].array["position"]
    faces7 = m7.face_sets[0].vertex_indices.reshape(-1, 3)
    head_mask = (pos7[faces7[:, 0], 1] > HEAD_Y_THRESHOLD) & \
                (pos7[faces7[:, 1], 1] > HEAD_Y_THRESHOLD) & \
                (pos7[faces7[:, 2], 1] > HEAD_Y_THRESHOLD)
    head_faces7 = faces7[head_mask]

    grid = np.round(pos7 * 10000).astype(np.int64)
    unique_pts, unique_inv = np.unique(grid, axis=0, return_inverse=True)
    spatial_faces = unique_inv[head_faces7]

    edge_to_faces = defaultdict(list)
    for fi, f in enumerate(spatial_faces):
        edges = [
            tuple(sorted((int(f[0]), int(f[1])))),
            tuple(sorted((int(f[1]), int(f[2])))),
            tuple(sorted((int(f[2]), int(f[0])))),
        ]
        for e in edges:
            edge_to_faces[e].append(fi)

    counts = defaultdict(int)
    for e, fl in edge_to_faces.items():
        counts[len(fl)] += 1

    non_manifold_edges = [e for e, fl in edge_to_faces.items() if len(fl) > 2]
    boundary_edges = [e for e, fl in edge_to_faces.items() if len(fl) == 1]
    internal_edges = [e for e, fl in edge_to_faces.items() if len(fl) == 2]

    # Verify boundary graph forms 2-regular closed cycle
    boundary_adj = defaultdict(list)
    for u, v in boundary_edges:
        boundary_adj[u].append(v)
        boundary_adj[v].append(u)

    vert_degrees = {v: len(nbrs) for v, nbrs in boundary_adj.items()}
    all_deg_2 = all(deg == 2 for deg in vert_degrees.values()) if vert_degrees else False

    # Check loop closure
    visited = set()
    loops = []
    for start_node in boundary_adj:
        if start_node in visited:
            continue
        loop = [start_node]
        visited.add(start_node)
        curr = start_node
        prev = None
        is_closed = False
        while True:
            nbrs = [n for n in boundary_adj[curr] if n != prev]
            if not nbrs:
                break
            nxt = nbrs[0]
            if nxt == start_node:
                is_closed = True
                break
            if nxt in visited:
                break
            visited.add(nxt)
            loop.append(nxt)
            prev = curr
            curr = nxt
        loops.append((loop, is_closed))

    neck_seam_closed = (len(loops) == 1 and loops[0][1] is True)
    passed = (len(non_manifold_edges) == 0 and all_deg_2 and neck_seam_closed)

    return {
        "name": "Manifold Edge and Boundary Loop Check",
        "passed": passed,
        "internal_edges_count": len(internal_edges),
        "boundary_edges_count": len(boundary_edges),
        "non_manifold_edges_count": len(non_manifold_edges),
        "boundary_loops_count": len(loops),
        "loop_lengths": [len(lp[0]) for lp in loops],
        "loop_closed": [lp[1] for lp in loops],
        "boundary_all_degree_2": all_deg_2,
    }


def test_5_havok_cloth_byte_for_byte(b_psx: Binder, b_van: Binder) -> dict:
    """Stress Test 5: Havok cloth byte-for-byte audit against pristine baseline."""
    van_entries = {e.name.replace('/', '\\').split('\\')[-1]: e for e in b_van.entries}
    psx_entries = {e.name.replace('/', '\\').split('\\')[-1]: e for e in b_psx.entries}

    sim_files = ["c8030_c.hkx", "c8030_c.clm2"]
    sim_matches = {}
    for sf in sim_files:
        d_v = van_entries[sf].get_uncompressed_data()
        d_p = psx_entries[sf].get_uncompressed_data()
        sim_matches[sf] = (d_v == d_p)

    flv_v = FLVER.from_bytes(van_entries["c8030.flver"].get_uncompressed_data())
    flv_p = FLVER.from_bytes(psx_entries["c8030.flver"].get_uncompressed_data())

    mesh_matches = {}
    for ci in CLOTH_SUBMESH_INDICES:
        m_v = flv_v.meshes[ci]
        m_p = flv_p.meshes[ci]
        va_v = m_v.vertex_arrays[0].array.tobytes()
        va_p = m_p.vertex_arrays[0].array.tobytes()
        fs_v = m_v.face_sets[0].vertex_indices
        fs_p = m_p.face_sets[0].vertex_indices
        mesh_matches[ci] = {
            "vertex_bytes_equal": (va_v == va_p),
            "face_indices_equal": np.array_equal(fs_v, fs_p),
        }

    all_sim_match = all(sim_matches.values())
    all_meshes_match = all(m["vertex_bytes_equal"] and m["face_indices_equal"] for m in mesh_matches.values())
    passed = all_sim_match and all_meshes_match

    return {
        "name": "Havok Cloth Byte-for-Byte Audit",
        "passed": passed,
        "sim_files": sim_matches,
        "cloth_meshes": mesh_matches,
    }


def test_6_bone_weight_partition_of_unity(flv: FLVER) -> dict:
    """Stress Test 6: Bone weight partition of unity (sum == 1.0 within 1e-4, byte sum == 255)."""
    m7 = flv.meshes[7]
    pos7 = m7.vertex_arrays[0].array["position"]
    weights7 = m7.vertex_arrays[0].array["bone_weights"]

    head_mask = pos7[:, 1] > HEAD_Y_THRESHOLD
    head_bw = weights7[head_mask]
    head_float_sums = np.sum(head_bw, axis=1)
    head_float_bad = int(np.count_nonzero(np.abs(head_float_sums - 1.0) >= 1e-4))
    head_byte_sums = np.round(head_bw * 255.0).astype(int).sum(axis=1)
    head_byte_bad = int(np.count_nonzero(head_byte_sums != 255))
    head_max_float_err = float(np.max(np.abs(head_float_sums - 1.0)))

    # Entire Mesh 7 (including hands)
    all_float_sums = np.sum(weights7, axis=1)
    all_float_bad = int(np.count_nonzero(np.abs(all_float_sums - 1.0) >= 1e-4))
    all_byte_sums = np.round(weights7 * 255.0).astype(int).sum(axis=1)
    all_byte_bad = int(np.count_nonzero(all_byte_sums != 255))
    all_max_float_err = float(np.max(np.abs(all_float_sums - 1.0)))

    passed = (head_float_bad == 0 and head_byte_bad == 0 and all_float_bad == 0 and all_byte_bad == 0)

    return {
        "name": "Bone Weight Partition of Unity Audit",
        "passed": passed,
        "head_vertex_count": len(head_bw),
        "head_float_violations_1e4": head_float_bad,
        "head_byte_violations_255": head_byte_bad,
        "head_max_float_deviation": head_max_float_err,
        "total_mesh7_vertex_count": len(weights7),
        "total_float_violations_1e4": all_float_bad,
        "total_byte_violations_255": all_byte_bad,
        "total_max_float_deviation": all_max_float_err,
    }


def main():
    print("=" * 80)
    print(">>> EMPIRICAL CHALLENGER: PLAIN DOLL (c8030) ADVERSARIAL STRESS SUITE <<<")
    print("=" * 80)

    b_van = Binder.from_path(VANILLA_CHRBND)
    b_psx = Binder.from_path(PSX_CHRBND)

    flv_psx = FLVER.from_bytes(next(e for e in b_psx.entries if e.name.endswith(".flver")).get_uncompressed_data())

    tests = [
        ("Test 1: Triangle Intersections", lambda: test_1_exhaustive_triangle_intersections(flv_psx)),
        ("Test 2: Clearance & Anti-Penetration", lambda: test_2_minimum_distance_clearance(flv_psx)),
        ("Test 3: Degenerate Geometry Filter", lambda: test_3_degenerate_geometry_stress_check(flv_psx)),
        ("Test 4: 2-Manifold Edge Topology", lambda: test_4_manifold_edge_check(flv_psx)),
        ("Test 5: Havok Cloth Byte Preservation", lambda: test_5_havok_cloth_byte_for_byte(b_psx, b_van)),
        ("Test 6: Bone Weight Unity Partition", lambda: test_6_bone_weight_partition_of_unity(flv_psx)),
    ]

    all_passed = True
    for title, test_fn in tests:
        t0 = time.time()
        res = test_fn()
        dt = time.time() - t0
        status_str = "[PASS]" if res["passed"] else "[FAIL]"
        print(f"\n{status_str} {title} ({dt:.3f}s)")
        for k, v in res.items():
            if k not in ("name", "passed"):
                print(f"    {k}: {v}")
        if not res["passed"]:
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("FINAL CHALLENGER VERDICT: CONFIRM (6/6 STRESS TESTS PASSED)")
        print("=" * 80)
        sys.exit(0)
    else:
        print("FINAL CHALLENGER VERDICT: FAIL")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
