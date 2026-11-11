# Contributor & Collaboration Standards

This document establishes the technical invariants, git conventions, and verification gates required for contributing to *Bloodborne: Low-Poly Overhaul*.

---

## 1. Technical Invariants & Rules

### Rule S1: Generic Pathing & No Runner Coupling
- Tooling and scripts must never assume or hardcode third-party runner directories or project names.
- All reconstructors and generators must require explicit destination paths (`--out`) and contain no defaulting to ambient engine folders.

### Rule S2: Pure Mod Scope
- The repository scope is strictly bounded to FromSoftware game assets (`dvdroot_ps4/`), patch packaging, and standalone reconstruction.
- Engine plugin implementations, Vulkan hook shaders, and launcher integrations are developed in separate reference directories.

### Rule S3: Workspace Hygiene
- Temporary build and test outputs (`mods/`, `.bak` files, uncompressed assets) must never be committed to git.
- The `dist/` directory holds generated `.patch` containers (ignored by git), `apply_patch.py`, `SHA256SUMS.txt`, and `RELEASE_NOTES.md`.

---

## 2. FLVER Mesh & Rigging Standards

Every modified FLVER model must satisfy the following mathematical and architectural constraints:

1. **Submesh Order Preservation**: FLVER submesh slot indices must strictly mirror the vanilla model. Reordering submeshes causes material misassignment in the engine.
2. **Normal & Tangent Frame Alignment**:
   - Tangents must be computed using `tdir + det_UV` handedness to match FromSoftware's coordinate system.
   - Normal vectors must maintain sagittal midline symmetry ($x \leftrightarrow -x$) across character faces and torsos to prevent asymmetric lighting seams.
3. **Bone Weight Normalization**:
   - Exactly 4 bone indices and 4 weights per vertex.
   - Vertex bone weights must sum to `1.0` ($\sum w_i = 1.0$).
4. **Havok Dynamic Cloth Invariants**:
   - In the **Cloth Physics Edition**, meshes bound to Havok cloth bones (capes, skirts, coats) must retain their cloth vertex groups and parent bone bindings. Decimating cloth vertices without preserving anchor weights leads to cloth solver explosions.
   - In the **Flat Stiff Edition**, cloth bones are collapsed and reparented directly to skeletal hierarchy bones (e.g., spine/hips) with hard-split facet normals.

---

## 3. Pull Request Audit Gates

Before submitting a Pull Request, run the automated verification suite:

```bash
# 1. Unit test suite
uv run pytest

# 2. Reconstructor CLI integrity
python3 apply_patch.py --help

# 3. Checksum verification
cd dist && sha256sum -c SHA256SUMS.txt
```

All PRs modifying pipeline tools must verify that retail vanilla `CUSA03173` is never mutated or written to.
