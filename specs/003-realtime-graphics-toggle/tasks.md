# Tasks: In-Game On-Demand Retro Mod Switcher

**Input**: Design documents from `/specs/003-realtime-graphics-toggle/`  
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)  

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create pipeline directory structure and test fixtures under tools/pipeline/ and tools/fixtures/switcher/
- [x] T002 [P] Create JSON schema contract validation utility in tools/fixtures/switcher/validate_schema.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Implement core domain types and enumerations in tools/pipeline/mod_switcher_types.py quoting VisualMode ("VANILLA_HD", "RETRO_5PILLAR"), TransitionPhase ("IDLE", "FADING_OUT", "SWAPPING_OVERLAY", "TRIGGERING_RELOAD", "AWAITING_SCENE_LOAD", "FADING_IN"), and ToggleInputState constraints verbatim from data-model.md
- [x] T004 [P] Implement persistent configuration manager in tools/pipeline/mod_switcher_state.py enforcing schema validation against contracts/toggle_state_schema.json with atomic file writes to out/retro_toggle_state.json
- [x] T005 [P] Implement atomic symlink overlay redirection engine in tools/pipeline/mod_overlay_manager.py with dual-profile mounting (VANILLA_HD pointing to CUSA03173/dvdroot_ps4/, RETRO_5PILLAR pointing to mods/*/dvdroot_ps4/)

**Checkpoint**: Foundation ready - user story implementation can begin.

---

## Phase 3: User Story 1 - On-Demand Mod Switch via Stick Combination (Priority: P1) [MVP]

**Goal**: Deliver in-engine mode toggle triggered by simultaneous L3 + R3 stick click with 200ms cross-dissolve fade and quick checkpoint reload (~1.5–2s) without process restart.

**Independent Test**: Execute `uv run python tools/verify_mod_switcher.py --test pad-chord` verifying that single L3/R3 are ignored, simultaneous L3+R3 triggers reload request, and rapid re-presses within 3000ms are debounced.

### Implementation for User Story 1

- [x] T006 [P] [US1] Implement pad chord detector and debouncer in tools/pipeline/pad_chord_detector.py sampling BTN_L3 (0x2) and BTN_R3 (0x4) with 3000ms lockout
- [x] T007 [P] [US1] Implement scene reload coordinator and 200ms fade transition state machine in tools/pipeline/scene_reload_coordinator.py
- [x] T008 [US1] Integrate pad chord detector, overlay manager, and reload coordinator in tools/pipeline/in_game_mod_switcher.py
- [x] T009 [US1] Implement automated test harness for chord detection and reload dispatch in tools/verify_mod_switcher.py (test_pad_chord)
- [x] T010 [US1] Validate User Story 1 independently with `uv run python tools/verify_mod_switcher.py --test pad-chord`

**Checkpoint**: User Story 1 fully functional and testable independently (MVP complete).

---

## Phase 4: User Story 2 - Synchronized Full-Pillar & HUD Transition (Priority: P2)

**Goal**: Ensure all 5 modular pillars (Maps, Props, Armors/Weapons, Characters, HUD/UI) pivot simultaneously during reload with zero mismatched high-poly/low-poly assets.

**Independent Test**: Execute `uv run python tools/verify_mod_switcher.py --test overlay-swap` verifying that all 5 pillar mount points atomically update and resolve to the target profile with 0 broken links.

### Implementation for User Story 2

- [x] T011 [P] [US2] Implement 5-pillar synchronization mapper in tools/pipeline/mod_overlay_manager.py covering map/, obj/, parts/, chr/, and menu/
- [x] T012 [P] [US2] Implement VFS integrity validator in tools/pipeline/mod_overlay_manager.py asserting zero broken symlinks and 100% target file accessibility
- [x] T013 [US2] Implement 5-pillar atomic swap automated test in tools/verify_mod_switcher.py (test_overlay_swap)
- [x] T014 [US2] Validate User Story 2 independently with `uv run python tools/verify_mod_switcher.py --test overlay-swap`

**Checkpoint**: User Stories 1 AND 2 both work independently and in combination.

---

## Phase 5: User Story 3 - Visual Profile State Persistence & Smooth Recovery (Priority: P3)

**Goal**: Persist active presentation profile across area warps, deaths, and session restarts.

**Independent Test**: Execute `uv run python tools/verify_mod_switcher.py --test persistence` verifying that out/retro_toggle_state.json retains state and initializes the active profile correctly after simulated reboot.

### Implementation for User Story 3

- [x] T015 [P] [US3] Implement synchronization between out/retro_toggle_state.json and bbport mods.json profile in tools/pipeline/mod_switcher_state.py
- [x] T016 [US3] Implement persistence and session recovery automated test in tools/verify_mod_switcher.py (test_persistence)
- [x] T017 [US3] Validate User Story 3 independently with `uv run python tools/verify_mod_switcher.py --test persistence`

**Checkpoint**: All three user stories functional and independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, system-wide test execution, and adversarial quality audit

- [x] T018 [P] Document in-engine mod switcher architecture and pad chord controls in BB_PSX_DEMAKE_GUIDE.md Section 16
- [x] T019 [P] Document VFS atomic swap mathematical models and reload timings in BB_PSX_DEMAKE_MATH_AND_FINDINGS.md Section 31
- [x] T020 Update ACTIVE_PLANS.md with Plan 11 tracking in-engine mod switcher milestones
- [x] T021 Run complete automated verification suite with `uv run python tools/verify_mod_switcher.py --all`
- [x] T022 Execute multi-model adversarial quality audit with `uv run python tools/pipeline/run_adversarial_audit.py`

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) - BLOCKS User Stories.
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2).
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) and integrates with User Story 1.
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) and integrates with User Stories 1 & 2.
- **Polish (Phase 6)**: Depends on all user stories being verified.

### Parallel Opportunities
- T001 and T002 can run in parallel.
- T004 and T005 can run in parallel within Phase 2.
- T006 and T007 can run in parallel within Phase 3.
- T011 and T012 can run in parallel within Phase 4.
- T018 and T019 can run in parallel within Phase 6.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1).
3. Validate User Story 1 independently with `uv run python tools/verify_mod_switcher.py --test pad-chord`.
4. Demonstrate MVP in-engine switching via stick chord.

### Incremental Delivery
1. Foundation Ready: Core types, atomic VFS engine, state manager.
2. Increment 1 (MVP): L3+R3 chord detection, 200ms fade, in-engine reload trigger.
3. Increment 2: All 5 modular pillars synchronized across map, obj, parts, chr, menu.
4. Increment 3: State persistence across deaths, warps, and session relaunches.
5. Polish: Documentation sync and adversarial quality sign-off.
