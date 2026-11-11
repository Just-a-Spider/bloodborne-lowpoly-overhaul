# Contract: Modular Packaging CLI

**Feature**: `002-fix-dungeon-props-modularize`  
**Target Tool**: `tools/pipeline/package_modular_mods.py`  

---

## 1. Command Syntax

```bash
uv run python tools/pipeline/package_modular_mods.py [OPTIONS]
```

## 2. Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--pillar <NAME>` | `str` | `all` | Specific pillar to package (`maps`, `props`, `armors-cloth`, `armors-stiff`, `characters`, `hud`, or `all`). |
| `--out-dir <PATH>` | `Path` | `mods/` | Target directory for generated modular mod packages. |
| `--clean` | `flag` | `False` | Clean stale assets from destination mod directories before copying. |
| `--dry-run` | `flag` | `False` | Analyze files and print manifest statistics without writing to disk. |

---

## 3. Directory Outputs & Isolation Matrix

When `--pillar all` executes, exactly five independent mod directories are populated under `mods/`:

```text
mods/
├── Bloodborne Retro Maps/
│   ├── mod.json
│   └── dvdroot_ps4/map/
├── Bloodborne Retro Props and Objects/
│   ├── mod.json
│   └── dvdroot_ps4/obj/
├── Bloodborne Retro Armors and Weapons - Cloth Physics/
│   ├── mod.json
│   └── dvdroot_ps4/parts/
├── Bloodborne Retro Armors and Weapons - Flat Stiff/
│   ├── mod.json
│   └── dvdroot_ps4/parts/
├── Bloodborne Retro Characters/
│   ├── mod.json
│   └── dvdroot_ps4/chr/
└── Bloodborne Retro HUD and UI/
    ├── mod.json
    └── dvdroot_ps4/menu/
```

### Invariants:
1. No mod folder may cross-contaminate another folder's subpath (e.g. `obj/` files MUST NEVER appear inside `Bloodborne Retro Maps/`).
2. Each package MUST include a valid `mod.json` containing `name`, `version`, `pillar`, and `file_count`.
3. Standalone toggle: Any single mod folder enabled in `bbport` MUST load cleanly without missing folder errors.
