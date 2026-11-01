# Bloodborne PSX Demake: Mathematical Foundations, Reverse-Engineering Insights & Architectural Specification (Part 1)

**Author**: Bloodborne PSX Demake Engineering Team  
**Platform Target**: Linux x86_64 (**shadPS4** / native **bbhost** Vulkan)  
**Base Game**: *Bloodborne: The Old Hunters Complete Edition* (CUSA03173 / 1.09)  
**Date**: October 2026  

---

## 1. Executive Summary & Theoretical Framework

The *Bloodborne PSX Demake* project is a systematic reverse-engineering effort designed to transform modern 8th-generation PlayStation 4 game assets into authentic 5th-generation (PlayStation 1 / Nintendo 64 / Vagrant Story) retro aesthetics while running at native speeds on Vulkan-based Linux runners (**shadPS4** and **bbhost**). 

The project operates under two foundational constraints:
1. **Mathematical Authenticity**: Visual degradation must strictly emulate hardware characteristics of late-90s rasterizers—specifically 15-bit RGB555 color depth, chunky pixelated texels (32x32 to 256x256 equivalent), scale-invariant angle-weighted Gouraud or flat facet normals, and low polygon density.
2. **Engine Stability & Zero Base Game Pollution**: Changes must not trigger rendering pipeline panics, GPU occlusion culling dropouts (`SET_PREDICATION`), Havok cloth physics overflows, or memory alignment faults. The pristine game data (`CUSA03173`) remains 100% immutable via copy-on-write Btrfs reflinking (`CUSA03173-PSX`).

This document formalizes the mathematics, algorithms, binary data structures, and edge-case rules derived across 42 experimental test cycles.

---

## 2. Mesh Geometry, Topology & Polygon Decimation Mathematics

### 2.1. Garland-Heckbert Quadric Error Metrics (QEM)

Polygon reduction in `tools/mesh_decimator.py` uses iterative edge contraction guided by Garland & Heckbert Quadric Error Metrics (implemented via `pyfqmr`).

#### 2.1.1. Fundamental Error Quadric
Let a triangular face in the original mesh lie on a plane $\mathbf{p} = [a, b, c, d]^T$ in $\mathbb{R}^3$ with $ax + by + cz + d = 0$ and $a^2 + b^2 + c^2 = 1$. The squared Euclidean distance from a homogeneous vertex $\mathbf{v} = [x, y, z, 1]^T$ to plane $\mathbf{p}$ is given by the quadratic form:
$$D^2(\mathbf{v}) = (\mathbf{p}^T \mathbf{v})^2 = \mathbf{v}^T (\mathbf{p} \mathbf{p}^T) \mathbf{v} = \mathbf{v}^T \mathbf{K}_p \mathbf{v}$$
where $\mathbf{K}_p = \mathbf{p}\mathbf{p}^T$ is the symmetric $4 \times 4$ fundamental error quadric.

#### 2.1.2. Vertex Error Quadric Accumulation & Optimal Contraction
For any vertex $\mathbf{v}$, its error quadric $\mathbf{Q}_v$ is the sum of fundamental quadrics across all incident faces $\mathcal{F}(v)$:
$$\mathbf{Q}_v = \sum_{p \in \text{planes}(\mathcal{F}(v))} \mathbf{K}_p$$
When contracting an edge $e = (v_1, v_2) \to \bar{\mathbf{v}}$, the combined quadric is $\mathbf{Q}_{\bar{v}} = \mathbf{Q}_{v_1} + \mathbf{Q}_{v_2}$, and the optimal position $\bar{\mathbf{v}}$ minimizes $\Delta(\bar{\mathbf{v}}) = \bar{\mathbf{v}}^T \mathbf{Q}_{\bar{v}} \bar{\mathbf{v}}$ by solving $\nabla \Delta(\bar{\mathbf{v}}) = \mathbf{0}$.

#### 2.1.3. Pre-Welding Hinge & Rigid Bone Group Invariant (`normal_w`)
Before constructing the QEM surface, coincident vertices within $0.1\text{ mm}$ are welded. However, in FromSoftware's FLVER2 format, rigid animated objects (`obj/` doors, levers, sarcophagi, and hinged trick weapons `wp_`) store their rigid bone index in the `normal_w` vertex attribute rather than `bone_indices`. To prevent independent moving parts (such as left and right workshop door leaves) from welding together across their hinge seam, the discrete pre-weld key $\mathbf{k}_i \in \mathbb{Z}^4$ incorporates `normal_w`:
$$\mathbf{k}_i = \left[ \lfloor 10^4 x_i \rceil, \ \lfloor 10^4 y_i \rceil, \ \lfloor 10^4 z_i \rceil, \ \text{normal\_w}_i \right]$$
Vertices are welded if and only if $\mathbf{k}_i = \mathbf{k}_j$.

#### 2.1.4. Normal-Guarded Sliver Contraction
Post-QEM meshes may contain degenerate triangles ($\text{Area} < 10^{-6}$) or high-aspect needle slivers ($\text{Aspect} = \frac{a b c s}{8 \cdot \text{Area}^2} > 25.0$). Slivers are eliminated by iteratively contracting their shortest non-boundary edge $(v_{\text{drop}} \to v_{\text{keep}})$, subject to the topological normal-preservation guard across all incident faces $t \in \mathcal{F}(v_{\text{drop}})$:
$$\frac{\mathbf{N}_t^{\text{old}}}{\Vert{}\mathbf{N}_t^{\text{old}}\Vert{}} \cdot \frac{\mathbf{N}_t^{\text{new}}}{\Vert{}\mathbf{N}_t^{\text{new}}\Vert{}} \ge 0.0$$
This prevents edge collapses from flipping adjacent triangle orientations or stalling on neckline boundaries.

---

### 2.2. Skeleton-Driven Semantic Partitioning & Bone-Group Weapon Isolation

Composite character submeshes and articulated trick weapons frequently combine disparate regions or moving bones into a single draw call (e.g., Plain Doll `c8030` Mesh 7 combining hands with head skin, or Saw Cleaver `wp_a_1000` combining handle and blade).

1. **Bone Hierarchy Classification**: Every bone $b \in [0, N_{\text{bones}}-1]$ in `flv.bones` is classified into semantic sets $\mathcal{B}_{\text{hand}}$ (`finger`, `thumb`, `hand`, `palm`, `wrist`, `claw`) and $\mathcal{B}_{\text{head}}$ (`head`, `neck`, `jaw`, `face`, `eye`, `lip`, `brow`, `ear`), propagating labels downward from parent to child bones.
2. **Sparse Graph Connected Components**: A compressed sparse row (CSR) adjacency matrix $\mathbf{A}$ is built over welded triangle indices, partitioning the submesh into connected components $\{C_1, C_2, \dots, C_K\}$.
3. **Component Role Assignment & Per-Bone Weapon Isolation**: Each component $C_k$ is assigned a reduction profile based on the dominant bone index $b^*(v) = b_{\arg\max_j w_j(v)}$ of its vertices:
   - **`HANDS` / `PRESERVE`**: Articulated extremities decimated with border preservation (`ratio = 0.45`).
   - **`HEAD_SKIN`**: Skin/face material decimated to a fixed likeness budget ($600\text{--}800$ triangles) with ear-safe headgear clearance.
   - **`RIGID` / `WEAPON` (`wp_`)**: Standard armor, body, or articulated props. Multi-bone weapons are partitioned strictly by dominant bone ID (`allowed_bones={int(b_id)}`) so QEM edge contractions and KDTree attribute transfers never bridge across separate moving bones (e.g., handle `Bone 1` to blade `Bone 2`, or Threaded Cane whip links $k$ to $k+1$). Multi-bone bridge connectors (hinge pins, wire links) are preserved 100% intact.

---

### 2.3. Thurmer–Wüthrich Angle-Weighted Normals & Handedness-Aware Tangents

#### 2.3.1. Scale-Invariant Angle-Weighted Normals
Area-weighted vertex normals allow large planar cheek or forehead triangles to overpower small, high-curvature triangles around the eyelids, nostrils, and lips. Shared vertices therefore compute **Thurmer–Wüthrich incident-angle-weighted normals**:
$$\alpha_{f,v} = \arccos\left( \text{clip}\left(\frac{(\mathbf{v}_{a} - \mathbf{v}) \cdot (\mathbf{v}_{b} - \mathbf{v})}{\Vert{}\mathbf{v}_{a} - \mathbf{v}\Vert{} \Vert{}\mathbf{v}_{b} - \mathbf{v}\Vert{}}, -1, 1\right) \right)$$
$$\mathbf{N}_v = \frac{\sum_{f \in \mathcal{F}(v)} \alpha_{f,v} \mathbf{N}_f}{\left\Vert{} \sum_{f \in \mathcal{F}(v)} \alpha_{f,v} \mathbf{N}_f \right\Vert{}}$$

#### 2.3.2. Gram-Schmidt Tangent Frame & Bitangent Handedness ($T_w \in \{-1, +1\}$)
For each triangle $f$ with edge vectors $\Delta \mathbf{p}_1, \Delta \mathbf{p}_2$ and UV differences $\Delta \mathbf{uv}_1, \Delta \mathbf{uv}_2$, the raw tangent $\mathbf{s}_f$ and bitangent $\mathbf{t}_f$ are:
$$\mathbf{s}_f = \frac{\Delta v_2 \Delta \mathbf{p}_1 - \Delta v_1 \Delta \mathbf{p}_2}{\Delta u_1 \Delta v_2 - \Delta v_1 \Delta u_2}, \quad \mathbf{t}_f = \frac{\Delta u_1 \Delta \mathbf{p}_2 - \Delta u_2 \Delta \mathbf{p}_1}{\Delta u_1 \Delta v_2 - \Delta v_1 \Delta u_2}$$
Accumulating angle-weighted $\mathbf{S}_v$ and $\mathbf{T}_v$ at each vertex, the orthonormal tangent $\mathbf{T}_v'$ and handedness sign $T_w$ are computed for both `uv_0` (`tangent_0`) and `uv_1` (`tangent_1`):
$$\mathbf{T}_v' = \frac{\mathbf{S}_v - (\mathbf{N}_v \cdot \mathbf{S}_v)\mathbf{N}_v}{\Vert{}\mathbf{S}_v - (\mathbf{N}_v \cdot \mathbf{S}_v)\mathbf{N}_v\Vert{}}, \quad T_w = \begin{cases} -1.0 & \text{if } (\mathbf{N}_v \times \mathbf{T}_v') \cdot \mathbf{T}_v < 0 \\ +1.0 & \text{otherwise} \end{cases}$$
This prevents inverted green ($Y$) BC5 normal map channels across mirrored sagittal UV shells.

---

### 2.4. Vectorized Barycentric UV Projection & Strict Byte-Sum-255 Skinning

1. **Normal-Aligned Barycentric UV Projection**: For each simplified face $f$ with centroid $\mathbf{c}_f$ and unit normal $\mathbf{n}_f$, the $K=8$ nearest original triangles are queried via $k$-d tree and scored by distance and normal alignment ($\mathbf{n}_f \cdot \mathbf{n}_{\text{orig}}$). Each corner $\mathbf{p}_{f,c}$ is projected onto the chosen original triangle $(v_a, v_b, v_c)$ to obtain clamped barycentric coordinates $(\lambda_a, \lambda_b, \lambda_c) \in [0,1]^3$, $\sum \lambda_i = 1$:
   $$\mathbf{uv}(f, c) = \lambda_a \mathbf{uv}_a + \lambda_b \mathbf{uv}_b + \lambda_c \mathbf{uv}_c$$
2. **Shared-Vertex UV Cluster Welding**: Corners sharing a simplified vertex position $\bar{\mathbf{v}}$ are welded into a single shared vertex if their projected UVs lie within $\epsilon_{uv} = 0.15$, maintaining manifold topology (`num_verts < num_tris`) while preserving hard UV chart seams.
3. **Strict Partition-of-Unity & Byte-Sum-255 Bone Weights**: FLVER2 packs bone weights as 4 unsigned bytes (`uint8`) that must sum to exactly $255$:
   $$\mathbf{w}_{\text{byte}} = \lfloor 255 \cdot \frac{\mathbf{w}}{\sum_{j=1}^4 w_j} \rceil, \quad w_{\text{byte}, j^*} \leftarrow w_{\text{byte}, j^*} + \left(255 - \sum_{j=1}^4 w_{\text{byte}, j}\right)$$
   where $j^* = \arg\max_j w_{\text{byte}, j}$.

---

### 2.5. Automated Shell Clearance with Lateral Ear Masking

When an inner cranial mesh $M_{\text{inner}}$ (e.g., Head Mesh 7) is covered by an outer headgear mesh $M_{\text{outer}}$ (e.g., Bonnet Mesh 4), decimation chords can cause scalp triangles to pierce the headgear.
To recess occluded crown and temple vertices toward the local anatomical center $\mathbf{c}_h$ without imploding lateral ear geometry:
1. **Lateral Ear Exclusion Mask**: Define the bounding span $\mathbf{s} = \mathbf{B}_{\max}(M_{\text{inner}}) - \mathbf{B}_{\min}(M_{\text{inner}})$. Vertices in the lateral ear zone are locked against inward radial displacement:
   $$\text{Mask}_{\text{ear}}(\mathbf{v}) = \left( \vert{}x_v\vert{} \le 0.35 \cdot s_x \right)$$
2. **Protected Neckline Seam**: Open boundary vertices ($\text{edge\_count} = 1$) are locked ($\text{Mask}_{\text{bound}}(\mathbf{v}) = \text{False}$).
3. **Radial & KDTree Clearance Projection**: Movable non-ear vertices in the crown and temple zones with outer-shell distance $d(\mathbf{v}, M_{\text{outer}}) < d_{\min} = 5.5\text{ mm}$ are displaced inward along $\frac{\mathbf{c}_h - \mathbf{v}}{\Vert{}\mathbf{c}_h - \mathbf{v}\Vert{}_2}$, guaranteeing positive clearance ($\ge 5.5\text{ mm}$) and $0$ piercing triangle pairs while keeping the ears intact.

---

## 3. Bounding Boxes, Frustum Culling & Occlusion Query Algebra

- **Hardware Occlusion Queries (`SET_PREDICATION`)**: Before drawing a submesh, the GPU depth-tests its AABB volume against the early $Z$-buffer. Artificial AABB padding penetrates floors and walls, causing the floor to occlude the box ($\text{SamplesPassed} = 0$) and dropping the character draw call.
- **Invariants**:
  1. Rigid submeshes use exact tight vertex extrema $[\min_i \mathbf{v}_i, \max_i \mathbf{v}_i]$.
  2. Havok cloth submeshes preserve 100% vanilla AABBs.
  3. All 206 bone AABBs are preserved via `tools/soulstruct_patch.py`.
  4. All auxiliary FaceSets (`FS1..FS5`) are synchronized to `FS0.copy()` on character/equipment FLVERs, while map FLVERs promote `LodLevel1`/`LodLevel2` **only** into `FS0` (leaving `FS1..N` intact for DOL lightmap/shadow passes).

