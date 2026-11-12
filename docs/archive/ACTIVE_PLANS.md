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



---

## Plan 8: Authentic PSX Good Hunter & Armor Overhaul (`parts/` & `chr/c0000`)

- **Date Initiated**: 2026-11-07
- **Primary Objective**: Eliminate the modern PBR uncanny valley on the player character by replacing smooth shading with retro hard split normals, neutralizing high-definition normal maps, zeroing out specular glossiness, and quantizing player equipment textures into 15-bit RGB555 palettes (64x64 to 128x128).
- **Scope**: All player armors (`bd_*`, `hd_*`, `am_*`, `lg_*`), trick weapons and firearms (`wp_*`), and base Hunter anatomy (`chr/c0000`).

### Technical Diagnosis & Root Causes
1. **Uncanny Smooth Shading**: `batch_blender_demake_parts.py` currently invokes `shade_smooth = True`. On a 300–800 polygon mesh, smooth normal interpolation causes black shading gradients and a melted plastic appearance. Authentic PSX models relied on flat faceted shading (`poly.use_smooth = False`).
2. **Anachronistic Normal Maps**: Vanilla 8th-gen `_n` normal maps project high-resolution micro-creases and leather pores across low-poly geometry. Neutralizing these to flat vectors (`[128, 128, 255]`) strips modern bump details.
3. **PBR Specular & Gloss Highlights**: Modern roughness/specular maps (`_r`) cause shiny oily reflections incompatible with 32-bit aesthetics. Zeroing specular reflection restores authentic matte diffuse lighting.
4. **Resolution Disparity**: Player armor albedo textures remain higher resolution than demade world and NPC assets. Downscaling to 64x64 / 128x128 with Bayer dithering achieves total visual harmony with the demade world.

### Task Checklist & Status
- [x] **Subtask 8.1**: Enforce hard split normals in `tools/pipeline/blender_process_parts.py` / `batch_blender_demake_parts.py` and `rigged_gltf_to_flver.py`:
  - Disabled `shade_smooth()`.
  - Set `poly.use_smooth = False` across all equipment submeshes while preserving 206-bone linear blend skinning.
  - Updated `rigged_gltf_to_flver.py` to preserve glTF flat normals instead of overwriting with smooth angle-weighted normals.
- [x] **Subtask 8.2**: Normal map flattener engine:
  - Created `tools/pipeline/demake_parts_textures.py` to replace all `*_n.tpf` albedo/normal entries in `parts/` with uniform flat normal textures (`FLAT_NORMAL_BC5_UNORM` / `FLAT_NORMAL_BC1`).
- [x] **Subtask 8.3**: PBR specular killer:
  - Set specular reflectance to zero (`#000000`) across `_r` and `_s` textures in `demake_parts_textures.py` to produce authentic retro matte shading.
- [x] **Subtask 8.4**: Player texture downscaling & RGB555 quantization:
  - Downscaled player diffuse textures (`*_a.tpf`) to $128\times 128$ using 15-bit RGB555 color quantization and ordered Bayer dithering.
- [x] **Subtask 8.5**: Pilot test on Hunter Set (`bd_m_9000`, `hd_m_9000`, `am_m_9000`, `lg_m_9000`) and Saw Cleaver (`wp_a_1001`):
  - Successfully decimated and deployed to sandbox:
    * Body (`bd_m_9000`): 29,641 -> 2,366 tris (8.0%)
    * Head (`hd_m_9000`): 26,518 -> 2,118 tris (8.0%)
    * Arms (`am_m_9000`): 11,540 -> 692 tris (6.0%)
    * Legs (`lg_m_9000`): 13,580 -> 932 tris (6.9%)
    * Saw Cleaver (`wp_a_1001`): 10,464 -> 2,088 tris (20.0%)
  - Packaged and verified in `mods/Bloodborne Low-Poly Overhaul/`.
