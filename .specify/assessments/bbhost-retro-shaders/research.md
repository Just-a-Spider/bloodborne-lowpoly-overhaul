# Idea Research: Porting Retro Graphics Shaders from bbport to bbhost

- **Slug**: bbhost-retro-shaders
- **Created**: 2026-11-11
- **Evidence confidence (overall)**: high

## Users & Demand

- Bloodborne PSX demake / low-poly overhaul community requires authentic 32-bit era rendering constraints (vertex coordinate snapping/jitter, affine texture mapping, 15-bit color dithering, point filtering) — [source: /home/andre/Games/Bloodborne/README.md] (confidence: high, cited)
- Player migration from `bbport` to `bbhost` is motivated by `bbhost`'s standalone native execution, decompiled subsystems, and modular plugin system, but requires feature parity for retro shaders — [source: user request & bbhost README.md] (confidence: high, cited)
- Stated demand focuses strictly on the GPU rendering/shader pipeline; mod formats, game scripts, and audio are explicitly out of scope for this investigation — [source: user clarification] (confidence: high, cited)

## Prior Art

- **bbport PR #419 (`deadinside28/bloodborne_pc/pull/419`)**: Contributed by `Just-a-Spider`, commit `c32ba6fc0ba616159a5dacea90b4b15700726643`. Added full retro graphics pipeline:
  1. Screen-space vertex snapping via SPIR-V generator hook in `emit_spirv_special.cpp` (`EmitVertexSnap`).
  2. Affine texture mapping via `spv::Decoration::NoPerspective` attribute injection in `spirv_emit_context.cpp`.
  3. Luminance-only 4x4 Bayer matrix dithering with 63 levels and chroma-ratio locking in `present_encode.frag`.
  4. Point/nearest texture sampling override in `sampler.cpp` and `texture_cache.cpp`.
  5. Cache partitioning (`_retro` folder suffix in `blob_store.cpp`).
  — [source: https://github.com/deadinside28/bloodborne_pc/pull/419.patch] (confidence: high, cited)
- **bbhost PS1 Plugin & Host Hooks (`plugins/ps1/ps1.cpp`, `src/host/scene_look.h`)**:
  1. Vertex snapping ALREADY EXISTS in `bbhost` via `src/host/vertex_snap.cpp` and `src/host/vertex_snap.h`. Implemented as host-side SPIR-V bytecode rewriting called in `render.cpp` (`vertex_look`), producing twin pipeline states salted with `kSnapSalt`.
  2. Nearest-neighbor texture filtering ALREADY EXISTS in `bbhost` via `scene_look_set_nearest` / `BB_FILTER_NEAREST` in `render.cpp` (`look_samplers`).
  3. Dithering ALREADY EXISTS in `bbhost` via compute shader `src/host/shaders/ps1_dither.comp` (Plugin API 25), but uses per-channel RGB quantization (levels = 31) rather than luminance-locked dithering.
  4. Affine texture mapping (`NoPerspective`) DOES NOT EXIST in `bbhost`.
  — [source: /home/andre/Games/bbhost-src/src/host/vertex_snap.h, /home/andre/Games/bbhost-src/plugins/ps1/ps1.cpp] (confidence: high, cited)

## Market & Context

- `bbport` and `bbhost` are two competing/parallel native PC implementations of Bloodborne v1.09 using Vulkan graphics translation.
- `bbport` translates shaders within an integrated GCN-to-SPIR-V recompiler path and uses a custom presentation pipeline (`present_encode.frag`).
- `bbhost` maintains strict separation between translator core (`src/gcn`), runtime hooks (`src/host`), and external plugins (`plugins/ps1`). To prevent invalidating translation cache fingerprints, `bbhost` uses bytecode transformation passes on SPIR-V modules (`src/host/vertex_snap.cpp`) rather than modifying the compiler frontend.
- Cost of doing nothing: Users migrating to `bbhost` lose affine texture warping, and must use `bbhost`'s RGB-channel dither which introduces color artifacts compared to `bbport`'s luminance dither.

## Data & Constraints

- **Platform limit / Architecture convention**: `bbhost` explicitly documents in `src/host/vertex_snap.h` that modifications must remain host-side (`src/host/`) rather than `src/gcn/` to avoid busting player translation cache fingerprints. Any affine texture injection must conform to this pattern (e.g. host-side SPIR-V bytecode pass on fragment stages) or be cleanly incorporated into `plugins/ps1`.
- **Shader model constraints**: Vulkan SPIR-V specification requires `NoPerspective` decorations on fragment inputs to match output declarations if interfaces are checked strictly, though Vulkan drivers permit input decoration relaxations. SPIR-V bytecode rewriting must handle `OpVariable` inputs and ensure valid instruction stream.
- **Dither algorithm comparison**:
  - `bbhost` (`ps1_dither.comp`): Independent compute pass, per-RGB channel quantization to 31 levels (5-bit). Causes noticeable color distortion in dark environments.
  - `bbport` (`present_encode.frag`): Present pass fragment shader, luminance calculation (`dot(c, vec3(0.299, 0.587, 0.114))`), 63 levels, RGB ratio preserved (`c * (Y_quant / Y)`). Retains true color tones while giving crisp 32-bit dither.

## Evidence Against the Idea

- **Duplication of existing work**: Vertex snapping and point filtering are already implemented and working in `bbhost`. Re-implementing them from `bbport`'s patch would be redundant and violate `bbhost`'s established twin-pipeline architecture.
- **Architectural divergence**: Directly copy-pasting code from `bbport` PR #419 into `bbhost` will not work because `bbhost` has different class hierarchies, rendering structures (`DrawState`, `RtImage`), and SPIR-V management. Changes must be adapted to `bbhost`'s native paradigms.
- **Complexity of host-side affine transformation**: Parsing and decorating all pixel shader input variables in arbitrary SPIR-V binaries (from both GCN lift and DXC HLSL pipelines) requires a dedicated SPIR-V rewriting pass similar in complexity to `vertex_snap.cpp`.

## Gaps & Open Questions

- [NEEDS CLARIFICATION: Should the retro shader features be exposed through `bbhost`'s existing `plugins/ps1` plugin, or through native `bbhost.toml` settings?]
- [NEEDS CLARIFICATION: Should `bbhost`'s `ps1_dither.comp` compute shader be upgraded to use bbport's luminance-locked Bayer dither algorithm, or added as a configurable mode?]
- [NEEDS CLARIFICATION: Is affine texture mapping (`NoPerspective`) a hard requirement for demake parity, or is vertex snapping + point filtering + luminance dither sufficient?]

## Sources

- `https://github.com/deadinside28/bloodborne_pc/pull/419.patch` (host: github.com, policy: allowlisted)
- `https://github.com/droogie/bbhost` (host: github.com, policy: allowlisted)
- `/home/andre/Games/bbhost-src/` (host: local filesystem, cloned alongside bbport-src)
- `/home/andre/Games/Bloodborne/BB_PSX_DEMAKE_GUIDE.md` (host: local repository)