---

## 4. PS4 GCN Morton Swizzling, 15-Bit RGB555 & Block Compression Codecs

### 4.1. Vectorized GCN Morton Swizzling (`8x8` Block Micro-Tiles)
PS4 textures tile $4 \times 4$ compressed blocks into $8 \times 8$ block ($32 \times 32$ pixel) micro-tiles indexed by a 6-bit Morton Z-order curve $d(lx, ly) = (y_2 x_2 y_1 x_1 y_0 x_0)_2 \in [0, 63]$. Vectorized NumPy permutation over precomputed `_MX` and `_MY` lookup tables swizzles and deswizzles full mip chains in milliseconds.

### 4.2. Block Compression Formats (`BC1`, `BC4`, `BC5`, `BC6H`, `BC7`)
| TPF Format | Codec | Bytes / $4\times 4$ Block | Usage in Bloodborne | Demake Pipeline Rule |
| :--- | :--- | :--- | :--- | :--- |
| `0x00`, `0x01`, `0x05` | **BC1 (DXT1)** | 8 bytes | Diffuse Albedo (`_a`), Specular Reflectance (`_r`), 1-bit Cutouts | Downsample `_a` to `32px`–`256px` with 15-bit RGB555 quantization & EDT alpha bleed. Keep `_r` vanilla on parts/chr. |
| `0x67` | **BC4 (RGTC1)** | 8 bytes | Single-channel Specular Gloss / Shininess (`_s`) | Preserve vanilla on parts/chr; optional `decode_bc4`/`encode_bc4` downsample on heavy urban vistas (`m22`). |
| `0x6C`, `0x6D` | **BC5 (RGTC2)** | **16 bytes** ($2 \times 8\text{B}$ BC4) | Two-channel Tangent Normal Maps (`_n`) | **Never** overwrite with 8-byte BC1 blocks. Neutral flat normal is `0x80800000000000008080000000000000` (16B). Downsample via dual-channel BC4 split without `>>3` bit-shift. |
| `0x6A` | **BC6H** | 16 bytes | HDR Floating-Point Face Normal Maps (`FC_*_n`) | Keep 100% byte-identical to vanilla (prevents NaN black face blotches). |
| `0x66` | **BC7** | 16 bytes | High-precision Hair/Fur Alpha (`_HR_a`) & Scaleform UI Atlases | Keep 100% byte-identical on hair/fur/foliage; use `ispc-texcomp` with `num_mips = unk3` (`1`) on `MENU_Icon_*` UI atlases. |

---

## 5. Environment & Chalice Dungeon (`m21`, `m22`, `m29`) Architecture

1. **Zero-Bloat In-Place BXF Slot Overwrite**:
   When a demade environment texture TPF recompresses to `len(recomp) <= comp_sz`, it is written directly into its existing `data_off` slot inside `.tpfbdt` (zero-padding trailing bytes up to `comp_sz`) and only the 8-byte size fields in `.tpfbhd` (`rec_off + 8` and `rec_off + 16`) are updated. This achieves a **96.5% compressed payload reduction** (e.g. `24.43 MB -> 0.86 MB` in `m21_0000`) with **0 EOF appends** and zero file bloat.
2. **Sky Dome & Celestial FLVER Isolation**:
   Map FLVERs with piece IDs $\ge 9000$ or materials referencing `sky`, `cloud`, `clond`, `moon`, `sun`, `star`, or `cosmo` are copied 100% vanilla so sky domes never decimate into angular cages.
3. **Chalice Dungeon Modular Multi-Block Support (`m29_*`)**:
   Chalice Dungeons store modular room/corridor geometry across multiple `map/m29_XX_YY_ZZ/` directories sharing `map/m29/m29_*.tpfbhd` texture binders and `obj/o29*.objbnd.dcx` dungeon props (gates, levers, sarcophagi, traps). Promoting `m29_*` FLVERs to native LODs while preserving `normal_w` on `o29*` mechanisms optimizes all story and procedural Root Chalice Dungeons simultaneously.

---

## 6. Ultra-Low-Poly Decimation: Topology Floors, Safety Gates & Face Landmark Problem (Tests 43–44)

### 6.1. Discovered Hard Topology Floors

Tests 43–44 (`tools/demake_c8030_ultralow.py`) established three inviolable floors when pushing QEM beyond the conservative 45% ratio used in Tests 33–42:

#### 6.1.1. Shared-Vertex Invariant Floor (Test 43)

A submesh is **topologically sound** for the Bloodborne FLVER2 renderer when its vertex array count is strictly less than its triangle count — i.e. vertices are shared across triangle fans (manifold mesh). When QEM reduces a mesh below a critical triangle density, two failure modes invert this invariant:

1. **UV Seam Expansion**: At low triangle counts, each hard UV chart boundary forces a unique vertex per triangle corner. If the mesh has $S$ seam edges, the post-decimation vertex count approaches $V \approx T + S_{\text{boundary}}$. When $S_{\text{boundary}} > 0$, small meshes inevitably flip `shared=False`.
2. **Sliver Proliferation**: The `contract_slivers_normal_guarded` pass (aspect $> 25.0$) introduces additional boundary vertices when it protects open-boundary neckline seam verts from collapse, further raising $V$.

**Safety Gate (implemented in `demake_c8030_ultralow.py`):**
For each submesh $i$ that was `shared=True` in vanilla:
$$\text{ABORT if } V_i^{\text{new}} > T_i^{\text{new}}$$
where $V_i^{\text{new}}$ and $T_i^{\text{new}}$ are post-decimation vertex and triangle counts read from `m.vertex_arrays[0].array` and `m.face_sets[0].vertex_indices`.

**Known exemption — Collar `Material #3` (`Mesh 3`):** This lace collar mesh has 27 post-QEM slivers from its dense UV chart topology. The sliver contraction pass generates boundary-locked vertices that exceed the triangle count at any target below ~900 tris. Solution: preserve at vanilla count (`target = 921`).

#### 6.1.2. Bonnet AABB Minimum for `SET_PREDICATION` Safety (Test 43)

The GPU occlusion query pipeline (`SET_PREDICATION`) depth-tests each submesh's AABB against the early Z-buffer before issuing the draw call. When Bonnet (Mesh 4, HD_F_7000_01) was reduced to 190 tris, its simplified cage AABB became too small relative to the character's world-space bounding volume. The GPU occlusion test returned `SamplesPassed = 0` at certain camera angles, dropping the draw call for arms, chest clothes, and legs in-game — the exact failure pattern from Test 18 & 20.

**Empirical minimum**: Bonnet must remain **≥ 400 tris** to maintain a cage AABB that passes the occlusion query at all tested camera angles. Current stable value: **500 tris**.

#### 6.1.3. Per-Mesh QEM Convergence Floors

pyfqmr's QEM implementation converges to local minima that do not always match the requested `target_count`. Observed convergence floors on `c8030`:

| Mesh | Material | Vanilla Tris | pyfqmr Floor | Stable Target |
| :--- | :--- | ---: | ---: | ---: |
| 3 | Collar lace | 921 | ~291 (unrolled) | 921 (preserve) |
| 4 | Bonnet | 11,008 | ~484 | 500 |
| 5 | Dress | 14,444 | ~581 (unrolled at 600) | 800 |
| 6 | Cuffs | 350 | ~158 | 80 |
| 9 | Legs/Boots | 15,002 | ~419 | 500 |

---

### 6.2. Face Landmark Preservation Problem at Sub-700-Tri Budgets

#### 6.2.1. The Core Failure

The current `HEAD_SKIN` component pipeline routes all cranial skin triangles through a single global QEM pass targeting a fixed triangle count (`head_target_tris`). At budgets ≤ 400 triangles, Garland–Heckbert QEM collapses by minimizing total geometric error — but geometric error is **area-weighted**. The large, low-curvature cheek and forehead surfaces accumulate low quadric cost and are preserved, while the small, high-curvature regions (mouth cavity, nostrils, eyelid crease, philtrum) have high local quadric cost and are collapsed first.

The result: the Doll's face at 400 tris retains cheeks and forehead geometry but loses all facial identity landmarks:
- **Mouth**: lip fold and corner vertices collapsed into a flat plane
- **Nostrils**: nasal ala and septum triangles merged into a single nose ridge
- **Eyelid crease**: upper/lower lid fold eliminated, eyes become convex spherical patches

This is the opposite of what PSX-era art direction required. Real retro character heads were sculpted with **intentionally exaggerated landmark vertices** — larger nose, wider mouth aperture, deeper eye sockets — to survive the polygon budget while remaining recognizable.

#### 6.2.2. Required: Semantic Facial Landmark Recognition

To solve this, the decimation pipeline needs a **facial landmark mask** that assigns per-vertex protection weights before QEM. The approach:

1. **Landmark Detection via Bone Proximity + UV Clustering**
   - Map known semantic UV regions from `c8030_skin_a` (mouth cavity UV band $v \in [0.62, 0.78]$, nostril UV cluster, eye socket UV islands) to 3D vertex positions via existing barycentric UV projection infrastructure.
   - Alternatively, use the `flv.bones` hierarchy: eye bones (`eye_L`, `eye_R`), jaw bone, and nose tip bone (if present) provide 3D anchors within 5–15 mm of the target surface features.

2. **Quadric Cost Inflation for Protected Regions**
   - Before running pyfqmr, pre-inflate the effective error quadric $\mathbf{Q}_v$ for landmark vertices by a multiplier $\lambda_{\text{landmark}} \gg 1$ (e.g. $\lambda = 100$). Since pyfqmr does not expose per-vertex quadric injection, the equivalent approach is **vertex pinning via coordinate perturbation**: landmark vertices are temporarily displaced to positions far from any edge contraction candidate, forcing pyfqmr to preserve them, then snapped back.
   - **Simpler alternative**: post-QEM vertex snapping — after global QEM, for each landmark anchor $\mathbf{a}_k$, find the nearest simplified vertex $\bar{v}_k$ and displace it to $\mathbf{a}_k$ if $\|\bar{v}_k - \mathbf{a}_k\| < r_{\text{snap}}$ (e.g. $r_{\text{snap}} = 8\text{ mm}$).

3. **Adaptive Triangle Budget Allocation**
   Subdivide `head_target_tris` across semantic regions:
   $$T_{\text{head}} = T_{\text{landmark}} + T_{\text{cheek/forehead}}$$
   where $T_{\text{landmark}} \approx 60\%$ of budget is reserved for the mouth/nose/eye region (approximately the $v \in [0.45, 0.85]$ UV band in `c8030_skin_a`) and $T_{\text{cheek/forehead}} \approx 40\%$ covers the remaining surface. This prevents the current behavior where QEM allocates 70%+ of triangles to featureless cheek geometry.

4. **PSX Art Direction Correction**
   After landmark-aware decimation, apply a **landmark exaggeration pass**: scale landmark vertex displacements from the face centroid by factor $\mu_{\text{exaggerate}} \in [1.05, 1.20]$ along the local surface normal $\mathbf{N}_v$. This deepens eye sockets, widens nostrils, and sharpens the lip fold — matching the intentional over-carving of PSX character models (e.g. Silent Hill's Alessa, Vagrant Story's Ashley).

#### 6.2.3. Implementation Roadmap

| Step | Task | Dependency |
| :--- | :--- | :--- |
| **A** | UV-to-3D landmark mapping: parse `c8030_skin_a` UV atlas to identify mouth/nose/eye island bounding boxes | `ps4_swizzle.py` + PIL |
| **B** | Bone-proximity landmark anchor extraction: extract 3D positions of `jaw`, `eye_L`, `eye_R` bones from `flv.bones` | `soulstruct` FLVER bone API |
| **C** | Vertex pinning via coordinate perturbation pre-QEM + snap-back post-QEM | `mesh_decimator.py` → `decimate_component_shared_verts` |
| **D** | Adaptive budget split: separate `HEAD_SKIN` component into `FACE_LANDMARK` + `FACE_SURFACE` partitions | `mesh_decimator.py` → `partition_submesh_components` |
| **E** | PSX exaggeration pass: outward normal displacement on landmark verts post-decimation | New function in `mesh_decimator.py` |
| **F** | Integration into `demake_c8030_doll.py` and `demake_c8030_ultralow.py` with `--landmark-aware` flag | Both tools |

---

## 7. Native Engine PSX Demake Math (bbport)

### 7.1. Screen-Space Homogeneous Vertex Grid Snapping

On PlayStation 1 hardware (GTE), vertices are projected into fixed-point screen-space integer pixel coordinates without sub-pixel precision, causing polygon vertices to jitter as the camera translates.

In modern homogeneous clip space $\mathbf{P}_{\text{clip}} = (X, Y, Z, W)$:
1. Safe camera space guard: verify $W > 10^{-4}$ and exclude UI draws ($\text{motion\_param} \neq 0$).
2. Normalized Device Coordinates (NDC) projection:
   $$X_{\text{ndc}} = \frac{X}{W}, \quad Y_{\text{ndc}} = \frac{Y}{W} \quad (X_{\text{ndc}}, Y_{\text{ndc}} \in [-1, 1])$$
3. Snap to fixed-point virtual resolution $(W_{\text{snap}}, H_{\text{snap}})$:
   $$R_x = \frac{W_{\text{snap}}}{2}, \quad R_y = \frac{H_{\text{snap}}}{2}$$
   $$X_{\text{grid}} = \frac{\text{roundEven}(X_{\text{ndc}} \cdot R_x)}{R_x}$$
   $$Y_{\text{grid}} = \frac{\text{roundEven}(Y_{\text{ndc}} \cdot R_y)}{R_y}$$
4. Reconstruct homogeneous clip coordinates:
   $$X_{\text{snapped}} = X_{\text{grid}} \cdot W, \quad Y_{\text{snapped}} = Y_{\text{grid}} \cdot W$$
Depth ($Z$) and perspective scaling ($W$) remain exact, maintaining correct depth buffer comparisons while rasterizing edges on the discretized pixel grid.

### 7.2. 15-Bit RGB555 Color Quantization & 4x4 Bayer Dithering

retro framebuffer output operates in 15-bit color (5 bits per RGB channel, 32 discrete intensity levels $k \in [0, 31]$) with hardware Bayer matrix dithering:

1. Normalized $4 \times 4$ Bayer matrix $\mathbf{M} \in [0, 15]$:
   $$\mathbf{M} = \begin{bmatrix} 0 & 8 & 2 & 10 \\ 12 & 4 & 14 & 6 \\ 3 & 11 & 1 & 9 \\ 15 & 7 & 13 & 5 \end{bmatrix}$$
