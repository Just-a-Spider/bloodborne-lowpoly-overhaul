# Concept: Pure Plugin for Retro Graphics Parity in bbhost

- **Slug**: bbhost-retro-shaders
- **Created**: 2026-11-11
- **Recommended option**: Option A — Dedicated Pure Plugin (lowpoly_overhaul.so) using bbhost API 27/28

## Options

### Option A — Dedicated Pure Plugin (lowpoly_overhaul.so) using bbhost API 27/28
- **Sketch**: A standalone plugin compiled against `include/bbhost_plugin.h` (API 28, native in `v0.2.32`). Leaves `bbhost` engine repository 100% untouched.
  - Directly drives built-in host hooks: `scene_snap` (vertex snap), `scene_filter` (point filtering), `scene_scale` (240p decoupled rendering), `scene_colour_bits` (RGBA8), and `audio_crush` (22kHz 12-bit sound).
  - Replaces Kyo's noisy RGB dither by hooking `on_render` (`BB_RENDER_AFTER_UPSCALE`) and executing our own compute shader implementing the PR #419 luminance-locked Bayer dither directly on the final frame image.
  - Provides affine texture mapping (`NoPerspective`) by hooking API 27 `shader_source` / `shader_override` to dynamically insert `noperspective` interpolators into camera pixel shaders.
- **Appetite**: small (3–5 days)
- **Trade-offs**:
  - *Wins*: Zero modifications to `bbhost` source or binary; cleanly isolated in `<data>/plugins/lowpoly_overhaul.so`; independent release lifecycle; fixes dither color banding without touching host code.
  - *Sacrifices / Risks*: Requires runtime host to be `bbhost v0.2.32` (installed `v0.2.18` uses API 11 and must be upgraded to v0.2.32 release). Affine texture override relies on DXC shader pipeline being active.
- **Rabbit holes**: Pattern matching pixel shader inputs across diverse material shaders to cleanly insert `noperspective` without syntax errors.

### Option B — Built-in PS1 Plugin + Standalone Dither Companion Plugin
- **Sketch**: Enable `bbhost v0.2.32`'s existing `plugins/ps1` for vertex snapping, point filtering, render scaling, and 8-bit color. Write a tiny, focused companion plugin (`clean_dither.so`) that hooks `on_render` (`BB_RENDER_AFTER_UPSCALE`) solely to run luminance-locked Bayer dither. Keep `ps1.dither = false` in `bbhost.toml`. Forgo affine texture warping entirely.
- **Appetite**: small (1–2 days)
- **Trade-offs**:
  - *Wins*: Minimal implementation surface; zero shader override complexity; fixes the primary visual flaw of `plugins/ps1` (dark scene color grain).
  - *Sacrifices*: No affine texture warping (polygons don't exhibit PS1 perspective warping).
- **Rabbit holes**: None; very straightforward compute dispatch.

### Option C — Static HLSL Mod Pack (No Plugin C++ Code)
- **Sketch**: Zero C++ code. Rely on `bbhost`'s loose shader override directory (`<data>/bbhost/shaders/`) to inject `noperspective` into pre-dumped HLSL files, paired with vanilla `ps1` plugin in `bbhost.toml`.
- **Appetite**: medium (1–2 weeks)
- **Trade-offs**:
  - *Wins*: No C++ compilation or plugin binary maintenance.
  - *Sacrifices*: Massive directory of static shader files; breaks on any engine shader compiler update; cannot fix RGB dither noise.
- **Rabbit holes**: Version drift breaking shader signatures (`BB_SHADER_REFUSED`); missing newly discovered shaders.

## Recommendation

**Option A (Dedicated Pure Plugin using bbhost API 27/28)** is strongly recommended.
- Fully honors the constraint: **zero changes to `bbhost` itself**.
- Packaged as a clean, self-contained `lowpoly_overhaul.so` plugin.
- Solves both core gaps over vanilla `ps1`: delivers clean luminance-locked dither (via `on_render`) and affine texture mapping (via `shader_override`).
- Requires only that the user runs `bbhost v0.2.32` (or builds upstream `bbhost-src`).

## Out of Scope (for the recommended option)

- Modifying any file inside `bbhost` core engine (`src/host/`, `src/gcn/`, `src/core/`).
- Game asset downscaling, models, armor editions, or XOR patches.
- Gameplay scripts, save migration, or network emulation.

## Assumptions to Validate

- Installed runner environment is updated from `v0.2.18` (API 11) to `v0.2.32` (API 28) so `on_render` and `shader_override` are available.
- `on_render` compute dispatch overhead is negligible (< 0.2 ms per frame).
- Pixel shader input rewriting (`noperspective StageInput`) via `shader_override` compiles cleanly via DXC at runtime without pipeline stall spikes.
