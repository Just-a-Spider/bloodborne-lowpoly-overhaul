# Feature Specification: Fix Research Hall Interactive Stairs and Lady Maria Cloth Physics

**Feature Branch**: `007-fix-stairs-maria-cloth`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Nursary Hall has some interactible stairs invicible, I suspect of a coordinates issues in he demake pipelines. Also, Lady Maria boss figh have cloth problems on her hat or cape, leaving some assets in place as she moves. CAn you take a look and fix? Also, Set the 007 as 000 and never commit that feature as it is non-mod related. After finishing the fixes, create the new patches needed on the domains, commit, push and release 1.2.1 with those fixes"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Research Hall Interactive Stairs and Ladders Visibility (Priority: P1)

A player exploring the Research Hall (Patient Room Hall / Nursery, internal map `m35_00`) must be able to visually see, navigate, and interact with all rotating staircases, access rungs, and ladder props. None of the interactible stair elements should appear invisible, misplaced in world space, or detached from their collision mechanisms.

**Why this priority**: Navigating the Research Hall is mandatory for game progression to Lady Maria and the Fishing Hamlet. Invisible stairs and broken ladder rungs prevent player traversal, trap players in the lower patient ward, and break immersion.

**Independent Test**: Load into map `m35_00` or inspect the Research Hall stair props (`o353006`, `o353011`, `o353013`, `o243010`-`o243014`, and `o350501`-`o350504`). Confirm all steps, railings, rungs, and rotating mechanisms render completely and align with their physical interaction coordinates.

**Acceptance Scenarios**:

1. **Given** the player is in Research Hall (`m35_00`), **When** looking at the main interactive staircase mechanisms, **Then** all stair steps, railings, and structural supports are fully visible with intact geometry and accurate bounding coordinates.
2. **Given** the player activates the central stair rotation mechanism, **When** the stairs rotate into new positions, **Then** the visual models move in direct sync with their Havok collision meshes and interaction prompts.
3. **Given** the player climbs any vertical access ladder in Research Hall, **When** ascending or descending, **Then** all ladder rungs (`o35050*`) remain visible and positioned accurately at their operational heights without collapse.

---

### User Story 2 - Lady Maria Boss Fight Cloth & Hat Mesh Synchronization (Priority: P1)

A player encountering Lady Maria in the Astral Clocktower (or equipping the Maria Hunter garb and hat) must observe her hat feathers and cape/garb mantle moving smoothly with her character model. No detached cloth fragments, floating feathers, or stationary meshes should remain anchored in space during animations or dashes.

**Why this priority**: Lady Maria is one of the centerpiece boss encounters in the game. Having feathers or cape geometry frozen in place while she moves breaks visual quality and ruins the retro PSX aesthetic.

**Independent Test**: Spawn or fight Lady Maria (`c9300` / armor set `9300`) and execute movement, dashes, and attack sequences. Confirm that all submeshes in `hd_f_9300` and `bd_f_9300` (and male variants) track character skeletal motion without detached geometry remaining at the spawn point.

**Acceptance Scenarios**:

1. **Given** Lady Maria moves, dashes, or attacks across the arena, **When** observing her feathered tricorn hat (`hd_f_9300`), **Then** the feather meshes remain firmly attached to her head and follow her motion continuously.
2. **Given** Lady Maria performs combat animations, **When** observing her mantle and cape (`bd_f_9300`), **Then** the cape geometry follows her torso and spine movements without leaving detached stationary meshes suspended in air.
3. **Given** player uses either the Cloth Physics edition or Flat Stiff edition of the Retro Armors mod, **When** equipping the Maria Hunter set, **Then** both editions correctly synchronize cloth elements to the character skeleton.

---

### User Story 3 - Pipeline Whitelist and Hierarchy Preservation (Priority: P2)

The 3D demake asset pipelines (`batch_blender_demake_obj.py` and `batch_blender_demake_parts.py`) must permanently protect multi-bone interactive prop mechanisms and unparented cloth dummy bones from improper decimation, coordinate stripping, or disconnection.

**Why this priority**: Prevents regressions during future asset builds and ensures repeatable, automated generation of retro props and armors.

**Independent Test**: Run pipeline verification checks against prop models and armor parts. Verify that interactive stairs and Maria set pieces pass all geometric and skeletal bounds tests.

**Acceptance Scenarios**:

1. **Given** the prop demake script processes interactive mechanisms (`o24301*`, `o35300*`, `o35050*`), **When** decimation filters execute, **Then** these models are bypassed or preserved with complete bone translation hierarchies and pristine FLVER structures.
2. **Given** the parts demake pipeline processes cloth meshes with dummy bones, **When** generating stiff retro armors, **Then** dummy bones are safely re-parented to the character skeletal root bones (e.g. Head, Spine, Neck) so meshes cannot float freely.

---

### User Story 4 - Packaging, Differential Patching, and Release 1.2.1 (Priority: P2)