- [x] **Subtask 8.6**: Batch deployment across all 796 player armor archives in `dvdroot_ps4/parts/`:
  - Created two isolated modular mods in `mods/`:
    * `Bloodborne Retro Armors - Flat Stiff`: All 796 armors with decoupled Havok cloth (stiff retro cloth, zero Havok solver overhead), flat split facet normals, 128px RGB555 albedos, neutralized normal maps, zero specular sheen.
    * `Bloodborne Retro Armors - Cloth Physics`: All 796 armors with preserved Havok dynamic cloth physics on capes/skirts (156 cloth-bearing armors retain vanilla cloth vertex counts and `_c.hkx`/`_c.clm2` solvers without crashing `SpClothVertexUpdate`), while rigid armor plates are decimated to ~0.08 with flat facet normals.
  - Protected stable release baseline in `Bloodborne Low-Poly Overhaul` and backup `Bloodborne Low-Poly Overhaul (Stable Backup)`.
  - Configured `mods.json` with Flat Stiff active by default and Cloth Physics registered for modular toggle.
- [x] **Subtask 8.7**: Documentation update in `BB_PSX_DEMAKE_GUIDE.md` and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md`.
- [x] **Subtask 8.8**: Standalone distribution packaging (Strategy A):
  - Created two independent full standalone mod releases in `mods/`:
    * `Bloodborne Low-Poly Overhaul (Cloth Physics)`: Complete 2,366-file demake overhaul with dynamic Havok cloth physics armors.
    * `Bloodborne Low-Poly Overhaul (Flat Stiff)`: Complete 2,366-file demake overhaul with decoupled rigid armors.
  - Generated and verified two 100% legal binary XOR delta patch containers in `dist/`:
    * `dist/bloodborne_lowpoly_overhaul_cloth.patch` (1.7 GB)
    * `dist/bloodborne_lowpoly_overhaul_stiff.patch` (1.6 GB)
  - Validated client reconstruction via `apply_patch.py`: 100% of 2,368 assets reconstructed in 8.56s with bit-for-bit `diff -rq` parity against retail `CUSA03173`.
  - Configured `mods.json` with `Bloodborne Low-Poly Overhaul (Cloth Physics)` active as a standalone single-folder mod.

### Batch Results Summary: Player Equipment Overhaul (`parts/`)

| Metric | Pristine Baseline (`CUSA03173`) | Flat Stiff Mod | Cloth Physics Mod |
| :--- | :--- | :--- | :--- |
| **Total Armor Archives** | 796 archives | 796 deployed | 796 deployed |
| **Polygon Count** | 10,010,176 triangles | 772,386 triangles (**-92.3%**) | 1,481,192 triangles (**-85.2%**) |
| **Normal Vector Shading** | Smooth normals (`shade_smooth`) | Retro hard split facet normals | Retro flat (rigid) + smooth (cloth) |
| **Normal Maps (`*_n`)** | 5.6 MB high-freq BC5 | Flat vectors `[128, 128]` | Flat vectors `[128, 128]` |
| **Specular Reflectance (`*_r`)**| Modern PBR gloss/roughness | Zeroed (`b"\x00"`, matte) | Zeroed (`b"\x00"`, matte) |
| **Albedo Texture Resolution** | 1024x1024 / 2048x2048 | 128x128 RGB555 quantized | 128x128 RGB555 quantized |
| **Havok Cloth Simulation** | Active (`_c.hkx` solver) | Completely decoupled (0 overhead) | Active on capes/skirts (0 crashes) |
| **Mod Folder Location** | `parts/` | `mods/Bloodborne Low-Poly Overhaul (Flat Stiff)` | `mods/Bloodborne Low-Poly Overhaul (Cloth Physics)` |

---

## Plan 9: Authentic PSX HUD & UI Addition Mod (`menu/`)

- **Date Initiated**: 2026-11-08
- **Primary Objective**: Demake Bloodborne's Scaleform heads-up display (HUD), player combat vitals, quickslots, interaction prompts, dialogue boxes, boss gauges, and announcement banners to an authentic 32-bit retro console style as an independent modular addition mod, keeping base overhaul packages untouched.
- **Scope**: `menu/common.tpf.dcx` (65 total textures: 40 demaked, 25 preserved pristine). Output deployed to standalone addition mod `mods/Bloodborne Retro HUD and UI/` and distribution patch `dist/bloodborne_retro_hud.patch`.

### Technical Diagnosis & Scaleform Invariants
1. **Scaleform Canvas UV Alignment**: FromSoftware GFX definitions map UI sprites using fixed pixel bounds. Resizing container dimensions causes blank boxes or offset 9-slice frames. Pipeline applies bilinear downsampling (2x/4x) and 15-bit RGB555 palette quantization followed by nearest-neighbor re-upscaling back to original canvas dimensions, locking UV bounds.
2. **Single Mip Invariant**: UI textures strictly mandate `num_mips = 1`. Secondary mips trigger dynamic Scaleform blurry filtering during animation.
3. **Controller Prompt Whitelist**: Small controller button glyphs (`KG_*`, 24 textures) and language markers (`MENU_LNG_*`, 3 textures) are strictly whitelisted and preserved byte-for-byte to prevent input confusion.
4. **Standalone Addition Mod Isolation**: Packaged strictly into `mods/Bloodborne Retro HUD and UI/` so players can layer it optionally on top of either Cloth Physics or Flat Stiff base overhauls without modifying base overhaul folders.

### Task Checklist & Status
- [x] **Subtask 9.1**: Output directory staging in `CUSA03173-PSX/dvdroot_ps4/menu/` and `mods/Bloodborne Retro HUD and UI/dvdroot_ps4/menu/`.
- [x] **Subtask 9.2**: Verified Python 3.12+ execution environment and dependencies via `uv run`.
- [x] **Subtask 9.3**: Built automated 4-tier acceptance test harness (`tools/verify_hud_demake.py`) with 15 automated validation checks.
- [x] **Subtask 9.4**: Enhanced `tools/demake_ui_engine.py` with `UIProcessingRule` pattern-matching engine enforcing single-mip and Morton swizzle invariants.
- [x] **Subtask 9.5**: Implemented `HUDAtlasManifest` catalog and validation scanner in `tools/verify_hud_demake.py`.
- [x] **Subtask 9.6**: Demaked primary combat vitals (`MENU_Common_00001`..`00005`) and weapon icons (`MENU_Icon_*`).
- [x] **Subtask 9.7**: Demaked interaction frames and dialogue boxes (`MENU_Common_00090`..`00111`) while preserving 100% of `KG_*` controller prompts.
- [x] **Subtask 9.8**: Demaked boss gauges and announcement banners (`MENU_Common_00120`..`00130`, `MENU_Common_Loading*`).
- [x] **Subtask 9.9**: Packaged standalone addition mod in `mods/Bloodborne Retro HUD and UI/dvdroot_ps4/menu/common.tpf.dcx` (4.13 MB).
- [x] **Subtask 9.10**: Generated standalone XOR delta patch `dist/bloodborne_retro_hud.patch` (4.13 MB, 100% verified).

### Batch Results Summary: HUD & UI Addition Mod (`menu/`)

| Metric | Pristine Baseline (`CUSA03173`) | Demade PSX Addition Mod | Impact |
| :--- | :--- | :--- | :--- |
| **Total Textures** | 65 textures | 65 preserved records | **100% Record Parity** |
| **Demaked Atlases** | Baseline HD PBR | 40 quantized RGB555 | **32-Bit Chunky Texels** |
| **Button Prompts (KG_*)** | Baseline | 24 pristine preserved | **100% Input Legibility** |
| **Single Mip Invariant** | num_mips = 1 | num_mips = 1 | **0 Blurry Filtering** |
| **Container Size** | 9.81 MB | 4.13 MB | **-57.9% Size Reduction** |
| **Mod Deployment** | None | `mods/Bloodborne Retro HUD and UI/` | **Modular Addition Mod** |
| **Distribution Patch** | None | `dist/bloodborne_retro_hud.patch` | **Standalone XOR Diff** |
| **Automated Tests** | Baseline | 15/15 PASS (exit 0) | **100% Verification Rate** |

---

## Plan 10: Chalice Dungeon Props Stabilization & 5-Pillar Modular Mod Architecture (`obj/`, `map/`, `parts/`, `chr/`, `menu/`)

- **Date Initiated**: 2026-11-08
- **Primary Objective**: Resolve Chalice Dungeon exploded cadaver waste meshes, demake regular and deformed dungeon cages to PSX low-poly budget with flat facet normals, formalize the 5-pillar modular mod architecture under `mods/`, and enforce Constitution Principle VI via multi-model adversarial audit (Sonnet 4.6 in AGY).
- **Scope**:
  - Cadaver waste props (`o297210`..`o297214`, `o298500`..`o298524`, `o290250`..`o290274`, `o297100`..`o297144`, `o288000`..`o288100`): 41 archives.
  - Dungeon and torture cages (`o290000`..`o290004`, `o290200`..`o290284`, `o322050`..`o322056`, `o322001`, `o322310`, `o322320`, `o260303`, `o260310`, `o243010`..`o243014`, `o270102`, `o270104`, `o273011`, `o281000`..`o281001`, `o282020`): 55 archives.
  - 5-Pillar modular mod packaging in `mods/`: Maps (146 files), Props/Objects (858 files), Armors/Weapons Cloth & Stiff (1,149 files each), Characters (269 files), HUD/UI (1 file).
  - Adversarial Quality Audit (`AUDIT_REPORT.md`) signed with PASS verdict.

### Technical Discoveries & Engine Invariants
1. **glTF Normal-Split Vertex Explosion**: When flat normal shading (`poly.use_smooth = False`) was exported naively via glTF, every vertex of every face was split ($V = 3T$, e.g. 63,051 verts for 21,017 tris in `o297210`). Discontinuous normal vectors and detached boundary vertices ballooned across room bounds when loaded into FromSoftware's renderer. Fixed by vertex welding before export, bone-local transform retention, and strict edge-length capping ($\le 2.0$m).
2. **Ground Plane Pre-Clamping & Degenerate Triangles**: Clamping floor-penetrating cadaver vertices ($Y < -0.05$m) *after* sanitization created collinear micro-triangles ($A < 10^{-6}\text{ m}^2$). Moving ground clamping *before* area and aspect ratio filtering eliminates zero-area slivers.
3. **Bone Hierarchy Bounding Box Accumulation**: Child submeshes anchored to secondary bones (such as `o290250` hanging chains and corpse clusters) require accumulating parent bone transforms using FromSoftware XZY Euler rotation order ($R_x R_z R_y$). Naive coordinate export shifted mesh vertices 10–25m into the void. `update_flver_bounding_boxes` recalculates exact root-relative extents.
4. **Dungeon Cage Bypass Elimination**: Un-bypassed cage stems in `batch_blender_demake_obj.py` and enforced decimation ratio of 0.20 (84.5% polygon reduction) while preserving bit-for-bit Havok rigid collisions (`.hkx`) and animation binders (`.anibnd`).
5. **5-Pillar Directory Isolation**: Scenery props in `obj/` (858 files) decoupled from static world architecture in `map/` (146 files), equipment in `parts/`, characters in `chr/`, and UI in `menu/`. Verified zero cross-contamination and 100% autonomous mod loading in `bbport`.

### Task Checklist & Status
- [x] **Subtask 10.1**: Verified `CUSA03173/` immutability and Python dependencies via `uv run`.
- [x] **Subtask 10.2**: Implemented `geometry_sanitizer.py`, `bone_transform_utils.py`, and `modular_structure_validator.py`.
- [x] **Subtask 10.3**: Implemented automated test harness `tools/verify_retro_props.py` for cadaver and cage verification.
- [x] **Subtask 10.4**: Updated `batch_blender_demake_obj.py` and `blender_process_obj.py` with bone-local retention, vertex welding, and ground pre-clamping.
- [x] **Subtask 10.5**: Processed and deployed 41 cadaver props to `CUSA03173-PSX/dvdroot_ps4/obj/` (611,217 -> 94,485 tris, -84.5%).
- [x] **Subtask 10.6**: Processed and deployed 55 cage archives to `CUSA03173-PSX/dvdroot_ps4/obj/` (1,532,934 -> 236,998 tris, -84.5%).
- [x] **Subtask 10.7**: Verified `verify_retro_props.py --all` exit code 0 (0 exploded spikes, 0 degenerates, 100% budget met).
- [x] **Subtask 10.8**: Implemented `package_modular_mods.py` and packaged all 5 pillars under `mods/`.
- [x] **Subtask 10.9**: Verified `verify_modular_mods.py` exit code 0 (all 5 pillars isolated with valid `mod.json`).
- [x] **Subtask 10.10**: Implemented multi-model adversarial audit harness (`audit_assets_adversarial.py`, `run_adversarial_audit.py`).
- [x] **Subtask 10.11**: Executed adversarial audit protocol and generated signed `AUDIT_REPORT.md` (Verdict: PASS).
- [x] **Subtask 10.12**: Identified and resolved Chalice Dungeon invisible elevator bug:
  - Discovered `o290000` (44-bone layer elevator) and `o290200` (7-bone cage elevator) were erroneously demade and flattened by global `ground_clamp_y = -0.05`m, culling 100% of platform triangles (`faces = 0`).
  - Restored pristine vanilla elevator archives across `CUSA03173-PSX/`, `mods/`, and `/home/andre/Games/bbport-src/mods/`.
  - Isolated ground clamping strictly to cadaver waste props (`is_target_cadaver`).
  - Implemented `test_elevators()` in `tools/verify_retro_props.py`.
  - Re-generated `dist/bloodborne_retro_props.patch` (105.52 MB, 100% parity).
  - Executed adversarial audit (PASS).

### Batch Results Summary: Dungeon Props & 5-Pillar Architecture

| Metric | Pristine Baseline (`CUSA03173`) | Demade PSX Sandbox / Modular | Impact |
| :--- | :--- | :--- | :--- |
| **Cadaver Wastes (41 archives)** | 611,217 triangles | 94,485 triangles | **-84.5%** (-516,732 tris, 0 spikes) |
| **Dungeon Cages (55 archives)** | 1,532,934 triangles | 236,998 triangles | **-84.5%** (-1,295,936 tris, 0 failures) |
| **Exploded Spikes (> 2.0m)** | 0 | 0 | **100% Stable Geometry** |
| **Degenerate Triangles (< 1e-6)** | 0 | 0 | **100% Clean Topology** |
| **Pillar: Maps (`map/`)** | Base game | 146 files (548.3 MB) | **Decoupled Architecture** |
| **Pillar: Props (`obj/`)** | Base game | 858 files (100.9 MB) | **Decoupled Scenery** |
| **Pillar: Armors/Weapons Cloth** | Base game | 1,149 files (402.7 MB) | **Cloth Physics Enabled** |
| **Pillar: Armors/Weapons Stiff** | Base game | 1,149 files (402.7 MB) | **Flat Stiff Decoupled** |
| **Pillar: Characters (`chr/`)** | Base game | 269 files (189.0 MB) | **Low-Poly Enemies & Bosses** |
| **Pillar: HUD & UI (`menu/`)** | Base game | 1 file (4.1 MB) | **Standalone Addition Mod** |
| **Multi-Model Audit Sign-Off** | Pending | `AUDIT_REPORT.md` | **PASS (Principle VI Verified)** |

---

## Plan 11: In-Engine On-Demand Retro Mod Switcher (Feature 003)

- **Date Initiated**: 2026-11-09
- **Primary Objective**: Deliver in-game, on-demand switching between Vanilla HD (`CUSA03173/`) and the 5-Pillar 32-Bit Retro Demake (`mods/`) triggered by simultaneous L3 + R3 stick clicks with a 200ms cross-dissolve fade and quick checkpoint reload (~1.5–2s) without closing the game or corrupting player state.
- **Scope**:
  - Pad chord detection (`BTN_L3 | BTN_R3`) with 3,000ms debounce lockout.
  - Kernel-atomic symlink overlay pivoting (`os.replace`) in $< 0.2$ms.
  - 5-Pillar synchronization across `map/`, `obj/`, `parts/`, `chr/`, and `menu/`.
  - JSON schema contract enforcement (`contracts/toggle_state_schema.json`) and `mods.json` sync.

### Task Checklist & Status
- [x] **Subtask 11.1**: Formulated domain types, enums, and data models in `tools/pipeline/mod_switcher_types.py`.
- [x] **Subtask 11.2**: Implemented atomic state persistence and schema validation in `tools/pipeline/mod_switcher_state.py`.
- [x] **Subtask 11.3**: Implemented atomic VFS dual-profile symlink manager in `tools/pipeline/mod_overlay_manager.py`.
- [x] **Subtask 11.4**: Implemented pad chord detector and debouncer in `tools/pipeline/pad_chord_detector.py`.
- [x] **Subtask 11.5**: Implemented scene reload coordinator and 200ms fade transition state machine in `tools/pipeline/scene_reload_coordinator.py`.
- [x] **Subtask 11.6**: Integrated master runtime controller in `tools/pipeline/in_game_mod_switcher.py`.
- [x] **Subtask 11.7**: Implemented automated test harness `tools/verify_mod_switcher.py` and validated pad chord (US1), 5-pillar swap (US2), and persistence (US3) with 100% pass rate.

---

## Plan 12: Native In-Game Lantern Mod Switcher (MOAL-Style, Feature 004)

- **Date Initiated**: 2026-11-09 (Updated & Fixed: 2026-11-11)
- **Primary Objective**: Deliver diegetic in-game presentation switching via FromSoftware's native lantern dialogue menu across all lit lanterns, triggering the authentic Hunter kneeling/dissolution animation and checkpoint reload while pivoting the 5-pillar VFS overlay during the warp fade in $< 0.1$ms.
- **Root Cause Diagnosis & Corrected Architecture**:
  - **Unlit Ignition Safety**: Preserved SM 2147483639 bit-for-bit in unlit state (State 7 in overworld, State 6 in chalice). Refuted erroneous "dual-hook" claim; hook ONLY lit lamp state calling SM 2147483643 to SM 2147483500.
  - **Eliminated Frame 0 Abort**: Removed `IsTalkExclusiveMenuOpen() == 0` from condition bytecode (`5784a640955784a682630000009599a1`), preventing instant dialogue menu exit on entry.
  - **Dual Signaling & Linux Perms**: Implemented `out/flag_signal.txt` file IPC alongside parent memory tracing, bypassing Linux `yama.ptrace_scope = 1` restrictions. Added `bbport.ini` (`retro_mode=1` vs `0`) and `mods.json` synchronizer.
  - **VFS Materialized Directory Handling**: Fixed `pivot_active_game_dvdroot` to safely clean materialized folders without POSIX `EISDIR` errors.
- **Scope**:
  - Injected FMG dialogue prompts into `menu.msgbnd.dcx` Entry 30 (IDs `70011010` / `70011011`).
  - Event flag protocol (`999901` for Retro Demake, `999902` for Modern HD).
  - Sub-millisecond atomic VFS pivot via `LanternEventListener` during the fade window.
  - State persistence in `out/retro_toggle_state.json` and sync with `bbport.ini` and `mods.json`.
  - Re-generated `dist/bloodborne_retro_hud.patch`.

### Task Checklist & Status
- [x] **Subtask 12.1**: Restored pristine MOAL `.talkesdbnd.dcx` backups and validated contracts in `tools/fixtures/lantern/validate_contracts.py`.
- [x] **Subtask 12.2**: Formulated domain models and event flag constants in `tools/pipeline/lantern_mod_types.py`.
- [x] **Subtask 12.3**: Injected localized FMG dialogue prompts (`70011010` / `70011011`) into `menu.msgbnd.dcx` across local and `bbport-src` targets.
- [x] **Subtask 12.4**: Fixed `inject_lantern_talk_esd.py` to preserve unlit State 7/6 ignition, hook only lit State 6/5, and inject canonical choice/exit graph across all 16 maps and MOAL.
- [x] **Subtask 12.5**: Rewrote `lantern_event_listener.py` supporting dual signaling (`out/flag_signal.txt` IPC + memory observer), safe directory pivots without `EISDIR`, and `bbport.ini` sync.
- [x] **Subtask 12.6**: Implemented persistence synchronizer updating `out/retro_toggle_state.json`, `mods.json`, and `bbport.ini` (`retro_mode=1` vs `0`).
- [x] **Subtask 12.7**: Rewrote verification suite `tools/verify_lantern_mod.py` with multi-tier checks (`fmg-injection`, `talk-esd`, `moal-compat`, `flag-signaling`, `persistence`).
- [x] **Subtask 12.8**: Verified complete automated suite `tools/verify_lantern_mod.py --all` (100% pass rate).
- [x] **Subtask 12.9**: Updated documentation across `BB_PSX_DEMAKE_GUIDE.md` Section 17 and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md` Section 32.
- [x] **Subtask 12.10**: Re-generated `dist/bloodborne_retro_hud.patch` and executed adversarial quality audit.



