#!/usr/bin/env python3
"""
scene_reload_coordinator.py - Lifecycle Coordinator for Mode Reload & Fade Transition

Coordinates the 6-stage lifecycle:
IDLE -> FADING_OUT (200ms) -> SWAPPING_OVERLAY -> TRIGGERING_RELOAD -> AWAITING_SCENE_LOAD -> FADING_IN (200ms) -> IDLE
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from tools.pipeline.mod_overlay_manager import ModOverlayManager
from tools.pipeline.mod_switcher_types import TransitionPhase, VisualMode


class SceneReloadCoordinator:
    """Coordinates visual transition, VFS swap, and in-engine scene reload."""

    def __init__(
        self,
        overlay_manager: ModOverlayManager,
        fade_duration_ms: int = 200,
        reload_duration_ms: int = 1500,
    ):
        self.overlay_manager = overlay_manager
        self.fade_duration_ms = fade_duration_ms
        self.reload_duration_ms = reload_duration_ms
        self.phase: TransitionPhase = TransitionPhase.IDLE
        self.phase_start_ms: int = 0
        self.target_mode: Optional[VisualMode] = None

    def request_switch(self, target_mode: Optional[VisualMode] = None) -> bool:
        """Initiates the transition lifecycle to target_mode (or toggles if None)."""
        if self.phase != TransitionPhase.IDLE:
            return False  # Already in transition

        current_mode = self.overlay_manager.get_active_mode()
        if target_mode is None:
            self.target_mode = (
                VisualMode.VANILLA_HD
                if current_mode == VisualMode.RETRO_5PILLAR
                else VisualMode.RETRO_5PILLAR
            )
        else:
            self.target_mode = target_mode

        self.phase = TransitionPhase.FADING_OUT
        self.phase_start_ms = int(time.monotonic() * 1000.0)
        return True

    def step(self, current_ms: Optional[int] = None) -> TransitionPhase:
        """
        Advances the transition state machine based on elapsed time.
        Returns the current phase.
        """
        if current_ms is None:
            current_ms = int(time.monotonic() * 1000.0)

        elapsed = current_ms - self.phase_start_ms

        if self.phase == TransitionPhase.FADING_OUT:
            if elapsed >= self.fade_duration_ms:
                self.phase = TransitionPhase.SWAPPING_OVERLAY
                self.phase_start_ms = current_ms

        if self.phase == TransitionPhase.SWAPPING_OVERLAY:
            if self.target_mode is not None:
                self.overlay_manager.atomic_swap_profile(self.target_mode)
            self.phase = TransitionPhase.TRIGGERING_RELOAD
            self.phase_start_ms = current_ms

        if self.phase == TransitionPhase.TRIGGERING_RELOAD:
            # Checkpoint warp / reload dispatched to engine
            self.phase = TransitionPhase.AWAITING_SCENE_LOAD
            self.phase_start_ms = current_ms

        if self.phase == TransitionPhase.AWAITING_SCENE_LOAD:
            if elapsed >= self.reload_duration_ms:
                self.phase = TransitionPhase.FADING_IN
                self.phase_start_ms = current_ms

        if self.phase == TransitionPhase.FADING_IN:
            if elapsed >= self.fade_duration_ms:
                self.phase = TransitionPhase.IDLE
                self.target_mode = None

        return self.phase
