# Tasks: Fix Dungeon Props Demake & Modular Mod Architecture

**Input**: Design documents from `/specs/002-fix-dungeon-props-modularize/`  
**Prerequisites**: [plan.md](file:///home/andre/Games/Bloodborne/specs/002-fix-dungeon-props-modularize/plan.md), [spec.md](file:///home/andre/Games/Bloodborne/specs/002-fix-dungeon-props-modularize/spec.md), [research.md](file:///home/andre/Games/Bloodborne/specs/002-fix-dungeon-props-modularize/research.md), [data-model.md](file:///home/andre/Games/Bloodborne/specs/002-fix-dungeon-props-modularize/data-model.md), [contracts/](file:///home/andre/Games/Bloodborne/specs/002-fix-dungeon-props-modularize/contracts/)  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.  

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`, `[US4]`)
- Every task includes exact file paths

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, baseline immutability confirmation, and test fixtures setup.

- [x] T001 Verify cryptographic immutability of pristine vanilla `CUSA03173/` baseline and confirm mod output staging in `CUSA03173-PSX/` and `mods/` per Constitution Principle I.
- [x] T002 Verify Python dependencies and unified execution environment in `pyproject.toml` and `uv.lock` via `uv run python`.
- [x] T003 [P] Create test fixture directory and baseline inspection helper in `tools/fixtures/prop_geometry_fixtures.py` for recording pre-demake and post-demake FLVER topologies.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core geometry sanitization and structure validation tools required across all user stories.

- [x] T004 Implement common geometry sanity validator in `tools/pipeline/geometry_sanitizer.py` quoting verbatim rules: triangle area $\ge 10^{-6}$ m$^2$, triangle aspect ratio $\rho \le 25.0$, maximum edge length $\le 2.0$m, FaceSet synchronization `FS1..FS5 = FS0.copy()`, and bone index boundaries $[0, 205]$.
- [x] T005 [P] Implement model-space bone hierarchy accumulator in `tools/pipeline/bone_transform_utils.py` calculating exact world-space AABB bounds from bone-local vertex coordinates per Section 29 of `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md`.
- [x] T006 Implement multi-pillar directory validator in `tools/pipeline/modular_structure_validator.py` defining strict subpath mapping for `map/`, `obj/`, `parts/`, `chr/`, and `menu/`.

**Checkpoint**: Foundation ready. User story implementation can now proceed.

---

## Phase 3: User Story 1 - Fix Exploded Cadaver Wastes in Dungeons (Priority: P1) - MVP

**Goal**: Eliminate gigantic ballooned polygon sheets, jagged geometry explosions, and camera-clipping spikes across all Chalice Dungeon cadaver waste heaps and corpse props.

**Independent Test**: Load Chalice Dungeons with cadaver waste props (`o297210`, `o298500`, `o290250`..`o290274`); verify corpse models render as stable grounded faceted props with 0 vertices displaced into void/ceiling and max triangle edge $\le 2.0$m.

### Tests for User Story 1

- [x] T007 [P] [US1] Implement automated test suite in `tools/verify_retro_props.py` checking cadaver waste models (`o297210`, `o298500`, `o290250`..`o290274`, `o297100`..`o297144`): assert max triangle edge length $\le 2.0$m, ground clamping $Y_{\min} \ge -0.05$m, and zero degenerate triangles (area $< 10^{-6}$ m$^2$).

### Implementation for User Story 1

- [x] T008 [US1] Update `tools/pipeline/batch_blender_demake_obj.py` to lock cadaver submesh vertices to bone-local coordinate frames relative to `mesh.default_bone_index` and enforce ground height clamping ($\Delta Y \ge -0.05$m).
- [x] T009 [US1] Update `tools/pipeline/blender_process_obj.py` to prevent unwelded duplicate vertex explosion on multi-layered corpse meshes, maintaining manifold shared vertices ($V < T$) and applying flat facet normals.
- [x] T010 [US1] Execute stabilization and demake pass on all Chalice cadaver waste and corpse pile archives (`o297210`..`o297214`, `o298500`..`o298524`, `o290250`..`o290274`, `o297100`..`o297144`, `o288000`..`o288100`) deploying to `CUSA03173-PSX/dvdroot_ps4/obj/`.
- [x] T011 [US1] Run `uv run python tools/verify_retro_props.py --check-cadavers` and verify exit code 0 with 100% assertions satisfied.

**Checkpoint**: User Story 1 complete. Exploded cadaver wastes completely eliminated and verified.

---

## Phase 4: User Story 2 - Demake Regular and Deformed Dungeon Cages (Priority: P1)

**Goal**: Convert all cylindrical hanging cages, ground cages, elevator cages, and deformed torture cages to authentic 32-bit low-poly retro geometry (200–800 triangles, 70–80% reduction) with flat facet normal shading while preserving animations and physics.

**Independent Test**: Inspect hanging cages, free-standing cages, and deformed torture cages in Chalice Dungeons and Mensis: verify polygon counts meet retro budget, facet normals display crisp retro shading, and Havok collision and animation tracks remain intact.

### Tests for User Story 2

- [x] T012 [P] [US2] Add test scenarios to `tools/verify_retro_props.py` for cage assets (`o290000`..`o290004`, `o290200`..`o290284`, `o322050`..`o322056`, `o322001`, `o322310`, `o322320`, `o260303`, `o260310`, `o243010`..`o243014`, `o270102`, `o270104`, `o273011`, `o281000`..`o281001`, `o282020`): assert triangle reduction ratio $\ge 70\%$, triangle count within 200–800 tris budget, flat normal facet verification (`norm_diff > 0.0`), bit-for-bit `.anibnd` animation preservation, and bit-for-bit `.hkx` collision preservation.

### Implementation for User Story 2

- [x] T013 [US2] Modify `tools/pipeline/batch_blender_demake_obj.py` to lift blanket bypasses for dungeon cage assets (`o290200`..`o290284`, `o290000`..`o290004`, `o322050`..`o322056`, `o322001`, `o322310`, `o322320`, `o260303`, `o260310`, `o243010`..`o243014`, `o270102`, `o270104`, `o273011`, `o281000`..`o281001`, `o282020`), processing cage geometry through Blender while preserving animation tracks and collision data.
- [x] T014 [US2] Update `tools/pipeline/blender_process_obj.py` to enforce `shade_flat` facet normal generation and decimation ratio targeting 70–80% triangle reduction for cage meshes.
- [x] T015 [US2] Execute batch demake pass on all dungeon, torture, and dog cage archives deploying to `CUSA03173-PSX/dvdroot_ps4/obj/`.
- [x] T016 [US2] Run `uv run python tools/verify_retro_props.py --check-cages` and verify exit code 0 with 100% assertions satisfied.

**Checkpoint**: User Stories 1 and 2 complete. All dungeon cages and cadaver wastes demade and stabilized.

---

## Phase 5: User Story 3 - Five-Pillar Modular Mod Architecture for bbport (Priority: P2)

**Goal**: Decouple the low-poly overhaul into five clean, independent modular mod packages under `mods/`, isolating static maps (`map/`) from interactive scenery props (`obj/`), armors/weapons (`parts/`), characters (`chr/`), and UI (`menu/`).

**Independent Test**: Enable individual mod folders or combinations in `mods/` through `bbport`; verify each package operates autonomously without missing asset errors or folder cross-contamination.

### Tests for User Story 3

- [x] T017 [P] [US3] Implement automated test harness `tools/verify_modular_mods.py` verifying 5-pillar directory isolation, `mod.json` schema validation, and absence of cross-contamination across `map/`, `obj/`, `parts/`, `chr/`, and `menu/`.

### Implementation for User Story 3

- [x] T018 [US3] Implement `tools/pipeline/package_modular_mods.py` supporting `--pillar <NAME>` and `--pillar all`, extracting asset deltas from `CUSA03173-PSX/` against pristine `CUSA03173/` and populating:
  - `mods/Bloodborne Retro Maps/` (`dvdroot_ps4/map/`)
  - `mods/Bloodborne Retro Props and Objects/` (`dvdroot_ps4/obj/`)
  - `mods/Bloodborne Retro Armors and Weapons - Cloth Physics/` and `- Flat Stiff/` (`dvdroot_ps4/parts/`)
  - `mods/Bloodborne Retro Characters/` (`dvdroot_ps4/chr/`)
  - `mods/Bloodborne Retro HUD and UI/` (`dvdroot_ps4/menu/`)
- [x] T019 [US3] Execute `tools/pipeline/package_modular_mods.py --pillar all --clean` to generate all 5 modular packages in `mods/` along with complete `mod.json` manifests.
- [x] T020 [US3] Run `uv run python tools/verify_modular_mods.py` and verify all 5 pillars pass isolation and manifest checks with exit code 0.

**Checkpoint**: User Stories 1, 2, and 3 complete. 5-pillar modular architecture deployed and validated.

---

## Phase 6: User Story 4 - Multi-Model Quality Audit Workflow (Priority: P3)

**Goal**: Enforce Constitution Principle VI by conducting an independent adversarial quality audit using an alternate AGY model (Sonnet 4.6 in AGY) before final release sign-off.

**Independent Test**: Execute the cross-model audit harness against modified asset stages, producing a signed `AUDIT_REPORT.md` confirming 0 high-poly bypass oversights and 0 mesh explosions.

### Tests for User Story 4

- [x] T021 [P] [US4] Implement `tools/pipeline/audit_assets_adversarial.py` to extract comprehensive geometry, topology, and packaging metrics across modified assets into `/tmp/audit_raw.json`.

### Implementation for User Story 4

- [x] T022 [US4] Implement AGY auditor subagent dispatch harness in `tools/pipeline/run_adversarial_audit.py` to invoke an independent alternate AGY model (Sonnet 4.6 / AGY auditor) passing `/tmp/audit_raw.json`.
- [x] T023 [US4] Execute adversarial audit protocol and generate signed `AUDIT_REPORT.md` validating 0 high-poly bypass oversights, 0 mesh explosions, and 100% 5-pillar directory isolation.

**Checkpoint**: All 4 user stories complete. Adversarial sign-off obtained.

---

## Phase 7: Polish & Documentation

**Purpose**: Documentation updates, guide synchronizations, and end-to-end quickstart validation.

- [x] T024 [P] Update `ACTIVE_PLANS.md` (Plan 10) with feature status, metric achievements, and modular architecture deliverables.
- [x] T025 [P] Append technical root causes, mathematical bone-offset accumulation, and cage decimation workarounds to `BB_PSX_DEMAKE_GUIDE.md` (Section 15) and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md` (Section 30).
- [x] T026 Run end-to-end quickstart validation per `quickstart.md` (`verify_retro_props.py`, `verify_modular_mods.py`, and audit verification) confirming exit code 0 across all suites.

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1: Setup
    │
    ▼
Phase 2: Foundational
    │
    ├───────────────────────┬───────────────────────┐
    ▼                       ▼                       ▼
Phase 3: US1 (Cadavers)  Phase 4: US2 (Cages)   Phase 5: US3 (Modular Mods)
    │                       │                       │
    └───────────────────────┴───────────────────────┘
                            │
                            ▼
                    Phase 6: US4 (Multi-Model Audit)
                            │
                            ▼
                    Phase 7: Polish & Docs
```

### User Story Dependencies

- **User Story 1 (P1 - Cadavers)**: Depends on Foundational (Phase 2). No dependency on cages or packaging.
- **User Story 2 (P1 - Cages)**: Depends on Foundational (Phase 2). No dependency on cadavers. Can run in parallel with US1.
- **User Story 3 (P2 - Modular Mods)**: Depends on US1 and US2 modified assets in `CUSA03173-PSX/` to package complete prop deliverables.
- **User Story 4 (P3 - Multi-Model Audit)**: Depends on US1, US2, and US3 completion to evaluate audit metrics across all pillars.

---

## Parallel Opportunities

```bash
# Foundational parallel execution:
Task: "T005 [P] Implement model-space bone hierarchy accumulator in tools/pipeline/bone_transform_utils.py"
Task: "T006 Implement multi-pillar directory validator in tools/pipeline/modular_structure_validator.py"

# User Story 1 & 2 test parallel execution:
Task: "T007 [P] [US1] Implement automated test suite in tools/verify_retro_props.py"
Task: "T012 [P] [US2] Add test scenarios to tools/verify_retro_props.py for cage assets"
Task: "T017 [P] [US3] Implement automated test harness tools/verify_modular_mods.py"
Task: "T021 [P] [US4] Implement tools/pipeline/audit_assets_adversarial.py"

# Documentation polish parallel execution:
Task: "T024 [P] Update ACTIVE_PLANS.md (Plan 10)"
Task: "T025 [P] Append technical root causes to BB_PSX_DEMAKE_GUIDE.md and BB_PSX_DEMAKE_MATH_AND_FINDINGS.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (`T001`–`T003`).
2. Complete Phase 2: Foundational (`T004`–`T006`).
3. Complete Phase 3: User Story 1 (`T007`–`T011`).
4. **VALIDATE**: Run `tools/verify_retro_props.py --check-cadavers`. Exploded blobs fixed.

### Incremental Delivery

1. Foundation ready (`T001`–`T006`).
2. Fix cadaver waste mesh explosions (`T007`–`T011`) → MVP delivered.
3. Demake regular and deformed dungeon cages (`T012`–`T016`) → Complete dungeon prop demake.
4. Package 5-pillar modular mods under `mods/` (`T017`–`T020`) → Clean modular distribution for `bbport`.
5. Execute adversarial multi-model audit (`T021`–`T023`) → Principle VI sign-off.
6. Documentation & quickstart validation (`T024`–`T026`) → Merge and release ready.
