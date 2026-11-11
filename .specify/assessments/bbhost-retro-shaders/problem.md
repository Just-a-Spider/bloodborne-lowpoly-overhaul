# Problem Definition: Retro Graphics Pipeline Parity in bbhost

- **Slug**: bbhost-retro-shaders
- **Created**: 2026-11-11
- **Inputs used**: research.md, user input

## Problem Statement

Players and developers migrating from `bbport` to `bbhost` cannot achieve full visual fidelity for the Bloodborne Low Poly Overhaul because `bbhost` lacks perspective-incorrect (affine) texture mapping and employs a per-channel RGB dither that causes color distortion in dark environments, blocking complete migration to `bbhost`.

## Affected Users & Stakeholders

- **Users**: Bloodborne Low Poly Overhaul players and modders — unable to experience complete 32-bit PS1 aesthetic (texture warping missing; dither produces rainbow speckles and banding in dark scenes) when running on `bbhost`.
- **Stakeholders**: Project maintainer — blocked from migrating workflow from `bbport` to `bbhost` until graphical parity is reached without regressions.

## Goals

- Achieve complete visual feature parity in `bbhost` with the retro graphics pipeline established in `bbport` PR #419.
- Implement perspective-incorrect (affine) texture mapping within `bbhost`, preferably driven through the existing `plugins/ps1` architecture via a clean host API hook (`scene_affine`).
- Deliver clean 15-bit Bayer dithering that preserves luminance ratios and avoids chroma distortion in shadows (upgrading `src/host/shaders/ps1_dither.comp` invoked by `plugins/ps1`).
- Maintain architecture integrity in `bbhost` (preserve translation cache fingerprints and maintain decoupled plugin/host boundaries).

## Non-Goals

- Gameplay scripts, game events, or save migration (explicitly out of scope).
- Asset modifications, 3D model downscaling, or armor texture edits (explicitly out of scope).
- Audio bit-crushing or low-pass filtering modifications (already present in `plugins/ps1`).
- Modifications to core `src/gcn/` translator that invalidate baseline cache hashes.

## Success Metrics

- **Feature Parity**: 100% coverage of bbport PR #419 retro shader features (vertex snap, affine UVs, luminance dither, point filtering). (baseline: affine missing; dither introduces color speckles).
- **Chroma Stability**: Zero hue drift or color artifacts on dark gradients during dithering. (baseline: RGB 5-bit dither causes visible color fringing).
- **Stability & Performance**: Zero crashes or SPIR-V validation faults when retro shaders are toggled. (baseline: current `bbhost` runs stable without affine).

## Cost of Inaction

Migration to `bbhost` remains blocked. The project remains tied to `bbport` solely for retro shader rendering, preventing adoption of `bbhost`'s superior decompilation architecture, performance gains, and active upstream development.

## Open Questions

- [NEEDS CLARIFICATION: Plugin integration approach: Extend `BbHostApi` with `scene_affine(bool)` so `plugins/ps1` controls it cleanly alongside `scene_snap` and `scene_dither`, vs static shader folder override?]
- [NEEDS CLARIFICATION: Should the luminance-locked Bayer dither replace `src/host/shaders/ps1_dither.comp` entirely or be added as an alternative dither mode in `plugins/ps1`?]
- [NEEDS CLARIFICATION: Is runtime hot-toggling required for affine mapping, or is game restart acceptable?]
