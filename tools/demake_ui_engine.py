"""
Master Retro UI & HUD Demake Engine for Bloodborne PSX (shadPS4 / bbhost).

Transforms Bloodborne's HD Scaleform menu and HUD textures into authentic retro pixel art:
1. Decodes BC7 and BC1 UI texture atlases (MENU_Common_*, MENU_Icon_*).
2. Downsamples to authentic retro resolution with 15-bit RGB555 retro color depth quantization.
3. Nearest-neighbor upscales back to atlas canvas (crisp, chunky retro texels).
4. Re-encodes with fast C++ ispc_texcomp (BC7) and vectorized encode_rgba_to_bc1 (BC1).
5. Preserves button prompts (KG_*) and language markers for UI readability.
6. Swizzles to PS4 GCN Morton micro-tiles across all mip levels.
"""

import sys, os, struct, time
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from ps4_swizzle import deswizzle_level, swizzle_level
from demake_color_engine import get_mip_sizes, decode_bc1_to_rgba, encode_rgba_to_bc1

import texture2ddecoder
import ispc_texcomp
from soulstruct.dcx import decompress, compress

VANILLA_MENU_DIR = Path("CUSA03173/dvdroot_ps4/menu")
SANDBOX_MENU_DIR = Path("CUSA03173-PSX/dvdroot_ps4/menu")

