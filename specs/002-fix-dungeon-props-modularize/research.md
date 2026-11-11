# Research: Dungeon Props Demake, Geometry Stabilization & Modular Mod Architecture

**Feature Branch**: `002-fix-dungeon-props-modularize`  
**Date**: 2026-11-08  
**Status**: Completed  

---

## 1. Dungeon Cage Demake Strategy (User Story 2)

### 1.1 Context & Problem
In Chalice Dungeons and nightmare levels, hanging cages, ground cages, and torture cages remained untouched with smooth high-poly cylindrical bars (~1,500 to 33,000 tris). Earlier batch runs bypassed them completely because `batch_blender_demake_obj.py` used broad filters:
1. `stem.startswith("o2902")` (originally meant for elevator pulleys, but swept all `o290200`–`o290284` dungeon elevator cages).
2. `stem.startswith("o32205")` (Nightmare / Mensis hanging and deformed cages `o322050`–`o322056`).
3. `has_anibnd = True` (dungeon cages with swinging hinges or animated doors like `o290000`, `o290010`, `o290020`).
4. `has_offset_bones = True` (multi-bone unskinned assemblies where bones have translation/rotation offsets).

### 1.2 Decision
- **Selective Cage Whitelist & Demake**: Decouple cage models from blanket bypass. Process cage geometry through headless Blender decimation (COLLAPSE modifier targeting 70–80% triangle reduction, ~200–800 triangles per cage assembly).
- **Hard Facet Shading**: Apply `shade_flat` / hard split vertex normals to all cage bars, eliminating high-poly smoothed cylinder highlights and establishing authentic 32-bit retro angularity.
- **Bone-Local Coordinate Preservation**: Rigid cages with multi-bone structures (`default_bone_index > 0`) must retain their local bone transformation coordinates without baking armature space shifts into vertex buffers.
- **Asset Scope**:
  - Chalice hanging & elevator cages: `o290200`..`o290284`, `o290350`..`o290374`, `o290000`..`o290004`, `o294980`..`o294994`, `o297830`..`o297844`.
  - Mensis / Nightmare hanging & deformed cages: `o322001`, `o322050`..`o322056`, `o322310`, `o322320`, `o260303`, `o260310`.
  - Dog & prison cages: `o243010`..`o243014`, `o270102`, `o270104`, `o273011`, `o281000`..`o281001`, `o282020`.
- **Invariants**: Preserve `.anibnd` animation tracks, dummy interaction markers, and Havok rigid collision boxes (`.hkx`).

### 1.3 Alternatives Considered
- *Full Manual Modeling*: High labor cost across 40+ cage variants. Rejected in favor of programmatic Blender COLLAPSE decimation with strict topology and normal enforcement.
- *Preserve as Vanilla*: Violates visual consistency; smooth 3D round bars clash heavily against retro low-poly environments.

---

## 2. Cadaver Waste Exploded Mesh Resolution (User Story 1)

### 2.1 Context & Problem
In Chalice Dungeons, large cadaver wastes (e.g. `o297210`, `o298500`, `o297100`..`o297144`, `o290250`..`o290274`) rendered as gigantic ballooned polygon sheets or distorted spikes across dungeon rooms (captured in user artifact `uploaded_media_1794181963306.jpg`).

Investigation revealed two compounding technical root causes:
1. **Unskinned Multi-Bone Coordinate Translation**:
   Props like `o290250` contain submeshes assigned to offset child bones (e.g. `Bone 0: _00` at $Y = +16.0$m, `Bone 2: _03` at $Y = -9.58$m with rotation $\theta = 1.13$ rad). When exported through naive glTF or decimated without preserving local bone offsets, vertices authored in local space get transformed twice or flattened to world coordinates, throwing triangles $10$ to $25$ meters across the room.
2. **Degenerate Slivers and Unwelded Duplicate Vertices**:
   In `o297210` Mesh 2 (`c1040_Body`), vanilla had 35,028 tris and 67,999 vertices. Decimation unshared vertices resulting in 63,051 vertices for only 7,005 triangles (9x vertex explosion). Boundary-adjacent edges collapsed into needle-thin slivers and planar spikes protruding through the dungeon floor and liquid planes.

