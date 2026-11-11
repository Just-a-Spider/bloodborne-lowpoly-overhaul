#!/usr/bin/env python3
"""
mod_switcher_types.py - Domain Types & State Models for In-Engine Mod Switcher

Directly encodes the entities, enums, and validation constraints specified in
specs/003-realtime-graphics-toggle/data-model.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# Pad button bitmasks matching bbport src/runtime_pad.c
BTN_L3 = 0x2
BTN_R3 = 0x4


class VisualMode(str, Enum):
    """Active aesthetic presentation profile."""
    VANILLA_HD = "VANILLA_HD"
    RETRO_5PILLAR = "RETRO_5PILLAR"


class TransitionPhase(str, Enum):
    """Lifecycle phases for mode transition."""
    IDLE = "IDLE"
    FADING_OUT = "FADING_OUT"
    SWAPPING_OVERLAY = "SWAPPING_OVERLAY"
    TRIGGERING_RELOAD = "TRIGGERING_RELOAD"
    AWAITING_SCENE_LOAD = "AWAITING_SCENE_LOAD"
    FADING_IN = "FADING_IN"


@dataclass
class ToggleInputState:
    """Tracks real-time controller sampling and chord debouncing."""
    buttons_current: int = 0
    l3_pressed: bool = False
    r3_pressed: bool = False
    chord_active: bool = False
    last_trigger_timestamp: Optional[int] = None  # monotonic ms
    debounce_duration_ms: int = 3000
    is_locked: bool = False

    def update(self, buttons: int, current_timestamp_ms: int) -> bool:
        """
        Updates button states and checks for chord activation.
        Returns True if a new valid (unlocked) chord transition triggered.
        """
        self.buttons_current = buttons
        self.l3_pressed = bool(buttons & BTN_L3)
        self.r3_pressed = bool(buttons & BTN_R3)
        chord_now = self.l3_pressed and self.r3_pressed

        if self.last_trigger_timestamp is None:
            self.is_locked = False
        else:
            time_since_last = current_timestamp_ms - self.last_trigger_timestamp
            self.is_locked = time_since_last < self.debounce_duration_ms

        if chord_now and not self.chord_active and not self.is_locked:
            self.chord_active = True
            self.last_trigger_timestamp = current_timestamp_ms
            self.is_locked = True
            return True
        elif not chord_now:
            self.chord_active = False

        return False


@dataclass
class ModSwitcherConfig:
    """Persistent configuration and active profile state."""
    schema_version: str = "1.0.0"
    active_mode: VisualMode = VisualMode.RETRO_5PILLAR
    hotkey_binding: str = "L3+R3"
    fade_duration_ms: int = 200
    debounce_duration_ms: int = 3000
    last_updated_iso: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["active_mode"] = self.active_mode.value if isinstance(self.active_mode, VisualMode) else self.active_mode
        return d


@dataclass
class OverlayMountState:
    """Represents the filesystem virtual overlay managed by bbport."""
    overlay_root: Path
    active_mode: VisualMode
    vanilla_source: Path
    retro_source: Path
    swap_in_progress: bool = False
