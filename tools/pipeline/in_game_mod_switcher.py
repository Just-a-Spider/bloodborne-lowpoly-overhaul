#!/usr/bin/env python3
"""
in_game_mod_switcher.py - In-Game On-Demand Retro Mod Switcher Runtime Service

Integrates PadChordDetector, ModOverlayManager, SceneReloadCoordinator, and StateManager.
Provides both an interactive runtime daemon and a CLI interface.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pipeline.mod_overlay_manager import ModOverlayManager
from tools.pipeline.mod_switcher_state import StateManager
from tools.pipeline.mod_switcher_types import TransitionPhase, VisualMode
from tools.pipeline.pad_chord_detector import PadChordDetector
from tools.pipeline.scene_reload_coordinator import SceneReloadCoordinator


class InGameModSwitcher:
    """Master controller coordinating input, VFS overlay, and persistent state."""

    def __init__(
        self,
        overlay_dir: Path,
        vanilla_dir: Path = Path("CUSA03173"),
        mods_dir: Path = Path("mods"),
        state_file: Path = Path("out/retro_toggle_state.json"),
    ):
        self.state_manager = StateManager(state_path=state_file)
        self.config = self.state_manager.load()

        self.overlay_manager = ModOverlayManager(
            overlay_dir=overlay_dir,
            vanilla_dir=vanilla_dir,
            mods_dir=mods_dir,
        )
        self.overlay_manager.initialize_overlay(self.config.active_mode)

        self.coordinator = SceneReloadCoordinator(
            overlay_manager=self.overlay_manager,
            fade_duration_ms=self.config.fade_duration_ms,
        )

        self.pad_detector = PadChordDetector(
            debounce_duration_ms=self.config.debounce_duration_ms
        )
        self.pad_detector.register_callback(self.on_chord_triggered)

    def on_chord_triggered(self) -> None:
        """Callback invoked when L3+R3 is pressed."""
        success = self.coordinator.request_switch()
        if success:
            # Advance state machine immediately to execute atomic swap
            while self.coordinator.phase != TransitionPhase.IDLE:
                self.coordinator.step()
                if self.coordinator.phase == TransitionPhase.AWAITING_SCENE_LOAD:
                    break  # Pause at scene load point in simulation

            new_mode = self.overlay_manager.get_active_mode()
            self.config.active_mode = new_mode
            self.state_manager.save(self.config)

    def toggle(self) -> VisualMode:
        """Manually triggers a mode toggle."""
        self.on_chord_triggered()
        return self.overlay_manager.get_active_mode()

    def set_mode(self, mode: VisualMode) -> None:
        """Forces the active presentation mode."""
        self.coordinator.request_switch(target_mode=mode)
        while self.coordinator.phase != TransitionPhase.IDLE:
            self.coordinator.step()
            if self.coordinator.phase == TransitionPhase.AWAITING_SCENE_LOAD:
                break
        self.config.active_mode = mode
        self.state_manager.save(self.config)

    def get_status(self) -> dict:
        """Returns the full runtime status report."""
        return {
            "active_mode": self.overlay_manager.get_active_mode().value,
            "phase": self.coordinator.phase.value,
            "is_debounced": self.pad_detector.is_locked(),
            "overlay_path": str(self.overlay_manager.overlay_dir),
            "config": self.config.to_dict(),
        }


def main():
    parser = argparse.ArgumentParser(description="Bloodborne In-Engine Retro Mod Switcher")
    parser.add_argument("--overlay", type=Path, default=Path("out/mod-game-runtime"), help="Active overlay directory")
    parser.add_argument("--vanilla", type=Path, default=Path("CUSA03173"), help="Pristine vanilla directory")
    parser.add_argument("--mods", type=Path, default=Path("mods"), help="Modular mods directory")
    parser.add_argument("--state", type=Path, default=Path("out/retro_toggle_state.json"), help="State file")
    parser.add_argument("--toggle", action="store_true", help="Toggle mode immediately")
    parser.add_argument("--set-mode", type=str, choices=["VANILLA_HD", "RETRO_5PILLAR"], help="Set specific mode")
    parser.add_argument("--status", action="store_true", help="Print status")

    args = parser.parse_args()
    switcher = InGameModSwitcher(
        overlay_dir=args.overlay,
        vanilla_dir=args.vanilla,
        mods_dir=args.mods,
        state_file=args.state,
    )

    if args.toggle:
        mode = switcher.toggle()
        print(f"Toggled to: {mode.value}")
    elif args.set_mode:
        switcher.set_mode(VisualMode(args.set_mode))
        print(f"Mode set to: {args.set_mode}")
    elif args.status:
        import json
        print(json.dumps(switcher.get_status(), indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
