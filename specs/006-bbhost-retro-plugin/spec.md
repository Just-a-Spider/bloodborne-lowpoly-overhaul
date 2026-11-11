# Feature Specification: bbhost Runner Upgrade & Pure Retro Shaders Plugin

**Feature Branch**: `006-bbhost-retro-plugin`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "We need to remove the old version completely and install, preferably similarly to bbport on steam, the new bbhost-src (if possible rename it to just bbhost) too. Focus only on the retro shaders of bbport... a plugin idea may be enough."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean Runner Migration & Steam Launch Integration (Priority: P1)

As a player and developer of the Bloodborne Low Poly Overhaul, I want to replace the obsolete host installation with the modern `bbhost` runner (v0.2.32) without losing save files, and launch it directly from Steam or desktop shortcuts with dedicated GPU offloading, so that my game environment is unified, stable, and plugin-ready.

**Why this priority**: Without upgrading to modern `bbhost` (v0.2.32), required modern plugin APIs (render interception and shader manipulation) are unavailable, and player saves must be rigorously protected throughout migration.

**Independent Test**: Can be verified by removing the old runner directory while verifying save directory preservation, compiling/installing the new runner to `/home/andre/Games/bbhost`, executing the launcher script, and verifying that the game boots into the Hunter's Dream with existing character saves intact.

**Acceptance Scenarios**:
1. **Given** an existing `bbhost` installation with user save files in `~/.local/share/bbhost/data/saves`, **When** the migration process runs, **Then** all save files remain completely intact and untouched.
2. **Given** the clean `bbhost` installation, **When** launched through Steam or the terminal wrapper (`/home/andre/.local/bin/bbhost`), **Then** the game starts with dedicated GPU offload flags and runs at steady target frame rates.

---

### User Story 2 - Complete 32-Bit Retro Shading Parity via Pure Plugin (Priority: P1)

As a player of the Bloodborne Low Poly Overhaul, I want the retro graphics pipeline (screen-space vertex coordinate snapping, affine texture mapping without perspective correction, nearest-neighbor point filtering, and 240p decoupled render scaling) to run via a self-contained external plugin with zero modifications to the core engine, so that the game authentically looks like a 32-bit PlayStation era demake.

**Why this priority**: Visual demake authenticity is the foundational requirement for migrating from `bbport`. Both vertex snapping and affine texture warping must be present simultaneously to produce the characteristic PS1 aesthetic.

**Independent Test**: Can be tested by loading the plugin in `bbhost` and observing character and environment geometry: polygon vertices jump along a low-resolution grid during movement, textures exhibit perspective warping across surfaces, and texture filtering is sharp with no bilinear blur.

**Acceptance Scenarios**:
1. **Given** the retro plugin active, **When** moving the camera around geometry, **Then** vertex positions snap to the selected grid resolution (e.g. 240p) causing classic 3D vertex wobble.
2. **Given** the retro plugin active, **When** viewing surfaces at oblique angles, **Then** textures display affine linear interpolation (warping) rather than perspective-correct projection.
3. **Given** the retro plugin active, **When** inspecting fine surface detail, **Then** textures sample with nearest-neighbor point filtering without bilinear smoothing.

---

### User Story 3 - Clean Luminance Dithering in Dark Scenes (Priority: P2)

