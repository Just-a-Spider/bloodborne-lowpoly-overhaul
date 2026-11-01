#!/usr/bin/env python3
"""
batch_demake_characters.py - Batch PSX demake of dvdroot_ps4/chr/ (enemies, bosses, NPCs).

What it does per cXXXX.chrbnd.dcx:
  MESH  : runs mesh_decimator.decimate_flver at a base ratio, then at 0.55, and picks the
          first result per submesh that passes the invariants (Test 43/44):
            - was shared=True in vanilla  ->  must still be shared=True (verts < tris)
            - no submesh collapses to 0 tris, or below --min-submesh-tris
            - bone-weight byte-sum errors may not exceed vanilla's
          A submesh that fails every ratio keeps its vanilla geometry. The character is
          never aborted for one bad submesh.
  TEXTURE: only BC1 diffuse (*_a / *_a_l, DXGI 71/72) is downsampled + RGB555-quantized.
          _n, _r, _s, masks, BC4/BC5/BC6H/BC7 and hair/fur are left byte-identical
          (Tests 12, 30, 31, 33-36). Sizes are checked so the TPF never grows.
  SPLIT : chr/*.tpf.dcx (e.g. c5000_2.tpf.dcx) get the same texture pass (stdlib DCX).

Source/target rules (Test 42): geometry and textures are always derived from the VANILLA
dump; the sandbox only supplies whichever half you did NOT ask to regenerate, so running
--meshes and --textures separately never overwrites the other.

Default is a DRY RUN into /tmp/chr_demake_stage. Nothing in CUSA03173-PSX changes until
--deploy. Every sandbox file is snapshotted to <name>.snap_pre_chr before first overwrite.

Usage:
    uv run python tools/batch_demake_characters.py --only c1000            # dry run, one mob
    uv run python tools/batch_demake_characters.py --only c5000 --aabb vanilla
    uv run python tools/batch_demake_characters.py --only 'c1*' --deploy
    uv run python tools/batch_demake_characters.py --all --workers 4 --deploy --clear-cache
    uv run python tools/batch_demake_characters.py --restore --only c5000
"""

import argparse
import fnmatch
import os
import shutil
import struct
import sys
import traceback
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import numpy as np

try:
    import soulstruct_patch  # noqa: F401  (must load before Binder/FLVER are used)
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER
    from soulstruct.utilities.maths.aabb import AABB  # noqa: F401
    from mesh_decimator import (
        decimate_flver,
        get_merged_vertex_attributes,
        write_attributes_to_mesh,
    )
    from demake_color_engine import demake_texture_pixel_space, get_mip_sizes
except ImportError as e:  # pragma: no cover
    print(f"[FATAL] import error: {e}", file=sys.stderr)
    sys.exit(1)

VANILLA_CHR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "chr"
SANDBOX_CHR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "chr"
STAGE_DIR = Path("/tmp/chr_demake_stage")
SNAP_SUFFIX = ".snap_pre_chr"
BBHOST_CACHE = Path.home() / ".local/share/bbhost/data/bbhost"

SKIP_STEMS = {"c8030"}            # custom ultra-low Plain Doll: never touch
FALLBACK_RATIO = 0.55
CLOTH_HEAVY_FRAC = 0.25           # >25% of tris on _Cloth materials -> treat as fur/cloth boss
SKIP_TEX_KEYWORDS = ("hair", "fur", "beard")   # sky/moon/lace keywords removed: BC1 1-bit alpha is handled by the engine


# ----------------------------------------------------------------------------------------
# Mesh helpers
# ----------------------------------------------------------------------------------------
def mesh_stats(m):
    """(tris, verts, bad_weight_count) or None for meshes without geometry."""
    if not m.face_sets or len(m.vertex_arrays) == 0:
        return None
    attrs = get_merged_vertex_attributes(m)
    faces = m.face_sets[0].vertex_indices.reshape(-1, 3)
    bad = 0
    if "bone_weights" in attrs:
        sums = np.sum(np.round(attrs["bone_weights"] * 255.0).astype(int), axis=1)
        bad = int(np.sum(sums != 255))
    return len(faces), len(attrs["position"]), bad


