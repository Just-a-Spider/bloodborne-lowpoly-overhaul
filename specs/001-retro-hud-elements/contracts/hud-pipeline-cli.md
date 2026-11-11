# Contract: HUD Demake CLI Tools

## 1. Batch HUD Demake Pipeline (`tools/pipeline/batch_demake_hud.py`)

### Synopsis

```bash
uv run python tools/pipeline/batch_demake_hud.py [OPTIONS]
```

### Options

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--vanilla` | `Path` | `CUSA03173` | Path to pristine vanilla retail game root (strictly read-only) |
| `--sandbox` | `Path` | `CUSA03173-PSX` | Path to active mod sandbox root |
| `--mod` | `Path` | `mods/Bloodborne Low-Poly Overhaul` | Path to standalone mod distribution directory |
| `--factor` | `int` | `2` | Downscale pixel factor for demaked UI atlases ($D \in \{2, 4\}$) |
| `--verify` | `flag` | `True` | Automatically executes verification test suite upon completion |
| `--verbose` | `flag` | `False` | Prints per-texture demake metrics and timing |

### Standard Output & Exit Codes

- **Exit Code 0**: All target menu archives demaked, swizzled, repacked, and passed verification.
- **Exit Code 1**: Invalid input arguments, missing source files, or file IO error.
- **Exit Code 2**: Verification assertion failure on repacked container.

### Console Output Format

```text
================================================================================
BLOODBORNE RETRO HUD & UI DEMAKE PIPELINE
================================================================================
Source Vanilla:     CUSA03173/dvdroot_ps4/menu/common.tpf.dcx
Destination Target: CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx
Mod Distribution:   mods/Bloodborne Low-Poly Overhaul/dvdroot_ps4/menu/common.tpf.dcx
Downscale Factor:   2x (4x for >=2048px)
Color Quantization: 15-bit RGB555 (32 levels/channel)
Prompt Whitelist:   24 KG_* prompts preserved pristine

[1/3] Decompressing common.tpf.dcx (DCX_DFPR, 9.81 MB)...
[2/3] Processing 65 texture records:
      - Demaked: 38 textures (MENU_Common_*, MENU_Icon_*)
      - Preserved: 27 textures (KG_*, MENU_LNG_*)
[3/3] Compressing & Deploying:
      - Backup created: common.tpf.dcx.bak
      - Sandbox written: CUSA03173-PSX/.../common.tpf.dcx (5.42 MB)
      - Mod package updated: mods/.../common.tpf.dcx
--------------------------------------------------------------------------------
Verification: PASS (15/15 tests passing, exit code 0)
Elapsed Time: 3.82s
================================================================================
```

---

## 2. HUD Automated Verification Harness (`tools/verify_hud_demake.py`)

### Synopsis

```bash
uv run python tools/verify_hud_demake.py [OPTIONS]
```

### Options

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--target` | `Path` | `CUSA03173-PSX/.../common.tpf.dcx` | Path to target modified container |
| `--tier` | `int` | `None` | Restrict execution to specific tier (`1`–`4`) |
| `--json` | `flag` | `False` | Output structured JSON test results to stdout |
| `--exit-zero` | `flag` | `False` | Force exit code 0 even on test failure (for diagnostic CI) |

### JSON Schema Output (when `--json` active)

```json
{
  "timestamp": "2026-11-08T15:20:00Z",
  "target_path": "CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx",
  "total_tests": 15,
  "passed": 15,
  "failed": 0,
  "skipped": 0,
  "tiers": {
    "tier1_container": {"passed": 4, "failed": 0},
    "tier2_scaleform": {"passed": 4, "failed": 0},
    "tier3_palette": {"passed": 4, "failed": 0},
    "tier4_immutability": {"passed": 3, "failed": 0}
  },
  "verdict": "PASS"
}
```
