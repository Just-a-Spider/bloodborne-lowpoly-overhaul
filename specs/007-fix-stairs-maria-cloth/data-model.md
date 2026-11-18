# Data Model: Research Hall Stairs & Lady Maria Cloth Fix

## Entities and Data Structures

### 1. Interactive Prop Asset (`obj/o{id}.objbnd.dcx`)
Environmental mechanism or climbable prop container used by the engine.

| Field | Type | Description |
| --- | --- | --- |
| `id` | String | Model ID (e.g., `o243010`, `o350501`, `o353006`) |
| `flver` | FLVER | 3D model containing vertices, submeshes, materials, and bones |
| `bones` | List[FLVERBone] | Skeletal hierarchy defining transform roots and individual rungs/steps |
| `hkx` | HKX (Optional) | Havok collision physics data for interaction triggers |
| `is_interactive` | Boolean | True if the asset is an interactible mechanism, rotating stair, or ladder |

#### Validation Invariants:
- `bones` count for `o350501`-`o350504` MUST exceed 30 rungs with positive Z/Y step offsets.
- Bounding box dimensions MUST match vanilla reference extrema to prevent frustum culling.

---

### 2. Character / Armor Parts Container (`parts/{type}_{gender}_{id}.partsbnd.dcx`)
Wearable armor piece or NPC model container.

| Field | Type | Description |
| --- | --- | --- |
| `type` | String | Part type: `hd` (headwear), `bd` (body/garb), `am` (arms), `lg` (legs) |
| `gender` | String | `f` (female) or `m` (male) |
| `id` | String | Armor set ID (e.g., `9300` for Lady Maria Hunter set) |
| `flver` | FLVER | 3D model with mesh partitions and material assignments |
| `cloth_hkx` | HKX (Optional) | `*_c.hkx` Havok cloth simulation package |
| `cloth_clm2` | CLM2 (Optional) | `*_c.clm2` cloth collision and pinning definition |

#### Validation Invariants:
- For Cloth Physics edition: `_c.hkx` and `_c.clm2` MUST be present in the binder, and cloth submeshes MUST reference `_Cloth.mtd`.
- For Flat Stiff edition: All FLVER bones referenced by submeshes MUST have a valid non-negative parent index (e.g. `parent_index >= 0`), linking to character skeleton roots (Head, Spine2, Neck) to prevent floating geometry.

---

### 3. Modular Mod Pillar Container (`mods/{PillarName}/`)
Granular mod folder targeting specific game asset domains.

| Pillar Directory | Target dvdroot Subfolder | Contents |
| --- | --- | --- |
| `Bloodborne Retro Props and Objects/` | `dvdroot_ps4/obj/` | Scenery props, interactive stairs, ladders |
| `Bloodborne Retro Armors and Weapons - Cloth Physics/` | `dvdroot_ps4/parts/` | Player armors with active Havok cloth physics |
| `Bloodborne Retro Armors and Weapons - Flat Stiff/` | `dvdroot_ps4/parts/` | Player armors with re-parented rigid meshes |
