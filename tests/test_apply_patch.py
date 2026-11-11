"""
Unit tests for apply_patch.py - Target directory inference and batch reconstruction.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from apply_patch import infer_mod_dir_name


def test_infer_mod_dir_name_from_metadata():
    patch_path = Path("custom_name.patch")
    meta = {"mod_name": "Bloodborne Custom Mod"}
    assert infer_mod_dir_name(patch_path, meta) == "Bloodborne Custom Mod"


def test_infer_mod_dir_name_from_standard_filenames():
    cases = {
        "bloodborne_retro_hud.patch": "Bloodborne Retro HUD and UI",
        "bloodborne_retro_maps.patch": "Bloodborne Retro Maps",
        "bloodborne_retro_props.patch": "Bloodborne Retro Props and Objects",
        "bloodborne_retro_armors_cloth.patch": "Bloodborne Retro Armors and Weapons - Cloth Physics",
        "bloodborne_retro_armors_stiff.patch": "Bloodborne Retro Armors and Weapons - Flat Stiff",
        "bloodborne_retro_characters.patch": "Bloodborne Retro Characters",
        "bloodborne_lowpoly_overhaul_cloth.patch": "Bloodborne Low-Poly Overhaul (Cloth Physics)",
        "bloodborne_lowpoly_overhaul_stiff.patch": "Bloodborne Low-Poly Overhaul (Flat Stiff)",
        "bloodborne_lowpoly_overhaul.patch": "Bloodborne Low-Poly Overhaul",
    }
    for filename, expected in cases.items():
        assert infer_mod_dir_name(Path(filename), None) == expected


def test_infer_mod_dir_name_fuzzy():
    assert infer_mod_dir_name(Path("v1.2_hud_elements.patch")) == "Bloodborne Retro HUD and UI"
    assert infer_mod_dir_name(Path("demake_props_v2.patch")) == "Bloodborne Retro Props and Objects"
    assert infer_mod_dir_name(Path("unknown_patch.patch")) == "Bloodborne Low-Poly Overhaul"


def test_cli_requires_out_argument(monkeypatch):
    """Verify that --out is required and parser fails without it."""
    import subprocess
    cmd = [sys.executable, "apply_patch.py", "--game", "dummy_game"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert result.returncode != 0
    assert "the following arguments are required: --out/-o" in result.stderr