2. Centered dither offset $d(x, y)$ scaled to one quantization step ($1/31$):
   $$d(x, y) = \frac{\frac{\mathbf{M}(x \bmod 4, y \bmod 4)}{16} - 0.5}{31}$$
3. Quantized output color:
   $$\mathbf{C}_{\text{out}} = \frac{\lfloor \text{clamp}(\mathbf{C}_{\text{in}} + d(x, y), 0, 1) \cdot 31 + 0.5 \rfloor}{31}$$

### 7.3. Affine Texture Mapping (Non-Perspective Interpolation)

retro hardware lacked perspective-correct hyperbolic texture coordinate division ($\frac{u}{w}, \frac{v}{w}, \frac{1}{w}$). In SPIR-V, forcing `spv::Decoration::NoPerspective` on fragment shader attribute inputs instructs the Vulkan rasterizer to perform screen-space linear interpolation:
$$\mathbf{UV}(s, t) = (1 - s - t)\mathbf{UV}_0 + s\mathbf{UV}_1 + t\mathbf{UV}_2$$
producing the characteristic warping and swimming of textures on elongated polygons.

---

## 8. Build Architecture & World Geometry Decimation Findings

### 8.1. `bbport` Build Pipeline Architecture

The execution and compilation hierarchy operates as follows:
```
[Desktop Application / Launcher (GTK4/Adw)]
                 │
                 ▼
          [run.sh wrapper]
                 │
                 ├─► [bash build.sh]
                 │          │
                 │          ├─► [ninja -C out/gpu bbgpu bbnet bbnet20]
                 │          │         └─► Compiles libbbgpu.so (Vulkan engine + SPIR-V translator)
                 │          └─► [gcc/clang]
                 │                    └─► Links out/bb-probe against libbbgpu.so via RPATH ($ORIGIN/gpu, $PWD/out/gpu)
                 │
                 ▼
       [exec out/bb-probe]
```
- **Fast Developer Inner Loop**: `ninja -C ../bbport-src/out/gpu` directly updates `libbbgpu.so` in seconds without recompiling `bb-probe`.
- **Full Verification**: `bash build.sh --test` runs all core integration tests (`pad-test`, `runtime-test`, `file-mods-test`, `sema-test`, `online-test`, `content-test`).
- **Shader Cache Invalidation**: `ShaderBinaryVersion = 21u` in `gpu/render/pipeline_store.h` invalidates stale on-disk SPIR-V binaries on engine startup.

### 8.2. World Ultra-Low Decimation Topology (`batch_demake_world_ultralow.py`)

The aggressive world decimation preset preserves critical level topology through a two-tier budget allocation:
1. **Landmark Ratio** ($r_{\text{landmark}} = 0.60$): Applied to primary player-traversed structures (submesh IDs $\ge 1000$ and landmark indices $000010 \dots 000040$), retaining 60% of native triangle density on stairs, walkable floors, and balustrades.
2. **Background Ratio** ($r_{\text{bg}} = 0.40$): Decimates distant architecture down to 40% density.
3. **Safety Minimum Fraction** ($f_{\text{min}} = 0.10$): Submeshes are clamped to never fall below 10% of their native triangle count, preventing Quadric Error Metric (QEM) edge-collapse from zeroing thin step risers ($\Delta y \approx 15\text{ cm}$) or inverting floor normals.
4. **Foliage & Sky Protection**: Sky sphere objects (`o210020`, `o210021`) and celestial meshes are excluded from QEM decimation; foliage cards are preserved at 100% geometry or demaked via 1-bit alpha thresholding.

