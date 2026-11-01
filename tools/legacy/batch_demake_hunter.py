"""
Batch PSX Demake Engine for Hunter Equipment, Armor Sets & Trick Weapons.
Applies mathematical QEM decimation (shared welded vertices, angle-weighted normals,
strict bone weight normalization), retro BC1 block texturing, and bone AABB preservation
across all player gear and weapons.
"""

import sys
import os
import shutil
import glob
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Tuple

sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch  # noqa: E402
from mesh_decimator import decimate_flver  # noqa: E402
from demake_color_engine import demake_texture_pixel_space  # noqa: E402

from soulstruct.containers import Binder  # noqa: E402
from soulstruct.flver import FLVER  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VANILLA_PARTS_DIR = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "parts"
SANDBOX_PARTS_DIR = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "parts"


def process_single_parts_file(
    filename: str,
    target_ratio: float = 0.45,
    target_dim: int = 256
) -> Tuple[str, bool, str]:
    """Processes a single partsbinder (.partsbnd.dcx) file with full mathematical demake."""
    vanilla_path = VANILLA_PARTS_DIR / filename
    sandbox_path = SANDBOX_PARTS_DIR / filename

    try:
        shutil.copy2(vanilla_path, sandbox_path)
        binder = Binder.from_path(str(sandbox_path))

        fn_lower = filename.lower()
        is_face_or_hair = any(fn_lower.startswith(p) for p in ('fc_', 'fg_', 'hr_'))

        for entry in binder.entries:
            if entry.name.endswith('.flver') and not is_face_or_hair:
                raw_flv = entry.get_uncompressed_data()
                if len(raw_flv) > 0x100:
                    flv = FLVER.from_bytes(raw_flv)
                    decimate_flver(
                        flv,
                        target_ratio=target_ratio,
                        flat_normals=False,
                        disable_cloth=False,
                        preserve_border=True,
                        filename=filename
                    )
                    entry.set_uncompressed_data(flv.to_bytes())

            elif entry.name.endswith('.tpf') and not is_face_or_hair:
                tpf_bytes = bytearray(entry.get_uncompressed_data())
                if tpf_bytes[:4] == b'TPF\x00':
                    tex_count = int.from_bytes(tpf_bytes[8:12], 'little')
                    for i in range(tex_count):
                        e = tpf_bytes[0x10 + i * 36 : 0x10 + (i + 1) * 36]
                        tex_off = int.from_bytes(e[0:4], 'little')
                        tex_sz = int.from_bytes(e[4:8], 'little')
                        unk1 = int.from_bytes(e[8:12], 'little')
                        unk2 = int.from_bytes(e[12:16], 'little')
                        str_off = int.from_bytes(e[24:28], 'little')

                        curr = str_off
                        while curr < len(tpf_bytes) - 1:
                            if tpf_bytes[curr] == 0 and tpf_bytes[curr + 1] == 0:
                                break
                            curr += 2
                        name = tpf_bytes[str_off:curr].decode('utf-16le', errors='ignore')
                        width = unk2 & 0xFFFF
                        height = (unk2 >> 16) & 0xFFFF
                        fmt = unk1 & 0xFF

                        base = name[:-2] if name.endswith('_l') else name
                        low_name = name.lower()

                        # Skip sky/celestial, blend masks, hair/fur BC7, and normal/specular maps
                        if any(k in low_name for k in ('sky', 'moon', 'cloud', 'blendmsk', 'mask', 'msk', 'fur', 'hair', 'beard')):
                            continue
                        if fmt == 0x66 or not base.endswith('_a'):
                            continue

                        orig = bytes(tpf_bytes[tex_off : tex_off + tex_sz])
                        demade_bytes = demake_texture_pixel_space(
                            orig, width, height, bpb=8, target_dim=target_dim, tex_name=name
                        )
                        if len(demade_bytes) == tex_sz:
                            tpf_bytes[tex_off : tex_off + tex_sz] = demade_bytes
                    entry.set_uncompressed_data(bytes(tpf_bytes))

        binder.write(str(sandbox_path))

        # Validation Audit against vanilla baseline
        b_v = Binder.from_path(str(vanilla_path))
        b_s = Binder.from_path(str(sandbox_path))
        for ev, es in zip(b_v.entries, b_s.entries):
            if es.name.endswith('.flver') and len(es.get_uncompressed_data()) > 0x100:
                flv_v = FLVER.from_binder_entry(ev)
                flv_s = FLVER.from_binder_entry(es)
                for bv, bs in zip(flv_v.bones, flv_s.bones):
                    if bv.bounding_box.min != bs.bounding_box.min or bv.bounding_box.max != bs.bounding_box.max:
                        return filename, False, "Bone AABB bounds corrupted"
                for mi, m in enumerate(flv_s.meshes):
                    if not m.vertex_arrays:
                        continue
                    num_v = len(m.vertex_arrays[0].array)
                    for fs in m.face_sets:
                        if fs.vertex_indices.max() >= num_v:
                            return filename, False, f"Mesh {mi} FaceSet out of bounds"

        return filename, True, "OK"
    except Exception as ex:
        return filename, False, str(ex)


def run_batch_hunter_demake(target_ratio: float = 0.45, target_dim: int = 256, max_workers: int = 8):
    SANDBOX_PARTS_DIR.mkdir(parents=True, exist_ok=True)

    # Discover all player equipment and weapon binders dynamically via globbing
    pattern_files = []
    for prefix in ('hd_', 'bd_', 'am_', 'lg_', 'wp_'):
        pattern_files.extend(glob.glob(str(VANILLA_PARTS_DIR / f"{prefix}*.partsbnd.dcx")))
    files_to_process = [Path(p).name for p in pattern_files]

    print(f"=== Starting Comprehensive Hunter & Weapon Batch: {len(files_to_process)} files ===")

    total_processed = 0
    total_failed = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_single_parts_file, fname, target_ratio, target_dim): fname
            for fname in files_to_process
        }

        for future in as_completed(futures):
            fname, success, msg = future.result()
            if success:
                total_processed += 1
                print(f"[VERIFIED] {fname}")
            else:
                total_failed += 1
                print(f"[FAIL] {fname}: {msg}")

    print(f"\n=== Batch Complete ===")
    print(f"Total Processed: {total_processed} / {len(files_to_process)}")
    print(f"Total Failed: {total_failed}")
    return total_failed == 0


if __name__ == '__main__':
    ratio = float(sys.argv[1]) if len(sys.argv) > 1 else 0.45
    dim = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    success = run_batch_hunter_demake(target_ratio=ratio, target_dim=dim, max_workers=workers)
    sys.exit(0 if success else 1)