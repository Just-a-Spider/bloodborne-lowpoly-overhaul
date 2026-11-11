# Implementation Plan: Fix Dungeon Props Demake & Modular Mod Architecture

**Branch**: `002-fix-dungeon-props-modularize` | **Date**: 2026-11-08 | **Spec**: [spec.md](file:///home/andre/Games/Bloodborne/specs/002-fix-dungeon-props-modularize/spec.md)

**Input**: Feature specification from `specs/002-fix-dungeon-props-modularize/spec.md`

## Summary

1. Stabilize and demake Chalice Dungeon cadaver waste heaps and corpse props (`o297210`, `o298500`, `o290250`..`o290274`, etc.), eliminating ballooned polygon explosions and giant spikes by enforcing bone-local coordinate locking, ground clamping, and degenerate sliver culling.
2. Demake regular and deformed dungeon cages (`o290000`..`o290004`, `o290200`..`o290284`, `o322050`..`o322056`, etc.) with 70–80% triangle reduction and authentic flat facet normal shading, lifting blanket bypasses while preserving `.anibnd` animations and Havok `.hkx` collisions.
3. Establish a 5-pillar modular mod architecture for `bbport` under `mods/`, isolating static maps (`map/`) from interactive/scenery props (`obj/`), armors/weapons (`parts/`), characters (`chr/`), and UI (`menu/`).
4. Implement Principle VI (Multi-Model Independent Quality Audit via Sonnet 4.6 in AGY) for adversarial pipeline sign-off.

---

## Technical Context

**Language/Version**: Python 3.11+ running exclusively via `uv run python ...`  
**Primary Dependencies**: `soulstruct` (FromSoftware format parser/packer), `soulstruct_patch`, `numpy`, `pillow`, headless Blender 5.2.3 (`/usr/bin/blender`), `pyfqmr` (QEM decimation).  
**Storage**: Btrfs copy-on-write filesystem, DCX containers (`DCX_DFPR` / deflate), binary FLVER2 models, TPF texture sheets.  
**Testing**: Multi-tier automated pytest/CLI verification test harnesses (`tools/verify_retro_props.py`, `tools/verify_modular_mods.py`).  
**Target Platform**: Bloodborne PC port (`bbport` / shadPS4) on Linux (Fedora/Ubuntu) and Steam Deck / low-spec GPUs (GTX 1650).  
**Project Type**: 3D asset decimation pipeline, game mod packaging architecture, and adversarial quality assurance.  
**Performance Goals**: Sub-2GiB VRAM usage (< 2,048 MiB), steady 60–90 FPS in Chalice Dungeons, zero camera-clipping polygon sheets.  
**Constraints**:
- Baseline `CUSA03173/` is 100% read-only and cryptographically immutable.
- Never modify user save files in `~/.local/share/bbhost/data/saves`.
- Havok collision (`.hkx`) and `.anibnd` animation tracks must remain bit-for-bit preserved.
- No emojis anywhere in code, commits, or documentation.
- Caveman communication mode active at all times.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Requirement | Plan Compliance Status | Notes |
| :--- | :--- | :--- | :--- |
| **I. Baseline Immutability** | `CUSA03173/` strictly read-only; outputs in `CUSA03173-PSX/` and `mods/`. | **PASS** | Base game is never written to; all outputs stage to `CUSA03173-PSX` and `mods/`. Pre-modification `.bak` generated. |
| **II. Tooling Rigor (uv run)** | Always use `uv run python ...`. | **PASS** | All commands and scripts executed via `uv run python ...`. Bare `python` strictly prohibited. |
| **III. Engine Invariants** | Havok `.hkx` preserved; FaceSets synchronized; degenerate triangles culled. | **PASS** | Collision meshes preserved; `FS1..FS5 = FS0.copy()`; sliver aspect ratio capped at $\le 25.0$; edge lengths $\le 2.0$m. |
| **IV. Automated Verification** | Multi-tier test suites pass with exit code 0 before integration. | **PASS** | `tools/verify_retro_props.py` and `tools/verify_modular_mods.py` enforce all geometric and structural invariants. |
| **V. Empirical Documentation** | Discrepancies logged to `BB_PSX_DEMAKE_GUIDE.md` and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md`. | **PASS** | Unskinned bone-local coordinates and cage bypass root causes documented in `research.md` and demake guides. |
| **VI. Multi-Model Audit** | Independent quality audit conducted by alternate AGY model (Sonnet 4.6). | **PASS** | Adversarial subagent protocol implemented via `audit_assets_adversarial.py` and dedicated auditor subagent. |

---

## Project Structure

### Documentation (this feature)

```text
specs/002-fix-dungeon-props-modularize/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 research findings & decisions
├── data-model.md        # Phase 1 data entities and validation rules
├── quickstart.md        # Phase 1 test and validation guide
├── contracts/           # Phase 1 CLI & workflow contracts
│   ├── props-pipeline-cli.md
│   ├── modular-packaging-cli.md
│   └── audit-workflow.md
├── checklists/
│   └── requirements.md  # 16/16 requirements checklist
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
tools/
├── pipeline/
│   ├── batch_blender_demake_obj.py   # Enhanced prop demake engine (cage un-bypass, cadaver stabilization)
│   ├── blender_process_obj.py        # Headless Blender 5.2.3 flat facet normals & QEM script
│   ├── package_modular_mods.py       # 5-pillar modular packaging engine for bbport under mods/
│   └── audit_assets_adversarial.py   # Geometric metric extraction for multi-model audit
├── verify_retro_props.py             # Acceptance test harness for cages and cadavers
└── verify_modular_mods.py            # Acceptance test harness for mods/ 5-pillar structure

mods/
├── Bloodborne Retro Maps/                                    # Pillar 1: dvdroot_ps4/map/
├── Bloodborne Retro Props and Objects/                       # Pillar 2: dvdroot_ps4/obj/
├── Bloodborne Retro Armors and Weapons - Cloth Physics/      # Pillar 3a: dvdroot_ps4/parts/
├── Bloodborne Retro Armors and Weapons - Flat Stiff/         # Pillar 3b: dvdroot_ps4/parts/
├── Bloodborne Retro Characters/                              # Pillar 4: dvdroot_ps4/chr/
└── Bloodborne Retro HUD and UI/                              # Pillar 5: dvdroot_ps4/menu/
```

**Structure Decision**: Selected modular multi-pillar architecture with dedicated tools in `tools/pipeline/` and verification suites in `tools/`. Decoupled props (`obj/`) completely from maps (`map/`) to ensure collision and dummy modifications never corrupt static world geometry.

---

## Complexity Tracking

> No constitutional violations. All principles and constraints satisfied.