### 2.2 Decision
- **Bone-Local Vertex Anchor Locking**: Ensure all vertex coordinates remain strictly in bone-local coordinate frames relative to `mesh.default_bone_index`. When processing rigid composite props, vertex arrays are transformed only relative to their local parent bone.
- **Ground Coordinate Clamping**: Submesh vertex bounds are validated against ground plane limits ($Y_{\min} \ge \text{floor} - 0.05$m).
- **Topology Sanitization**:
  - Cull zero-area degenerate triangles ($\text{Area} < 10^{-6}$ m$^2$).
  - Cull needle slivers with aspect ratio $\rho > 25.0$.
  - Synchronize FaceSets: `FS1..FS5 = FS0.copy()` per Constitution Principle III.
  - Recalculate AABB bounding boxes using bone hierarchy accumulation formula (Section 29 of `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md`).

### 2.3 Alternatives Considered
- *Bypass all corpse props to vanilla*: Leaves corpse piles at high poly count (~35k tris per pile), bloating VRAM and command buffers.
- *Simple QEM decimation without bone locking*: Produces the exact mesh explosions observed in-game.

---

## 3. Five-Pillar Modular Mod Architecture for bbport (User Story 3)

### 3.1 Context & Problem
Previously, assets were packaged into a single monolithic mod folder `mods/Bloodborne Low-Poly Overhaul/`. User requested decoupling into modular addition packages under `mods/`, specifically separating props from maps to protect static world geometry from prop and collision adjustments.

### 3.2 Decision
Structure the overhaul into five independent modular pillars under `mods/`:

1. **`mods/Bloodborne Retro Maps/`**:
   - `dvdroot_ps4/map/`: Purely static world architecture, dungeon modular room blocks (`m29_*`), vistas, sky terrain, and BXF texture binders (`.tpfbdt`, `.tpfbhd`). Zero prop logic or rigid mechanisms.
2. **`mods/Bloodborne Retro Props and Objects/`**:
   - `dvdroot_ps4/obj/`: Scenery props, mechanisms, doors, ladders, chests, cages, and cadaver waste heaps (`*.objbnd.dcx`). Contains Havok collision (`.hkx`), interaction dummies, and `.anibnd` animations decoupled from maps.
3. **`mods/Bloodborne Retro Armors and Weapons - Cloth Physics/` & `mods/Bloodborne Retro Armors and Weapons - Flat Stiff/`**:
   - `dvdroot_ps4/parts/`: Player armor sets (`am_*`, `bd_*`, `lg_*`, `fc_*`), trick weapons (`wp_*`), and firearms. Two distinct options: dynamic Cloth Physics vs low-spec Flat Stiff attire.
4. **`mods/Bloodborne Retro Characters/`**:
   - `dvdroot_ps4/chr/`: Enemies, bosses, Plain Doll (`c8030`), NPCs, and beasts (`*.chrbnd.dcx`).
5. **`mods/Bloodborne Retro HUD and UI/`**:
   - `dvdroot_ps4/menu/`: Standalone retro HUD, vitals gauges, interaction prompts, and announcement banners (`common.tpf.dcx`, etc.).

Each package contains:
- `mod.json` with metadata, version, dependencies (optional), and file inventory.
- Standalone `dvdroot_ps4/` hierarchy allowing `bbport` to load any subset without dependency errors.

### 3.3 Alternatives Considered
- *Combine Maps and Props*: Monolithic risk: errors in prop collision or rigging could break map loading. Separating them guarantees safety and targeted testing.
- *Loose individual files*: Mod manager chaos; difficult to toggle or uninstall.

---

## 4. Multi-Model Quality Audit Workflow (User Story 4 / Principle VI)

### 4.1 Context & Problem
Automated pipelines can produce blind spots (omitted cages, exploded vertices, unquantized textures) that single-model agents might miss. Principle VI of the Constitution mandates an adversarial quality audit conducted by an independent alternate AGY model (such as Sonnet 4.6) before final sign-off.

### 4.2 Decision
- **Audit Harness (`tools/verify_retro_audit.py`)**: Script that extracts geometric metrics, topology stats, bounding boxes, normal distribution, and texture formats across modified assets.
- **Adversarial Subagent Protocol**:
  - Main agent invokes an independent auditor subagent with a dedicated auditing prompt.
  - Auditor reviews the generated audit metrics, verifies absence of mesh explosions (max edge length $\le 2.0$m, aspect ratio $\le 25.0$), verifies cage decimation ratios (70–80% reduction), and checks modular folder isolation.
  - Auditor produces a signed `AUDIT_REPORT.md` with explicit PASS/FAIL per check.
  - Pipeline halts if any check fails.

### 4.3 Alternatives Considered
- *Self-auditing by same agent*: Prone to confirmation bias and repeated blind spots.
- *Manual in-game check only*: Unsystematic and violates Constitution Principle IV.
