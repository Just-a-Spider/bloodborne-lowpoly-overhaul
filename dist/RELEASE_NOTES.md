# Bloodborne: Low-Poly Overhaul v1.2.1

Release v1.2.1 delivers critical fixes for Research Hall interactive mechanisms and Lady Maria boss fight cloth synchronization across both dynamic Havok Cloth and Flat Stiff editions.

All distribution packages are zero-dependency XOR differential patches against clean retail *Bloodborne* v1.09 (`CUSA03173`).

---

## What's New in v1.2.1

### 1. Research Hall Interactive Stairs & Ladders Visibility
- Fixed invisible and collapsed moving stairs and vertical step ladders in Research Hall (`m35_00` / internal `DLC時計塔`).
- Corrected prop categorization in `tools/pipeline/batch_blender_demake_obj.py` by removing `o24301*` from cage decimation.
- Added strict bypass whitelisting for Research Hall rotating stair mechanisms (`o243010`-`o243014`, `o353006`, `o353011`, `o353013`, `o249001`, `o249002`) and multi-bone ladder rungs (`o350500`-`o350504`).
- Restored pristine FromSoftware FLVER geometry, discrete rung bone transforms, and operational bounding boxes in `Bloodborne Retro Props and Objects` (`bloodborne_retro_props.patch`).

### 2. Lady Maria Boss Fight Cloth Physics & Hat Mesh Synchronization
- Fixed detached hat feathers and cape/mantle submeshes on Lady Maria (Hunter set 9300: `hd_f_9300`, `hd_m_9300`, `bd_f_9300`, `bd_m_9300`) that previously remained floating in mid-air at spawn coordinates during movement and dashes.
- **Cloth Physics Edition** (`bloodborne_retro_armors_cloth.patch`): Preserves active FromSoftware Havok dynamic cloth solver packages (`_c.hkx`, `_c.clm2`) and `_Cloth.mtd` material bindings, while parenting simulation dummy bones to character skeleton roots (Head for hat feathers, Spine2 for mantle).
- **Flat Stiff Edition** (`bloodborne_retro_armors_stiff.patch`): Binds decoupled feather submeshes directly to Head bone and mantle/scarves to Spine2 and Neck bones with valid default bone indices and non-negative bone parenting, completely preventing stationary mesh detachment.

### 3. Internal Map ID Reference & Governance
- Formally integrated internal map IDs (`m21_00` through `m36_00`) and Japanese naming conventions into `.specify/memory/constitution.md` to prevent asset miscategorization across demake stages.
- Bumped Constitution to version 1.2.1.

---

## Release Artifacts & Checksums

| Artifact Name | Size | SHA256 Digest |
| --- | --- | --- |
| `bloodborne_retro_armors_cloth.patch` | 411.4 MB | `adcc99c985de112a706ed791c9eb4237d8bd059cec8986c2849fb83277268391` |
| `bloodborne_retro_armors_stiff.patch` | 411.4 MB | `748cffe0db8a2b72278929842576bec20815e81b82a7c0a40c9b15d651eee906` |
| `bloodborne_retro_characters.patch` | 189.1 MB | `f0b2d570f48ca795c4e513ade3f180a3da55c39143bc6708a17149ddaa66a0c8` |
| `bloodborne_retro_hud.patch` | 4.1 MB | `6284dc9045d4be864f2c79dd51961581527c7d67b77cba1da3337417e2e940e0` |
| `bloodborne_retro_maps.patch` | 548.4 MB | `b1565863c4e29eab290f6e98dfd377f21d274fc4a40c9b5be3d99d4cd76dc2ff` |
| `bloodborne_retro_props.patch` | 116.1 MB | `7d2fe7df7c5be5a71c76a0bc3f69cd3dd467a735634df1eda38d92cb519253d1` |
| `apply_patch.py` | 14.3 KB | `b225d15abffb8a3d9abc8444ed58a425f1b05bb98a223cb74a8c2f529d82d25b` |
| `apply_patch.exe` | 668.5 KB | `1cc39047fbc0089e6c1831fe585b51fbea73d85cdd0bcd837dfe06eeba983372` |

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
