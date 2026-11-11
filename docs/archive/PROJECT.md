# Project: Plain Doll (c8030) Authentic retro Low-Poly Head Reconstruction

## Architecture
- **Low-Poly Head Reconstruction**: Replaces raw QEM edge-collapsed facial geometry in `c8030.flver` (`Mesh 7: F_7000_skin` head portion, $Y > 1.80$) with an authentic PlayStation 1 low-poly head cage (~250-400 triangles). Features clean manifold topology and planar facial facets, eliminating open border tears and needle slivers.
- **Bonnet Clearance & Anti-Penetration**: Maintains positive spatial clearance (>=2.0mm) between face skin (`Mesh 7`) and bonnet brim (`Mesh 4: HD_F_7000_01`), completely eliminating inter-mesh penetration and z-fighting.
- **Seam Welding & Hand Isolation**: Mesh 7 contains both head and hands with 0 bridging triangles. Surgically replaces the head portion while welding boundary vertices to the 56 neckline transition vertices ($Y \approx 1.80$), preserving all 4,007 ball-jointed doll hand vertices ($Y < 1.30$).
- **Skeletal Rigging & Weight Normalization**: Binds reconstructed facial vertices to character skeleton (Head `Bone 5`, Neck `Bone 4`, Jaw `Bone 6`, Eye/Eyelid `Bones 7-12`). Enforces strict partition of unity ($\sum w_j = 1.0$ with byte sum 255) and valid bone indices $[0, 205]$.
- **Diffuse UV Projection & Retro Shading**: Maps vanilla facial diffuse texture (`c8030_skin_a`) features onto low-poly UV layout with zero cross-chart stretching (UV jumps < 0.3). Retains authentic 15-bit RGB555 palette color quantization, porcelain skin luminance, and flat facet / retro normal shading.
- **Engine Invariants & Container Safety**:
  - Havok Cloth Invariant: Meshes 0, 1, 2, 10, 11 and simulation files (`c8030_c.hkx`, `c8030_c.clm2`) remain 100% untouched.
  - FaceSet Synchronization: All FLVER FaceSets synchronized (`FS1..FS5 = FS0.copy()`).
  - AABB Bounds: Rigid submeshes use exact vertex extrema $[\min \mathbf{v}, \max \mathbf{v}]$ with zero artificial padding; cloth submeshes retain vanilla AABBs.
  - Texture Preservation: BC7 hair alpha (`c8030_HR_a`), BC1 1-bit alpha (`c8030_BD_a`), and BC5 normal map format (`c8030_skin_n`) preserved intact.
  - Geometric Degenerate Filter: Zero-area faces (<1e-6) and needle slivers ($\rho > 25.0$) culled.
  - Fallback Backup: Backup `CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx.bak` created before write; pristine `CUSA03173/` 100% immutable.
- **E2E Acceptance Test Suite**: Standalone runner `tools/verify_c8030_doll.py` organized into 4 tiers with 12 automated verification checks.

