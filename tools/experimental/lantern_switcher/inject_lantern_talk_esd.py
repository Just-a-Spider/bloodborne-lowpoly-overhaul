#!/usr/bin/env python3
"""
inject_lantern_talk_esd.py - Talk ESD Injection for Native Lantern Mod Switcher

Patches FromSoftware lamp Talk ESDs so that interacting with ANY lit lantern
in-game natively displays the graphics presentation toggle options:
- Text ID 70011010: "Switch to Retro 32-Bit Demake" (Choice 20 -> Flag 999901 + Warp)
- Text ID 70011011: "Restore Modern High-Definition" (Choice 21 -> Flag 999902 + Warp)

Preserves 100% of FromSoftware unlit lamp ignition logic (SM 2147483644 State 7 -> SM 2147483639).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys
from typing import Dict, List

from soulstruct.base.ezstate.esd import Command, Condition, State
from soulstruct.bloodborne.ezstate import TalkESDBND
from soulstruct.containers import Binder

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_GAME_TALK = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "script" / "talk"

# All 56 lit lantern Talk ESDs across FromSoftware's 16 Bloodborne maps
ALL_LAMP_ESDS: Dict[str, List[str]] = {
    "m21_01_00_00.talkesdbnd.dcx": ["t211000.esd"],
    "m22_00_00_00.talkesdbnd.dcx": ["t220000.esd", "t220001.esd"],
    "m23_00_00_00.talkesdbnd.dcx": ["t230000.esd", "t230001.esd", "t230002.esd"],
    "m24_00_00_00.talkesdbnd.dcx": ["t240000.esd", "t240001.esd", "t240002.esd", "t240003.esd"],
    "m24_01_00_00.talkesdbnd.dcx": ["t241000.esd", "t241001.esd", "t241002.esd", "t241003.esd"],
    "m24_02_00_00.talkesdbnd.dcx": ["t242000.esd", "t242001.esd", "t242002.esd"],
    "m25_00_00_00.talkesdbnd.dcx": ["t250000.esd", "t250001.esd", "t250002.esd"],
    "m26_00_00_00.talkesdbnd.dcx": ["t260000.esd", "t260001.esd", "t260002.esd", "t260003.esd"],
    "m27_00_00_00.talkesdbnd.dcx": ["t270000.esd", "t270001.esd"],
    "m28_00_00_00.talkesdbnd.dcx": ["t280000.esd", "t280001.esd", "t280002.esd", "t280003.esd"],
    "m29_00_00_00.talkesdbnd.dcx": [
        "t290110.esd", "t290111.esd", "t290112.esd", "t290113.esd", "t290114.esd",
        "t290115.esd", "t290116.esd", "t290117.esd", "t290118.esd", "t290119.esd",
    ],
    "m32_00_00_00.talkesdbnd.dcx": ["t320000.esd", "t320001.esd", "t320002.esd", "t320003.esd"],
    "m33_00_00_00.talkesdbnd.dcx": ["t330000.esd", "t330001.esd"],
    "m34_00_00_00.talkesdbnd.dcx": ["t340000.esd", "t340001.esd", "t340002.esd", "t340003.esd"],
    "m35_00_00_00.talkesdbnd.dcx": ["t350000.esd", "t350001.esd", "t350002.esd"],
    "m36_00_00_00.talkesdbnd.dcx": ["t360000.esd", "t360001.esd", "t360002.esd"],
}

# Backward compatibility alias
LAMP_MAP = ALL_LAMP_ESDS


def ezl_int(n: int) -> bytearray:
    """Encodes an integer expression in FromSoftware EZL bytecode."""
    if -64 <= n <= 63:
        return bytearray([n + 64]) + b"\xa1"
    return bytearray(b"\x82" + struct.pack("<i", n) + b"\xa1")


def ezl_cond_result(choice_id: int) -> bytes:
    """Compiles: GetTalkListEntryResult() == choice_id."""
    prefix = bytes.fromhex("5784a6")
    if -64 <= choice_id <= 63:
        val = bytes([choice_id + 64])
    else:
        val = b"\x82" + struct.pack("<i", choice_id)
    return prefix + val + bytes.fromhex("95a1")


def make_call_warp() -> Command:
    """Calls SM 2147483641(MACHINE_ARGS[0], MACHINE_ARGS[1], 0) to trigger native lamp warp."""
    return Command(
        bank=6,
        index=2147483641,
        args=[bytearray(b"@\xb8\xa1"), bytearray(b"A\xb8\xa1"), bytearray(b"@\xa1")],
    )


def make_cond_exit(exit_state_id: int = 19) -> Condition:
    """Condition: MACHINE_CALL_STATUS != ONGOING -> transition to exit state."""
    return Condition(
        next_state_id=exit_state_id,
        test_ezl=bytes.fromhex("b9ba96a1"),
        pass_commands=[],
        subconditions=[],
    )


def patch_moal_esd(esd) -> bool:
    """Patches MOAL's existing SM 2147483500 to add retro & modern toggle options."""
    if 2147483500 not in esd.state_machines:
        return False

    # DO NOT touch SM 2147483644 State 7! MOAL State 6 already calls 2147483500, State 7 calls 2147483639.
    sm = esd.state_machines[2147483500]
    s0 = sm[0]

    exit_state_id = s0.conditions[0].next_state_id

    # Check if already patched
    for cmd in s0.enter_commands:
        if cmd.bank == 1 and cmd.index == 19 and len(cmd.args) >= 2:
            if ezl_int(70011010) in cmd.args:
                return True  # Already injected

    # Insert choice 20 and 21 before the final ShowShopMessage command
    cmd_retro = Command(
        bank=1,
        index=19,
        args=[ezl_int(20), ezl_int(70011010), ezl_int(-1)],
    )
    cmd_modern = Command(
        bank=1,
        index=19,
        args=[ezl_int(21), ezl_int(70011011), ezl_int(-1)],
    )
    s0.enter_commands.insert(-1, cmd_retro)
    s0.enter_commands.insert(-1, cmd_modern)

    # Add branch conditions
    cond_retro = Condition(
        next_state_id=20,
        test_ezl=ezl_cond_result(20),
        pass_commands=[],
        subconditions=[],
    )
    cond_modern = Condition(
        next_state_id=21,
        test_ezl=ezl_cond_result(21),
        pass_commands=[],
        subconditions=[],
    )
    s0.conditions.append(cond_retro)
    s0.conditions.append(cond_modern)

    # State 20: Switch to Retro (Flag 999901 + Lamp Warp)
    sm[20] = State(
        state_id=20,
        conditions=[make_cond_exit(exit_state_id)],
        enter_commands=[
            Command(bank=1, index=11, args=[ezl_int(999901), ezl_int(1)]),
            make_call_warp(),
        ],
        exit_commands=[],
        ongoing_commands=[],
    )

    # State 21: Restore Modern HD (Flag 999902 + Lamp Warp)
    sm[21] = State(
        state_id=21,
        conditions=[make_cond_exit(exit_state_id)],
        enter_commands=[
            Command(bank=1, index=11, args=[ezl_int(999902), ezl_int(1)]),
            make_call_warp(),
        ],
        exit_commands=[],
        ongoing_commands=[],
    )

    return True