def mesh_ok(v, n, min_tris):
    vt, vv, vb = v
    nt, nv, nb = n
    if nt == vt and nv == vv:
        return True                       # untouched
    if nt == 0:
        return False
    if vt >= min_tris and nt < min_tris:
        return False
    if vv < vt and nv >= nt:              # shared=True invariant (Test 43/44)
        return False
    if nb > vb:
        return False
    return True


def mesh_kind(m):
    """cloth (Havok, never touch) / fur (alpha fur cards) / alpha / body."""
    mat = m.material.name.lower() if m.material else ""
    mtd = m.material.mat_def_name.lower() if m.material else ""
    if "cloth" in mat or "cloth" in mtd:
        return "cloth"
    if "fur" in mat:
        return "fur"
    if "_al." in mtd:
        return "alpha"
    return "body"


def cloth_fraction(flv):
    tot = cloth = 0
    for m in flv.meshes:
        s = mesh_stats(m)
        if not s:
            continue
        tot += s[0]
        mat = m.material.name.lower() if m.material else ""
        mtd = m.material.mat_def_name.lower() if m.material else ""
        if "cloth" in mat or "_cloth" in mtd:
            cloth += s[0]
    return cloth / max(1, tot)


def decimate_with_fallback(raw, filename, ratio_override, mob_ratio, boss_ratio,
                           head_tris, min_tris, aabb_mode, body_mode="global", fur_ratio=1.0):
    """Returns (final_flver, report_dict)."""
    vanilla = FLVER.from_bytes(raw)
    vstats = {mi: mesh_stats(m) for mi, m in enumerate(vanilla.meshes)}
    vstats = {mi: s for mi, s in vstats.items() if s}
    kinds = {mi: mesh_kind(vanilla.meshes[mi]) for mi in vstats}
    cfrac = cloth_fraction(vanilla)
    klass = "cloth-heavy" if cfrac > CLOTH_HEAVY_FRAC else "standard"
    base = ratio_override if ratio_override else (boss_ratio if klass == "cloth-heavy" else mob_ratio)
    ratios = [base] if base >= FALLBACK_RATIO else [base, FALLBACK_RATIO]

    attempts = []                         # [(ratio, flver)]
    chosen = {}                           # mi -> attempt index (absent = keep vanilla)
    pending = set(vstats)
    # fur/alpha cards stay 100% vanilla unless --fur-ratio < 1 (bone-group path inflated their verts)
    if fur_ratio >= 1.0:
        pending = {mi for mi in pending if kinds[mi] not in ("fur", "alpha")}
    errors = []
    for r in ratios:
        flv = FLVER.from_bytes(raw)
        targets = None
        if body_mode == "global":
            # explicit per-submesh targets -> decimate_component_shared_verts (the Doll recipe);
            # without them every submesh goes through decimate_rigid_by_bone_groups, which keeps
            # every multi-bone face (i.e. most of a skinned body) untouched.
            targets = {}
            for mi, st in vstats.items():
                k = kinds[mi]
                if k == "cloth":
                    continue
                if k == "body":
                    rr = r
                elif fur_ratio < 1.0:
                    rr = min(1.0, fur_ratio * r / base)
                else:
                    continue
                targets[mi] = max(24, int(round(st[0] * rr)))
        try:
            decimate_flver(flv, target_ratio=r, flat_normals=False, disable_cloth=False,
                           preserve_border=True, head_target_tris=head_tris,
                           submesh_targets=targets, filename=filename)
        except Exception as e:  # decimator bug on this model: fall through to next ratio
            errors.append(f"ratio {r}: {type(e).__name__}: {e}")
            continue
        ai = len(attempts)
        attempts.append((r, flv))
        for mi in sorted(pending):
            n = mesh_stats(flv.meshes[mi])
            if n and mesh_ok(vstats[mi], n, min_tris):
                if n[0] < vstats[mi][0]:
                    chosen[mi] = ai
                pending.discard(mi)
        if not pending:
            break

    final = FLVER.from_bytes(raw)
    for mi, ai in chosen.items():
        src = attempts[ai][1].meshes[mi]
        write_attributes_to_mesh(
            final.meshes[mi],
            get_merged_vertex_attributes(src),
            src.face_sets[0].vertex_indices.reshape(-1, 3),
        )
        final.meshes[mi].bounding_box = src.bounding_box

    # Submeshes that failed every ratio stay vanilla (already the case in `final`).
    failed = sorted(pending)

    if aabb_mode == "vanilla":
        for mi, m in enumerate(final.meshes):
            m.bounding_box = vanilla.meshes[mi].bounding_box
        final.bounding_box = vanilla.bounding_box
    else:  # "tight": decimate_flver's validated behaviour (tight on rigid, vanilla on cloth)
        mins, maxs = [], []
        for m in final.meshes:
            if m.face_sets and len(m.vertex_arrays):
                mins.append(np.array(m.bounding_box.min))
                maxs.append(np.array(m.bounding_box.max))
        if mins:
            final.bounding_box = type(vanilla.bounding_box)(
                type(vanilla.bounding_box.min)(np.min(mins, axis=0)),
                type(vanilla.bounding_box.max)(np.max(maxs, axis=0)),
            )

    orig_t = sum(s[0] for s in vstats.values())
    new_t = 0
    per_ratio = {}
    for mi in vstats:
        s = mesh_stats(final.meshes[mi])
        new_t += s[0]
        if mi in chosen:
            rr = attempts[chosen[mi]][0]
            per_ratio[rr] = per_ratio.get(rr, 0) + 1
    mesh_rows = []
    for mi in sorted(vstats):
        fs = mesh_stats(final.meshes[mi])
        m = final.meshes[mi]
        mat = m.material.name if m.material else "?"
        mtd = m.material.mat_def_name if m.material else "?"
        src = f"r={attempts[chosen[mi]][0]:.2f}" if mi in chosen else ("VANILLA(failed)" if mi in pending else "untouched")
        mesh_rows.append((mi, kinds[mi], mat[:24], vstats[mi][0], fs[0], vstats[mi][1], fs[1], src))
    report = dict(mesh_rows=mesh_rows, klass=klass, cloth_frac=cfrac, base_ratio=base, orig=orig_t, new=new_t,
                  per_ratio=per_ratio, vanilla_kept=failed, errors=errors,
                  bones=len(vanilla.bones) if getattr(vanilla, "bones", None) else 0)
    return final, report


