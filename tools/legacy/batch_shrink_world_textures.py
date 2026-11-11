#!/usr/bin/env python3
"""
batch_shrink_world_textures.py - True VRAM reduction for world map textures (BXF .tpfbhd/.tpfbdt archives)
via lossless top-mip slicing.

Why this tool is required:
  Previous tools (batch_demake_environment.py) used downsample_env_tpf_same_size, which downsampled
  textures to 32px and then NEAREST-NEIGHBOR UPSCALED BACK to canvas dimensions (1024x1024 / 2048x2048)
  to preserve file offsets. This rendered chunky pixels but SAVED ZERO VRAM (Vulkan allocated full 2K/4K extents).
  
  This tool slices off the top N mip levels, rewrites TPF header dimensions (e.g. 2048x2048 -> 256x256),
  decrements mip count, and repacks the BXF container cleanly. Vulkan allocates 90-98% less VRAM per texture.

Usage:
    uv run python tools/batch_shrink_world_textures.py --map m21 --audit
    uv run python tools/batch_shrink_world_textures.py --map m21 --target 256
    uv run python tools/batch_shrink_world_textures.py --map m21 --target 256 --deploy
    uv run python tools/batch_shrink_world_textures.py --map m21 --restore
"""

import argparse
import os
import shutil
import struct
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from soulstruct.dcx import decompress, compress
from shrink_chr_textures import shrink_tpf

VANILLA_MAP = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "map"
SANDBOX_MAP = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "map"
STAGE_DIR = Path("/tmp/world_shrink_stage")
SNAP_SUFFIX = ".snap_pre_shrink"

CELESTIAL_KEYWORDS = ["cloud", "sky", "moon", "sun", "star", "magic", "cosmos"]


def is_celestial(name: str) -> bool:
    low = name.lower()
    return any(k in low for k in CELESTIAL_KEYWORDS)


def shrink_bxf_archive(bhd_path: Path, bdt_path: Path, target: int = 256, audit: bool = False):
    """
    Slices top mip levels for all eligible TPFs in a BXF container.
    Returns (new_bhd_bytes, new_bdt_bytes, stats_dict).
    """
    bhd_data = bytearray(bhd_path.read_bytes())
    bdt_data = bytearray(bdt_path.read_bytes())

    if len(bhd_data) < 0x40 or bhd_data[:4] != b"BHF4":
        raise ValueError(f"Invalid BXF BHF4 header in {bhd_path.name}")

    count = struct.unpack("<I", bhd_data[12:16])[0]
    out_bdt = bytearray(b"\x00" * 48)
    out_bhd = bytearray(bhd_data)

    total_orig_comp = 0
    total_new_comp = 0
    shrunk_textures = 0
    kept_textures = 0
    skipped_celestial = 0

    for i in range(count):
        rec_off = 0x40 + i * 36
        comp_sz, decomp_sz = struct.unpack("<2Q", bhd_data[rec_off + 8 : rec_off + 24])
        data_off, entry_id, name_off = struct.unpack("<3I", bhd_data[rec_off + 24 : rec_off + 36])

        curr = name_off
        while curr < len(bhd_data) - 1:
            if bhd_data[curr] == 0 and bhd_data[curr + 1] == 0:
                break
            curr += 2
        name = bhd_data[name_off:curr].decode("utf-16le", errors="ignore")

        total_orig_comp += comp_sz
        raw_payload = bytes(bdt_data[data_off : data_off + comp_sz])

        if is_celestial(name):
            skipped_celestial += 1
            new_payload = raw_payload
            new_decomp_sz = decomp_sz
        else:
            try:
                tpf_decomp, dcx_type = decompress(raw_payload)
                if tpf_decomp[:4] == b"TPF\x00":
                    shrunk_tpf, rows = shrink_tpf(tpf_decomp, want=lambda n: True, target=target)
                    if len(shrunk_tpf) < len(tpf_decomp):
                        new_payload = compress(shrunk_tpf, dcx_type)
                        new_decomp_sz = len(shrunk_tpf)
                        shrunk_textures += 1
                    else:
                        new_payload = raw_payload
                        new_decomp_sz = decomp_sz
                        kept_textures += 1
                else:
                    new_payload = raw_payload
                    new_decomp_sz = decomp_sz
                    kept_textures += 1
            except Exception:
                new_payload = raw_payload
                new_decomp_sz = decomp_sz
                kept_textures += 1

        total_new_comp += len(new_payload)

        if not audit:
            new_off = (len(out_bdt) + 15) & ~15
            out_bdt.extend(b"\x00" * (new_off - len(out_bdt)))
            out_bdt.extend(new_payload)

            out_bhd[rec_off + 8 : rec_off + 16] = struct.pack("<Q", len(new_payload))
            out_bhd[rec_off + 16 : rec_off + 24] = struct.pack("<Q", new_decomp_sz)
            out_bhd[rec_off + 24 : rec_off + 28] = struct.pack("<I", new_off)

    stats = {
        "count": count,
        "shrunk": shrunk_textures,
        "kept": kept_textures,
        "celestial": skipped_celestial,
        "orig_bytes": total_orig_comp,
        "new_bytes": total_new_comp,
    }
    return bytes(out_bhd), bytes(out_bdt), stats


