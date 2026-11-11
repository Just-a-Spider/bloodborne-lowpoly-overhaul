# Tasks: Native In-Game Lantern Mod Switcher (MOAL-Style)

**Input**: Design documents from `/specs/004-native-lantern-switcher/`  
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)  

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Restoring pristine third-party assets, directory setup, and contract validation

- [ ] T001 Restore pristine MOAL talk binders from .bak copies in /home/andre/Games/bbport-src/mods/MOAL 107 2.1.0 2026-10-20T17-22Z xPW1O2eZ1/MOAL/dvdroot_ps4/script/talk/ removing broken in-place edits
- [ ] T002 [P] Create JSON schema contract validation utility in tools/fixtures/lantern/validate_contracts.py verifying contracts/lantern_menu_contract.json and contracts/event_flag_registry.json

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core domain types and test harness infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Implement domain models, flag constants, and EzState graph definitions in tools/pipeline/lantern_mod_types.py quoting constraints verbatim from data-model.md (LanternDialogueOption options [1, 20, 21, 99], EventFlagSignal flags [999901, 999902], and EzStateMenuGraph state flow)
- [ ] T004 [P] Implement FMG menu text injector in tools/pipeline/inject_lantern_menu_text.py adding text IDs 70011010 ("Switch to Retro 32-Bit Demake") and 70011011 ("Restore Modern High-Definition") into Entry 30 of menu.msgbnd.dcx
- [ ] T005 [P] Rewrite automated test suite harness in tools/verify_lantern_mod.py to validate EzState condition bytecode, assert SM 2147483644 State 7 calls SM 2147483639 (unlit ignition intact), assert SM 2147483500 condition 0 does not contain IsTalkExclusiveMenuOpen() == 0, and eliminate mock tautologies

**Checkpoint**: Foundation ready - user story implementation can begin.

---

## Phase 3: User Story 1 - Native In-Game Lantern Presentation Menu (Priority: P1) [MVP]

**Goal**: Deliver in-game dialogue prompt on lit lanterns showing "Switch to Retro 32-Bit Demake" or "Restore Modern High-Definition" directly inside FromSoftware's native UI while preserving unlit lamp ignition bit-for-bit.

**Independent Test**: Execute `uv run python tools/verify_lantern_mod.py --test talk-esd` verifying all 56 lamp Talk ESDs have State 7 calling SM 2147483639, State 6 calling SM 2147483500, and SM 2147483500 State 0 condition 0 free of frame 0 exit bugs.

### Implementation for User Story 1

- [x] T006 [P] [US1] Fix patch_vanilla_esd in tools/pipeline/inject_lantern_talk_esd.py: redirect ONLY State 6 in SM 2147483644 to SM 2147483500, preserve State 7 calling SM 2147483639, and construct SM 2147483500 State 0 with canonical choice/cancel conditions without IsTalkExclusiveMenuOpen() == 0
- [x] T007 [P] [US1] Fix patch_moal_esd in tools/pipeline/inject_lantern_talk_esd.py: insert Choices 20/21 into MOAL SM 2147483500 State 0 before Leave (99) and strictly preserve State 7 calling SM 2147483639
- [x] T008 [US1] Inject patched vanilla talk binders across all 16 maps into mods/Bloodborne Retro HUD and UI/dvdroot_ps4/script/talk/ and /home/andre/Games/bbport-src/mods/Bloodborne Retro HUD and UI/dvdroot_ps4/script/talk/ via tools/pipeline/inject_lantern_talk_esd.py
- [x] T009 [US1] Inject patched MOAL talk binders across all 16 maps into /home/andre/Games/bbport-src/mods/MOAL 107 2.1.0 2026-10-20T17-22Z xPW1O2eZ1/MOAL/dvdroot_ps4/script/talk/ via tools/pipeline/inject_lantern_talk_esd.py --patch-moal
- [x] T010 [P] [US1] Inject localized lantern toggle prompts into mods/Bloodborne Retro HUD and UI/dvdroot_ps4/msg/engus/menu.msgbnd.dcx and /home/andre/Games/bbport-src/mods/Bloodborne Retro HUD and UI/dvdroot_ps4/msg/engus/menu.msgbnd.dcx via tools/pipeline/inject_lantern_menu_text.py
- [x] T011 [US1] Validate User Story 1 independently with `uv run python tools/verify_lantern_mod.py --test fmg-injection` and `uv run python tools/verify_lantern_mod.py --test talk-esd`

**Checkpoint**: User Story 1 fully functional and testable independently (MVP complete).

---

## Phase 4: User Story 2 - Seamless Diegetic Reload upon Selection (Priority: P2)