As a player exploring dark environments (such as Central Yharnam alleys and nighttime Hunter's Dream), I want the 15-bit color dithering effect to quantize luminance while strictly preserving color hue ratios, so that gradients have vintage dither cross-hatching without rainbow artifacts, color speckling, or noisy green/magenta tinting.

**Why this priority**: Built-in generic host dithering operates per RGB channel, producing severe color noise in dark scenes that degrades visual quality. Preserving luminance ratios ensures clean, authentic shading.

**Independent Test**: Can be tested by standing in a dark area (e.g. Hunter's Dream gravestones) and comparing the dithered output: shading transitions show clean monochrome Bayer cross-hatching while colors retain their exact hue ratios with zero rainbow speckles.

**Acceptance Scenarios**:
1. **Given** the retro plugin dithering active, **When** rendering dark scene gradients, **Then** the 4x4 Bayer pattern applies to luminance without causing chromatic hue drift.
2. **Given** the retro plugin dithering active, **When** rendering deep shadows or bright highlights, **Then** dither transitions attenuate smoothly to avoid harsh noise in extreme brightness levels.

---

### User Story 4 - Live In-Game Configuration & Hot-Toggling (Priority: P3)

As a player or content creator, I want to toggle and tune retro visual settings (vertex snap resolution, affine mapping, dithering, point filtering, audio downsampling) in real-time through an in-game menu or configuration file without restarting the game.

**Why this priority**: Real-time adjustment lets players tailor the demake aesthetic to their preference (e.g. choosing between subtle 480p snapping or aggressive 240p snapping) and capture immediate before/after visual comparisons.

**Independent Test**: Can be tested by opening the in-game overlay menu during gameplay, switching individual retro toggles on and off, and observing immediate graphical updates without restarting the application.

**Acceptance Scenarios**:
1. **Given** the game running, **When** an option (such as dithering or point filtering) is toggled in the menu, **Then** the visual effect updates immediately on the next rendered frame.
2. **Given** a customized setting saved, **When** restarting the game, **Then** previous settings reload automatically from configuration.

---

### User Story 5 - Import bbport Saves into bbhost (Priority: P2)

As a player migrating from `bbport`, I want to import my existing character progress and game saves from `bbport` (`~/.local/share/bbport/user/savedata/.../SPRJ0005`) into `bbhost` (`~/.local/share/bbhost/data/saves/SPRJ0005`) with automatic pre-import safety backups, so that I continue my campaign progress without starting over.

**Why this priority**: Preserving gameplay progress is essential for players migrating from `bbport` to `bbhost`. Saves must be validated and safely imported with zero risk of accidental data loss.

**Independent Test**: Can be tested by running the save import utility, verifying that a timestamped pre-import backup is created in `bbhost/data/saves/`, copying newer save containers from `bbport`, and booting `bbhost` to verify that character slots and lamp checkpoints load accurately.

**Acceptance Scenarios**:
1. **Given** existing saves in `bbport` and `bbhost`, **When** the import tool runs, **Then** the current `bbhost` save directory is backed up to a timestamped archive before any write occurs.
2. **Given** valid `bbport` save files (`userdata0000`, `backup0000`), **When** imported into `bbhost`, **Then** `bbhost` recognizes the character slots and loads the game at the exact save location.

---

### Edge Cases

- **Save Data Protection**: What happens if the old runner directory contains configuration or save backups? The migration process must strictly avoid modifying `~/.local/share/bbhost/data/saves` and backup user-specific configuration (`bbhost.toml`) before refreshing binaries.
- **Shader Compilation Interruption**: How does the system handle asynchronous shader recompilation when affine mapping is active? If an overridden shader fails to compile, it must gracefully fall back to vanilla rendering without crashing the application.
- **High Frame Rate Playback**: What happens to vertex snapping and dithering at 60 or 90 FPS? Snapping and dithering must remain locked to pixel grids without cumulative temporal drift or stutter.
- **UI & HUD Integrity**: How are menus, dialogue boxes, and vitals gauges handled? The 2D user interface must remain crisp, un-snapped, and rendered at native window resolution.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST preserve all player saves in `~/.local/share/bbhost/data/saves` without modification during all upgrade and migration operations.
- **FR-002**: System MUST install the latest compiled runner (`bbhost v0.2.32`) to the standard location (`/home/andre/Games/bbhost`) replacing the legacy binary.
- **FR-003**: System MUST provide a launcher wrapper and desktop shortcut that launches `bbhost` with dedicated GPU offload flags matching the existing `bbport` Steam environment.
- **FR-004**: System MUST deliver retro graphics capabilities strictly as a self-contained plugin (`lowpoly_overhaul.so`) without modifying core engine source files.
- **FR-005**: Plugin MUST support configurable screen-space vertex snapping with selectable grid resolutions (including 240p, 360p, and 480p).
- **FR-006**: Plugin MUST support perspective-incorrect (affine) texture mapping on 3D geometry.
- **FR-007**: Plugin MUST support nearest-neighbor (point) texture sampling for 3D world and character surfaces.
- **FR-008**: Plugin MUST provide a 4x4 Bayer dithering pass that quantizes luminance and locks color ratios, preventing rainbow chromatic noise on dark gradients.
- **FR-009**: Plugin MUST maintain standard high-resolution rendering for user interface, fonts, and heads-up displays, applying retro scaling and dithering only to 3D scene elements.
- **FR-010**: Plugin MUST support runtime configuration toggles via the in-game overlay menu and persistent configuration file.
- **FR-011**: System MUST provide an automated save import utility (`/home/andre/Games/reference/tools/import_bbport_saves.py`) that backs up existing `bbhost` saves before safely importing decrypted PS4 `SPRJ0005` save files from `bbport`.
- **FR-012**: All tooling, migration scripts, and plugin sources MUST reside outside this mod repository in `/home/andre/Games/reference/` to preserve repository clean-state.

### Key Entities

- **Runner Environment**: The host execution directory containing the `bbhost` binary, configuration files, logging facilities, and plugin runtime loaders.
- **Retro Plugin**: A compiled shared library (`lowpoly_overhaul.so`) residing in the runner's plugin directory that interfaces with the host graphics and presentation pipeline.
- **Presentation Target**: The final rendered 3D scene image before user interface compositing, subjected to low-resolution scaling, luminance dithering, and color quantization.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of existing user save files in `~/.local/share/bbhost/data/saves` load seamlessly in the upgraded runner without corruption or data loss.
- **SC-002**: Launching through Steam or desktop shortcut initializes `bbhost` and enters the game in under 10 seconds on dedicated GPU hardware.
- **SC-003**: Visual inspection confirms complete parity with `bbport` PR #419: vertex snapping, affine texture mapping, point filtering, and Bayer dithering are all simultaneously active and observable.
- **SC-004**: Dark gradient rendering exhibits zero chromatic hue shift or color noise (monochrome luminance dithering verified across nighttime lighting).
- **SC-005**: Core runner source code remains 100% pristine and unmodified across the migration.
- **SC-006**: Frame pacing sustains 60 FPS in Hunter's Dream and Central Yharnam on standard target hardware.
- **SC-007**: Saves imported from `bbport` via `/home/andre/Games/reference/tools/import_bbport_saves.py` load with 100% character integrity and zero progress loss in `bbhost`.

## Assumptions

- The host system runs Linux with Vulkan drivers and dedicated GPU offload capabilities (`offload --no-boost`).
- The `bbhost-src` repository contains all source code and submodules necessary to build `bbhost v0.2.32` locally using CMake and ninja/make.
- Steam shortcut integration can utilize the executable wrapper at `/home/andre/.local/bin/bbhost` mirroring the `/home/andre/.local/bin/bbport` setup.
- The base game files in `CUSA03173/` remain completely untouched, with low-poly modifications loaded from `CUSA03173-PSX/` or configured mod directories.
