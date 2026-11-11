# Asset Recreation Guide

This guide details how to reproduce, build, and verify the *Bloodborne: Low-Poly Overhaul* assets from clean retail vanilla *Bloodborne* v1.09 (`CUSA03173`).

---

## 1. Prerequisites

- Python >= 3.13 with `uv` package manager.
- Blender >= 4.2 / 5.x installed and accessible in `$PATH`.
- Clean, unmodified retail dump of *Bloodborne* v1.09 at `/path/to/CUSA03173` (containing `dvdroot_ps4/`).

---

## 2. Rebuilding From Scratch Pipeline

To reconstruct all transformed assets algorithmically from vanilla game files:

```bash
uv run python tools/pipeline/build_from_scratch.py \
    --game /path/to/CUSA03173 \
    --out-dir /path/to/output_mod \
    --workers 12
```

### Pipeline Execution Order:
1. **Map Textures**: Top-mip bitstream slicing on `dvdroot_ps4/map/*.tpf.dcx` and `*.bxf` binders.
2. **Interactive Objects**: Blender mesh decimation on `dvdroot_ps4/obj/*.objbnd.dcx` (protecting multi-bone elevator rigs).
3. **Player Armors & Weapons**: Blender rigged decimation and normal quantization on `dvdroot_ps4/parts/*.partsbnd.dcx`.
4. **Characters & Enemies**: Manifold edge collapse decimation on `dvdroot_ps4/chr/*.chrbnd.dcx` and `c8030` Plain Doll.
5. **HUD & UI**: Scaleform pixelation filter across `dvdroot_ps4/menu/*.gfx` and font textures.

---

## 3. Applying Pre-built Differential Patches

If you have downloaded release `.patch` containers, reconstruction requires only standard Python with **zero external dependencies**:

### Reconstruct Individual Pillar:
```bash
python3 apply_patch.py \
    --game /path/to/CUSA03173 \
    --patch dist/bloodborne_retro_hud.patch \
    --out /path/to/mods/bloodborne_retro_hud
```

### Reconstruct All Pillars (Batch Mode):
```bash
python3 apply_patch.py \
    --game /path/to/CUSA03173 \
    --all-patches \
    --patch-dir dist/ \
    --out /path/to/mods
```

---

## 4. Integrity Verification

Verify reconstructed mod directory against adversarial corruption and topology regressions:

```bash
uv run python tools/pipeline/run_adversarial_audit.py --mod-dir /path/to/reconstructed_mod
```
