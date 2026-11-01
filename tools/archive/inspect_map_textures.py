#!/usr/bin/env python3
"""
inspect_map_textures.py - READ-ONLY audit of a map's BXF texture archives.

Answers, per texture, with data instead of guesses:
  * Was it left alone by the OLD demake rules, and why? (protected keyword / BC7 skip / unprotected binder /
    format-byte mismatch / layout mismatch)
  * What is it really? (DXGI format from the TPF entry, size, mips)
  * Is it a 1-bit alpha cutout (grates, banners, foliage cards...)? Those turn into "holes to the void" when
    shrunk to 32 px.
  * Did the sandbox copy actually change versus vanilla?

Nothing is written except a CSV in /tmp.

Usage:
    uv run tools/inspect_map_textures.py m22
    uv run tools/inspect_map_textures.py m22 --grep brick
    uv run tools/inspect_map_textures.py m21 m22 --pbr           # also audit _n/_r/_s
"""

import argparse
import csv
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
VANILLA_ROOT = REPO_ROOT / "CUSA03173" / "dvdroot_ps4"
SANDBOX_ROOT = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4"

import numpy as np

import soulstruct_patch  # noqa: F401,E402
from soulstruct.dcx import decompress  # noqa: E402
from demake_color_engine import get_mip_sizes  # noqa: E402
from ps4_swizzle import deswizzle_level  # noqa: E402

# Mirrors batch_demake_environment.PROTECTED_ENV_KEYWORDS (substring match, as the old script did)
PROTECTED = ("clond", "cloud", "sky", "moon", "sun", "star", "magic", "cosmos",
             "blendmsk", "mask", "msk", "gi_", "envmap", "lightmap", "dol", "lut", "sfx",
             "foliage", "grass", "plant", "tree", "leaf", "ivy", "branch",
             "flower", "moss", "vine", "weed", "bush", "fern", "shrub")
DXGI_NAME = {71: "BC1_UNORM", 72: "BC1_SRGB", 77: "BC3_UNORM", 78: "BC3_SRGB", 80: "BC4_UNORM", 81: "BC4_SNORM",
             83: "BC5_UNORM", 84: "BC5_SNORM", 95: "BC6H_UF16", 96: "BC6H_SF16", 98: "BC7_UNORM", 99: "BC7_SRGB"}
DXGI_KIND = {71: "bc1", 72: "bc1", 80: "bc4", 81: "bc4", 83: "bc5", 84: "bc5"}


def read_bhd(path):
    data = Path(path).read_bytes()
    count = struct.unpack("<I", data[12:16])[0]
    out = []
    for i in range(count):
        rec = 0x40 + i * 36
        comp_sz = struct.unpack("<Q", data[rec + 8: rec + 16])[0]
        data_off = struct.unpack("<I", data[rec + 24: rec + 28])[0]
        name_off = struct.unpack("<I", data[rec + 32: rec + 36])[0]
        cur = name_off
        while cur < len(data) - 1 and not (data[cur] == 0 and data[cur + 1] == 0):
            cur += 2
        out.append((data[name_off:cur].decode("utf-16le", errors="ignore"), comp_sz, data_off))
    return out


def entry_tpf(bdt, comp_sz, data_off):
    return decompress(bytes(bdt[data_off: data_off + comp_sz]))[0]


def tpf_info(tpf):
    tex_off, tex_sz, unk1, unk2 = struct.unpack("<4I", bytes(tpf[0x10:0x20]))
    dxgi = struct.unpack("<I", bytes(tpf[0x10 + 32:0x10 + 36]))[0]
    return tex_off, tex_sz, unk1, unk2 & 0xFFFF, (unk2 >> 16) & 0xFFFF, dxgi


def chain_commits(w, h, bpb, tex_sz):
    tot = 0
    for _w, _h, _pw, _ph, sz in get_mip_sizes(w, h, bpb):
        tot += sz
        if tot == tex_sz:
            return True
        if tot > tex_sz:
            return False
    return False


