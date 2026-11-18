# Research: Research Hall Interactive Stairs & Lady Maria Cloth Physics Fix

## Problem 1: Research Hall Interactive Stairs & Ladders

### Context & Symptoms
In Research Hall (`m35_00` / internal `DLC時計塔` / Patient Room Hall / "立体階段部屋"), players observed that moving rotating staircases (`o353006`, `o353011`, `o353013`, `o243010`-`o243014`) and ladders (`o350501`-`o350504`) were either completely invisible, collapsed, or disconnected from their interaction colliders.

### Root Cause Analysis
1. In `tools/pipeline/batch_blender_demake_obj.py`:
   - `o243010` through `o243014` were erroneously classified under `is_target_cage`:
     ```python
     is_target_cage = (
         stem.startswith("o2010") or stem.startswith("o2000") or
         stem.startswith("o2200") or stem.startswith("o24301") or ...
     )
     ```
   - This caused `should_bypass` to evaluate to `False` for `o24301*`. As a result, Blender imported the multi-bone prop, decimated it as a simple static cage (reducing triangle counts by up to 80%), and flattened its internal skeletal bones.
   - Interactive rotating stairs rely on discrete bone transforms and Havok physics collision meshes that expect precise submesh coordinate frames. Decimating them corrupted their bounding boxes and caused the engine to cull them or render them at origin.
2. In `o350501` through `o350504` (Research Hall ladders):
   - These assets contain up to 34 individual rung bones with step translations up to +15.0m. In an earlier decimation pass, `o350501` was decimated down to a ratio of 0.04 (4%), collapsing the visual rungs into single degenerate vertices.

### Decision & Workaround
- Remove `stem.startswith("o24301")` from `is_target_cage` in `batch_blender_demake_obj.py`.
- Add an explicit whitelist in `should_bypass` for all Research Hall interactive mechanisms and ladders:
  `o350500`-`o350504`, `o353006`, `o353011`, `o353013`, `o243010`-`o243014`, `o249001`, `o249002`.
- Restore pristine FromSoftware FLVER assets from `CUSA03173/dvdroot_ps4/obj/` to `CUSA03173-PSX/dvdroot_ps4/obj/`.
- Deploy to `mods/Bloodborne Retro Props and Objects/`.

---

## Problem 2: Lady Maria Boss Fight Cloth & Hat Mesh Detachment

### Context & Symptoms
During the Lady Maria boss fight (`c9300` / armor set `9300`: `hd_f_9300`, `bd_f_9300`, `hd_m_9300`, `bd_m_9300`), feather submeshes on her hat and cape/mantle submeshes on her coat detach upon movement and remain frozen in space at Maria's initial spawn coordinates.

### Root Cause Analysis
1. Vanilla FLVER structure for set 9300:
   - `hd_f_9300.partsbnd.dcx` contains submesh 3 (`HD_F_9300_feather1_cloth`) and submesh 4 (`HD_F_9300_feather2_cloth`), bound to bone 3 and bone 4. In vanilla, these bones have `parent_index = -1` (unparented dummy bones).
   - `bd_f_9300.partsbnd.dcx` contains cloth submeshes (`BD_F_9300_mantle_cloth`, etc.) bound to unparented dummy bones (`parent_index = -1`).
   - In vanilla, the Havok Cloth simulation system (`_c.hkx` and `_c.clm2` in the partsbnd) dynamically calculates world transforms for these cloth dummy bones every frame relative to the character root.
2. The Demake Pipeline decoupled cloth:
   - `batch_blender_demake_parts.py` decoupled cloth by replacing `_Cloth.mtd` with `_e.mtd` (or `_b.mtd`) and stripping `_c.hkx` and `_c.clm2`.
   - Without the Havok cloth solver executing on these meshes, the game engine never updates the transform of bones with `parent_index = -1`. Consequently, the feather and mantle geometry remain frozen at `(0, 0, 0)` in local space at spawn time, causing the assets to appear left behind as Maria walks or dashes away.

### Decision & Workaround
1. **For Cloth Physics Edition** (`mods/Bloodborne Retro Armors and Weapons - Cloth Physics/`):
   - Preserve pristine Havok cloth solver data (`_c.hkx`, `_c.clm2`, `_Cloth.mtd`) for Lady Maria set 9300 (`hd_f_9300`, `bd_f_9300`, `hd_m_9300`, `bd_m_9300`).
   - Keep dynamic simulation enabled so the feathers and mantle flow realistically.
2. **For Flat Stiff Edition** (`mods/Bloodborne Retro Armors and Weapons - Flat Stiff/`) and stiff pipeline passes:
   - When converting cloth meshes to rigid geometry:
     - For `hd_*_9300`: Bone 3 (`HD_F_9300_feather1`) and Bone 4 (`HD_F_9300_feather2`) must have their `parent_index` updated from `-1` to Bone 0 (`Head`).
     - For `bd_*_9300`: Unparented mantle/cape dummy bones must have their `parent_index` updated from `-1` to the logical spine/neck bone (Bone 2 `Spine2` or Bone 3 `Neck`).
     - Update vertex weights and bone references if necessary so the meshes track the character skeleton rigidly.

---

## Packaging, Differential Patching & Governance

### Decision
- Deploy repaired files to `CUSA03173-PSX/dvdroot_ps4/`.
- Repack modular mods with `tools/pipeline/package_modular_mods.py`.
- Generate differential patch `bloodborne_lowpoly_overhaul.patch` with `tools/pipeline/create_patch.py`.
- Bump project to version 1.2.1 in `dist/RELEASE_NOTES.md`.
- Ensure `specs/000-*` is not tracked in Git.
