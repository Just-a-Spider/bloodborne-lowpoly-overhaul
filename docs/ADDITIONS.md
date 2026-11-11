# Asset Additions & Demaking Workflow

This document defines the canonical process for authoring, demaking, and injecting new 3D models and textures into the *Bloodborne: Low-Poly Overhaul* project.

---

## 1. Architecture Overview

The demake pipeline processes four primary asset classes:
1. **Characters & Enemies (`chr/`)**: Multi-bone rigged FLVER containers (`cXXXX.anibnd.dcx` / `cXXXX.chrbnd.dcx`).
2. **Player Attire & Weapons (`parts/`)**: Skeletal equipment FLVER containers (`am_*.partsbnd.dcx`, `wp_*.partsbnd.dcx`).
3. **Interactive Objects & Props (`obj/`)**: Physics and animated map objects (`oXXXX.objbnd.dcx`).
4. **World Textures & Maps (`map/`)**: BXF split containers and TPF texture binders.

---

## 2. Model Demaking Pipeline

All mesh decimation and normal processing run headlessly via Blender 5.x.

### 2.1 Rigged Characters and Equipment
1. **Extract Vanilla FLVER**: Unpack target DCX container using Soulstruct.
2. **Convert to glTF**:
   ```bash
   uv run python tools/pipeline/flver_to_rigged_gltf.py <input.flver> <intermediate.gltf>
   ```
3. **Headless Blender Decimation**:
   Execute decimation with planar collapse and vertex snap:
   ```bash
   blender -b --python tools/pipeline/blender_process_parts.py -- <intermediate.gltf> <decimated.gltf> <ratio>
   ```
4. **Convert Back to FLVER**:
   ```bash
   uv run python tools/pipeline/rigged_gltf_to_flver.py <decimated.gltf> <output.flver> --reference <input.flver>
   ```
   *Note: Submesh material IDs, bone weights, and Havok cloth bindings must match the reference FLVER.*

### 2.2 Interactive Objects
Objects with animated transforms (elevators, swinging lamps, gates) require bone-preserving transforms:
```bash
uv run python tools/pipeline/batch_blender_demake_obj.py --input-dir /path/to/vanilla/obj --output-dir /path/to/mod/obj
```
- Multi-bone Lecture Building (`m32`) props and levers are protected by explicit whitelist in `batch_blender_demake_obj.py`.

---

## 3. Retro Texture Processing

Textures are quantized to authentic 15-bit RGB555 palettes with 4x4 Bayer dithering:
- **Albedos**: Downscaled to 128x128 or 256x256, uncompressed BC1 / DXT1.
- **Normal Maps**: Neutralized to flat `(128, 128, 255)` to strip modern micro-wrinkles while preserving low-poly facet edges.
- **Specular / Gloss**: Zeroed to eliminate oily PBR shine.

Batch script:
```bash
uv run python tools/pipeline/demake_parts_textures.py --input-dir /path/to/vanilla/parts --output-dir /path/to/mod/parts
```

---

## 4. Quality & Rigging Invariants Checklist
- [ ] Decimated vertex count <= 25% of vanilla baseline.
- [ ] FLVER submesh ordering matches original vanilla slot indexing.
- [ ] Normal/tangent frame calculation uses `tdir + det_UV` handedness.
- [ ] Bone weight sum per vertex equals 1.0 (normalized across 4 bone slots).
- [ ] Sagittal midline symmetry preserved on character faces and chests.
