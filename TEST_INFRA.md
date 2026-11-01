# Test Infrastructure: Plain Doll (c8030) retro Head Reconstruction

## 1. Overview
The acceptance testing infrastructure provides automated, multi-tiered end-to-end verification for the Plain Doll (`c8030.chrbnd.dcx`) PlayStation 1 low-poly head reconstruction. It verifies geometric topology, skeletal rigging, engine bounds, texture quantization, format invariants, and baseline container safety.

- **Test Suite Location**: `tools/archive/verify_c8030_doll.py`
- **Execution Command**: `uv run python tools/verify_c8030_doll.py`
- **Integrity Mode**: Benchmark
- **Environment**: Linux x86-64, Python 3.13 (`uv run`), Soulstruct 2.6.0, NumPy, SciPy (`cKDTree`), Pillow.

---

## 2. Test Architecture & 4-Tier Hierarchy

The suite is structured into 4 distinct verification tiers comprising 15 automated checks:

```
tools/verify_c8030_doll.py
├── Tier 1: Geometric Topology & Polygon Budget (T1.1 - T1.5)
│   ├── T1.1: Facial Skin Polygon Budget (Mesh 7 head in [250, 450] triangles)
│   ├── T1.2: Degenerate Face Filter (Zero-area < 1e-6 & duplicate index faces == 0)
│   ├── T1.3: Needle Sliver Filter (Max inradius/circumradius aspect ratio <= 25.0)
│   ├── T1.4: Manifold Topology & Boundary Seam Check (Non-manifold edges == 0, zero open tears)
│   └── T1.5: Inter-Mesh Clearance & Penetration Check (Bonnet Mesh 4 vs Face Skin Mesh 7)
├── Tier 2: Skeletal Rigging & Engine Bounds (T2.1 - T2.4)
│   ├── T2.1: Bone Weight Normalization (100% verts sum == 1.0 within 1e-3, byte sum == 255)
│   ├── T2.2: Bone Index Validity (All indices in [0, 205], head bound to Bones 4, 5, 6..)
│   ├── T2.3: Auxiliary FaceSet Synchronicity (FS1..FS5 == FS0.copy() across all modified meshes)
│   └── T2.4: Bounding Box Invariant (Rigid meshes exact extrema; cloth meshes byte-identical to vanilla)
├── Tier 3: Shading & Texture Integrity (T3.1 - T3.3)
│   ├── T3.1: 15-Bit RGB555 Diffuse Quantization (c8030_skin_a multiples of 8, [0, 248], 32 levels)
│   ├── T3.2: Texture Format & Normal Invariant (c8030_skin_n BC5 fmt 0x6c preserved, no BC1 overwrite)
│   └── T3.3: Diffuse UV Feature Alignment (Facial UVs mapped to anatomical skin chart, zero NaNs, UV jumps < 0.3)
└── Tier 4: Container Safety & Baseline Immutability (T4.1 - T4.3)
    ├── T4.1: Pristine CUSA03173 Immutability Audit (Byte-for-byte SHA-256 match)
    ├── T4.2: Fallback Backup Verification (c8030.chrbnd.dcx.bak exists and is valid readable container)
    └── T4.3: Havok Cloth Physics Integrity (Meshes 0, 1, 2, 10, 11 and _c.hkx, _c.clm2 identical)
```

---

## 3. Tier Specifications & Mathematical Methodology

### Tier 1: Geometric Topology & Polygon Budget
- **T1.1 (Facial Skin Polygon Budget)**:
  - *Target*: Mesh 7 head region ($Y > 1.60\text{m}$).
  - *Constraint*: Authentic retro budget $250 \le N_{\text{head\_tris}} \le 450$.
  - *Rationale*: Eliminates high-poly GPU pipeline stalls while retaining 90s facial silhouette.
- **T1.2 (Degenerate Face Filter)**:
  - *Formula*: Triangle area $A = \frac{1}{2} \|(\mathbf{v}_1 - \mathbf{v}_0) \times (\mathbf{v}_2 - \mathbf{v}_0)\|$.
  - *Threshold*: Zero-area faces ($A < 10^{-6}$), internal duplicate indices within a face ($f_0 == f_1$, etc.), and duplicate face pairs must equal 0.
