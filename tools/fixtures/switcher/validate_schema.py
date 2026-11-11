#!/usr/bin/env python3
"""
validate_schema.py - JSON Schema Contract Validation Utility

Validates configuration and IPC payloads against JSON schema contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

import jsonschema


def load_json(path_or_str: Union[str, Path, dict]) -> dict:
    if isinstance(path_or_str, dict):
        return path_or_str
    p = Path(path_or_str)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(str(path_or_str))


def validate_contract(data: Union[str, Path, dict], schema: Union[str, Path, dict]) -> bool:
    """Validates data dictionary against a JSON schema contract. Raises jsonschema.ValidationError on failure."""
    d = load_json(data)
    s = load_json(schema)
    jsonschema.validate(instance=d, schema=s)
    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data.json> <schema.json>", file=sys.stderr)
        sys.exit(1)
    try:
        validate_contract(sys.argv[1], sys.argv[2])
        print("PASS: Schema contract valid.")
        sys.exit(0)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
