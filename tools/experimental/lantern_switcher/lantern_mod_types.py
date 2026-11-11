#!/usr/bin/env python3
"""
lantern_mod_types.py - Domain Models & Constants for Native Lantern Mod Switcher

Directly encodes the entities, event flag identifiers, and text constants specified in
specs/004-native-lantern-switcher/data-model.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pipeline.mod_switcher_types import TransitionPhase, VisualMode

# Reserved FromSoftware event flags for guest-to-host mod signaling
FLAG_REQUEST_RETRO_5PILLAR = 999901
FLAG_REQUEST_VANILLA_HD = 999902

# FMG Entry 30 text IDs for lantern interaction dialogue
FMG_CATEGORY_EVENT_TEXT = 30
TEXT_ID_LIGHT_LAMP = 70011000
TEXT_ID_RETURN_DREAM = 70011001
TEXT_ID_RETRO_PROMPT = 70011010
TEXT_LABEL_RETRO_PROMPT = "Switch to Retro 32-Bit Demake"
TEXT_ID_MODERN_PROMPT = 70011011
TEXT_LABEL_MODERN_PROMPT = "Restore Modern High-Definition"
TEXT_ID_LEAVE = 15000005

# FromSoftware State Machine & State IDs
SM_TOP_LEVEL_LAMP = 2147483646
SM_LAMP_INTERACT = 2147483644
SM_IGNITE_LAMP = 2147483639
SM_WARP_CONFIRM = 2147483643
SM_WARP_EXEC = 2147483641
SM_CUSTOM_MENU = 2147483500

# Choice IDs in SM 2147483500 State 0
CHOICE_WARP_DREAM = 1
CHOICE_SWITCH_RETRO = 20
CHOICE_RESTORE_MODERN = 21
CHOICE_LEAVE = 99

# States in SM 2147483500
STATE_MENU_ROOT = 0
STATE_WARP_DREAM = 1
STATE_SWITCH_RETRO = 20
STATE_RESTORE_MODERN = 21
STATE_TERMINAL = 19


@dataclass
class LanternDialogueOption:
    """Defines an interactive menu selection presented in the lantern interaction dialog."""
    option_id: int
    fmg_entry_id: int
    label: str
    target_mode: VisualMode
    target_event_flag: int


@dataclass
class EventFlagSignal:
    """In-engine communication flag exchanged between event engine and host coordinator."""
    flag_id: int
    state: bool = False
    timestamp_ms: int = 0


@dataclass
class LanternReloadSession:
    """Tracks the lifecycle of an active lantern-triggered scene reconstruction."""
    phase: TransitionPhase = TransitionPhase.IDLE
    active_lantern_id: int = 200000
    target_mode: VisualMode = VisualMode.RETRO_5PILLAR
    session_start_ms: int = 0
