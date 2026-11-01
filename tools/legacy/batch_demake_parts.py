"""
Master Multi-Threaded Batch Demake Engine for Bloodborne Equipment & Weapons.
Processes all 1,190 parts in dvdroot_ps4/parts/ across all categories (wp, bd, hd, lg, am, fg, hr, fc).

Applies:
- QEM edge-collapse polygon reduction (target_ratio=0.45)
- Havok cloth preservation (skips QEM on cloth submeshes to protect _c.hkx particle buffers)
- Bone AABB bounds preservation (soulstruct_patch.py)
- retro 15-bit RGB555 palette quantization with contrast dithering
- Flat tangent normal mapping (0x8080FF) and zero specular reflection
- BC7 hair transparency protection
"""

import sys, os, glob, time, shutil, argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch
from auto_demake_engine import auto_demake_file

VANILLA_PARTS_DIR = Path("CUSA03173/dvdroot_ps4/parts")
SANDBOX_PARTS_DIR = Path("CUSA03173-PSX/dvdroot_ps4/parts")

def demake_worker(task: tuple[str, str, str, float, int]) -> tuple[str, bool, str, float]:
    """Worker process for demaking a single .partsbnd.dcx file."""
    filename, vanilla_path, sandbox_path, ratio, dim = task
    start_t = time.time()
    try:
        # Copy fresh from pristine vanilla reference
        shutil.copy2(vanilla_path, sandbox_path)
        
        # Apply mathematical demake
        success = auto_demake_file(
            sandbox_path,
            target_ratio=ratio,
            flat_normals=False,
            disable_cloth=False,
            target_dim=dim,
            skip_tpf=False,
            verbose=False,
        )
        elapsed = time.time() - start_t
        if success:
            return (filename, True, "OK", elapsed)
        else:
            return (filename, False, "auto_demake_file returned False", elapsed)
    except Exception as e:
        elapsed = time.time() - start_t
        return (filename, False, str(e), elapsed)

def main():
    parser = argparse.ArgumentParser(description="Multi-threaded batch demake for Bloodborne parts")
    parser.add_argument("--categories", nargs="+", default=["all"],
                        help="Categories to process (wp, bd, hd, lg, am, fg, hr, fc, or all)")
    parser.add_argument("--ratio", type=float, default=0.45, help="QEM decimation ratio (default: 0.45)")
    parser.add_argument("--dim", type=int, default=256, help="Texture target dim (default: 256px)")
    parser.add_argument("--workers", type=int, default=12, help="Number of parallel worker processes (default: 12)")
    parser.add_argument("--dry-run", action="store_true", help="List target files without processing")

    args = parser.parse_args()

    SANDBOX_PARTS_DIR.mkdir(parents=True, exist_ok=True)

    all_files = sorted(glob.glob(str(VANILLA_PARTS_DIR / "*.partsbnd.dcx")))
    if not all_files:
        print(f"Error: No .partsbnd.dcx files found in {VANILLA_PARTS_DIR}")
        sys.exit(1)

    target_files = []
    selected_cats = [c.lower() for c in args.categories]

    for f in all_files:
        fn = os.path.basename(f)
        prefix = fn.split("_")[0].lower()
        if "all" in selected_cats or prefix in selected_cats:
            target_files.append(fn)

    print("=================================================================")
    print(f">>> BLOODBORNE FULL EQUIPMENT DEMAKE BLITZ <<<")
    print(f"Target files: {len(target_files)} of {len(all_files)}")
    print(f"Categories: {', '.join(selected_cats)}")
    print(f"Parameters: ratio={args.ratio}, dim={args.dim}px, workers={args.workers}")
    print("=================================================================\n")

    if args.dry_run:
        print(f"[DRY RUN] Would process {len(target_files)} files.")
        return

    tasks = [
        (fn, str(VANILLA_PARTS_DIR / fn), str(SANDBOX_PARTS_DIR / fn), args.ratio, args.dim)
        for fn in target_files
    ]

    start_total = time.time()
    completed = 0
    succeeded = 0
    failed = 0
    failed_files = []

    print(f"Spawning {args.workers} worker processes...")
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(demake_worker, t): t[0] for t in tasks}

        for future in as_completed(futures):
            filename, success, msg, elapsed = future.result()
            completed += 1
            if success:
                succeeded += 1
            else:
                failed += 1
                failed_files.append((filename, msg))

            # Progress ticker every 50 files or when done
            if completed % 50 == 0 or completed == len(tasks):
                pct = (completed / len(tasks)) * 100
                rate = completed / max(0.1, (time.time() - start_total))
                print(f"[{completed:04d}/{len(tasks):04d}] ({pct:5.1f}%) | {rate:.1f} files/sec | Success: {succeeded}, Failed: {failed}")

    total_time = time.time() - start_total
    print("\n=================================================================")
    print(f">>> BATCH PROCESSING COMPLETE in {total_time:.1f}s ({total_time/60:.2f} min) <<<")
    print(f"Total Completed: {completed}/{len(tasks)}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed: {failed}")
    if failed_files:
        print("Failed files sample:")
        for fn, err in failed_files[:10]:
            print(f"  - {fn}: {err}")
    print("=================================================================\n")

    # Clean up any Soulstruct backup files
    bak_count = 0
    for bak in SANDBOX_PARTS_DIR.glob("*.bak"):
        try:
            bak.unlink()
            bak_count += 1
        except Exception:
            pass
    if bak_count > 0:
        print(f"Cleaned up {bak_count} backup (.bak) files.")

    # Wipe bbhost Vulkan pipeline caches
    cache_dir = Path.home() / ".local/share/bbhost/data/bbhost"
    cleared = 0
    for bin_file in cache_dir.glob("*.bin"):
        try:
            bin_file.unlink()
            cleared += 1
        except Exception:
            pass
    print(f"Cleared {cleared} bbhost Vulkan pipeline caches.")

if __name__ == "__main__":
    main()
