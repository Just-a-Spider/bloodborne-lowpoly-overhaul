# Feature Specification: Native In-Game Lantern Mod Switcher (MOAL-Style)

**Feature Branch**: `004-native-lantern-switcher`  
**Created**: 2026-11-09  
**Status**: Draft  
**Input**: User description: "Yeah, let's try to implement a more native mod for this feature"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Native In-Game Lantern Presentation Menu (Priority: P1)

As a Hunter resting at any lamp post in Yharnam or Hunter's Dream, I want to see a dedicated in-game dialogue option when interacting with the lantern (e.g., "Switch to Retro 32-Bit Demake" or "Restore Modern High-Definition") alongside the standard warp options, so that I can configure my game's visual presentation entirely within the game's authentic UI without alt-tabbing or running external command-line tools.

**Why this priority**: Core user experience. Delivering an in-game lantern menu option (similar to community quality-of-life mods like Mother of All Lanterns) embeds the demake switch directly into FromSoftware's diegetic interface.

**Independent Test**: Can be tested at the 1st Floor Sickroom lantern or Central Yharnam lantern by walking up to the lamp, pressing Cross (interact), and verifying that the lantern interaction dialogue displays the toggle menu choice with readable localized text.

**Acceptance Scenarios**:

1. **Given** the player is in Modern HD mode, **When** interacting with any active lantern, **Then** the dialogue menu displays the option "Switch to Retro 32-Bit Demake".
2. **Given** the player is in Retro 32-Bit mode, **When** interacting with any active lantern, **Then** the dialogue menu displays the option "Restore Modern High-Definition".
3. **Given** the player cancels out of the lantern menu (pressing Circle), **When** returning to gameplay, **Then** normal movement resumes immediately without triggering a scene reload.

---

### User Story 2 - Seamless Diegetic Reload upon Selection (Priority: P2)

As a player selecting the visual switch option at a lantern, I want the Hunter to perform the native lantern kneeling/dissolve animation followed by a fast checkpoint reload, re-emerging at the lantern with all 3D geometry, textures, and HUD elements converted to the targeted visual mode, so that the transition feels like a natural in-universe awakening rather than an abrupt glitch.

**Why this priority**: Immersion and technical safety. Anchoring the reload to the lantern warp sequence leverages the game engine's native level reloading cycle, ensuring 100% clean memory deallocation and zero physics corruption.

**Independent Test**: Select the toggle option at a lantern; observe the Hunter kneeling animation, screen fade, ~2s reload, and reappearance at the same lantern with the new visual presentation active.

**Acceptance Scenarios**:

1. **Given** the player confirms the presentation switch at a lantern, **When** the choice is registered, **Then** the native lantern dissolution animation plays and the screen fades to black.
2. **Given** the reload completes, **When** the screen fades back in, **Then** the Hunter awakens at the lantern with all 5 asset pillars (maps, props, armors, characters, HUD) displaying the new visual mode.
3. **Given** active character status, **When** the lantern reload finishes, **Then** player blood echoes, inventory items, insight, and world quest flags remain 100% intact.

---

### User Story 3 - Persistence & Universal Lantern Availability (Priority: P3)

As a player progressing through the game, I want the presentation toggle option to be available at every standard lantern (including Chalice Dungeon lanterns and boss arena lanterns), and for my active choice to persist across map warps, deaths, and future game sessions.

**Why this priority**: Polish and continuity. Ensures the feature is universally accessible regardless of where the player travels.

**Independent Test**: Travel between Hunter's Dream, Central Yharnam, and a Chalice Dungeon; verify that lanterns in all zones present the toggle option and maintain the chosen aesthetic across zone transitions.

**Acceptance Scenarios**:

1. **Given** the player switches to retro mode at Central Yharnam, **When** dying or warping to Hunter's Dream, **Then** the destination loads directly in retro mode.
2. **Given** the player discovers a new lantern after defeating a boss, **When** lighting and interacting with the new lamp, **Then** the presentation toggle option is available on that lamp.

---

### Edge Cases

- **Lantern Interaction with Aggroed Enemies**: If an enemy attacks while the lantern menu is open, standard FromSoftware poise/hit-reaction rules apply; if the player takes damage before confirming, the menu closes gracefully without corrupting reload state.
- **Unlit / Inactive Lanterns**: The presentation toggle must only appear on ignited/active lanterns, not unlit props.
- **Chalice Dungeon Layer Elevators**: Toggling presentation at a Chalice Dungeon lantern must preserve elevator state and floor coordinates without causing elevator shafts to disappear.
- **Rapid Menu Selection**: Repeatedly selecting the option or mashing confirm will execute a single atomic reload cycle; subsequent requests are debounced until the player fully regains control.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST integrate a custom dialogue option into the native lantern interaction menu.
- **FR-002**: System MUST dynamically adapt the dialogue prompt text to indicate the opposing mode ("Switch to Retro 32-Bit Demake" vs "Restore Modern High-Definition").
- **FR-003**: System MUST trigger the native lantern kneeling/warp animation upon confirmation of the toggle option.
- **FR-004**: System MUST execute a quick checkpoint reload (~2s) that reconstructs the scene using the selected asset profile.
- **FR-005**: System MUST swap all five modular asset pillars (Maps, Props, Armors/Weapons, Characters, HUD/UI) in complete synchronization during the reload.
- **FR-006**: System MUST preserve player blood echoes, insight, inventory, and quest flags bit-for-bit across the reload.
- **FR-007**: System MUST support universal availability across all valid active lanterns in standard maps and Chalice Dungeons.
- **FR-008**: System MUST persist the chosen visual presentation mode across area transitions, respawns, and game restarts.
- **FR-009**: System MUST maintain strict immutability of the baseline retail game (`CUSA03173/`) and player save files.

### Key Entities

- **Lantern Interaction Menu**: The in-game dialogue interface displayed when interacting with an ignited lantern prop.
- **Visual Presentation State**: The active aesthetic configuration (Retro 32-Bit Demake vs Modern HD Baseline).
- **Reload Transition Controller**: The subsystem that catches the lantern toggle selection, redirects the active asset mounts, and supervises the scene reconstruction.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of ignited lanterns present the visual presentation toggle option in their interaction dialogue.
- **SC-002**: Visual mode transition completes within 2.5 seconds from dialogue confirmation to player regaining control.
- **SC-003**: 0 loss of blood echoes, insight, or player inventory during lantern-triggered reloads.
- **SC-004**: 100% of asset pillars (maps, scenery, gear, entities, UI) transition simultaneously with zero visual mismatches.
- **SC-005**: 100% of player save files in `~/.local/share/bbhost/data/saves` and baseline `CUSA03173/` files remain unmodified.

## Assumptions

- The FromSoftware talk script and menu message systems support adding a custom dialogue selection to the lantern interaction flow.
- The game's native checkpoint reload / bonfire warp routine safely unloads and reloads map and character asset containers from the active virtual filesystem overlay.
- Gameplay combat statistics, damage values, weapon scaling, and hitboxes remain strictly identical between both visual modes.
