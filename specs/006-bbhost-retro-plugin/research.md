# Research & Technical Decisions: bbhost Migration & Pure Retro Plugin

**Feature**: `006-bbhost-retro-plugin`
**Date**: 2026-11-11

## Decision 1: Host Runner Migration & Directory Replacement

- **Decision**: Safely retire `/home/andre/Games/bbhost` (v0.2.18), build `bbhost v0.2.32` from `/home/andre/Games/bbhost-src`, and install it cleanly to `/home/andre/Games/bbhost`.
- **Rationale**:
  - The installed binary `v0.2.18` operates on Plugin API 11, which lacks `on_render` (API 27), `shader_override` (API 27), `scene_dither` (API 25), `audio_crush` (API 21), and `scene_snap` (API 18).
  - Upstream `v0.2.32` provides complete API 28 interfaces necessary to implement modern pure plugins.
  - Per Constitution Principle I and User Rules, player saves located in `~/.local/share/bbhost/data/saves` are decoupled from `/home/andre/Games/bbhost` and must be preserved with zero modification.
- **Alternatives Considered**:
  - *Patching v0.2.18 in-place*: Rejected; massive API generation gap spanning 17 API revisions.
  - *Keeping both directories side-by-side (`bbhost` and `bbhost-src`)*: Rejected; user explicitly asked to remove old version and rename/install new version as `bbhost`.

## Decision 2: Steam & Desktop Launch Integration

- **Decision**: Create an executable wrapper at `/home/andre/.local/bin/bbhost` using `/home/andre/.local/bin/offload --no-boost /home/andre/Games/bbhost/run-bbhost.sh "$@"` and register `/home/andre/.local/share/applications/io.github.bbhost.desktop`.
- **Rationale**:
  - Mirrors the existing, proven `bbport` launcher wrapper (`/home/andre/.local/bin/bbport`).
  - Ensures the dedicated NVIDIA GPU (GTX 1650 Max-Q) is engaged while disabling CPU boost to prevent thermal throttling on Linux.
  - Enables direct execution from Steam Big Picture, desktop application launchers, and terminal commands.
- **Alternatives Considered**:
  - *Calling binary directly without offload*: Rejected; risks running on integrated AMD Radeon Graphics with sub-optimal frame rates.

## Decision 3: Pure Plugin Architecture (`lowpoly_overhaul.so`)

- **Decision**: Implement all retro shader features as an external shared library (`plugins/lowpoly_overhaul.so`) adhering to `bbhost` Plugin API 28 without modifying a single line of `bbhost` engine code.
- **Rationale**:
  - Strictly fulfills the user's primary design constraint ("I dont want to modify anything in the bbhost itself, a plugin idea may be enough").
  - Independent build lifecycle using standard `g++ -O3 -shared -fPIC -std=c++20`.
  - Automatically discovered and loaded by `bbhost` at startup from `/home/andre/Games/bbhost/plugins/`.
- **Alternatives Considered**:
  - *Directly editing `bbhost` core files (`src/host/render.cpp`, `src/gcn/`)*: Rejected; violates user constraint and creates upstream merge conflicts.

## Decision 4: Luminance-Locked 4x4 Bayer Dithering via `on_render`

- **Decision**: Hook `api->on_render(name, BB_RENDER_AFTER_UPSCALE, ...)` and dispatch an embedded Vulkan compute shader executing the PR #419 luminance-ratio Bayer dither directly on the final frame image.
- **Rationale**:
  - `bbhost`'s built-in `ps1_dither.comp` performs raw RGB 5-bit channel quantization, causing noticeable rainbow grain and chromatic distortion in dark scenes (Hunter's Dream at night, Central Yharnam).
  - The PR #419 formula calculates luminance `Y = dot(rgb, vec3(0.299, 0.587, 0.114))`, applies 4x4 Bayer matrix across 63 levels, and reconstructs RGB with `rgb * (Y_quant / Y)`, preserving exact hue ratios.
  - Hooking `on_render` runs compute dispatches cleanly outside render passes with zero host engine modifications.
- **Alternatives Considered**:
  - *Using built-in `api->scene_dither(5)`*: Rejected; exhibits chromatic speckle noise.

## Decision 5: Affine Texture Mapping via API 27 `shader_override`

- **Decision**: Utilize `api->shader_source` and `api->shader_override` to dynamically intercept material pixel shaders, prefix `StageInput` attribute declarations with `noperspective`, and submit them to DXC for compilation into twin pipelines.
- **Rationale**:
  - Emulates authentic PlayStation 1 perspective-incorrect texture warping without requiring engine-level bytecode hooks.
  - Dynamically covers game shaders encountered during gameplay without requiring a fragile static repository of loose HLSL files.
- **Alternatives Considered**:
  - *Pre-dumped static HLSL folder*: Rejected; fragile across engine releases and game updates.
