# Research & Technical Decisions: Retro HUD & Interaction Elements Demake

## Overview

This document establishes the architectural, algorithmic, and container format decisions for retro-demaking Bloodborne's Scaleform heads-up display (HUD), combat vitals, interaction prompts, and announcement banners.

---

### Decision 1: Atlas Segmentation & Selective Processing in `common.tpf.dcx`

- **Decision**: Process all 20 `MENU_Common_*` atlases and all 16 `MENU_Icon_*` atlases in `common.tpf.dcx`, while strictly preserving button guide glyphs (`KG_*`) and localized language markers (`MENU_LNG_*`) in pristine un-demaked state.
- **Rationale**:
  - `MENU_Common_*` textures contain the primary gameplay HUD: player health/stamina fill bars, quicksilver bullet and blood vial counters, weapon slot frames, enemy/boss health gauges, dialogue boxes, and interaction prompt backplates.
  - `MENU_Icon_*` textures contain item icons, weapon silhouettes, and status indicators.
  - Scaleform controller prompt icons (`KG_OK`, `KG_Cancel`, `KG_L1`, `KG_R1`, `KG_Start`, etc.) are rendered at small scale (32x32 to 64x64). Decimating or aggressively quantizing these causes button icons to blur into unrecognizable blobs, causing input confusion.
  - Selectively preserving `KG_*` while demaking all surrounding frames and gauges achieves an authentic retro feel without harming accessibility.
- **Alternatives Considered**:
  - *Full indiscriminate atlas demake*: Rejected because button glyphs become illegible.
  - *Icons-only demake*: Rejected because vitals bars, boss bars, and interaction banners would remain modern high-resolution vectors.

---

### Decision 2: Retro Quantization Algorithm & Canvas UV Preservation

- **Decision**: Transform UI textures via a three-phase pipeline:
  1. Downsample texture by an integer factor ($D=2$ for $\le 1024$px, $D=4$ for $2048$px) using bilinear sampling.
  2. Quantize RGB channels to 15-bit RGB555 color space ($32$ uniform steps per channel: `arr = (arr >> 3) << 3`), preserving the 8-bit alpha channel for clean cutout borders.
  3. Upscale the quantized pixel art back to original canvas resolution using **Nearest-Neighbor** interpolation.
- **Rationale**:
  - FromSoftware's Scaleform runtime (`ingametop.gfx`, `messagebox.gfx`, `equipment.gfx`) defines UV coordinate bounds mapped to fixed canvas pixel coordinates (e.g. 2048x2048 or 1024x1024).
  - Shrinking the container canvas itself desynchronizes UV mappings, causing the UI to display blank boxes or misplaced slices.
  - Upscaling quantized pixels back to the original canvas preserves exact UV coordinates while producing crisp, chunky 32-bit retro texels.
- **Alternatives Considered**:
  - *Resizing container dimensions*: Rejected because Scaleform GFX files have hardcoded UV coordinates; altering canvas size breaks UI layout across all menus.
  - *8-bit indexed palette (RGB332 / indexed color)*: Rejected because FromSoft PS4 texture decoders do not support 8-bit palettized TPFs (only BC1/BC7/RGBA8).

---

### Decision 3: Single Mip Level Invariant & PS4 Morton Swizzling

- **Decision**: Enforce strictly 1 mip level (`num_mips = 1`) on all modified UI textures in `common.tpf.dcx`, with PS4 GCN Morton micro-tile swizzling and zero-padded alignment within each texture's allocated `tex_sz`.
- **Rationale**:
  - Scaleform UI textures in Bloodborne are authored with a single mip level (`num_mips = 1`). Generating lower mip levels causes Scaleform's dynamic scaler to sample lower mips during animation, resulting in unwanted blurry filtering.
  - The PS4 GPU hardware texture sampler requires Morton micro-tiling for linear block-compressed textures (BC7/BC1).
  - Textures must not exceed their header allocated `tex_sz`. Zero-filling trailing alignment padding prevents corrupted bytes from leaking into adjacent texture offsets.
- **Alternatives Considered**:
  - *Generating standard mipmaps*: Rejected because Scaleform renders blurry scaled icons when mip levels exist.
  - *Unswizzled linear buffer*: Rejected because shadPS4 and PS4 hardware texture decoders expect swizzled micro-tiles for all TPF buffers.

---

### Decision 4: Safe Mod Packaging & Distribution Architecture

- **Decision**: Deploy modified UI archives exclusively to `CUSA03173-PSX/dvdroot_ps4/menu/` and standalone distribution packages under `mods/Bloodborne Low-Poly Overhaul/dvdroot_ps4/menu/`. Integrate menu assets into `create_patch.py` / `apply_patch.py` XOR diffing.
- **Rationale**:
  - Fully conforms to Constitution Principle I (Baseline Immutability). Pristine retail `CUSA03173/` is never modified.
  - Pre-modification backup `common.tpf.dcx.bak` is generated prior to write.
  - Standalone XOR patch format packages menu changes without distributing copyrighted FromSoftware assets.
- **Alternatives Considered**:
  - *In-place modification of retail folder*: Strictly prohibited by project constitution.

---

### Decision 5: Test Verification Strategy

- **Decision**: Author an automated verification script (`tools/verify_hud_demake.py`) structured into four verification tiers:
  - **Tier 1 (Container Integrity)**: Validates DCX compression, TPF header magic (`TPF\x00`), texture count ($N=65$), and offset monotonicity.
  - **Tier 2 (Scaleform UV & Layout Invariants)**: Validates that all canvas dimensions ($W \times H$) match vanilla originals bit-for-bit, and single mip level (`num_mips = 1`) is preserved.
  - **Tier 3 (Palette & Quantization Audit)**: Validates that `MENU_Common_*` and `MENU_Icon_*` conform to 15-bit RGB555 palette steps ($C \pmod 8 == 0$), while `KG_*` controller prompts remain uncompromised.
  - **Tier 4 (Baseline & Backup Immutability)**: Asserts retail `CUSA03173/dvdroot_ps4/menu/common.tpf.dcx` hash is unchanged and `.bak` exists.
