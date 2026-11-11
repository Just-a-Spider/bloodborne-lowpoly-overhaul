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

## Modular 5-Pillar Architecture

Starting with Release v1.2.0, the overhaul is decoupled into **five independent modular mod pillars**. Players can install the entire demake or choose specific pillars:

1. **Retro Maps (`dvdroot_ps4/map/`)**: Sliced 128x128 / 256x256 uncompressed BC1 texture binders with 15-bit RGB555 palette quantization (-85% to -98% VRAM across all 14 game regions), while keeping walkable level architecture at pristine LOD0 geometry to preserve collision and lightmaps.
2. **Retro Props & Objects (`dvdroot_ps4/obj/`)**: Decimated interactive world props, mechanisms, chests, statues, and lanterns, with strict affine-transform guards for elevators, gates, and ladders.
3. **Retro Armors & Weapons (`dvdroot_ps4/parts/`)**: Low-poly player attire sets, trick weapons, and firearms. Distributed in two specialized editions:
   - **Cloth Physics Edition**: Retains authentic FromSoftware Havok dynamic cloth physics on capes, coats, and skirts.
   - **Flat Stiff Edition**: Decouples cloth simulation for maximum frame rates on low-power GPUs (Steam Deck, GTX 1650 Max-Q).
4. **Retro Characters (`dvdroot_ps4/chr/`)**: Low-poly manifold decimation across all enemies, bosses, beasts, friendly NPCs, and the Plain Doll (`c8030`).
5. **Retro HUD & UI (`dvdroot_ps4/menu/`)**: Standalone retro vitals gauges, icons, interaction frames, and announcement banners.

---

## Player Quick Start

Reconstruct standalone mod folders on any machine using standard Python 3.9+ with **zero external dependencies**.

