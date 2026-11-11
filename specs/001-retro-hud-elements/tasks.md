---
description: "Task list for Retro HUD & Interaction Elements Demake implementation"
---

# Tasks: Retro HUD & Interaction Elements Demake

**Input**: Design documents from `specs/001-retro-hud-elements/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `.specify/memory/constitution.md`
**Tests**: Automated 4-tier acceptance test suite (`tools/verify_hud_demake.py`) required by Constitution Principle IV.
**Organization**: Tasks organized by user story for independent implementation and testing.

## Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable task (different files, no blocking dependencies)
- **[Story]**: User story label (`[US1]`, `[US2]`, `[US3]`) for story-phase tasks
- Strict checklist format with exact file paths

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Pipeline initialization, output staging, and dependency verification

- [x] T001 Set up HUD output directory staging in `CUSA03173-PSX/dvdroot_ps4/menu/` and standalone addition mod directory `mods/Bloodborne Retro HUD and UI/dvdroot_ps4/menu/`
- [x] T002 [P] Verify Python 3.12+ execution environment and dependencies (`soulstruct`, `ispc_texcomp`, `texture2ddecoder`, `numpy`, `Pillow`) via `uv run python` in `tools/demake_ui_engine.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core container manipulation, validation harness, and processing rules that all user stories depend on

- [x] T003 [P] Build automated 4-tier acceptance test harness skeleton in `tools/verify_hud_demake.py` implementing Tier 1 (TPF header magic `TPF\x00`, texture count $N=65$, offset monotonicity) and Tier 4 (pristine `CUSA03173/` immutability, backup `.bak` validation)
- [x] T004 Enhance `tools/demake_ui_engine.py` with `UIProcessingRule` pattern-matching engine enforcing single-mip invariant (`num_mips == 1`), block alignment ($W, H \pmod 4 == 0$), and zero-filled capacity padding within `tex_sz`
- [x] T005 [P] Implement `HUDAtlasManifest` catalog and validation scanner in `tools/verify_hud_demake.py` ensuring all 65 records in `common.tpf.dcx` are indexed with expected formats (`0x66` BC7, `0x00`/`0x01` BC1)

**Checkpoint**: Foundation ready. User stories can proceed.

---

## Phase 3: User Story 1 - Primary Vitals & Quickslots Combat HUD (Priority: P1) [MVP]

**Goal**: Demake player vitals (health bar, stamina bar, quicksilver bullets, blood vials) and active weapon/item quickslot icons to 15-bit RGB555 retro styling while locking Scaleform canvas dimensions and gauge fill ratios.

**Independent Test**: Execute test harness Tier 2 and Tier 3 on vitals atlases `MENU_Common_00001` through `MENU_Common_00005`, verifying RGB555 color stepping ($R, G, B \pmod 8 == 0$) and identical canvas dimensions ($2048\times 2048$, $2048\times 1024$, $1024\times 1024$).

### Tests for User Story 1

- [x] T006 [P] [US1] Author Tier 2 (canvas dimensions lock) and Tier 3 (15-bit RGB555 palette stepping) test assertions for vitals atlases (`MENU_Common_00001`..`00005`) and weapon icons (`MENU_Icon_01001`..`02002`) in `tools/verify_hud_demake.py`

### Implementation for User Story 1

- [x] T007 [P] [US1] Implement 15-bit RGB555 bilinear downsampling ($D=4$ for $2048$px, $D=2$ for $\le 1024$px) and nearest-neighbor canvas re-upscaler for vitals atlases (`MENU_Common_00001`..`00005`) in `tools/demake_ui_engine.py`
- [x] T008 [P] [US1] Implement retro quantization and Morton BC7/BC1 re-encoding for quickslot weapon and item icons (`MENU_Icon_00001`..`02002`) in `tools/demake_ui_engine.py`
- [x] T009 [US1] Implement vitals container extraction, batch processing, and repacking in `tools/pipeline/batch_demake_hud.py` with automatic `common.tpf.dcx.bak` generation
- [x] T010 [US1] Execute verification suite on US1 vitals and assert exit code 0 via `uv run python tools/verify_hud_demake.py --tier 2 --tier 3`

**Checkpoint**: User Story 1 complete and independently verified. Deliverable as core HUD MVP.

---

## Phase 4: User Story 2 - World Interaction Prompts, Dialogues & Loot Notifications (Priority: P2)

**Goal**: Demake world interaction frames ("Talk", "Open", "Traverse"), dialogue choice boxes, and item pickup toasts in retro styling while strictly preserving controller button prompt (`KG_*`) and localization (`MENU_LNG_*`) clarity.

**Independent Test**: Execute test harness Tier 3 asserting all 24 `KG_*` controller prompts match pristine vanilla byte-for-byte (`SHA256(T_payload) == SHA256(T_vanilla)`), while interaction frames in `MENU_Common_00090`..`00111` exhibit 15-bit quantization.

### Tests for User Story 2

- [x] T011 [P] [US2] Author controller prompt whitelist integrity assertions (`SHA256` matching) and interaction frame quantization tests in `tools/verify_hud_demake.py`

