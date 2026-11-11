#!/usr/bin/env python3
"""
lantern_event_listener.py - Event Flag Signal Bridge & VFS Overlay Coordinator

Listens for in-engine event flags 999901 (Retro 5-Pillar) and 999902 (Vanilla HD)
set by the native lantern Talk ESD. Automatically pivots the active bbport runtime
file overlay in < 0.1ms during the lantern warp fade window.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import struct
import sys
import time
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pipeline.lantern_mod_types import (
    FLAG_REQUEST_RETRO_5PILLAR,
    FLAG_REQUEST_VANILLA_HD,
)
from tools.pipeline.mod_overlay_manager import ModOverlayManager
from tools.pipeline.mod_switcher_state import StateManager
from tools.pipeline.mod_switcher_types import VisualMode

BBPORT_MODS_DIR = Path("/home/andre/Games/bbport-src/mods")
BBPORT_CONFIG_PATH = Path("/home/andre/Games/bbport-src/mods.json")
BBPORT_INI_PATH = Path("/home/andre/Games/bbport-src/bbport.ini")
BASE_GAME_DVDROOT = REPO_ROOT / "CUSA03173" / "dvdroot_ps4"

PILLAR_MAP = {
    "map": BBPORT_MODS_DIR / "Bloodborne Retro Maps" / "dvdroot_ps4" / "map",
    "obj": BBPORT_MODS_DIR / "Bloodborne Retro Props and Objects" / "dvdroot_ps4" / "obj",
    "parts": BBPORT_MODS_DIR / "Bloodborne Retro Armors and Weapons - Cloth Physics" / "dvdroot_ps4" / "parts",
    "chr": BBPORT_MODS_DIR / "Bloodborne Retro Characters" / "dvdroot_ps4" / "chr",
    "menu": BBPORT_MODS_DIR / "Bloodborne Retro HUD and UI" / "dvdroot_ps4" / "menu",
}


def read_proc_mem(pid: int, address: int, size: int) -> Optional[bytes]:
    """Reads raw bytes from /proc/<pid>/mem."""
    try:
        with open(f"/proc/{pid}/mem", "rb", 0) as f:
            f.seek(address)
            return f.read(size)
    except Exception:
        return None


def write_proc_mem(pid: int, address: int, data: bytes) -> bool:
    """Writes raw bytes to /proc/<pid>/mem."""
    try:
        with open(f"/proc/{pid}/mem", "r+b", 0) as f:
            f.seek(address)
            f.write(data)
            return True
    except Exception:
        return False


def read_u8(pid: int, address: int) -> Optional[int]:
    buf = read_proc_mem(pid, address, 1)
    return buf[0] if buf and len(buf) == 1 else None


def read_u32(pid: int, address: int) -> Optional[int]:
    buf = read_proc_mem(pid, address, 4)
    return struct.unpack("<I", buf)[0] if buf and len(buf) == 4 else None


def read_u64(pid: int, address: int) -> Optional[int]:
    buf = read_proc_mem(pid, address, 8)
    return struct.unpack("<Q", buf)[0] if buf and len(buf) == 8 else None


def find_image_base(pid: int) -> Optional[int]:
    """Finds guest image base address (starting at 0x0800000000) from /proc/<pid>/maps."""
    try:
        with open(f"/proc/{pid}/maps", "r") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                start_hex = parts[0].split("-")[0]
                addr = int(start_hex, 16)
                if addr >= 0x0800000000 and "r" in parts[1]:
                    return addr
    except Exception:
        pass
    return None


def get_active_mod_game_dir(pid: int) -> Optional[Path]:
    """Extracts active mod-game directory path from /proc/<pid>/cmdline."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().split(b"\x00")
            for arg in cmd:
                arg_str = arg.decode(errors="ignore")
                if "mod-game-" in arg_str:
                    p = Path(arg_str)
                    if p.is_dir():
                        return p
    except Exception:
        pass
    return None


