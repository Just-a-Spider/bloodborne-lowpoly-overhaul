#!/usr/bin/env python3
"""
batch_demake_world_ultralow.py - ultra-low-poly pass for MAP FLVERs (the Doll recipe, adapted to world geometry).

Why a separate tool: running the character decimator directly on world meshes (--lod 0) broke the Hunter's Dream
pillars and ground. The decimator resets color_0 to white, recomputes normals/tangents and replaces extra UV sets.
Native LOD promotion (--lod 1/2) never has that problem because it only swaps FaceSet indices (validated, Tests 21-29).
This tool keeps native LOD promotion as stage 1 and adds, as stage 2, what the Doll pipeline had:

  1. Native LOD promotion into FaceSet 0 (hybrid: landmarks LOD1, background LOD2), same rules as
     batch_demake_environment.py, incl. the 25% floor (15% for foliage).
  2. Per-submesh QEM on top of the promoted surface, with EXPLICIT per-submesh targets (decimate_component_shared_verts
     path, like the Doll), each with a floor:  max(24 tris, min_frac * vanilla tris).
  3. Gates per submesh, ratio ladder per submesh (ratio -> gentler ratio -> keep the promoted LOD, never abort):
       - no NaN/inf, no zero-triangle result, must actually reduce
       - a submesh that was shared=True (verts < tris) in vanilla must still be shared=True
  4. World vertex-data restore: color_0, normals, tangents (and any extra attributes) are copied back from the
     best-matching ORIGINAL vertex (nearest position, ties broken by uv_0, so seam duplicates keep their own data).
  5. Original AABBs are kept (map culling), cloth/sky/foliage-cards/alpha submeshes are never QEM'd.
  v2 policy: QEM is OPT-IN by what the mesh is (diffuse texture name, --qem-allow-tex), skips landmark FLVERs, `_blend`
     (vertex-painted ground), `_env`, emissive and `*_dirt` overlay materials, and submeshes under --qem-min-base
     triangles. v1 QEM'd everything and broke m21's stairs, floors, pillars and dirt overlays.
  6. Optional, EXPERIMENTAL: foliage card thinning (--foliage-keep < 1) drops whole cards, spread evenly.

Run batch_demake_environment.py first (textures, objects), then this tool: it re-reads VANILLA FLVERs and overwrites
the same sandbox FLVERs. Running the environment script's --flvers pass afterwards would overwrite this tool's output.

Default is a DRY RUN into /tmp/world_ultralow_stage. --deploy snapshots each sandbox FLVER to *.snap_pre_world first.

Usage:
    uv run python tools/batch_demake_world_ultralow.py --map m21 --audit -v        # no writes: LODs, materials, plan
    uv run python tools/batch_demake_world_ultralow.py --map m21 --preset aggressive
    uv run python tools/batch_demake_world_ultralow.py --map m21 --preset ultra --deploy
    uv run python tools/batch_demake_world_ultralow.py --map m21 --restore
"""

import argparse
import fnmatch
import glob
import math
import os
import re
import shutil
import sys
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

STAGE_DIR = Path("/tmp/world_ultralow_stage")
SNAP_SUFFIX = ".snap_pre_world"

PRESETS = {
    #              landmark QEM ratio, background QEM ratio, min fraction of VANILLA tris, foliage cards kept
    "moderate":   dict(ratio_landmark=0.80, ratio_bg=0.60, min_frac=0.20, foliage_keep=1.00),
    "aggressive": dict(ratio_landmark=0.60, ratio_bg=0.40, min_frac=0.10, foliage_keep=1.00),
    "ultra":      dict(ratio_landmark=0.45, ratio_bg=0.25, min_frac=0.06, foliage_keep=0.60),
}
MIN_TRIS = 24