### Implementation for User Story 2

- [x] T012 [P] [US2] Implement prompt, dialogue frame, and notification toast demaking for `MENU_Common_00090` through `MENU_Common_00111` with nearest-neighbor 9-slice boundary protection in `tools/demake_ui_engine.py`
- [x] T013 [US2] Enforce pristine bypass rule for all 24 `KG_*` controller button prompts and 3 `MENU_LNG_*` language textures in `tools/demake_ui_engine.py`
- [x] T014 [US2] Integrate interaction and dialogue atlas processing into `tools/pipeline/batch_demake_hud.py`
- [x] T015 [US2] Execute automated verification asserting 100% prompt whitelist integrity and exit code 0 via `uv run python tools/verify_hud_demake.py`

**Checkpoint**: User Stories 1 and 2 functional and independently testable.

---

## Phase 5: User Story 3 - Boss Encounter Gauges & Milestone Banners (Priority: P3)

**Goal**: Demake boss health bars, lock-on reticles, and full-screen milestone announcement banners ("PREY SLAUGHTERED", "YOU DIED", "NIGHTMARE SLAIN") into 32-bit gothic horror retro presentation.

**Independent Test**: Verify boss gauge endcaps and announcement banner atlases (`MENU_Common_00120`, `MENU_Common_00130`, `MENU_Common_Loading*`) comply with RGB555 quantization, single-mip layout (`num_mips == 1`), and zero-padded byte limits.

### Tests for User Story 3

- [x] T016 [P] [US3] Author boss health gauge and announcement banner verification assertions in `tools/verify_hud_demake.py`

### Implementation for User Story 3

- [x] T017 [P] [US3] Implement boss health bar and banner demaking (`MENU_Common_00120`, `MENU_Common_00130`, `MENU_Common_LoadingItemKnowledgeIcon`, `MENU_Common_LoadingMapImage`) with dithered retro backdrop in `tools/demake_ui_engine.py`
- [x] T018 [US3] Integrate boss and milestone atlas processing into master pipeline in `tools/pipeline/batch_demake_hud.py`
- [x] T019 [US3] Execute full 4-tier regression suite covering all 65 textures in `tools/verify_hud_demake.py`

**Checkpoint**: All three user stories completed and verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Mod packaging, patch generation, and documentation

- [x] T020 [P] Package standalone addition mod in `mods/Bloodborne Retro HUD and UI/dvdroot_ps4/menu/common.tpf.dcx` preserving base overhaul folders untouched
- [x] T021 [P] Generate standalone addition patch `dist/bloodborne_retro_hud.patch` using XOR diffing via `tools/pipeline/create_patch.py`
- [x] T022 Execute quickstart validation guide scenarios in `specs/001-retro-hud-elements/quickstart.md`
- [x] T023 Document Scaleform UV invariants and HUD demake findings in `BB_PSX_DEMAKE_GUIDE.md` and `ACTIVE_PLANS.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies, executes immediately.
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion; core combat HUD MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational completion; integrates with `common.tpf.dcx`.
- **User Story 3 (Phase 5)**: Depends on Foundational completion; completes remaining atlases.
- **Polish (Phase 6)**: Depends on all user stories passing verification.

### User Story Dependencies

- **US1 (P1)**: Independent. Demakes core vitals (`MENU_Common_00001`..`00005`) and weapon icons (`MENU_Icon_*`).
- **US2 (P2)**: Independent. Demakes prompt boxes (`MENU_Common_00090`..`00111`) while preserving `KG_*`.
- **US3 (P3)**: Independent. Demakes boss bars and banners (`MENU_Common_00120`..`00130`).

### Parallel Opportunities

- T001 and T002 can execute in parallel.
- T003 and T005 test harness tasks can execute in parallel.
- Within US1: T006 (tests), T007 (vitals downsampler), and T008 (icon encoder) can run in parallel.
- Within US2: T011 (tests) and T012 (frame demaker) can run in parallel.
- Within US3: T016 (tests) and T017 (banner demaker) can run in parallel.
- In Polish: T020 (packager) and T021 (patcher) can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Author tests and implementation components concurrently:
Task: "Author Tier 2 and Tier 3 test assertions in tools/verify_hud_demake.py"
Task: "Implement 15-bit RGB555 downsampling and canvas re-upscaler in tools/demake_ui_engine.py"
Task: "Implement retro quantization and Morton BC7/BC1 re-encoding in tools/demake_ui_engine.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1: Setup (T001–T002).
2. Complete Phase 2: Foundational (T003–T005).
3. Complete Phase 3: User Story 1 (T006–T010).
4. **STOP and VALIDATE**: Run `uv run python tools/verify_hud_demake.py --tier 2 --tier 3` to verify vitals HUD independently.

### Incremental Delivery
1. Add User Story 2 (T011–T015): Verify interaction prompts and 100% `KG_*` controller guide preservation.
2. Add User Story 3 (T016–T019): Verify boss health bars and milestone announcement banners.
3. Polish & Packaging (T020–T023): Stage into standalone mod directory and generate delta patch.
