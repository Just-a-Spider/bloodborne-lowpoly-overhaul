#!/usr/bin/env python3
"""
mod_overlay_manager.py - Atomic Symlink Overlay Redirection Engine

Manages dual-profile VFS mounting (VANILLA_HD vs RETRO_5PILLAR) with kernel-atomic
symlink pivoting and 5-pillar synchronization.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Dict, List, Optional, Tuple

from tools.pipeline.mod_switcher_types import OverlayMountState, VisualMode

PILLAR_SUBDIRS = ["map", "obj", "parts", "chr", "menu"]

MOD_PILLAR_NAMES = [
    "Bloodborne Retro Maps",
    "Bloodborne Retro Props and Objects",
    "Bloodborne Retro Armors and Weapons - Cloth Physics",
    "Bloodborne Retro Characters",
    "Bloodborne Retro HUD and UI",
]


class ModOverlayManager:
    """Controls the dynamic switchable VFS overlay for Bloodborne."""

    def __init__(
        self,
        overlay_dir: Path,
        vanilla_dir: Path = Path("CUSA03173"),
        mods_dir: Path = Path("mods"),
    ):
        self.overlay_dir = Path(overlay_dir).resolve()
        self.vanilla_dir = Path(vanilla_dir).resolve()
        self.mods_dir = Path(mods_dir).resolve()
        self.profiles_dir = self.overlay_dir / "profiles"
        self.vanilla_profile = self.profiles_dir / "vanilla"
        self.retro_profile = self.profiles_dir / "retro"
        self.active_symlink = self.overlay_dir / "dvdroot_ps4"

    def setup_profiles(self) -> None:
        """Constructs both static profile directory trees without modifying source assets."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # 1. Vanilla profile: dvdroot_ps4 points to pristine base game
        if not self.vanilla_profile.exists():
            self.vanilla_profile.mkdir(parents=True, exist_ok=True)
            v_target = self.vanilla_dir / "dvdroot_ps4"
            v_link = self.vanilla_profile / "dvdroot_ps4"
            if not v_link.exists():
                v_link.symlink_to(v_target, target_is_directory=True)

        # 2. Retro 5-Pillar profile: layered virtual tree
        if not self.retro_profile.exists():
            retro_dvdroot = self.retro_profile / "dvdroot_ps4"
            retro_dvdroot.mkdir(parents=True, exist_ok=True)

            # Link baseline vanilla folders first
            v_dvdroot = self.vanilla_dir / "dvdroot_ps4"
            if v_dvdroot.is_dir():
                for item in v_dvdroot.iterdir():
                    dest = retro_dvdroot / item.name
                    if not dest.exists():
                        dest.symlink_to(item, target_is_directory=item.is_dir())

            # Overlay each active pillar
            for mod_name in MOD_PILLAR_NAMES:
                mod_dvdroot = self.mods_dir / mod_name / "dvdroot_ps4"
                if not mod_dvdroot.is_dir():
                    continue

                for sub_item in mod_dvdroot.iterdir():
                    target_sub = retro_dvdroot / sub_item.name
                    if sub_item.is_dir():
                        if target_sub.is_symlink():
                            target_sub.unlink()
                            target_sub.mkdir(exist_ok=True)
                            # populate original vanilla contents into folder
                            orig_dir = v_dvdroot / sub_item.name
                            if orig_dir.is_dir():
                                for f in orig_dir.iterdir():
                                    (target_sub / f.name).symlink_to(f, target_is_directory=f.is_dir())
                        elif not target_sub.exists():
                            target_sub.mkdir(exist_ok=True)

                        # Overlay mod files into folder
                        for f in sub_item.iterdir():
                            dest_f = target_sub / f.name
                            if dest_f.is_symlink() or dest_f.exists():
                                dest_f.unlink()
                            dest_f.symlink_to(f, target_is_directory=f.is_dir())
                    else:
                        if target_sub.is_symlink() or target_sub.exists():
                            target_sub.unlink()
                        target_sub.symlink_to(sub_item, target_is_directory=False)

    def initialize_overlay(self, initial_mode: VisualMode = VisualMode.RETRO_5PILLAR) -> VisualMode:
        """Initializes the active overlay symlink to the chosen mode."""
        self.setup_profiles()
        target = self.retro_profile / "dvdroot_ps4" if initial_mode == VisualMode.RETRO_5PILLAR else self.vanilla_profile / "dvdroot_ps4"

        if self.active_symlink.is_symlink() or self.active_symlink.exists():
            self.active_symlink.unlink()

        self.active_symlink.symlink_to(target, target_is_directory=True)
        return initial_mode

    def atomic_swap_profile(self, target_mode: VisualMode) -> Tuple[bool, float]:
        """
        Atomically switches the dvdroot_ps4 symlink to target_mode using atomic os.replace.
        Returns (success, swap_duration_ms).
        """
        t0 = time.perf_counter()
        target = self.retro_profile / "dvdroot_ps4" if target_mode == VisualMode.RETRO_5PILLAR else self.vanilla_profile / "dvdroot_ps4"

        tmp_link = self.overlay_dir / f"dvdroot_ps4.tmp.{os.getpid()}"
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()

        tmp_link.symlink_to(target, target_is_directory=True)
        os.replace(tmp_link, self.active_symlink)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        return True, duration_ms

    def get_active_mode(self) -> VisualMode:
        """Determines active mode by inspecting destination of active_symlink."""
        if not self.active_symlink.is_symlink():
            return VisualMode.VANILLA_HD
        resolved = self.active_symlink.resolve()
        if "retro" in str(resolved):
            return VisualMode.RETRO_5PILLAR
        return VisualMode.VANILLA_HD

    def validate_vfs_integrity(self) -> Tuple[bool, List[str]]:
        """
        Validates that all mounted symlinks resolve to valid readable targets.
        Returns (is_valid, list_of_broken_links).
        """
        broken = []
        if not self.active_symlink.exists():
            return False, ["active_symlink_does_not_exist"]

        for root, _, files in os.walk(self.active_symlink):
            root_path = Path(root)
            for f in files:
                p = root_path / f
                if p.is_symlink() and not p.exists():
                    broken.append(str(p))

        return len(broken) == 0, broken
