#!/usr/bin/env python3
"""
validate_contracts.py - JSON Schema Contract Validation for Native Lantern Switcher

Validates menu option definitions and event flag registry against contracts/.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, Union

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MENU_CONTRACT_SCHEMA = REPO_ROOT / "specs/004-native-lantern-switcher/contracts/lantern_menu_contract.json"
FLAG_REGISTRY_SCHEMA = REPO_ROOT / "specs/004-native-lantern-switcher/contracts/event_flag_registry.json"


def load_json(path_or_dict: Union[str, Path, dict]) -> dict:
    if isinstance(path_or_dict, dict):
        return path_or_dict
    p = Path(path_or_dict)
    return json.loads(p.read_text(encoding="utf-8"))


def validate_lantern_menu_config(config: Union[str, Path, dict]) -> bool:
    """Validates lantern menu definitions against lantern_menu_contract.json."""
    c = load_json(config)
    s = load_json(MENU_CONTRACT_SCHEMA)
    jsonschema.validate(instance=c, schema=s)
    return True


def validate_event_flag_registry(registry: Union[str, Path, dict]) -> bool:
    """Validates event flag definitions against event_flag_registry.json."""
    r = load_json(registry)
    s = load_json(FLAG_REGISTRY_SCHEMA)
    jsonschema.validate(instance=r, schema=s)
    return True


if __name__ == "__main__":
    sample_menu = {
        "fmg_category": 30,
        "options": [
            {
                "text_id": 70011010,
                "label": "Switch to Retro 32-Bit Demake",
                "target_mode": "RETRO_5PILLAR",
                "event_flag": 999901
            },
            {
                "text_id": 70011011,
                "label": "Restore Modern High-Definition",
                "target_mode": "VANILLA_HD",
                "event_flag": 999902
            }
        ]
    }
    sample_flags = {
        "flags": {
            "999901": "REQUEST_RETRO_5PILLAR",
            "999902": "REQUEST_VANILLA_HD"
        }
    }
    assert validate_lantern_menu_config(sample_menu) is True
    assert validate_event_flag_registry(sample_flags) is True
    print("PASS: Lantern contracts validated.")