# QEM policy (v2). QEM on architecture broke stairs, floors, pillars and the *_dirt overlay meshes on m21, so QEM is
# now opt-IN by what the mesh is, judged from its diffuse texture name. Everything else keeps its native LOD.
QEM_ALLOW_DEFAULT = ""      # m21 test: even rocks showed UV streaking and gained no fps, so QEM is OFF unless you opt in
QEM_DENY_DEFAULT = "dirt,damage,decal,mark,blood,stain,blendmsk,cloud,clond,sky,moon"
PROTECT_MTD_DEFAULT = "_al.,_blend,_env,_e.,_em."     # alpha, vertex-painted ground blending, env-mapped, emissive

_D = {}


def deps():
    """Heavy imports are lazy so the pure helpers below can be imported and tested without Soulstruct."""
    if not _D:
        import soulstruct_patch  # noqa: F401
        import batch_demake_environment as env
        import mesh_decimator as md
        _D.update(env=env, md=md)
    return _D


# ----------------------------------------------------------------------------------------
# Pure helpers (numpy/scipy only)
# ----------------------------------------------------------------------------------------
def ntri(fs) -> int:
    return int(np.asarray(fs.vertex_indices).size // 3)


def faces_of(fs) -> np.ndarray:
    return np.asarray(fs.vertex_indices).reshape(-1, 3).astype(np.int64)


def _uv(attrs):
    if "uv_0" not in attrs:
        return None
    a = np.asarray(attrs["uv_0"], dtype=np.float32)
    return a.reshape(len(a), -1)[:, :2]


def match_original_vertices(old_pos, old_uv, new_pos, new_uv, k=8, rel_tol=0.5, abs_tol=1e-4):
    """For every new vertex, the index of the original vertex that best describes it:
    among the near-equidistant nearest candidates pick the one with the closest uv_0 (keeps seam duplicates apart)."""
    k = max(1, min(k, len(old_pos)))
    d, idx = cKDTree(old_pos).query(new_pos, k=k)
    if k == 1:
        d, idx = d[:, None], idx[:, None]
    if old_uv is None or new_uv is None:
        return idx[:, 0]
    ok = d <= (d[:, :1] * (1.0 + rel_tol) + abs_tol)
    duv = np.linalg.norm(old_uv[idx] - new_uv[:, None, :], axis=2)
    duv = np.where(ok, duv, np.inf)
    return idx[np.arange(len(new_pos)), np.argmin(duv, axis=1)]


CORE_FIELDS = {"position", "uv_0", "uv_1", "normal_w", "bone_indices", "bone_weights"}


def fields_to_preserve(names, groups):
    out = []
    for n in names:
        if n in CORE_FIELDS:
            continue
        if n.startswith("color_") and "colors" in groups:
            out.append(n)
        elif n == "normal" and "normals" in groups:
            out.append(n)
        elif (n.startswith("tangent_") or n.startswith("bitangent")) and "tangents" in groups:
            out.append(n)
        elif "extra" in groups and not (n.startswith("color_") or n == "normal" or n.startswith("tangent_")
                                        or n.startswith("bitangent")):
            out.append(n)       # uv_2+, unknown attributes
    return out


def restore_world_vertex_data(ref_attrs, new_attrs, groups):
    """Copy preserved fields from the best-matching ORIGINAL vertex into the decimated attributes."""
    fields = [f for f in fields_to_preserve(ref_attrs.keys(), groups) if f in new_attrs or f in ref_attrs]
    if not fields:
        return new_attrs
    old_pos = np.asarray(ref_attrs["position"], dtype=np.float32).reshape(-1, 3)
    new_pos = np.asarray(new_attrs["position"], dtype=np.float32).reshape(-1, 3)
    idx = match_original_vertices(old_pos, _uv(ref_attrs), new_pos, _uv(new_attrs))
    out = dict(new_attrs)
    for f in fields:
        out[f] = np.asarray(ref_attrs[f])[idx]
    return out


def thin_components(faces, keep, min_components=30, min_tris=MIN_TRIS):
    """Keep ~`keep` of the connected components (foliage cards), chosen by a stable hash so the thinning is evenly
    spread. Returns the reduced face array, or None when thinning is not applicable."""
    if keep >= 1.0 or len(faces) == 0:
        return None
    n = int(faces.max()) + 1
    rows = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
    cols = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
    graph = coo_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)), shape=(n, n))
    ncomp, labels = connected_components(graph, directed=False)
    if ncomp < min_components:
        return None
    h = ((np.arange(ncomp, dtype=np.uint64) * np.uint64(2654435761)) % np.uint64(1009)).astype(np.float64) / 1009.0
    keep_comp = h < keep
    mask = keep_comp[labels[faces[:, 0]]]
    out = faces[mask]
    return out if len(out) >= min_tris else None


