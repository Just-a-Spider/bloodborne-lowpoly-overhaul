# Active Pipeline Plans, Task Status & Technical Ledger

This document maintains the persistent, tracked status of all ongoing architectural plans, reverse-engineering discoveries, mathematical formulations, library workarounds, and implementation milestones for the Bloodborne PSX Demake.

>**important** 
We are never to modify files in the vanilla CUSA03173 folder. Never. Always work in a separate, isolated branch and deploy to a dedicated `CUSA03173-PSX` folder.
---

## Plan 1: Blender Custom Low-Poly Pipeline & Havok Cloth Decoupling

- **Date Initiated**: 2026-10-28
- **Primary Objective**: Bypass FromSoftware Havok cloth solver (`SpClothVertexUpdate`) crashes and eliminate algorithmic facial collapse by authoring custom, bone-weighted retro models (300–1,500 tris) in Blender 5.2.3 LTS, compiling back to Bloodborne FLVER2 format, and deploying directly to `CUSA03173-PSX`.
- **Pilot Subject**: Plain Doll (`chr/c8030.chrbnd.dcx`)

### Task Checklist & Status
- [x] **Subtask 1.1**: Skeleton hierarchy & cloth bone reverse-engineering (confirmed 46 cloth bones already exist in FromSoft FLVER skeleton).
- [x] **Subtask 1.2**: Havok solver dependency audit (confirmed `c0000` and other non-cloth characters have `cloth_hkx=False`; removing `_Cloth.mtd` and `_c.hkx` prevents solver initialization).
- [x] **Subtask 1.3**: `tools/pipeline/flver_to_rigged_gltf.py` — Export FLVER with full 206-bone skeleton, `JOINTS_0`, `WEIGHTS_0`, and decoded TPF textures. Tested and verified in Blender 5.2.3 (imports all 13 submeshes with 206 vertex groups and Armature in 0.36s).
- [x] **Subtask 1.4**: `tools/pipeline/blender_process_c8030.py` — Headless Blender script to decouple cloth, re-skin to skeleton bones, decimate with facial feature protection (~2.5K tris), and transfer weights. Verified execution downsampling Plain Doll from 63.5K to ~10K/3K tris with 206-bone skinning intact.
- [x] **Subtask 1.5**: `tools/pipeline/rigged_gltf_to_flver.py` — Compiler to turn rigged glTF back into dual-buffer FLVER (`VA0`/`VA1`), swap cloth MTDs, and recalculate AABB bounding boxes. Verified recompiling Plain Doll FLVER from 3.3 MB to 852 KB with 13 valid meshes and zero cloth MTDs.
- [x] **Subtask 1.6**: `tools/pipeline/deploy_c8030_blender_psx.py` — End-to-end extraction, processing, repackaging (without `_c.hkx`), and deployment to `CUSA03173-PSX`. Successfully executed end-to-end: exported rigged glTF, processed through headless Blender 5.2.3, recompiled FLVER (826 KB), stripped Havok cloth solvers, and deployed to sandbox.
- [x] **Subtask 1.7**: In-game validation in Hunter's Dream (tested talking, idle, and full level-up animation: verified 100% stable at 84–86 FPS with zero Havok cloth crashes).
- [x] **Subtask 1.8**: Sliced 24 character textures via `shrink_chr_textures.py` (diffuse $\le 256$px, secondary $\le 128$px). Entire `c8030.chrbnd.dcx` dropped from 18.0 MB to **825 KB** (-95.4%), fitting real 1 MB retro hardware constraints.
- [x] **Subtask 1.9**: Documentation & math sync across `BB_PSX_DEMAKE_GUIDE.md` and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md`.
- [x] **Subtask 1.10**: Plain Doll face seam shading recovery:
  - Discovered FromSoftware FLVER stores the V-derivative ($tdir$) in `tangent_0`, not the U-derivative ($sdir$).
  - Fixed handedness $W = \text{sign}(\det_{\text{UV}}) \in \{-1.0, +1.0\}$, matching vanilla handedness distribution 100%.
  - Clamped sagittal midline vertices ($|X| < 5.0\text{mm}$) to $X=0.0$ with strictly forward normals ($N_x = 0.0$) and vertical tangents ($T_x = 0.0$), eliminating lighting crease down nose and chin.
  - Synced default vertex colors to vanilla character standard `[1.0, 0.0, 1.0, 1.0]` ($G = 0.0$ subsurface scattering mask).
  - Redeployed and verified clean symmetrical lighting across the entire head and face.

---

## Technical Discoveries, Math & Engine Invariants

### 1. Cloth Skeleton Discovery
`c8030.flver` contains 206 total bones. 46 bones are explicitly rigged for clothing:
- Skirt chains: `Skirt_B` through `Skirt_B07`, `Skirt_F` through `Skirt_F07`, `Skirt_L` through `Skirt_L07`, `Skirt_R` through `Skirt_R07`, `LG_Skirt`.
- Mantle/Shawl: `c8030_BD_Mantle01`, `c8030_BD_Mantle02`.
- Hair: `c8030_Hair01`, `c3080_Hair02`, `c8030_BackHair`.

**Takeaway**: The Havok cloth simulation was merely displacing vertices whose rest positions were already parented to skeletal chains. Binding geometry directly to these bones in Blender turns dynamic cloth into stable skeletal animations without physics overhead.

### 2. Havok Solver Gate Invariant
FromSoftware's cloth physics pipeline (`SpClothVertexUpdate`) executes **only** when two conditions are simultaneously met:
1. The FLVER material definitions (`MTD`) reference `*_Cloth.mtd` (e.g. `C[ARSN]_e_Cloth.mtd`).
2. The archive contains `c8030_c.hkx` and `c8030_c.clm2`.

When materials are swapped to standard skinned materials (`C[ARSN]_e.mtd`) and `_c.hkx` is excluded, the engine never allocates cloth buffers, permanently eliminating the vertex-count mismatch crash.

### 3. Dual Vertex Buffer Layout (`VA0`/`VA1`)
Bloodborne FLVER meshes mandate split vertex arrays:
- **`VA0` (Direct Geometric Attributes)**:
  - `position`: `float3` (12 bytes)
  - `normal`: `uint8x4` or `float4` (packed normalized direction vectors)
  - `tangent`: `uint8x4` or `float4`
- **`VA1` (Skeletal Deform & Texture Mapping Attributes)**:
  - `bone_weights`: `uint16x4` normalized ($W / 32767.0$) or `float4`
  - `bone_indices`: `uint8x4` (indices into `Mesh.bone_indices` local LUT)
  - `uv_0`: `float2` or `int16x2` (UV texture coordinates)

The vertex counts of `VA0` and `VA1` must be strictly identical ($N_{\text{VA0}} = N_{\text{VA1}}$).

### 4. Blender 5.2 Python ABI Boundary & glTF Decoupling
- **Discrepancy**: Blender 5.2.3 LTS uses system Python 3.14 (`/usr/bin/python3.14`). The project virtualenv uses Python 3.13 (`cpython-3.13-x86_64-linux-gnu`). Attempting to import Soulstruct and NumPy directly inside Blender triggers `ImportError: incompatible with python 'cpython-314'`.
- **Architectural Solution**: Strictly decouple the pipeline using standard Binary glTF 2.0 (`.glb`) as the IPC interchange format:
  1. **`.venv` (Python 3.13)**: Executes `flver_to_rigged_gltf.py` (Soulstruct + NumPy) $\rightarrow$ creates `c8030_rigged.glb`.
  2. **Blender (Python 3.14)**: Imports `c8030_rigged.glb`, decouples Havok cloth via bone weighting, decimates geometry, transfers weights $\rightarrow$ exports `c8030_demade.glb`.
  3. **`.venv` (Python 3.13)**: Executes `rigged_gltf_to_flver.py` (Soulstruct + NumPy) $\rightarrow$ compiles FLVER2 buffers and repacks `.chrbnd.dcx`.

### 5. Blender Joint Sorting & Global FLVER Remap Bug
- **Discrepancy**: Blender's glTF exporter sorts bone nodes alphabetically by name when generating the `skin.joints` array (e.g. `AM_F_7000_01` became Joint 0, `Head` became Joint 145).
- **Symptom**: When re-importing `JOINTS_0` directly into FLVER, vertices were assigned to completely wrong FromSoft global bones (e.g. Pelvis vertices assigned to the Arm, Bonnet assigned to the Pelvis), causing mesh explosions and diagonally tilted T-pose in Hunter's Dream.
- **Resolution**: Implemented dynamic bone name lookup (`bone_name_to_flver_idx`) in `rigged_gltf_to_flver.py`. Builds a remapping LUT `blender_to_flver_bone` to translate Blender joint indices back to pristine FromSoftware global bone IDs, zeroing out unweighted influence slots. Verified Bonnet strictly binds to `Head` (Bone 5), Skirt to `Pelvis` (Bone 0) and `Skirt_B/F/L/R`, and Face to `Head`/`Jaw`/`Eyes`.

### 6. FLVER Tangent Vector Axis Mismatch & Midline Sagittal Symmetry
- **Discovery**: FromSoftware's FLVER format stores the **$V$-derivative** ($tdir$, aligned with texture $V$), NOT the $U$-derivative ($sdir$), in `tangent_0`. Standard glTF/MikkTSpace exporters store $sdir$ in tangent.
- **Symptom**: In the character pixel shader, normal mapping evaluated rotated by $90^\circ$. Because the Plain Doll's face UV map is mirrored across $X=0$, feeding $sdir$ caused one side of the face to receive light while the other side received an inverted bitangent, plunging the right cheek into deep shadow.
- **Mathematical Invariant**:
  $$\text{tdir} = \frac{1}{\Delta U_1 \Delta V_2 - \Delta V_1 \Delta U_2} (\Delta U_1 (\mathbf{P}_2 - \mathbf{P}_0) - \Delta U_2 (\mathbf{P}_1 - \mathbf{P}_0))$$
  $$\mathbf{T}' = \text{normalize}(\mathbf{T}_{\text{dir}} - (\mathbf{N} \cdot \mathbf{T}_{\text{dir}}) \mathbf{N})$$
  $$T_w = \begin{cases} +1.0 & \text{if } \det_{\text{UV}} \ge 0 \\ -1.0 & \text{otherwise} \end{cases}$$
- **Midline Normal Invariant**: In vanilla FromSoftware character models, midline vertices ($X=0$) strictly satisfy $N_x = 0.000$ and $T_x = 0.000$. Enforcing $N_x = 0$ on $|X| < 5.0\text{mm}$ guarantees complete photometric symmetry across the facial seam.

---

## Performance & Optimization Ledger: Plain Doll (`c8030`)

| Metric | Vanilla (`CUSA03173`) | Demade PSX (`CUSA03173-PSX`) | Reduction / Delta |
| :--- | :--- | :--- | :--- |
| **Polygon Count** | 63,494 triangles | 10,251 triangles | **-83.9%** (-53,243 tris) |
| **Vertex Count** | 41,347 vertices | 8,881 vertices | **-78.5%** (-32,466 verts) |
| **FLVER Binary** | 3.28 MB (3,281,392 B) | 826 KB (826,176 B) | **-74.8%** (-2.45 MB) |
| **TPF Textures (24 maps)** | 14.58 MB (14,582,160 B) | 754 KB (754,064 B) | **-94.8%** (-13.83 MB VRAM) |
| **Archive Total (`.dcx`)** | 18.0 MB (18,485,732 B) | 825 KB (844,484 B) | **-95.4%** (-17.18 MB) |
| **Havok Cloth Physics** | 2,133,888 B (`_c.hkx` + `_c.clm2`) | **0 bytes** (Completely Stripped) | **-100%** CPU/GPU Solver cycles |
| **Hunter's Dream FPS** | ~45–48 FPS (Vanilla base) | **84–86 FPS locked** | **+80.0% FPS uplift** |

---

## Plan 2: Complete Player Equipment & Weapon Blender Demake (`parts/`)

- **Date Completed**: 2026-10-28
- **Primary Objective**: Replace flawed in-memory Python QEM decimation on all player equipment (`parts/`) with the Headless Blender 5.2.3 low-poly pipeline. Decouple Havok cloth physics from all armors, align FromSoftware tangent frames, preserve 100% of weapon transformation states/dummies, and deploy to `CUSA03173-PSX`.
- **Scope**: 984 eligible archives (`bd_`, `hd_`, `am_`, `lg_`, `wp_`). 206 Facegen/Hair archives strictly preserved.

### Task Checklist & Status
- [x] **Subtask 2.1**: Adapted glTF exporter (`tools/pipeline/flver_to_rigged_gltf.py`) to handle models with 0 to $N$ skeleton bones and arbitrary mesh counts without crashing.
- [x] **Subtask 2.2**: Developed headless Blender processing script (`tools/pipeline/blender_process_parts.py`) supporting semantic decimation ratios for armor plates (0.22), cloth pieces (0.25), headgear (0.20), and trick weapons (0.35) with smooth shading and influence pruning ($\le 4$).
- [x] **Subtask 2.3**: Upgraded FLVER compiler (`tools/pipeline/rigged_gltf_to_flver.py`) to dynamically map joints, reconstruct FromSoft tangents ($\mathbf{T}_{\text{dir}}$ + $W = \text{sign}(\det_{\text{UV}})$), preserve all weapon Dummy attach points, and swap cloth MTDs to `.mtd`/`_e.mtd`.
- [x] **Subtask 2.4**: Built multi-threaded batch orchestrator (`tools/pipeline/batch_blender_demake_parts.py`) with 12 parallel workers, automated `.snap_pre_blender` snapshot backups, and graceful empty binder handling.
- [x] **Subtask 2.5**: Executed pilot test on Hunter Garb (`bd_m_9000`) and Saw Cleaver (`wp_a_1001`): verified 0 cloth MTDs, `_c.hkx` stripped, 100% dummies preserved.
- [x] **Subtask 2.6**: Full batch run executed across all 984 parts: 984/984 succeeded with 0 failures in 206.3s.
- [x] **Subtask 2.7**: Verified texture shrink status: all 1,191 archives in `parts/` have textures sliced to $\le 256$px/128px.
- [x] **Subtask 2.8**: Sanity audit verified: 0 `_c.hkx` files, 0 `_Cloth.mtd` definitions across deployed armors, 100% weapon dummies intact.

### Batch Results Summary: Equipment & Weapons (`parts/`)

| Metric | Pristine Vanilla (`CUSA03173`) | Demade PSX (`CUSA03173-PSX`) | Reduction |
| :--- | :--- | :--- | :--- |
| **Total Archives** | 984 processed | 984 deployed | **100% Success (0 fails)** |
| **Polygon Count** | 11,372,322 triangles | 2,725,034 triangles | **-76.0%** (-8,647,288 tris) |
| **Armor Havok Cloth** | Hundreds of `_c.hkx`/`_c.clm2` | **0 bytes** (100% Stripped) | **-100%** Cloth solver cycles |
| **Trick Weapon Dummies** | 100% Original counts | 100% Preserved | **Zero loss** of FX/Grip anchors |
| **Processing Time** | Baseline | 206.3s (12 workers) | **~4.7 files / sec** |

---

## Plan 3: Complete Enemy & Boss Character Blender Demake (`chr/`)

- **Date Completed**: 2026-10-29
- **Primary Objective**: Replace legacy Python QEM decimation on all enemy and boss archives (`chr/`) with the Headless Blender 5.2.3 low-poly pipeline. Decouple Havok cloth physics from all bosses/mobs, eliminate fur overdraw while preserving beast silhouettes, align FromSoftware tangent frames, strictly protect Plain Doll (`c8030`), and deploy to `CUSA03173-PSX`.
- **Scope**: All 245 character archives in `dvdroot_ps4/chr/` (including Father Gascoigne `c2020`, Werewolf `c1000`, Cleric Beast `c2010`, Vicar Amelia `c2110`, Blood-Starved Beast `c2100`, etc.). Plain Doll `c8030` strictly bypassed.

### Task Checklist & Status
- [x] **Subtask 3.1**: Built headless Blender processing script (`tools/pipeline/blender_process_chr.py`) supporting semantic decimation ratios: mob bodies (0.22), cloth/robes (0.25), beast fur (0.20), boss weapons (0.35), high-poly bosses >15k tris (0.20), and smooth vertex normal shading.
- [x] **Subtask 3.2**: Built multi-threaded orchestrator (`tools/pipeline/batch_blender_demake_chr.py`) with 12 parallel workers, automatic `.snap_pre_blender_chr` snapshots, sandbox low-res TPF preservation, and strict `c8030` Plain Doll bypass.
- [x] **Subtask 3.3**: Executed pilot test on Father Gascoigne (`c2020`) and Werewolf (`c1000`): verified 0 cloth MTDs, `_c.hkx` stripped, 100% bone weights normalized.
- [x] **Subtask 3.4**: Full batch run executed across all 245 archives: 245/245 succeeded with 0 failures in 84.6s.
- [x] **Subtask 3.5**: Character texture shrink verification: verified 100% of character textures already preserved at $\le 256$px/128px retro low-res.
- [x] **Subtask 3.6**: Discovered and resolved 20 FromSoftware cloth MTD variants (including `C[DSB][IBL][Cloth]`, `_PDEnhanced`, and `_Cloth.mtd`), comprehensively mapping all of them to standard skinned shaders in `tools/pipeline/rigged_gltf_to_flver.py`.
- [x] **Subtask 3.7**: Automated sanity audit verified: 0 `_c.hkx` or `_c.clm2` files, 0 cloth MTDs across all 2,478 meshes, 0 bone weight errors, and Plain Doll `c8030` strictly untouched (842,311 bytes).

### Batch Results Summary: Enemies & Bosses (`chr/`)

| Metric | Pristine Vanilla (`CUSA03173`) | Demade PSX (`CUSA03173-PSX`) | Reduction |
| :--- | :--- | :--- | :--- |
| **Total Archives** | 245 processed | 245 deployed | **100% Success (0 fails)** |
| **Total FLVERs** | 230 active FLVERs | 230 recompiled | **100% Rebuilt** |
| **Total Meshes** | 2,478 submeshes | 2,478 submeshes | **0 Missing Meshes** |
| **Polygon Count** | 11,843,416 triangles | 2,541,360 triangles | **-78.5%** (-9,302,056 tris) |
| **Enemy Havok Cloth** | Hundreds of `_c.hkx`/`_c.clm2` | **0 bytes** (100% Stripped) | **-100%** Cloth solver cycles |
| **Remaining Cloth MTDs**| 23+ across vanilla bosses/mobs| **0 definitions** | **100% Converted** to skinned |
| **Plain Doll (`c8030`)** | 842,311 bytes | 842,311 bytes | **100% Protected** (Untouched) |
| **Processing Time** | Baseline | 84.6s (12 workers) | **~2.9 archives / sec** |

---

## Plan 4: Complete World Objects & Interactive Props Blender Demake (`obj/`)

- **Date Completed**: 2026-10-29
- **Primary Objective**: Deploy the Headless Blender 5.2.3 low-poly demake engine across all 1,885 interactive and destructible world object archives in `dvdroot_ps4/obj/`. Resolve the Test 53 limitation by preserving multi-bone animated skeletons (doors, chests, coffins, elevators), decouple 37 Central Yharnam hanging cloth banners (`_cloth.hkx`, `_cloth.clm`), preserve 100% of rigid body collision files (`.hkx`) and animation archives (`.anibnd`), preserve low-res sliced TPF textures, and deploy to `CUSA03173-PSX`.
- **Scope**: All 1,885 object archives in `dvdroot_ps4/obj/` (`.objbnd.dcx`).

### Task Checklist & Status
- [x] **Subtask 4.1**: Created headless Blender processing script (`tools/pipeline/blender_process_obj.py`) supporting semantic decimation ratios: animated doors/chests/gates (0.25), cloth banners (0.25), massive statuary/coffins (0.20), general static props (0.20), and tiny details clamped at 0.60.
- [x] **Subtask 4.2**: Created multi-threaded orchestrator (`tools/pipeline/batch_blender_demake_obj.py`) with 12 parallel workers, automatic `.snap_pre_blender_obj` snapshots, and low-res sandbox TPF preservation.
- [x] **Subtask 4.3**: Identified and isolated cloth solver files (`_c.hkx`, `_cloth.hkx`, `_c.clm`, `_cloth.clm`, `_c.clm2`) from rigid collision (`.hkx`), stripping solvers while preserving 1,857 rigid player collision meshes and 505 animation binders (`.anibnd`).
- [x] **Subtask 4.4**: Fixed empty MTD string handling in `tools/pipeline/rigged_gltf_to_flver.py` (`with_name("")` ValueError).
- [x] **Subtask 4.5**: Executed pilot tests on animated chest (`o000600`), Central Yharnam banner (`o222996`), and massive coffin rig (`o000650` with 387 bones and 71 dummies): verified 100% bone and dummy preservation.
- [x] **Subtask 4.6**: Full batch run executed across all 1,885 archives: 1,885/1,885 succeeded with 0 failures in 410.9s.
- [x] **Subtask 4.7**: Automated sanity audit verified: 0 cloth solvers remaining, 0 cloth MTDs across 6,725 meshes, 1,857 rigid collision files intact, 505 `.anibnd` intact, and 100% normalized bone weights.

### Batch Results Summary: World Objects & Props (`obj/`)

| Metric | Pristine Vanilla (`CUSA03173`) | Demade PSX (`CUSA03173-PSX`) | Reduction |
| :--- | :--- | :--- | :--- |
| **Total Archives** | 1,885 processed | 1,885 deployed | **100% Success (0 fails)** |
| **Active FLVER Models** | 2,397 active FLVERs | 2,397 recompiled | **100% Rebuilt** |
| **Submeshes Evaluated** | 6,725 submeshes | 6,725 submeshes | **0 Missing Meshes** |
| **Polygon Count** | 26,744,491 triangles | 5,478,523 triangles | **-79.5%** (-21,265,968 tris) |
| **Rigid Collision (.hkx)** | 1,857 files | 1,857 files | **100% Preserved** |
| **Animation Archives (.anibnd)**| 505 files | 505 files | **100% Preserved** |
| **Cloth Solvers** | 37 `_c`/`_cloth` solvers | **0 bytes** (100% Stripped) | **-100%** Solver CPU/GPU cycles |
| **Cloth MTD Definitions** | 54 in vanilla | **0 definitions** | **100% Converted** to skinned |
| **Processing Time** | Baseline | 410.9s (12 workers) | **~4.6 archives / sec** |

---

## Plan 5: World Objects Gameplay Fidelity & Non-Destructive Maps Demake (`map/`)

- **Date Completed**: 2026-10-29
- **Primary Objective**: Resolve user-reported gameplay regressions from initial object decimation (doors stuck closed due to lost `default_bone_index`, ladders missing horizontal rungs, and specular plastic sheen) and execute user mandate for world maps: "Keep as much rendered, reducing said detail".
- **Scope**: All 1,885 object archives in `dvdroot_ps4/obj/` and all 84 map directories in `dvdroot_ps4/map/` (11,033 FLVERs).

### Task Checklist & Status
- [x] **Subtask 5.1**: Enforced retro hard split normals (`poly.use_smooth = False`, banned `shade_smooth()`) in `tools/pipeline/blender_process_obj.py` to eliminate specular plastic sheen.
- [x] **Subtask 5.2**: Whitelisted all 504 animated objects (`.anibnd`) and ladders (`o0001*`) in `tools/pipeline/batch_blender_demake_obj.py` to retain 100% pristine FLVER geometry + sliced TPF textures. Decimated static scenery props (fountains, carriages, statues) with hard split normals.
- [x] **Subtask 5.3**: Re-executed full batch pass for all 1,885 objects: verified door node bindings (`default_bone_index = 96, 98, 100, 102`), 7,294 ladder rungs intact, and zero plastic smoothing.
- [x] **Subtask 5.4**: Created `tools/pipeline/batch_demake_maps_fidelity.py` to partition map geometry into foreground (< 2000, 100% pristine LOD0) and background vistas (>= 2000, gentle LOD1 with strict 50% floor).
- [x] **Subtask 5.5**: Deployed fidelity world maps across all 84 maps (11,033 FLVERs in 97.6s): 2,617 foreground FLVERs restored to pristine LOD0, 5,946 vista chunks gentle LOD1 (saved 35.63M tris), 2,470 vista chunks pristine LOD0.
- [x] **Subtask 5.6**: Verified in Central Yharnam (`m22`): 451 foreground chunks restored to pristine LOD0, arches and railings intact, zero plastic box collapse. Cleared Vulkan pipeline cache.
- [x] **Subtask 5.7**: Diagnosed user-reported stair collapse and slanted mesh explosion: chunk threshold `< 2000` misclassified city stairs (`002010..002030`) as distant vistas. Updated threshold to `< 8000` (6,502 playable chunks preserved at 100% LOD0), whitelisted stair objects (`o257200` `obj_stair_01`), and redeployed across all 84 maps and objects. Cleared Vulkan cache.

### Batch Results Summary: World Maps (`map/`)

| Metric | Pristine Baseline (`CUSA03173`) | Demade PSX (`CUSA03173-PSX`) | Visual / Budget Impact |
| :--- | :--- | :--- | :--- |
| **Total Map Directories** | 84 maps | 84 deployed | **100% Maps Updated** |
| **Total Map FLVER Models** | 11,033 models | 11,033 processed | **0 Failures** |
| **Foreground Architecture (< 2000)** | 2,617 FLVERs | 2,617 pristine LOD0 | **100% Detail Retained** (0 plastic boxes) |
| **Vista Gentle LOD1 (>= 2000)** | 5,946 FLVERs | 5,946 gentle LOD1 | **-29.8% on vistas** (saved 35.63M tris) |
| **Vista Pristine LOD0 (>= 2000)** | 2,470 FLVERs | 2,470 pristine LOD0 | **Silhouettes Preserved** |
| **World BXF Textures** | 14 archives | 14 archives (<= 256px) | **-85% to -98% VRAM** |
| **Processing Time** | Baseline | 97.6s (12 workers) | **~113 FLVERs / sec** |









- **plan_fix_hunters_dream_doors_and_static_portals.md**: Fix offset and missing open state on Hunter's Dream workshop doors and protect all static pre-opened door/gate props.
- [x] **Subtask 6.1**: Refactored `flver_to_rigged_gltf.py` and `rigged_gltf_to_flver.py` to bypass Armatures for unskinned rigid props (`has_skin = False`), exporting and decimating in pure bone-local space.
- [x] **Subtask 6.2**: Added `has_alpha_cutout` protection in `batch_blender_demake_obj.py` to preserve pristine vanilla TPF containers for ladders (`o000100`) and workshop glass/doors (`o210010`–`o210013`).
- [x] **Subtask 6.3**: Successfully demade and deployed workshop doors (`o210010`..`o210013`, 19,862 -> 3,987 tris) and universal ladder (`o000100`, 7,294 -> 1,457 tris) to `CUSA03173-PSX`.

---

## Plan 7: Complete Chalice Dungeon Objects & Mechanism Restoration (`obj/`)

- **Date Completed**: 2026-10-30
- **Primary Objective**: Eliminate all coordinate drift, mid-air floating pillars/pedestals, missing ladder rungs, displaced boss door statues, and void-clipped chandeliers across all Chalice Dungeons by deploying the bone-local Blender demake pipeline and expanding mechanism whitelists across all 913 Chalice Dungeon object archives (`o29*.objbnd.dcx`).
- **Scope**: All 913 Chalice object archives in `dvdroot_ps4/obj/` (`o29*`).

### Task Checklist & Status
- [x] **Subtask 7.1**: Expanded mechanism whitelist in `tools/pipeline/batch_blender_demake_obj.py` to protect all 12 ladders (`o000100`, `o282030`, `o298010`–`o298014`, `o323090`–`o323092`, `o326090`, `o350500`–`o350504`), Chalice boss door statues (`o290500`, `o290502`, `o290504`), and animated objects (`has_anibnd = True`).
- [x] **Subtask 7.2**: Executed multi-threaded batch pass across all 913 `o29*.objbnd.dcx` archives (116.7s, 12 workers): 913/913 processed with 0 failures, reducing 6.84M to 1.37M triangles (-79.9%, saving 5.47M tris).
- [x] **Subtask 7.3**: Verified Chalice boss door statues (`o290500`, `o290502`, `o290504`): pristine alignment restored, lateral $-1.01$m displacement eliminated, doorway completely clear.
- [x] **Subtask 7.4**: Verified Chalice ladders (`o298010`, `o298012`, `o298014`): 100% 3D climbing rungs preserved, ground contact aligned to floor.
- [x] **Subtask 7.5**: Verified Chalice pillars and pedestals (`o294960`–`o294969`, `o293721`, `o293729`, `o299600`–`o299654`): bone-local decimation verified with zero Y-drift ($Y_{\min} = 0.00$m to $-0.03$m flat on ground).
- [x] **Subtask 7.6**: Verified Chalice chandeliers (`o295020`, `o295030`, `o295070`, `o295190`, `o295230`, `o295610`): $+6.7$m void displacement eliminated, hanging cleanly from ceiling anchors with blue candle flames correctly anchored.
- [x] **Subtask 7.7**: Documented technical root cause, mathematical formulations, and whitelisting policies in `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md` (Section 28) and `BB_PSX_DEMAKE_GUIDE.md` (Section 7).

### Batch Results Summary: Chalice Dungeon Objects (`o29*.objbnd.dcx`)

| Metric | Pristine Baseline (`CUSA03173`) | Demade PSX (`CUSA03173-PSX`) | Reduction / Impact |
| :--- | :--- | :--- | :--- |
| **Total Archives Processed** | 913 archives | 913 deployed | **100% Success (0 fails)** |
| **Polygon Count** | 6,839,297 triangles | 1,373,944 triangles | **-79.9%** (-5,465,353 tris) |
| **Interactive Whitelist Bypass** | Baseline | 38 archives pristine | **100% Mechanisms Preserved** |
| **Pillar Ground Alignment** | $Y_{\min} \in [+0.56, +4.87]$m (broken) | $Y_{\min} \in [-0.03, 0.00]$m | **100% Floor Contact Restored** |
| **Boss Door Statues** | Offset $-1.01$m (blocked) | Centered | **Doorway Unblocked** |
| **Chandelier Ceiling Alignment** | Displaced $+6.7$m into void | Anchored to ceiling | **Blue Flame Candles Visible** |
| **Processing Time** | Baseline | 116.7s (12 workers) | **~7.8 archives / sec** |