Packaging tools must bundle the corrected props and armor sets into the 5 modular mod directories, generate unified differential XOR patches with SHA256 integrity checks, update release documentation to version 1.2.1, and verify that non-mod experimental features (feature 000) remain excluded from Git tracking.

**Why this priority**: Delivers the completed fixes to users in both modular format and single-file patch format for easy distribution.

**Independent Test**: Execute `package_modular_mods.py` and `create_patch.py`, followed by automated patch verification tests and Git status validation.

**Acceptance Scenarios**:

1. **Given** fixed assets in `CUSA03173-PSX/`, **When** packaging runs, **Then** updated props and armor sets appear in `mods/Bloodborne Retro Props and Objects/` and `mods/Bloodborne Retro Armors and Weapons - *`.
2. **Given** updated distribution containers, **When** `create_patch.py` runs, **Then** differential patch `bloodborne_lowpoly_overhaul.patch` and `dist/SHA256SUMS.txt` are refreshed for version 1.2.1.
3. **Given** repository status, **When** committing changes, **Then** feature `000` (`specs/000-thd-pvp-coop-restore` and assessment notes) is completely ignored and excluded from commit staging.

---

### Edge Cases

- What happens if a player loads a save file already standing in Research Hall?
  The corrected prop FLVER files in `obj/` are loaded directly by the engine without requiring save conversion or restart.
- What happens if a player uses the Flat Stiff variant of retro armors where Havok physics files (`.hkx`) are omitted?
  The dummy bones of feather and mantle meshes must be re-parented to the main skeleton so the rigid geometry follows the player/boss movement naturally.
- What happens if interactive stair mechanisms have multiple sub-objects in the map?
  All relevant variants (`o243010`-`o243014`, `o353006`, `o353011`, `o353013`, `o350501`-`o350504`) must be safeguarded to ensure full visual consistency across all floors of Research Hall.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST restore complete visibility and geometry for Research Hall interactive staircase mechanisms (`o243010`-`o243014`, `o353006`, `o353011`, `o353013`).
- **FR-002**: System MUST restore all multi-bone vertical access ladders and rungs in Research Hall (`o350501`-`o350504`), maintaining precise bone translations and physical step heights.
- **FR-003**: System MUST prevent decimation scripts from misidentifying interactive mechanisms (`o24301*`) as simple cage meshes.
- **FR-004**: System MUST eliminate stationary floating feather geometry on Lady Maria's hat (`hd_f_9300` and `hd_m_9300`) during character animations.
- **FR-005**: System MUST eliminate stationary floating cape/mantle geometry on Lady Maria's garb (`bd_f_9300` and `bd_m_9300`) during character animations.
- **FR-006**: In the Cloth Physics edition, the system MUST preserve active Havok dynamic solver references and physics data for Maria armor set 9300.
- **FR-007**: In the Flat Stiff edition, the system MUST bind unparented dummy cloth bones to their corresponding parent skeletal nodes (e.g. Head for hat feathers, Spine2/Neck for cape).
- **FR-008**: System MUST update modular mod packages under `mods/` with the repaired props and armor sets.
- **FR-009**: System MUST generate updated differential distribution patches and release notes for version 1.2.1.
- **FR-010**: System MUST strictly exclude non-mod experimental feature specifications (feature 000) from version control tracking and commits.

### Key Entities

- **Interactive Stair Props**: Movable environmental objects with multi-bone hierarchies and physics collision triggers in `m35_00` (`o353006`, `o353011`, `o353013`, `o243010`-`o243014`).
- **Access Ladder Props**: Segmented vertical climbable objects with discrete bone rungs (`o350501`-`o350504`).
- **Lady Maria Armor (Set 9300)**: Player and NPC parts container for headwear (`hd_f_9300`, `hd_m_9300`) and body armor (`bd_f_9300`, `bd_m_9300`), featuring feather and mantle cloth meshes.
- **Modular Mod Pillars**: Five decoupled distribution folders under `mods/` allowing granular mod loading in `bbport`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Research Hall stair and ladder props (`o24301*`, `o35300*`, `o35050*`) exhibit non-zero vertex counts and valid bounding boxes matching vanilla operational dimensions.
- **SC-002**: 0 detached or stationary floating mesh artifacts remain suspended in space during Lady Maria boss fight animations or movement.
- **SC-003**: All automated test suites (`test_apply_patch.py`, prop verification, armor verification) pass with exit code 0.
- **SC-004**: Modular mod packages and differential distribution patch are refreshed and verified with valid SHA256 hashes.
- **SC-005**: Git repository clean state confirms `specs/000-*` is not staged or tracked in commits.

## Assumptions

- Vanilla assets in `CUSA03173/` remain untouched as the pristine source of truth.
- The stair coordinates issue is due to decimation and skeleton stripping in `batch_blender_demake_obj.py`, and can be fixed by whitelisting and restoring pristine FromSoftware geometry for those interactive mechanisms.
- The Maria cloth issue affects both the NPC boss fight and the player wearable version of set 9300.
- No other boss armor sets share this specific detached dummy bone structure, but the fix is extensible.
