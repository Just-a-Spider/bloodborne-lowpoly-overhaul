# Tasks: bbhost Runner Upgrade & Pure Retro Shaders Plugin

**Input**: Design documents from `/specs/006-bbhost-retro-plugin/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)
**Tests**: Verification scenarios documented in [quickstart.md](quickstart.md)
**Organization**: Tasks are grouped by user story to enable independent implementation and testing.
**Workspace Rule**: All external tools, scripts, and plugin sources MUST reside under `/home/andre/Games/reference/` (completely outside the Bloodborne mod repository).

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Pre-migration safety checks and external reference workspace initialization

- [x] T001 Pre-migration safety check: verify player saves in `~/.local/share/bbhost/data/saves` and backup `~/.config/bbhost/bbhost.toml` to `~/.config/bbhost/bbhost.toml.bak`
- [x] T002 Create external workspace directories `/home/andre/Games/reference/tools/`, `/home/andre/Games/reference/plugins/lowpoly_overhaul/`, and `/home/andre/Games/reference/plugins/lowpoly_overhaul/shaders/`
- [x] T003 [P] Create plugin build configuration in `/home/andre/Games/reference/plugins/lowpoly_overhaul/Makefile` targeting C++20 (`-std=c++20 -O3 -shared -fPIC`) with include path to `/home/andre/Games/bbhost-src/include`

---

## Phase 2: Foundational (Host Rebuild & Deployment)

**Purpose**: Core runner upgrade to `v0.2.32` that MUST be complete before plugins can be executed

- [x] T004 Compile `bbhost v0.2.32` from source in `/home/andre/Games/bbhost-src` using CMake and Ninja (`cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build --config Release -j$(nproc)`)
- [x] T005 Retire legacy `/home/andre/Games/bbhost` (v0.2.18) directory and cleanly install freshly compiled `v0.2.32` binaries, tools, and assets into `/home/andre/Games/bbhost`
- [x] T006 [P] Create launcher wrapper script at `/home/andre/.local/bin/bbhost` configured with `offload --no-boost` pointing to `/home/andre/Games/bbhost/run-bbhost.sh` per [launcher-contract.md](contracts/launcher-contract.md)
- [x] T007 [P] Create desktop shortcut at `~/.local/share/applications/io.github.bbhost.desktop` per [launcher-contract.md](contracts/launcher-contract.md)

**Checkpoint**: Foundation ready — modern `bbhost v0.2.32` runner deployed and ready for user story implementation.

---

## Phase 3: User Story 1 - Clean Runner Migration & Steam Launch Integration (Priority: P1) 🎯 MVP

**Goal**: Seamless execution of Bloodborne via updated runner with GPU offload and verified save detection

**Independent Test**: Boot runner via `/home/andre/.local/bin/bbhost`; verify game boots to main menu with existing player saves intact per [quickstart.md](quickstart.md) Scenario 1.

### Implementation for User Story 1

- [x] T008 [US1] Configure hardware optimization environment flags in `/home/andre/Games/bbhost/run-bbhost.sh` (`BBHOST_TIGHT_MEMORY=1`, `BBHOST_BUFFER_SHADOW=1`, `BBHOST_CS_OPTIMIZE=1`, `BBHOST_UNTILE_THREADS=4`)
- [x] T009 [US1] Verify end-to-end boot, Steam wrapper offloading, and existing character save loading from `~/.local/share/bbhost/data/saves` per [quickstart.md](quickstart.md) Scenario 1

**Checkpoint**: User Story 1 complete — `bbhost v0.2.32` runs cleanly with player saves protected.

---

## Phase 4: User Story 2 - Complete 32-Bit Retro Shading Parity via Pure Plugin (Priority: P1)

**Goal**: Full 32-bit PSX graphics pipeline (vertex snapping, affine texture mapping, point filtering, 240p decoupled rendering) delivered via pure plugin with zero engine modifications

**Independent Test**: Load `lowpoly_overhaul.so`; verify vertex snapping, affine texture warping, and nearest-neighbor texture sampling on 3D meshes per [quickstart.md](quickstart.md) Scenario 2.

### Implementation for User Story 2

- [x] T010 [P] [US2] Implement plugin export interface and lifecycle functions in `/home/andre/Games/reference/plugins/lowpoly_overhaul/lowpoly_overhaul.cpp` (`bb_plugin_info`, `bb_plugin_options`, `bb_plugin_init`, `bb_plugin_image`) per [plugin-api.md](contracts/plugin-api.md)
- [x] T011 [US2] Implement native scene look controls in `/home/andre/Games/reference/plugins/lowpoly_overhaul/lowpoly_overhaul.cpp` driving `scene_snap` (`snap_resolution` choices `"Off"`, `"120p"`, `"240p"`, `"360p"`, `"480p"`), `scene_filter(BB_FILTER_NEAREST)`, `scene_scale(BB_SCALE_NEAREST, 240)`, and `scene_colour_bits(8)`
- [x] T012 [US2] Implement dynamic affine texture mapping via API 27 `shader_source` and `shader_override` in `/home/andre/Games/reference/plugins/lowpoly_overhaul/lowpoly_overhaul.cpp` by parsing pixel shader `StageInput` structs and prepending `noperspective` interpolators
- [x] T013 [US2] Build `lowpoly_overhaul.so` via `/home/andre/Games/reference/plugins/lowpoly_overhaul/Makefile`, deploy to `/home/andre/Games/bbhost/plugins/`, and verify exported symbols via `nm -D`

**Checkpoint**: User Story 2 complete — vertex snapping, affine mapping, and point filtering active in `bbhost`.

---

## Phase 5: User Story 3 - Clean Luminance Dithering in Dark Scenes (Priority: P2)

**Goal**: Pristine 15-bit Bayer dithering that quantizes luminance and locks color ratios, eliminating dark scene rainbow noise

**Independent Test**: Inspect dark scene gradients (e.g. Hunter's Dream at night); verify monochrome 4x4 Bayer cross-hatching without chromatic grain per [quickstart.md](quickstart.md) Scenario 3.

### Implementation for User Story 3

- [x] T014 [P] [US3] Implement luminance-locked 4x4 Bayer compute shader in `/home/andre/Games/reference/plugins/lowpoly_overhaul/shaders/dither_luma.comp` with 63 luminance levels and chroma-ratio locking per bbport PR #419
- [x] T015 [P] [US3] Compile compute shader to SPIR-V header `/home/andre/Games/reference/plugins/lowpoly_overhaul/shaders/dither_luma.spv.h` using `glslangValidator -V`
- [x] T016 [US3] Implement Vulkan compute pipeline creation and dispatch in `/home/andre/Games/reference/plugins/lowpoly_overhaul/dither_pipeline.h` registered at `on_render(name, BB_RENDER_AFTER_UPSCALE, ...)` in `/home/andre/Games/reference/plugins/lowpoly_overhaul/lowpoly_overhaul.cpp`
- [x] T017 [US3] Verify luminance dither visual output on dark gradients in Hunter's Dream and Central Yharnam per [quickstart.md](quickstart.md) Scenario 3

**Checkpoint**: User Story 3 complete — clean luminance dithering active with zero dark scene chromatic noise.

---

## Phase 6: User Story 4 - Live In-Game Configuration & Hot-Toggling (Priority: P3)

**Goal**: Real-time adjustment of retro visual effects via in-game menu and persistent configuration

**Independent Test**: Open F9 menu in-game; toggle individual retro visual effects; verify immediate visual update per [quickstart.md](quickstart.md) Scenario 3.

### Implementation for User Story 4

- [x] T018 [US4] Implement live options change listener `on_option` in `/home/andre/Games/reference/plugins/lowpoly_overhaul/lowpoly_overhaul.cpp` supporting real-time toggles for snap, affine, dither, and point filter
- [x] T019 [US4] Verify in-game F9 overlay menu controls and persistent configuration round-trip in `/home/andre/Games/bbhost/bbhost.toml`

**Checkpoint**: User Story 4 complete — live in-game hot-toggling operational.

---

## Phase 7: User Story 5 - Import bbport Saves into bbhost (Priority: P2)

**Goal**: Safe import and synchronization of campaign save files from `bbport` into `bbhost` with pre-import backup protection

**Independent Test**: Run `/home/andre/Games/reference/tools/import_bbport_saves.py`; verify backup created and game loads imported `bbport` progress per [quickstart.md](quickstart.md) Scenario 4.

### Implementation for User Story 5

- [x] T020 [P] [US5] Implement save import script `/home/andre/Games/reference/tools/import_bbport_saves.py` that creates timestamped backups in `~/.local/share/bbhost/data/saves/` and copies decrypted `SPRJ0005` files from `~/.local/share/bbport/user/savedata/1/CUSA00207/SPRJ0005`
- [x] T021 [US5] Verify save import integrity by checking file sizes (1,310,720 bytes for `userdata0000`, 262,144 bytes for `backup0010`) and loading imported campaign save in `bbhost` per [quickstart.md](quickstart.md) Scenario 4

**Checkpoint**: User Story 5 complete — `bbport` campaign saves safely imported into `bbhost`.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, performance validation, and repository standards

- [x] T022 [P] Document technical findings, plugin architecture, save import procedures, and build steps in `BB_PSX_DEMAKE_GUIDE.md` per Constitution Principle V
- [x] T023 Execute full regression validation suite per [quickstart.md](quickstart.md) (save preservation, 60 FPS pacing, sub-2GiB VRAM footprint, PSX visual inspection)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3+)**: Depend on Foundational phase completion
  - Phase 3 (US1: Runner Migration & Launch) is MVP
  - Phase 4 (US2: Retro Shaders Plugin) depends on US1
  - Phase 5 (US3: Luminance Dither) depends on US2 plugin skeleton
  - Phase 6 (US4: Live In-Game Controls) depends on US2 & US3
  - Phase 7 (US5: Import bbport Saves) can run after US1
- **Polish (Phase 8)**: Depends on all user stories being complete

### Parallel Opportunities

- T002 & T003 (Directories and Makefile)
- T006 & T007 (Wrapper script and Desktop entry)
- T010 & T014 (Plugin exports and Dither compute shader)
- T020 (Save import tool) in parallel with plugin work
- T022 & T023 (Documentation and regression testing)

### Implementation Strategy

1. Complete Setup + Foundational (compile `bbhost v0.2.32`, install to `/home/andre/Games/bbhost`, setup wrapper).
2. Complete US1 (MVP: verify `bbhost` runs).
3. Complete US5 (Import `bbport` campaign progress safely with backup).
4. Complete US2 & US3 (Build `lowpoly_overhaul.so` with vertex snap, affine mapping, luminance dither).
5. Complete US4 (In-game F9 controls).
6. Polish & Documentation.