## Feature Inventory
Every feature from user requirements and survey is assigned to a milestone:
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Authentic PSX Head Cage | Author/generate manifold 250-400 triangle head cage replacing QEM face in Mesh 7 | M1 | ORIGINAL_REQUEST R1 |
| 2 | Bonnet Clearance Margin | Guarantee >=2.0mm clearance against Bonnet Mesh 4; zero triangle intersections | M1 | ORIGINAL_REQUEST R1 |
| 3 | Seam Welding & Hand Isolation | Preserve 4,007 hand vertices in Mesh 7; weld head boundary to 56 neck seam vertices | M1 | Survey 1, 2 |
| 4 | Skeletal Rigging Integrity | Bind head to Bones 4, 5, 6; normalize bone weights ($\sum w = 1.0$, byte sum = 255) | M1 | ORIGINAL_REQUEST R3 |
| 5 | Diffuse UV Feature Projection | Project eyes, nose, mouth from vanilla `c8030_skin_a` with zero cross-seam stretching | M2 | ORIGINAL_REQUEST R2 |
| 6 | 15-Bit RGB555 & Retro Shading | Apply 15-bit RGB555 palette color quantization, porcelain luminance, flat facet normals | M2 | ORIGINAL_REQUEST R2 |
| 7 | Alpha Cutout & Normal Preservation | Preserve BC7 hair alpha (`c8030_HR_a`), BC1 1-bit lace (`c8030_BD_a`), BC5 normal (`c8030_skin_n`) | M2 | Survey 1, 3 |
| 8 | Havok Cloth Physics Invariant | Bypass Meshes 0, 1, 2, 10, 11; preserve `c8030_c.hkx` and `c8030_c.clm2` 100% untouched | M3 | ORIGINAL_REQUEST Invariant 1 |
| 9 | FaceSet Synchronicity | Synchronize `FS1..FS5 = FS0.copy()` across all modified submeshes | M3 | ORIGINAL_REQUEST Invariant 2 |
| 10 | Exact Tight AABB Bounds | Exact extrema $[\min \mathbf{v}, \max \mathbf{v}]$ on rigid meshes; vanilla AABBs on cloth meshes | M3 | ORIGINAL_REQUEST Invariant 3 |
| 11 | Degenerate Geometry Filter | Zero-area (<1e-6) faces and needle slivers ($\rho > 25.0$) culled | M3 | ORIGINAL_REQUEST Invariant 6 |
| 12 | Fallback Backup & Isolation | `c8030.chrbnd.dcx.bak` created; pristine `CUSA03173/` 100% immutable | M3 | ORIGINAL_REQUEST R4 |
| 13 | E2E Acceptance Test Suite | Implement `tools/verify_c8030_doll.py` (4 tiers, 12 tests) passing 100% with exit code 0 | Test Track | Survey 3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| Test Track | E2E Test Suite Creation | Build `tools/verify_c8030_doll.py` (Tiers 1-4, 15 tests), create `TEST_INFRA.md`, publish `TEST_READY.md` | none | DONE (test_writer_doll_1, TEST_READY.md published) |
| M1 | PSX Head Geometry & Rigging | Reconstruct 250-400 tri manifold cage (314 tris), bonnet clearance (4.10mm), seam welding, normalize bone weights | none | DONE (worker_doll_m1_gen2: tools/reconstruct_doll_head.py) |
| M2 | Diffuse UV Projection & Shading | UV mapping of vanilla facial features, RGB555 palette quantization, flat facet normals | M1 | DONE (worker_doll_m1_gen2: tools/demake_color_engine.py) |
| M3 | FLVER Assembly & E2E Gate | Inject head into Mesh 7, sync FaceSets, exact AABBs, repack DCX with backup, pass 100% E2E tests | Test Track, M2 | DONE (15/15 PASS, Gate PASS, Audit CLEAN) |

## Interface Contracts
### Head Generator ↔ FLVER Injector (`tools/reconstruct_doll_head.py`)
- `generate_psx_head_cage() -> HeadCageData`
  - `positions`: `np.ndarray`, shape `(N, 3)`, dtype `float32`, $Y \in [1.79, 2.01]$
  - `faces`: `np.ndarray`, shape `(M, 3)`, dtype `int32`, $250 \le M \le 450$
  - `uvs`: `np.ndarray`, shape `(N, 2)`, dtype `float32`, bounded in $[0.0, 1.0]$
  - `normals`: `np.ndarray`, shape `(N, 3)`, dtype `float32`, unit length
  - `bone_indices`: `np.ndarray`, shape `(N, 4)`, dtype `uint8`
  - `bone_weights`: `np.ndarray`, shape `(N, 4)`, dtype `float32`, row sum $== 1.0$ within $10^{-4}$
- `weld_neck_seam(head_data, neck_seam_verts) -> WeldedMeshData`
  - Welds bottom edge loop of head cage to the 56 transition vertices ($Y \approx 1.80$)
- `check_bonnet_clearance(head_positions, bonnet_positions) -> min_distance`
  - Asserts $\min(\text{distance}) \ge 0.0020$ (2.0mm clearance)

### FLVER Assembly & Packaging (`tools/inject_doll_head.py`)
- `inject_head_into_flver(flver_path, head_mesh_data) -> FLVER`
  - Replaces head portion in Mesh 7 while preserving hand vertices
  - Synchronizes all FaceSets (`FS1..FS5 = FS0.copy()`)
  - Recalculates exact bounding boxes for rigid meshes
- `repack_doll_chrbnd(flver_obj, tpf_path=None) -> None`
  - Creates backup `CUSA03173-PSX/.../c8030.chrbnd.dcx.bak`
  - Repacks `c8030.chrbnd.dcx` preserving Havok files untouched

## Code Layout
- `tools/verify_c8030_doll.py`: Standalone 4-tier E2E acceptance test runner (owned by Test Writer)
- `tools/reconstruct_doll_head.py`: PSX low-poly head cage generation, rigging, and UV projection (owned by M1/M2 Worker)
- `tools/inject_doll_head.py`: FLVER injection, FaceSet synchronization, AABB calculation, DCX packaging (owned by M3 Worker)
- `tools/flver_parser.py`: Existing FLVER parser and serializer
- `tools/soulstruct_patch.py`: Soulstruct monkeypatch for bone AABBs
- `tools/demake_color_engine.py`: Texture demaking, RGB555 palette quantization, and BC codecs
- `CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx`: Destination container for Plain Doll
- `CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx.bak`: Pre-modification fallback backup
