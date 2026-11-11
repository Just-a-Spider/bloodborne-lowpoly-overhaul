# Data Model: Retro HUD & Interaction Elements Demake

## Overview

This document specifies the core entities, relationships, attributes, and validation invariants for the HUD texture demake pipeline.

---

### Entities

#### 1. `UITextureRecord`
Represents an individual authored texture atlas or sprite inside a FromSoftware TPF binary container.

| Field | Type | Description | Invariants |
| :--- | :--- | :--- | :--- |
| `name` | `str` | Texture identifier (e.g. `MENU_Common_00001`, `KG_OK`) | UTF-16LE encoded in TPF header |
| `width` | `int` | Canvas pixel width | Power of 2 or block-aligned ($W \pmod 4 == 0$) |
| `height` | `int` | Canvas pixel height | Power of 2 or block-aligned ($H \pmod 4 == 0$) |
| `format` | `int` | Compression codec identifier | `0x66` (BC7) or `0x00` / `0x01` (BC1) |
| `num_mips` | `int` | Number of authored mip levels | Strictly `1` for all UI textures |
| `tex_offset` | `int` | Byte offset to payload within uncompressed TPF | 16-byte aligned |
| `tex_size` | `int` | Allocated payload byte capacity | Equal to or greater than encoded payload size |
| `raw_bytes` | `bytes` | Swizzled GPU texture payload | Length matches allocated mip level size |

---

#### 2. `UIProcessingRule`
Governs how the demake engine transforms or preserves a specific texture record.

| Field | Type | Description | Invariants |
| :--- | :--- | :--- | :--- |
| `pattern` | `str` | Name prefix or regex match (`MENU_Common_*`, `KG_*`) | Non-empty |
| `policy` | `Enum` | Processing action (`DEMAKE_RETRO`, `BYPASS_PRISTINE`) | Valid enum value |
| `downscale_factor` | `int` | Integer downsampling divisor ($D$) | $D \in \{2, 4\}$ for demaked, $1$ for bypassed |
| `palette_depth` | `int` | Color quantization bit depth | $15$ bits (RGB555) |
| `alpha_handling` | `Enum` | Alpha preservation policy | `PRESERVE_8BIT` (unquantized cutout mask) |
| `upscale_filter` | `Enum` | Re-upscale interpolation filter | `NEAREST_NEIGHBOR` (chunky retro texels) |

---

#### 3. `HUDAtlasManifest`
Inventory of all 65 textures in `common.tpf.dcx`, grouped by functional role.

| Group Name | Texture Prefix | Count | Target Policy | Downscale Factor |
| :--- | :--- | :--- | :--- | :--- |
| **Vitals & UI Atlases** | `MENU_Common_00001` .. `00130` | 20 | `DEMAKE_RETRO` | 2x (4x for 2048px) |
| **Item & Weapon Icons** | `MENU_Icon_00001` .. `07001` | 16 | `DEMAKE_RETRO` | 2x |
| **Loading & Map Art** | `MENU_Common_Loading*` | 2 | `DEMAKE_RETRO` | 2x |
| **Controller Prompts** | `KG_*` (`KG_OK`, `KG_Cancel`, etc.) | 24 | `BYPASS_PRISTINE` | 1x (Pristine) |
| **Localization Markers** | `MENU_LNG_*` (`CN`, `KR`, `TW`) | 3 | `BYPASS_PRISTINE` | 1x (Pristine) |
| **Total Inventory** | — | **65** | — | — |

---

#### 4. `ProcessedMenuArchive`
Lifecycle container representing a processed, validated menu DCX archive ready for deployment.

| Field | Type | Description |
| :--- | :--- | :--- |
| `source_path` | `Path` | Pristine source file in `CUSA03173/dvdroot_ps4/menu/` |
| `destination_path` | `Path` | Target sandbox file in `CUSA03173-PSX/dvdroot_ps4/menu/` |
| `backup_path` | `Path` | Fallback backup (`.bak`) in sandbox directory |
| `dcx_type` | `str` | Compression type (`DCX_DFPR` / `DCX_KRAK`) |
| `total_textures` | `int` | Count of textures in archive (65) |
| `modified_count` | `int` | Count of modified textures (38) |
| `bypassed_count` | `int` | Count of bypassed pristine textures (27) |
| `status` | `Enum` | Processing status (`PENDING`, `SUCCESS`, `VALIDATION_FAILED`) |

---

### Invariants & Validation Rules

1. **Canvas Preservation Invariant**:
   $$\forall T \in \text{Textures}, \quad \text{dim}_{\text{demade}}(T) == \text{dim}_{\text{vanilla}}(T)$$
   The pixel width and height of each atlas in the TPF header MUST match the pristine vanilla dimensions bit-for-bit.

2. **Single Mip Invariant**:
   $$\forall T \in \text{Textures}, \quad \text{num\_mips}(T) == 1$$
   No secondary mip levels may be written into UI texture records.

3. **RGB555 Quantization Rule**:
   $$\forall (r, g, b) \in \text{RGB}_{\text{demade}}, \quad r \pmod 8 == 0, \quad g \pmod 8 == 0, \quad b \pmod 8 == 0$$
   Every RGB color component in demaked atlases must be an exact multiple of 8 (32 discrete levels).

4. **Controller Prompt Whitelist Invariant**:
   $$\forall T \in \text{Textures} \text{ where } T.\text{name} \text{ starts with } \text{"KG\_"}, \quad \text{SHA256}(T_{\text{payload}}) == \text{SHA256}(T_{\text{vanilla}})$$
   All button prompt textures MUST remain bit-for-bit identical to vanilla to prevent input ambiguity.

5. **Payload Boundary Invariant**:
   $$\text{offset}(T) + \text{size}(\text{payload}) \le \text{offset}(T) + \text{tex\_sz}(T)$$
   Any unused capacity within `tex_sz` MUST be zero-filled to prevent uninitialized memory leakage.
