# Bloodborne: Low-Poly Overhaul

A comprehensive performance optimization and authentic retro low-poly overhaul for *Bloodborne* on PC (CUSA03173 v1.09).

This project combines an algorithmic 3D asset decimation pipeline, retro palette quantization, and an additive Vulkan retro graphics pipeline. It eliminates CPU command-buffer bottlenecks, reduces GPU VRAM consumption below the 2GiB barrier, and boosts framerates on low-spec hardware and laptop GPUs from 22 FPS up to 90 FPS.

---

## Empirical Performance Benchmarks

Tested on Linux (Kernel 6.17, Bcachefs, NVIDIA GeForce GTX 1650 with Max-Q Design 4GB VRAM):

| Scenario / Area | Resolution & Preset | Configuration | Measured Framerate | Measured VRAM | Key Architectural Impact |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Vanilla Retail Baseline** | 1680x1050 Native | Vanilla Assets | **22–27 FPS** | 2,449 MiB | Severe draw-call & shadow ALU bottleneck |
| **Vanilla + Retro Pipeline** | 1680x1050 Balanced | Retro ON (`retro_mode=1`) | **40–50 FPS** | 2,449 MiB | **+80% FPS** (aniso disabled, dynamic shadows off) |
| **Low-Poly Overhaul Base** | 1680x1050 Balanced | Low-Poly Mod + Retro ON | **55–60 FPS** | **2,083 MiB** | **-366 MiB VRAM**, eliminates micro-triangles |
| **The Great Bridge (`m21`)** | 1680x1050 Balanced | Low-Poly Mod + Retro ON | **~55 FPS** | 2,385 MiB | Dense outdoor geometry baseline |
| **The Great Bridge (`m21`)** | 1680x1050 Performance | Low-Poly Mod + Retro ON | **~65 FPS** | 2,244 MiB | **-141 MiB** via G-Buffer scaling |
| **The Great Bridge (`m21`)** | 1280x800 Performance | Low-Poly Mod + Retro ON | **~75 FPS** | 2,155 MiB | **-230 MiB** vs 1050p |
| **Hunter's Dream (`m21`)** | 1280x800 Performance | Low-Poly Mod + Retro ON | **80–90 FPS** | **1,952 MiB** | **Sub-2GiB barrier broken** (< 2,048 MiB) |
| **Chalice Dungeons (`m29`)** | 1280x800 Performance | Low-Poly Mod + Retro ON | **80–90 FPS** | 2,060–2,127 MiB | High-framerate floor in indoor corridors |
| **Hunter's Dream (Live)** | 1920x1200 FSR 3.1 | Vanilla Baseline | **58 FPS** (17.3 ms) | — | High-resolution modern PBR baseline |
| **Hunter's Dream (Live)** | 1920x1200 FSR 3.1 | Retro Pipeline ON | **51 FPS** (19.5 ms) | — | 15-bit Bayer dither, point-filtered |
| **Hunter's Dream (Live)** | 1920x1200 FSR 3.1 | Low-Poly Mod + Retro ON | **56 FPS** (17.8 ms) | — | Complete 32-bit retro demake aesthetic |

### Architectural Root Causes:
1. **Command Dispatch Alleviation**: Vanilla Bloodborne issues high draw call overhead with complex vertex buffer state switches. Reducing asset density by 75–80% collates primitives and allows the command translator to stream draw calls synchronously without micro-stutters.
2. **VRAM Bandwidth Collapse**: Texture binders downscaled to 128x128 / 256x256 fit cleanly within L2 caches and prevent memory paging on 2GB and 4GB mobile GPUs.

---

## Visual Showcase

