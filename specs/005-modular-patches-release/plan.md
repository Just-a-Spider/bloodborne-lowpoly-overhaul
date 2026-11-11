# Implementation Plan: Modular Mod Release & Patch Distribution

**Branch**: `005-modular-patches-release` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-modular-patches-release/spec.md`

## Summary

Deliver verified, reproducible distribution artifacts for the 5-pillar modular Bloodborne demake overhaul (`dist/*.patch`) along with standalone reconstruction tooling (`apply_patch.py`), automated release verification (`verify_release_artifacts.py`), cryptographic manifests (`dist/SHA256SUMS.txt`), and comprehensive documentation updates across `README.md` and `BB_PSX_DEMAKE_GUIDE.md`.

## Technical Context

**Language/Version**: Python 3.9+ for standalone client `apply_patch.py` (pure standard library); Python 3.12+ managed via `uv` for developer pipeline tooling.

**Primary Dependencies**: Zero external dependencies for client tool (`hashlib`, `struct`, `json`, `pathlib`, `concurrent.futures`). Pipeline tooling uses `uv`, `pytest`, `pyfqmr`, `scipy`.

**Storage**: File-based XOR binary delta containers (`.patch`), `dvdroot_ps4/` VFS mod directory tree, and `dist/SHA256SUMS.txt`.

**Testing**: Automated verification harness (`tools/pipeline/verify_release_artifacts.py`), `tools/pipeline/modular_structure_validator.py`, and `tools/verify_hud_demake.py`.

**Target Platform**: Linux, Windows, macOS (any system with Python 3.9+).

**Project Type**: Standalone CLI distribution utility + release packaging pipeline.

**Performance Goals**:
- < 15 seconds to reconstruct full modular pillar.
- < 60 seconds to execute complete cryptographic release verification across all 9 patch containers.
- Sub-150MB peak memory during streaming XOR differential decoding.

**Constraints**:
- Baseline immutability: `CUSA03173/` is strictly read-only.
- Safe save isolation: never touch `~/.local/share/bbhost/data/saves`.
- Zero external pip requirements for players running `apply_patch.py`.
- Strict modular path separation: zero leakage between pillars.

**Scale/Scope**: 5 modular pillars (6 patch variants) + 3 master overhaul bundles covering 2,669 assets (7.1 GB compiled patch payloads).

---

## Constitution Check

*GATE: All principles from Constitution v1.2.0 evaluated and satisfied.*

| Principle | Requirement | Plan Status |
|---|---|---|
| **I. Baseline Immutability & Safe Mod Isolation** | `CUSA03173/` strictly read-only; saves untouched. | PASS. Patch reconstruction writes exclusively to user-specified output or `mods/`. |
| **II. Tooling Rigor & Unified Runtime** | All pipeline commands use `uv run python ...`. | PASS. Pipeline scripts invoked strictly with `uv run python`. |
| **III. Engine Invariants & Physics Preservation** | Havok cloth simulation preserved in Cloth package; Stiff package properly decoupled. | PASS. Cloth and Stiff packages packaged and validated independently. |
| **IV. Automated Verification & Gate Enforcement** | Automated release verification with exit code 0. | PASS. `verify_release_artifacts.py` gates release readiness. |
| **V. Empirical Documentation & Knowledge Retention** | Document quirks and invariants in guides. | PASS. Updates to `BB_PSX_DEMAKE_GUIDE.md` and `README.md`. |
| **VI. Multi-Model Independent Quality Audit** | Adversarial review before final sign-off. | PASS. Independent verification step planned before tagging release. |

---

## Project Structure

### Documentation (this feature)

```text
specs/005-modular-patches-release/
├── plan.md              # This file
├── research.md          # Phase 0 research findings
├── data-model.md        # Phase 1 data entities and schemas
├── quickstart.md        # Phase 1 verification and execution guide
├── contracts/           # Phase 1 interface specifications
│   ├── cli-contract.md
│   └── patch-container-spec.md
├── checklists/
│   └── requirements.md  # Quality validation checklist
└── tasks.md             # Phase 2 task execution breakdown (via /speckit-tasks)
```

### Source Code (repository root)

```text
apply_patch.py                             # Enhanced standalone client reconstructor
dist/
├── bloodborne_lowpoly_overhaul.patch      # Master Overhaul (Standard)
├── bloodborne_lowpoly_overhaul_cloth.patch# Master Overhaul (Cloth)
├── bloodborne_lowpoly_overhaul_stiff.patch# Master Overhaul (Stiff)
├── bloodborne_retro_armors_cloth.patch    # Pillar 3A: Armors & Weapons (Cloth)
├── bloodborne_retro_armors_stiff.patch    # Pillar 3B: Armors & Weapons (Stiff)
├── bloodborne_retro_characters.patch      # Pillar 4: Characters
├── bloodborne_retro_hud.patch             # Pillar 5: HUD and UI (Clean)
├── bloodborne_retro_maps.patch            # Pillar 1: Maps & Environment
├── bloodborne_retro_props.patch           # Pillar 2: Props & Objects
└── SHA256SUMS.txt                         # Authoritative checksum manifest
mods/                                      # Modular local staging trees
├── Bloodborne Retro Armors and Weapons - Cloth Physics/
├── Bloodborne Retro Armors and Weapons - Flat Stiff/
├── Bloodborne Retro Characters/
├── Bloodborne Retro HUD and UI/
├── Bloodborne Retro Maps/
└── Bloodborne Retro Props and Objects/
tools/pipeline/
├── create_patch.py                        # Patch generation tool
├── package_modular_mods.py                # Modular mod packager
├── modular_structure_validator.py         # Subpath isolation validator
└── verify_release_artifacts.py            # Release audit & manifest generator
README.md                                  # End-user player guide & patch inventory
BB_PSX_DEMAKE_GUIDE.md                     # Technical architecture & pipeline documentation
```

**Structure Decision**: Retains existing root and `tools/pipeline/` structure, enhancing `apply_patch.py` and adding `tools/pipeline/verify_release_artifacts.py`.

---

## Complexity Tracking

*No constitutional violations identified. Standard architecture with zero extra dependencies.*