- **T1.3 (Needle Sliver Filter)**:
  - *Formula*: Edge lengths $e_1, e_2, e_3$, semi-perimeter $s = \frac{e_1 + e_2 + e_3}{2}$. Inradius $r_{\text{in}} = A / s$, circumradius $r_{\text{out}} = \frac{e_1 e_2 e_3}{4 A}$. Aspect ratio $\rho = \frac{r_{\text{out}}}{2 r_{\text{in}}} = \frac{e_1 e_2 e_3 s}{8 A^2}$.
  - *Threshold*: $\max(\rho) \le 25.0$.
  - *Rationale*: Prevents rasterizer micro-pixel spikes, tangent space degeneration, and normal flicker.
- **T1.4 (Manifold Topology & Boundary Seams)**:
  - *Internal Edges*: Shared by exactly 2 faces.
  - *Boundary Edges*: Shared by exactly 1 face. Must strictly lie along neck transition seam ($Y \le 1.82\text{m}$).
  - *Non-Manifold Edges*: Shared by $>2$ faces must equal 0.
  - *Open Surface Tears*: Boundary edges with $Y > 1.82\text{m}$ must equal 0.
- **T1.5 (Bonnet Clearance & Inter-Mesh Penetration)**:
  - *Clearance*: Spatial distance between Mesh 7 head vertices and Bonnet (`Mesh 4: HD_F_7000_01`) via KDTree must satisfy $\min(\text{distance}) \ge 0.0020\text{m}$ (2.0mm).
  - *Penetration*: Triangle-triangle Möller edge piercing check across overlapping AABB candidate pairs must find 0 intersecting pairs.

### Tier 2: Skeletal Rigging & Engine Bounds
- **T2.1 (Bone Weight Normalization)**:
  - *Partition of Unity*: Every head vertex must satisfy $|\sum_{j=1}^4 w_j - 1.0| < 0.001$.
  - *Byte Packing Invariant*: In FLVER binary format (`FourBytesC`), $\sum_{j=1}^4 \text{byte}_j == 255$ to eliminate coordinate accordion stretching.
- **T2.2 (Bone Index Validity)**:
  - *Global Range*: All indices $b_{i,j} \in [0, 205]$.
  - *Cranial Rigging*: Head vertices must be weighted exclusively to the cranial/neck skeleton (Bones 4, 5, 6, 7..12, and neck base 3, 13, 40). Zero weighting to hand/leg/body bones.
- **T2.3 (FaceSet Synchronicity)**:
  - *Requirement*: For all modified rigid meshes, auxiliary FaceSets must be synchronized:
    $$\forall k \in [1, 5]: \quad \text{FS}_k.\text{vertex\_indices} = \text{FS}_0.\text{vertex\_indices}.\text{copy}()$$
  - *Rationale*: Prevents LOD and shadow pass GPU segmentation faults and camera angle occlusion culling drops.
- **T2.4 (Bounding Box Invariant)**:
  - *Rigid Meshes (3, 4, 5, 6, 7, 8, 9, 12)*: Exact vertex extrema $[\min \mathbf{v}, \max \mathbf{v}]$ with zero artificial padding.
  - *Cloth Meshes (0, 1, 2, 10, 11)*: Retain exact vanilla dynamic bounding boxes.

### Tier 3: Shading & Texture Integrity
- **T3.1 (15-Bit RGB555 Diffuse Quantization)**:
  - *Target*: `c8030_skin_a` diffuse texture inside `c8030.tpf`.
  - *Formula*: $(C \gg 3) \ll 3$ produces 32 discrete color levels in steps of 8, bounded in $[0, 248]$.
  - *Requirement*: 100% of texels must be multiples of 8, dynamic range $[0, 248]$, $\le 32$ discrete levels per channel.
- **T3.2 (Texture Format & Normal Invariant)**:
  - *Normal Map*: `c8030_skin_n` format must equal `0x6c` (BC5, 16 bytes/block). BC1 (`0x00`/`0x01`) overwrite strictly prohibited.
  - *Hair Alpha*: `c8030_HR_a` format must equal `0x66` (BC7 alpha cutout preserved).
  - *Dress Lace*: `c8030_BD_a` format must equal `0x01` (BC1 1-bit alpha preserved).