# ----------------------------------------------------------------------------------------
# Texture helpers (BC1 diffuse only)
# ----------------------------------------------------------------------------------------
def _tpf_name(tpf, str_off):
    cur = str_off
    while cur < len(tpf) - 1 and not (tpf[cur] == 0 and tpf[cur + 1] == 0):
        cur += 2
    return bytes(tpf[str_off:cur]).decode("utf-16le", errors="ignore")


def demake_tpf_bytes(tpf_bytes, dim, bc1_dxgi):
    """Returns (new_bytes, n_done, n_skipped, log). Size is guaranteed unchanged."""
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b"TPF\x00":
        return tpf, 0, 0, [("(not a TPF)", "bad magic")]
    done = skipped = 0
    log = []
    count = struct.unpack("<I", tpf[8:12])[0]
    for i in range(count):
        e = tpf[0x10 + i * 36: 0x10 + (i + 1) * 36]
        tex_off, tex_sz, unk1, unk2, _u3, _u4, str_off = struct.unpack("<7I", e[:28])
        dxgi = struct.unpack("<I", e[32:36])[0]   # last entry word = DXGI format (71/72 BC1, 80 BC4, 98/99 BC7...)
        name = _tpf_name(tpf, str_off)
        low = name.lower()
        base = low[:-2] if low.endswith("_l") else low
        fmt = unk1 & 0xFF
        w, h = unk2 & 0xFFFF, (unk2 >> 16) & 0xFFFF
        tag = f"{name} fmt=0x{fmt:02X} dxgi={dxgi} {w}x{h} size={tex_sz}"
        if not base.endswith("_a"):
            skipped += 1
            log.append((tag, "not *_a"))
            continue
        if dxgi not in bc1_dxgi:
            skipped += 1
            log.append((tag, "DXGI code is not BC1 (71/72)"))
            continue
        if any(k in low for k in SKIP_TEX_KEYWORDS):
            skipped += 1
            log.append((tag, "keyword skip (hair/fur/lace/sky...)"))
            continue
        try:
            tot, k = 0, None                  # stored data must be a whole number of BC1 mip levels
            for lvl, mm in enumerate(get_mip_sizes(w, h, 8), 1):
                tot += mm[4]
                if tot == tex_sz:
                    k = lvl
                    break
                if tot > tex_sz:
                    break
            if k is None:
                skipped += 1              # unexpected layout: don't risk it
                log.append((tag, "size is not a whole BC1 mip chain"))
                continue
            orig = bytes(tpf[tex_off: tex_off + tex_sz])
            out = demake_texture_pixel_space(orig, w, h, bpb=8, target_dim=dim, tex_name=name)
            if len(out) != tex_sz:
                skipped += 1
                log.append((tag, "output size mismatch"))
                continue
            tpf[tex_off: tex_off + tex_sz] = out
            done += 1
            log.append((tag, "DEMADE"))
        except Exception as ex:
            skipped += 1
            log.append((tag, f"exception {type(ex).__name__}: {ex}"))
    assert len(tpf) == len(tpf_bytes), "TPF size changed"
    return tpf, done, skipped, log