def compact_mesh(attrs, faces):
    """Drop unused vertices and remap faces."""
    used = np.unique(faces)
    remap = np.full(int(faces.max()) + 1, -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out = {k: np.asarray(v)[used] for k, v in attrs.items() if len(v) > used.max()}
    return out, remap[faces].astype(np.uint32)


def tex_category(stem):
    """'m21_01_brick_002_dirt_a' -> 'brick_dirt', 'm21_00_rock_big_100_a_l' -> 'rock_big'."""
    s = stem.lower()
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"^m\d\d_(\d\d_)?", "", s)
        s = re.sub(r"^\d\d_", "", s)
    toks = [t for t in s.split("_") if t and not t.isdigit() and t not in ("a", "l")]
    return "_".join(toks) or "?"


def qem_eligible(kind, stem, allow, deny):
    """QEM only for plain 'body' meshes whose diffuse texture name is on the allow list (or '*') and not on the deny list."""
    if kind != "body":
        return False
    if any(k in stem for k in deny):
        return False
    return "*" in allow or any(k in stem for k in allow)


def plan_target(base_tris, vanilla_tris, ratio, min_frac, min_tris=MIN_TRIS):
    """Explicit QEM target for a submesh, or None when QEM would not help."""
    if base_tris < 2 * min_tris:
        return None             # tiny submesh: not worth touching
    floor_t = max(min_tris, int(math.ceil(min_frac * vanilla_tris)))
    tgt = max(floor_t, int(round(base_tris * ratio)))
    return tgt if tgt < base_tris else None


def world_mesh_ok(base_tris, vanilla_shared, new, min_tris=MIN_TRIS):
    nt, nv, finite = new
    if not finite or nt <= 0 or nt < min(min_tris, base_tris) or nt >= base_tris:
        return False
    if vanilla_shared and nv >= nt:         # shared=True invariant (Tests 43/44)
        return False
    return True


def ladder(ratio):
    """Ratio ladder per submesh: requested ratio, then a gentler one."""
    gentle = min(0.9, max(ratio * 1.6, ratio + 0.25))
    return [ratio] if gentle <= ratio + 1e-6 else [ratio, gentle]


# ----------------------------------------------------------------------------------------
# FLVER helpers
# ----------------------------------------------------------------------------------------
def flag_id(fs):
    try:
        return int(fs.flags)
    except Exception:  # noqa: BLE001
        return str(fs.flags)


def is_landmark(map_id, filename):
    if map_id == "m21":
        return any(f"0010{x:02d}" in filename for x in range(0, 36)) or "001000" in filename
    idx_str = filename.split("_")[-1].split(".")[0]
    return (int(idx_str) if idx_str.isdigit() else 0) < 8000


def mesh_names(m):
    mat = (m.material.name or "").lower() if m.material else ""
    mtd = (m.material.mat_def_name or "").lower() if m.material else ""
    return mat, mtd


def tex_stem_of_mesh(m):
    """Diffuse texture stem of a submesh (first *_a / *_a_l texture, else the first texture)."""
    if not m.material:
        return ""
    first = ""
    for tex in getattr(m.material, "textures", None) or []:
        path = getattr(tex, "path", "") or ""
        stem = re.split(r"[\\/]", path)[-1].split(".")[0].lower()
        if not stem:
            continue
        if stem.endswith("_a") or stem.endswith("_a_l"):
            return stem
        first = first or stem
    return first