Across `m21` (Hunter's Dream), the aggressive pass successfully decimated 218 FLVERs:
- Total triangles: 7,769,107 (vanilla) $\rightarrow$ 4,108,419 (native LOD) $\rightarrow$ **2,781,132 final (35.8% budget)**.
- Outcomes: 449 QEM passes, 89 LOD-only promotions, 81 gated fallbacks (preserving promoted LOD when QEM failed safety thresholds). Stable and live in `CUSA03173-PSX`.

---

## 9. True VRAM Reduction Mathematics & Mip-Slicing Invariants

### 9.1. Mathematical Contrast: Canvas Pseudo-Upscaling vs. Top-Mip Bitstream Slicing

Previous texture demake implementations (`demake_color_engine.py:186-194`) exhibited a critical performance limitation: textures were downsampled to low resolution in pixel space and then nearest-neighbor upscaled back to canvas dimensions ($W_0 \times H_0$) to maintain byte-length invariants. 

Because the Vulkan engine allocates `VkImage` extents strictly based on container header dimensions $(W_0, H_0)$ and mip count $k$, hardware memory allocation was identical to pristine vanilla:
$$VRAM_{\text{pseudo}} = \sum_{i=0}^{k-1} \max\left(1, \left\lceil \frac{W_0 \cdot 2^{-i}}{4} \right\rceil\right) \cdot \max\left(1, \left\lceil \frac{H_0 \cdot 2^{-i}}{4} \right\rceil\right) \cdot bpb \equiv VRAM_{\text{vanilla}}$$
where $bpb \in \{8, 16\}$ is the bytes-per-block constant for the texture format (BC1 = 8 bytes, BC5/BC7 = 16 bytes). Total GPU VRAM saved was exactly **0 bytes**.

To achieve true hardware memory reduction without decoding artifacts or re-compression degradation, we developed direct top-mip bitstream slicing (`tools/batch_shrink_world_textures.py` and `tools/shrink_chr_textures.py`). 

By dropping the top $d = \text{drop}$ mip levels directly from the linear byte stream:
$$\text{cut} = \sum_{i=0}^{d-1} \max\left(1, \left\lceil \frac{w_i}{4} \right\rceil\right) \cdot \max\left(1, \left\lceil \frac{h_i}{4} \right\rceil\right) \cdot bpb$$
$$\text{Payload}_{\text{new}} = \text{Payload}_{\text{orig}}[\text{cut}:]$$

The container entry header is rewritten with the dimensions and mip count of the remaining chain:
$$w_{\text{new}} = w_d, \quad h_{\text{new}} = h_d, \quad k_{\text{new}} = k - d$$

Vulkan allocates `VkImage` extents for $(w_d, h_d, k - d)$:
$$VRAM_{\text{sliced}} = \sum_{i=d}^{k-1} \max\left(1, \left\lceil \frac{w_i}{4} \right\rceil\right) \cdot \max\left(1, \left\lceil \frac{h_i}{4} \right\rceil\right) \cdot bpb$$

#### Quantitative Comparison ($2048 \times 2048$ BC7 Texture Sliced to $256 \times 256$, $d = 3$):
- $VRAM_{\text{orig}} = \sum_{i=0}^{11} \dots = 5,592,448\text{ B} \approx 5.33\text{ MB}$
- $VRAM_{\text{sliced}} = \sum_{i=3}^{11} \dots = 87,408\text{ B} \approx 85.3\text{ KB}$
- $\text{VRAM Reduction} = \frac{5,592,448 - 87,408}{5,592,448} = \mathbf{98.44\%}$

### 9.2. TPF Entry Binary Invariants & Verification Proofs

Each TPF container satisfies strict memory packing invariants:
1. **Contiguous Texture Streams**: Entry data blocks are packed back-to-back with zero trailing padding:
   $$\text{offset}_{i} = \text{offset}_{i-1} + \text{size}_{i-1}, \quad \text{offset}_0 = \min_{j} (\text{offset}_j)$$
2. **Global Header Parity**: Total container size word matches the exact sum of all entry sizes:
   $$\text{Header}[1] = \sum_{i=0}^{N-1} \text{size}_i$$
3. **Dimensions & Mip-Count Byte**: Entry word `unk2` stores 16-bit packed dimensions ($w \mid (h \ll 16)$), and byte 2 of `unk1` stores the active mip count:
   $$\text{Header}_{\text{entry}}[2] = (\text{unk1} \ \& \ \sim 0x00FF0000) \mid ((k - d) \ll 16)$$
4. **Header Invariance**: Names region (`0x10 + count * 36` to $\text{offset}_0$), DXGI formats, and entry flags (`unk3`, `unk4`) remain byte-identical to original FromSoftware metadata.

### 9.3. Empirical Multi-Category Deployment Metrics

| Asset Category | Target Resolution | Files Processed | Archives Changed | Uncompressed Texture Data Saved | Hardware VRAM Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`map/m21` (World)** | $\le 256\text{px}$ | 5 split BXF archives | 5 / 5 (100%) | 297 MB $\rightarrow$ 77.7 MB on disk (-74%) | ~85–90% reduction in level texture footprint |
| **`chr/` (Characters)** | $\le 256\text{px}$ | 108 archives | 96 / 108 (88.9%) | **301.8 MiB** uncompressed data saved | ~75% reduction on active enemy draw calls |
| **`parts/` (Weapons/Armor)**| $\le 256\text{px}$ | 1,191 archives | 802 / 1,191 (67.3%) | **1,076.9 MiB** uncompressed data saved | ~60.8% reduction across player gear |
| **`obj/` (Props/Doors)** | $\le 128\text{px}$ | 1,880 archives | 227 / 1,880 (12.1%) | **309.4 MiB** uncompressed data saved | ~60.6% reduction on interactive world props |
| **Total Pipeline** | — | **3,184 archives** | **1,130 archives** | **1,765.8 MiB (~1.72 GB)** saved | Complete elimination of entry-level VRAM paging |

---

## 10. Dual-Path Asset Configuration & Dynamic Runtime Mount Switching

### 10.1. The Dual-Path Problem Statement

Historically, testing between the pristine vanilla baseline (`CUSA03173`) and the demaked PSX build (`CUSA03173-PSX`) required manually editing paths in `~/.config/bbport-launcher/settings.json`, swapping symlinks, or maintaining two independent port configurations. 

Furthermore, users required the ability to toggle between the PSX retro aesthetic and normal modern rendering *in-game* without terminating the active game session.

### 10.2. Separation of Rendering Shaders vs. In-Flight GPU Memory

A fundamental constraint of FromSoftware's game engine architecture (`GXFlver`, `GXTexture`, `bnd4`) dictates that asset swapping and shader toggling operate at different temporal boundaries:

1. **Screen-Space & Rasterization Shaders** (Immediate / $\Delta t = 1\text{ frame}$):
   - 15-bit color truncation & $4\times 4$ Bayer matrix dithering (`present_encode.frag`).
   - Forced point (nearest-neighbor) texture sampling (`sampler.cpp`).
   - Fixed-point vertex grid snapping (`emit_spirv_special.cpp`).
   - Affine non-perspective UV interpolation (`spirv_emit_context.cpp`).
   - **Mechanism**: These flags live in atomics in `BbSettings::Values` and directly control SPIR-V translation and Vulkan descriptor sampler states. Toggling `psx_mode` flips all shaders on the very next render pass.

2. **3D Models & Sliced Texture Bitstreams** (Deferred / $\Delta t = \text{load event}$):
   - Active vertex and index buffers for the current area are already bound into GPU memory.
   - Active `VkImage` extents are fixed at their allocated dimensions ($256 \times 256$ vs $2048 \times 2048$).
   - **Mechanism**: Swapping assets mid-frame without reallocating descriptors would cause Vulkan device lost or Havok cloth desyncs. However, by dynamically remounting the guest path `/app0` and `/hostapp` in `src/runtime_file.c`, the game engine automatically loads from the newly selected path whenever an asset streaming event occurs:
     - Warping to another lamp or area.
     - Dying or using a Bold Hunter's Mark (level reload).
     - Equipping weapons, armor, or helmets (on-demand `.partsbnd.dcx` read).
     - Streaming newly spawned enemies or NPCs (`.chrbnd.dcx` read).

### 10.3. Dynamic Runtime Remount Implementation

In `src/runtime_file.c`, mounts are represented by a locked lookup table:
```c
struct Mount {
    char guest[64];
    char host[512];
};
```
When `runtime_file_set_app0(const char *host)` is invoked:
```c
void runtime_file_set_app0(const char *host) {
    if (!host || !*host) return;
    runtime_file_mount("/app0", host);
    runtime_file_mount("/hostapp", host);
    printf("Runtime: /app0 and /hostapp remounted to %s\n", host);
}
```
Existing mounts are updated in-place under `pthread_mutex_lock(&lock)`, redirecting all subsequent `translate()` calls from guest paths (`/app0/dvdroot_ps4/...`) to the newly targeted host directory without restarting the process.

### 10.4. Pipeline Cache Segregation & Vulkan Immutable State

A critical bug was identified where launching with `psx_mode = 0` still exhibited vertex snapping and affine UVs:
1. **The Root Cause**: The disk pipeline cache (`user/cache/CUSA03173`) was shared between both modes. When `psx_mode = 1` ran, it compiled SPIR-V bytecode containing NDC snapping instructions and `NoPerspective` declarations, saving them under `ShaderBinaryVersion = 21u`. When the user later booted with `psx_mode = 0`, the cache loader verified that `binary_version == 21u`, loaded the cached PSX shaders, and executed them verbatim.
2. **GPU Immutability**: In the Vulkan specification, `VkPipeline` (containing compiled shader stages) and `VkSampler` (nearest vs bilinear) are immutable GPU objects. Once created, their properties cannot be altered by toggling a host atomic variable mid-draw.
3. **The Solution**:
   - **Cache Folder Isolation**: In `gpu/render/blob_store.cpp`, the cache directory is segregated:
     $$\text{dir} = \text{CacheDir} \ / \ (\text{GameSerial} + (\text{is\_psx} \ ? \ \text{"\_psx"} : \text{""}))$$
     producing `user/cache/CUSA03173` for pure vanilla and `user/cache/CUSA03173_psx` for retro demake.
   - **Cache Invalidation**: Bumped `ShaderBinaryVersion = 22u` to purge obsolete binaries.
   - **In-Game Mode Transition**: In `gpu/shim/bbport_overlay.cpp`, toggling `psx_mode` flags `restart = true` and prompts `"Mode change will apply after restarting the game"`, exposing the built-in `[Apply and restart game]` button (`runtime_restart()`).

### 10.5. Restart Environment Inheritance & Asset Directory Binding

When `runtime_restart()` invokes `execlp("bash", "bash", "run.sh", NULL)`, the operating system preserves the calling process's environment block. If the game was booted initially in vanilla mode, `BB_GAME_DIR` remained set to `CUSA03173` across `exec`.

To guarantee that assets switch synchronously with shaders on restart:
1. **Config-Driven Resolution in `run.sh`**:
   `run.sh` inspects `$BB_CONFIG` (`bbport.ini`) before resolving `game`:
   ```bash
   if [[ $psx_mode_cfg == "1" ]]; then
       game=${BB_PSX_GAME_DIR:-"${game%-PSX}-PSX"}
   elif [[ $psx_mode_cfg == "0" ]]; then
       game=${BB_VANILLA_GAME_DIR:-"${game%-PSX}"}
   fi
   export BB_GAME_DIR=$game
   ```
2. **Pre-Restart Environment Overwrite**:
   Before executing `runtime_restart()`, `bbport_overlay.cpp` updates the active process environment:
   ```cpp
   setenv("BB_GAME_DIR", target.c_str(), 1);
   ```
Both shaders and 3D asset streams remain 100% in sync across in-game restarts.

---

## 11. Ultra-Low Geometry Decimation for Hunter Parts and Trick Weapons

### 11.1. Why Prior Equipment Decimation Looked High-Poly
The initial `batch_demake_hunter.py` pass ran with a conservative `target_ratio = 0.45`. For high-detail player gear such as the Hunter Garb (`bd_m_9000`), the rigid body mesh remained at 7,434 triangles (down from 14,084). In comparison, the Plain Doll (`c8030`) rigid meshes had been aggressively reduced to 3%–5% of vanilla (Bonnet: 500 tris, Dress: 800 tris, Boots: 500 tris), creating a sharp stylistic dissonance where the Doll looked authentically low-poly while player gear appeared modern.

### 11.2. Root Cause: Pyfqmr Border Lockout on Faceted Meshes
In `tools/mesh_decimator.py`, `border_flag` was hardcoded to `True` for weapons:
```python
border_flag = True if is_weapon else preserve_border
```
In QEM (Quadric Error Metrics) simplification via `pyfqmr`, enabling `preserve_border = True` strictly locks every boundary vertex and boundary edge loop. Because weapons (saw blades, hilts, triggers, gun barrels) and player armors (open coat hems, lapels, belts, buckles, straps) consist of multiple open topological sheets rather than closed manifolds, a majority of their vertices lie on boundaries. With `preserve_border = True`, pyfqmr could only collapse interior vertices, leaving edge loops dense and causing simplification to stall at 70%–85% of original geometry.

**Fix**:
1. Relaxed border constraints (`preserve_border = False`) for single-bone rigid weapon and armor components while preserving angle-weighted vertex normals.
2. Partitioned multi-bone weapons by dominant bone ID (`decimate_rigid_by_bone_groups`), strictly preserving multi-bone bridge faces (such as chain links, hinge pins, and mechanism joints) 100% untouched to prevent mesh tearing during trick weapon transform animations.

### 11.3. Root Cause: Semantic Bone Classifier False Positives
In `tools/mesh_decimator.py`:
```python
HAND_BONE_KEYWORDS = ("finger", "thumb", "hand", "palm", "wrist", "claw")
```
Weapons featuring mechanical articulation bones named `B_Rclaw` and `B_Lclaw` (e.g., the Saw Cleaver's serrated folding claws or the Beast Claw) matched the keyword `"claw"`. The submesh component partitioner erroneously tagged the weapon blades as humanoid `HANDS`, locking them to a 45% conservative ratio.

**Fix**:
In `classify_skeleton_bones(flv, is_weapon=is_file_weapon)`:
```python
if is_weapon or not getattr(flv, "bones", None):
    return set(), set()
```
Weapons bypass humanoid semantic bone classification completely.

### 11.4. Havok Cloth vs Rigid Armor Invariant
Bloodborne uses Havok Cloth simulation (`SpClothVertexUpdate`) for mantles, capes, skirts, and scarves. The compiled physics container `_c.hkx` references exact vertex buffer offsets and particle indices:
$$V_{\text{cloth\_psx}} \equiv V_{\text{cloth\_vanilla}}$$
Any modification to submeshes referencing `_Cloth.mtd` or `_cloth.mtd` causes out-of-bounds pointer dereferences and engine crashes. The ultra-low parts pipeline strictly preserves cloth submeshes at 100% geometry while reducing rigid submeshes to $0.20 - 0.25$ target ratio:
- `bd_m_9000` rigid submesh 0: 14,084 $\rightarrow$ 4,508 tris (32.0%)
- `bd_m_9000` rigid submesh 8: 3,065 $\rightarrow$ 1,106 tris (36.1%)
- `bd_m_9000` cloth submeshes 2–7: 7,366 $\rightarrow$ 7,366 tris (100.0% intact)

### 11.5. Special Shaders & Byte Sum Invariant
In ghost/phantom equipment (`*09.partsbnd.dcx` with `P_Ghost_SP.mtd`), vanilla bone weights are non-skinning or unnormalized float values with byte sums of $252 - 256$.
1. For submeshes under the 24-triangle simplification floor (`orig_count < 24`), `normalize_bone_weights_strict` is invoked to enforce byte sum $= 255$.
2. For special shaders where vanilla itself lacks partition of unity, the invariant auditor permits matching vanilla.

### 11.6. Batch Execution Results Across 984 Parts Archives
The deployment pipeline (`tools/batch_demake_parts_ultralow.py --all --deploy --workers 12`) completed across all 984 equipment archives in 60.1 seconds:
- **Total files processed**: 984 / 984 (0 failed, 100% pass)
- **Vanilla triangles**: 11,372,322
- **Ultra-low PSX triangles**: 4,765,958 (41.9% remaining)
- **Triangles eliminated**: **6,606,364 triangles**
- **Texture VRAM protection**: Preserved all previously mip-sliced retro TPF textures from `CUSA03173-PSX`, preventing texture re-inflation.

---

## 12. Ultra-Low Geometry Decimation for Enemies and Bosses (`chr/`)

### 12.1. Why Prior Character Passes Stalled Performance
In prior passes (`batch_demake_characters.py`), enemies and bosses retained heavy polygon loads:
1. **Alpha Fur Card Exclusion**: All meshes referencing `"fur"` or `"hair"` in their material name were bypassed 100% (`--fur-ratio 1.0`). For beasts like Father Gascoigne (`c5000`), 39,010 triangles of alpha fur cards remained untouched. The Scourge Beast (`c1000`) similarly retained 11,556 fur triangles.
2. **Conservative Skeleton Ratios**: Humanoid enemy bodies were decimated with conservative limits that kept multi-bone faces intact, leaving basic mobs at 18,000–30,000 triangles each. In chalice rooms containing 3–5 enemies, the GPU was burdened with over 120,000 dynamic character triangles.

### 12.2. Dedicated Fur Card QEM Decimation
Non-cloth fur cards are rendered using standard alpha-tested or emissive materials (`C[ARSN]_e.mtd`, `C[ARSN]_al.mtd`). Unlike Havok cloth, fur cards have no compiled physics particle constraints in `_c.hkx`.
By passing non-cloth fur submeshes into `decimate_component_shared_verts` with:
$$\text{target\_tris} = \max(24, \text{round}(\text{orig\_tris} \times 0.25))$$
the engine collapses redundant planar card splits while preserving boundary anchor vertices and dominant bone bindings. This achieved a 75% reduction on fur geometry (e.g. `c5000` fur dropped from 39,010 to ~9,700 tris) while maintaining authentic retro bristled fur silhouettes.

### 12.3. Vanilla Floating-Point Weight Discrepancies
During validation, 9 character archives (`c1010`, `c1130`, `c2730`, `c2620`, `c3050`, `c4060`, `c7000`, `c8045`, `c9980`) failed strict byte-sum $= 255$ checks. Inspection of pristine vanilla `CUSA03173` revealed that FromSoftware's original DCC export pipeline introduced rounding errors on unweighted chains and accessories:
$$\sum_{j=0}^3 \text{round}(w_j \times 255) = 254$$
Requiring absolute byte sum $= 255$ on untouched or lightly simplified geometry resulted in false positives. The invariant auditor was updated to enforce that decimation never introduces *new* bone weight errors:
$$\text{bad\_weights}_{\text{decimated}} \le \text{bad\_weights}_{\text{vanilla}}$$

### 12.4. Python Virtual Environment Configuration
When executing `uv run python ...`, `uv` attempted to resolve `Bloodborne` as a wheel package via `uv_build`, requiring `--no-project` because the repository is a mod workspace rather than a Python library. Adding:
```toml
[tool.uv]
package = false
```
to `pyproject.toml` explicitly configures the repository as a virtual script environment, permanently eliminating the need for `--no-project` flags.

### 12.5. Batch Execution Results Across 244 Character Archives
The deployment pipeline (`tools/batch_demake_characters_ultralow.py --all --deploy --workers 12`) processed all 244 character archives (excluding `c8030` Plain Doll) in 63.7 seconds:
- **Total archives processed**: 244 / 244 (0 failed, 100% pass rate)
- **Vanilla triangles**: 11,843,416
- **Ultra-low PSX triangles**: 3,923,491 (33.1% remaining)
- **Triangles eliminated**: **7,919,925 triangles** (66.9% cut across all enemies and bosses)
- **Combined Parts + Enemies Triangles Eliminated**: **14,526,289 triangles**

---

## 13. Comprehensive Uncompromised Performance & VRAM Pass

### 13.1. Interactive Object Props Decimation (`obj/`)
Prior demake iterations left all 1,880 world props (carriages, statues, barrels, lanterns, doors) undecimated at vanilla PS4 fidelity (~26.8 million triangles). The dedicated batch tool `tools/batch_demake_objects_ultralow.py` executed across all 1,880 archives:
- **Total archives processed**: 1,880 / 1,880 (100% pass rate)
- **Vanilla triangles**: 26,808,286
- **Demade PSX triangles**: 9,281,655 (34.6% remaining)
- **Triangles eliminated**: **17,526,631 triangles** (-65.4%)
- **Embedded TPF textures**: 819.6 MB $\to$ 89.6 MB (-89.1%)
- **Havok Collision & Physics**: `.hkx`, `.anibnd`, `.clm` preserved byte-for-byte.
- **Central Yharnam Phantoms**: Cloned demade `o299902` to `o299921`, `o299935`, `o299936`, `o299937`, `o299942`.

### 13.2. Enemy & Boss Texture Mip-Slicing (`chr/`)
Using `tools/shrink_chr_textures.py`, top mip levels were cleanly excised across all 268 character archives:
- **Diffuse (`*_a`, `*_a_l`)**: Sliced to $\le 256$px.
- **Secondary Maps (`*_n`, `*_s`, `*_r`)**: Sliced to $\le 128$px.
- **Fur & Hair Protection**: Patterns `*fur*`, `*hair*`, `*beard*`, `*_hr_*` excluded 100% to preserve silhouette appeal.
- **Texture bytes saved**: 975.6 MB $\to$ 129.8 MB (**806.6 MB saved** across 169 modified archives).

### 13.3. Equipment & Weapon Secondary Maps Reduction (`parts/`)
All 1,191 player equipment archives were processed:
- Normal, specular, and roughness maps dropped to $\le 128$px.
- **Texture bytes saved**: 1,759.3 MB $\to$ 85.8 MB (**1,595.9 MB saved** across 828 modified archives).

### 13.4. Over-Constrained Texture GC Stalls & Resolution
Initially, `BB_GC_BUDGET_MB=1024` and `BB_VRAM_LIMIT_MB=1536` were tested to simulate a retro VRAM cap. However:
1. `GetDeviceMemoryUsage()` reports *total* device VRAM, which includes render targets, G-buffers, swapchains, and host allocations (~900-1100 MB baseline).
2. Clamping the budget to 1536 MB resulted in $>92\%$ usage, triggering `TextureCache::VramShort()` permanently.
3. The engine entered emergency GC on every frame (`below_tick = gc_tick - 160`) and purged GPU buffers every 2 seconds (`EvictIdleCopies`), creating PCIe bus thrashing that spiked loading times and dragged frame pacing down to ~30 FPS.
4. **Resolution**: Removed `BB_GC_BUDGET_MB` and `BB_VRAM_LIMIT_MB`. The physical asset downsizing (sliced mips on disk) already keeps in-flight VRAM naturally small without inducing artificial driver panic or GC thrashing. Fast streaming and uncapped pacing are fully restored.

### 13.5. Luminance-Aware Light Attenuation Smoothing
To resolve harsh concentric "onion rings" around lamps and torches while retaining retro 15-bit color:
- `present_encode.frag` was upgraded to 6-bit channel quantization (`63.0`), 2x pixel-doubled Bayer dither, and smooth luminance falloff (`smoothstep(0.35, 0.85, lum)`).
- Eliminates stepping bands around bright lights while preserving authentic CRT-style dither in shadows and midtones. Recompiled into `libbbgpu.so`.

### 13.6. Storage Reclaim & Snapshot Hygiene
All redundant `.snap_*` and Soulstruct `.bak` backup files were audited and purged:
- Freed **19.7 GB** of disk bloat.
- Game folder size dropped from **41 GB to 19 GB** (vanilla baseline is 30 GB).

---

## 14. Mesh Integrity & Deferred Shading Fillrate Bottlenecks

### 14.1. The Performance Paradox: Vertex Shading vs Deferred Fillrate
Bloodborne is a deferred renderer. It writes 5 full-screen G-buffer targets (Albedo, Normal, Specular/Roughness, Depth, Material flags) and executes multi-pass compute/pixel shaders for every active light source, fog volume, and post-processing effect.
1. **Vertex Processing Overhead**: Modern GPUs (such as the GTX 1650) process over 1 billion vertices per second. In any typical Bloodborne room, vertex shading consumes $\le 0.5$ ms (less than 3% of the 16.6 ms frame budget). Cutting triangles by 60% saves $\approx 0.3$ ms, which is imperceptible on the FPS counter.
2. **Deferred Lighting Dominance**: At native $1680 \times 1050$, the GPU must evaluate lighting across $1,764,000$ pixels every single frame. Regardless of whether an object has 100 triangles or 10,000 triangles, the pixel shaders must execute on all covered pixels.
3. **Texture Sampling Cache**: Modern GPUs fetch textures into L1/L2 cache lines. Slicing textures to 256px reduces VRAM footprint, but yields identical sampling cycles once cached. Real performance gains come exclusively from **internal scene resolution scaling** (`preset=1` Quality mode: $1120 \times 700$, cutting fillrate by 55%).

### 14.2. Object Rigging Corruption on Animated Props
Over 80% of interactive objects in `obj/` are multi-bone animated rigs (`o000600` chest: 78 bones, `o000650` chest: 387 bones, `o000200` door: 202 bones).
When `decimate_flver` processed these archives:
1. Skeletons referencing bone names like `Head` or `Hand` (`c9000_A_Head` on `o000650`) were falsely routed through humanoid facial decimators.
2. Bone indices and weights were scrambled across joints.
3. In-game animations (`.anibnd`) transformed vertex positions using foreign bone matrices, causing vertices to stretch across the room (mesh explosions).
4. **Resolution**: `tools/repair_objects_clean.py` restored pristine FromSoftware FLVER meshes and bone rigs across all 1,880 archives, while cleanly slicing embedded TPF textures to $\le 256$px (saving 768 MB texture bytes with zero vertex risk).

### 14.3. Shader Ergonomics & Visual Usability
1. **Point Filtering Aliasing**: Nearest-neighbor sampling on high-resolution displays ($1680 \times 1050$) without mipmap filtering causes severe Nyquist frequency aliasing. Textures shimmer violently like TV static when moving. Bilinear sampling (`psx_point_filter=0`) stabilizes retro textures cleanly.
2. **Vertex Snapping**: Snapping vertices to 320x240 NDC induces continuous geometric vibration during camera motion. Disabling wobble (`psx_vertex_snap=0`) eliminates motion fatigue.
3. **Affine Mapping**: Disabling `psx_affine=0` prevents perspective distortion and texture swimming in narrow dungeon corridors.

---

## 15. Color Science, Chromaticity Locking & Engine Integration

### 15.1. Mathematical Root Cause of Chromatic Posterization
In standard post-processing retro shaders, 15-bit or 18-bit color quantization is typically applied independently to each RGB color channel:
$$C_{\text{out}} = \frac{\lfloor C_{\text{in}} \cdot 63.0 + 0.5 \rfloor}{63.0}, \quad C \in \{R, G, B\}$$

In low-luminance regions ($lum < 0.15$), a single quantization step ($\Delta = 1/63 \approx 0.0158$) constitutes a massive proportional jump (15% to 30% of total channel intensity).
Because real-world dark materials (such as weathered Hunter garb, cobblestone, and stone arches) are neutral greys where $R \approx G \approx B$, slight variations in pre-quantization values or dither noise cause adjacent channels to round in opposite directions:
$$(R, G, B) = (0.024, 0.023, 0.024) \xrightarrow{\text{quantize}} \left(\frac{2}{63}, \frac{1}{63}, \frac{2}{63}\right) = (0.0317, 0.0158, 0.0317)$$
Here, green is halved relative to red and blue ($G / R = 0.50$ instead of $0.96$), producing an intense, unnatural magenta blotch. On an adjacent pixel or Bayer matrix offset, the opposite rounding produces toxic green patches.

### 15.2. Chroma-Locked Luminance Dithering Formulation
To completely eliminate false-color splotches while preserving authentic retro-era CRT tonal dithering, we decouple luminance quantization from chromaticity:

1. **Luminance Extraction** (Rec. 601 / NTSC standard):
   $$Y = 0.299 R + 0.587 G + 0.114 B$$

2. **Bayer 4x4 Dither Addition to Luminance**:
   $$Y_{\text{dither}} = Y + \left(\frac{\text{Bayer4x4}(x, y)}{16.0} - 0.5\right) \cdot \frac{\text{dither\_strength}}{63.0}$$

3. **6-bit Scalar Quantization of Luminance**:
   $$Y_{\text{quant}} = \frac{\lfloor Y_{\text{dither}} \cdot 63.0 + 0.5 \rfloor}{63.0}$$

4. **Chroma-Locked Color Reconstruction**:
   $$RGB_{\text{final}} = RGB_{\text{in}} \cdot \left(\frac{Y_{\text{quant}}}{\max(Y, 0.0001)}\right)$$

**Mathematical Proof of Chromatic Invariance**:
For any two color channels $C_1, C_2 \in \{R, G, B\}$:
$$\frac{C_{1, \text{final}}}{C_{2, \text{final}}} = \frac{C_{1, \text{in}} \cdot \frac{Y_{\text{quant}}}{Y}}{C_{2, \text{in}} \cdot \frac{Y_{\text{quant}}}{Y}} = \frac{C_{1, \text{in}}}{C_{2, \text{in}}}$$
The chromaticity vector and hue angle $\theta$ are strictly invariant under quantization. Neutral greys remain pure neutral grey across all lighting conditions, eliminating 100% of chromatic posterization artifacts.

5. **Elimination of Artificial Black Lift**:
   Previous iterations added a scalar offset (`+0.045`) to lift darks, which caused Gothic Bloodborne shadows to appear milky grey. In the chroma-locked formulation, this artificial lift was removed ($+0.0$), restoring inky, true black levels with pristine contrast.

### 15.3. Live Vulkan Sampler Cache Key Invalidation
Vulkan objects (`VkSampler`, `VkPipeline`) are immutable on the GPU. When toggling retro options like "Point texture filtering" (`psx_point_filter`), modifying settings at runtime previously had no visual effect because `TextureCache::GetSampler` used a 64-bit key that omitted the PSX filtering state:
```cpp
// Key collision: Point and Bilinear requested identical cached VkSampler
uint64_t key = (static_cast<uint64_t>(min_filter) << 0) | ...;
```
**Fix**: `TextureCache::GetSampler` now incorporates `BbSettings::Get().psx_point_filter` into the key hash:
```cpp
uint64_t key = ...;
HashCombine(key, BbSettings::Get().psx_point_filter);
```
When the user toggles texture filtering in the ImGui overlay, the cache produces a different key, instantiating and binding the nearest-neighbor sampler on the very next draw call without restarting the game.

### 15.4. Split-Brain Configuration Resolution & Launcher Persistence
Two distinct configuration paths previously operated in parallel:
- **Native Port / Runner**: `../bbport-src/bbport.ini`
- **Desktop Launcher**: `~/.local/share/bbport/bbport.ini`

Because `run.sh` defaulted to local directory config without checking `$BB_CONFIG`, toggling options in the Launcher GUI failed to propagate to game launches.
**Resolution**:
1. `game_environment()` in `launcher/bbport_launcher.py` explicitly exports:
   ```python
   env["BB_CONFIG"] = str(self.config_path)
   env["BB_DATA_DIR"] = str(BB_DATA_DIR)
   ```
2. `run.sh` parses `$BB_CONFIG` first, falling back to local `bbport.ini`.
3. Widget initialization bug in `LauncherWindow.__init__` (calling `self.store()` before child row creation) was removed, restoring zero-warning GTK launcher startups.

---

## 16. Blender Headless Pipeline, Skeletal Cloth Decoupling & FLVER Re-Encoding

### 16.1. FromSoftware Cloth Rigging Architecture (The 46-Bone Discovery)
During reverse-engineering of `chr/c8030.chrbnd.dcx` (Plain Doll), a critical architectural reality of FromSoftware's rigging was uncovered:
Cloth submeshes (Skirt `Mesh 2`, Shawl/Mantle `Mesh 0/1`, Hair `Mesh 10/11`) are **not** unweighted cloth ribbons. Every cloth vertex is already rigged and skin-weighted to full skeletal chains in the FromSoft skeleton:
- `Skirt_B`, `Skirt_B02` ... `Skirt_B07` (Back skirt chain)
- `Skirt_F`, `Skirt_F02` ... `Skirt_F07` (Front skirt chain)
- `Skirt_L`, `Skirt_L02` ... `Skirt_L07` (Left skirt chain)
- `Skirt_R`, `Skirt_R02` ... `Skirt_R07` (Right skirt chain)
- `cape_F`, `cape_L`, `cape_R`, `c8030_BD_Mantle01`, `c8030_BD_Mantle02` (Shawl chains)
- `c8030_Hair01`, `c3080_Hair02`, `c8030_BackHair` (Hair chains)

In vanilla Bloodborne, FromSoftware character artists rigged all clothing to skeletal chains first. Havok Cloth simulation (`_c.hkx` / `_c.clm2`) was layered on top as an optional runtime physics override.

### 16.2. Havok Cloth Solver Dependency Invariant
The engine's cloth physics system (`SpClothVertexUpdate`) executes **only** when two conditions are met:
1. Submesh material definition (`MTD`) specifies a cloth shader (e.g. `C[ARSN]_e_Cloth.mtd` or `C[ARSN]_Cloth.mtd`).
2. The `.chrbnd.dcx` container includes `c8030_c.hkx` and `c8030_c.clm2`.

When `_c.hkx` is excluded from the container and materials are swapped to standard skinned materials (`C[ARSN]_e.mtd`), the engine **never initializes `SpClothVertexUpdate`**. The clothing animates 100% naturally via standard skeletal skinning. This permanently eliminates:
- Vertex count mismatch crashes.
- Cloth vertices shooting to $\pm\infty$.
- Havok cloth memory overhead.

### 16.3. Blender 5.2.3 Python ABI Boundary & glTF 2.0 Interchange
- **ABI Incompatibility**: Blender 5.2.3 LTS embeds Python 3.14 (`/usr/bin/python3.14`). The project virtualenv uses Python 3.13 (`cpython-3.13-x86_64-linux-gnu`). Compiled C-extensions (NumPy `_multiarray_umath.cpython-313...`, Soulstruct DCX/Oodle bindings) trigger fatal `ImportError: incompatible with python 'cpython-314'` when loaded in Blender.
- **Interchange Architecture**: We strictly decouple the toolchain via standard Binary glTF 2.0 (`.glb`):
  1. `tools/pipeline/flver_to_rigged_gltf.py` (`.venv`, Python 3.13): Reads FLVER and TPF via Soulstruct, builds standard 206-joint glTF skin, and outputs `c8030_rigged.glb`.
  2. `tools/pipeline/blender_process_c8030.py` (Blender 5.2.3, Python 3.14): Imports glTF, executes decimate modifier with boundary and seam preservation, prunes vertex influences to $\le 4$, and exports `c8030_demade.glb`.
  3. `tools/pipeline/rigged_gltf_to_flver.py` (`.venv`, Python 3.13): Reads `c8030_demade.glb`, maps submeshes back to Bloodborne dual-array layouts (`VA0`/`VA1`), swaps cloth MTDs, recalculates AABB boxes, and compiles the new FLVER.

### 16.4. Inverse Bind Matrix (IBM) & Coordinate System Derivation
In glTF 2.0, skinning evaluates:
$$v' = \sum_{j} w_j \cdot M_{\text{animated}, j} \cdot IBM_j \cdot v$$
To maintain exact bind-pose alignment with FromSoftware models:
1. Local bone matrix $M_{\text{local}} = T(x, y, z) \cdot R(\text{quat}) \cdot S(s_x, s_y, s_z)$.
2. FromSoftware Euler angles are evaluated in XZY order: pitch ($X$), roll ($Z$), yaw ($Y$).
3. Bone world matrix $M_{\text{world}, j} = M_{\text{world}, \text{parent}} \cdot M_{\text{local}, j}$.
4. Inverse Bind Matrix $IBM_j = (M_{\text{world}, j})^{-1}$, packed into column-major `float32x16` format.
In bind pose, $M_{\text{animated}, j} \cdot IBM_j = I$, guaranteeing zero vertex drift on import.

### 16.5. Dual-Buffer Split Vertex Arrays (`VA0`/`VA1`) & Soulstruct AABB Patch
Bloodborne FLVER meshes mandate split vertex arrays:
- `VA0`: `position` (float3), `normal` (float3 / packed uint8x4), `tangent_0` (float4, with $T_w = -1.0$).
- `VA1`: `bone_indices` (uint16x4 / uint8x4), `bone_weights` (float4, normalized $\sum w_i = 1.0$), `uv_0` (float2).

**Soulstruct Bug & Patch**:
Soulstruct's native `FLVER.refresh_bounding_boxes()` unconditionally attempts `vertex_array["position"]` across all arrays in a mesh, crashing with `ValueError: no field of name position` when encountering `VA1`.
`tools/soulstruct_patch.py` was extended to patch `refresh_bounding_boxes`, checking `if "position" in va.array.dtype.names:` before querying min/max extents, enabling fully automated, crash-free FLVER recompilation.

### 16.6. Blender Alphabetical Joint Index Sorting & Dynamic Remap
- **The Bug**: When exporting rigged models from Blender via `bpy.ops.export_scene.gltf`, Blender's glTF serializer sorts bone nodes alphabetically when assembling the `skin.joints` list. Node 0 became `AM_F_7000_01` (Left Arm) instead of `Pelvis`.
- **The Failure**: When `rigged_gltf_to_flver.py` read `JOINTS_0` directly as FromSoftware bone IDs, vertices assigned to Joint 0 were mapped to FLVER Bone 0 (`Pelvis`), and vertices assigned to Joint 145 (`Head`) were mapped to FLVER Bone 145 (`Master`). During runtime idle animation playback, the Pelvis rotation bent the character's arm and head into the ground, producing an exploded diagonal T-pose.
- **The Mathematical Solution**:
  Construct a dynamic translation LUT $\mathcal{M}: \mathbb{N} \to \mathbb{N}$:
  $$\mathcal{M}(j) = \text{index of } (\text{NodeName}(\text{Joint}[j])) \text{ in } \text{FLVER.bones}$$
  For each vertex $v$ and influence slot $k \in \{0, 1, 2, 3\}$:
  $$\text{BoneID}_{\text{FLVER}}(v, k) = \begin{cases} \mathcal{M}(\text{JOINTS}_0(v, k)) & \text{if } \text{WEIGHTS}_0(v, k) > 10^{-5} \\ 0 & \text{otherwise} \end{cases}$$
  Guarantees 100% anatomical fidelity across all 206 skeleton bones.

---

## 17. FromSoftware FLVER Tangent Vector Axis Convention & Midline Sagittal Symmetry

### 17.1. Tangent Vector Axis Mismatch ($sdir$ vs $tdir$)
Standard glTF, Blender, and MikkTSpace exporters store the **$U$-derivative** ($\mathbf{S}_{\text{dir}}$) in the primary tangent vector $\mathbf{T}$, where:
$$\mathbf{P}_1 - \mathbf{P}_0 = \Delta U_1 \mathbf{S}_{\text{dir}} + \Delta V_1 \mathbf{T}_{\text{dir}}$$
$$\mathbf{P}_2 - \mathbf{P}_0 = \Delta U_2 \mathbf{S}_{\text{dir}} + \Delta V_2 \mathbf{T}_{\text{dir}}$$
Solving for $\mathbf{S}_{\text{dir}}$ and $\mathbf{T}_{\text{dir}}$ yields:
$$\det = \Delta U_1 \Delta V_2 - \Delta V_1 \Delta U_2$$
$$\mathbf{S}_{\text{dir}} = \frac{1}{\det} (\Delta V_2 (\mathbf{P}_1 - \mathbf{P}_0) - \Delta V_1 (\mathbf{P}_2 - \mathbf{P}_0))$$
$$\mathbf{T}_{\text{dir}} = \frac{1}{\det} (\Delta U_1 (\mathbf{P}_2 - \mathbf{P}_0) - \Delta U_2 (\mathbf{P}_1 - \mathbf{P}_0))$$

Empirical analysis across all 13 submeshes of pristine vanilla `c8030.flver` revealed that FromSoftware stores **$\mathbf{T}_{\text{dir}}$ (the $V$-derivative / bitangent direction)** in `tangent_0`, with absolute dot product correlation exceeding $0.95$:
$$\langle \mathbf{T}_{\text{vanilla}}, \mathbf{T}_{\text{dir}} \rangle = 0.896 \text{ to } 0.996 \quad (\text{versus } \langle \mathbf{T}_{\text{vanilla}}, \mathbf{S}_{\text{dir}} \rangle < 0.16)$$

**The Symptom**: When feeding $\mathbf{S}_{\text{dir}}$ into `tangent_0`, FromSoftware's character pixel shader evaluated tangent-space normal maps rotated by $90^\circ$. Because the Plain Doll's facial UV map is mirrored across the vertical midline ($X=0$), feeding the wrong tangent axis caused the reconstructed normal on the right side of the face to invert inwards into the skull, plunging the entire right cheek into deep shadow.

### 17.2. Handedness ($W$) Formula Inversion on Mirrored UVs
In FromSoftware FLVER meshes, the tangent handedness component $T_w \in \{-1.0, +1.0\}$ strictly follows the determinant of the UV coordinate transformation:
$$T_w = \begin{cases} +1.0 & \text{if } \det_{\text{UV}} \ge 0 \\ -1.0 & \text{otherwise} \end{cases}$$
Accumulated across triangle interior angles $\alpha_c$:
$$\text{det\_sum}(v) = \sum_{f \in \text{Faces}(v)} \text{sign}(\det_f) \cdot \alpha_c(f, v)$$
$$T_w(v) = \begin{cases} +1.0 & \text{if } \text{det\_sum}(v) \ge 0 \\ -1.0 & \text{otherwise} \end{cases}$$
Verification against pristine `c8030.flver` confirmed a **100.0% match** on non-degenerate geometry.

### 17.3. Midline Sagittal Symmetry Normal Invariant
In symmetrical humanoid character models, decimation along UV seams creates small transverse offsets ($\Delta X \in [0.001, 0.005]\text{m}$) and tilts normal vectors ($|N_x| \in [0.3, 0.7]$) across the nose bridge and chin.
In pristine FromSoftware character FLVERs, all vertices lying on the sagittal midline ($X=0$) strictly have $N_x = 0.000$ and $T_x = 0.000$.

**Enforcement Rule**:
For any vertex $v$ with $|P_x(v)| < 0.0050\text{m}$:
$$P_x(v) \leftarrow 0.0$$
$$N_x(v) \leftarrow 0.0, \quad \mathbf{N}(v) \leftarrow \text{normalize}(\mathbf{N}(v))$$
$$T_x(v) \leftarrow 0.0, \quad \mathbf{T}(v) \leftarrow \text{normalize}(\mathbf{T}(v))$$
This eliminates all photometric seam discontinuities and normal map splits down the center line.

### 17.4. Default Vertex Color Vector
FromSoftware character shaders use `color_0` as a multi-channel surface mask:
- Red ($R = 1.0$): Ambient occlusion / cavity lighting.
- Green ($G = 0.0$): Subsurface scattering (SSS) / translucency / wetness mask. Setting $G = 1.0$ fully saturates subsurface transmission.
- Blue ($B = 1.0$): Emissive / detail multiplier.
- Alpha ($A = 1.0$): Surface opacity / blend factor.

Default FLVER character vertex color is therefore strictly $\mathbf{C} = [1.0, 0.0, 1.0, 1.0]$.

---

## 18. Player Equipment Cloth Skeletal Skinning & Trick Weapon Multi-FLVER Invariants

### 18.1. Armor Cloth Skeletal Pre-Binding Discovery
Inspection of all player body armor FLVERs (`BD_M_XXXX.flver`, `BD_F_XXXX.flver`) revealed that every submesh assigned to a cloth material (e.g. `mantle_cloth`, `skirt01_cloth`, `frontskirt_cloth`, `towel_cloth`, `scarf_cloth`) is already **100% skin-weighted** to the character skeleton in vertex array `VA1`:
$$\sum_{k=0}^{3} w_k(v) = 1.000 \quad \forall v \in \text{ClothVertices}$$
The Havok cloth solver (`SpClothVertexUpdate`) was merely applying an iterative dynamic displacement vector on top of these skeletal positions. When decoupling cloth physics:
1. All `_Cloth.mtd` material definitions are replaced with standard skinned character materials (`.mtd` / `_e.mtd`).
2. All `_c.hkx` (Havok physics pack) and `_c.clm2` (cloth collision mask) binder entries are purged.
3. The geometry can now be safely simplified via Blender decimation without triggering vertex-count mismatch assertions in the engine.
4. In-engine runtime deforms execute exclusively through standard GPU matrix skinning, eliminating 100% of cloth solver CPU/GPU overhead while animating smoothly with the player skeleton.

### 18.2. Trick Weapon Multi-FLVER States & Dummy Invariants
Bloodborne trick weapons (`WP_A_XXXX.partsbnd.dcx`) contain 1 to 4 distinct FLVER archives representing discrete mechanical transformation stages:
- `WP_A_XXXX.flver`: Retracted / untricked state (e.g. folded Saw Cleaver).
- `WP_A_XXXX_1.flver`: Intermediate transition / unfolding state.
- `WP_A_XXXX_2.flver`: Extended / tricked state (e.g. open Saw Cleaver).
- `WP_A_XXXX_3.flver`: Sheath or secondary accessory (when applicable).

**Dummy Invariant**:
Each weapon FLVER contains critical `Dummy` struct entries:
- `Dummy 0`: Weapon grip attachment point (anchored to character right hand `R_Hand`).
- `Dummy 10..19`: Hitbox volume centers and blade trajectory raycasts.
- `Dummy 20..29`: Bullet muzzle flash, projectile spawn vectors, and elemental trail anchors.

The glTF export and FLVER recompiler strictly preserve all original `Dummy` entries by serializing them alongside the mesh metadata and re-injecting them bit-for-bit into the recompiled FLVER headers. Zero dummies are discarded or re-indexed.

---

## 19. Enemy Fur Shell Overdraw & Full Character Cloth MTD Disambiguation

### 19.1. Beast Fur Shell Geometry & Overdraw Optimization
Beast and boss characters in Bloodborne (`c1000` Werewolf/Beast Patient, `c1020` Scourge Beast, `c2010` Cleric Beast, `c2110` Vicar Amelia, `c8045` Watchdog) utilize multi-layered alpha-tested shell geometry (e.g. `#10#_Fur`, `#10#_Fur2_cloth`, `#10#_Fur4_cloth`, `#10#_Fur5_cloth`).
- **Overdraw Contention**: Stacking 4–6 layers of alpha-tested fur cards across 80,000+ triangles causes massive deferred fragment shading stalls on low-midrange GPUs (GTX 1650 fillrate saturation).
- **QEM Puncturing vs. Blender Decimation**: Algorithmic QEM collapsed thin shell layers unevenly, causing adjacent fur cards to intersect and invert normals, producing jagged see-through holes in beast silhouettes.
- **Blender 5.2.3 Topology Collapse**: Applying Blender's volume-preserving decimation at ratio 0.20 (preserving boundary edges and smooth vertex normals) reduces fur triangle density by 80% uniformly. The outer silhouette cards remain intact while inner overdraw cards are simplified, delivering retro fur coats with zero visual holes and 75% lower fragment fillrate.

### 19.2. Complete 20-Variant Cloth MTD Translation Table
Analysis of all 245 character archives identified 20 distinct FromSoftware Havok cloth material definitions (`MTD`). In order to completely eliminate runtime `SpClothVertexUpdate` allocations without causing missing material purple/black fallbacks, `tools/pipeline/rigged_gltf_to_flver.py` maps every cloth MTD to its exact FromSoft skinned equivalent:

| Original Cloth MTD | Decoupled Skinned Replacement | Category / Usage |
| :--- | :--- | :--- |
| `C[ARSN]_Cloth.mtd` | `C[ARSN].mtd` | Standard enemy body cloth |
| `C[ARSN]_Df_Cloth.mtd` | `C[ARSN]_Df.mtd` | Diffuse-focused cloth |
| `C[ARSN]_Df_e_Cloth.mtd` | `C[ARSN]_Df_e.mtd` | Diffuse + edge highlighted cloth |
| `C[ARSN]_SSS_Cloth.mtd` | `C[ARSN]_SSS.mtd` | Subsurface scattering cloth |
| `C[ARSN]_SSS_e_Cloth.mtd` | `C[ARSN]_SSS_e.mtd` | SSS + edge highlighted cloth |
| `C[ARSN]_Tr_e_Cloth.mtd` | `C[ARSN]_e.mtd` | Translucent edge cloth |
| `C[ARSN]_e_Cloth.mtd` | `C[ARSN]_e.mtd` | Standard edge cloth (Gascoigne coat) |
| `C[ARSN]_em_Glow_Cloth.mtd` | `C[ARSN]_em_Glow.mtd` | Emissive glowing cloth |
| `C[ARSN]_em_Glow_e_Cloth.mtd` | `C[ARSN]_em_Glow_e.mtd` | Glowing edge cloth |
| `C[DSB][IBL][Alpha][Cloth].mtd`| `C[DSB][IBL][Alpha].mtd` | Alpha cutout cloth (`c9911`) |
| `C[DSB][IBL][Cloth].mtd` | `C[DSB][IBL].mtd` | IBL environmental cloth (`c7000`) |
| `C[DSB][IBL][Edge][Cloth].mtd` | `C[DSB][IBL][Edge].mtd` | IBL edge cloth (`c7000`) |
| `C[ARSN]_Cloth_PDEnhanced.mtd` | `C[ARSN]_PDEnhanced.mtd` | PDEnhanced boss cloth (`c5020`) |
| `C[ARSN]_SSS_e_Cloth_PDEnhanced.mtd`| `C[ARSN]_SSS_PDEnhanced.mtd`| SSS PDEnhanced cloth (`c5020`) |
| `C[ARSN]_Tr_e_Cloth_PDEnhanced.mtd` | `C[ARSN]_e_PDEnhanced.mtd` | Translucent PDEnhanced cloth (`c5020`)|
| `C[ARSN]_e_Cloth_PDEnhanced.mtd` | `C[ARSN]_e_PDEnhanced.mtd` | Edge PDEnhanced cloth (`c5020`) |
| `C_3060_[ARSN]_Dither_Cloth.mtd` | `C_3060_[ARSN]_Dither.mtd` | Dithered ghost cloth |
| `C_Ghost_SP_Cloth.mtd` | `C_Ghost_SP.mtd` | Special ghost cloth |
| `P[ARSN]_Cloth.mtd` | `P[ARSN].mtd` | Parts / armor base cloth |
| `P[ARSN]_e_Cloth.mtd` | `P[ARSN]_e.mtd` | Parts / armor edge cloth |

### 19.3. Rigged glTF Bone Weight Normalization Invariant
To ensure flawless GPU matrix deformation on PS4/Linux Vulkan hardware:
1. Every vertex $v$ must have at most 4 active bone influences ($\text{degree} \le 4$).
2. Vertex bone weights $w_i \in [0.0, 1.0]$ are normalized such that $\sum_{i=0}^{3} w_i = 1.000$.
3. When serialized to FromSoftware 8-bit vertex layouts:
   $$B_i = \text{round}(w_i \times 255.0)$$
   $$\Delta = 255 - \sum_{i=0}^{3} B_i, \quad B_{\text{argmax}} \leftarrow B_{\text{argmax}} + \Delta$$
   $$\sum_{i=0}^{3} B_i \equiv 255 \quad \forall v \in \text{Meshes}$$
Enforcing this closed-form byte-sum normalization eliminates 100% of skinning floating-point drift and prevents vertex tearing at joint boundaries.

---

## 20. World Object Rigid Collision & Skeletal Rig Decimation Invariants

### 20.1. Rigid Player Collision vs. Havok Cloth Solver Separation
In `dvdroot_ps4/obj/`, object archives (`.objbnd.dcx`) store two fundamentally distinct categories of physics and simulation files:
1. **Rigid Body Player Collision (`oXXXXXX.hkx`)**: 1,857 files that define physical convex hulls, raycast boundaries, and collision primitives for player interaction (chests, ladders, doors, tombstones, fences, carriages). Stripping these files results in physics clipping where the player passes through solid props or falls through elevator floors. These must be **100% preserved**.
2. **Dynamic Cloth Solver Files (`*_c.hkx`, `*_cloth.hkx`, `*_c.clm`, `*_cloth.clm`, `*_c.clm2`)**: 37 files that compute iterative dynamic vertex displacement on street banners, flags, and awnings in Central Yharnam (`o222996`, `o222997`, `o222998`, `o222999`).
The batch demake pipeline enforces strict prefix/extension filtering:
$$\text{is\_cloth}(e) \iff (``\_c." \in e \lor ``\_cloth." \in e) \land e.\text{ext} \in \{\text{.hkx}, \text{.clm}, \text{.clm2}\}$$
Cloth solvers are purged while 1,857 rigid player collision files and 505 animation archives (`.anibnd`) remain completely untouched.

### 20.2. Complex Multi-Bone Prop Skeletons & Animation Preservation
Unlike static map architecture, interactive and animated world objects utilize complex multi-bone skeletal hierarchies:
- `o000650` (Ornate Coffin Rig): 387 bones, 71 dummies.
- `o000200` (Cathedral Ward Iron Door): 202 bones, 1 dummy.
- `o000600` (Treasure Chest): 78 bones, 1 dummy.
Legacy Python QEM decimated these meshes without bone hierarchy tracking, scrambling joint assignments and causing exploding geometry when opened in-game (Test 53). Headless Blender 5.2.3 exports these props as rigged binary glTF with full bone hierarchies. The FLVER recompiler builds a dynamic bone name LUT:
$$\text{LUT}: \text{BoneName} \mapsto \text{GlobalFLVERIndex}$$
This maps Blender joint indices directly back to FromSoftware global bone IDs, preserving 100% of skeletal rigs and `Dummy` attachment points.

### 20.3. Empty MTD Defensive Guard in Soulstruct
Certain environment props (e.g. `o222011` Chalice Dungeon shelf, `o281500`, `o293410`) contain materials with empty definition paths (`mtd = ""`). In Soulstruct:
```python
@mat_def_name.setter
def mat_def_name(self, name: str):
    self.mat_def_path = str(Path(self.mat_def_path).with_name(name))
```
Passing an empty string to `Path.with_name("")` raises Python's standard `ValueError: Invalid name ''`. The compiler implements a defensive equality guard:
```python
if decouple_cloth and m.material.mat_def_name:
    new_mtd = decouple_cloth_mtd(m.material.mat_def_name)
    if new_mtd != m.material.mat_def_name:
        m.material.mat_def_name = new_mtd
```
This safely bypasses empty MTD definitions without throwing exceptions during batch processing.

---

## 21. Object Animation Node Bindings, Ladders, and Retro Hard Split Normals

### 21.1. Rigid Submesh Bone Binding Invariant (`default_bone_index`)
Bloodborne animated doors (e.g. `o000200`) do not use vertex skinning matrices ($w_i$). Instead, each door leaf is an unskinned rigid submesh whose movement is governed entirely by `submesh.default_bone_index`:
- Leaf 0: `default_bone_index = 96`
- Leaf 1: `default_bone_index = 98`
- Leaf 2: `default_bone_index = 100`
- Leaf 3: `default_bone_index = 102`
- Stationary Frame: `default_bone_index = 0`

Round-tripping through standard DCC pipelines resets `default_bone_index = 0`, pinning all door leaves to the origin frame so doors appear permanently closed in-game. To guarantee 100% animation and interaction fidelity, all 504 animated objects (`.anibnd`) and ladders (`o0001*`) bypass mesh decimation entirely, retaining pristine FLVER geometry while utilizing low-res sliced TPF textures.

### 21.2. Eliminating the Specular "Plastic Sheen" via Split Normals
In Vulkan deferred shading, calling `bpy.ops.object.shade_smooth()` averages surface normals across adjacent polygon edges. For hard-surface stone blocks, pillars, and iron gates, smoothed normals produce curved specular gradients:
$$\mathbf{N}_{\text{smooth}} = \frac{\sum_i \mathbf{N}_i}{\|\sum_i \mathbf{N}_i\|}$$
This causes the Blinn-Phong specular term $(\mathbf{N} \cdot \mathbf{H})^m$ to generate wide, soft highlights characteristic of molded plastic. Enforcing hard split normals:
```python
for poly in obj.data.polygons:
    poly.use_smooth = False
```
restores discontinuous surface normals at geometric edges, restoring authentic chiseled stone and faceted retro iron.

---

## 22. Detail-Preserving Non-Destructive World Maps Demake (`map/`)

### 22.1. Why Aggressive LOD2 Promotion Degrades Visual Quality
In FromSoftware map chunks (`*.flver.dcx`), LOD2 meshes (`flags = 2`) were authored for distant background culling (kilometers away). When forced into the player's immediate foreground:
1. Architectural cornices, Gothic window tracery, balustrades, and cemetery railings are culled completely.
2. Buildings become flat rectangular cuboids with minimal geometric variance, maximizing plastic specular reflection.
3. Lightmap UV coordinates and vertex ambient occlusion buffers become misaligned.

### 22.2. "Keep Rendered, Reduce Detail" Mathematical Framework
The high-fidelity map demake engine (`tools/pipeline/batch_demake_maps_fidelity.py`) partitions map FLVERs into two distinct domains:

1. **Foreground Architecture & Walkable Geometry ($\text{ChunkID} < 2000$)**:
   $$\text{Geometry}(F) = \text{LOD0}_{\text{vanilla}}$$
   Maintains 100% FromSoftware authored geometry (2,617 chunks) to eliminate all plastic box collapse and maintain fine Gothic silhouettes.
2. **Distant Vista & Mountain Cliffs ($\text{ChunkID} \ge 2000$)**:
   Promotes native gentle $\text{LOD1}$ with a strict $50\%$ triangle floor:
   $$\text{FaceSet}_0 \leftarrow \text{FaceSet}_{\text{LOD1}} \iff \frac{|\text{FaceSet}_{\text{LOD1}}|}{|\text{FaceSet}_{\text{LOD0}}|} \ge 0.50 \land |\text{FaceSet}_{\text{LOD1}}| \ge 24$$
   If $\text{LOD1}$ is absent or falls below 50%, $\text{LOD0}$ is retained intact.
3. **Texture VRAM Reduction**:
   All 14 map BXF texture archives (`m21` through `m36`) remain downscaled to $\le 256$px/128px, delivering 85% to 98% VRAM reduction without culling geometry.

### 22.3. Batch Deployment Results Across 84 Maps
- **Total FLVERs Processed**: 11,033 / 11,033 (0 failures)
- **Foreground Pristine LOD0**: 2,617 FLVERs
- **Vista Gentle LOD1**: 5,946 FLVERs (saving 35,634,931 triangles, -29.8% on vistas)
- **Vista Pristine LOD0**: 2,470 FLVERs
- **Execution Time**: 97.6 seconds (12 workers)

---

## 23. FromSoftware Level Geometry Chunk Partitioning (< 8000)

### 23.1. Mathematical Root Cause of Stair Collapse & Slanted Mesh Explosion
In FromSoftware map archives (`mXX_00_00_00_CCCCDD.flver.dcx`), chunk suffixes do not partition at index 2,000. Chunks `002000` through `007999` are active, walkable city streets, staircases, and residential architecture within player bounds:
$$\text{Chunk } 002020: X \in [-32.1, -17.9], \; Y \in [7.3, 12.0], \; Z \in [175.6, 194.3]$$
$$\text{Chunk } 002010: X \in [-34.4, -16.3], \; Y \in [2.1, 7.1], \; Z \in [170.5, 192.0]$$
This spans the Central Yharnam stone staircase leading from the lamp terrace ($Y=10$) down to the street bonfire ($Y=2$). Swapping FaceSet 0 with LOD1 indices on these foreground chunks caused:
1. **Rib & Platform Elimination**: Fine step treads and landing platforms collapsed into planar ramps.
2. **Mesh Explosion**: LOD1 vertex indices indexed simplified bounding polygons that produced a large slanted rectangular facet stretching across the stairs.

### 23.2. Level Geometry Boundary ($\text{ChunkID} < 8000$)
Empirical analysis of all 84 map directories establishes that true distant vistas and horizon mountains occur exclusively at indices $\ge 8000$ (e.g. `008100`..`009501` with $X \in [-2716, 2736]$, $Z \in [-2738, 2714]$):
$$\text{Geometry}(F) = \begin{cases} \text{LOD0}_{\text{vanilla}} & \text{if } \text{ChunkID} < 8000 \quad (6,502 \text{ chunks}) \\ \text{Gentle LOD1} & \text{if } \text{ChunkID} \ge 8000 \land |\text{LOD1}| \ge 0.50 \cdot |\text{LOD0}| \quad (3,498 \text{ chunks}) \end{cases}$$

### 23.3. Staircase Props Whitelist (`obj/`)
Movable wooden stair props (`o257200` and `o257201` `obj_stair_01`, along with `o214007`, `o243001`, `o259000`, `o323080`, `o241013`, `o270050`, `o353006`) are whitelisted alongside animated objects to retain 100% pristine FLVER geometry.

---

## 24. Interactive Props, Ladder Alpha Rungs, and Workshop Door Architecture (`obj/`)

### 24.1. Missing Ladder Rungs Root Cause (`o000100`)
In Bloodborne, ladders across the entire world are single-instanced via `o000100.objbnd.dcx` using scalable side poles and 1-bit alpha texture card geometry for the rungs:
1. `o000100.flver` contains twin vertical rails with a flat polygonal plane spanning between them.
2. The diffuse map `o0100_a` (BC1/DXT1 format, 1024x1024) defines horizontal wooden slats via binary alpha cutouts.
3. Slicing/downscaling `o0100_a` to $128 \times 128$ blurred the sub-pixel rung boundaries below the BC1 alpha test threshold ($A < 0.5 \implies 0$), rendering all rungs completely invisible and leaving only bare vertical side poles.

### 24.2. Closed & Plastic Doors / Shattered Hunter's Dream Door (`o213002`)
1. **Interactive State Desync**: Decimating `anibnd` interactive objects desynchronized bone hierarchy binding matrices (`default_bone_index`), forcing doors into unrotated initial T-poses and producing unnatural flat plastic specular sheen.
2. **Hunter's Dream Workshop Door (`o213002`)**: The workshop door incorporates cracked glass mullions. Slicing its texture `o213002_WP_A_1021_a` down to $256 \times 128$ severely corrupted delicate multi-bit glass alpha transparency, causing the glass panels to render as jagged, shattered floating polygons.

### 24.3. Interactive Asset Evolution
Initially whitelisted to pristine vanilla, interactive props are now successfully demade to authentic PSX low-poly geometry while retaining 100% spatial, animation, and alpha fidelity using the bone-local coordinate pipeline detailed in Section 25.

---

## 25. Bone-Local Rigid Decimation & Aesthetic Preservation Architecture (`obj/`)

### 25.1. The Root Cause of Offset & Sunken Doors
In FromSoftware FLVER models, objects are partitioned into two architectural classes:
1. **Skinned Meshes** (`has_skin = True`): Contain per-vertex `bone_indices` and `bone_weights` (characters, enemies, cloth). Vertices are defined in model/world space relative to the skeleton root.
2. **Rigid Props & Doors** (`has_skin = False`): Submesh vertices are stored directly in **bone-local coordinate space** relative to `default_bone_index`.

When exporting unskinned rigid models through a glTF Armature with `inverseBindMatrices` ($\mathbf{B}^{-1}$), the bone-local vertices were mistakenly treated as model-space coordinates. When imported into Blender and re-exported, the mesh was assigned an armature transform. In-game, the engine applied the bone world matrix $\mathbf{M}_{\text{bone}}$ to vertices that had already been transformed:
$$\mathbf{v}_{\text{render}} = \mathbf{M}_{\text{bone}} \cdot \mathbf{M}_{\text{bone}} \cdot \mathbf{v}_{\text{local}}$$
For the Hunter's Dream workshop door (`o210011`):
- Bone 1 translation: $T_y = +2.628$ m, rotation $\theta = +95.0^\circ$ ($1.658$ rad).
- Double transform caused the door to rotate $190^\circ$ (appearing backwards or sunken through the wall) and translated the hinge into the floor, while unskinned door halves sat at unrotated origin poses.

### 25.2. Pure Bone-Local glTF Decimation Pipeline
To preserve exact spatial alignment, hinge pivots, and open/closed animations while cutting geometry by 80%:
1. **Unskinned glTF Export (`flver_to_rigged_gltf.py`)**:
   If $\forall m \in \text{Meshes}, \text{bone\_indices} \notin \text{va.array.dtype}$, Armature node, bone nodes, IBM buffer, and `skins` array are completely bypassed. Each submesh is exported as a standalone root scene node in pure bone-local space.
2. **Headless Blender Decimation**:
   Blender applies `DecimateModifier(ratio=0.20)` directly on the bone-local mesh. Zero bone matrices are touched.
3. **FLVER Recompilation (`rigged_gltf_to_flver.py`)**:
   Midline sagittal symmetry enforcement is restricted to `len(skin_joints) > 0` (preventing seam distortion on door panels). Vertices are repacked directly into `va.array` while preserving the exact `default_bone_index` of each submesh and the pristine bone hierarchy from `base_flver`.
4. **Boundary Verification**:
   The resulting bounding boxes match vanilla FromSoftware geometry to within sub-millimeter precision ($\Delta \le 6 \times 10^{-6}$ m), guaranteeing perfect hinge alignment and in-game animation playback.

### 25.3. Texture Alpha Cutout Protection (`has_alpha_cutout`)
For props relying on alpha transparency:
- Universal ladder `o000100` uses a 1-bit alpha quad to render horizontal rungs between side poles.
- Workshop doors and Gehrman assets (`o210010`..`o210013`, `o213002`) incorporate cracked multi-bit glass mullions.
- The pipeline flags these models via `has_alpha_cutout`, strictly preserving the pristine vanilla TPF container (1.62 MB with intact BC3/DXT5 alpha channels) while reducing mesh triangles to 20.0%, fully eliminating missing ladder rungs and shattered glass artifacts.

---

## 26. Static Prop Model-Space Pre-Baking for Port / Engine Renderers

### 26.1. The Bone Hierarchy Discrepancy in PC Ports
In native Bloodborne on PS4, the engine's scene graph computes world matrices for all bones $\mathbf{M}_{\text{bone}}$ and multiplies each submesh by its `default_bone_index`.
In PC ports and emulators (such as `bbport`), static environment props (`obj/` archives lacking `.anibnd` animations) are optimized: their FLVER vertex buffers are uploaded directly to Vulkan as static geometry and drawn with only the actor's world transform matrix.

### 26.2. The Workshop Door Artifact (`o210011`, `o210012`, `o210013`)
In FromSoftware's pristine assets, the workshop doors were exported with asymmetric coordinate spaces:
- `o210010` (Closed door): Modeled in model space ($X \in [-1.09, 1.09], Y \in [-0.035, 3.09]$).
- `o210011` (Open door): Modeled in Bone 1 local space ($Y \in [-2.315, 0.811]$), where Bone 1 contains translation $T_y = +2.628$ m and yaw $\theta = +95.0^\circ$.
When drawn without bone evaluation:
1. Vertices remained unrotated ($\theta = 0^\circ$), blocking the doorway instead of resting swung wide against the wall ($X \approx 1.0$ m).
2. Vertices remained untranslated ($T_y = 0$), sinking 2.3 meters into the floor with only the upper 0.8 meters visible above ground (producing the waist-high "half-door" appearance).

### 26.3. Model-Space Pre-Baking Resolution
For all unskinned static objects where submeshes reference non-zero `default_bone_index`:
$$\mathbf{p}' = (\mathbf{p} \odot \mathbf{S}) \mathbf{R}^T + \mathbf{T}$$
$$\mathbf{n}' = \frac{\mathbf{n}\mathbf{R}^T}{\|\mathbf{n}\mathbf{R}^T\|}, \quad \mathbf{t}'_{:3} = \frac{\mathbf{t}_{:3}\mathbf{R}^T}{\|\mathbf{t}_{:3}\mathbf{R}^T\|}$$
1. Mesh attributes are transformed into root model space (Bone 0).
2. Submesh `default_bone_index` is set to 0.
3. Reference bone transform is reset to identity ($\mathbf{T}=\mathbf{0}, \mathbf{R}=\mathbf{I}, \mathbf{S}=\mathbf{1}$).
4. Bounding boxes are refreshed.

### 26.4. Dual-Wing Hinge Discrepancy & Bifold Model Resolution
In FromSoftware double doors (`o210011`, `o210012`, `o210013`), both door wings are stored in the local coordinate space of `default_bone_index = 1` ($T_y = +2.628$ m, $\theta = +95.0^\circ$).
Attempting manual sagittal splitting or zeroing out the bone index resulted in:
1. Sinking the door 2.3 meters into the ground ($Y \in [-2.315, 0.811]$ m), appearing as a waist-high fence.
2. Inverting the hinge pivot around $(0, 0, 0)$ instead of the hinge bone origin.

Resolution: Static workshop doors (`o210010`, `o210011`, `o210012`, `o210013`) must maintain pristine FromSoftware skeletal hierarchy and vertex bindings.

---

## 27. Universal Map & Interactive Object Fidelity Invariants

### 27.1. Map LOD1 Promotion Catastrophe & Mesh Explosion
World map pieces (`*.flver.dcx` under `map/`) must NEVER have `FS 0` replaced with `FS 1` (LOD1).
Root causes:
1. **LOD1 Topology Decoupling**: LOD1 face sets omit walkable platforms, stair ribs, and banisters, and reference simplified vertex clusters. Overwriting `FS 0` produces massive non-manifold polygon spikes (slanted monolith slabs / mesh explosions).
2. **Chunk Number Fallacy**: Assuming chunks $\ge 8000$ are "distant vista" erroneously captured playable city street chunks (e.g. `m22_00_00_00_009500`, containing Central Yharnam bonfire street, stairs, and carts) as well as 6-digit block coordinates in `m21` (`111210`..`141214`, containing the Hunter's Dream workshop and garden).
3. **Pristine Invariant**: All 3,498 map FLVERs are strictly preserved at 100% FromSoftware LOD0.

### 27.2. Interactive Ladder Rung Conservation (`o000100` and `o298010`–`o298014`)
Interactive ladders across the game (universal `o000100`, Chalice Dungeon ladders `o298010`, `o298012`, `o298014`, and world ladders `o282030`, `o323090`–`o323092`, `o326090`, `o350500`, `o350503`, `o350504`) use physical 3D cylindrical meshes for ladder rungs (not alpha cards). Standard volume-preserving QEM edge collapse modifier dissolves thin cylinders into zero-area points before touching the outer stiles, rendering rungs completely invisible.
Resolution: All 12 ladder archives are permanently whitelisted and restored to pristine vanilla.

---

## 28. World Object Armature Decoupling & Chalice Drift Root Cause (`obj/`)

### 28.1. The Oct 29 07:56 Batch Deployment Anomaly
Empirical audit of `CUSA03173-PSX/dvdroot_ps4/obj/` revealed that 1,362 out of 1,885 objects had timestamps from `Oct 29 07:56`. Only 5 files (`o210010`–`o210013` workshop doors and `o000100` ladder) were updated during commits `3227851` and `232539f`. The remaining 1,362 objects contained stale assets generated before the rigid bone-local decimation pipeline fix.

### 28.2. Multi-Bone Unskinned Model Distortion Mechanics
In FromSoftware FLVER models, rigid mechanisms (doors, chalice door statues, pillars, chandeliers) have `num_bones > 0` but `has_skin = False` (no `bone_indices` or `bone_weights` attributes in vertex arrays). Each submesh is positioned relative to its `mesh.default_bone_index`:
$$\mathbf{P}_{\text{world}} = \mathbf{M}_{\text{bone}(m.\text{default\_bone\_index})} \cdot \mathbf{P}_{\text{local}}$$

Prior to commit `3227851`, `flver_to_rigged_gltf.py` attached an `Armature` with Inverse Bind Matrices (`IBM = \mathbf{M}_{\text{bone}}^{-1}`) to ALL models with `num_bones > 0`. Blender's glTF importer applied the skin/armature binding, evaluating bone transforms during QEM decimation:
1. **Chalice Door Statues (`o290500`, `o290502`, `o290504`)**:
   - `Bone 0: statue01` ($T_x = +1.20$ m) and `Bone 1: statue02` ($T_x = -1.20$ m).
   - Mesh 0 was bound to Bone 0, causing Blender to bake a $-1.01$ m lateral displacement into vertex coordinates.
   - Result in-game: Right statue slid left across the portal opening, blocking the doorway; left statue displaced $-2.21$ m into the corridor wall.
2. **Chalice Floating Pillars & Pedestals (`o294961`, `o293721`, `o295030`, `o295230`)**:
   - Pillars with sub-bones (e.g. `gargoyle` at $T_y = +4.81$ m, `pedestal` at $T_y = -0.57$ m) suffered vertical coordinate inversion ($\Delta Y \in [+0.56\text{ m}, +4.87\text{ m}]$), suspending pillar plinths and pedestal bases in mid-air off the dungeon floor.
3. **Chalice Ladders (`o298010`–`o298014`)**:
   - Bound to `Lantern005` bone and decimated without rung protection, lifting the ladder assembly off the floor while dissolving all climbing rungs.

### 28.3. Mathematical Resolution
1. **Bone-Local Export Invariant**: When `has_skin = False`, glTF nodes must be generated WITHOUT `ArmatureSkin`, `skin.joints`, or `inverseBindMatrices`. Submesh vertices $\mathbf{P}_{\text{local}}$ are processed in identity model coordinates and written directly back into the FLVER with `default_bone_index` preserved.
2. **Pristine Whitelist Expansion**:
   - All 12 game ladders: `{"o000100", "o282030", "o298010", "o298012", "o298014", "o323090", "o323091", "o323092", "o326090", "o350500", "o350503", "o350504"}`.
   - Chalice boss door statues: `{"o290500", "o290502", "o290504"}`.
   - Interactive animated binders: `has_anibnd = True`.

---

## 29. FLVER Model-Space Bounding Box Formulation & Multi-Bone Composite Props

### 29.1. Mathematical Root Cause of Floating Statues & Invisible Chandeliers
In FromSoftware FLVER2 specifications, `mesh.bounding_box` and `flver.bounding_box` are defined in **Model / Object Root coordinates**, while vertex buffers $\mathbf{P}$ for unskinned submeshes are stored in local coordinates relative to `mesh.default_bone_index`.

When recalculating bounding boxes naively as $\text{AABB}(\min(\mathbf{P}), \max(\mathbf{P}))$:
1. Every submesh's bounding box collapses to origin $(0, 0, 0)$.
2. For multi-part composite props such as `o299600` (which combines `pedestal` at $Y = -0.10$ m, `statue` at $Y = 1.89$ m, `o294980` pillar at $X = 5.75$ m, $Z = 8.10$ m, and `candle_stand001` at $Y = 5.00$ m, $X = 5.16$ m):
   - The engine camera frustum culler checks visibility against the collapsed $(0, 0, 0)$ bounding box.
   - When viewing the statue or pillar in-game, the pedestal bounding box falls outside the frustum or fails occlusion queries, culling the pedestal and leaving the statue floating in mid-air.
   - The candle stand bounding box is evaluated at $(0, 0, 0)$ instead of $Y = 5.0$ m, causing the engine to draw the candle bracket intersecting inside the statue body.
3. For corridor hanging chandeliers (`o295370`), Bone 0 is translated by $Z = +25.0$ m, $Y = +3.5$ m across a 25-meter corridor span $[0.13, 25.85]$ m. Collapsing the bounding box to $[-0.96, 0.93]$ m causes the entire chandelier row to be culled by the engine as soon as the camera advances into the corridor.

### 29.2. Exact Bone Hierarchy Accumulation Formula
To correctly refresh bounding boxes for any FLVER without breaking FromSoftware spatial culling:
$$\mathbf{M}_i = \begin{cases} \mathbf{M}_{\text{local}, i} & \text{if } \text{parent}(i) = -1 \\ \mathbf{M}_{\text{parent}(i)} \cdot \mathbf{M}_{\text{local}, i} & \text{otherwise} \end{cases}$$
where $\mathbf{M}_{\text{local}, i} = \begin{bmatrix} \mathbf{R}_i \cdot \mathbf{S}_i & \mathbf{T}_i \\ \mathbf{0} & 1 \end{bmatrix}$ with FromSoftware Euler convention $\text{XZY}$.

For each submesh $m$:
$$\mathbf{P}_{\text{world}} = \begin{cases} \mathbf{P}_{\text{local}} & \text{if mesh has } \texttt{bone\_indices} \\ \mathbf{P}_{\text{local}} \cdot \mathbf{R}_{\text{world}, \text{def\_bone}}^T + \mathbf{T}_{\text{world}, \text{def\_bone}} & \text{if unskinned rigid} \end{cases}$$
$$\text{mesh.bounding\_box} = \text{AABB}(\min(\mathbf{P}_{\text{world}}), \max(\mathbf{P}_{\text{world}}))$$
$$\text{flver.bounding\_box} = \text{AABB}\left(\min_m(\text{mesh.bounding\_box.min}), \max_m(\text{mesh.bounding\_box.max})\right)$$

This formulation achieves $\Delta = 0.000000$ m exact match with FromSoftware retail binary layouts.

### 29.3. Thin Chain Edge-Collapse & Pristine Bypass
Blender COLLAPSE decimation at $0.25$ ratio collapses thin vertical chain links (`m29_00_chain_400`) upward by $+2.09$ m ($Y \in [-3.76, -0.50] \to [-1.67, -0.50]$ m).
All multi-bone composite props, hanging chandeliers, candlestick statues, and cage elevators are strictly whitelisted for pristine vanilla bypass:
- Multi-bone room assemblies: `o2996*`, `o2949*`, `o2994*`, `o2999*`.
- Corridor chandeliers: `o2953*`, `o2950*`, `o2951*`, `o2952*`, `o2956*`, `o2961*`.
- Candlestick and lantern statues: `o2973*`, `o2974*`, `o2937*`, `o2905*`, `o2911*`.
- Mechanical cage elevators and pulleys: `o2902*`, `o2903*`, `o2904*`.

### 29.4. Chalice Ladder ("Escalera de Mano") Lantern & Base Offset Discrepancy
Interactive wooden ladders in Chalice dungeons (`o2980*`, `o2981*`, `o2982*`) contain interactive climbing dummies ($191$ bottom mount, $192$ top mount, $193$ bottom dismount, $194$ top dismount, $195$ center) and child attachment bones (`lower_Lantern003` in `o298000`, `lower_Lantern1` in `o298100`, dummy $703$).
When subjected to Blender geometry decimation:
1. `o298000`: Vanilla AABB $Y \in [-0.091, 8.119]$ m $\to$ PSX AABB $Y \in [-0.779, 8.121]$ m ($\Delta Y_{\min} = -0.6881$ m).
2. `o298100`: Vanilla AABB $Y \in [-0.241, 7.119]$ m $\to$ PSX AABB $Y \in [-0.765, 8.121]$ m ($\Delta Y_{\min} = -0.5236$ m, $\Delta Y_{\max} = +1.0020$ m).
3. The lantern mesh offset and collapsed 3D cylinder rungs shifted the object bounding box and visual ladder stiles, causing the ladder base to hover $\sim 0.6$ m off the ground plane and dislodging the lantern to the left.

Resolution:
All Chalice ladder archives (`o298000`–`o298214`, 15 archives) along with all interactive ladder rigs across the entire game are whitelisted for pristine FromSoftware geometry bypass in `batch_blender_demake_obj.py`. Deployed archives match retail binary geometry with $\Delta = 0.000000$ m parity.

---

## 33. Empirical Performance Benchmarks & Dual-Bottleneck Architecture (GTX 1650 Max-Q)

Empirical telemetry conducted on target hardware (`NVIDIA GeForce GTX 1650 with Max-Q Design`, 4GB VRAM, Linux 6.x Vulkan driver).

### Telemetry Matrix

| Test Case | Resolution & Preset | Asset Stage | Zone Tested | VRAM Usage (`bb-probe`) | Framerate | Impact vs Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A (Vanilla Baseline)** | 1680x1050 Balanced (P2) | Retail `CUSA03173` | Hunter's Dream / Chalice | **2,449 MiB** | **22–27 FPS** | *Retail Baseline* |
| **B (Shaders Only)** | 1680x1050 Balanced (P2) | Retail `CUSA03173` | Hunter's Dream / Chalice | **2,449 MiB** | **40–50 FPS** | **+80% to +100% FPS** (ALU Relief) |
| **C (Demake Mod 1050p)** | 1680x1050 Balanced (P2) | `mods/Bloodborne PSX Demake/` | Hunter's Dream / Chalice | **2,083 MiB** | **55–60 FPS (up to 80)** | **-366 MiB VRAM, +140% FPS** |
| **D (Heavy Area P2)** | 1680x1050 Balanced (P2) | `mods/Bloodborne PSX Demake/` | The Great Bridge (`m21`) | **2,385 MiB** | **~55 FPS** | Outdoor Dense Scene Base |
| **E (Heavy Area P3)** | 1680x1050 Performance (P3) | `mods/Bloodborne PSX Demake/` | The Great Bridge (`m21`) | **2,244 MiB** | **~65 FPS** | **-141 MiB** (G-Buffer Scale) |
| **F (Heavy Area 800p)** | 1280x800 Performance (P3) | `mods/Bloodborne PSX Demake/` | The Great Bridge (`m21`) | **2,155 MiB** | **~75 FPS** | **-230 MiB vs D** |
| **G (Chalice 800p Active)** | 1280x800 Performance (P3) | `mods/Bloodborne PSX Demake/` | Chalice Dungeon (Active) | **2,060 MiB** | **80–90 FPS** | Consistent High-FPS Floor |
| **H (Chalice 800p Cold)** | 1280x800 Performance (P3) | `mods/Bloodborne PSX Demake/` | Chalice Dungeon (Cold Boot) | **2,127 MiB** | **80–90 FPS** | Initial Pipeline Allocations |
| **I (Sub-2GiB Breakthrough)** | 1280x800 Performance (P3) | `mods/Bloodborne PSX Demake/` | Hunter's Dream | **1,952 MiB** | **80–90 FPS** | **Sub-2GiB Verified (< 2,048 MiB)** |

### Dual Bottleneck Diagnosis

1. **ALU / Fillrate Bottleneck (Shaders & Deferred Lighting Engine)**:
   - *Test A $\to$ Test B*: With identical vanilla geometry and textures (VRAM static at 2,449 MiB), FPS leaps from 22–27 to 40–50 FPS.
   - *Root Cause*: Bloodborne's native deferred lighting evaluates per-light dynamic shadow maps (`effect_dynamic_shadows`), depth of field blur passes (`effect_dof`), and bloom post-processing.
   - *PSX Shader Optimizations*:
     - `effect_dynamic_shadows=0` in `bbport.ini` eliminates heavy multi-tap shadow projection compute.
     - `psx_point_filter=1` in `gpu/textures/sampler.cpp` disables anisotropic filtering (`anisotropyEnable = false`) and enforces `Nearest` filtering, radically reducing TMU cache miss penalties.
     - `psx_affine=1` in `gpu/shader/backend/spirv/spirv_emit_context.cpp` annotates interpolators with `spv::Decoration::NoPerspective`, removing per-pixel perspective division ($1/w$) during rasterization.

2. **Geometry & Memory Bandwidth Bottleneck (Front-End & VRAM)**:
   - *Test B $\to$ Test C*: Retaining the PSX shader profile while mounting the 2,670 decimated mod assets (`mods/Bloodborne PSX Demake/`) drops VRAM from 2,449 MiB to 2,083 MiB ($\Delta = -366\text{ MiB}$) and lifts framerate from 40–50 FPS to 55–60 FPS in dense dungeons (and up to 80 FPS in open zones).
   - *Root Cause*: High-poly retail meshes (50k–100k triangles per character/boss) cause catastrophic sub-pixel triangle rasterization and vertex shader invocation bottlenecks on low-spec GPUs.
   - *Decimation & Downscale Impact*: Low-poly geometry combined with $128\times 128$ / $256\times 256$ BC3/BC7 textures reduces bus transfer bandwidth and eliminates front-end primitive assembly stalls.