# Minimal DFLT DCX reader/writer (for standalone chr/*.tpf.dcx). Verified by round-trip.
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


# ----------------------------------------------------------------------------------------
# Per-file workers
# ----------------------------------------------------------------------------------------
def _safe_target(path):
    p = str(Path(path).resolve())
    assert "CUSA03173-PSX" in p, f"Safety: refusing to write outside sandbox: {p}"
    assert "/CUSA03173/" not in p, f"Safety: refusing to write to vanilla dump: {p}"


def process_chrbnd(name, a):
    stem = name.split(".")[0]
    rep = dict(file=name, kind="chrbnd", status="ok", flvers=[], tpf_done=0, tpf_skipped=0)
    try:
        van = Binder.from_path(VANILLA_CHR / name)
        sb_path = SANDBOX_CHR / name
        sandbox = {}
        if sb_path.exists() and not (a["meshes"] and a["textures"]):
            sandbox = {e.name: e.get_uncompressed_data() for e in Binder.from_path(sb_path).entries}

        for entry in van.entries:
            if entry.name.endswith(".flver"):
                raw = entry.get_uncompressed_data()
                if a["meshes"] and len(raw) > 0x100:
                    flv, r = decimate_with_fallback(
                        raw, stem, a["ratio"], a["mob_ratio"], a["boss_ratio"],
                        a["head_tris"], a["min_submesh_tris"], a["aabb"],
                        a["body_mode"], a["fur_ratio"])
                    entry.set_uncompressed_data(flv.to_bytes())
                    rep["flvers"].append(r)
                elif entry.name in sandbox:
                    entry.set_uncompressed_data(sandbox[entry.name])
            elif entry.name.endswith(".tpf"):
                if a["textures"]:
                    out, d, s, lg = demake_tpf_bytes(entry.get_uncompressed_data(), a["dim"], set(a["bc1_dxgi"]))
                    entry.set_uncompressed_data(bytes(out))
                    rep["tpf_done"] += d
                    rep["tpf_skipped"] += s
                    rep.setdefault("tex_log", []).extend(lg)
                elif entry.name in sandbox:
                    entry.set_uncompressed_data(sandbox[entry.name])

        STAGE_DIR.mkdir(parents=True, exist_ok=True)
        van.write(STAGE_DIR / name)
    except Exception as e:
        rep["status"] = f"FAILED {type(e).__name__}: {e}"
        rep["trace"] = traceback.format_exc()
    return rep


def process_split_tpf(name, a):
    rep = dict(file=name, kind="split-tpf", status="ok", flvers=[], tpf_done=0, tpf_skipped=0)
    try:
        payload, header = dcx_read(VANILLA_CHR / name)
        out, d, s, lg = demake_tpf_bytes(payload, a["dim"], set(a["bc1_dxgi"]))
        rep["tpf_done"], rep["tpf_skipped"] = d, s
        rep["tex_log"] = lg
        STAGE_DIR.mkdir(parents=True, exist_ok=True)
        dcx_write(STAGE_DIR / name, out, header)
    except Exception as e:
        rep["status"] = f"FAILED {type(e).__name__}: {e}"
    return rep


def _work(args):
    name, a = args
    return process_split_tpf(name, a) if name.endswith(".tpf.dcx") else process_chrbnd(name, a)


