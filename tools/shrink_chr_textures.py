#!/usr/bin/env python3
"""
shrink_chr_textures.py - PROTOTYPE: really shrink named textures in one cXXXX.chrbnd.dcx by
cutting off their biggest mip levels (no decoding, no re-encoding, so it is safe for any format).

What it changes, per texture you select:
  - the stored bytes: the top N mip levels are sliced off (the remaining levels are byte-identical
    to the original lower mips)
  - the entry's width/height (unk2) and the mip-count byte (byte 2 of unk1)
  - the entry's size and offset, and the TPF header's total-size word
Everything else (names, DXGI word, unk3/unk4, other textures) is copied unchanged.

Layout facts verified on c1000 / c5000_2 with inspect_tpf_mips.py:
  mip count = byte 2 of unk1; header word 1 = sum of texture sizes; texture data packed back to
  back with nothing after the last one; block size derived from size math.

Single-level textures (e.g. c5000_Body_a at 4096x2048) have no chain to slice and are skipped.

Source file: the sandbox copy if it exists (so decimated meshes / demade textures are kept),
otherwise vanilla. Default is a DRY RUN into /tmp/chr_shrink_stage. --deploy snapshots the
sandbox file to *.snap_pre_shrink first; --restore puts the snapshot back.

Batch mode (every chrbnd + standalone chr/*.tpf.dcx, default textures "*_a,*_a_l"):
    uv run tools/shrink_chr_textures.py --all --workers 4                        # dry run, whole chr/
    uv run tools/shrink_chr_textures.py --only 'c1*' --deploy                    # subset, write to sandbox
  Always run this AFTER batch_demake_characters.py (that script rebuilds textures from vanilla).
  c8030 (custom Plain Doll) is always skipped.

Usage:
    uv run tools/shrink_chr_textures.py c1000 --textures c1000_Body_a            # dry run
    uv run tools/shrink_chr_textures.py c1000 --textures 'c1000_*_a' --target 256
    uv run tools/shrink_chr_textures.py c1000 --textures c1000_Body_a --deploy
    uv run tools/shrink_chr_textures.py c1000 --restore
"""

import argparse
import fnmatch
import shutil
import struct
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from demake_color_engine import get_mip_sizes  # noqa: E402


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


