# Modding Pipeline & Build Guide

This document details the end-to-end pipeline for authoring assets, rebuilding from scratch, and packaging distribution patches for *Bloodborne: Low-Poly Overhaul*.

---

## 1. Prerequisites

- Python >= 3.12 managed via `uv`.
- Blender >= 4.2 / 5.x installed and accessible in system `$PATH`.
- System libraries: `libgomp`, `openmp`.
- Clean retail dump of *Bloodborne* v1.09 at `/path/to/CUSA03173` (containing `dvdroot_ps4/`).

---

## 2. Asset Authoring & Demaking

All mesh decimation and normal processing run headlessly via Blender.

### 2.1 Rigged Characters and Equipment
1. **Extract Vanilla FLVER**: Unpack target DCX container using Soulstruct.
2. **Convert to glTF**:
   ```bash
   uv run python tools/pipeline/flver_to_rigged_gltf.py <input.flver> <intermediate.gltf>
   ```
3. **Headless Blender Decimation**:
   Execute planar collapse and vertex snapping:
   ```bash
   blender -b --python tools/pipeline/blender_process_parts.py -- <intermediate.gltf> <decimated.gltf> <ratio>
   ```
4. **Convert Back to FLVER**:
   ```bash
   uv run python tools/pipeline/rigged_gltf_to_flver.py <decimated.gltf> <output.flver> --reference <input.flver>
   ```
   *Note: Submesh material IDs, bone weights, and Havok cloth bindings must match the reference FLVER.*

### 2.2 Interactive Objects & Props
Objects with animated transforms (elevators, swinging lamps, gates) require bone-preserving transforms:
```bash
uv run python tools/pipeline/batch_blender_demake_obj.py --input-dir /path/to/vanilla/obj --output-dir /path/to/mod/obj
```
*Multi-bone Lecture Building (`m32`) props and levers are protected by explicit whitelist.*

### 2.3 Retro Texture Processing
Textures are quantized to authentic 15-bit RGB555 palettes with 4x4 Bayer dithering:
- **Albedos**: Downscaled to 128x128 or 256x256, uncompressed BC1 / DXT1.
- **Normal Maps**: Neutralized to flat `(128, 128, 255)` to strip modern micro-wrinkles while preserving facet edges.
- **Specular / Gloss**: Zeroed to eliminate oily PBR shine.

```bash
uv run python tools/pipeline/demake_parts_textures.py --input-dir /path/to/vanilla/parts --output-dir /path/to/mod/parts
```

---

## 3. Rebuilding From Scratch

To reconstruct all transformed assets algorithmically from clean vanilla game files:

```bash
uv run python tools/pipeline/build_from_scratch.py \
    --game /path/to/CUSA03173 \
    --out-dir /path/to/output_mod \
    --workers 12
```

### Execution Order:
1. **Map Textures**: Top-mip bitstream slicing on `dvdroot_ps4/map/*.tpf.dcx` and `*.bxf` binders.
2. **Interactive Objects**: Blender mesh decimation on `dvdroot_ps4/obj/*.objbnd.dcx`.
3. **Player Armors & Weapons**: Blender rigged decimation and normal quantization on `dvdroot_ps4/parts/*.partsbnd.dcx`.
4. **Characters & Enemies**: Manifold edge collapse decimation on `dvdroot_ps4/chr/*.chrbnd.dcx`.
5. **HUD & UI**: Scaleform pixelation filter across `dvdroot_ps4/menu/*.gfx` and font textures.

---

## 4. Packaging Differential Patches

All mod distribution packages use zero-dependency byte-level XOR delta streaming against pristine retail `CUSA03173/dvdroot_ps4/`. Never redistribute raw FromSoftware assets.

### Generate All 5 Modular Pillars:
```bash
uv run python tools/pipeline/package_modular_mods.py \
    --vanilla /path/to/CUSA03173 \
    --dist-dir dist/ \
    --workers 12
```

### Generate a Single Component Patch:
```bash
uv run python tools/pipeline/create_patch.py \
    --vanilla /path/to/CUSA03173 \
    --mod /path/to/mod_folder \
    --output dist/bloodborne_custom_component.patch \
    --workers 12
```

### Checksums & Manifest:
```bash
cd dist && sha256sum *.patch apply_patch.py > SHA256SUMS.txt
sha256sum -c SHA256SUMS.txt
```

---

## 5. Quality & Audit Gates

Verify the mod directory against corruption and topology regressions:

```bash
uv run python tools/pipeline/run_adversarial_audit.py --mod-dir /path/to/reconstructed_mod
uv run python tools/pipeline/modular_structure_validator.py --mods-dir mods
uv run pytest
```