# ----------------------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------------------
def select_files(a):
    names = sorted(p.name for p in VANILLA_CHR.glob("*.chrbnd.dcx"))
    if a["textures"] and a["split_tpf"]:
        names += sorted(p.name for p in VANILLA_CHR.glob("*.tpf.dcx"))
    pats = [p.strip() for p in a["only"].split(",")] if a["only"] else ["*"]
    excl = [p.strip() for p in a["exclude"].split(",")] if a["exclude"] else []

    def match(n, pat):
        return fnmatch.fnmatch(n.split(".")[0], pat) or fnmatch.fnmatch(n.split(".")[0].split("_")[0], pat)

    out = []
    for n in names:
        if n.split(".")[0].split("_")[0] in SKIP_STEMS:
            continue
        if any(match(n, p) for p in pats) and not any(match(n, p) for p in excl):
            out.append(n)
    return out


def deploy_file(name):
    src = STAGE_DIR / name
    dst = SANDBOX_CHR / name
    _safe_target(dst)
    if dst.exists():
        snap = dst.with_name(dst.name + SNAP_SUFFIX)
        if not snap.exists():
            shutil.copy2(dst, snap)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def restore(a):
    pats = [p.strip() for p in a["only"].split(",")] if a["only"] else ["*"]
    n = 0
    for snap in sorted(SANDBOX_CHR.glob("*" + SNAP_SUFFIX)):
        orig = snap.with_name(snap.name[: -len(SNAP_SUFFIX)])
        if any(fnmatch.fnmatch(orig.name.split(".")[0].split("_")[0], p) for p in pats):
            _safe_target(orig)
            shutil.copy2(snap, orig)
            n += 1
    print(f"[RESTORE] reverted {n} file(s) from {SNAP_SUFFIX} snapshots")


def print_report(reports, verbose=False):
    print(f"\n{'file':32s} {'class':11s} {'ratio':>5s} {'tris':>17s} {'kept-vanilla':>12s} {'fallback':>8s} tex")
    to, tn = 0, 0
    for r in reports:
        if r["status"] != "ok":
            print(f"{r['file']:32s} {r['status']}")
            continue
        tex = f"{r['tpf_done']} done/{r['tpf_skipped']} skipped"
        if not r["flvers"]:
            print(f"{r['file']:32s} {'-':11s} {'-':>5s} {'-':>17s} {'-':>12s} {'-':>8s} {tex}")
            if verbose:
                for tag, why in r.get("tex_log", []):
                    print(f"    [tex] {why:34s} {tag}")
            continue
        for f in r["flvers"]:
            to += f["orig"]
            tn += f["new"]
            fb = sum(c for rr, c in f["per_ratio"].items() if rr >= FALLBACK_RATIO and rr != f["base_ratio"])
            pct = f["new"] / max(1, f["orig"]) * 100
            print(f"{r['file']:32s} {f['klass']:11s} {f['base_ratio']:5.2f} "
                  f"{f['orig']:7d}->{f['new']:6d} ({pct:3.0f}%) {len(f['vanilla_kept']):12d} {fb:8d} {tex}")
            for e in f["errors"]:
                print(f"    [decimator error] {e}")
            if verbose:
                print(f"    {'mesh':>4s} {'kind':6s} {'material':24s} {'tris':>13s} {'verts':>13s}  result")
                for (mi, kind, mat, ot, nt, ov, nv, src) in f["mesh_rows"]:
                    print(f"    {mi:4d} {kind:6s} {mat:24s} {ot:6d}->{nt:6d} {ov:6d}->{nv:6d}  {src}")
        if verbose:
            for tag, why in r.get("tex_log", []):
                print(f"    [tex] {why:34s} {tag}")
    if to:
        print(f"\nTOTAL triangles: {to} -> {tn} ({tn / to * 100:.1f}%)")
    bad = [r for r in reports if r["status"] != "ok"]
    if bad:
        print(f"[WARN] {len(bad)} file(s) failed and were NOT staged/deployed.")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--only", default="", help="comma list of ids/globs, e.g. c1000,c5* (matches the cXXXX prefix)")
    sel.add_argument("--all", action="store_true", help="every chr/ archive (except c8030)")
    p.add_argument("--exclude", default="", help="comma list of ids/globs to skip")
    p.add_argument("--deploy", action="store_true", help="write into CUSA03173-PSX (default: dry run to /tmp)")
    p.add_argument("--restore", action="store_true", help="restore snapshots (honours --only)")
    p.add_argument("--meshes", action="store_true", help="geometry only")
    p.add_argument("--textures", action="store_true", help="textures only")
    p.add_argument("--no-split-tpf", dest="split_tpf", action="store_false", help="skip chr/*.tpf.dcx")
    p.add_argument("--ratio", type=float, default=0.0, help="force one base ratio for every model")
    p.add_argument("--mob-ratio", type=float, default=0.25)
    p.add_argument("--boss-ratio", type=float, default=0.35, help="used when >25%% of tris are cloth")
    p.add_argument("--head-tris", type=int, default=650)
    p.add_argument("--body-mode", choices=["global", "bonegroups"], default="global",
                   help="global = per-submesh QEM targets (Doll recipe); bonegroups = keep multi-bone faces "
                        "(safe for weapons/limbs, barely reduces skinned bodies)")
    p.add_argument("--fur-ratio", type=float, default=1.0,
                   help="ratio for non-cloth alpha fur cards; 1.0 = leave vanilla (default, QEM on alpha cards is untested)")
    p.add_argument("--min-submesh-tris", type=int, default=40)
    p.add_argument("--aabb", choices=["tight", "vanilla"], default="tight",
                   help="tight = decimate_flver behaviour validated on the Doll; "
                        "vanilla = restore original AABBs (untested hypothesis, try on one boss first)")
    p.add_argument("--dim", type=int, default=128, help="diffuse texel dimension")
    p.add_argument("--bc1-dxgi", type=lambda s: [int(x, 0) for x in s.split(",")], default=[71, 72],
                   help="DXGI codes (last word of each TPF entry) treated as BC1 (default 71,72)")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--verbose", "-v", action="store_true", help="per-submesh table and per-texture skip reasons")
    p.add_argument("--clear-cache", action="store_true", help="delete bbhost pipeline cache after deploy")
    ns = p.parse_args()
    a = vars(ns)
    if not a["meshes"] and not a["textures"]:
        a["meshes"] = a["textures"] = True
    return a