def levels_to_reach(w, h, target):
    d = 0
    while max(w, h) > target and (w > 1 or h > 1):
        w, h = max(1, w // 2), max(1, h // 2)
        d += 1
    return d

VANILLA_ROOT = REPO_ROOT / "CUSA03173" / "dvdroot_ps4"
SANDBOX_ROOT = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4"
VANILLA_CHR = VANILLA_ROOT / "chr"
SANDBOX_CHR = SANDBOX_ROOT / "chr"
STAGE_DIR = Path("/tmp/chr_shrink_stage")
SNAP_SUFFIX = ".snap_pre_shrink"
MIP_MASK = 0x00FF0000


class TargetResolver:
    """Resolves target dimension per texture name: secondary maps (_n, _s, _r) drop to secondary_target."""
    def __init__(self, target: int, secondary_target: int = 0):
        self.target = target
        self.secondary_target = secondary_target

    def __call__(self, name: str) -> int:
        if self.secondary_target > 0:
            low = name.lower()
            if low.endswith(("_n", "_s", "_r", "_n_l", "_s_l", "_r_l")):
                return self.secondary_target
        return self.target


def shrink_tpf(tpf: bytes, want, target):
    """Returns (new_tpf_bytes, report_rows). Raises ValueError on any layout surprise."""
    if tpf[:4] != b"TPF\x00":
        raise ValueError("bad TPF magic")
    magic, _total, count, flags = struct.unpack("<4I", tpf[:16])
    ents = [list(struct.unpack("<9I", tpf[0x10 + i * 36: 0x10 + (i + 1) * 36])) for i in range(count)]
    first = min(e[0] for e in ents)
    order = sorted(range(count), key=lambda i: ents[i][0])

    pos = first
    for i in order:                                   # packed back to back, nothing trailing
        if ents[i][0] != pos:
            raise ValueError("texture data is not packed back to back")
        pos += ents[i][1]
    if pos != len(tpf):
        raise ValueError("unexpected bytes after the last texture")

    rows, new_data = [], {}
    for i, e in enumerate(ents):
        off, sz, unk1, unk2 = e[0], e[1], e[2], e[3]
        name = tpf_name(tpf, e[6])
        w, h = unk2 & 0xFFFF, (unk2 >> 16) & 0xFFFF
        data = tpf[off: off + sz]
        row = dict(name=name, before=(w, h, sz), after=(w, h, sz), note="untouched")
        if want(name):
            m = match_levels(w, h, sz)
            if m is None:
                row["note"] = "SKIPPED: size does not match a known mip layout"
            else:
                bpb, k, chain = m
                if ((unk1 >> 16) & 0xFF) != k:
                    row["note"] = "SKIPPED: mip-count byte disagrees with size math"
                else:
                    t_dim = target(name) if callable(target) else target
                    drop = min(levels_to_reach(w, h, t_dim), k - 1)
                    if drop == 0:
                        row["note"] = "untouched (single level or already <= target)"
                    else:
                        cut = sum(c[4] for c in chain[:drop])
                        data = data[cut:]
                        nw, nh = chain[drop][0], chain[drop][1]
                        e[3] = nw | (nh << 16)
                        e[2] = (unk1 & ~MIP_MASK) | ((k - drop) << 16)
                        e[1] = len(data)
                        row["after"] = (nw, nh, len(data))
                        row["note"] = f"dropped top {drop} level(s), {k} -> {k - drop} levels"
        rows.append(row)
        new_data[i] = data

    pos = first
    for i in order:
        ents[i][0] = pos
        pos += ents[i][1]
    total_new = sum(e[1] for e in ents)

    head = bytearray(tpf[:first])                     # header + names region, kept as is
    struct.pack_into("<4I", head, 0, magic, total_new, count, flags)
    for i, e in enumerate(ents):
        struct.pack_into("<9I", head, 0x10 + i * 36, *e)
    out = bytes(head) + b"".join(new_data[i] for i in order)

    verify_tpf(out, tpf)
    return out, rows


def verify_tpf(out: bytes, orig: bytes):
    """Re-parse the result and check every invariant we rely on."""
    magic, total, count, _f = struct.unpack("<4I", out[:16])
    omagic, _ot, ocount, _of = struct.unpack("<4I", orig[:16])
    if (magic, count) != (omagic, ocount):
        raise ValueError("verify: magic/count changed")
    ents = [struct.unpack("<9I", out[0x10 + i * 36: 0x10 + (i + 1) * 36]) for i in range(count)]
    oents = [struct.unpack("<9I", orig[0x10 + i * 36: 0x10 + (i + 1) * 36]) for i in range(count)]
    if total != sum(e[1] for e in ents):
        raise ValueError("verify: header total != sum of sizes")
    first = min(e[0] for e in ents)
    if len(out) != first + total:
        raise ValueError("verify: file length != first offset + total")
    if out[:0x10 + count * 36][16 + 36 * count:] != orig[:0x10 + count * 36][16 + 36 * count:]:
        pass  # (names region compared below)
    nm_start = 0x10 + count * 36
    if out[nm_start:first] != orig[nm_start: min(e[0] for e in oents)]:
        raise ValueError("verify: names region changed")
    for e, oe in zip(ents, oents):
        w, h = e[3] & 0xFFFF, (e[3] >> 16) & 0xFFFF
        m = match_levels(w, h, e[1])
        if m is None or m[1] != ((e[2] >> 16) & 0xFF):
            raise ValueError(f"verify: texture at offset {e[0]} no longer self-consistent")
        if (e[2] & ~MIP_MASK) != (oe[2] & ~MIP_MASK) or e[4:] != oe[4:] or e[6] != oe[6]:
            raise ValueError("verify: a non-size/dims/mip field changed")


def process(cid, patterns, target, deploy):
    from soulstruct_patch import apply_soulstruct_patches  # noqa: F401
    from soulstruct.containers import Binder

    name = f"{cid}.chrbnd.dcx"
    sandbox = SANDBOX_CHR / name
    src = sandbox if sandbox.exists() else VANILLA_CHR / name
    print(f"=== shrink {name}  source={'sandbox' if src == sandbox else 'vanilla'}  target={target}px ===")
    want = lambda n: any(fnmatch.fnmatch(n.lower(), p.lower()) for p in patterns)  # noqa: E731

    b = Binder.from_path(src)
    before_total = after_total = 0
    for e in b.entries:
        if not e.name.endswith(".tpf"):
            continue
        raw = e.get_uncompressed_data()
        out, rows = shrink_tpf(raw, want, target)
        e.set_uncompressed_data(out)
        before_total += len(raw)
        after_total += len(out)
        print(f"\n  {Path(e.name).name}: {len(raw)} -> {len(out)} bytes")
        for r in rows:
            if r["note"].startswith("untouched") and not want(r["name"]):
                continue
            bw, bh, bs = r["before"]
            aw, ah, a_s = r["after"]
            print(f"    {r['name']:28s} {bw}x{bh} {bs:>9d} B -> {aw}x{ah} {a_s:>9d} B   {r['note']}")
    if before_total == after_total:
        print("\nNothing changed (no matching textures, or all single-level). Not staging.")
        return
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    stage = STAGE_DIR / name
    b.write(stage)
    print(f"\n[STAGED] {stage}   textures {before_total} -> {after_total} bytes "
          f"({after_total / before_total * 100:.1f}%)")

    if not deploy:
        print("Dry run. Add --deploy to write into CUSA03173-PSX.")
        return
    assert "CUSA03173-PSX" in str(sandbox.resolve())
    if sandbox.exists():
        snap = sandbox.with_name(sandbox.name + SNAP_SUFFIX)
        if not snap.exists():
            shutil.copy2(sandbox, snap)
            print(f"[SNAPSHOT] {snap}")
    tmp = sandbox.with_name(sandbox.name + ".tmp")
    shutil.copy2(stage, tmp)
    tmp.replace(sandbox)
    print(f"[DEPLOYED] {sandbox}")
    print("Clear the bbhost cache before launching: rm -f ~/.local/share/bbhost/data/bbhost/*.bin")
    print(f"Undo: uv run tools/shrink_chr_textures.py {cid} --restore")


# ----------------------------------------------------------------------------------------
# Batch mode
# ----------------------------------------------------------------------------------------
SKIP_STEMS = {"c8030"}
DEFAULT_PATTERNS = ["*_a", "*_a_l"]


def dcx_read(path):
    data = Path(path).read_bytes()
    if (data[:4] != b"DCX\x00" or data[0x18:0x1C] != b"DCS\x00" or data[0x24:0x28] != b"DCP\x00"
            or data[0x28:0x2C] != b"DFLT" or data[0x44:0x48] != b"DCA\x00"):
        raise ValueError("not a DFLT DCX")
    unc, comp = struct.unpack(">II", data[0x1C:0x24])
    payload = zlib.decompress(data[0x4C: 0x4C + comp])
    if len(payload) != unc:
        raise ValueError("DCX size mismatch")
    return payload, bytearray(data[:0x4C])


def dcx_write(path, payload, header):
    comp = zlib.compress(bytes(payload), 9)
    header = bytearray(header)
    struct.pack_into(">II", header, 0x1C, len(payload), len(comp))
    blob = bytes(header) + comp
    blob += b"\x00" * (-len(blob) % 16)
    Path(path).write_bytes(blob)
    back, _ = dcx_read(path)
    if back != bytes(payload):
        raise ValueError("DCX round-trip mismatch")


def make_want(patterns, exclude=()):
    def want(n):
        n = n.lower()
        return (any(fnmatch.fnmatch(n, p.lower()) for p in patterns)
                and not any(fnmatch.fnmatch(n, x.lower()) for x in exclude))
    return want


def shrink_standalone(src, stage, want, target):
    payload, header = dcx_read(src)
    out, rows = shrink_tpf(payload, want, target)
    changed = len(out) != len(payload)
    if changed:
        dcx_write(stage, out, header)
    return len(payload), len(out), rows, changed


def shrink_chrbnd(src, stage, want, target):
    from soulstruct_patch import apply_soulstruct_patches  # noqa: F401
    from soulstruct.containers import Binder
    b = Binder.from_path(src)
    before = after = 0
    rows = []
    for e in b.entries:
        if not e.name.endswith(".tpf"):
            continue
        raw = e.get_uncompressed_data()
        out, r = shrink_tpf(raw, want, target)
        e.set_uncompressed_data(out)
        before += len(raw)
        after += len(out)
        rows += r
    changed = after != before
    if changed:
        b.write(stage)
    return before, after, rows, changed


def _shrink_job(job):
    name, patterns, target, exclude, category = job
    sandbox_dir = SANDBOX_ROOT / category
    vanilla_dir = VANILLA_ROOT / category
    sandbox = sandbox_dir / name
    src = sandbox if sandbox.exists() else vanilla_dir / name
    rep = dict(file=name, status="ok", before=0, after=0, rows=[], changed=False,
               source="sandbox" if src == sandbox else "vanilla", category=category)
    try:
        STAGE_DIR.mkdir(parents=True, exist_ok=True)
        fn = shrink_standalone if name.endswith(".tpf.dcx") else shrink_chrbnd
        rep["before"], rep["after"], rep["rows"], rep["changed"] = fn(src, STAGE_DIR / name, make_want(patterns, exclude), target)
    except Exception as e:
        rep["status"] = f"FAILED {type(e).__name__}: {e}"
    return rep


def deploy_file(name, category="chr", make_snapshot=True):
    src = STAGE_DIR / name
    dst = (SANDBOX_ROOT / category) / name
    assert "CUSA03173-PSX" in str(dst.resolve())
    dst.parent.mkdir(parents=True, exist_ok=True)
    if make_snapshot and dst.exists():
        snap = dst.with_name(dst.name + SNAP_SUFFIX)
        if not snap.exists():
            shutil.copy2(dst, snap)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dst)