def bc1_cutout(tpf, tex_off, w, h):
    """True if any BC1 block is in 3-colour+transparent mode (c0 <= c1) and uses index 3."""
    mips = get_mip_sizes(w, h, 8)
    _w, _h, pw, ph, sz0 = mips[0]
    lin = np.frombuffer(bytes(deswizzle_level(bytes(tpf[tex_off: tex_off + sz0]), w, h, 8)), dtype=np.uint8)
    blocks = lin[: (pw // 4) * (ph // 4) * 8].reshape(-1, 8)
    c0 = blocks[:, 0].astype(np.uint16) | (blocks[:, 1].astype(np.uint16) << 8)
    c1 = blocks[:, 2].astype(np.uint16) | (blocks[:, 3].astype(np.uint16) << 8)
    idx = (blocks[:, 4].astype(np.uint32) | (blocks[:, 5].astype(np.uint32) << 8)
           | (blocks[:, 6].astype(np.uint32) << 16) | (blocks[:, 7].astype(np.uint32) << 24))
    has3 = np.zeros(len(blocks), dtype=bool)
    for p in range(16):
        has3 |= ((idx >> (2 * p)) & 3) == 3
    return bool(((c0 <= c1) & has3).any())


def slot_of(low):
    ends = lambda *x: any(low.endswith(e) for e in x)  # noqa: E731
    if ends("_a.tpf.dcx", "_a_l.tpf.dcx", "_a.tpf.dc", "_a_l.tpf.dc"):
        return "albedo"
    if ends("_n.tpf.dcx", "_n_l.tpf.dcx", "_n.tpf.dc", "_n_l.tpf.dc"):
        return "normal"
    if ends("_r.tpf.dcx", "_r_l.tpf.dcx", "_r.tpf.dc", "_r_l.tpf.dc"):
        return "spec_r"
    if ends("_s.tpf.dcx", "_s_l.tpf.dcx", "_s.tpf.dc", "_s_l.tpf.dc"):
        return "spec_s"
    return "other"


def old_script_outcome(low, slot, fmt, w, h, tex_sz, pbr):
    """What the OLD (format-byte based) rules did. Returns (outcome, detail)."""
    kw = next((k for k in PROTECTED if k in low), None)
    if kw:
        return "protected-keyword", kw
    if any(low.endswith(x) for x in ("_m.tpf.dcx", "_m_l.tpf.dcx", "_m.tpf.dc", "_m_l.tpf.dc")):
        return "protected-mask", "_m"
    if slot == "other":
        return "not-an-a/n/r/s-slot", ""
    if slot != "albedo" and not pbr:
        return "pbr-not-requested", slot
    if "carpet" in low:
        return "carpet-special", ""
    if fmt in (0x66, 0x6A):
        return "skipped-BC7/BC6H-by-fmt", f"0x{fmt:02X}"
    bpb_old = 16 if fmt in (0x6C, 0x6D) else 8
    branch = "bc5" if fmt in (0x6C, 0x6D) else ("bc4" if (fmt == 0x67 or slot == "spec_s") else
                                                ("bc1" if fmt in (0x00, 0x01, 0x05) else None))
    if branch is None:
        return "skipped-unknown-fmt", f"0x{fmt:02X}"
    if not chain_commits(w, h, bpb_old, tex_sz):
        return "SILENTLY-UNTOUCHED-layout-mismatch", f"old rule assumed {bpb_old}B blocks / {branch}"
    return "processed", branch


PROTECTED_NEW = PROTECTED + ("cirrus",)
_NEW_RE = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(k) for k in PROTECTED_NEW) + ")")


def new_script_outcome(dxgi, cutout, low=""):
    m = _NEW_RE.search(low)
    if m:
        return f"protected ({m.group(0)})"
    kind = DXGI_KIND.get(dxgi)
    if kind is None:
        return "untouched (BC3/BC6H/BC7/unknown)"
    if kind == "bc1" and cutout:
        return "untouched (alpha cutout kept)"
    return "demade"


def binders_processed_by_script(map_id, map_dir):
    if map_id == "m21":
        return {"m21_0000"}
    return {p.stem for p in map_dir.glob(f"{map_id}_*.tpfbhd")
            if "env" not in p.stem.lower() and "gi_" not in p.stem.lower()}


def audit_map(map_id, pbr, grep):
    vmap = VANILLA_ROOT / "map" / map_id
    smap = SANDBOX_ROOT / "map" / map_id
    if not vmap.exists():
        print(f"[skip] {vmap} not found")
        return []
    proc_binders = binders_processed_by_script(map_id, vmap)
    rows = []
    for bhd in sorted(vmap.glob("*.tpfbhd")):
        stem = bhd.stem
        bdt_path = bhd.with_suffix(".tpfbdt")
        if not bdt_path.exists():
            continue
        vbdt = bdt_path.read_bytes()
        sbdt = sent = None
        sb_bhd = smap / bhd.name
        if sb_bhd.exists() and (smap / bdt_path.name).exists():
            sent = {n: (c, o) for n, c, o in read_bhd(sb_bhd)}
            sbdt = (smap / bdt_path.name).read_bytes()
        for name, comp_sz, data_off in read_bhd(bhd):
            low = name.lower()
            slot = slot_of(low)
            if slot == "other" or (slot != "albedo" and not pbr):
                continue
            try:
                tpf = entry_tpf(vbdt, comp_sz, data_off)
                tex_off, tex_sz, unk1, w, h, dxgi = tpf_info(tpf)
            except Exception as e:  # noqa: BLE001
                rows.append(dict(map=map_id, binder=stem, name=name, slot=slot, error=str(e)))
                continue
            fmt = unk1 & 0xFF
            cutout = bool(DXGI_KIND.get(dxgi) == "bc1" and bc1_cutout(tpf, tex_off, w, h))
            old, detail = old_script_outcome(low, slot, fmt, w, h, tex_sz, pbr)
            changed = None
            if sent is not None and name in sent:
                try:
                    changed = entry_tpf(sbdt, *sent[name]) != tpf
                except Exception:  # noqa: BLE001
                    changed = None
            rows.append(dict(map=map_id, binder=stem, name=name, slot=slot, w=w, h=h, fmt=f"0x{fmt:02X}",
                             dxgi=DXGI_NAME.get(dxgi, str(dxgi)), size=tex_sz, cutout=cutout,
                             binder_processed=stem in proc_binders, old=old, detail=detail,
                             new=new_script_outcome(dxgi, cutout, low), sandbox_changed=changed))
    report(map_id, rows, grep)
    return rows


