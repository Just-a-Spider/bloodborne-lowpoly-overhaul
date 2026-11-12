# Bloodborne: Low-Poly Overhaul v1.2.0

Release v1.2.0 introduces the **Modular 5-Pillar Architecture**, decoupling the project into five standalone components. Choose the full 32-bit retro demake experience or install specific pillars.

All packages are zero-dependency XOR differential patches against clean retail *Bloodborne* v1.09 (`CUSA03173`).

---

## What's New

### The 5 Modular Pillars
- **Retro Maps (`map/`)**: Low-poly world geometry and 15-bit RGB555 retro textures across all 14 game areas, preserving original collision and lightmaps.
- **Retro Props & Objects (`obj/`)**: Low-poly models for scenery props, chests, breakables, and lanterns, with strict guards for animated elevators and levers.
- **Retro Armors & Weapons (`parts/`)**: Low-poly attire and trick weapons. Available in two editions:
  - **Cloth Physics Edition**: Keeps authentic FromSoftware Havok dynamic cloth physics.
  - **Flat Stiff Edition**: Classic stiff retro simulation without dynamic cloth.
- **Retro Characters (`chr/`)**: Low-poly models across all enemies, bosses, NPCs, and the Plain Doll (`c8030`).
- **Retro HUD & UI (`menu/`)**: Authentic 32-bit pixelated gauges, weapon icons, and dialogue frames.

---

## Installation

### Windows (Easiest)
1. Download `apply_patch.exe` and your chosen `.patch` files from Assets below.
2. Double-click `apply_patch.exe` and select your game and output folders.

### Linux / Python
```bash
python3 apply_patch.py --game /path/to/CUSA03173 --all-patches --patch-dir . --out /path/to/mods
```

### Load Order (`mods.json`)
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
*(Choose either Cloth Physics OR Flat Stiff armors, never both).*

---

## Verification
Checksums for all patch files are verified in `SHA256SUMS.txt`.
