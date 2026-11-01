"""
PS4 GCN Morton Texture Swizzle / Deswizzle Engine.
Decodes and encodes PS4 tiled texture layouts (8x8 blocks / 32x32 pixels micro-tiles).
"""

import numpy as np

# Precompute 1D permutation indices for an 8x8 Morton micro-tile
_MX = np.array([(d >> 0 & 1) | ((d >> 2 & 1) << 1) | ((d >> 4 & 1) << 2) for d in range(64)])
_MY = np.array([(d >> 1 & 1) | ((d >> 3 & 1) << 1) | ((d >> 5 & 1) << 2) for d in range(64)])

def morton_interleave(x: int, y: int) -> int:
    """Interleaves bits of two 3-bit integers into a 6-bit Morton code (0..63)."""
    d = 0
    for i in range(3):
        d |= ((x >> i) & 1) << (2 * i)
        d |= ((y >> i) & 1) << (2 * i + 1)
    return d

def morton_deinterleave(d: int) -> tuple[int, int]:
    """Deinterleaves a 6-bit Morton code into two 3-bit integers (x, y)."""
    x, y = 0, 0
    for i in range(3):
        x |= ((d >> (2 * i)) & 1) << i
        y |= ((d >> (2 * i + 1)) & 1) << i
    return x, y

# Precompute 64-entry lookups for speed
MORTON_ENCODE = [morton_interleave(x, y) for y in range(8) for x in range(8)]
MORTON_DECODE = [morton_deinterleave(d) for d in range(64)]

def deswizzle_level(data: bytes, width: int, height: int, bpb: int) -> bytearray:
    pad_w = max(32, (width + 31) & ~31)
    pad_h = max(32, (height + 31) & ~31)
    macro_x, macro_y = pad_w // 32, pad_h // 32
    num_tiles = macro_x * macro_y

    # View input as (macro_y, macro_x, 64, bpb)
    src = np.frombuffer(data[:num_tiles * 64 * bpb], dtype=np.uint8)
    tiles = src.reshape(macro_y, macro_x, 64, bpb)

    # Scatter 64 Morton blocks into (macro_y, 8, macro_x, 8, bpb)
    out = np.zeros((macro_y, 8, macro_x, 8, bpb), dtype=np.uint8)
    out[:, _MY, :, _MX, :] = tiles.transpose(2, 0, 1, 3)
    return bytearray(out.tobytes())

def swizzle_level(data: bytes, width: int, height: int, bpb: int) -> bytearray:
    pad_w = max(32, (width + 31) & ~31)
    pad_h = max(32, (height + 31) & ~31)
    macro_x, macro_y = pad_w // 32, pad_h // 32

    # View linear blocks as (macro_y, 8, macro_x, 8, bpb)
    src = np.frombuffer(data[:macro_y * 8 * macro_x * 8 * bpb], dtype=np.uint8)
    grid = src.reshape(macro_y, 8, macro_x, 8, bpb)

    # Gather along Morton curve into (macro_y, macro_x, 64, bpb)
    tiles = grid[:, _MY, :, _MX, :].transpose(1, 2, 0, 3)
    return bytearray(tiles.tobytes())
