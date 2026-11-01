#!/usr/bin/env python3
"""
inspect_tpf_mips.py - READ-ONLY check of TPF header fields and mip layout.

Purpose: confirm the assumptions needed before we try "drop the top mip levels" on chr textures:
  1. Block size (8 or 16 bytes) can be derived from tex_sz + dimensions, not from the format byte.
  2. Which header field is the mip count (unk3? unk4?).
  3. Whether texture data is packed back to back (so shrinking needs a re-layout) and how
     it is aligned.

It never writes anything. Sources are read from the VANILLA dump (or any path you give).

Usage:
    uv run tools/inspect_tpf_mips.py c1000                  # c1000.chrbnd.dcx (+ c1000_2.tpf.dcx if present)
    uv run tools/inspect_tpf_mips.py c5000
    uv run tools/inspect_tpf_mips.py --path some/file.chrbnd.dcx
    uv run tools/inspect_tpf_mips.py c1000 --target 256     # predicted size if cut down to 256px
"""

import argparse
import math
import struct
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
VANILLA_CHR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "chr"

from demake_color_engine import get_mip_sizes  # same layout code the demake uses


def dcx_read(path):
    data = Path(path).read_bytes()
    if (data[:4] != b"DCX\x00" or data[0x18:0x1C] != b"DCS\x00" or data[0x24:0x28] != b"DCP\x00"
            or data[0x28:0x2C] != b"DFLT" or data[0x44:0x48] != b"DCA\x00"):
        raise ValueError("not a DFLT DCX")
    unc, comp = struct.unpack(">II", data[0x1C:0x24])
    payload = zlib.decompress(data[0x4C: 0x4C + comp])
    if len(payload) != unc:
        raise ValueError("DCX size mismatch")
    return payload


# DXGI_FORMAT numbers -> (name, bytes per 4x4 block). The last word of each 36-byte entry took only
# the values 71/72/80/98/99 in your c1000/c5000 dumps, which are exactly these DXGI codes.
DXGI = {71: ("BC1_UNORM", 8), 72: ("BC1_SRGB", 8), 74: ("BC2_UNORM", 16), 75: ("BC2_SRGB", 16),
        77: ("BC3_UNORM", 16), 78: ("BC3_SRGB", 16), 80: ("BC4_UNORM", 8), 81: ("BC4_SNORM", 8),
        83: ("BC5_UNORM", 16), 84: ("BC5_SNORM", 16), 95: ("BC6H_UF16", 16), 96: ("BC6H_SF16", 16),
        98: ("BC7_UNORM", 16), 99: ("BC7_SRGB", 16)}


def tpf_name(tpf, off):
    cur = off
    while cur < len(tpf) - 1 and not (tpf[cur] == 0 and tpf[cur + 1] == 0):
        cur += 2
    return bytes(tpf[off:cur]).decode("utf-16le", errors="ignore")


def match_levels(w, h, tex_sz):
    """Find (bpb, stored_levels) such that the first k mip levels add up to tex_sz."""
    for bpb in (8, 16):
        chain = get_mip_sizes(w, h, bpb)
        total = 0
        for k, (_w, _h, _pw, _ph, sz) in enumerate(chain, 1):
            total += sz
            if total == tex_sz:
                return bpb, k, chain
            if total > tex_sz:
                break
    return None


def size_after_drop(chain, k_stored, drop):
    return sum(m[4] for m in chain[drop:k_stored])


