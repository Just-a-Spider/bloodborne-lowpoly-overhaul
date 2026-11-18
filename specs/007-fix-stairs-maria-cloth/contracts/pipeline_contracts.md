# Pipeline Contracts: Prop Bypass & Armor Rigging

## 1. Prop Bypass Contract (`tools/pipeline/batch_blender_demake_obj.py`)

### Function: `should_bypass(stem: str) -> bool`
Evaluates whether a prop ID should bypass decimation to prevent coordinate collapse or physics desync.

#### Guarantees:
- Returns `True` for all Research Hall ladder assets: `o350500`, `o350501`, `o350502`, `o350503`, `o350504`.
- Returns `True` for all Research Hall rotating stairs & mechanisms: `o353006`, `o353011`, `o353013`, `o243010`, `o243011`, `o243012`, `o243013`, `o243014`.
- Returns `True` for general interactive elevators/levers: `o249001`, `o249002`, `o248001`.
- `is_target_cage` MUST NOT include `o24301*`.

---

## 2. Lady Maria Armor Rigging Contract (`deploy_retro_armors.py` / FLVER Processor)

### Target Parts:
- Headwear: `hd_f_9300.partsbnd.dcx`, `hd_m_9300.partsbnd.dcx`
- Garb: `bd_f_9300.partsbnd.dcx`, `bd_m_9300.partsbnd.dcx`

#### Cloth Physics Mode Guarantees:
- `_c.hkx` and `_c.clm2` remain packed in the container.
- Material assignments for feather and mantle meshes retain `_Cloth.mtd`.

#### Flat Stiff Mode Guarantees:
- In `hd_*_9300`: Bone 3 (`HD_*_9300_feather1`) and Bone 4 (`HD_*_9300_feather2`) parent index set to Bone 0 (`Head`).
- In `bd_*_9300`: Unparented dummy mantle bones have their parent indices reassigned to Bone 2 (`Spine2`) or Bone 3 (`Neck`).
- No bone referenced by active vertices has `parent_index == -1`.
