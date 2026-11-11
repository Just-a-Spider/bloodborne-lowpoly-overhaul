# Tasks: Modular Mod Release & Patch Distribution

**Input**: Design documents from `/specs/005-modular-patches-release/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-contract.md, quickstart.md

## Organization
Tasks are grouped by user story to enable independent implementation and testing of each story.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Baseline cleanup and inventory verification

- [X] T001 Inspect existing patch containers in `dist/` and modular directories in `mods/` to verify baseline integrity
- [X] T002 Verify clean HUD mod state in `mods/Bloodborne Retro HUD and UI` to ensure zero talk scripts or message residuals exist before release packaging

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core packager and validator prerequisites blocking user stories

- [X] T003 [P] Update `tools/pipeline/create_patch.py` to embed optional `mod_name` in patch container metadata JSON
- [X] T004 Run and verify `tools/pipeline/modular_structure_validator.py` across all 5 modular pillars under `mods/`

---

## Phase 3: User Story 1 - Standalone Modular Mod Reconstruction by Players (Priority: P1) 🎯 MVP

**Goal**: Enable players to reconstruct any modular mod pillar or batch-reconstruct all pillars using `apply_patch.py` with automatic target directory inference and zero external dependencies.

**Independent Test**: Reconstruct `dist/bloodborne_retro_hud.patch` without `--out` argument and verify that output files are placed into `Bloodborne Retro HUD and UI/` with 100% SHA256 integrity match.

- [X] T005 [P] [US1] Create unit tests for automatic target directory inference and batch mode in `tests/test_apply_patch.py`
- [X] T006 [US1] Implement automatic output directory inference and metadata `mod_name` reading in `apply_patch.py`
- [X] T007 [US1] Implement `--mods-dir` and batch reconstruction mode (`--all-patches` / `--patch-dir`) in `apply_patch.py`
- [X] T008 [US1] Implement disk space check and user-friendly error handling for missing files in `apply_patch.py`
- [X] T009 [US1] Execute end-to-end single-patch reconstruction test on `dist/bloodborne_retro_hud.patch` and verify target directory and asset hashes

---

## Phase 4: User Story 2 - Automated Release Verification & Cryptographic Manifest (Priority: P2)

**Goal**: Provide an automated release audit tool `tools/pipeline/verify_release_artifacts.py` to validate all patch files in `dist/`, enforce modular path separation, and generate `dist/SHA256SUMS.txt`.

**Independent Test**: Execute `uv run python tools/pipeline/verify_release_artifacts.py --vanilla CUSA03173 --dist dist --manifest dist/SHA256SUMS.txt` and confirm all 9 patch containers pass with exit code 0.

- [X] T010 [P] [US2] Create release verification tool in `tools/pipeline/verify_release_artifacts.py` implementing header magic, metadata JSON, and payload offset checks
- [X] T011 [US2] Implement streaming in-memory XOR roundtrip verification against `CUSA03173` in `tools/pipeline/verify_release_artifacts.py`
- [X] T012 [US2] Integrate pillar path confinement and anti-leakage checks into `tools/pipeline/verify_release_artifacts.py`
- [X] T013 [US2] Implement manifest generation producing `dist/SHA256SUMS.txt` with SHA256 hashes and file sizes for all `.patch` containers and `apply_patch.py`
- [X] T014 [US2] Execute `tools/pipeline/verify_release_artifacts.py` across all modular and overhaul patches in `dist/` and generate `dist/SHA256SUMS.txt`

---

## Phase 5: User Story 3 - Distribution & Modding Documentation (Priority: P3)

**Goal**: Deliver updated, comprehensive player and developer documentation across `README.md` and `BB_PSX_DEMAKE_GUIDE.md`.

**Independent Test**: Review `README.md` and `BB_PSX_DEMAKE_GUIDE.md` to confirm runnable commands for installing each modular pillar, configuring `mods.json`, and executing pipeline checks.

- [X] T015 [P] [US3] Update `README.md` with modular architecture overview, Cloth vs Flat Stiff armor selection, and `apply_patch.py` quick-start guide
- [X] T016 [P] [US3] Add release artifact inventory table (filename, size, SHA256, target folder, description) and `mods.json` configuration examples to `README.md`
- [X] T017 [US3] Update `BB_PSX_DEMAKE_GUIDE.md` Section 14 with modular release generation workflows, verification tool usage, and Talk ESD status
- [X] T018 [US3] Create release summary document in `dist/RELEASE_NOTES.md` documenting v1.2.0 modular release artifacts and checksum verification

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final end-to-end verification and quality audit

- [X] T019 Run full quickstart validation scenarios from `specs/005-modular-patches-release/quickstart.md`
- [X] T020 Run `sha256sum -c dist/SHA256SUMS.txt` to verify manifest consistency
- [X] T021 Perform final audit against Constitution principles (baseline immutability, zero modified vanilla files, saves untouched)

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 completion; blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Phase 2; deliverable as independent MVP.
- **User Story 2 (Phase 4)**: Depends on Phase 2; can proceed in parallel with US1.
- **User Story 3 (Phase 5)**: Depends on Phase 3 and Phase 4 completion (requires final hashes and verification commands).
- **Polish (Phase 6)**: Depends on completion of all user stories.

### Parallel Opportunities
- T001 and T002 can run in parallel.
- T003 and T004 can run in parallel.
- T005 and T010 can run in parallel.
- T015 and T016 can run in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (T001-T002) & Phase 2 (T003-T004).
2. Complete User Story 1 (T005-T009).
3. Verify `apply_patch.py` auto-detect and extraction independently.

### Incremental Delivery
1. Add User Story 2 (T010-T014): Automated release verification & checksum manifest.
2. Add User Story 3 (T015-T018): Player & developer documentation.
3. Polish (T019-T021): End-to-end quickstart and constitution checks.