- **T3.3 (Diffuse UV Feature Alignment)**:
  - *Coordinates*: Range bounded within $[0.0, 1.0]$ with zero NaNs and zero Infs.
  - *Seam Stretching*: Maximum edge length in UV space across any head triangle must satisfy $\Delta \text{UV} < 0.30$.

### Tier 4: Container Safety & Baseline Immutability
- **T4.1 (Pristine CUSA03173 Immutability)**:
  - *Reference Container*: `CUSA03173/dvdroot_ps4/chr/c8030.chrbnd.dcx`.
  - *Target Hash*: SHA-256 `b76532a7bf75a762e426562e803440e1ff275e2ee5c8789ddb9208cf27e5944f` (12,449,615 bytes).
  - *Requirement*: 100% byte-for-byte immutability.
- **T4.2 (Fallback Backup Verification)**:
  - *File*: `CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx.bak`.
  - *Requirement*: Must exist and be readable as a valid Soulstruct `Binder` containing all 5 required container files (`c8030.tpf`, `c8030.flver`, `c8030.HKX`, `c8030_c.hkx`, `c8030_c.clm2`).
- **T4.3 (Havok Cloth Physics Integrity)**:
  - *Simulation Files*: `c8030_c.hkx` and `c8030_c.clm2` must match vanilla byte-for-byte.
  - *Cloth Submeshes*: Meshes 0, 1, 2, 10, 11 must retain identical vertex positions and face sets to vanilla.

---

## 4. Invocation & Usage

All commands must be executed using `uv run python` from repository root:

```bash
# Full test suite execution (15 tests across 4 tiers)
uv run python tools/verify_c8030_doll.py

# Tier-specific execution
uv run python tools/verify_c8030_doll.py --tier 1
uv run python tools/verify_c8030_doll.py --tier 2
uv run python tools/verify_c8030_doll.py --tier 3
uv run python tools/verify_c8030_doll.py --tier 4

# Fast smoke execution (sampling mode for fast feedback)
uv run python tools/verify_c8030_doll.py --fast

# Machine-readable JSON output
uv run python tools/verify_c8030_doll.py --json

# Non-blocking inspect mode (returns exit code 0 even on test failure)
uv run python tools/verify_c8030_doll.py --exit-zero
```

---

## 5. Pass/Fail Semantics & Exit Codes

- **Exit Code `0`**: All executed tests returned `PASS`.
- **Exit Code `1`**: One or more tests returned `FAIL` or `ERROR`.
- **Exit Code `0` with `--exit-zero`**: Diagnostic inspection mode.

Status Definitions:
- `[PASS]`: Criterion strictly satisfied according to authoritative specification.
- `[FAIL]`: Specification violation detected; detailed diagnostic output printed with counts, values, and deltas.
- `[SKIP]`: Optional dependency or target resource missing in test environment.
- `[ERROR]`: Fatal exception during test execution.

---

## 6. Current Baseline Defect Audit (Initial Run)

Execution against the pre-reconstruction PSX model (`CUSA03173-PSX/dvdroot_ps4/chr/c8030.chrbnd.dcx`):

```
SUMMARY: 15 Tests | 7 Passed | 8 Failed | 0 Skipped | 0 Errors
```

### Verified Failure Modes Flagged:
1. `T1.1`: Head triangle count is 1,426 (317% above [250, 450] budget).
2. `T1.2`: 17 zero-area triangles ($A < 10^{-6}$) and 1 duplicate face.
3. `T1.3`: 21 needle sliver triangles (max aspect ratio 240.43:1 > 25.0:1).
4. `T1.4`: 1 non-manifold edge defect detected.
5. `T1.5`: Bonnet clearance is 0.621mm (< 2.0mm) and 47 penetrating triangle pairs.
6. `T2.1`: 357/1,065 head vertices violate float sum 1.0 and byte sum 255.
7. `T3.1`: Diffuse texture `c8030_skin_a` has non-multiple-of-8 values (39 levels).
8. `T3.3`: 332 triangles exhibit severe UV seam stretching (max jump 1.0038 > 0.30).

All 7 safety invariants (T2.2, T2.3, T2.4, T3.2, T4.1, T4.2, T4.3) pass cleanly.
