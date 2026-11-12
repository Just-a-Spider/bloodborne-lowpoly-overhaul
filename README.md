# Bloodborne: Low-Poly Overhaul

An authentic retro 32-bit low-poly overhaul for *Bloodborne* on PC (CUSA03173 v1.09).

This project combines an algorithmic 3D asset decimation pipeline, retro palette quantization, and an additive Vulkan retro graphics pipeline to deliver a comprehensive PSX-era demake aesthetic.

---

## Visual Showcase

| 1. Vanilla Baseline | 2. Retro Pipeline ON (Vanilla Assets) | 3. Retro Pipeline + Low-Poly Overhaul Mod |
| :---: | :---: | :---: |
| [![Vanilla](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_vanilla.jpg)](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_vanilla.jpg) | [![Retro ON](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_on.jpg)](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_on.jpg) | [![Retro + Mod](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_lowpoly_mod.jpg)](https://raw.githubusercontent.com/Just-a-Spider/bloodborne_pc/media-assets/screenshot_retro_lowpoly_mod.jpg) |
| Standard modern PBR, bilinear textures | 15-bit Bayer dither, nearest-neighbor | Full 32-bit conversion: low-poly geometry + retro pipeline |

---

## Modular 5-Pillar Architecture

Starting with Release v1.2.0, the overhaul is decoupled into **five independent modular mod pillars**. Players can install the entire demake or choose specific pillars:

1. **Retro Maps (`dvdroot_ps4/map/`)**: Sliced 128x128 / 256x256 uncompressed BC1 texture binders with 15-bit RGB555 palette quantization across all 14 game regions, while keeping walkable level architecture at pristine LOD0 geometry to preserve collision and lightmaps.
2. **Retro Props & Objects (`dvdroot_ps4/obj/`)**: Decimated interactive world props, mechanisms, chests, statues, and lanterns, with strict affine-transform guards for elevators, gates, and ladders.
3. **Retro Armors & Weapons (`dvdroot_ps4/parts/`)**: Low-poly player attire sets, trick weapons, and firearms. Distributed in two specialized editions:
   - **Cloth Physics Edition**: Retains authentic FromSoftware Havok dynamic cloth physics on capes, coats, and skirts.
   - **Flat Stiff Edition**: Classic stiff retro simulation without dynamic cloth physics.
4. **Retro Characters (`dvdroot_ps4/chr/`)**: Low-poly manifold decimation across all enemies, bosses, beasts, friendly NPCs, and the Plain Doll (`c8030`).
5. **Retro HUD & UI (`dvdroot_ps4/menu/`)**: Standalone retro vitals gauges, icons, interaction frames, and announcement banners.

---

## Player Quick Start

Reconstruct standalone mod folders on any machine with **zero external dependencies**.

### Prerequisites:
- A legal copy of *Bloodborne* v1.09 (`CUSA03173/`).
- Download your desired `.patch` files and reconstructor from [Latest Release](https://github.com/Just-a-Spider/bloodborne-lowpoly-overhaul/releases/latest):
  - **Windows**: Download standalone native `apply_patch.exe` (no Python needed).
  - **Linux / macOS / Python**: Download `apply_patch.py` (requires standard Python 3.9+).

---

### Option A: Install Individual Modular Mod Pillars (Recommended)

1. **Windows Native (`apply_patch.exe`)**:
   - Double-click `apply_patch.exe` for interactive auto-detection and setup, OR:
   ```cmd
   apply_patch.exe --game C:\path\to\CUSA03173 --all-patches --patch-dir dist --out C:\path\to\mods
   ```

2. **Python Reconstructor (`apply_patch.py`)**:
   - Reconstruct a specific pillar (for example, Retro HUD and UI):
   ```bash
   python3 apply_patch.py --game /path/to/CUSA03173 --patch bloodborne_retro_hud.patch --out /path/to/mods/bloodborne_retro_hud
   ```
   - Reconstruct all modular pillars at once:
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

## Release Files

| File | Size | Description |
|---|---|---|
| `bloodborne_retro_maps.patch` | 548 MB | **Maps**: Low-poly world geometry and retro textures |
| `bloodborne_retro_props.patch` | 105 MB | **Props**: Scenery, doors, chests, and lanterns |
| `bloodborne_retro_armors_cloth.patch` | 907 MB | **Armors (Cloth)**: Low-poly gear with dynamic cloth physics |
| `bloodborne_retro_armors_stiff.patch` | 827 MB | **Armors (Stiff)**: Low-poly gear with classic stiff retro physics |
| `bloodborne_retro_characters.patch` | 189 MB | **Characters**: Enemies, bosses, NPCs, and the Plain Doll |
| `bloodborne_retro_hud.patch` | 4 MB | **HUD & UI**: Retro vitals gauges, icons, and frames |
| `apply_patch.exe` | 669 KB | Standalone Windows patcher (GUI folder picker, zero setup) |
| `apply_patch.py` | 14 KB | Standalone Python patcher (Linux / macOS) |

> Checksums available in `SHA256SUMS.txt` on the [Releases](https://github.com/Just-a-Spider/bloodborne-lowpoly-overhaul/releases/latest) page.

---

## Interactive 3D Model Viewer

Inspect and verify any character (`chr`), prop (`obj`), map chunk, or armor piece (`parts`) in real-time with the built-in diagnostic WebGL viewer:

```bash
# By asset ID (auto-detected across modular mods and vanilla game):
uv run python tools/viewer/model_viewer.py c2500

# Or by direct path:
uv run python tools/viewer/model_viewer.py "mods/Bloodborne Retro Characters/dvdroot_ps4/chr/c2500.chrbnd.dcx"

# Custom vanilla game or mods directory:
uv run python tools/viewer/model_viewer.py c2500 --game /path/to/CUSA03173 --mods-dir /path/to/mods
```

- **Live A/B Testing (`Space`)**: Instant side-by-side comparison between pristine vanilla and retro demade models.
- **Shading Overlays**: Full texture preview, flat faceted shading (`F`), clay mode, and wireframe toggle (`W`).
- **Real-Time Metrics**: Live triangle/vertex counts, decimation reduction delta, and submesh isolation.

---

## Documentation & Source

Guides for modders, contributors, and technical deep-dives:

- **[Demake Guide](docs/BB_PSX_DEMAKE_GUIDE.md)**: Architecture, visual findings, and engine quirks.
- **[Pipeline & Build Guide](docs/PIPELINE.md)**: Asset creation, building from scratch, and patch packaging.
- **[Contributing](CONTRIBUTING.md)**: Development standards, rigging invariants, and pull requests.

<details>
<summary>Building from Source (Pipeline Commands)</summary>

### Prerequisites
- Python 3.12+ managed via `uv`
- Blender 4.x in system `PATH`
- System libraries: `libgomp`, `openmp`

```bash
# Validate structure:
uv run python tools/pipeline/modular_structure_validator.py --mods-dir mods

# Package modular deliverables:
uv run python tools/pipeline/package_modular_mods.py --pillar all --clean

# Generate patch:
uv run python tools/pipeline/create_patch.py --vanilla CUSA03173 --mod "mods/Bloodborne Retro HUD and UI" --out dist/bloodborne_retro_hud.patch
```

</details>
