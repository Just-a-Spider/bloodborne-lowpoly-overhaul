# Quickstart & Verification Guide: Research Hall Stairs & Maria Cloth

## Prerequisites
- Working directory: `/home/andre/Games/Bloodborne`
- Hermetic Python environment: `uv run python ...`

## 1. Apply Pipeline Fixes and Restore Assets
```bash
# 1. Update batch_blender_demake_obj.py with bypass rules
# 2. Restore vanilla stair props into CUSA03173-PSX
uv run python -c "
import shutil
from pathlib import Path

vanilla_obj = Path('CUSA03173/dvdroot_ps4/obj')
target_obj = Path('CUSA03173-PSX/dvdroot_ps4/obj')
props = ['o350501', 'o350502', 'o350503', 'o350504', 'o353006', 'o353011', 'o353013', 'o243010', 'o243011', 'o243012', 'o243013', 'o243014']
for p in props:
    src = vanilla_obj / f'{p}.objbnd.dcx'
    if src.exists():
        shutil.copy2(src, target_obj / f'{p}.objbnd.dcx')
        print(f'Restored {p}')
"
```

## 2. Fix Lady Maria Hat and Garb
```bash
# Verify and package Maria set 9300 for both Cloth and Stiff editions
uv run python tools/pipeline/deploy_retro_armors.py
```

## 3. Modular Mod Packaging & Differential Patch
```bash
# Repack modular mod folders
uv run python tools/pipeline/package_modular_mods.py

# Generate differential release patch
uv run python tools/pipeline/create_patch.py

# Verify patch application
uv run pytest tests/test_apply_patch.py
```
