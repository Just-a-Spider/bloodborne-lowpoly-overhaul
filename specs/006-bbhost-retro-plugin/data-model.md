# Data Model: bbhost Migration & Pure Retro Plugin

**Feature**: `006-bbhost-retro-plugin`
**Date**: 2026-11-11

## Entities & Configuration Schemas

### 1. Plugin Configuration (`[lowpoly_overhaul]`)

Persistent options stored in `bbhost.toml` (or tuned live via the F9 overlay menu):

| Field | Type | Default | Valid Range / Choices | Description |
|---|---|---|---|---|
| `enabled` | `bool` | `true` | `true`, `false` | Master enable switch for the overhaul plugin |
| `snap_resolution` | `string` | `"240p"` | `"Off"`, `"120p"`, `"240p"`, `"360p"`, `"480p"` | Screen-space vertex jitter grid resolution |
| `affine_mapping` | `bool` | `true` | `true`, `false` | Enables perspective-incorrect (affine) texture warping |
| `luminance_dither` | `bool` | `true` | `true`, `false` | Enables 4x4 Bayer dithering with locked chroma ratio |
| `point_filter` | `bool` | `true` | `true`, `false` | Forces nearest-neighbor sampling on 3D textures |
| `colour_8bit` | `bool` | `true` | `true`, `false` | Quantizes color targets to RGBA8 (color banding) |
| `audio_crush` | `string` | `"Off"` | `"Off"`, `"PS1"`, `"Crunchy"`, `"Custom"` | Old-hardware sound downsampling & lowpass filter |

### 2. Dither Compute Pipeline Context (`RenderComputeContext`)

Vulkan compute infrastructure managed in `lowpoly_overhaul.so` for `on_render`:

| Attribute | Type | Description |
|---|---|---|
| `device` | `VkDevice` | Target Vulkan logical device obtained from `BbRenderCall` |
| `dither_pipeline` | `VkPipeline` | Compiled compute pipeline for luminance-locked Bayer dither |
| `pipeline_layout` | `VkPipelineLayout` | Layout describing push constants (extent, level count) and storage bindings |
| `descriptor_set` | `VkDescriptorSet` | Descriptor set binding input/output frame image views |
| `target_extent` | `VkExtent2D` | Dimensions of the rendered 3D picture target (`BbRenderImage`) |

### 3. Shader Override Tracker (`ShaderOverrideEntry`)

In-memory cache tracking intercepted material pixel shaders:

| Attribute | Type | Description |
|---|---|---|
| `shader_id` | `std::string` | Name or lift hash of the pixel shader (e.g. `GXShader@hash.ps`) |
| `has_stage_input` | `bool` | Indicates whether shader declares a `StageInput` structure |
| `patched_source` | `std::string` | Generated HLSL with `noperspective` attribute interpolators |
| `status` | `int` | Current compiler state (`BB_SHADER_WAITING`, `BB_SHADER_NONE`, `BB_SHADER_REFUSED`) |

### 4. Runner Migration State (`MigrationState`)

Tracks state during host binary replacement:

| State | Prerequisites | Transitions To | Post-Conditions |
|---|---|---|---|
| `PreCheck` | Confirm saves exist in `~/.local/share/bbhost/data/saves` | `BackupConfig` | Saves verified untouched |
| `BackupConfig` | Read existing `bbhost.toml` | `RetireLegacy` | Config saved to `bbhost.toml.bak` |
| `RetireLegacy` | Legacy directory `/home/andre/Games/bbhost` exists | `DeployV0232` | Legacy binary folder removed |
| `DeployV0232` | `bbhost-src` builds cleanly via CMake/Ninja | `InstallWrapper` | Binaries and assets placed in `/home/andre/Games/bbhost` |
| `InstallWrapper` | Runner executable present | `Ready` | `/home/andre/.local/bin/bbhost` and `.desktop` registered |

### 5. Save Import Container (`SaveImportRecord`)

Defines parameters for importing `SPRJ0005` save files from `bbport` to `bbhost`:

| Property | Type | Description |
|---|---|---|
| `source_dir` | `Path` | `~/.local/share/bbport/user/savedata/1/CUSA00207/SPRJ0005` |
| `dest_dir` | `Path` | `~/.local/share/bbhost/data/saves/SPRJ0005` |
| `backup_dir` | `Path` | `~/.local/share/bbhost/data/saves/SPRJ0005.pre_import_bak_<timestamp>` |
| `required_files` | `List[str]` | `["userdata0000", "backup0000", "backup0010"]` |
| `file_size_bytes` | `int` | `userdata0000`: 1,310,720 bytes; `backup0010`: 262,144 bytes |
| `validation_hash` | `str` | SHA256 of imported save files verified before and after copy |