### Prerequisites:
- A legal copy of *Bloodborne* v1.09 (`CUSA03173/`).
- Python 3.9 or higher (standard library only; no pip dependencies required).
- Download `apply_patch.py` and desired `.patch` files from the [Latest Release](https://github.com/Just-a-Spider/bloodborne-lowpoly-overhaul/releases/latest).

---

### Option A: Install Individual Modular Mod Pillars (Recommended)

1. Reconstruct a specific pillar (for example, Retro HUD and UI):
   ```bash
   python3 apply_patch.py --game /path/to/CUSA03173 --patch bloodborne_retro_hud.patch --out /path/to/mods/bloodborne_retro_hud
   ```

2. Reconstruct all modular pillars at once:
   ```bash
   python3 apply_patch.py --game /path/to/CUSA03173 --all-patches --patch-dir dist --out /path/to/mods
   ```

3. Configure your mod load order in `mods.json` (inside your mods folder):
   ```json
   {
     "order": [
       "Bloodborne Retro HUD and UI",
       "Bloodborne Retro Maps",
       "Bloodborne Retro Props and Objects",
       "Bloodborne Retro Characters",
       "Bloodborne Retro Armors and Weapons - Cloth Physics"
     ],
     "disabled": [
       "Bloodborne Retro Armors and Weapons - Flat Stiff"
     ]
   }
   ```
   > **Note**: Choose either `Cloth Physics` OR `Flat Stiff` armors, never both enabled at once.

---

## Release Artifacts Inventory

All `.patch` containers are compiled with SHA256 integrity verification. Verify downloaded files using:
```bash
sha256sum -c SHA256SUMS.txt
```

| Artifact File | Size | Target Pillar / Description | SHA256 Digest |
|---|---|---|---|
| `bloodborne_retro_maps.patch` | 548.4 MB | **Pillar 1: Maps** (Downscaled BC1 textures, all regions) | `b1565863c4e29eab290f6e98dfd377f21d274fc4a40c9b5be3d99d4cd76dc2ff` |
| `bloodborne_retro_props.patch` | 105.5 MB | **Pillar 2: Props** (867 scenery props, doors, lamps) | `57c49714faa66099d191034f60d161aee5a1c75f8dd56ebae80d20eba5a35789` |
| `bloodborne_retro_armors_cloth.patch` | 907.4 MB | **Pillar 3A: Armors (Cloth)** (Dynamic Havok physics) | `7c53bc057ca025d85ca944493481baec389b5c476408025db71bee6847a5f6bd` |
| `bloodborne_retro_armors_stiff.patch` | 827.0 MB | **Pillar 3B: Armors (Stiff)** (Decoupled stiff physics) | `ab81f1ee119bb1f7382cc46823a45633d1be54581f287eb2644817d367990a9f` |
| `bloodborne_retro_characters.patch` | 189.1 MB | **Pillar 4: Characters** (Enemies, bosses, NPCs, Doll) | `f0b2d570f48ca795c4e513ade3f180a3da55c39143bc6708a17149ddaa66a0c8` |
| `bloodborne_retro_hud.patch` | 4.1 MB | **Pillar 5: HUD & UI** (Retro vitals, prompts, frames) | `6284dc9045d4be864f2c79dd51961581527c7d67b77cba1da3337417e2e940e0` |
| `apply_patch.py` | 14.3 KB | **Standalone Python Reconstructor** (Zero dependencies) | `b225d15abffb8a3d9abc8444ed58a425f1b05bb98a223cb74a8c2f529d82d25b` |

---

## Modder & Pipeline Guide (Rebuilding from Scratch)

For researchers and modders wishing to modify geometric decimation ratios, bone weight interpolation algorithms, or palette quantization formulas from source:

### Pipeline Prerequisites:
- Python 3.12+ managed via `uv`.
- Blender 4.x installed and present in your system `PATH`.
- System libraries: `libgomp`, `openmp`.

### 1. Validate Modular Structure:
```bash
uv run python tools/pipeline/modular_structure_validator.py --mods-dir mods
```

### 2. Package Modular Mod Deliverables:
```bash
uv run python tools/pipeline/package_modular_mods.py --pillar all --clean
```

### 3. Generate & Verify Distribution Patches:
```bash
# Generate patch for individual modular mod:
uv run python tools/pipeline/create_patch.py --vanilla CUSA03173 --mod "mods/Bloodborne Retro HUD and UI" --out dist/bloodborne_retro_hud.patch

# Audit all release artifacts and generate checksum manifest:
uv run python tools/pipeline/verify_release_artifacts.py --vanilla CUSA03173 --dist dist --manifest dist/SHA256SUMS.txt
```

---

## Technical Documentation & Workflows

- **[ADDITIONS.md](docs/ADDITIONS.md)**: Asset creation, decimation parameters, texture quantization, and FLVER injection pipeline.
- **[RECREATION.md](docs/RECREATION.md)**: Step-by-step instructions to rebuild mod assets algorithmically from retail vanilla `CUSA03173`.
- **[DISTRIBUTION.md](docs/DISTRIBUTION.md)**: Differential XOR patch generation, checksum manifests, and release packaging.
- **[COLLABORATION.md](docs/COLLABORATION.md)**: Contributor standards, rigging invariants, Havok cloth physics rules, and PR verification gates.
- **[BB_PSX_DEMAKE_GUIDE.md](docs/BB_PSX_DEMAKE_GUIDE.md)**: Technical root causes, Soulstruct FLVER deserializer quirks, modular architecture, and pipeline verification.
- **[BB_PSX_DEMAKE_MATH_AND_FINDINGS.md](docs/BB_PSX_DEMAKE_MATH_AND_FINDINGS.md)**: Empirical framerate benchmarks, VRAM breakdown, Morton swizzle math, and binary container layout.
- **[RELEASE_NOTES.md](dist/RELEASE_NOTES.md)**: Release v1.2.0 features, modular pillar descriptions, and SHA256 checksums.