def mesh_kind(m, protect_mtd):
    env = deps()["env"]
    mat, mtd = mesh_names(m)
    if any(k in mat or k in mtd for k in env.SKY_FLVER_KEYWORDS):
        return "sky"
    if any(k in mat or k in mtd for k in getattr(env, "FOLIAGE_KEYWORDS", ())):
        return "foliage"
    if "cloth" in mat or "cloth" in mtd:
        return "cloth"
    if any(k in mtd for k in protect_mtd):
        return "protected"
    return "body"


def promote_native_lod(m, effective_lod, floor_pct):
    fs0 = m.face_sets[0]
    orig = ntri(fs0)

    def usable(fs, pct):
        return (len(fs.vertex_indices) > 0 and ntri(fs) >= max(MIN_TRIS, int(orig * pct))
                and getattr(fs, "triangle_strip", None) == getattr(fs0, "triangle_strip", None))

    target = None
    for fs in m.face_sets:
        if flag_id(fs) == effective_lod and usable(fs, floor_pct):
            target = fs
            break
    if target is None and effective_lod == 2:
        for fs in m.face_sets:
            if flag_id(fs) == 1 and usable(fs, 0.25):
                target = fs
                break
    if target is not None and target is not fs0:
        fs0.vertex_indices = np.array(target.vertex_indices, copy=True)


def world_stats(m):
    md = deps()["md"]
    attrs = md.get_merged_vertex_attributes(m)
    faces = faces_of(m.face_sets[0])
    pos = np.asarray(attrs["position"], dtype=np.float32)
    ok = bool(np.isfinite(pos).all())
    if "normal" in attrs:
        ok = ok and bool(np.isfinite(np.asarray(attrs["normal"], dtype=np.float32)).all())
    return len(faces), len(pos), ok


def load_base(src_path, cfg):
    """Vanilla FLVER + LOD0 textures + native LOD promotion. Vertex arrays are untouched."""
    env = deps()["env"]
    flv = env.FLVER.from_path(src_path)
    name = Path(src_path).name
    eff = 1 if (cfg["hybrid"] and is_landmark(cfg["map_id"], name)) else cfg["lod"]
    if cfg["lod0"] != "off":
        env.force_lod0_material_textures(flv, cfg["available"])
    kinds, vst = {}, {}
    for mi, m in enumerate(flv.meshes):
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue
        van_tris = ntri(m.face_sets[0])
        van_verts = len(m.vertex_arrays[0].array)
        lods = {flag_id(fs): ntri(fs) for fs in m.face_sets}
        kind = mesh_kind(m, cfg["protect_mtd"])
        kinds[mi] = kind
        if kind != "sky":
            promote_native_lod(m, eff, 0.15 if kind == "foliage" else 0.25)
        stem = tex_stem_of_mesh(m)
        vst[mi] = dict(vanilla_tris=van_tris, tris=ntri(m.face_sets[0]), verts=van_verts,
                       shared=van_verts < van_tris, lods=lods, stem=stem, cat=tex_category(stem) if stem else "?")
    return flv, kinds, vst


def qem_attempt(src_path, cfg, targets, filename):
    d = deps()
    flv, _k, _v = load_base(src_path, cfg)
    d["md"].decimate_flver(flv, target_ratio=1.0, flat_normals=False, disable_cloth=False,
                           preserve_border=cfg["preserve_border"], submesh_targets=targets, filename=filename)
    return flv


