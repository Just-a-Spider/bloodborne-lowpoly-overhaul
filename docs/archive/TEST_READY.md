# Test Suite Ready: Plain Doll (c8030) retro Head Reconstruction & Redesign

**Status**: READY TO EXECUTE  
**Timestamp**: 2026-10-19T11:45:00Z  
**Author**: Test Writer (`test_writer_doll_2`)

---

## 1. Test Harness Overview
The authoritative 4-tier E2E acceptance test suite for the Plain Doll (`c8030.chrbnd.dcx`) retro demake redesign is authored, validated, and ready for worker verification and regression prevention.

- **Test Suite Location**: `tools/archive/verify_c8030_doll.py`
- **Execution Command**: `uv run python tools/verify_c8030_doll.py`
- **CLI Options**: `--tier <1-4>`, `--json`, `--fast`, `--exit-zero`

---

## 2. Test Coverage Matrix

| Tier | Test ID | Description | Target Specification | Current PSX Asset Status |
|------|---------|-------------|----------------------|--------------------------|
| **1** | T1.1 | Facial Skin Polygon Budget | Redesign R1 (600–800 tris) | **FAIL** (314 total head tris, 274 at Y > 1.80) |
| **1** | T1.2 | Degenerate Face Filter | Invariant 6 (Area >= 1e-6) | **PASS** (0 zero-area, 0 duplicate faces) |
| **1** | T1.3 | Needle Sliver Filter | Invariant 6, AC1 (Aspect <= 25.0) | **PASS** (0 slivers > 25.0:1) |
| **1** | T1.4 | Manifold Topology & Boundary Seams | Redesign R1 (0 tears, 0 non-manifold) | **PASS** (0 non-manifold edges, clean neck seam) |
| **1** | T1.5 | Bonnet Clearance & Penetration Check | Redesign R1 (>=2.0mm, 0 penetrating) | **FAIL** (25 penetrating triangle pairs) |
| **2** | T2.1 | Bone Weight Normalization | Redesign R2 (sum 1.0, byte sum 255) | **PASS** (100% normalized) |
| **2** | T2.2 | Bone Index Validity | Redesign R2 (indices [0, 205], cranial skeleton) | **PASS** (100% valid indices) |
| **2** | T2.3 | Auxiliary FaceSet Synchronicity | Redesign R2 (FS1..FS5 == FS0) | **PASS** (Rigid meshes synchronized) |
| **2** | T2.4 | Bounding Box Invariant | Redesign R2 (exact extrema / vanilla cloth) | **PASS** (Exact extrema & vanilla cloth bounds) |
| **3** | T3.1 | 15-Bit RGB555 Diffuse Quantization | Redesign R3 (step 8, 32 levels, [0, 248]) | **PASS** (15-bit RGB555 palette on skin) |
| **3** | T3.2 | Texture Format & Normal Invariant | Redesign R3 (BC5 0x6c, BC7 hair, BC1 lace) | **PASS** (Formats preserved) |
| **3** | T3.3 | Diffuse UV Feature Alignment | Redesign R1, R2 (UV jumps < 0.3) | **PASS** (Clean UV mapping) |
| **4** | T4.1 | Pristine CUSA03173 Immutability Audit | Redesign R4 (SHA-256 match) | **PASS** (b76532...44f exact match) |
| **4** | T4.2 | Fallback Backup Verification | Redesign R4 (c8030.chrbnd.dcx.bak) | **PASS** (Valid 5-entry container) |
| **4** | T4.3 | Havok Cloth Physics Integrity | Redesign R4 (Meshes 0,1,2,10,11 & sim files) | **PASS** (100% byte & mesh match) |

---

## 3. Current Baseline Audit Summary

Execution on current pre-redesign asset:
```
SUMMARY: 15 Tests | 13 Passed | 2 Failed | 0 Skipped | 0 Errors
```

The test runner cleanly and accurately isolates the exact 2 structural defects that the Plain Doll redesign is scheduled to fix:
1. `T1.1`: Head polygon count is 314 (Y > 1.80 is 274), which is below the new 600-800 triangle budget required for facial likeness restoration.
2. `T1.5`: Bonnet brim penetration check detected 25 penetrating triangle pairs against the bonnet (strict acceptance criteria mandates 0 penetrating pairs and >= 2.0mm clearance).

---

## 4. How to Run

```bash
# Full test suite execution
uv run python tools/verify_c8030_doll.py

# Specific tier execution
uv run python tools/verify_c8030_doll.py --tier 1
uv run python tools/verify_c8030_doll.py --tier 2
uv run python tools/verify_c8030_doll.py --tier 3
uv run python tools/verify_c8030_doll.py --tier 4

# Fast smoke check
uv run python tools/verify_c8030_doll.py --fast

# Machine-readable JSON output
uv run python tools/verify_c8030_doll.py --json

# Non-blocking inspection
uv run python tools/verify_c8030_doll.py --exit-zero
```
