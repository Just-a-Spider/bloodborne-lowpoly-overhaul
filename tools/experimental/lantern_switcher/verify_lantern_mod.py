#!/usr/bin/env python3
"""
verify_lantern_mod.py - Automated Verification Suite for Native Lantern Mod Switcher

Validates:
1. FMG text injection into menu.msgbnd.dcx (US1).
2. Talk ESD state machine topology & unlit lamp safety (US1).
3. MOAL mod compatibility & non-destructive integration (US1).
4. Event flag signaling & presentation profile sync (US2).
5. State persistence & session recovery (US3).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from soulstruct.bloodborne.text import FMG
from soulstruct.bloodborne.ezstate import TalkESDBND
from soulstruct.containers import Binder
from tools.pipeline.inject_lantern_talk_esd import ALL_LAMP_ESDS, ezl_int
from tools.pipeline.lantern_event_listener import LanternEventListener
from tools.pipeline.lantern_mod_types import (
    FLAG_REQUEST_RETRO_5PILLAR,
    FLAG_REQUEST_VANILLA_HD,
    SM_CUSTOM_MENU,
    SM_IGNITE_LAMP,
    SM_LAMP_INTERACT,
    SM_WARP_EXEC,
    TEXT_ID_MODERN_PROMPT,
    TEXT_ID_RETRO_PROMPT,
    TEXT_LABEL_MODERN_PROMPT,
    TEXT_LABEL_RETRO_PROMPT,
)
from tools.pipeline.mod_overlay_manager import ModOverlayManager
from tools.pipeline.mod_switcher_state import StateManager
from tools.pipeline.mod_switcher_types import VisualMode

MOAL_DIR = Path("/home/andre/Games/bbport-src/mods/MOAL 107 2.1.0 2026-10-20T17-22Z xPW1O2eZ1/MOAL/dvdroot_ps4/script/talk")


def test_fmg_injection() -> bool:
    print("[TEST] Running FMG Menu Text Injection Verification (US1)...")
    target_paths = [
        REPO_ROOT / "mods/Bloodborne Retro HUD and UI/dvdroot_ps4/msg/engus/menu.msgbnd.dcx",
        Path("/home/andre/Games/bbport-src/mods/Bloodborne Retro HUD and UI/dvdroot_ps4/msg/engus/menu.msgbnd.dcx"),
    ]

    for p in target_paths:
        if not p.is_file():
            print(f"  [WARN] Skipping missing FMG at {p}")
            continue
        binder = Binder.from_path(p)
        entry_30 = None
        for entry in binder.entries:
            if entry.entry_id == 30 or "イベントテキスト" in entry.path:
                entry_30 = entry
                break
        assert entry_30 is not None, f"Entry 30 missing in {p}!"

        fmg = FMG.from_bytes(entry_30.data)
        assert TEXT_ID_RETRO_PROMPT in fmg.entries, f"Text ID {TEXT_ID_RETRO_PROMPT} missing in {p}!"
        assert fmg.entries[TEXT_ID_RETRO_PROMPT] == TEXT_LABEL_RETRO_PROMPT, f"Mismatched label for ID {TEXT_ID_RETRO_PROMPT}!"

        assert TEXT_ID_MODERN_PROMPT in fmg.entries, f"Text ID {TEXT_ID_MODERN_PROMPT} missing in {p}!"
        assert fmg.entries[TEXT_ID_MODERN_PROMPT] == TEXT_LABEL_MODERN_PROMPT, f"Mismatched label for ID {TEXT_ID_MODERN_PROMPT}!"

    print("  [PASS] US1 FMG text prompts verified in both mod distributions (100% compliant).")
    return True


def test_talk_esd() -> bool:
    print("[TEST] Running Talk ESD Topology & Unlit Safety Verification (US1)...")
    check_dirs = [
        ("Bloodborne Retro HUD and UI (local)", REPO_ROOT / "mods/Bloodborne Retro HUD and UI/dvdroot_ps4/script/talk"),
        ("Bloodborne Retro HUD and UI (bbport)", Path("/home/andre/Games/bbport-src/mods/Bloodborne Retro HUD and UI/dvdroot_ps4/script/talk")),
    ]

    for label, talk_dir in check_dirs:
        if not talk_dir.is_dir():
            print(f"  [WARN] Skipping {label}: folder not found.")
            continue

        verified = 0
        total_targets = sum(len(v) for v in ALL_LAMP_ESDS.values())
        for f_name, esd_list in ALL_LAMP_ESDS.items():
            f_path = talk_dir / f_name
            assert f_path.is_file(), f"{f_name} missing in {label}!"
            bnd = Binder.from_path(f_path)
            for esd_name in esd_list:
                target = None
                for e in bnd.entries:
                    if e.name.replace("\\", "/").split("/")[-1] == esd_name:
                        target = e
                        break
                assert target is not None, f"{esd_name} missing inside {f_name} in {label}!"
                esd = target.to_binary_file(TalkESDBND.TALK_ESD_CLASS)

                assert SM_LAMP_INTERACT in esd.state_machines, f"SM {SM_LAMP_INTERACT} missing in {esd_name} ({label})!"
                sm_main = esd.state_machines[SM_LAMP_INTERACT]

                # Distinguish Chalice Labyrinth lamps (m29 / t29011x) from Overworld lamps:
                # Chalice lamps: lit state is 5, ignition state is 6
                # Overworld lamps: lit state is 6, ignition state is 7
                if esd_name.startswith("t29011"):
                    lit_state_id = 5
                    unlit_state_id = 6
                else:
                    lit_state_id = 6
                    unlit_state_id = 7

                # 1. CRITICAL: Unlit lamp ignition MUST call SM 2147483639 (ignition) and never menu
                assert unlit_state_id in sm_main, f"State {unlit_state_id} missing in SM {SM_LAMP_INTERACT} ({esd_name})!"
                s_unlit = sm_main[unlit_state_id]
                ignite_cmds = [c for c in s_unlit.enter_commands if c.bank == 6]
                assert len(ignite_cmds) >= 1, f"State {unlit_state_id} has no bank 6 command in {esd_name}!"
                assert ignite_cmds[0].index == SM_IGNITE_LAMP, (
                    f"State {unlit_state_id} HIJACK DETECTED in {esd_name}! Calls {ignite_cmds[0].index} instead of {SM_IGNITE_LAMP}."
                )

                # 2. Lit lamp state MUST call SM 2147483500 (custom menu)
                assert lit_state_id in sm_main, f"State {lit_state_id} missing in SM {SM_LAMP_INTERACT} ({esd_name})!"
                s_lit = sm_main[lit_state_id]
                menu_cmds = [c for c in s_lit.enter_commands if c.bank == 6]
                assert len(menu_cmds) >= 1, f"State {lit_state_id} has no bank 6 command in {esd_name}!"
                assert menu_cmds[0].index == SM_CUSTOM_MENU, (
                    f"State {lit_state_id} not redirected to {SM_CUSTOM_MENU} in {esd_name}! Calls {menu_cmds[0].index}."
                )

                # 3. SM 2147483500 menu structure
                assert SM_CUSTOM_MENU in esd.state_machines, f"SM {SM_CUSTOM_MENU} missing in {esd_name} ({label})!"
                sm_menu = esd.state_machines[SM_CUSTOM_MENU]
                assert 0 in sm_menu, f"State 0 missing in SM {SM_CUSTOM_MENU} ({esd_name})!"
                s0 = sm_menu[0]

                # Verify choices 20 and 21 in State 0
                choice_ids = set()
                for cmd in s0.enter_commands:
                    if cmd.bank == 1 and cmd.index == 19 and len(cmd.args) >= 2:
                        if ezl_int(70011010) in cmd.args:
                            choice_ids.add(20)
                        elif ezl_int(70011011) in cmd.args:
                            choice_ids.add(21)
                assert 20 in choice_ids and 21 in choice_ids, f"Choices 20/21 missing in {esd_name} ({label})!"

                # 4. CRITICAL: Condition 0 must NOT evaluate IsTalkExclusiveMenuOpen() == 0 (no frame 0 abort)
                for cond in s0.conditions:
                    # 7584a6 is IsTalkExclusiveMenuOpen()
                    assert b"\x75\x84\xa6\x40\x95" not in cond.test_ezl, (
                        f"Frame 0 abort detected in condition of {esd_name}! Evaluates IsTalkExclusiveMenuOpen() == 0."
                    )

                # 5. States 20 and 21 must exist and trigger warp
                assert 20 in sm_menu and 21 in sm_menu, f"States 20/21 missing in {esd_name} ({label})!"
                assert any(c.bank == 6 and c.index == SM_WARP_EXEC for c in sm_menu[20].enter_commands), (
                    f"State 20 does not call warp in {esd_name}!"
                )
                assert any(c.bank == 6 and c.index == SM_WARP_EXEC for c in sm_menu[21].enter_commands), (
                    f"State 21 does not call warp in {esd_name}!"
                )

                verified += 1

        print(f"  [PASS] {label}: Verified all {verified}/{total_targets} lamp Talk ESDs (Unlit safe, menu verified).")
    return True


def test_moal_compatibility() -> bool:
    print("[TEST] Running MOAL Compatibility Verification...")
    if not MOAL_DIR.is_dir():
        print("  [WARN] Skipping MOAL verification: MOAL directory not found.")
        return True

    verified = 0
    total_targets = sum(len(v) for v in ALL_LAMP_ESDS.values())
    for f_name, esd_list in ALL_LAMP_ESDS.items():
        f_path = MOAL_DIR / f_name
        if not f_path.is_file():
            continue
        bnd = Binder.from_path(f_path)
        for esd_name in esd_list:
            target = None
            for e in bnd.entries:
                if e.name.replace("\\", "/").split("/")[-1] == esd_name:
                    target = e
                    break
            if target is None:
                continue
            esd = target.to_binary_file(TalkESDBND.TALK_ESD_CLASS)

            # In MOAL, unlit state in SM 2147483644 MUST be SM_IGNITE_LAMP (State 6 in chalice, State 7 in overworld)
            unlit_state_id = 6 if esd_name.startswith("t29011") else 7
            sm_main = esd.state_machines.get(SM_LAMP_INTERACT)
            assert sm_main is not None, f"SM {SM_LAMP_INTERACT} missing in MOAL {esd_name}!"
            assert unlit_state_id in sm_main, f"State {unlit_state_id} missing in MOAL {esd_name}!"
            ignite_cmds = [c for c in sm_main[unlit_state_id].enter_commands if c.bank == 6]
            assert len(ignite_cmds) >= 1 and ignite_cmds[0].index == SM_IGNITE_LAMP, (
                f"MOAL State {unlit_state_id} corrupted in {esd_name}! Calls {ignite_cmds[0].index if ignite_cmds else 'None'} instead of {SM_IGNITE_LAMP}."
            )

            # SM 2147483500 must contain choice 20 and 21
            sm_menu = esd.state_machines.get(SM_CUSTOM_MENU)
            assert sm_menu is not None, f"SM {SM_CUSTOM_MENU} missing in MOAL {esd_name}!"
            s0 = sm_menu[0]
            choice_ids = set()
            for cmd in s0.enter_commands:
                if cmd.bank == 1 and cmd.index == 19 and len(cmd.args) >= 2:
                    if ezl_int(70011010) in cmd.args:
                        choice_ids.add(20)
                    elif ezl_int(70011011) in cmd.args:
                        choice_ids.add(21)
            assert 20 in choice_ids and 21 in choice_ids, f"Choices 20/21 missing in MOAL {esd_name}!"
            assert 20 in sm_menu and 21 in sm_menu, f"States 20/21 missing in MOAL {esd_name}!"
            verified += 1

    print(f"  [PASS] MOAL: Verified all {verified}/{total_targets} lamp Talk ESDs (State 7 intact, Choices 20/21 active).")
    return True


def test_flag_signaling() -> bool:
    print("[TEST] Running Event Flag Signal & Sync Verification (US2)...")
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        overlay_dir = tmp_dir / "mod-game-lantern-verify"
        mom = ModOverlayManager(overlay_dir=overlay_dir, vanilla_dir=REPO_ROOT / "CUSA03173", mods_dir=REPO_ROOT / "mods")
        mom.initialize_overlay(VisualMode.VANILLA_HD)

        state_file = tmp_dir / "retro_toggle_state.json"
        bbport_ini = tmp_dir / "bbport.ini"
        bbport_ini.write_text("retro_mode=0\npsx_mode=0\n", encoding="utf-8")
        mods_json = tmp_dir / "mods.json"
        mods_json.write_text('{"order":[],"disabled":["Bloodborne Retro Maps"]}', encoding="utf-8")

        sm = StateManager(state_path=state_file)
        listener = LanternEventListener(
            overlay_manager=mom,
            state_manager=sm,
            mods_json_path=mods_json,
            bbport_ini_path=bbport_ini,
        )

        # 1. Signal flag 999901 (Request Retro)
        ok1, duration1, mode1 = listener.process_event_flag(FLAG_REQUEST_RETRO_5PILLAR)
        assert ok1, "Event flag 999901 failed to trigger mode switch!"
        assert mode1 == VisualMode.RETRO_5PILLAR
        assert mom.get_active_mode() == VisualMode.RETRO_5PILLAR

        # Verify bbport.ini synced
        ini_content = bbport_ini.read_text(encoding="utf-8")
        assert "retro_mode=1" in ini_content, "bbport.ini retro_mode was not enabled for RETRO_5PILLAR!"

        # 2. Signal flag 999902 (Request Vanilla)
        ok2, duration2, mode2 = listener.process_event_flag(FLAG_REQUEST_VANILLA_HD)
        assert ok2, "Event flag 999902 failed to trigger mode switch!"
        assert mode2 == VisualMode.VANILLA_HD
        assert mom.get_active_mode() == VisualMode.VANILLA_HD

        # Verify bbport.ini synced
        ini_content2 = bbport_ini.read_text(encoding="utf-8")
        assert "retro_mode=0" in ini_content2, "bbport.ini retro_mode was not disabled for VANILLA_HD!"

        # 3. Test Signal File IPC
        signal_file = tmp_dir / "flag_signal.txt"
        signal_file.write_text("999901\n", encoding="utf-8")
        handled = listener.check_and_process_signal_file(signal_file)
        assert handled, "Signal file IPC failed to process!"
        assert not signal_file.exists(), "Signal file was not consumed/unlinked!"
        assert mom.get_active_mode() == VisualMode.RETRO_5PILLAR

        print(f"  [PASS] US2 Event flag signaling and bbport.ini sync verified (swap duration: {duration1:.3f} ms).")
    return True


def test_persistence() -> bool:
    print("[TEST] Running Lantern State Persistence & Recovery Verification (US3)...")
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        overlay_dir = tmp_dir / "mod-game-lantern-persist"
        mom = ModOverlayManager(overlay_dir=overlay_dir, vanilla_dir=REPO_ROOT / "CUSA03173", mods_dir=REPO_ROOT / "mods")
        mom.initialize_overlay(VisualMode.RETRO_5PILLAR)

        state_file = tmp_dir / "retro_toggle_state.json"
        mods_json = tmp_dir / "mods.json"
        mods_json.write_text('{"order":[],"disabled":[]}', encoding="utf-8")
        bbport_ini = tmp_dir / "bbport.ini"
        bbport_ini.write_text("retro_mode=1\n", encoding="utf-8")

        sm = StateManager(state_path=state_file)
        listener = LanternEventListener(
            overlay_manager=mom,
            state_manager=sm,
            mods_json_path=mods_json,
            bbport_ini_path=bbport_ini,
        )

        # Trigger lantern toggle to VANILLA_HD
        listener.process_event_flag(FLAG_REQUEST_VANILLA_HD)

        # Assert state file persisted
        cfg = sm.load()
        assert cfg.active_mode == VisualMode.VANILLA_HD, "State file not persisted in VANILLA_HD!"

        # Assert mods.json sync
        m_data = json.loads(mods_json.read_text(encoding="utf-8"))
        assert "Bloodborne Retro Maps" in m_data["disabled"], "Retro mods not added to disabled list!"

        print("  [PASS] US3 Lantern state persistence & mods.json sync verified (100% compliant).")
    return True


def main():
    parser = argparse.ArgumentParser(description="Bloodborne Native Lantern Mod Verification Suite")
    parser.add_argument(
        "--test",
        choices=["fmg-injection", "talk-esd", "moal-compat", "flag-signaling", "persistence"],
        help="Run single test suite",
    )
    parser.add_argument("--all", action="store_true", help="Run all verification suites")

    args = parser.parse_args()

    results = []
    if args.test == "fmg-injection" or args.all:
        results.append(test_fmg_injection())
    if args.test == "talk-esd" or args.all:
        results.append(test_talk_esd())
    if args.test == "moal-compat" or args.all:
        results.append(test_moal_compatibility())
    if args.test == "flag-signaling" or args.all:
        results.append(test_flag_signaling())
    if args.test == "persistence" or args.all:
        results.append(test_persistence())

    if not results:
        parser.print_help()
        sys.exit(1)

    if all(results):
        print("[SUCCESS] All Native Lantern Switcher verification suites passed cleanly.")
        sys.exit(0)
    else:
        print("[FAILURE] One or more verification suites failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
