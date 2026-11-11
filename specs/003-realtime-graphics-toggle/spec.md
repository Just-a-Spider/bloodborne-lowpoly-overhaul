# Feature Specification: In-Game On-Demand Retro Mod Switcher

**Feature Branch**: `003-realtime-graphics-toggle`  
**Created**: 2026-11-09  
**Status**: Clarified  
**Input**: User description: "Feature: In-game on-demand mod activation/deactivation similar to Halo CE remake on Xbox 360, possible?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - On-Demand Mod Switch via Stick Combination (Priority: P1)

As a player exploring Yharnam or resting at a lantern, I want to press L3 + R3 simultaneously to trigger a fast in-engine visual reload that switches between the pristine modern high-definition presentation and the authentic 32-bit retro demake (all 5 asset pillars), so that I can compare aesthetics and play in my preferred style without closing or relaunching the game.

**Why this priority**: Core value of the feature. Delivers seamless aesthetic switching without requiring the user to quit to desktop, relaunch `bbport`, or manually toggle folders.

**Independent Test**: Can be tested in Central Yharnam or Hunter's Dream by pressing L3 + R3 during exploration or at a lantern; observe a smooth 200ms fade transition into a quick checkpoint reload (~2s) that returns with swapped 3D meshes (Hunter, enemies, environment props, maps) and retro textures.

**Acceptance Scenarios**:

1. **Given** the player is playing with vanilla presentation, **When** pressing L3 + R3 simultaneously, **Then** the screen smoothly cross-dissolves (200ms) into a fast checkpoint reload, and the game reappears with the full 5-Pillar Retro Mod active.
2. **Given** the player is playing with the retro mod active, **When** pressing L3 + R3 again, **Then** the game reloads and returns to pristine modern HD graphics.
3. **Given** active gameplay state, **When** the mod reload occurs, **Then** player position, health, inventory, blood echoes, and enemy boss states remain 100% intact.

---

### User Story 2 - Synchronized Full-Pillar & HUD Transition (Priority: P2)

As a player toggling presentation modes, I want all five asset pillars (Maps, Props, Armors/Weapons, Characters, and HUD/UI) to swap together simultaneously, so that the entire visual presentation (3D world, entities, gauges, dialogue boxes) remains 100% cohesive with zero mismatched high-poly/low-poly elements.

**Why this priority**: Visual integrity. Having low-poly props with high-poly characters or high-res UI over chunky texels ruins the retro immersion.

**Independent Test**: Trigger mode switch and verify in the loaded scene that character models (`chr/`), weapons and armor (`parts/`), dungeon props/cages (`obj/`), architecture (`map/`), and HUD gauges (`menu/`) all reflect the targeted visual mode.

**Acceptance Scenarios**:

1. **Given** modern presentation, **When** switching to retro mode, **Then** all 5 modular pillars activate in unison on the subsequent scene load.
2. **Given** retro presentation, **When** switching to modern mode, **Then** all 5 modular pillars deactivate in unison, restoring baseline vanilla assets.

---

### User Story 3 - Visual Profile State Persistence & Smooth Recovery (Priority: P3)

As a player who prefers a specific visual style, I want my active presentation mode to be remembered across map transitions, death respawns, and game sessions, so that I do not have to re-toggle my preferred visual style every time I warp or restart.

**Why this priority**: Quality of life and session continuity. Prevents frustration from having to repeatedly toggle modes after death or area travel.

**Independent Test**: Set mode to retro, warp to Hunter's Dream or intentionally die to an enemy, and confirm that the respawn screen and destination map initialize directly in retro mode.

**Acceptance Scenarios**:

1. **Given** the player has selected retro mode, **When** warping between Hunter's Dream and Chalice Dungeons, **Then** the destination area loads directly into retro mode without requiring an extra toggle.
2. **Given** the player exits the game in retro mode, **When** relaunching the game, **Then** the initial title menu and loaded save state preserve the retro visual presentation.

---

### Edge Cases

- **Toggle During Active Combat**: Toggling L3 + R3 during combat prompts the fast checkpoint reload; player respawns at nearest lantern or stable checkpoint anchor without loss of echoes or state corruption.
- **Toggle During Boss Encounters**: Disallow accidental L3+R3 triggers during active boss cutscenes or lock-on dodge maneuvers by requiring an intentional dual-stick press or lantern menu confirmation.
- **Rapid Input Spam**: If user presses L3 + R3 repeatedly, input is debounced (minimum 3-second lockout between reload requests).
- **VRAM & Memory Stability**: Hot-swapping active asset layers via clean in-engine reload ensures GPU buffers from previous mode are freed prior to allocating the new mode's buffers, remaining safely under the 2,048 MiB VRAM budget on 4GB hardware.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide dedicated input binding: simultaneous L3 + R3 stick click (with optional lantern menu prompt) to request visual mode switch.
- **FR-002**: System MUST execute visual mode switch via fast checkpoint/lantern quick reload (~2s) that hot-swaps active 3D assets, textures, and HUD between Vanilla baseline and the 5-Pillar Retro Mod without terminating `bbhost`.
- **FR-003**: System MUST bind the on-demand toggle command to L3 + R3 simultaneous stick click.
- **FR-004**: System MUST perform a smooth 200ms cross-dissolve / fade transition into the reload sequence.
- **FR-005**: System MUST ensure player progress, blood echoes, position, and quest flags remain strictly preserved during the mod hot-swap reload.
- **FR-006**: System MUST swap all 5 modular pillars simultaneously (Maps, Props, Armors/Weapons, Characters, HUD/UI) to maintain complete aesthetic unity.
- **FR-007**: System MUST persist the user's active presentation mode across area transitions, respawns, and game restarts.
- **FR-008**: System MUST maintain strict immutability of the pristine retail baseline (`CUSA03173/`) and player save files.

### Key Entities

- **Visual Presentation Profile**: Active aesthetic configuration (Retro 32-Bit Mode vs Modern HD Mode), dictating mounted asset layer (`mods/` 5-pillar overlay vs pristine `CUSA03173/`).
- **In-Engine Mod Hot-Swap Controller**: Runtime coordinator that intercepts L3+R3, triggers 200ms cross-dissolve, signals `bbport` filesystem layer to redirect asset mounts, and requests engine checkpoint reload.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Visual presentation switch executes via clean in-engine reload within 2.5 seconds from trigger to player regaining control.
- **SC-002**: 0 gameplay state corruption, loss of blood echoes, or physics glitches occur during reload.
- **SC-003**: 100% of 5 modular pillars (Maps, Props, Armors, Characters, HUD) transition in exact synchrony.
- **SC-004**: Total VRAM footprint remains under 2,048 MiB on target hardware across mode transitions.
- **SC-005**: 100% of player save files and vanilla game assets remain unmodified.

## Clarifications

### Clarification Session 2026-11-09
- **Q1: Architectural Scope**: Given that `bbport` loads mods into memory via `out/mod-game-*` symlinks at boot and FromSoft's engine has no native dual-mesh VRAM swap, which architecture should Feature 003 implement?
  - **Resolution**: Lantern/Reload Mod Switcher. L3+R3 or lantern interaction prompts a quick in-engine reload (~2s checkpoint reload) hot-swapping actual low-poly 3D models/textures between Vanilla and the 5-Pillar Retro Mod.
- **Q2: Input Binding**: Which input binding should trigger the mode toggle?
  - **Resolution**: L3 + R3 simultaneous stick click.
- **Q3: Visual Transition Effect**: What visual transition effect should occur when toggling modes?
  - **Resolution**: Smooth cross-dissolve / fade transition (200ms) leading into the fast reload.
