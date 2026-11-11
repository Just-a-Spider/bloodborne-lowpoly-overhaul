# Decision: Pure Plugin Retro Shaders & Host Migration to bbhost

- **Slug**: bbhost-retro-shaders
- **Decided**: 2026-11-11
- **Verdict**: go
- **Artifacts reviewed**: research.md, problem.md, concept.md

## Scorecard

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| Problem validity | strong | Migration from `bbport` to `bbhost` is blocked by lack of affine warping and noisy RGB dither in `bbhost`. |
| Evidence strength | strong | Fully cited git history and API headers (`deadinside28/bloodborne_pc/pull/419`, `bbhost` API 28 in `v0.2.32`). |
| Value vs. inaction | strong | Unifies development on active native PC decompilation runner; avoids maintaining two separate game runners. |
| Feasibility / appetite | strong | Pure plugin architecture requires zero edits to `bbhost` core; small appetite (3–5 days). |
| Strategic fit | strong | Perfect alignment with Bloodborne Low Poly Overhaul project without compromising host immutability. |
| Risk posture | strong | Safe upgrade path protects user saves (`~/.local/share/bbhost/data/saves`) and baseline game files (`CUSA03173`). |

## Verdict & Rationale

**Verdict: GO.**
The assessment proves that migrating to `bbhost` while achieving 100% retro graphics parity is fully achievable through a **pure external plugin** (`lowpoly_overhaul.so`) on `bbhost v0.2.32` without modifying `bbhost`'s engine source code. The prerequisite environment cleanup (replacing obsolete `v0.2.18` with cleanly compiled `v0.2.32` in `/home/andre/Games/bbhost` and integrating with Steam) is clearly defined and low-risk.

## If go — Handoff to `/speckit-specify`

- **Problem**: Migration to updated `bbhost v0.2.32` from `bbport` requires runner reinstallation, Steam launch integration, and retro graphics shader parity (affine texture mapping and luminance-locked Bayer dither) via a pure plugin with zero engine modifications.
- **Chosen approach**: Option A — Dedicated Pure Plugin (`lowpoly_overhaul.so`) using `bbhost` API 27/28 + clean runner upgrade to `v0.2.32` in `../bbhost`.
- **In scope / out of scope**:
  - *In scope*:
    1. Safe removal of old `bbhost v0.2.18` runner and clean installation of compiled `v0.2.32` into `/home/andre/Games/bbhost` (renamed from `bbhost-src`).
    2. Preservation of user save files in `~/.local/share/bbhost/data/saves`.
    3. Steam runner shortcut / script setup matching existing `bbport` steam workflow.
    4. Standalone `plugins/lowpoly_overhaul/` plugin implementing:
       - Native scene control (`scene_snap`, `scene_filter`, `scene_scale`, `scene_colour_bits`, `audio_crush`).
       - Custom compute dispatch for luminance-locked 4x4 Bayer dither via `on_render(BB_RENDER_AFTER_UPSCALE)`.
       - Affine texture mapping injection via API 27 `shader_source` + `shader_override`.
  - *Out of scope*:
    - Modifying `bbhost` engine C++ files.
    - Modifying base game files in `CUSA03173/`.
    - Modifying saves or game save structure.
    - Asset modifications, 3D models, or armor editions.
- **Success metrics**:
  - `bbhost v0.2.32` compiled and installed as `/home/andre/Games/bbhost`.
  - Steam launches `bbhost` seamlessly with existing game saves recognized.
  - `lowpoly_overhaul.so` plugin loaded by `bbhost` with live toggles in in-game menu.
  - Zero color speckles in dark scenes; authentic 32-bit PS1 vertex jitter and affine texture warping.
- **Carried-forward open questions**:
  - Verify whether `bbhost` binary compilation on local Linux environment requires specific Vulkan SDK or DXC library dependencies.
  - Determine optimal Steam shortcut launch arguments (e.g. `--app0` path pointing to `CUSA03173-PSX`).
