#!/usr/bin/env python3
"""
tools/pipeline/batch_demake_hud.py - Batch Pipeline Orchestrator for Bloodborne Retro HUD & UI Demake.
Packages output to CUSA03173-PSX sandbox and standalone addition mod 'mods/Bloodborne Retro HUD and UI/'.
"""

import sys
import os
import shutil
import time
import argparse
from pathlib import Path

# Add project root and tools directory to Python sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from tools.demake_ui_engine import demake_ui_file, process_ui_tpf
from soulstruct.dcx import decompress, compress
import tools.verify_hud_demake as verifier

DEFAULT_VANILLA = PROJECT_ROOT / "CUSA03173"
DEFAULT_SANDBOX = PROJECT_ROOT / "CUSA03173-PSX"
DEFAULT_MOD = PROJECT_ROOT / "mods" / "Bloodborne Retro HUD and UI"

def run_batch_hud_demake(
    vanilla_dir: Path,
    sandbox_dir: Path,
    mod_dir: Path,
    filter_group: str = "all",
    verify: bool = True,
    verbose: bool = True
) -> bool:
    src_tpf = vanilla_dir / "dvdroot_ps4" / "menu" / "common.tpf.dcx"
    dst_sandbox_tpf = sandbox_dir / "dvdroot_ps4" / "menu" / "common.tpf.dcx"
    dst_mod_tpf = mod_dir / "dvdroot_ps4" / "menu" / "common.tpf.dcx"
    bak_sandbox_tpf = sandbox_dir / "dvdroot_ps4" / "menu" / "common.tpf.dcx.bak"

    if not src_tpf.exists():
        print(f"Error: Vanilla source {src_tpf} not found!", file=sys.stderr)
        return False

    print("=" * 80)
    print("BLOODBORNE RETRO HUD & UI DEMAKE PIPELINE")
    print("=" * 80)
    print(f"Vanilla source:     {src_tpf}")
    print(f"Sandbox target:     {dst_sandbox_tpf}")
    print(f"Addition mod:       {dst_mod_tpf}")
    print(f"Filter group:       {filter_group}")
    print("-" * 80)

    start_time = time.time()

    # Step 1: Ensure pre-modification backup exists in sandbox
    dst_sandbox_tpf.parent.mkdir(parents=True, exist_ok=True)
    if not bak_sandbox_tpf.exists():
        if dst_sandbox_tpf.exists():
            shutil.copy2(dst_sandbox_tpf, bak_sandbox_tpf)
            print(f"[Backup] Staged existing sandbox file to {bak_sandbox_tpf.name}")
        else:
            shutil.copy2(src_tpf, bak_sandbox_tpf)
            print(f"[Backup] Staged vanilla retail backup to {bak_sandbox_tpf.name}")

    # Step 2: Decompress & Process TPF
    print("[1/3] Decompressing common.tpf.dcx...")
    raw_bytes, dcx_type = decompress(str(src_tpf))

    print(f"[2/3] Processing UI textures (filter={filter_group})...")
    demade_bytes, mod_cnt, byp_cnt = process_ui_tpf(raw_bytes, filter_group=filter_group, verbose=verbose)

    # Step 3: Compress with DCX and write to both destinations
    print("[3/3] Compressing and deploying containers...")
    comp_data = compress(bytes(demade_bytes), dcx_type=dcx_type)

    dst_sandbox_tpf.write_bytes(comp_data)
    print(f"  -> Written to sandbox: {dst_sandbox_tpf} ({len(comp_data) / 1024 / 1024:.2f} MB)")

    dst_mod_tpf.parent.mkdir(parents=True, exist_ok=True)
    dst_mod_tpf.write_bytes(comp_data)
    print(f"  -> Written to addition mod: {dst_mod_tpf} ({len(comp_data) / 1024 / 1024:.2f} MB)")

    elapsed = time.time() - start_time
    print("-" * 80)
    print(f"Packaging complete in {elapsed:.2f}s (modified {mod_cnt}, bypassed {byp_cnt})")

    # Step 4: Automated Verification
    if verify:
        print("\nExecuting automated acceptance verification...")
        harness = verifier.build_suite(dst_sandbox_tpf)
        passed, failed = harness.run()
        print(f"Verification: {'PASS' if failed == 0 else 'FAIL'} ({passed}/{passed+failed} tests passed)")
        if failed > 0:
            print("Error: Verification tests failed!", file=sys.stderr)
            return False

    print("=" * 80)
    return True

def main():
    parser = argparse.ArgumentParser(description="Bloodborne Retro HUD & UI Demake Pipeline")
    parser.add_argument("--vanilla", type=Path, default=DEFAULT_VANILLA, help="Path to vanilla CUSA03173")
    parser.add_argument("--sandbox", type=Path, default=DEFAULT_SANDBOX, help="Path to sandbox CUSA03173-PSX")
    parser.add_argument("--mod", type=Path, default=DEFAULT_MOD, help="Path to standalone addition mod")
    parser.add_argument("--filter", type=str, default="all", choices=["all", "us1", "us2", "us3"], help="Filter group")
    parser.add_argument("--no-verify", action="store_true", help="Skip verification harness")
    parser.add_argument("--verbose", action="store_true", default=False, help="Print detailed texture info")
    args = parser.parse_args()

    success = run_batch_hud_demake(
        vanilla_dir=args.vanilla,
        sandbox_dir=args.sandbox,
        mod_dir=args.mod,
        filter_group=args.filter,
        verify=not args.no_verify,
        verbose=args.verbose
    )

    if not success:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
