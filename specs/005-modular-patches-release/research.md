# Phase 0 Research: Modular Mod Release & Patch Distribution

**Feature**: Modular Mod Release & Patch Distribution Artifacts (`005-modular-patches-release`)
**Date**: 2026-11-11

## 1. Modular Pillar & Patch Inventory

### Decision
Support 5 independent modular mod pillars (6 distinct patch variants including Armors Cloth/Stiff split) plus 3 master overhaul bundles:

| Pillar / Package | Target Directory (`mods/`) | Source Path in Game | Patch Artifact in `dist/` | Size |
|---|---|---|---|---|
| **Pillar 1: Maps** | `Bloodborne Retro Maps` | `dvdroot_ps4/map/` | `bloodborne_retro_maps.patch` | ~549 MB |
| **Pillar 2: Props & Objects** | `Bloodborne Retro Props and Objects` | `dvdroot_ps4/obj/` | `bloodborne_retro_props.patch` | ~106 MB |
| **Pillar 3A: Armors (Cloth)** | `Bloodborne Retro Armors and Weapons - Cloth Physics` | `dvdroot_ps4/parts/` | `bloodborne_retro_armors_cloth.patch` | ~908 MB |
| **Pillar 3B: Armors (Stiff)** | `Bloodborne Retro Armors and Weapons - Flat Stiff` | `dvdroot_ps4/parts/` | `bloodborne_retro_armors_stiff.patch` | ~828 MB |
| **Pillar 4: Characters** | `Bloodborne Retro Characters` | `dvdroot_ps4/chr/` | `bloodborne_retro_characters.patch` | ~190 MB |
| **Pillar 5: HUD & UI** | `Bloodborne Retro HUD and UI` | `dvdroot_ps4/menu/` | `bloodborne_retro_hud.patch` | ~4.13 MB |
| **Master: Cloth Overhaul** | `Bloodborne Low-Poly Overhaul (Cloth Physics)` | All pillars (cloth parts) | `bloodborne_lowpoly_overhaul_cloth.patch` | ~1.7 GB |
| **Master: Stiff Overhaul** | `Bloodborne Low-Poly Overhaul (Flat Stiff)` | All pillars (stiff parts) | `bloodborne_lowpoly_overhaul_stiff.patch` | ~1.7 GB |
| **Master: Standard** | `Bloodborne Low-Poly Overhaul` | Base overhaul | `bloodborne_lowpoly_overhaul.patch` | ~1.3 GB |

### Rationale
- Decoupling Maps and Props prevents ladder ground-alignment and mechanism collision regressions.
- Providing separate Cloth vs Stiff armors allows low-spec users (GTX 1650 Max-Q / Steam Deck) to choose between maximum FPS or authentic Havok cloth simulation.
- Preserves clean HUD isolation (menu textures only, excluding broken Talk ESD files).

### Alternatives Considered
- *Single monolithic patch only*: Rejected because users on modest GPUs cannot selectively disable heavy cloth physics or isolate texture changes.
- *ZIP/7z distribution*: Rejected because redistributing modified copyrighted assets violates baseline immutability and legal distribution standards. XOR delta patches require the player's legal game copy.

---

## 2. Client Reconstruction Ergonomics (`apply_patch.py`)

### Decision
Enhance `apply_patch.py` to:
1. Detect patch identity and automatically infer the target output folder name when `--out` is not specified.
2. Support batch extraction via `--all-patches` or `--patch-dir dist/` to extract all modular pillars into a target mods directory in a single operation.
3. Retain pure Python 3.9+ standard library compatibility with zero external pip dependencies.

### Rationale
- Defaulting to `Bloodborne Low-Poly Overhaul` caused modular patches (`bloodborne_retro_hud.patch`) to unpack into an incorrect folder name if users omitted `-o`.
- Inferring folder names directly from container metadata or filename eliminates user error.

### Alternatives Considered
- *Requiring explicit `-o` for every command*: Error-prone; users frequently omit `-o` and complain of overwritten or misplaced mods.

---

## 3. Automated Release Verification Harness (`verify_release_artifacts.py`)

### Decision
Create `tools/pipeline/verify_release_artifacts.py` to automate end-to-end release testing:
1. Validate container header magic (`BBLPO01\x00`) and metadata JSON format.
2. In-memory roundtrip XOR inversion against `CUSA03173/` validating 100% of target file SHA256 hashes.
3. Validate pillar path boundaries against `modular_structure_validator.py` rules (e.g. no `map/` files in `obj/`).
4. Generate `dist/SHA256SUMS.txt` containing SHA256 digests of all `.patch` files and `apply_patch.py`.

### Rationale
- Eliminates manual verification before creating releases.
- Acts as a hard gate preventing corrupted or stale delta files from reaching distribution.

### Alternatives Considered
- *Ad-hoc shell scripts using `sha256sum`*: Incomplete; does not test XOR delta inversion or pillar path confinement.

---

## 4. Documentation Strategy

### Decision
1. **`README.md`**: Update Player Quick Start section with:
   - Modular installation guide and modular vs overhaul selection.
   - Armor physics choice (Cloth vs Flat Stiff).
   - Artifact download inventory table with file sizes and SHA256 hashes.
   - `mods.json` load order configuration for `bbport`.
   - Troubleshooting common player errors.
2. **`BB_PSX_DEMAKE_GUIDE.md`**: Update Section 14 (Modular Architecture & Packaging) with:
   - Release creation and verification pipeline workflows.
   - Clean HUD state documentation (Talk ESD unbundled pending compiler fix).
   - Verification commands and release checklist.

### Rationale
Provides immediate clarity for players downloading patches and developers maintaining the pipeline.
