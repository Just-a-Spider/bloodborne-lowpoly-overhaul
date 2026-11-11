#!/usr/bin/env python3
"""
verify_mod_switcher.py - Automated Verification Suite for Feature 003

Validates:
1. Pad chord detection & 3000ms debounce lockout (US1).
2. 5-Pillar atomic VFS overlay swap and link integrity (US2).
3. State persistence & session recovery against JSON schema contract (US3).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import time

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.fixtures.switcher.validate_schema import validate_contract
from tools.pipeline.mod_overlay_manager import ModOverlayManager, MOD_PILLAR_NAMES
from tools.pipeline.mod_switcher_state import StateManager
from tools.pipeline.mod_switcher_types import BTN_L3, BTN_R3, VisualMode
from tools.pipeline.pad_chord_detector import PadChordDetector


def test_pad_chord() -> bool:
    print("[TEST] Running Pad Chord & Debounce Verification (US1)...")
    detector = PadChordDetector(debounce_duration_ms=3000)
    trigger_count = 0

    def on_toggle():
        nonlocal trigger_count
        trigger_count += 1

    detector.register_callback(on_toggle)

    t0 = 1000

    # 1. Single L3 press: should NOT trigger
    res1 = detector.process_buttons(BTN_L3, timestamp_ms=t0)
    assert not res1 and trigger_count == 0, "Single L3 must not trigger chord!"

    # 2. Single R3 press: should NOT trigger
    res2 = detector.process_buttons(BTN_R3, timestamp_ms=t0 + 100)
    assert not res2 and trigger_count == 0, "Single R3 must not trigger chord!"

    # 3. Simultaneous L3 + R3 press: MUST trigger
    res3 = detector.process_buttons(BTN_L3 | BTN_R3, timestamp_ms=t0 + 200)
    assert res3 and trigger_count == 1, "Simultaneous L3 + R3 must trigger chord!"

    # 4. Rapid spam within 3000ms: MUST be debounced
    for offset in range(300, 2500, 200):
        res_spam = detector.process_buttons(BTN_L3 | BTN_R3, timestamp_ms=t0 + offset)
        assert not res_spam, f"Spam at +{offset}ms must be debounced!"
    assert trigger_count == 1, "Duplicate trigger occurred during debounce window!"

    # 5. After 3000ms expiration: MUST trigger again
    # Release first
    detector.process_buttons(0, timestamp_ms=t0 + 3100)
    res4 = detector.process_buttons(BTN_L3 | BTN_R3, timestamp_ms=t0 + 3300)
    assert res4 and trigger_count == 2, "L3 + R3 after debounce expiration must trigger!"

    print("  [PASS] US1 Pad chord detection & debounce lockout verified (100% compliant).")
    return True


def test_overlay_swap() -> bool:
    print("[TEST] Running 5-Pillar Atomic Overlay Swap Verification (US2)...")
    with tempfile.TemporaryDirectory() as td:
        overlay_dir = Path(td) / "mod-game-verify"
        mom = ModOverlayManager(
            overlay_dir=overlay_dir,
            vanilla_dir=Path("CUSA03173"),
            mods_dir=Path("mods"),
        )

        # 1. Initialize in RETRO_5PILLAR mode
        mode = mom.initialize_overlay(VisualMode.RETRO_5PILLAR)
        assert mode == VisualMode.RETRO_5PILLAR, "Initial mode must be RETRO_5PILLAR!"
        assert mom.get_active_mode() == VisualMode.RETRO_5PILLAR

        # Check VFS integrity
        valid, broken = mom.validate_vfs_integrity()
        assert valid, f"Broken symlinks detected in RETRO mode: {broken}"

        # 2. Perform atomic swap to VANILLA_HD
        ok, duration_ms = mom.atomic_swap_profile(VisualMode.VANILLA_HD)
        assert ok, "Atomic swap to VANILLA_HD failed!"
        assert duration_ms < 10.0, f"Swap duration too slow: {duration_ms:.3f} ms (expected < 10ms)"
        assert mom.get_active_mode() == VisualMode.VANILLA_HD, "Active mode did not switch to VANILLA_HD!"

        # Check VFS integrity in vanilla
        valid, broken = mom.validate_vfs_integrity()
        assert valid, f"Broken symlinks detected in VANILLA mode: {broken}"

        # 3. Swap back to RETRO_5PILLAR
        ok2, duration_ms2 = mom.atomic_swap_profile(VisualMode.RETRO_5PILLAR)
        assert ok2, "Atomic swap back to RETRO_5PILLAR failed!"
        assert mom.get_active_mode() == VisualMode.RETRO_5PILLAR

        print(f"  [PASS] US2 5-Pillar atomic swap verified (duration: {duration_ms:.3f} ms, 0 broken links).")
    return True


def test_persistence() -> bool:
    print("[TEST] Running State Persistence & Recovery Verification (US3)...")
    with tempfile.TemporaryDirectory() as td:
        state_file = Path(td) / "retro_toggle_state.json"
        schema_path = Path("specs/003-realtime-graphics-toggle/contracts/toggle_state_schema.json")
        sm = StateManager(state_path=state_file, schema_path=schema_path)

        # 1. Initial load writes default state
        cfg1 = sm.load()
        assert cfg1.active_mode == VisualMode.RETRO_5PILLAR
        assert state_file.is_file()

        # 2. Validate JSON schema contract
        assert validate_contract(state_file, schema_path), "State file violates JSON schema contract!"

        # 3. Update active mode and save
        cfg1.active_mode = VisualMode.VANILLA_HD
        sm.save(cfg1)

        # 4. Simulate application reboot: fresh StateManager instance reads disk
        sm2 = StateManager(state_path=state_file, schema_path=schema_path)
        cfg2 = sm2.load()
        assert cfg2.active_mode == VisualMode.VANILLA_HD, "Failed to persist mode across reboots!"

        # 5. Test mods.json sync
        mods_json = Path(td) / "mods.json"
        sm.sync_bbport_mods_json(mods_json, VisualMode.VANILLA_HD)
        import json
        m_data = json.loads(mods_json.read_text(encoding="utf-8"))
        for pillar in MOD_PILLAR_NAMES:
            assert pillar in m_data["disabled"], f"Pillar {pillar} should be disabled in VANILLA_HD mode!"

        sm.sync_bbport_mods_json(mods_json, VisualMode.RETRO_5PILLAR)
        m_data2 = json.loads(mods_json.read_text(encoding="utf-8"))
        for pillar in MOD_PILLAR_NAMES:
            assert pillar not in m_data2["disabled"], f"Pillar {pillar} should be enabled in RETRO_5PILLAR mode!"

        print("  [PASS] US3 State persistence & mods.json profile sync verified (100% compliant).")
    return True


def main():
    parser = argparse.ArgumentParser(description="Bloodborne Mod Switcher Verification Suite")
    parser.add_argument("--test", choices=["pad-chord", "overlay-swap", "persistence"], help="Run single test suite")
    parser.add_argument("--all", action="store_true", help="Run all verification suites")

    args = parser.parse_args()

    results = []
    if args.test == "pad-chord" or args.all:
        results.append(test_pad_chord())
    if args.test == "overlay-swap" or args.all:
        results.append(test_overlay_swap())
    if args.test == "persistence" or args.all:
        results.append(test_persistence())

    if not results:
        parser.print_help()
        sys.exit(1)

    if all(results):
        print("[SUCCESS] All In-Game Mod Switcher verification suites passed cleanly.")
        sys.exit(0)
    else:
        print("[FAILURE] One or more verification suites failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
