<!--
SYNC IMPACT REPORT
==================
Version Change: 1.1.0 -> 1.2.0
Modified Principles: None
Modified Sections:
  - Technical Constraints & Performance Standards: Updated Modular Packaging from 4 pillars to 5 independent pillars (Maps and Props/Objects decoupled).
Removed Sections: None
Follow-up TODOs: None
-->

# Bloodborne Low-Poly Overhaul Constitution

## Core Principles

### I. Baseline Immutability & Safe Mod Isolation
The vanilla retail game directory (`CUSA03173/`) is pristine and MUST NEVER be modified, written to, or altered in-place under any circumstance. All mod experiments, decimation outputs, and binary repacks MUST write strictly to `CUSA03173-PSX/` or destination mod packaging paths. User save files in `~/.local/share/bbhost/data/saves` MUST remain protected and untouched. Pre-modification backups (`.bak`) MUST be generated before overwriting any target game container.

### II. Tooling Rigor & Unified Runtime (uv run Standard)
All Python tooling, pipeline stages, decimation scripts, test runners, and benchmarks MUST execute through `uv run python ...`. Bare `python` or `python3` invocations are strictly prohibited across automation and agent execution environments. Zero unmanaged global dependencies are permitted; all execution environments MUST remain hermetic, lockfile-pinned (`uv.lock`), and reproducible.

### III. Engine Invariants & Havok Physics Preservation
Geometric optimization and retargeting MUST NOT compromise runtime stability. Havok cloth simulation meshes (e.g. `c8030` Meshes 0, 1, 2, 10, 11) and physics binary files (`*.hkx`, `*.clm2`) MUST remain 100% untouched. FLVER submesh FaceSets MUST remain synchronized (`FS1..FS5 = FS0.copy()`). Rigid submesh bounding boxes (AABBs) MUST reflect exact vertex extrema with zero artificial padding. Zero-area degenerate triangles (< 1e-6) and needle slivers ($\rho > 25.0$) MUST be culled prior to packaging.

### IV. Automated Verification & Gate Enforcement
Every asset decimation, manual cage reconstruction, and container injection MUST pass automated, multi-tier test suites prior to integration. Acceptance tests (such as `tools/verify_c8030_doll.py`, `tools/verify_hud_demake.py`) MUST execute with exit code 0 and 100% assertions satisfied across topology, clearance (>= 2.0mm against adjacent garments), skeletal bone weight normalization ($\sum w_j = 1.0$), and bone index boundaries $[0, 205]$. Manual-only approval is forbidden.

### V. Empirical Documentation & Knowledge Retention
Whenever a library quirk, API discrepancy, binary format nuance, or serialization fault (e.g., Soulstruct bone bounds, pyfqmr edge collapses, scipy, Assimp, or Blender FLVER exporter quirks) is identified, the exact technical root cause and verified workaround MUST immediately be appended to `BB_PSX_DEMAKE_GUIDE.md` and/or `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md`. Discarding unexpected errors, silently working around anomalies without logging, or leaving findings undocumented is strictly prohibited.

### VI. Multi-Model Independent Quality Audit
All completed features, major pipeline passes, and release milestones MUST undergo an independent quality audit conducted by an alternate Antigravity (AGY) model (such as Sonnet 4.6) before final sign-off. This cross-model review acts as an adversarial check against hallucinated passes, un-demaked high-poly asset omissions, deformed mesh explosions, and visual regressions.

## Technical Constraints & Performance Standards

- **Low-Poly Geometric Budget**: Character head and limb cages MUST target 250–450 manifold triangles with clean planar facets. Overall asset density MUST be reduced by 75–80% to alleviate draw-call CPU command-buffer bottlenecks.
- **Visual & Shading Authenticity**: Textures MUST follow 15-bit RGB555 palette quantization and nearest-neighbor point filtering. Diffuse textures MUST downscale to 128x128 or 256x256 uncompressed BC1 blocks, while preserving BC7 for alpha hair and BC5 for normal maps.
- **Hardware Target**: The pipeline MUST maintain a sub-2GiB VRAM footprint floor (< 2,048 MiB) on low-spec GPUs (such as NVIDIA GTX 1650 Max-Q 4GB), sustaining 55–90 FPS across outdoor bridges, hubs, and interior chalice dungeons.
- **Distribution Integrity**: Distribution packages MUST compile to differential patches via integer-vectorized XOR diffing (`bloodborne_lowpoly_overhaul.patch`), enabling zero-dependency standalone reconstruction via `apply_patch.py` with mandatory SHA256 integrity checks.
- **Modular Packaging**: Mod deliverables MUST support modular distribution under `mods/` for `bbport` / mod managers across five defined pillars:
  1. **Maps & Environment**: `mods/Bloodborne Retro Maps/` (`dvdroot_ps4/map/` world architecture, vistas, dungeon geometry, BXF texture binders)
  2. **Props & Objects**: `mods/Bloodborne Retro Props and Objects/` (`dvdroot_ps4/obj/` scenery props, mechanisms, doors, ladders, chests, cages, and cadaver waste heaps decoupled from maps for collision and dummy safety)
  3. **Armors and Weapons**: `mods/Bloodborne Retro Armors and Weapons - Cloth Physics/` and `mods/Bloodborne Retro Armors and Weapons - Flat Stiff/` (`dvdroot_ps4/parts/` player armors, trick weapons, firearms)
  4. **Characters**: `mods/Bloodborne Retro Characters/` (`dvdroot_ps4/chr/` enemies, bosses, Plain Doll, friendly NPCs)
  5. **UI & HUD**: `mods/Bloodborne Retro HUD and UI/` (`dvdroot_ps4/menu/` retro vitals gauges, icons, interaction frames, announcement banners)

## Development Workflow & Quality Gates

- **Structured Staging**: Work MUST proceed through four explicit phases: (1) Contract & Invariant Specification, (2) Test Harness Implementation, (3) Mesh/Texture Generation & Injection, and (4) E2E Automated Gate Verification.
- **Verification Gates**: Code review and CI/CD checks MUST enforce that no PR or task is marked complete without full regression test execution. Any failure in automated geometric, rigging, or bounding-box gates halts the deployment pipeline immediately.
- **Fallback Recovery**: If a packaging step or runtime validation fails, the pipeline MUST immediately abort and restore from pre-modification backups (`.bak`).

## Governance

This Constitution is the foundational engineering standard for the Bloodborne Low-Poly Overhaul project and supersedes all ad-hoc conventions. All contributors and agent personas MUST adhere strictly to these principles and constraints.

- **Amendment Procedure**: Any amendment to this constitution requires explicit rationale, unanimous consensus or maintainer approval, and a corresponding SemVer version increment.
- **Versioning Policy**: Follows Semantic Versioning (MAJOR for breaking changes or removal of core principles; MINOR for new principles or material expansions; PATCH for non-semantic clarifications and formatting updates).
- **Compliance Review**: All task plans, implementation PRs, and architectural decisions MUST be audited against these core rules before merge.

**Version**: 1.2.0 | **Ratified**: 2026-11-08 | **Last Amended**: 2026-11-08