def patch_vanilla_esd(esd) -> bool:
    """Patches vanilla ESD: replaces warp dialog call in SM 2147483644 lit state with full menu SM 2147483500."""
    if 2147483644 not in esd.state_machines:
        return False

    sm_main = esd.state_machines[2147483644]

    # In vanilla SM 2147483644:
    # Overworld lamps: State 6 is lit lamp interaction (calls SM 2147483643), State 7 is ignition (calls SM 2147483639).
    # Chalice dungeon lamps (m29): State 5 is lit lamp interaction (calls SM 2147483643), State 6 is ignition (calls SM 2147483639).
    # Find the lit lamp state dynamically by searching for the command calling SM 2147483643 (or already calling 2147483500).
    lit_state_id = None
    orig_args = [bytearray(b"B\xb8\xa1"), bytearray(b"C\xb8\xa1"), bytearray(b"D\xb8\xa1")]
    for sid, st in sm_main.items():
        for c in st.enter_commands:
            if c.bank == 6 and c.index in (2147483643, 2147483500):
                lit_state_id = sid
                if c.args:
                    orig_args = list(c.args)
                break
        if lit_state_id is not None:
            break

    if lit_state_id is None:
        lit_state_id = 6

    if lit_state_id in sm_main:
        for cmd in sm_main[lit_state_id].enter_commands:
            if cmd.bank == 6 and cmd.index in (2147483643, 2147483500):
                cmd.index = 2147483500
                cmd.args = [bytearray(b) for b in orig_args]

    # Build SM 2147483500 from scratch
    sm_menu = {}

    # State 0: Dialogue menu entries
    s0_cmds = [
        Command(bank=1, index=20, args=[]),  # ClearTalkListData
        Command(bank=1, index=19, args=[ezl_int(1), ezl_int(70011001), ezl_int(-1)]),  # Return to Dream
        Command(bank=1, index=19, args=[ezl_int(20), ezl_int(70011010), ezl_int(-1)]),  # Switch to Retro
        Command(bank=1, index=19, args=[ezl_int(21), ezl_int(70011011), ezl_int(-1)]),  # Restore Modern HD
        Command(bank=1, index=19, args=[ezl_int(99), ezl_int(15000005), ezl_int(-1)]),  # Leave
        Command(bank=1, index=10, args=[ezl_int(0), ezl_int(0), ezl_int(0)]),  # ShowShopMessage
    ]

    # Canonical exit condition: GetTalkListEntryResult() == 0 or GetTalkListEntryResult() == 99
    # Bytecode: 5784a640955784a682630000009599a1
    # NOTE: NO IsTalkExclusiveMenuOpen() == 0 check (eliminates frame 0 abort)!
    cond_exit_menu = Condition(
        next_state_id=19,
        test_ezl=bytes.fromhex("5784a640955784a682630000009599a1"),
        pass_commands=[],
        subconditions=[],
    )

    s0_conds = [
        Condition(next_state_id=1, test_ezl=ezl_cond_result(1), pass_commands=[], subconditions=[]),
        Condition(next_state_id=20, test_ezl=ezl_cond_result(20), pass_commands=[], subconditions=[]),
        Condition(next_state_id=21, test_ezl=ezl_cond_result(21), pass_commands=[], subconditions=[]),
        cond_exit_menu,
    ]

    sm_menu[0] = State(
        state_id=0,
        conditions=s0_conds,
        enter_commands=s0_cmds,
        exit_commands=[],
        ongoing_commands=[],
    )

    # State 1: Return to Hunter's Dream (calls vanilla SM 2147483643)
    call_hd = Command(
        bank=6,
        index=2147483643,
        args=[bytearray(b) for b in orig_args],
    )
    sm_menu[1] = State(
        state_id=1,
        conditions=[make_cond_exit()],
        enter_commands=[call_hd],
        exit_commands=[],
        ongoing_commands=[],
    )

    # State 20: Switch to Retro (Flag 999901 + Lamp Warp)
    sm_menu[20] = State(
        state_id=20,
        conditions=[make_cond_exit()],
        enter_commands=[
            Command(bank=1, index=11, args=[ezl_int(999901), ezl_int(1)]),
            make_call_warp(),
        ],
        exit_commands=[],
        ongoing_commands=[],
    )

    # State 21: Restore Modern HD (Flag 999902 + Lamp Warp)
    sm_menu[21] = State(
        state_id=21,
        conditions=[make_cond_exit()],
        enter_commands=[
            Command(bank=1, index=11, args=[ezl_int(999902), ezl_int(1)]),
            make_call_warp(),
        ],
        exit_commands=[],
        ongoing_commands=[],
    )

    # State 19: Terminal exit
    sm_menu[19] = State(
        state_id=19,
        conditions=[Condition(next_state_id=-1, test_ezl=b"A\xa1", pass_commands=[], subconditions=[])],
        enter_commands=[],
        exit_commands=[],
        ongoing_commands=[],
    )

    esd.state_machines[2147483500] = sm_menu
    return True


