# Contract: HUD Binary Texture & Container Format

## 1. TPF Container Binary Layout

All Bloodborne UI assets are packaged in FromSoftware TPF (Texture Pack Format) archives compressed with DCX (`DCX_DFPR`).

### Container Header Structure

| Offset | Size (Bytes) | Type | Field Description | Expected Value |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | 4 | `char[4]` | Container Magic | `b"TPF\x00"` |
| `0x04` | 4 | `uint32` | Total data size (uncompressed) | Total container byte length |
| `0x08` | 4 | `uint32` | Texture Count ($N$) | Strictly `65` for `common.tpf` |
| `0x0C` | 4 | `uint32` | Platform Flag / Encoding | `0x02` / `0x00` |
| `0x10` | $36 \times N$ | `struct[36]` | Texture Header Entries array | Array of 36-byte records |

---

### Texture Entry Record (`struct[36]`)

| Record Offset | Size | Type | Field Description | Invariants |
| :--- | :--- | :--- | :--- | :--- |
| `+0x00` | 4 | `uint32` | `tex_offset` | 16-byte aligned payload pointer |
| `+0x04` | 4 | `uint32` | `tex_size` | Allocated byte capacity for texture |
| `+0x08` | 4 | `uint32` | `format_flags` | Low byte: `0x66` (BC7) or `0x00` (BC1) |
| `+0x0C` | 4 | `uint32` | `dimensions` | Low 16 bits = Width ($W$), High 16 bits = Height ($H$) |
| `+0x10` | 4 | `uint32` | `num_mips` | Strictly `1` for Scaleform UI |
| `+0x14` | 4 | `uint32` | `unk4` | Standard flags (`0x00`) |
| `+0x18` | 4 | `uint32` | `str_offset` | Pointer to UTF-16LE null-terminated texture name |
| `+0x1C` | 8 | `uint32[2]` | `reserved` | Zero padding |

---

## 2. GPU Swizzle Layout & GCN Morton Micro-Tiles

### Morton Interleaving
PS4 GPU hardware (GCN architecture) reads texture blocks in $8\times 8$ pixel micro-tiles rather than linear scanlines.

- **BC7 Textures (16 bytes per $4\times 4$ block)**:
  - Block dimensions: $PW = \lceil W / 4 \rceil$, $PH = \lceil H / 4 \rceil$
  - Swizzle function: `swizzle_level(linear_data, W, H, bpb=16)`
- **BC1 Textures (8 bytes per $4\times 4$ block)**:
  - Block dimensions: $PW = \lceil W / 4 \rceil$, $PH = \lceil H / 4 \rceil$
  - Swizzle function: `swizzle_level(linear_data, W, H, bpb=8)`

### Alignment & Padding Contract
- Payload size for single mip level:
  $$S_0 = \text{max}(1, PW) \times \text{max}(1, PH) \times \text{bpb}$$
- If $S_0 < \text{tex\_size}$, the range $[\text{tex\_offset} + S_0, \text{tex\_offset} + \text{tex\_size})$ MUST be filled with `0x00`.

---

## 3. Scaleform GFX Integration Invariants

1. **UV Coordinate Lock**:
   - `common_base.gfx`, `ingametop.gfx`, `messagebox.gfx`, and `equipment.gfx` map sprites using absolute texel normalized coordinates $[u, v] \in [0.0, 1.0]$.
   - Modifying atlas canvas width or height shifts texel sampling centers, distorting 9-slice borders. All canvas dimensions MUST remain identical to retail originals.

2. **RGB555 Stepping Contract**:
   - Color RGB values must satisfy:
     $$R, G, B \in \{0, 8, 16, 24, \dots, 248\}$$
   - Alpha channel ($A$) remains unquantized $[0, 255]$ to maintain anti-aliased font and frame borders.
