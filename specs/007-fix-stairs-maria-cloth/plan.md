# Implementation Plan: Fix Research Hall Interactive Stairs and Lady Maria Cloth Physics

**Branch**: `007-fix-stairs-maria-cloth` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-fix-stairs-maria-cloth/spec.md`

## Summary

Resolve invisible and detached interactive stairs/ladders in Research Hall (`m35_00`) by correcting classification in `batch_blender_demake_obj.py` and restoring pristine multi-bone FLVER assets. Resolve Lady Maria boss fight detached cloth/feather meshes by retaining Havok cloth physics in the Cloth edition and re-parenting dummy bones to character root bones in the Flat Stiff edition. Update modular packages, generate differential patches, and publish release 1.2.1 while strictly excluding non-mod experimental features (000).

## Technical Context

**Language/Version**: Python 3.11 / Blender 4.x Python API / Soulstruct 2.3+

**Primary Dependencies**: `soulstruct`, `scipy`, `numpy`, `pytest`

**Storage**: FromSoftware game binders (`.objbnd.dcx`, `.partsbnd.dcx`), binary FLVER models, Havok `.hkx`

**Testing**: `pytest tests/test_apply_patch.py`, `tools/verify_retro_props.py`, automated bone and bounding box checks

**Target Platform**: PlayStation 4 (Bloodborne CUSA03173) / ShadPS4 / bbhost

**Project Type**: Asset pipeline & binary patch generation

**Performance Goals**: 100% stair visibility and collision alignment; 0 detached/floating meshes on Lady Maria; 60 FPS sustained

**Constraints**: Immutability of `CUSA03173/`; no emojis; `uv run python` exclusively; sub-2GiB VRAM footprint floor

**Scale/Scope**: 12 interactive prop assets, 4 player/NPC armor containers, 5 modular mod directories

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Baseline Immutability: PASS - `CUSA03173/` is read-only. All outputs go to `CUSA03173-PSX/`, `mods/`, and `dist/`.
- Tooling Rigor: PASS - All scripts run with `uv run python ...`.
- Engine Invariants & Havok Physics Preservation: PASS - Maria cloth preserves `.hkx`/`.clm2` in Cloth edition and re-parents dummy bones in Stiff edition; interactive stair bones and AABBs preserved.
- Automated Verification: PASS - Automated tests verify AABBs, bone hierarchies, and patch integrity.
- Empirical Documentation: PASS - Root causes and solutions recorded in `research.md`.
- No Emojis: PASS - Zero emojis used across all artifacts, code, and commit logs.

## Project Structure

### Documentation (this feature)

```text
specs/007-fix-stairs-maria-cloth/
├── plan.md              # This file
├── research.md          # Root cause analysis and technical decisions
├── data-model.md        # Asset structures, validation invariants
├── quickstart.md        # Step-by-step verification commands
├── contracts/           # Pipeline contracts and guarantees
│   └── pipeline_contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Generated implementation tasks
```

### Source Code (repository root)

```text
tools/pipeline/
├── batch_blender_demake_obj.py   # Prop demake pipeline with bypass rules
├── deploy_retro_armors.py        # Retro armor deployment and bone re-parenting
├── package_modular_mods.py       # Modular mod packaging script
└── create_patch.py               # Differential XOR patch generator

tests/
├── test_apply_patch.py           # Differential patch regression test
└── verify_maria_cloth.py         # Dedicated Maria cloth and stair verification test
```

**Structure Decision**: Uses existing `tools/pipeline/` for asset processing and tests under `tests/` for automated verification.

## Complexity Tracking

No constitution violations.