def patch_talk_binder(source_path: Path, dest_path: Path, is_moal: bool = False) -> bool:
    """Reads a .talkesdbnd.dcx, patches all its lamp ESDs, and writes to dest_path."""
    filename = source_path.name.removesuffix(".bak")
    if filename not in ALL_LAMP_ESDS:
        return False

    lamp_targets = set(ALL_LAMP_ESDS[filename])
    bnd = Binder.from_path(source_path)

    patched_count = 0
    for entry in bnd.entries:
        entry_file = entry.name.replace("\\", "/").split("/")[-1]
        if entry_file in lamp_targets:
            esd = entry.to_binary_file(TalkESDBND.TALK_ESD_CLASS)
            if is_moal:
                ok = patch_moal_esd(esd)
            else:
                ok = patch_vanilla_esd(esd)

            if ok:
                entry.data = bytes(esd)
                patched_count += 1
            else:
                print(f"  [WARN] Failed to patch ESD {entry_file} in {filename}")

    if patched_count == 0:
        print(f"  [ERROR] No target ESDs patched in {filename}")
        return False

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    bnd.write(dest_path)
    return True


def inject_all():
    parser = argparse.ArgumentParser(description="Inject native lantern switcher into FromSoftware talk ESDs")
    parser.add_argument("--vanilla-out", type=Path, help="Output folder for patched vanilla ESDs")
    parser.add_argument("--patch-moal", type=Path, help="Path to MOAL dvdroot_ps4/script/talk/ directory to patch in-place")
    args = parser.parse_args()

    default_hud_mod = REPO_ROOT / "mods" / "Bloodborne Retro HUD and UI" / "dvdroot_ps4" / "script" / "talk"
    bbport_hud_mod = Path("/home/andre/Games/bbport-src/mods/Bloodborne Retro HUD and UI/dvdroot_ps4/script/talk")
    moal_mod_talk = args.patch_moal or Path("/home/andre/Games/bbport-src/mods/MOAL 107 2.1.0 2026-10-20T17-22Z xPW1O2eZ1/MOAL/dvdroot_ps4/script/talk")

    total_expected = sum(len(v) for v in ALL_LAMP_ESDS.values())
    print(f"[INJECT] Patching Vanilla Lamp ESDs ({total_expected} ESDs across 16 maps)...")
    success_count = 0
    for f_name in sorted(ALL_LAMP_ESDS.keys()):
        src = BASE_GAME_TALK / f_name
        dest_local = default_hud_mod / f_name
        dest_bbport = bbport_hud_mod / f_name
        ok1 = patch_talk_binder(src, dest_local, is_moal=False)
        ok2 = patch_talk_binder(src, dest_bbport, is_moal=False)
        if ok1 and ok2:
            success_count += 1
            print(f"  [OK] Vanilla {f_name} ({len(ALL_LAMP_ESDS[f_name])} lamps) patched.")

    print(f"[SUMMARY] Patched {success_count}/{len(ALL_LAMP_ESDS)} vanilla lamp talk binders ({total_expected} total ESDs).")

    if moal_mod_talk.is_dir():
        print(f"\n[INJECT] Patching MOAL Lamp ESDs ({total_expected} ESDs)...")
        moal_success = 0
        for f_name in sorted(ALL_LAMP_ESDS.keys()):
            moal_file = moal_mod_talk / f_name
            moal_bak = moal_mod_talk / f"{f_name}.bak"
            src = moal_bak if moal_bak.is_file() else moal_file
            if src.is_file():
                ok = patch_talk_binder(src, moal_file, is_moal=True)
                if ok:
                    moal_success += 1
                    print(f"  [OK] MOAL {f_name} ({len(ALL_LAMP_ESDS[f_name])} lamps) patched.")
        print(f"[SUMMARY] Patched {moal_success}/{len(ALL_LAMP_ESDS)} MOAL lamp talk binders.")


if __name__ == "__main__":
    inject_all()
