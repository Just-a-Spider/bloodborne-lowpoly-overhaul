#!/usr/bin/env python3
"""
inject_lantern_menu_text.py - Injects Lantern Toggle Prompts into menu.msgbnd.dcx

Modifies Entry 30 (イベントテキスト.fmg) to add:
- ID 70011010: "Switch to Retro 32-Bit Demake"
- ID 70011011: "Restore Modern High-Definition"
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from soulstruct.bloodborne.text import FMG
from soulstruct.containers import Binder
from tools.pipeline.lantern_mod_types import (
    TEXT_ID_MODERN_PROMPT,
    TEXT_ID_RETRO_PROMPT,
    TEXT_LABEL_MODERN_PROMPT,
    TEXT_LABEL_RETRO_PROMPT,
)


def inject_lantern_prompts(
    src_msgbnd: Path,
    out_msgbnd: Path,
    retro_label: str = TEXT_LABEL_RETRO_PROMPT,
    modern_label: str = TEXT_LABEL_MODERN_PROMPT,
) -> bool:
    """Injects lantern toggle dialogue prompts into menu.msgbnd.dcx without touching baseline."""
    src = Path(src_msgbnd).resolve()
    out = Path(out_msgbnd).resolve()

    if not src.is_file():
        raise FileNotFoundError(f"Source menu.msgbnd.dcx not found at {src}")

    binder = Binder.from_path(src)
    entry_30 = None
    for entry in binder.entries:
        if entry.entry_id == 30 or "イベントテキスト" in entry.path:
            entry_30 = entry
            break

    if entry_30 is None:
        raise ValueError("Entry 30 (イベントテキスト.fmg) not found in menu.msgbnd.dcx")

    fmg = FMG.from_bytes(entry_30.data)
    fmg.entries[TEXT_ID_RETRO_PROMPT] = retro_label
    fmg.entries[TEXT_ID_MODERN_PROMPT] = modern_label

    entry_30.data = bytes(fmg)

    out.parent.mkdir(parents=True, exist_ok=True)
    binder.write(out)
    return True


def main():
    parser = argparse.ArgumentParser(description="Inject lantern toggle prompts into menu.msgbnd.dcx")
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("CUSA03173/dvdroot_ps4/msg/engus/menu.msgbnd.dcx"),
        help="Pristine vanilla menu.msgbnd.dcx",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("mods/Bloodborne Retro HUD and UI/dvdroot_ps4/msg/engus/menu.msgbnd.dcx"),
        help="Destination path for modded menu.msgbnd.dcx",
    )
    args = parser.parse_args()

    inject_lantern_prompts(args.src, args.out)
    print(f"PASS: Injected lantern prompts into {args.out}")


if __name__ == "__main__":
    main()
