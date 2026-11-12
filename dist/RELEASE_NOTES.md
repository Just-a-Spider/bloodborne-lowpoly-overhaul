# Release Notes: Bloodborne Low-Poly Overhaul v1.2.0

**Release Date**: 2026-11-11  
**Target Game**: Bloodborne (CUSA03173 v1.09)  
**Distribution Format**: Differential XOR Patch Containers (`.patch`)  

---

## Executive Summary

Release v1.2.0 introduces the **Modular 5-Pillar Architecture**, decoupling the Bloodborne Low-Poly Overhaul into five autonomous mod deliverables. Players can now freely choose which components of the demake to experience—from world maps and props to characters, HUD, and specialized armor editions.

All distribution packages are compiled as zero-dependency XOR differential patches against legal retail copies of Bloodborne v1.09 (`CUSA03173`), guaranteeing 100% legal compliance and zero copyrighted asset redistribution.

---

## Release Artifacts Inventory & Checksums

Verify all downloaded assets before installation:
```bash
sha256sum -c SHA256SUMS.txt
```

| Filename | Size | Target Directory / Component | SHA256 Checksum |
|---|---|---|---|
| `bloodborne_retro_maps.patch` | 548.4 MB | `Bloodborne Retro Maps/` | `b1565863c4e29eab290f6e98dfd377f21d274fc4a40c9b5be3d99d4cd76dc2ff` |
| `bloodborne_retro_props.patch` | 105.5 MB | `Bloodborne Retro Props and Objects/` | `57c49714faa66099d191034f60d161aee5a1c75f8dd56ebae80d20eba5a35789` |
| `bloodborne_retro_armors_cloth.patch` | 907.4 MB | `Bloodborne Retro Armors and Weapons - Cloth Physics/` | `7c53bc057ca025d85ca944493481baec389b5c476408025db71bee6847a5f6bd` |
| `bloodborne_retro_armors_stiff.patch` | 827.0 MB | `Bloodborne Retro Armors and Weapons - Flat Stiff/` | `ab81f1ee119bb1f7382cc46823a45633d1be54581f287eb2644817d367990a9f` |
| `bloodborne_retro_characters.patch` | 189.1 MB | `Bloodborne Retro Characters/` | `f0b2d570f48ca795c4e513ade3f180a3da55c39143bc6708a17149ddaa66a0c8` |
| `bloodborne_retro_hud.patch` | 4.1 MB | `Bloodborne Retro HUD and UI/` | `6284dc9045d4be864f2c79dd51961581527c7d67b77cba1da3337417e2e940e0` |
| `apply_patch.exe` | 661.0 KB | Standalone Windows Native Reconstructor (Zero dependencies) | `b567c3f17ab1ba1dc41cebf93ea33d183c1b68d6ca9a9ad2dcc456aa14a873d8` |
| `apply_patch.py` | 14.8 KB | Standalone Python Reconstructor (Zero external libraries) | `b225d15abffb8a3d9abc8444ed58a425f1b05bb98a223cb74a8c2f529d82d25b` |

---

## Key Features & Highlights

### 1. The Five Modular Pillars
- **Pillar 1: Retro Maps (`map/`)**: High-efficiency downscaled 128x128 / 256x256 uncompressed BC1 textures with RGB555 palette quantization across all 14 game areas (-85% to -98% active VRAM), preserving walkable geometry and lightmaps at pristine LOD0.
- **Pillar 2: Retro Props & Objects (`obj/`)**: Low-poly decimation across 867 world props, chests, breakables, and lanterns, with strict affine-transform guards protecting multi-bone elevators and gates.
- **Pillar 3: Retro Armors & Weapons (`parts/`)**: Low-poly Hunter outfits, weapons, and firearms. Choose between **Cloth Physics Edition** (authentic Havok cloth fluttering) or **Flat Stiff Edition** (cloth decoupled for extreme performance on handhelds and low-power hardware).
- **Pillar 4: Retro Characters (`chr/`)**: Manifold edge-collapse decimation across all enemies, bosses, NPCs, and the Plain Doll (`c8030`).
- **Pillar 5: Retro HUD & UI (`menu/`)**: Authentic 32-bit pixelated Scaleform HUD vitals, weapon icons, dialogue frames, and boss gauges while preserving 100% of controller button glyphs (`KG_*`).

### 2. Standalone Reconstructor Ergonomics (`apply_patch.py`)
- **Zero External Dependencies**: Pure standard library Python 3.9+; runs anywhere without `pip` or virtual environments.
- **Explicit Destination Targeting**: Explicit `--out` directory targeting guarantees full control over mod file placement.
- **Batch Reconstruction**: Use `--all-patches --patch-dir dist/ --out /path/to/mods` to reconstruct all modular pillars in a single command.
- **Robust Error Handling**: Proactive disk space checks and early version verification protect game files from partial writes.

---

## Installation Quick Start

### Single Pillar:
```bash
python3 apply_patch.py --game /path/to/CUSA03173 --patch bloodborne_retro_hud.patch --out /path/to/mods/bloodborne_retro_hud
```

### All Modular Pillars:
```bash
python3 apply_patch.py --game /path/to/CUSA03173 --all-patches --patch-dir dist/ --out /path/to/mods
```

### Mod Load Order (`mods.json`):
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
> **Warning**: Never enable both `Cloth Physics` and `Flat Stiff` armors simultaneously; choose one edition based on your hardware preference.
