# Feature Specification: Fix Dungeon Props Demake & Modular Mod Architecture

**Feature Branch**: `002-fix-dungeon-props-modularize`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "Fix: Some dungeon assets like the cages, regular and deformed were not demade. And large cadaver wastes shows as exploded blobs in dungeons. Part of the map demake, we could work on separating the overhaul from map, armors, etc. Also add into the project composition, audits of finished jobs must be done with another agy model like sonnet 4.6. Note: Deliverable of the UI mod is also the mod in the mods/ folder for bbport. Maps integrate not only dungeon props. All items that are part of environment apply there. A separation of objects may be crucial for maps and separated props to be more safe."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fix Exploded Cadaver Wastes in Dungeons (Priority: P1)

As a player exploring Chalice Dungeons, I want cadaver waste heaps and mass corpse piles to render as stable, grounded low-poly retro models with planar facet shading, so that my field of view is completely free of gigantic distorted polygon sheets, jagged geometry explosions, or camera-clipping planar spikes.

**Why this priority**: Mesh explosions severely compromise visual immersion, block dungeon corridors, clip through the player camera, and obscure enemies and traps in dark dungeon chambers.

**Independent Test**: Can be tested independently by loading a Chalice Dungeon containing cadaver waste heaps: verify corpses render as stable grounded faceted props with zero vertices displaced into the ceiling or room void.

**Acceptance Scenarios**:

1. **Given** player enters a dungeon chamber with cadaver waste piles, **When** the camera approaches or pans around the corpse heap, **Then** all vertices remain tightly bound to the ground plane with zero stretched polygon sheets protruding into the room.
2. **Given** player attacks near or walks over the cadaver waste prop, **When** physics and camera collision evaluate, **Then** player collision boundaries remain aligned with the floor without snagging on displaced invisible vertices.

---

### User Story 2 - Demake Regular and Deformed Dungeon Cages (Priority: P1)

As a player navigating dungeon corridors and torture chambers, I want all cylindrical hanging cages, ground cages, and deformed torture cages to feature authentic 32-bit low-poly faceted geometry and 15-bit color quantization, so that dungeon props visually harmonize with the demade character and world models.

**Why this priority**: Cages are prominent landmark props in Bloodborne dungeons. High-poly smooth cylindrical bars stand out jarringly against low-poly surroundings, breaking retro aesthetic cohesion.

**Independent Test**: Can be tested independently by inspecting hanging cages, free-standing cages, and deformed torture cages in Chalice Dungeons: verify polygon counts conform to retro budget and facet normals display crisp retro shading.

**Acceptance Scenarios**:

1. **Given** player encounters a hanging or ground cage in a dungeon, **When** viewed under direct light, **Then** the cage bars and frame exhibit clean faceted retro geometry without smooth high-poly curves.
2. **Given** player observes a deformed or bent torture cage, **When** inspecting from any angle, **Then** the deformed shape retains authentic retro angularity while maintaining intact physical boundaries and rigging stability.

---

### User Story 3 - Five-Pillar Modular Mod Architecture for bbport (Priority: P2)

As a player or modder using `bbport` / mod managers, I want the Bloodborne low-poly overhaul separated into five independent modular mod pillars under `mods/`:
1. **Maps & Environment (`map/`)**: World and dungeon architecture, terrain, room chunks, vistas, and environment BXF textures.
2. **Props & Objects (`obj/`)**: Scenery props, mechanisms, doors, ladders, chests, cages, and cadaver waste heaps. Separated from static maps to isolate collision (`.hkx`), interaction dummies, and moving parts.
3. **Armors and Weapons (`parts/`)**: Player attire with dynamic Cloth Physics or decoupled Flat Stiff options, trick weapons, and firearms.
4. **Characters (`chr/`)**: Enemies, bosses, Plain Doll (`c8030`), and friendly NPCs.
5. **UI & HUD (`menu/`)**: Standalone retro heads-up display, vitals gauges, interaction frames, and milestone announcement banners.

so that I can selectively toggle, combine, or update components according to visual preference, hardware capabilities, and testing safety.

**Why this priority**: Monolithic all-in-one packaging forces an all-or-nothing approach. Modular delivery with props separated from maps ensures that prop fixes and collision adjustments cannot destabilize static world geometry.

**Independent Test**: Can be tested independently by enabling individual mod folders in `mods/` through `bbport` configuration: verify each package functions autonomously without missing asset errors.

**Acceptance Scenarios**:

1. **Given** a player enables only the Retro HUD and UI mod, **When** launching the game, **Then** the retro HUD loads cleanly alongside standard world assets.
2. **Given** a player enables modular Maps and Props & Objects alongside either Cloth Physics or Flat Stiff Armors, **When** traveling between Hunter's Dream and Chalice Dungeons, **Then** assets stream seamlessly without crashes or directory path conflicts.
3. **Given** a player modifies or updates Props & Objects, **When** testing in-game, **Then** Maps and Characters remain completely unaffected, guaranteeing safety against world corruption.
4. **Given** a mod manager audits `mods/`, **When** inspecting directory structure, **Then** each pillar contains only its dedicated directory tree (`map/`, `obj/`, `parts/`, `chr/`, `menu/`).

