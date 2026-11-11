# Contract: Props Pipeline CLI

**Feature**: `002-fix-dungeon-props-modularize`  
**Target Tool**: `tools/pipeline/batch_blender_demake_obj.py` and `tools/repair_objects_clean.py`  

---

## 1. Command Syntax

```bash
uv run python tools/pipeline/batch_blender_demake_obj.py [OPTIONS]
```

## 2. Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--only <PATTERN>` | `str` | `None` | Filter target object IDs by glob (e.g. `'o2902*'`, `'o297210'`, `'o32205*'`). |
| `--cages` | `flag` | `False` | Run demake targeting specifically dungeon cages and torture assemblies. |
| `--cadavers` | `flag` | `False` | Run stabilization and demake specifically on cadaver wastes and corpse heaps. |
| `--deploy` | `flag` | `False` | Write outputs directly to `CUSA03173-PSX/dvdroot_ps4/obj/`. Default is dry run/stage. |
| `--ratio <FLOAT>` | `float` | `0.25` | Target triangle reduction ratio for geometry decimation. |
| `--workers <INT>` | `int` | `8` | Number of parallel worker processes. |

---

## 3. Exit Codes & Behavioral Invariants

- **`0`**: Successful execution; all requested models processed or verified.
- **`1`**: Invalid arguments, missing vanilla sources, or unhandled file corruption.
- **`2`**: Geometric invariant failure (mesh explosion detected with max edge $> 2.0$m, or missing collision).

### Strict Behavioral Invariants:
1. `CUSA03173/` is strictly read-only.
2. Havok collision (`.hkx`) is 100% bit-for-bit preserved.
3. Interaction dummies (`Dummy` entries in FLVER) are bit-for-bit preserved.
4. Animated object binders (`.anibnd`) remain intact and linked.
