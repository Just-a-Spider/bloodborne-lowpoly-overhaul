# Implementation Plan: Retro HUD & Interaction Elements Demake

**Branch**: `001-retro-hud-elements` | **Date**: 2026-11-08 | **Spec**: [specs/001-retro-hud-elements/spec.md](spec.md)

**Input**: Feature specification from `specs/001-retro-hud-elements/spec.md`

## Summary

Demake Bloodborne's Scaleform heads-up display (HUD), player vitals, quickslots, interaction prompts, dialogue boxes, boss gauges, and announcement banners to an authentic 32-bit retro console style. The pipeline decodes BC7/BC1 UI texture atlases from `common.tpf.dcx`, downsamples and quantizes RGB channels to 15-bit RGB555 palette steps, applies nearest-neighbor canvas re-upscaling to lock Scaleform UV coordinate alignment, swizzles payloads into PS4 GCN Morton micro-tiles with single-mip invariants, and repacks into DCX containers deployed to `CUSA03173-PSX/` and standalone distribution packages with zero modifications to retail base game files.

## Technical Context

**Language/Version**: Python 3.12+ (strictly executed via `uv run python ...`)

**Primary Dependencies**: `soulstruct` (DCX compression/decompression, binary TPF parsing), `ispc_texcomp` (vectorized BC7 block compression), `texture2ddecoder` (BC7 decoding), `numpy` (array manipulations), `Pillow` (downsampling and nearest-neighbor resampling), `ps4_swizzle` (Morton micro-tile swizzling)

**Storage**: FromSoftware TPF binary containers compressed via DCX (`CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx`)

**Testing**: Standalone 4-tier acceptance test suite (`tools/verify_hud_demake.py`) with 15 automated validation checks covering container integrity, Scaleform UV compatibility, RGB555 palette compliance, controller button whitelist immutability, and retail folder safety

**Target Platform**: Linux (Kernel 6.x) and Windows via shadPS4 / bbhost PC translation layers

**Project Type**: CLI asset demake and verification pipeline

**Performance Goals**: Complete batch demake execution in < 5.0 seconds across all 65 textures; zero runtime GPU/CPU overhead; zero VRAM footprint inflation

**Constraints**:
- Baseline Immutability: Pristine `CUSA03173/` is 100% read-only.
- Scaleform UV Lock: Canvas pixel width and height MUST remain bit-for-bit identical to retail ($W, H$).
- Mip Level Invariant: Strictly single authored mip level (`num_mips = 1`).
- Controller Prompt Clarity: All 24 `KG_*` controller button icons and 3 `MENU_LNG_*` language textures MUST remain completely un-demaked.
- Color Depth: Quantized to 15-bit RGB555 (32 uniform levels per color channel, multiples of 8).

**Scale/Scope**: 65 total texture records in `common.tpf.dcx` (38 demaked, 27 preserved pristine)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Rule | Compliance Status | Justification |
| :--- | :---: | :--- |
| **I. Baseline Immutability & Safe Mod Isolation** | **PASS** | `CUSA03173/` is untouched. Outputs deploy to `CUSA03173-PSX/` and `mods/`. Backup `.bak` generated prior to write. |
| **II. Tooling Rigor & Unified Runtime (`uv run`)** | **PASS** | All scripts, runners, and tests executed via `uv run python ...`. Zero unpinned dependencies. |
| **III. Engine Invariants & Havok Physics Preservation** | **PASS** | UI textures enforce single-mip layout (`num_mips = 1`), correct Morton GCN swizzling, zero-padded buffer capacity, and exact canvas dimensions matching Scaleform GFX UV maps. |
| **IV. Automated Verification & Gate Enforcement** | **PASS** | 4-tier automated test harness (`tools/verify_hud_demake.py`) gates deployment with exit code 0 requirement. |
| **V. Empirical Documentation & Knowledge Retention** | **PASS** | Scaleform UV constraints, Morton swizzle math, and button guide retention documented in `research.md`, `contracts/`, and `data-model.md`. |

*GATE STATUS: ALL 5 PRINCIPLES PASS. ZERO VIOLATIONS.*

## Project Structure

### Documentation (this feature)

```text
specs/001-retro-hud-elements/
├── plan.md              # Master implementation plan
├── research.md          # Phase 0: Architectural decisions & Scaleform research
├── data-model.md        # Phase 1: Data entities & container invariants
├── quickstart.md        # Phase 1: Step-by-step execution & validation guide
├── contracts/           # Phase 1: CLI & binary format contracts
│   ├── hud-pipeline-cli.md
│   └── hud-texture-format.md
└── checklists/
    └── requirements.md  # Spec quality checklist (all passed)
```

### Source Code Layout

```text
tools/
├── demake_ui_engine.py               # Core UI atlas decoding, RGB555 quantizer, and swizzle encoder
├── verify_hud_demake.py              # Standalone 4-tier acceptance test suite
└── pipeline/
    ├── batch_demake_hud.py           # Master CLI orchestrator for menu archives
    ├── package_mod.py                # Standalone mod packaging and file staging
    └── create_patch.py               # Distribution XOR delta patch generator

CUSA03173-PSX/
└── dvdroot_ps4/
    └── menu/
        ├── common.tpf.dcx            # Deployed retro HUD container
        └── common.tpf.dcx.bak        # Pre-modification fallback backup

mods/
├── Bloodborne Low-Poly Overhaul (Cloth Physics)/   # Base overhaul (Cloth variant, untouched)
├── Bloodborne Low-Poly Overhaul (Flat Stiff)/      # Base overhaul (Stiff variant, untouched)
└── Bloodborne Retro HUD and UI/                    # Standalone addition mod
    └── dvdroot_ps4/
        └── menu/
            └── common.tpf.dcx                      # Packaged retro HUD & UI addition mod
```

**Structure Decision**: Utilizes the established `tools/pipeline/` batch architecture and `tools/demake_ui_engine.py` core engine, maintaining separation between low-level texture codec manipulation, batch pipeline orchestration, and automated test harness verification.

## Complexity Tracking

> *No constitutional or architectural violations identified. Zero entries required.*

---

## Phases & Deliverables

### Phase 0: Outline & Research (Completed)
- Artifact: [specs/001-retro-hud-elements/research.md](research.md)
- Decisions: Atlas segmentation, RGB555 quantization algorithm, single-mip Morton swizzle invariant, controller prompt whitelist, and test verification architecture.

### Phase 1: Design & Contracts (Completed)
- Artifact: [specs/001-retro-hud-elements/data-model.md](data-model.md) (Data entities, invariants, manifest)
- Artifact: [specs/001-retro-hud-elements/contracts/hud-pipeline-cli.md](contracts/hud-pipeline-cli.md) (CLI specification)
- Artifact: [specs/001-retro-hud-elements/contracts/hud-texture-format.md](contracts/hud-texture-format.md) (TPF & GCN swizzle binary layout)
- Artifact: [specs/001-retro-hud-elements/quickstart.md](quickstart.md) (Execution & validation guide)

### Phase 2: Tasks & Implementation (Next Step)
- Command: `/speckit-tasks` to generate dependency-ordered `tasks.md`.