def demake_ui_rgba(rgba: np.ndarray, downscale_factor: int = 2) -> np.ndarray:
    """Applies authentic 15-bit RGB555 retro pixelation to an uncompressed RGBA image."""
    h, w, _ = rgba.shape
    retro_w = max(16, w // downscale_factor)
    retro_h = max(16, h // downscale_factor)

    im_orig = Image.fromarray(rgba)
    im_small = im_orig.resize((retro_w, retro_h), Image.Resampling.BILINEAR)

    arr = np.array(im_small)
    # 15-bit RGB555 quantization (32 levels per channel)
    arr[:, :, :3] = (arr[:, :, :3] >> 3) << 3

    im_quant = Image.fromarray(arr)
    # Nearest-neighbor upscale back to canvas
    im_psx = im_quant.resize((w, h), Image.Resampling.NEAREST)
    return np.array(im_psx)

def process_ui_tpf(tpf_bytes: bytes, downscale_factor: int = 2, icons_only: bool = True, verbose: bool = True) -> bytearray:
    """Processes in-memory UI TPF data with retro pixel art conversion for BC7 and BC1."""
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b'TPF\x00':
        return tpf

    bc7_settings = ispc_texcomp.BC7EncSettings.from_profile('alpha_veryfast')

    tex_count = struct.unpack('<I', tpf[8:12])[0]
    modified_count = 0

    for i in range(tex_count):
        e = tpf[0x10 + i*36 : 0x10 + (i+1)*36]
        tex_off, tex_sz, unk1, unk2, unk3, unk4, str_off = struct.unpack('<7I', e[:28])

        curr = str_off
        while curr < len(tpf) - 1:
            if tpf[curr] == 0 and tpf[curr+1] == 0: break
            curr += 2
        name = tpf[str_off:curr].decode('utf-16le', errors='ignore')
        w = unk2 & 0xFFFF
        h = (unk2 >> 16) & 0xFFFF
        fmt = unk1 & 0xFF

        # Filter: by default demake icons only to keep Scaleform 9-slice borders, text frames, and prompts pristine
        if icons_only and not name.startswith('MENU_Icon_'):
            continue

        # Skip small controller button prompts and language markers to maintain legibility
        if name.startswith('KG_') or name.startswith('MENU_LNG_') or max(w, h) <= 64:
            continue

        # Unpack num_mips (unk3) from FromSoftware TPF record (UI textures are strictly 1 mip level)
        num_mips = max(1, unk3)
        bpb = 16 if fmt == 0x66 else 8
        mips = get_mip_sizes(w, h, bpb)[:num_mips]
        w0, h0, pw0, ph0, sz0 = mips[0]

        # 1. Deswizzle Mip 0
        linear0 = deswizzle_level(tpf[tex_off : tex_off + sz0], w0, h0, bpb)

        # 2. Decode to RGBA
        if fmt == 0x66: # BC7
            bgra = np.frombuffer(texture2ddecoder.decode_bc7(bytes(linear0), pw0, ph0), dtype=np.uint8).reshape(ph0, pw0, 4)
            rgba0 = bgra[:h0, :w0, [2, 1, 0, 3]].copy()
        elif fmt in (0, 1): # BC1
            rgba0 = decode_bc1_to_rgba(linear0, pw0, ph0)[:h0, :w0]
        else:
            continue

        # 3. Apply Retro retro Pixelation
        rgba_psx = demake_ui_rgba(rgba0, downscale_factor=downscale_factor)
        im_psx_master = Image.fromarray(rgba_psx)

        # 4. Generate & Re-encode ONLY the authored mips (num_mips)
        curr_off = tex_off
        for idx, (w_i, h_i, pw_i, ph_i, sz_i) in enumerate(mips):
            im_mip = im_psx_master.resize((w_i, h_i), Image.Resampling.NEAREST)
            arr_mip = np.array(im_mip)

            pad_arr = np.zeros((ph_i, pw_i, 4), dtype=np.uint8)
            pad_arr[:h_i, :w_i] = arr_mip
            if pw_i > w_i: pad_arr[:h_i, w_i:pw_i] = arr_mip[:, -1:, :]
            if ph_i > h_i: pad_arr[h_i:ph_i, :] = pad_arr[h_i-1:h_i, :]

            if fmt == 0x66: # BC7
                surf = ispc_texcomp.RGBASurface(pad_arr.tobytes(), pw_i, ph_i, pw_i * 4)
                linear_mip = ispc_texcomp.compress_blocks_bc7(surf, bc7_settings)
            else: # BC1
                linear_mip = encode_rgba_to_bc1(pad_arr)

            swizzled_mip = swizzle_level(linear_mip, w_i, h_i, bpb)
            tpf[curr_off : curr_off + sz_i] = swizzled_mip
            curr_off += sz_i

        # Cleanly zero-fill alignment padding within tex_sz to prevent spilling into adjacent textures
        if curr_off < tex_off + tex_sz:
            tpf[curr_off : tex_off + tex_sz] = b'\x00' * (tex_off + tex_sz - curr_off)

        modified_count += 1
        if verbose:
            print(f"  [UI] Demaked {name} ({w}x{h}, fmt=0x{fmt:02x}) -> retro {w//downscale_factor}x{h//downscale_factor} texels (mips={num_mips})")

    return tpf

def demake_ui_file(src_path: Path, dst_path: Path, downscale_factor: int = 2, icons_only: bool = True) -> bool:
    """Demakes a .tpf.dcx UI archive."""
    if not src_path.exists():
        print(f"Error: Source file not found: {src_path}")
        return False

    mode_str = "Icons Only" if icons_only else "All UI (Full)"
    print(f"\nProcessing UI Archive: {src_path.name} (mode: {mode_str}, factor: {downscale_factor}x)...")
    start_t = time.time()
    raw_data, dcx_type = decompress(str(src_path))
    demade_tpf = process_ui_tpf(raw_data, downscale_factor=downscale_factor, icons_only=icons_only, verbose=True)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    comp_data = compress(bytes(demade_tpf), dcx_type=dcx_type)
    dst_path.write_bytes(comp_data)
    elapsed = time.time() - start_t
    print(f"[SUCCESS] Demaked {src_path.name} in {elapsed:.2f}s -> {dst_path}")
    return True

# Compatibility alias
demake_common_ui_tpf = demake_ui_file

if __name__ == '__main__':
    target = VANILLA_MENU_DIR / "common.tpf.dcx"
    dest = SANDBOX_MENU_DIR / "common.tpf.dcx"
    factor = 2
    icons_only = True

    for arg in sys.argv[1:]:
        if arg == '--all-ui':
            icons_only = False
        elif arg == '--icons-only':
            icons_only = True
        elif arg.isdigit():
            factor = int(arg)

    demake_ui_file(target, dest, downscale_factor=factor, icons_only=icons_only)