def process_flver(job):
    src_path, cfg = job
    d = deps()
    env, md = d["env"], d["md"]
    name = Path(src_path).name
    block = Path(src_path).parent.name
    rep = dict(file=name, block=block, status="ok", changed=False, vanilla=0, promoted=0, final=0,
               meshes=[], errors=[], mtds=Counter())
    try:
        probe = env.FLVER.from_path(src_path)
        if env.is_sky_or_celestial_flver(probe, name):
            tris = sum(ntri(m.face_sets[0]) for m in probe.meshes if m.face_sets)
            rep.update(status="sky-vanilla", vanilla=tris, promoted=tris, final=tris)
            return rep
        del probe

        base, kinds, vst = load_base(src_path, cfg)
        rep["vanilla"] = sum(v["vanilla_tris"] for v in vst.values())
        rep["promoted"] = sum(v["tris"] for v in vst.values())
        lod_only = any(fnmatch.fnmatch(name, g) for g in cfg["lod_only"])
        landmark = is_landmark(cfg["map_id"], name)
        ratio = cfg["ratio_landmark"] if landmark else cfg["ratio_bg"]

        for mi, st in vst.items():
            mat, mtd = mesh_names(base.meshes[mi])
            rep["mtds"][mtd[-40:]] += st["vanilla_tris"]

        qem_scope = cfg["qem_landmarks"] or not landmark
        chosen, attempts = {}, []
        status = {mi: (f"untouched ({kinds[mi]})" if kinds[mi] in ("sky", "cloth") else "LOD-only") for mi in vst}
        if not cfg["audit"] and not lod_only:
            pending = {mi for mi, k in kinds.items()
                       if qem_scope and vst[mi]["tris"] >= cfg["qem_min_base"]
                       and qem_eligible(k, vst[mi]["stem"], cfg["qem_allow"], cfg["qem_deny"])
                       and plan_target(vst[mi]["tris"], vst[mi]["vanilla_tris"], ratio, cfg["min_frac"]) is not None}
            for r in ladder(ratio):
                if not pending:
                    break
                targets = {mi: plan_target(vst[mi]["tris"], vst[mi]["vanilla_tris"], r, cfg["min_frac"])
                           for mi in pending}
                targets = {mi: t for mi, t in targets.items() if t is not None}
                if not targets:
                    break
                try:
                    flv_a = qem_attempt(src_path, cfg, targets, name)
                except Exception as e:  # noqa: BLE001
                    rep["errors"].append(f"ratio {r}: {type(e).__name__}: {e}")
                    continue
                ai = len(attempts)
                attempts.append(flv_a)
                for mi in sorted(pending):
                    s = world_stats(flv_a.meshes[mi])
                    if world_mesh_ok(vst[mi]["tris"], vst[mi]["shared"], s):
                        chosen[mi] = ai
                        status[mi] = f"QEM r={r:.2f} -> {s[0]}"
                        pending.discard(mi)
            for mi in pending:
                status[mi] = "kept promoted LOD (QEM failed gates)"

        final = base          # base already holds the promoted LOD; replace only the chosen submeshes
        ref, _k, _v = load_base(src_path, cfg)
        for mi, ai in chosen.items():
            src_m, ref_m, fin_m = attempts[ai].meshes[mi], ref.meshes[mi], final.meshes[mi]
            new_attrs = restore_world_vertex_data(md.get_merged_vertex_attributes(ref_m),
                                                  md.get_merged_vertex_attributes(src_m), cfg["preserve"])
            md.write_attributes_to_mesh(fin_m, new_attrs, faces_of(src_m.face_sets[0]).astype(np.uint32))

        if cfg["foliage_keep"] < 1.0 and not cfg["audit"]:
            for mi, k in kinds.items():
                if k != "foliage":
                    continue
                fin_m = final.meshes[mi]
                nf = thin_components(faces_of(fin_m.face_sets[0]), cfg["foliage_keep"])
                if nf is None:
                    continue
                attrs, faces = compact_mesh(md.get_merged_vertex_attributes(fin_m), nf)
                md.write_attributes_to_mesh(fin_m, attrs, faces)
                status[mi] = f"cards thinned {vst[mi]['tris']} -> {len(nf)}"

        # Original AABBs are kept automatically: `final` is the vanilla FLVER with only vertex data/faces replaced.
        rep["final"] = sum(ntri(m.face_sets[0]) for mi, m in enumerate(final.meshes) if mi in vst)
        for mi, st in vst.items():
            mat, mtd = mesh_names(final.meshes[mi])
            elig = qem_scope and qem_eligible(kinds[mi], st["stem"], cfg["qem_allow"], cfg["qem_deny"])
            rep["meshes"].append(dict(mi=mi, kind=kinds[mi], mat=mat[:26], mtd=mtd[-26:], vanilla=st["vanilla_tris"],
                                      promoted=st["tris"], final=ntri(final.meshes[mi].face_sets[0]),
                                      lods=st["lods"], status=status.get(mi, "untouched"), cat=st["cat"],
                                      tex=st["stem"][-30:], eligible=bool(elig)))
        rep["changed"] = True       # every non-sky FLVER is rewritten (LOD0 texture paths, native LOD, QEM)
        if not cfg["audit"] and rep["changed"]:
            out = STAGE_DIR / block / name
            out.parent.mkdir(parents=True, exist_ok=True)
            final.write(out)
            bak = out.with_suffix(out.suffix + ".bak")
            if bak.exists():
                bak.unlink()
    except Exception as e:  # noqa: BLE001
        rep["status"] = f"FAILED {type(e).__name__}: {e}"
        rep["trace"] = traceback.format_exc()
    return rep