def read_event_flag_bit(pid: int, image_base: int, flag_id: int) -> Tuple[bool, Optional[int], Optional[int]]:
    """
    Traverses SprjEventFlagMan red-black tree in bb-probe memory to read flag state.
    Returns (is_set, bit_ptr, bit_offset).
    """
    flag_man_ptr = read_u64(pid, image_base + 0x0553B100)
    if not flag_man_ptr:
        return False, None, None

    divisor = read_u32(pid, flag_man_ptr + 0x1C)
    if not divisor:
        return False, None, None

    block_id = (flag_id // divisor) * divisor
    root_node = read_u64(pid, flag_man_ptr + 0x38)
    if not root_node:
        return False, None, None

    # Tree traversal
    curr = read_u64(pid, root_node + 0x8)
    found_node = None
    while curr:
        is_nil = read_u8(pid, curr + 0x19)
        if is_nil is None or is_nil != 0:
            break
        curr_key = read_u32(pid, curr + 0x20)
        if curr_key is None:
            break
        if curr_key < block_id:
            curr = read_u64(pid, curr + 0x10)
        else:
            found_node = curr
            curr = read_u64(pid, curr + 0x8)

    if not found_node or read_u32(pid, found_node + 0x20) != block_id:
        return False, None, None

    node_type = read_u32(pid, found_node + 0x28)
    if node_type == 2:
        bit_ptr = read_u64(pid, found_node + 0x30)
    elif node_type == 1:
        chunk_sz = read_u32(pid, flag_man_ptr + 0x20) or 0
        chunk_idx = read_u32(pid, found_node + 0x30) or 0
        flags_data = read_u64(pid, flag_man_ptr + 0x28) or 0
        bit_ptr = flags_data + chunk_idx * chunk_sz
    else:
        return False, None, None

    if not bit_ptr:
        return False, None, None

    rem = flag_id % divisor
    byte_offset = rem >> 3
    bit_offset = 7 - (rem & 7)

    target_byte_addr = bit_ptr + byte_offset
    b = read_u8(pid, target_byte_addr)
    if b is None:
        return False, None, None

    is_set = bool((b >> bit_offset) & 1)
    return is_set, target_byte_addr, bit_offset


def clear_event_flag_bit(pid: int, byte_addr: int, bit_offset: int) -> bool:
    """Clears consumed event flag bit in process memory."""
    b = read_u8(pid, byte_addr)
    if b is None:
        return False
    cleared = b & ~(1 << bit_offset)
    return write_proc_mem(pid, byte_addr, bytes([cleared]))


def sync_bbport_ini(ini_path: Path, active_mode: VisualMode) -> bool:
    """Synchronizes retro_mode and psx_mode in bbport.ini."""
    target_ini = Path(ini_path)
    if not target_ini.is_file():
        return False
    try:
        lines = target_ini.read_text(encoding="utf-8").splitlines()
        val = "1" if active_mode == VisualMode.RETRO_5PILLAR else "0"
        new_lines = []
        has_retro = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("retro_mode="):
                new_lines.append(f"retro_mode={val}")
                has_retro = True
            elif stripped.startswith("psx_mode="):
                new_lines.append(f"psx_mode={val}")
            else:
                new_lines.append(line)
        if not has_retro:
            new_lines.append(f"retro_mode={val}")

        tmp = target_ini.with_suffix(".tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.replace(tmp, target_ini)
        return True
    except Exception as e:
        print(f"[WARN] Failed to sync bbport.ini at {ini_path}: {e}")
        return False


def pivot_active_game_dvdroot(mod_game_dvdroot: Path, target_mode: VisualMode) -> Tuple[bool, float]:
    """
    Safely pivots symlinks inside running mod-game-XXXX/dvdroot_ps4/
    between Retro 5-Pillar paths and Base Game CUSA03173 paths.
    Takes < 0.1ms. Safely handles materialized real directories without EISDIR.
    """
    t0 = time.perf_counter()
    if not mod_game_dvdroot.is_dir():
        return False, 0.0

    for pillar, retro_src in PILLAR_MAP.items():
        link_path = mod_game_dvdroot / pillar
        target = retro_src if target_mode == VisualMode.RETRO_5PILLAR else (BASE_GAME_DVDROOT / pillar)

        if not target.exists():
            continue

        if link_path.is_symlink():
            try:
                if link_path.resolve() == target.resolve():
                    continue
            except OSError:
                pass
            tmp_link = mod_game_dvdroot / f"{pillar}.tmp.{os.getpid()}"
            if tmp_link.exists() or tmp_link.is_symlink():
                tmp_link.unlink()
            tmp_link.symlink_to(target, target_is_directory=True)
            os.replace(tmp_link, link_path)
        elif link_path.is_dir():
            shutil.rmtree(link_path)
            link_path.symlink_to(target, target_is_directory=True)
        elif link_path.exists():
            link_path.unlink()
            link_path.symlink_to(target, target_is_directory=True)
        else:
            link_path.symlink_to(target, target_is_directory=True)

    dt_ms = (time.perf_counter() - t0) * 1000.0
    return True, dt_ms


class LanternEventListener:
    """Bridges FromSoftware in-engine event flags to host Linux VFS symlink pivots."""

    def __init__(
        self,
        overlay_manager: ModOverlayManager,
        state_manager: Optional[StateManager] = None,
        mods_json_path: Optional[Path] = None,
        bbport_ini_path: Optional[Path] = None,
        signal_file_path: Optional[Path] = None,
    ):
        self.overlay_manager = overlay_manager
        self.state_manager = state_manager or StateManager()
        self.mods_json_path = Path(mods_json_path) if mods_json_path else BBPORT_CONFIG_PATH
        self.bbport_ini_path = Path(bbport_ini_path) if bbport_ini_path else BBPORT_INI_PATH
        self.signal_file_path = Path(signal_file_path) if signal_file_path else (REPO_ROOT / "out" / "flag_signal.txt")
        self.last_flag_processed: Optional[int] = None
        self._proc_mem_warned = False

    def sync_bbport_ini(self, ini_path: Path, active_mode: VisualMode) -> bool:
        return sync_bbport_ini(ini_path, active_mode)

    def check_and_process_signal_file(
        self,
        signal_file: Optional[Path] = None,
        mod_game_dvdroot: Optional[Path] = None,
    ) -> bool:
        target_file = Path(signal_file) if signal_file else self.signal_file_path
        if not target_file.is_file():
            return False
        try:
            text = target_file.read_text(encoding="utf-8").strip()
            target_file.unlink()
            if not text:
                return False
            flag = int(text)
            self.process_event_flag(flag, mod_game_dvdroot)
            return True
        except Exception as e:
            print(f"[WARN] Error processing signal file {target_file}: {e}")
            if target_file.exists():
                try:
                    target_file.unlink()
                except OSError:
                    pass
            return False

    def process_event_flag(
        self, flag_id: int, mod_game_dvdroot: Optional[Path] = None
    ) -> Tuple[bool, float, VisualMode]:
        """
        Processes an in-engine event flag.
        Returns (success, swap_duration_ms, new_active_mode).
        """
        if flag_id == FLAG_REQUEST_RETRO_5PILLAR:
            target_mode = VisualMode.RETRO_5PILLAR
        elif flag_id == FLAG_REQUEST_VANILLA_HD:
            target_mode = VisualMode.VANILLA_HD
        else:
            return False, 0.0, self.overlay_manager.get_active_mode()

        t0 = time.perf_counter()

        # Pivot static overlay
        ok, duration_ms = self.overlay_manager.atomic_swap_profile(target_mode)

        # Pivot active running game if directory provided
        if mod_game_dvdroot and mod_game_dvdroot.is_dir():
            pivot_active_game_dvdroot(mod_game_dvdroot, target_mode)

        # Update persistent state
        cfg = self.state_manager.load()
        cfg.active_mode = target_mode
        self.state_manager.save(cfg)

        if self.mods_json_path and self.mods_json_path.is_file():
            self.state_manager.sync_bbport_mods_json(self.mods_json_path, target_mode)

        if self.bbport_ini_path and self.bbport_ini_path.is_file():
            self.sync_bbport_ini(self.bbport_ini_path, target_mode)

        self.last_flag_processed = flag_id
        return ok, duration_ms, target_mode

    def run_daemon(self, poll_interval_s: float = 0.05) -> None:
        """
        Continuously polls signal file IPC and guest memory for event flags 999901 / 999902.
        Pivots VFS overlay immediately upon detection.
        """
        print(f"[DAEMON] Lantern event listener active. Polling interval: {poll_interval_s*1000:.0f}ms...")
        print("[DAEMON] Monitoring signal file IPC and bb-probe process...")

        active_pid: Optional[int] = None
        image_base: Optional[int] = None
        mod_game_dvdroot: Optional[Path] = None

        while True:
            # 1. Always process signal file IPC
            self.check_and_process_signal_file(mod_game_dvdroot=mod_game_dvdroot)

            # 2. Check for bb-probe process
            if active_pid is None or not Path(f"/proc/{active_pid}").is_dir():
                active_pid = None
                image_base = None
                mod_game_dvdroot = None
                for proc_dir in Path("/proc").glob("[0-9]*"):
                    try:
                        comm = (proc_dir / "comm").read_text().strip()
                        if comm in ("bb-probe", "bbport"):
                            pid = int(proc_dir.name)
                            base = find_image_base(pid)
                            if base:
                                active_pid = pid
                                image_base = base
                                mod_dir = get_active_mod_game_dir(pid)
                                if mod_dir:
                                    mod_game_dvdroot = mod_dir / "dvdroot_ps4"
                                print(f"[DAEMON] Attached to bb-probe (PID {pid}, base 0x{base:x}, game: {mod_game_dvdroot})")
                                break
                    except Exception:
                        continue

            if active_pid and image_base:
                try:
                    # Check Retro Flag 999901
                    retro_set, addr, bit = read_event_flag_bit(active_pid, image_base, FLAG_REQUEST_RETRO_5PILLAR)
                    if retro_set and addr is not None and bit is not None:
                        print("[DAEMON] Event Flag 999901 detected! Switching to Retro 5-Pillar...")
                        clear_event_flag_bit(active_pid, addr, bit)
                        ok, ms, mode = self.process_event_flag(FLAG_REQUEST_RETRO_5PILLAR, mod_game_dvdroot)
                        print(f"[DAEMON] Swapped to {mode.name} in {ms:.3f} ms.")

                    # Check Modern HD Flag 999902
                    hd_set, addr, bit = read_event_flag_bit(active_pid, image_base, FLAG_REQUEST_VANILLA_HD)
                    if hd_set and addr is not None and bit is not None:
                        print("[DAEMON] Event Flag 999902 detected! Restoring Modern HD...")
                        clear_event_flag_bit(active_pid, addr, bit)
                        ok, ms, mode = self.process_event_flag(FLAG_REQUEST_VANILLA_HD, mod_game_dvdroot)
                        print(f"[DAEMON] Swapped to {mode.name} in {ms:.3f} ms.")
                except PermissionError:
                    if not self._proc_mem_warned:
                        print("[DAEMON] /proc/<pid>/mem restricted by kernel Yama ptrace scope. Active in file IPC mode.")
                        self._proc_mem_warned = True

            time.sleep(poll_interval_s)


def main():
    parser = argparse.ArgumentParser(description="Lantern Event Flag Listener & VFS Coordinator")
    parser.add_argument("--daemon", action="store_true", help="Run as background polling daemon")
    parser.add_argument("--flag", type=int, choices=[999901, 999902], help="Manually signal an event flag")
    args = parser.parse_args()

    overlay_mgr = ModOverlayManager(overlay_dir=REPO_ROOT / "out" / "vfs_overlay")
    overlay_mgr.initialize_overlay()
    listener = LanternEventListener(overlay_manager=overlay_mgr)

    if args.flag:
        ok, ms, mode = listener.process_event_flag(args.flag)
        print(f"Processed flag {args.flag}: mode={mode.name}, duration={ms:.3f}ms")
    elif args.daemon:
        listener.run_daemon()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