def short(names, n=12):
    names = sorted(set(names))
    return ", ".join(names[:n]) + (f", ... (+{len(names) - n})" if len(names) > n else "")


def report(map_id, rows, grep):
    ok = [r for r in rows if "error" not in r]
    print(f"\n==================== {map_id}: {len(ok)} audited textures ({len(rows) - len(ok)} unreadable) ====================")
    print("Old-script outcome by slot:")
    c = Counter((r["slot"], r["old"]) for r in ok)
    for (slot, old), n in sorted(c.items()):
        print(f"  {slot:8s} {old:38s} {n:5d}")

    unproc = [r for r in ok if r["slot"] == "albedo" and not r["binder_processed"]]
    print(f"\nAlbedos in binders the script never opens (always vanilla): {len(unproc)}")
    by_b = defaultdict(list)
    for r in unproc:
        by_b[r["binder"]].append(r["name"])
    for b, ns in sorted(by_b.items()):
        print(f"  {b}: {len(ns)}  e.g. {short(ns, 6)}")

    print("\nAlbedos left vanilla WITHIN processed binders, by reason:")
    groups = defaultdict(list)
    for r in ok:
        if r["slot"] == "albedo" and r["binder_processed"] and r["old"] != "processed":
            groups[(r["old"], r["detail"])].append(r["name"])
    for (old, detail), ns in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"  {old} [{detail}]: {len(ns)}  e.g. {short(ns, 8)}")

    cut = [r for r in ok if r["slot"] == "albedo" and r["cutout"]]
    hit = [r for r in cut if r["old"] == "processed"]
    print(f"\n1-bit-alpha cutout albedos: {len(cut)} total, {len(hit)} were shrunk by the old rules (likely 'void' holes)")
    if hit:
        print("  " + short([r["name"] for r in hit], 25))

    mism = [r for r in ok if r["old"] == "processed" and
            {"bc1": "bc1", "bc4": "bc4", "bc5": "bc5"}.get(r["detail"]) != DXGI_KIND.get(
                next((k for k, v in DXGI_NAME.items() if v == r["dxgi"]), -1))]
    print(f"\nProcessed with the wrong decoder for their real format: {len(mism)}")
    if mism:
        print("  " + short([f"{r['name']}({r['detail']} vs {r['dxgi']})" for r in mism], 12))

    unchanged = [r for r in ok if r["slot"] == "albedo" and r["old"] == "processed" and r["sandbox_changed"] is False]
    print(f"\nProcessed-by-rule albedos that are byte-identical in the sandbox (script did not write them): {len(unchanged)}")
    if unchanged:
        print("  " + short([r["name"] for r in unchanged], 12))

    if grep:
        print(f"\nRows matching '{grep}':")
        for r in ok:
            if grep.lower() in r["name"].lower():
                print(f"  {r['binder']:12s} {r['name']:44s} {r['slot']:7s} {r['w']}x{r['h']} fmt={r['fmt']} {r['dxgi']:10s} "
                      f"cutout={r['cutout']!s:5s} binder_ok={r['binder_processed']!s:5s} old={r['old']}[{r['detail']}] "
                      f"changed={r['sandbox_changed']} new={r['new']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maps", nargs="+", help="map ids, e.g. m21 m22")
    ap.add_argument("--pbr", action="store_true", help="also audit _n/_r/_s")
    ap.add_argument("--grep", default="", help="print full rows for texture names containing this text")
    a = ap.parse_args()
    allrows = []
    for m in a.maps:
        allrows += audit_map(m, a.pbr, a.grep)
    out = Path("/tmp") / ("map_textures_" + "_".join(a.maps) + ".csv")
    keys = sorted({k for r in allrows for k in r})
    if allrows:
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(allrows)
        print(f"\nFull table: {out}")


if __name__ == "__main__":
    main()