# ----------------------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------------------
def deploy_file(block, name):
    env = deps()["env"]
    src = STAGE_DIR / block / name
    dst = env.SANDBOX_ROOT / "map" / block / name
    assert "CUSA03173-PSX" in str(dst.resolve())
    if dst.exists():
        snap = dst.with_name(dst.name + SNAP_SUFFIX)
        if not snap.exists():
            shutil.copy2(dst, snap)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dst)


def restore(maps, only):
    env = deps()["env"]
    n = 0
    for mp in maps:
        for snap in sorted(glob.glob(str(env.SANDBOX_ROOT / "map" / f"{mp}_*" / f"*{SNAP_SUFFIX}"))):
            snap = Path(snap)
            orig = snap.with_name(snap.name[: -len(SNAP_SUFFIX)])
            if only and not any(fnmatch.fnmatch(orig.name, g) for g in only):
                continue
            assert "CUSA03173-PSX" in str(orig.resolve())
            shutil.copy2(snap, orig)
            n += 1
    print(f"[RESTORE] reverted {n} FLVER(s) from {SNAP_SUFFIX} snapshots")


def report_map(map_id, reports, a):
    ok = [r for r in reports if r["status"] in ("ok", "sky-vanilla")]
    van = sum(r["vanilla"] for r in ok)
    pro = sum(r["promoted"] for r in ok)
    fin = sum(r["final"] for r in ok)
    kinds = {}
    cats = {}
    stat = Counter()
    for r in ok:
        for x in r["meshes"]:
            k = kinds.setdefault(x["kind"], [0, 0, 0])
            k[0] += x["vanilla"]; k[1] += x["promoted"]; k[2] += x["final"]
            c = cats.setdefault(x["cat"], [0, 0, 0, 0])
            c[0] += x["vanilla"]; c[1] += x["promoted"]; c[2] += x["final"]; c[3] += x["promoted"] if x["eligible"] else 0
            stat[x["status"].split(" ->")[0].split(" r=")[0]] += 1
    print(f"\n========== {map_id}: {len(reports)} FLVERs ({sum(r['status'] == 'sky-vanilla' for r in reports)} sky kept vanilla) ==========")
    for r in sorted(reports, key=lambda r: -r["vanilla"])[: (len(reports) if a.verbose else 12)]:
        if r["status"].startswith("FAILED"):
            print(f"  [FAIL] {r['file']}: {r['status']}")
            continue
        pct = lambda x: x / max(1, r["vanilla"]) * 100  # noqa: E731
        print(f"  {r['file']:36s} {r['vanilla']:>9d} -> LOD {r['promoted']:>9d} ({pct(r['promoted']):4.0f}%) "
              f"-> final {r['final']:>9d} ({pct(r['final']):4.0f}%)")
        for e in r["errors"]:
            print(f"      [decimator error] {e}")
        if a.verbose:
            for x in r["meshes"]:
                lods = " ".join(f"L{k}:{v}" for k, v in sorted(x["lods"].items(), key=lambda kv: str(kv[0])))
                print(f"      {x['mi']:3d} {x['kind']:9s} {x['cat']:18s} {x['mtd']:26s} {x['vanilla']:>7d} -> {x['promoted']:>7d} "
                      f"-> {x['final']:>7d}  [{lods}]  {x['status']}")
    print(f"\n  TOTAL triangles: vanilla {van:,} -> native LOD {pro:,} ({pro / max(1, van) * 100:.1f}%) "
          f"-> final {fin:,} ({fin / max(1, van) * 100:.1f}%)")
    print("\n  By kind (vanilla -> native LOD -> final):")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1][0]):
        print(f"    {k:10s} {v[0]:>10,} -> {v[1]:>10,} -> {v[2]:>10,}")
    print("\n  By diffuse-texture category (vanilla -> native LOD -> final | QEM-eligible tris at native LOD):")
    for k, v in sorted(cats.items(), key=lambda kv: -kv[1][0])[:30]:
        print(f"    {k:22s} {v[0]:>10,} -> {v[1]:>10,} -> {v[2]:>10,} | {v[3]:>10,}")
    print("\n  submesh outcomes: " + ", ".join(f"{k}: {v}" for k, v in stat.most_common()))
    fails = [r for r in reports if r["status"].startswith("FAILED")]
    if fails:
        print(f"  [WARN] {len(fails)} FLVER(s) failed and were not staged.")
    if a.audit:
        mt = Counter()
        for r in ok:
            mt.update(r["mtds"])
        print("\n  Materials (MTD tail) by vanilla triangles - look for the DOL-lit ones, then pass them via --protect-mtd:")
        for k, v in mt.most_common(25):
            print(f"    {v:>10,}  {k}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--map", nargs="+", required=True, help="map ids, e.g. m21 m22 (or 'all')")
    p.add_argument("--only", default="", help="comma list of FLVER file-name globs, e.g. 'm21_00_00_00_0010*'")
    p.add_argument("--preset", choices=sorted(PRESETS), default="aggressive")
    p.add_argument("--ratio-landmark", type=float)
    p.add_argument("--ratio-bg", type=float)
    p.add_argument("--min-frac", type=float, help="floor as a fraction of VANILLA triangles per submesh")
    p.add_argument("--foliage-keep", type=float, help="EXPERIMENTAL: fraction of foliage cards kept (1.0 = off)")
    p.add_argument("--lod", type=int, choices=[1, 2], default=2, help="native LOD for background FLVERs (default 2)")
    p.add_argument("--uniform-lod", action="store_true", help="no hybrid: use --lod everywhere")
    p.add_argument("--lod0-textures", choices=["check", "always", "off"], default="check")
    p.add_argument("--preserve", default="colors,normals,tangents,extra",
                   help="vertex data copied back from the original (comma list; '' = let the decimator recompute)")
    p.add_argument("--protect-mtd", default=PROTECT_MTD_DEFAULT, help="comma list of MTD substrings that never get QEM")
    p.add_argument("--qem-allow-tex", default=QEM_ALLOW_DEFAULT,
                   help="QEM only submeshes whose diffuse texture name contains one of these, e.g. 'rock_big,cliff' "
                        "('*' = all body meshes). Default: empty = no QEM, native LOD only")
    p.add_argument("--qem-deny-tex", default=QEM_DENY_DEFAULT, help="never QEM texture names containing these (overrides allow)")
    p.add_argument("--qem-landmarks", action="store_true", help="also QEM landmark FLVERs (default: native LOD1 only)")
    p.add_argument("--qem-min-base", type=int, default=1000, help="skip submeshes with fewer promoted triangles than this")
    p.add_argument("--lod-only", default="", help="comma list of FLVER file-name globs that get native LOD only (e.g. DOL columns)")
    p.add_argument("--free-border", action="store_true", help="allow QEM to simplify open borders (more reduction, risk of cracks)")
    p.add_argument("--audit", action="store_true", help="no QEM, no writes: print LODs, materials and the plan")
    p.add_argument("--deploy", action="store_true")
    p.add_argument("--restore", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main():
    a = parse_args()
    env = deps()["env"]
    maps = a.map
    if maps == ["all"]:
        maps = sorted({Path(p).name[:3] for p in glob.glob(str(env.VANILLA_ROOT / "map" / "m[0-9][0-9]_*"))})
    only = [g.strip() for g in a.only.split(",") if g.strip()]
    if a.restore:
        restore(maps, only)
        return

    preset = dict(PRESETS[a.preset])
    for k in ("ratio_landmark", "ratio_bg", "min_frac", "foliage_keep"):
        v = getattr(a, k)
        if v is not None:
            preset[k] = v
    print(f"=== world ultra-low: maps={maps} preset={a.preset} {preset} "
          f"{'AUDIT' if a.audit else ('DEPLOY' if a.deploy else 'DRY RUN')} ===")
    if not [x for x in a.qem_allow_tex.split(",") if x.strip()]:
        print("  QEM: OFF (no --qem-allow-tex given) -> native LOD promotion only"
              + (", foliage thinning on" if preset["foliage_keep"] < 1.0 else ""))
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    for map_id in maps:
        files = sorted(glob.glob(str(env.VANILLA_ROOT / "map" / f"{map_id}_*" / "*.flver.dcx")))
        if only:
            files = [f for f in files if any(fnmatch.fnmatch(Path(f).name, g) for g in only)]
        if not files:
            print(f"[skip] no FLVERs for {map_id}")
            continue
        cfg = dict(map_id=map_id, lod=a.lod, hybrid=not a.uniform_lod, lod0=a.lod0_textures,
                   available=env.collect_map_texture_stems(map_id) if a.lod0_textures == "check" else None,
                   preserve=set(x.strip() for x in a.preserve.split(",") if x.strip()),
                   protect_mtd=[x.strip() for x in a.protect_mtd.split(",") if x.strip()],
                   qem_allow=[x.strip().lower() for x in a.qem_allow_tex.split(",") if x.strip()],
                   qem_deny=[x.strip().lower() for x in a.qem_deny_tex.split(",") if x.strip()],
                   qem_landmarks=a.qem_landmarks, qem_min_base=a.qem_min_base,
                   lod_only=[x.strip() for x in a.lod_only.split(",") if x.strip()],
                   preserve_border=not a.free_border, audit=a.audit, **preset)
        jobs = [(f, cfg) for f in files]
        reports = []
        if a.workers > 1:
            with ProcessPoolExecutor(max_workers=a.workers) as ex:
                futs = [ex.submit(process_flver, j) for j in jobs]
                for i, fu in enumerate(as_completed(futs), 1):
                    reports.append(fu.result())
                    if i % 25 == 0 or i == len(jobs):
                        print(f"  {map_id}: {i}/{len(jobs)}", flush=True)
        else:
            for i, j in enumerate(jobs, 1):
                reports.append(process_flver(j))
                if i % 25 == 0 or i == len(jobs):
                    print(f"  {map_id}: {i}/{len(jobs)}", flush=True)
        report_map(map_id, reports, a)

        if a.deploy and not a.audit:
            done = [r for r in reports if r["status"] == "ok" and r["changed"]]
            for r in done:
                deploy_file(r["block"], r["file"])
            print(f"  [DEPLOYED] {len(done)} FLVER(s) for {map_id} (snapshots: *{SNAP_SUFFIX})")
    if a.deploy and not a.audit:
        print("\nClear the bbhost cache before launching: rm -f ~/.local/share/bbhost/data/bbhost/*.bin")
    elif not a.audit:
        print(f"\nDry run: staged in {STAGE_DIR}. Add --deploy to write into CUSA03173-PSX.")


if __name__ == "__main__":
    main()