def process_map(map_id: str, target: int, audit: bool, deploy: bool):
    vanilla_dir = VANILLA_MAP / map_id
    sandbox_dir = SANDBOX_MAP / map_id
    if not vanilla_dir.exists():
        print(f"[ERROR] Map directory not found: {vanilla_dir}")
        return

    bhd_files = sorted(vanilla_dir.glob(f"{map_id}_*.tpfbhd"))
    if (vanilla_dir / f"gi_env_{map_id}.tpfbhd").exists():
        bhd_files.append(vanilla_dir / f"gi_env_{map_id}.tpfbhd")

    print(f"\n=======================================================")
    print(f"=== Map {map_id.upper()} Mip Slicing (Target <= {target}px) ===")
    print(f"=== Found {len(bhd_files)} BXF archives ===")
    print(f"=======================================================\n")

    grand_orig = 0
    grand_new = 0
    grand_shrunk = 0

    for bhd_src in bhd_files:
        binder_stem = bhd_src.stem
        bdt_src = bhd_src.with_suffix(".tpfbdt")
        if not bdt_src.exists():
            continue

        # Use sandbox file as source if present (so existing modifications are preserved)
        bhd_in = sandbox_dir / bhd_src.name if (sandbox_dir / bhd_src.name).exists() else bhd_src
        bdt_in = sandbox_dir / bdt_src.name if (sandbox_dir / bdt_src.name).exists() else bdt_src

        t0 = time.time()
        print(f"Processing {binder_stem}...", end=" ", flush=True)
        new_bhd, new_bdt, stats = shrink_bxf_archive(bhd_in, bdt_in, target=target, audit=audit)
        elapsed = time.time() - t0

        orig_mb = stats["orig_bytes"] / (1024 * 1024)
        new_mb = stats["new_bytes"] / (1024 * 1024)
        pct = (1.0 - stats["new_bytes"] / max(1, stats["orig_bytes"])) * 100.0

        grand_orig += stats["orig_bytes"]
        grand_new += stats["new_bytes"]
        grand_shrunk += stats["shrunk"]

        print(f"Done in {elapsed:.1f}s | Shrunk: {stats['shrunk']}/{stats['count']} | {orig_mb:.1f} MB -> {new_mb:.1f} MB (-{pct:.1f}%)")

        if audit:
            continue

        if deploy:
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            dest_bhd = sandbox_dir / bhd_src.name
            dest_bdt = sandbox_dir / bdt_src.name

            # Snapshot before overwrite
            snap_bhd = dest_bhd.with_suffix(dest_bhd.suffix + SNAP_SUFFIX)
            snap_bdt = dest_bdt.with_suffix(dest_bdt.suffix + SNAP_SUFFIX)
            if dest_bhd.exists() and not snap_bhd.exists():
                shutil.copy2(dest_bhd, snap_bhd)
            if dest_bdt.exists() and not snap_bdt.exists():
                shutil.copy2(dest_bdt, snap_bdt)

            dest_bhd.write_bytes(new_bhd)
            dest_bdt.write_bytes(new_bdt)
        else:
            stage_dir = STAGE_DIR / map_id
            stage_dir.mkdir(parents=True, exist_ok=True)
            (stage_dir / bhd_src.name).write_bytes(new_bhd)
            (stage_dir / bdt_src.name).write_bytes(new_bdt)

    total_orig_mb = grand_orig / (1024 * 1024)
    total_new_mb = grand_new / (1024 * 1024)
    total_pct = (1.0 - grand_new / max(1, grand_orig)) * 100.0
    print(f"\n---> {map_id.upper()} Total: {grand_shrunk} textures sliced | {total_orig_mb:.1f} MB -> {total_new_mb:.1f} MB (-{total_pct:.1f}% on disk / VRAM)")
    if not deploy and not audit:
        print(f"Dry run staged to {STAGE_DIR / map_id}. Add --deploy to write to CUSA03173-PSX.")


def restore_map(map_id: str):
    sandbox_dir = SANDBOX_MAP / map_id
    if not sandbox_dir.exists():
        print(f"Nothing to restore for {map_id}")
        return

    snaps = list(sandbox_dir.glob(f"*{SNAP_SUFFIX}"))
    if not snaps:
        print(f"No snapshot files found in {sandbox_dir}")
        return

    print(f"Restoring {len(snaps)} snapshots for {map_id}...")
    for snap in snaps:
        orig = snap.with_name(snap.name[: -len(SNAP_SUFFIX)])
        shutil.move(snap, orig)
        print(f"  Restored {orig.name}")


def main():
    parser = argparse.ArgumentParser(description="Shrink world map BXF textures by dropping top mip levels")
    parser.add_argument("--map", nargs="+", default=["m21"], help="Map ID(s) to process (default: m21)")
    parser.add_argument("--target", type=int, default=256, help="Target max resolution (default: 256)")
    parser.add_argument("--audit", action="store_true", help="Read-only audit: print predicted size reductions")
    parser.add_argument("--deploy", action="store_true", help="Write directly to CUSA03173-PSX with snapshots")
    parser.add_argument("--restore", action="store_true", help="Restore snapshots from .snap_pre_shrink")
    args = parser.parse_args()

    for m in args.map:
        if args.restore:
            restore_map(m)
        else:
            process_map(m, target=args.target, audit=args.audit, deploy=args.deploy)


if __name__ == "__main__":
    main()