| 1. Vanilla Baseline | 2. Retro Pipeline ON (Vanilla Assets) | 3. Retro Pipeline + Low-Poly Overhaul Mod |
| :---: | :---: | :---: |
| [![Vanilla](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_vanilla.jpg)](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_vanilla.jpg) | [![Retro ON](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_on.jpg)](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_on.jpg) | [![Retro + Mod](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_lowpoly_mod.jpg)](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_lowpoly_mod.jpg) |
| Standard modern PBR, bilinear textures | 15-bit Bayer dither, nearest-neighbor | Full 32-bit conversion: low-poly geometry + retro pipeline |

---

## Player Quick Start (7-Second Setup)

Reconstruct the full standalone mod (2,669 assets, 1.28 GB) on any machine using standard Python 3.9+ with **zero external dependencies**.

### Prerequisites:
- A legal copy of *Bloodborne* v1.09 (`CUSA03173/`).
- Python 3.9 or higher (standard library only).

### Installation Steps:
1. Download `apply_patch.py` and `bloodborne_lowpoly_overhaul.patch` from the [Latest Release](https://github.com/Just-a-Spider/bloodborne-lowpoly-overhaul/releases/latest).
2. Run the patch reconstructor:
   ```bash
   python3 apply_patch.py --game /path/to/CUSA03173
   ```
   *(The reconstructor automatically detects `bloodborne_lowpoly_overhaul.patch` in the current directory and extracts all 2,669 assets in ~12 seconds using parallel integer-vectorized XOR).*

3. Deploy the reconstructed folder to your game's `mods` directory:
   ```bash
   mv "Bloodborne Low-Poly Overhaul" /path/to/game/mods/
   ```

4. Enable `"Bloodborne Low-Poly Overhaul"` in your mod manager or in `mods.json`:
   ```json
   {
     "order": [
       "Bloodborne Low-Poly Overhaul"
     ],
     "disabled": []
   }
   ```

---

## Modder & Pipeline Guide (Rebuilding from Scratch)

For researchers and modders wishing to modify geometric decimation ratios, bone weight interpolation algorithms, or palette quantization formulas from source:

### Pipeline Prerequisites:
- Python 3.12+ managed via `uv`.
- Blender 4.x installed and present in your system `PATH`.
- System libraries: `libgomp`, `openmp`.

### 1. Rebuild Entire Mod from Pristine Base Game:
```bash
uv run python tools/pipeline/build_from_scratch.py --vanilla CUSA03173
```
This orchestrates the 6 pipeline stages:
- **Stage 1 (`parts`)**: Decimates all Hunter armor sets, trick weapons, and firearms via Blender quadric edge-collapse.
- **Stage 2 (`chr`)**: Decimates enemies, bosses, the Plain Doll, and Hunter rigs while preserving Havok cloth submeshes and bone weights.
- **Stage 3 (`obj`)**: Decimates interactive props and world architecture with strict whitelist protections for ladder ground alignments and composite assemblies.
- **Stage 4 (`map`)**: Downscales environment texture binders into 128x128 / 256x256 uncompressed BC1 blocks with RGB555 palette quantization.
- **Stage 5 (`package`)**: Non-destructively isolates the differential delta into `mods/Bloodborne Low-Poly Overhaul/`.
- **Stage 6 (`verify`)**: Executes automated mathematical checks on bone AABBs and ground contact invariants.

### 2. Generate Distribution Patch:
```bash
uv run python tools/pipeline/create_patch.py --vanilla CUSA03173 --mod "mods/Bloodborne Low-Poly Overhaul"
```
Produces `dist/bloodborne_lowpoly_overhaul.patch` with full SHA256 integrity manifests in < 25 seconds.

---

## Key Documentation
- [BB_PSX_DEMAKE_GUIDE.md](BB_PSX_DEMAKE_GUIDE.md): Technical root causes, Soulstruct FLVER deserializer quirks, and pipeline architecture.
- [BB_PSX_DEMAKE_MATH_AND_FINDINGS.md](BB_PSX_DEMAKE_MATH_AND_FINDINGS.md): Empirical framerate benchmarks, VRAM breakdown, Morton swizzle math, and binary container layout.
