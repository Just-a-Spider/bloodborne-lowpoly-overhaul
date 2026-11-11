#!/usr/bin/env python3
"""
pad_chord_detector.py - Gamepad Chord Detection & Input Debouncer

Detects simultaneous L3 + R3 stick clicks and enforces a 3000ms debounce lockout window.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from tools.pipeline.mod_switcher_types import BTN_L3, BTN_R3, ToggleInputState


class PadChordDetector:
    """Monitors gamepad button streams and emits toggle events on debounced L3+R3 chords."""

    def __init__(self, debounce_duration_ms: int = 3000):
        self.state = ToggleInputState(debounce_duration_ms=debounce_duration_ms)
        self.on_toggle_callbacks: List[Callable[[], None]] = []

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Registers a callback function invoked on valid chord trigger."""
        self.on_toggle_callbacks.append(callback)

    def process_buttons(self, buttons: int, timestamp_ms: Optional[int] = None) -> bool:
        """
        Processes a raw button bitfield.
        Returns True if a new debounced L3+R3 toggle event was triggered.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.monotonic() * 1000.0)

        triggered = self.state.update(buttons, timestamp_ms)
        if triggered:
            for cb in self.on_toggle_callbacks:
                try:
                    cb()
                except Exception:
                    pass
        return triggered

    def is_locked(self, current_timestamp_ms: Optional[int] = None) -> bool:
        """Returns True if the detector is currently within the debounce cooldown window."""
        if self.state.last_trigger_timestamp is None:
            return False
        if current_timestamp_ms is None:
            current_timestamp_ms = int(time.monotonic() * 1000.0)
        return (current_timestamp_ms - self.state.last_trigger_timestamp) < self.state.debounce_duration_ms