def levels_to_reach(w, h, target):
    d = 0
    while max(w, h) > target and (w > 1 or h > 1):
        w, h = max(1, w // 2), max(1, h // 2)
        d += 1
    return d


def inspect_tpf(label, tpf, target):
    print(f"\n=== {label}  ({len(tpf)} bytes) ===")
    if tpf[:4] != b"TPF\x00":
        print("  not a TPF (bad magic)")
        return None
    hdr = struct.unpack("<4I", tpf[:16])
    count = hdr[2]
    print(f"  header u32s: {[hex(x) for x in hdr]}  textures={count}")
    rows = []
    for i in range(count):
        e = tpf[0x10 + i * 36: 0x10 + (i + 1) * 36]
        tex_off, tex_sz, unk1, unk2, unk3, unk4, str_off, t0, t1 = struct.unpack("<9I", e)
        name = tpf_name(tpf, str_off)
        w, h = unk2 & 0xFFFF, (unk2 >> 16) & 0xFFFF
        rows.append(dict(i=i, name=name, off=tex_off, sz=tex_sz, fmt=unk1 & 0xFF, unk1=unk1,
                         w=w, h=h, unk3=unk3, unk4=unk4, tail=(t0, t1)))

    print(f"  {'name':26s} {'fmt':>4s} {'unk1':>8s} {'tail1':>5s} {'dxgi':>10s} {'size':>9s} {'WxH':>10s} "
          f"{'bpb':>3s} {'lvls':>4s} {'mipB':>4s}  predicted after cut")
    tally_unk3 = tally_unk4 = matched = 0
    tally_mipb = dxgi_ok = dxgi_bad = dxgi_unknown = single = 0
    total_before = total_after = 0
    for r in rows:
        m = match_levels(r["w"], r["h"], r["sz"])
        if m is None:
            print(f"  {r['name']:26s} 0x{r['fmt']:02X} {r['unk1']:08X} {r['tail'][1]:5d} {'?':>10s} {r['sz']:9d} "
                  f"{r['w']:5d}x{r['h']:<4d}  --  NO LAYOUT MATCH (size doesn't fit 8 or 16 byte blocks)")
            continue
        bpb, k, chain = m
        matched += 1
        tally_unk3 += r["unk3"] == k
        tally_unk4 += r["unk4"] == k
        mipb = (r["unk1"] >> 16) & 0xFF
        tally_mipb += mipb == k
        single += k == 1
        dx = DXGI.get(r["tail"][1])
        if dx is None:
            dxgi_unknown += 1
            dxname = f"?{r['tail'][1]}"
        else:
            dxname = dx[0]
            if dx[1] == bpb:
                dxgi_ok += 1
            else:
                dxgi_bad += 1
                dxname += "!!"
        d = min(levels_to_reach(r["w"], r["h"], target), k - 1)
        after = size_after_drop(chain, k, d)
        total_before += r["sz"]
        total_after += after
        nw, nh = max(1, r["w"] >> d), max(1, r["h"] >> d)
        print(f"  {r['name']:26s} 0x{r['fmt']:02X} {r['unk1']:08X} {r['tail'][1]:5d} {dxname:>10s} {r['sz']:9d} "
              f"{r['w']:5d}x{r['h']:<4d} {bpb:3d} {k:4d} {mipb:4d}  drop {d} -> {nw}x{nh} = {after} B")
        r["bpb"], r["levels"] = bpb, k

    print(f"\n  layout matched: {matched}/{len(rows)}")
    print(f"  unk3 == stored mip levels: {tally_unk3}/{matched}   unk4 == stored mip levels: {tally_unk4}/{matched}"
          f"   byte2 of unk1 (mipB) == stored levels: {tally_mipb}/{matched}")
    print(f"  tail1 as DXGI code: block size agrees with size math {dxgi_ok}, disagrees {dxgi_bad} (marked !!), "
          f"unknown code {dxgi_unknown}")
    print(f"  single-level textures (no mip chain to slice): {single}/{matched}")
    hdr_total = hdr[1]
    print(f"  header word 1 = {hdr_total} vs sum of texture sizes {sum(r['sz'] for r in rows)}  "
          f"({'equal' if hdr_total == sum(r['sz'] for r in rows) else 'DIFFERENT'})")
    if total_before:
        print(f"  predicted total with --target {target}: {total_before} -> {total_after} bytes "
              f"({total_after / total_before * 100:.1f}%)  [ALL textures, incl. _n/_r/_s: this is a size "
              f"prediction only, not a recommendation to cut them]")

    srt = sorted(rows, key=lambda r: r["off"])
    gaps = [(a["name"], b["off"] - (a["off"] + a["sz"])) for a, b in zip(srt, srt[1:])]
    nonzero = [g for g in gaps if g[1] != 0]
    print(f"  data packed back-to-back: {'yes' if not nonzero else 'NO'}"
          f"{'' if not nonzero else '  gaps: ' + str(nonzero[:5])}")
    if srt:
        g = 0
        for r in srt:
            g = math.gcd(g, r["off"])
        print(f"  first data offset: {srt[0]['off']}   offset alignment (gcd): {g}")
        print(f"  entry tail words (last 8 bytes of each 36-byte entry): "
              f"{sorted({r['tail'] for r in rows})[:4]}")
    return rows


def files_for(a):
    out = []
    if a.path:
        out.append(Path(a.path))
    for cid in a.ids:
        out.append(VANILLA_CHR / f"{cid}.chrbnd.dcx")
        extra = VANILLA_CHR / f"{cid}_2.tpf.dcx"
        if extra.exists():
            out.append(extra)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="character ids, e.g. c1000 c5000")
    ap.add_argument("--path", help="explicit .chrbnd.dcx / .tpf.dcx path")
    ap.add_argument("--target", type=int, default=256, help="predict sizes when cut to this many px (default 256)")
    a = ap.parse_args()
    if not a.ids and not a.path:
        ap.error("give a character id or --path")

    for f in files_for(a):
        if not f.exists():
            print(f"[skip] {f} not found")
            continue
        try:
            if f.name.endswith(".chrbnd.dcx") or ".bnd" in f.name:
                from soulstruct_patch import apply_soulstruct_patches  # noqa: F401
                from soulstruct.containers import Binder
                b = Binder.from_path(f)
                for e in b.entries:
                    if e.name.endswith(".tpf"):
                        inspect_tpf(f"{f.name} :: {Path(e.name).name}", e.get_uncompressed_data(), a.target)
            else:
                inspect_tpf(f.name, dcx_read(f), a.target)
        except Exception as ex:
            print(f"[error] {f.name}: {type(ex).__name__}: {ex}")


if __name__ == "__main__":
    main()