def main():
    a = parse_args()
    if a["restore"]:
        restore(a)
        return
    if not a["only"] and not a["all"]:
        print("Refusing to run on everything by accident: pass --only <ids> or --all.", file=sys.stderr)
        sys.exit(2)

    files = select_files(a)
    if not files:
        print("No files matched.")
        return
    print(f"=== batch_demake_characters: {len(files)} file(s), "
          f"meshes={a['meshes']} textures={a['textures']} aabb={a['aabb']} "
          f"{'DEPLOY' if a['deploy'] else 'DRY RUN'} ===")
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    jobs = [(n, a) for n in files]
    reports = []
    if a["workers"] > 1:
        with ProcessPoolExecutor(max_workers=a["workers"]) as ex:
            futs = {ex.submit(_work, j): j[0] for j in jobs}
            for i, f in enumerate(as_completed(futs), 1):
                r = f.result()
                reports.append(r)
                print(f"[{i}/{len(jobs)}] {r['file']}: {r['status']}", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            r = _work(j)
            reports.append(r)
            print(f"[{i}/{len(jobs)}] {r['file']}: {r['status']}", flush=True)

    reports.sort(key=lambda r: r["file"])
    print_report(reports, a["verbose"])

    if a["deploy"]:
        ok = [r["file"] for r in reports if r["status"] == "ok"]
        for n in ok:
            deploy_file(n)
        print(f"\n[DEPLOYED] {len(ok)} file(s) -> {SANDBOX_CHR}  (snapshots: *{SNAP_SUFFIX})")
        if a["clear_cache"]:
            n = 0
            for f in BBHOST_CACHE.glob("*.bin"):
                f.unlink()
                n += 1
            print(f"[CACHE] removed {n} bbhost pipeline cache file(s)")
        else:
            print("[NOTE] clear the bbhost cache before launching: rm -f ~/.local/share/bbhost/data/bbhost/*.bin")
    else:
        print(f"\nDry run: staged in {STAGE_DIR}. Add --deploy to write into CUSA03173-PSX.")


if __name__ == "__main__":
    main()