---

### User Story 4 - Multi-Model Quality Audit Workflow (Priority: P3)

As a project maintainer, I want completed asset batches and pipeline passes audited by an independent alternate agent model (Sonnet 4.6 in AGY) before final acceptance, so that single-model blind spots, un-demaked asset omissions, and geometric deformation anomalies are systematically caught.

**Why this priority**: Multi-model adversarial review ensures that high-poly bypass oversights (such as untouched cages) and decimation regressions (such as cadaver waste explosions) are caught automatically prior to release.

**Independent Test**: Can be tested independently by executing the cross-model audit harness against modified asset stages, producing a signed verification audit report.

**Acceptance Scenarios**:

1. **Given** a prop demake pass completes, **When** the multi-model audit runs, **Then** the alternate model performs an independent inspection of modified models, verifying polygon budgets, bone alignments, and absence of visual regressions.
2. **Given** any discrepancy is identified by the auditor, **When** evaluating the audit report, **Then** the pipeline halts and reports specific offending asset IDs for immediate remediation.

---

### Edge Cases

- **Multi-Bone Animated Cages vs Rigid Props**: Some dungeon cages have animated doors or swing animations (`.anibnd`), while others are static props. The decimation pipeline must distinguish between bone-local unskinned props and armature-rigged dynamic objects to prevent coordinate detachment.
- **Corpse Pile Dummy Anchors**: Certain cadaver piles contain item pickup dummies (`o0006*`) or blood splat event markers. Modifying mesh geometry must preserve exact dummy coordinate anchors relative to world placement.
- **Layered Mod Overwrite Order in bbport**: When users enable multiple modular packages (e.g. Maps + Props + Armors + UI), the directory structure must adhere to `bbport` standard layout rules so mod priority resolves predictably without file corruption.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST resolve geometric exploding and planar vertex spikes on all dungeon cadaver waste and corpse pile assets, restoring stable grounded low-poly geometry with planar facet shading.
- **FR-002**: System MUST decimate and convert all regular and deformed dungeon cage assets to authentic low-poly retro geometry with flat facet normal shading.
- **FR-003**: System MUST preserve collision meshes (`.hkx`), interaction dummies, and physical boundaries for all modified dungeon props.
- **FR-004**: System MUST partition mod deliverables into five clean, independent modular mod packages located in `mods/` suitable for `bbport` loading:
  1. `mods/Bloodborne Retro Maps/` (`dvdroot_ps4/map/`)
  2. `mods/Bloodborne Retro Props and Objects/` (`dvdroot_ps4/obj/`)
  3. `mods/Bloodborne Retro Armors and Weapons - Cloth Physics/` and `mods/Bloodborne Retro Armors and Weapons - Flat Stiff/` (`dvdroot_ps4/parts/`)
  4. `mods/Bloodborne Retro Characters/` (`dvdroot_ps4/chr/`)
  5. `mods/Bloodborne Retro HUD and UI/` (`dvdroot_ps4/menu/`)
- **FR-005**: System MUST ensure each modular package in `mods/` operates independently or in layered combinations without missing dependencies or broken asset paths.
- **FR-006**: System MUST maintain strict immutability of the pristine retail game directory (`CUSA03173/`).
- **FR-007**: System MUST enforce an independent multi-model quality audit (utilizing an alternate AGY model like Sonnet 4.6) for validation and sign-off on finished asset pipelines.
- **FR-008**: System MUST deliver and verify the Retro HUD and UI mod as a standalone addition mod inside `mods/` for `bbport`.

### Key Entities

- **Dungeon Prop Asset**: An individual interactive or scenery model in Chalice Dungeons (cages, cadaver wastes, altars, mechanisms) containing 3D geometry, material parameters, collision meshes, and optional animation binders.
- **Modular Mod Package**: An isolated directory within `mods/` structured with a `dvdroot_ps4/` tree that delivers a specific feature slice (Maps, Props, Armors, Characters, UI) capable of being toggled independently in `bbport`.
- **Cross-Model Audit Report**: A structured quality assessment produced by an alternate model evaluating geometric integrity, polygon budgets, texture quantization, and absence of visual regressions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% elimination of exploded vertex spikes across all Chalice Dungeon cadaver waste and corpse pile assets in visual and bounding-box inspection.
- **SC-002**: 100% of dungeon cage variants (both regular and deformed) converted to low-poly retro specification with flat facet normals.
- **SC-003**: All five modular mod pillars in `mods/` load successfully in `bbport` with modular toggling verified across Maps, Props, Armors & Weapons, Characters, and UI/HUD.
- **SC-004**: Cross-model audit completed with 0 un-demaked asset omissions or deformation regressions reported.
- **SC-005**: Pristine `CUSA03173/` retail baseline maintains 100% bit-for-bit cryptographic immutability.

## Assumptions

- Cadaver waste explosions are caused by unskinned bone offset loss or degenerate triangle decimation during asset processing, fixable via bone-local coordinate preservation.
- Cages were previously bypassed due to automated `.anibnd` or composite heuristic rules; selective decimation can be applied while protecting moving hinges and physics.
- `bbport` loads mods hierarchically from `mods/`, supporting multiple modular subfolders layered according to user priority.
