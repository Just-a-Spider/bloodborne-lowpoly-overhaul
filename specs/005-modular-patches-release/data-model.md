# Data Model: Modular Mod Release & Patch Distribution

**Feature**: Modular Mod Release & Patch Distribution Artifacts (`005-modular-patches-release`)
**Date**: 2026-11-11

## 1. Entities

### `PatchContainer`
Represents a compiled `.patch` distribution artifact containing metadata and byte-level diffs.

| Field | Type | Description |
|---|---|---|
| `magic` | `bytes[8]` | Format identifier: `b"BBLPO01\x00"` |
| `meta_len` | `uint32` | Little-endian 32-bit unsigned integer length of JSON metadata |
| `meta_json` | `string` | UTF-8 encoded JSON payload containing container metadata and file manifests |
| `payload` | `bytes` | Concatenated XOR differential and standalone file payloads starting at `offset = 12 + meta_len` |

### `ManifestMetadata`
Structured JSON payload inside `PatchContainer`.

| Field | Type | Description |
|---|---|---|
| `format` | `string` | `"BBLPO_XOR_CONTAINER"` |
| `version` | `string` | Patcher version, e.g. `"1.0.0"` |
| `created_at` | `string` | ISO 8601 UTC timestamp |
| `game_version` | `string` | Supported base game version, e.g. `"1.09"` |
| `vanilla_title` | `string` | Title descriptor: `"Bloodborne (CUSA03173)"` |
| `mod_name` | `string` (optional) | Canonical mod directory name (e.g. `"Bloodborne Retro Maps"`) |
| `total_files` | `integer` | Count of entries in `files` list |
| `files` | `List[ManifestEntry]` | Manifest of files to reconstruct |

### `ManifestEntry`
Metadata descriptor for each target file.

| Field | Type | Description |
|---|---|---|
| `path` | `string` | Relative path inside game directory (e.g. `dvdroot_ps4/menu/menu.tpf.dcx`) |
| `type` | `string` | `"xor_delta"` (modified vanilla file) or `"full"` (new standalone file) |
| `vanilla_size` | `integer` | Byte size of vanilla base game file (0 for `"full"`) |
| `vanilla_sha256` | `string` | Hex SHA256 of vanilla base game file (`""` for `"full"`) |
| `target_size` | `integer` | Byte size of reconstructed target mod file |
| `target_sha256` | `string` | Hex SHA256 of reconstructed target mod file |
| `offset` | `integer` | Byte offset of file payload relative to start of payload stream |
| `length` | `integer` | Byte length of file payload in payload stream |

### `ModularPillarDefinition`
Specification of content constraints per modular pillar.

| Pillar Name | Canonical Directory | Allowed Subpaths | Forbidden Subpaths | Patch File |
|---|---|---|---|---|
| Maps | `Bloodborne Retro Maps` | `map` | `obj`, `parts`, `chr`, `menu`, `msg`, `script` | `bloodborne_retro_maps.patch` |
| Props & Objects | `Bloodborne Retro Props and Objects` | `obj` | `map`, `parts`, `chr`, `menu`, `msg`, `script` | `bloodborne_retro_props.patch` |
| Armors (Cloth) | `Bloodborne Retro Armors and Weapons - Cloth Physics` | `parts` | `map`, `obj`, `chr`, `menu`, `msg`, `script` | `bloodborne_retro_armors_cloth.patch` |
| Armors (Stiff) | `Bloodborne Retro Armors and Weapons - Flat Stiff` | `parts` | `map`, `obj`, `chr`, `menu`, `msg`, `script` | `bloodborne_retro_armors_stiff.patch` |
| Characters | `Bloodborne Retro Characters` | `chr` | `map`, `obj`, `parts`, `menu`, `msg`, `script` | `bloodborne_retro_characters.patch` |
| HUD & UI | `Bloodborne Retro HUD and UI` | `menu` | `map`, `obj`, `parts`, `chr`, `msg`, `script` | `bloodborne_retro_hud.patch` |

### `ModLoadOrderConfig` (`mods.json`)
Structure consumed by `bbport` / mod managers.

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

## 2. Validation Invariants
1. `ManifestEntry.offset` must strictly equal the running cumulative sum of previous entry lengths.
2. For all `type == "xor_delta"`, `length == max(vanilla_size, target_size)`.
3. In `apply_patch.py`, reconstructed bytes `M` inverted against vanilla `V` (`M = delta ^ V`) must satisfy `sha256(M) == target_sha256`.
4. Every modular patch must contain zero files under any forbidden subpath for its pillar.
