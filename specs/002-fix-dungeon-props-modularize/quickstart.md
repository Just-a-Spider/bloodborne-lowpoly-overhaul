# Quickstart: Dungeon Props Fix & Modular Mod Validation

**Feature**: `002-fix-dungeon-props-modularize`  
**Purpose**: Run-through guide for testing dungeon cage demakes, cadaver waste stabilization, 5-pillar modular packaging, and multi-model audit sign-off.

---

## 1. Prerequisites

- Python 3.11+ running via `uv run python ...`
- Pristine base game at `CUSA03173/` (read-only)
- Mod staging directory at `CUSA03173-PSX/`

---

## 2. Validation Scenarios

### Scenario 1: Stabilize & Demake Exploded Cadaver Wastes (User Story 1)
```bash
# Run stabilization pass on corpse heaps and cadavers
uv run python tools/pipeline/batch_blender_demake_obj.py --only 'o29721*' --deploy
uv run python tools/pipeline/batch_blender_demake_obj.py --only 'o29850*' --deploy
uv run python tools/pipeline/batch_blender_demake_obj.py --only 'o29025*' --deploy

# Verify absence of exploded triangles (max edge <= 2.0m)
uv run python tools/verify_retro_props.py --check-cadavers
```
**Expected Outcome**: 0 meshes with edge $> 2.0$m, all vertices ground-locked, exit code 0.

---

### Scenario 2: Demake Regular & Deformed Dungeon Cages (User Story 2)
```bash
# Process Chalice and Mensis cages with flat facet shading
uv run python tools/pipeline/batch_blender_demake_obj.py --only 'o29020*' --deploy
uv run python tools/pipeline/batch_blender_demake_obj.py --only 'o32205*' --deploy
uv run python tools/pipeline/batch_blender_demake_obj.py --only 'o29000*' --deploy

# Verify cage decimation and facet shading
uv run python tools/verify_retro_props.py --check-cages
```
**Expected Outcome**: All cage assemblies reduced by $\ge 70\%$, flat normal facet shading confirmed, animations and collision preserved, exit code 0.

---

### Scenario 3: Package Five Modular Mod Pillars (User Story 3)
```bash
# Package all 5 pillars to mods/
uv run python tools/pipeline/package_modular_mods.py --pillar all --clean

# Verify directory isolation and manifests
uv run python tools/verify_modular_mods.py
```
**Expected Outcome**:
- 5 distinct directories in `mods/` (`Bloodborne Retro Maps`, `Bloodborne Retro Props and Objects`, `Bloodborne Retro Armors and Weapons - Cloth Physics` / `- Flat Stiff`, `Bloodborne Retro Characters`, `Bloodborne Retro HUD and UI`).
- Zero path cross-contamination.
- Each directory contains valid `mod.json`.
- Exit code 0.

---

### Scenario 4: Multi-Model Independent Audit (User Story 4 / Principle VI)
```bash
# Extract raw metric snapshot
uv run python tools/pipeline/audit_assets_adversarial.py --report /tmp/audit_report.json

# Run independent audit review subagent (Sonnet 4.6 / AGY auditor)
# Subagent evaluates /tmp/audit_report.json and generates AUDIT_REPORT.md
```
**Expected Outcome**: Signed `AUDIT_REPORT.md` confirming 0 un-demaked cage bypasses, 0 mesh explosions, 100% modular isolation, and PASS verdict.
