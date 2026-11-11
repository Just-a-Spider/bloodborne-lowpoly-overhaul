#!/usr/bin/env python3
"""
Prop Geometry Fixture & Topology Snapshot Helper.
Provides utilities to inspect, record, and compare FLVER topology before and after demake passes.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

import sys
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import soulstruct_patch  # noqa: E402
from soulstruct.containers import Binder  # noqa: E402
from soulstruct.flver.core import FLVER  # noqa: E402


@dataclass
class SubmeshTopologySnapshot:
    submesh_index: int
    material_name: str
    default_bone_index: int
    vertex_count: int
    triangle_count: int
    max_edge_length: float
    min_triangle_area: float
    max_aspect_ratio: float
    y_bounds: Tuple[float, float]
    has_skin: bool
    is_manifold: bool


@dataclass
class PropTopologyReport:
    asset_id: str
    flver_name: str
    bones_count: int
    submeshes: List[SubmeshTopologySnapshot] = field(default_factory=list)

    @property
    def total_triangles(self) -> int:
        return sum(s.triangle_count for s in self.submeshes)

    @property
    def max_edge_overall(self) -> float:
        return max((s.max_edge_length for s in self.submeshes), default=0.0)


def inspect_flver_topology(flv: FLVER, asset_id: str = "", flver_name: str = "") -> PropTopologyReport:
    report = PropTopologyReport(asset_id=asset_id, flver_name=flver_name, bones_count=len(flv.bones))

    for mi, m in enumerate(flv.meshes):
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue

        verts = m.vertex_arrays[0].array["position"]
        faces = m.face_sets[0].vertex_indices.reshape(-1, 3)
        v_count = len(verts)
        t_count = len(faces)
        if t_count == 0 or v_count == 0:
            continue

        v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
        e0 = np.linalg.norm(v1 - v0, axis=1)
        e1 = np.linalg.norm(v2 - v1, axis=1)
        e2 = np.linalg.norm(v0 - v2, axis=1)
        max_edge = float(np.maximum(np.maximum(e0, e1), e2).max())

        cross = np.cross(v1 - v0, v2 - v0)
        areas = 0.5 * np.linalg.norm(cross, axis=1)
        min_area = float(areas.min()) if len(areas) > 0 else 0.0

        # Aspect ratio: product of sides / (8 * (s-a)*(s-b)*(s-c))
        s = 0.5 * (e0 + e1 + e2)
        denom = 8.0 * (s - e0) * (s - e1) * (s - e2)
        safe_denom = np.where(denom > 1e-12, denom, 1e-12)
        aspect = (e0 * e1 * e2) / safe_denom
        max_aspect = float(aspect.max()) if len(aspect) > 0 else 1.0

        y_min = float(verts[:, 1].min())
        y_max = float(verts[:, 1].max())

        dtype_names = m.vertex_arrays[0].array.dtype.names or ()
        has_skin = "bone_indices" in dtype_names

        snapshot = SubmeshTopologySnapshot(
            submesh_index=mi,
            material_name=m.material.name if m.material else f"Submesh_{mi}",
            default_bone_index=m.default_bone_index,
            vertex_count=v_count,
            triangle_count=t_count,
            max_edge_length=max_edge,
            min_triangle_area=min_area,
            max_aspect_ratio=max_aspect,
            y_bounds=(y_min, y_max),
            has_skin=has_skin,
            is_manifold=(v_count <= t_count * 3),
        )
        report.submeshes.append(snapshot)

    return report


def inspect_objbnd_topology(path: Path) -> List[PropTopologyReport]:
    b = Binder.from_path(str(path))
    reports = []
    for e in b.entries:
        if e.name.lower().endswith(".flver") and len(e.get_uncompressed_data()) > 0x100:
            flv = FLVER.from_bytes(e.get_uncompressed_data())
            rep = inspect_flver_topology(flv, asset_id=path.stem.split(".")[0], flver_name=Path(e.name).name)
            reports.append(rep)
    return reports
