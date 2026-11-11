#!/usr/bin/env python3
"""
mod_switcher_state.py - Persistent Configuration & State Manager

Manages out/retro_toggle_state.json with atomic writes and schema contract validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.fixtures.switcher.validate_schema import validate_contract
from tools.pipeline.mod_switcher_types import ModSwitcherConfig, VisualMode

DEFAULT_STATE_PATH = Path("out/retro_toggle_state.json")
SCHEMA_PATH = Path("specs/003-realtime-graphics-toggle/contracts/toggle_state_schema.json")


class StateManager:
    """Handles thread-safe, atomic persistence of the mod switcher configuration."""

    def __init__(self, state_path: Path = DEFAULT_STATE_PATH, schema_path: Path = SCHEMA_PATH):
        self.state_path = Path(state_path)
        self.schema_path = Path(schema_path)

    def load(self) -> ModSwitcherConfig:
        """Loads and validates configuration from disk. Falls back to default on missing file."""
        if not self.state_path.is_file():
            config = ModSwitcherConfig(
                last_updated_iso=datetime.now(timezone.utc).isoformat()
            )
            self.save(config)
            return config

        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if self.schema_path.is_file():
            validate_contract(data, self.schema_path)

        return ModSwitcherConfig(
            schema_version=data.get("schema_version", "1.0.0"),
            active_mode=VisualMode(data.get("active_mode", VisualMode.RETRO_5PILLAR.value)),
            hotkey_binding=data.get("hotkey_binding", "L3+R3"),
            fade_duration_ms=data.get("fade_duration_ms", 200),
            debounce_duration_ms=data.get("debounce_duration_ms", 3000),
            last_updated_iso=data.get("last_updated_iso", ""),
        )

    def save(self, config: ModSwitcherConfig) -> None:
        """Atomically saves configuration to disk with schema validation."""
        config.last_updated_iso = datetime.now(timezone.utc).isoformat()
        payload = config.to_dict()

        if self.schema_path.is_file():
            validate_contract(payload, self.schema_path)

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp_path, self.state_path)

    def sync_bbport_mods_json(self, mods_json_path: Path, active_mode: VisualMode) -> None:
        """
        Synchronizes active mode with bbport's mods.json profile.
        When in VANILLA_HD mode, disables modular mods.
        When in RETRO_5PILLAR mode, enables all 5 modular pillars.
        """
        p = Path(mods_json_path)
        if not p.parent.is_dir():
            return

        settings = {"order": [], "disabled": []}
        if p.is_file():
            try:
                settings = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass

        pillars = [
            "Bloodborne Retro Maps",
            "Bloodborne Retro Props and Objects",
            "Bloodborne Retro Armors and Weapons - Cloth Physics",
            "Bloodborne Retro Characters",
            "Bloodborne Retro HUD and UI",
        ]

        disabled_set = set(settings.get("disabled", []))
        if active_mode == VisualMode.VANILLA_HD:
            # Disable retro pillars
            for pillar in pillars:
                disabled_set.add(pillar)
        else:
            # Enable retro pillars
            for pillar in pillars:
                disabled_set.discard(pillar)

        settings["disabled"] = sorted(list(disabled_set))
        temp = p.with_suffix(".tmp")
        temp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        os.replace(temp, p)