**Goal**: Ensure selecting the toggle option triggers native lantern dissolution, sets event flag 999901 or 999902, and pivots the visual presentation profile safely without Linux proc mem permission faults.

**Independent Test**: Execute `uv run python tools/verify_lantern_mod.py --test flag-signaling` asserting flag 999901/999902 dispatches presentation sync across state file, bbport.ini (retro_mode), and overlay manager.

### Implementation for User Story 2

- [x] T012 [P] [US2] Rewrite tools/pipeline/lantern_event_listener.py to support dual signaling (parent-traced memory observation and out/flag_signal.txt file IPC) with safe directory handling preventing EISDIR on materialized folders
- [x] T013 [P] [US2] Connect tools/pipeline/lantern_event_listener.py with bbport.ini configuration synchronizer toggling retro_mode=1 vs retro_mode=0
- [x] T014 [US2] Implement automated test test_flag_signaling in tools/verify_lantern_mod.py verifying flag dispatch, signal file consumption, and bbport.ini sync
- [x] T015 [US2] Validate User Story 2 independently with `uv run python tools/verify_lantern_mod.py --test flag-signaling`

**Checkpoint**: User Stories 1 AND 2 work independently and in combination.

---

## Phase 5: User Story 3 - Persistence & Universal Lantern Availability (Priority: P3)

**Goal**: Persist active presentation profile across area warps, deaths, and session restarts when toggled via lantern dialogue.

**Independent Test**: Execute `uv run python tools/verify_lantern_mod.py --test persistence` verifying that out/retro_toggle_state.json and /home/andre/Games/bbport-src/mods.json retain the selected mode after lantern interaction.

### Implementation for User Story 3

- [x] T016 [P] [US3] Implement atomic state synchronization in tools/pipeline/lantern_event_listener.py updating out/retro_toggle_state.json and syncing enabled/disabled mod lists in /home/andre/Games/bbport-src/mods.json
- [x] T017 [US3] Implement persistence automated test test_persistence in tools/verify_lantern_mod.py verifying state file retention and mods.json consistency
- [x] T018 [US3] Validate User Story 3 independently with `uv run python tools/verify_lantern_mod.py --test persistence`

**Checkpoint**: All three user stories functional and independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation correction, standalone patch re-generation, and adversarial quality audit

- [x] T019 [P] Rewrite Section 17 in BB_PSX_DEMAKE_GUIDE.md correcting Talk ESD architecture, documenting State 6 hook requirement, State 7 unlit preservation, and condition evaluation semantics
- [x] T020 [P] Rewrite Section 32 in BB_PSX_DEMAKE_MATH_AND_FINDINGS.md correcting FromSoftware EzState disassembly and removing erroneous dual-hook claims
- [x] T021 Update ACTIVE_PLANS.md Plan 12 with accurate diagnosis, corrected architecture, and verified milestones
- [x] T022 Re-generate dist/bloodborne_retro_hud.patch with corrected talk binders and menu text
- [x] T023 Run complete automated verification suite with `uv run python tools/verify_lantern_mod.py --all`
- [x] T024 Execute multi-model adversarial quality audit with `uv run python tools/pipeline/run_adversarial_audit.py`

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
- T006, T007, and T010 can run in parallel within Phase 3.
- T012 and T013 can run in parallel within Phase 4.
- T019 and T020 can run in parallel within Phase 6.

---

## Parallel Example: User Story 1

```bash
# Launch Talk ESD patcher fixes and FMG text injector in parallel:
Task: "Fix patch_vanilla_esd in tools/pipeline/inject_lantern_talk_esd.py"
Task: "Fix patch_moal_esd in tools/pipeline/inject_lantern_talk_esd.py"
Task: "Inject localized lantern toggle prompts via tools/pipeline/inject_lantern_menu_text.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup: restore MOAL `.bak` files).
2. Complete Phase 2 (Foundational: types, injector, rewritten test harness).
3. Complete Phase 3 (User Story 1: State 6 hook only, canonical condition graph, inject all 16 maps).
4. **STOP and VALIDATE**: Test User Story 1 independently with `uv run python tools/verify_lantern_mod.py --test talk-esd`.
5. Verify in-game: unlit lamps ignite normally; lit lamps open dialogue menu cleanly.

### Incremental Delivery
1. Foundation Ready: Domain types, EzState definitions, rewritten test harness.
2. Increment 1 (MVP): In-game dialogue menu on lit lamps without breaking unlit lamps across vanilla and MOAL.
3. Increment 2: Event flag signaling, `bbport.ini` `retro_mode` toggle, and safe directory synchronization.
4. Increment 3: State persistence across sessions and `mods.json` sync.
5. Polish: Documentation correction in guide and findings, patch rebuild, adversarial audit PASS.