def select_batch(only, category="chr"):
    vanilla_dir = VANILLA_ROOT / category
    ext = f"*.{category}bnd.dcx" if category != "parts" else "*.partsbnd.dcx"
    names = sorted(p.name for p in vanilla_dir.glob(ext)) + \
            sorted(p.name for p in vanilla_dir.glob("*.tpf.dcx"))
    pats = [x.strip() for x in only.split(",")] if only else ["*"]
    out = []
    for n in names:
        stem = n.split(".")[0].split("_")[0]
        if stem in SKIP_STEMS:
            continue
        if any(fnmatch.fnmatch(stem, p) or fnmatch.fnmatch(n.split(".")[0], p) for p in pats):
            out.append(n)
    return out


def run_batch(a):
    patterns = [p.strip() for p in a.textures.split(",") if p.strip()] or DEFAULT_PATTERNS
    files = select_batch(a.only, a.category)
    if not files:
        print(f"No files matched in category {a.category}.")
        return
    resolver = TargetResolver(a.target, getattr(a, 'secondary_target', 0))
    sec_info = f" (secondary={a.secondary_target}px)" if getattr(a, 'secondary_target', 0) > 0 else ""
    print(f"=== shrink batch ({a.category}): {len(files)} file(s), textures={patterns}, target={a.target}px{sec_info}, "
          f"{'DEPLOY' if a.deploy else 'DRY RUN'} ===")
    exclude = [x.strip() for x in a.exclude.split(",") if x.strip()]
    print(f"    excluding: {exclude or 'nothing'}")
    jobs = [(n, patterns, resolver, exclude, a.category) for n in files]
    reports = []
    if a.workers > 1:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(_shrink_job, j) for j in jobs]
            for i, f in enumerate(as_completed(futs), 1):
                reports.append(f.result())
                if i % 25 == 0 or i == len(jobs):
                    print(f"  ... {i}/{len(jobs)}", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            reports.append(_shrink_job(j))
            if i % 25 == 0 or i == len(jobs):
                print(f"  ... {i}/{len(jobs)}", flush=True)
    reports.sort(key=lambda r: r["file"])

    tb = ta = ch = 0
    for r in reports:
        if r["status"] != "ok":
            print(f"  [FAIL] {r['file']}: {r['status']}")
            continue
        if not r["changed"]:
            continue
        ch += 1
        tb += r["before"]
        ta += r["after"]
        cut = sum(1 for x in r["rows"] if x["note"].startswith("dropped"))
        print(f"  {r['file']:32s} {r['before']:>10d} -> {r['after']:>10d} B ({r['after'] / r['before'] * 100:5.1f}%)  "
              f"{cut} texture(s) cut  [{r['source']}]")
        if a.verbose:
            for x in r["rows"]:
                if x["note"].startswith(("dropped", "SKIPPED")):
                    bw, bh, bs = x["before"]
                    aw, ah, s2 = x["after"]
                    print(f"      {x['name']:28s} {bw}x{bh} {bs} -> {aw}x{ah} {s2}  {x['note']}")
    fails = sum(1 for r in reports if r["status"] != "ok")
    print(f"\n{ch} file(s) would change, {fails} failed, {len(reports) - ch - fails} had nothing to cut.")
    if tb:
        print(f"Texture bytes in changed files: {tb} -> {ta}  ({ta / tb * 100:.1f}%, saves {(tb - ta) / 1048576:.1f} MiB of uncompressed texture data summed over ALL these characters; "
              f"in-game VRAM only changes for the ones loaded at the same time)")

    if a.deploy:
        done = [r["file"] for r in reports if r["status"] == "ok" and r["changed"]]
        for n in done:
            deploy_file(n, a.category, make_snapshot=not a.no_snapshot)
        snap_note = f" (snapshots: *{SNAP_SUFFIX})" if not a.no_snapshot else " (no snapshots)"
        print(f"[DEPLOYED] {len(done)} file(s) -> {SANDBOX_ROOT / a.category}{snap_note}")
        print("Clear the bbhost cache before launching: rm -f ~/.local/share/bbhost/data/bbhost/*.bin")
    else:
        print(f"Dry run: staged in {STAGE_DIR}. Add --deploy to write into CUSA03173-PSX.")


def restore_batch(only, category="chr"):
    n = 0
    sandbox_dir = SANDBOX_ROOT / category
    for name in select_batch(only, category):
        sandbox = sandbox_dir / name
        snap = sandbox.with_name(sandbox.name + SNAP_SUFFIX)
        if snap.exists():
            assert "CUSA03173-PSX" in str(sandbox.resolve())
            shutil.copy2(snap, sandbox)
            n += 1
    print(f"[RESTORE] reverted {n} file(s) from {SNAP_SUFFIX} snapshots in {category}")


def restore(cid):
    sandbox = SANDBOX_CHR / f"{cid}.chrbnd.dcx"
    snap = sandbox.with_name(sandbox.name + SNAP_SUFFIX)
    if not snap.exists():
        sys.exit(f"No snapshot at {snap}")
    shutil.copy2(snap, sandbox)
    print(f"[RESTORE] {sandbox} reverted from {snap.name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", nargs="?", default="", help="character id, e.g. c1000 (omit with --all / --only)")
    ap.add_argument("--category", choices=["chr", "parts", "obj"], default="chr",
                    help="asset category: chr, parts, or obj (default: chr)")
    ap.add_argument("--all", action="store_true", help="every archive in category (except c8030)")
    ap.add_argument("--only", default="", help="comma list of ids/globs for batch mode, e.g. c1*,c5000,wp_a_*")
    ap.add_argument("--exclude", default="*fur*,*hair*,*beard*,*_hr_*",
                    help="batch mode: texture-name globs to leave alone (default keeps alpha-cutout fur/hair/beard "
                         "at full size, they are tall strips that would become ~64px wide). Use --exclude '' to disable")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--textures", default="", help="comma list of texture-name globs, e.g. c1000_Body_a,c1000_Moon_Body_a")
    ap.add_argument("--target", type=int, default=256, help="cut each selected texture until its longest side <= this")
    ap.add_argument("--secondary-target", type=int, default=128,
                    help="target dimension for secondary maps (_n, _s, _r); set 0 to disable (default: 128px)")
    ap.add_argument("--no-snapshot", action="store_true", help="do not create .snap_pre_shrink backups")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    if a.all or a.only:
        if a.restore:
            restore_batch(a.only, a.category)
        else:
            run_batch(a)
        return
    if not a.id:
        ap.error("give a character id, or use --all / --only")
    if a.restore:
        restore(a.id)
        return
    pats = [p.strip() for p in a.textures.split(",") if p.strip()]
    if not pats:
        ap.error("--textures is required (e.g. --textures c1000_Body_a)")
    process(a.id, pats, a.target, a.deploy)


if __name__ == "__main__":
    main()