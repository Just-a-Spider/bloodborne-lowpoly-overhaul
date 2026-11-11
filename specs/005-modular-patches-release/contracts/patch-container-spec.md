# Binary Patch Container Specification: BBLPO01

**Feature**: Modular Mod Release & Patch Distribution Artifacts (`005-modular-patches-release`)
**Date**: 2026-11-11

## 1. File Layout

A `.patch` container is a single binary file divided into three sequential sections:

```text
+-------------------+---------------------+-------------------------+-------------------------+
| MAGIC (8 bytes)   | Meta Length (4 B)   | JSON Metadata (N bytes) | Payload Stream (M bytes)|
+-------------------+---------------------+-------------------------+-------------------------+
0                   8                     12                        12 + N
```

### Section 1: Magic Bytes (8 bytes)
- Offset: `0`
- Value: `b"BBLPO01\x00"` (`0x42 0x42 0x4C 0x50 0x4F 0x30 0x31 0x00`)
- Identifies file as a Bloodborne Low-Poly Overhaul XOR Patch Container version 1.

### Section 2: Metadata Length (4 bytes)
- Offset: `8`
- Value: Unsigned 32-bit integer, Little-Endian (`struct.unpack("<I", ...)`).
- Defines byte length `N` of following JSON metadata section.

### Section 3: Metadata JSON (N bytes)
- Offset: `12`
- Encoding: UTF-8.
- Contains dictionary with schema defined in `data-model.md`.

### Section 4: Payload Stream (M bytes)
- Offset: `12 + N`
- Contains contiguous raw bytes for each entry defined in `files` list.
- Byte range for file entry `i`: `[12 + N + entry.offset, 12 + N + entry.offset + entry.length)`.

## 2. Reversal and Reconstruction Invariant

For every file in manifest:
- If `type == "xor_delta"`:
  ```python
  min_len = min(len(delta_bytes), len(vanilla_bytes))
  reconstructed = (delta_int ^ vanilla_int) + delta_bytes[min_len:]
  ```
- If `type == "full"`:
  ```python
  reconstructed = delta_bytes
  ```
- Assert: `sha256(reconstructed) == entry.target_sha256`
