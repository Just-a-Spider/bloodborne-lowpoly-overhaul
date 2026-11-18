# Tasks: Fix Research Hall Interactive Stairs and Lady Maria Cloth Physics

**Input**: Design documents from `/specs/007-fix-stairs-maria-cloth/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Explicit file paths included in all tasks

---

## Phase 1: Setup (Governance & Isolation)

**Purpose**: Repository hygiene, governance constraints, and exclusion enforcement

- [X] T001 Verify and update .gitignore to exclude specs/000-*/ and .specify/assessments/
- [X] T002 Verify Constitution 1.2.1 contains internal map nomenclature table in .specify/memory/constitution.md

---

## Phase 2: Foundational (Pipeline Fixes)

**Purpose**: Core pipeline filters that must be fixed before deploying assets

- [X] T003 Update tools/pipeline/batch_blender_demake_obj.py to remove o24301 from is_target_cage and add explicit bypass whitelist for Research Hall stair/ladder mechanisms (o35050*, o353006, o353011, o353013, o243010-o243014, o249001, o249002)

**Checkpoint**: Pipeline logic safeguarded against prop decimation regressions

---

## Phase 3: User Story 1 - Research Hall Interactive Stairs & Ladders Visibility (Priority: P1)

**Goal**: Restore 100% visibility, bone hierarchy, and collision alignment for Research Hall moving stairs and ladders

**Independent Test**: Execute tests/verify_research_hall_stairs.py to verify non-zero vertex counts, valid AABBs, and discrete ladder rung bones

- [X] T004 [US1] Restore vanilla FLVER objbnd containers for o243010-o243014, o353006, o353011, o353013, and o350501-o350504 from CUSA03173/dvdroot_ps4/obj/ to CUSA03173-PSX/dvdroot_ps4/obj/
- [X] T005 [P] [US1] Create automated verification test tests/verify_research_hall_stairs.py checking vertex counts, AABB extrema, and ladder bone rung hierarchies
- [X] T006 [US1] Run tests/verify_research_hall_stairs.py with uv run python to validate stair and ladder integrity

**Checkpoint**: Research Hall interactive staircases and ladder rungs completely visible and structurally verified

---

## Phase 4: User Story 2 - Lady Maria Boss Fight Cloth & Hat Mesh Synchronization (Priority: P1)

**Goal**: Eliminate floating/detached feather and mantle meshes during Lady Maria movement and combat animations

**Independent Test**: Execute tests/verify_maria_cloth.py to confirm cloth physics solver data in Cloth edition and bone re-parenting in Stiff edition

- [X] T007 [US2] Update tools/pipeline/deploy_retro_armors.py to preserve Havok cloth physics (hkx, clm2, _Cloth.mtd) for set 9300 in Cloth edition, and re-parent unparented cloth dummy bones to character skeleton roots in Flat Stiff edition
- [X] T008 [US2] Execute tools/pipeline/deploy_retro_armors.py with uv run python to deploy fixed hd_f_9300, hd_m_9300, bd_f_9300, bd_m_9300 into CUSA03173-PSX/dvdroot_ps4/parts/ and mods/
- [X] T009 [P] [US2] Create and run automated verification script tests/verify_maria_cloth.py verifying bone parent indices, material names, and absence of detached -1 dummy bones in stiff mode

**Checkpoint**: Lady Maria hat and garb meshes track character movement with zero detached/floating artifacts

---

## Phase 5: User Story 3 - Modular Mod Packaging & Differential Patching (Priority: P2)

**Goal**: Bundle repaired assets across the 5 modular mod pillars and regenerate standalone differential release patch

**Independent Test**: Execute pytest tests/test_apply_patch.py to ensure zero-defect patch application and hash verification

- [X] T010 [US3] Run uv run python tools/pipeline/package_modular_mods.py to sync props and armors into mods/
- [X] T011 [US3] Run uv run python tools/pipeline/create_patch.py to generate updated dist/bloodborne_lowpoly_overhaul.patch and refresh dist/SHA256SUMS.txt
- [X] T012 [US3] Run uv run pytest tests/test_apply_patch.py to verify patch integrity and binary reconstruction

**Checkpoint**: All 5 mod pillars updated and differential patch verified

---

## Phase 6: Polish, Release 1.2.1 & Governance

**Purpose**: Release notes, version bump, and clean Git publishing

- [X] T013 Update dist/RELEASE_NOTES.md with 1.2.1 release notes detailing Research Hall stairs and Lady Maria cloth fixes
- [X] T014 Verify Git staging excludes specs/000-*/ and only stages production mod changes
- [ ] T015 Commit changes, push to origin main, and publish release 1.2.1

---

## Dependencies & Execution Order

- Setup (Phase 1) & Foundational (Phase 2) MUST run before User Stories
- User Story 1 (Phase 3) and User Story 2 (Phase 4) can proceed in sequence or parallel
- User Story 3 (Phase 5) requires assets from US1 and US2
- Release 1.2.1 (Phase 6) requires US3 completion
