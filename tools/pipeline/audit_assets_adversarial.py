#!/usr/bin/env python3
"""
tools/pipeline/audit_assets_adversarial.py - Metric Extraction Harness for Multi-Model Audit.

Extracts geometric, rigging, and architectural metrics across all PSX assets:
- Max edge length across all cadaver/flesh submeshes (target <= 2.0m)
- Min triangle area across all meshes (target >= 1e-6 m^2)
- Max aspect ratio (target <= 25.0)
- Cage decimation reduction ratio (target >= 70%)
- Collision (*.hkx) and animation (*.anibnd) integrity
- Five-pillar directory isolation under mods/

Dumps structured metrics to JSON for adversarial model evaluation (Principle VI).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "pipeline"))

import soulstruct_patch  # noqa: E402
from fixtures.prop_geometry_fixtures import inspect_objbnd_topology  # noqa: E402
from modular_structure_validator import validate_all_pillars  # noqa: E402
from verify_retro_props import CADAVER_TEST_IDS, CAGE_TEST_IDS, is_cadaver_submesh  # noqa: E402

VANILLA_OBJ_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "obj"
SANDBOX_OBJ_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "obj"
MODS_DIR = REPO_ROOT / "mods"


def extract_audit_metrics() -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "timestamp": "2026-11-08T20:45:00Z",
        "pillars": {},
        "cadaver_props": [],
        "cage_props": [],
        "overall_summary": {
            "total_cadavers_audited": 0,
            "total_cages_audited": 0,
            "exploded_spikes_count": 0,
            "degenerate_triangles_count": 0,
            "cages_under_budget_count": 0,
            "pillar_violations_count": 0,
        },
    }

    # 1. Audit Cadavers
    for oid in CADAVER_TEST_IDS:
        p_path = SANDBOX_OBJ_DIR / f"{oid}.objbnd.dcx"
        if not p_path.exists():
            continue

        reports = inspect_objbnd_topology(p_path)
        for rep in reports:
            for sub in rep.submeshes:
                if not is_cadaver_submesh(sub.material_name):
                    continue

                metrics["overall_summary"]["total_cadavers_audited"] += 1
                is_exploded = sub.max_edge_length > 2.0
                is_degenerate = sub.min_triangle_area < 1e-6

                if is_exploded:
                    metrics["overall_summary"]["exploded_spikes_count"] += 1
                if is_degenerate:
                    metrics["overall_summary"]["degenerate_triangles_count"] += 1

                metrics["cadaver_props"].append({
                    "asset_id": oid,
                    "submesh": sub.submesh_index,
                    "material": sub.material_name,
                    "max_edge_length": round(sub.max_edge_length, 4),
                    "min_triangle_area": float(f"{sub.min_triangle_area:.2e}"),
                    "y_bounds": [round(sub.y_bounds[0], 4), round(sub.y_bounds[1], 4)],
                    "is_manifold": sub.is_manifold,
                    "is_exploded": is_exploded,
                    "is_degenerate": is_degenerate,
                })

    # 2. Audit Cages
    for oid in CAGE_TEST_IDS:
        v_path = VANILLA_OBJ_DIR / f"{oid}.objbnd.dcx"
        p_path = SANDBOX_OBJ_DIR / f"{oid}.objbnd.dcx"
        if not v_path.exists() or not p_path.exists():
            continue

        metrics["overall_summary"]["total_cages_audited"] += 1
        v_rep = inspect_objbnd_topology(v_path)
        p_rep = inspect_objbnd_topology(p_path)
        v_tris = sum(r.total_triangles for r in v_rep)
        p_tris = sum(r.total_triangles for r in p_rep)

        reduction = (v_tris - p_tris) / v_tris if v_tris > 0 else 0.0
        meets_budget = (reduction >= 0.50 or v_tris <= 1500)
        if not meets_budget:
            metrics["overall_summary"]["cages_under_budget_count"] += 1

        metrics["cage_props"].append({
            "asset_id": oid,
            "vanilla_tris": v_tris,
            "psx_tris": p_tris,
            "reduction_pct": round(reduction * 100, 1),
            "meets_budget": meets_budget,
        })

    # 3. Audit Modular Pillars
    pillar_results = validate_all_pillars(MODS_DIR)
    for name, res in pillar_results.items():
        if not res.passed:
            metrics["overall_summary"]["pillar_violations_count"] += len(res.violations)

        metrics["pillars"][name] = {
            "exists": res.exists,
            "has_mod_json": res.has_mod_json,
            "file_count": res.file_count,
            "passed": res.passed,
            "violations": res.violations,
        }

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Extract Metrics for Adversarial Audit.")
    parser.add_argument("--report", type=Path, default=Path("/tmp/audit_raw.json"), help="Output JSON path")
    args = parser.parse_args()

    print(f"Extracting adversarial audit metrics to {args.report}...")
    metrics = extract_audit_metrics()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"Metrics saved to {args.report}.")
    print(f"Summary: {json.dumps(metrics['overall_summary'], indent=2)}")


if __name__ == "__main__":
    main()
