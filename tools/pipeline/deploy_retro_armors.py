#!/usr/bin/env python3
"""
Bloodborne PSX Demake: Retro Armor Deployment & Packaging Pipeline.

Automates building, packaging, and registering modular retro armor mods:
1. Flat Stiff Edition (All 796 armors, decoupled Havok cloth, hard split facet normals, RGB555 albedos)
2. Havok Cloth Physics Edition (Preserves dynamic capes/skirts on 156 cloth armors, hard split normals on rigid plates)

Usage:
    uv run python tools/pipeline/deploy_retro_armors.py --mode both --active cloth
    uv run python tools/pipeline/deploy_retro_armors.py --mode cloth --workers 12
    uv run python tools/pipeline/deploy_retro_armors.py --mode stiff --active stiff
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from soulstruct.containers import Binder
from soulstruct.flver.core import FLVER
from bone_transform_utils import update_flver_bounding_boxes

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = Path(__file__).resolve().parent

DEFAULT_VANILLA_PARTS = REPO_ROOT / "CUSA03173" / "dvdroot_ps4" / "parts"
DEFAULT_SANDBOX_PARTS = REPO_ROOT / "CUSA03173-PSX" / "dvdroot_ps4" / "parts"
DEFAULT_MODS_DIR = REPO_ROOT / "mods"
DEFAULT_MODS_JSON = REPO_ROOT / "mods.json"

STIFF_MOD_NAME = "Bloodborne Retro Armors and Weapons - Flat Stiff"
CLOTH_MOD_NAME = "Bloodborne Retro Armors and Weapons - Cloth Physics"
BASE_MOD_NAME = "Bloodborne Low-Poly Overhaul"
BACKUP_MOD_NAME = "Bloodborne Low-Poly Overhaul (Stable Backup)"

MARIA_PARTS_FILES = [
    "hd_f_9300.partsbnd.dcx", "hd_f_9300_l.partsbnd.dcx",
    "hd_m_9300.partsbnd.dcx", "hd_m_9300_l.partsbnd.dcx",
    "bd_f_9300.partsbnd.dcx", "bd_f_9300_l.partsbnd.dcx",
    "bd_m_9300.partsbnd.dcx", "bd_m_9300_l.partsbnd.dcx",
]


def fix_maria_cloth_and_hat(cloth_parts_dir: Path, stiff_parts_dir: Path, sandbox_parts_dir: Path):
    """
    Repairs Lady Maria (set 9300) hat and garb:
    1. For Cloth Physics Edition and CUSA03173-PSX:
       Preserves Havok dynamic solver data (_c.hkx, _c.clm2, _Cloth.mtd) and parents
       dummy simulation bones to character roots (Head for hat, Spine2 for mantle).
    2. For Flat Stiff Edition:
       Decoupled cloth submeshes are assigned explicit default_bone_indices (Head for hat feathers,
       Spine2/Neck for mantle and scarves) and unparented dummy bones are anchored to character roots.
    """
    print("\n=== Synchronizing Lady Maria (Set 9300) Hat & Garb ===")

    # 1. Cloth Physics mode + Sandbox deployment
    for fname in MARIA_PARTS_FILES:
        src = cloth_parts_dir / fname
        if not src.is_file():
            # If not in cloth mod dir, try vanilla as fallback
            v_src = DEFAULT_VANILLA_PARTS / fname
            if v_src.is_file():
                src = v_src

        if not src.is_file():
            print(f"  [WARN] Source file {fname} not found, skipping cloth fix.")
            continue

        b = Binder.from_path(src)
        flv_e = next((e for e in b.entries if e.name.endswith(".flver")), None)
        if flv_e:
            flv = FLVER.from_bytes(flv_e.get_uncompressed_data())
            if fname.startswith("hd_"):
                head_idx = next((i for i, bn in enumerate(flv.bones) if bn.name == "Head"), 0)
                for bn in flv.bones:
                    if "feather" in bn.name.lower() or "9300" in bn.name:
                        if bn.parent_bone_index == -1:
                            bn.parent_bone_index = head_idx
            else:
                spine2_idx = next((i for i, bn in enumerate(flv.bones) if bn.name == "Spine2"), 2)
                for bn in flv.bones:
                    if "mantle" in bn.name.lower() or "scarf" in bn.name.lower() or "9300" in bn.name or "dummy" in bn.name.lower():
                        if bn.parent_bone_index == -1:
                            bn.parent_bone_index = spine2_idx

            update_flver_bounding_boxes(flv)
            flv_e.set_uncompressed_data(flv.to_bytes())

        data = b.to_bytes()
        # Save to Cloth Physics mod
        dest_cloth = cloth_parts_dir / fname
        dest_cloth.parent.mkdir(parents=True, exist_ok=True)
        dest_cloth.write_bytes(data)

        # Save to Sandbox (CUSA03173-PSX)
        dest_sandbox = sandbox_parts_dir / fname
        dest_sandbox.parent.mkdir(parents=True, exist_ok=True)
        dest_sandbox.write_bytes(data)
        print(f"  [CLOTH] {fname}: Dynamic Havok cloth and parented bones deployed ({len(data)} bytes)")

    # 2. Flat Stiff mode
    for fname in MARIA_PARTS_FILES:
        src = stiff_parts_dir / fname
        if not src.is_file():
            continue

        b = Binder.from_path(src)
        flv_e = next((e for e in b.entries if e.name.endswith(".flver")), None)
        if flv_e:
            flv = FLVER.from_bytes(flv_e.get_uncompressed_data())
            if fname.startswith("hd_"):
                head_idx = next((i for i, bn in enumerate(flv.bones) if bn.name == "Head"), 0)
                for bn in flv.bones:
                    if "feather" in bn.name.lower() or "9300" in bn.name:
                        if bn.parent_bone_index == -1:
                            bn.parent_bone_index = head_idx
                if len(flv.meshes) > 1:
                    flv.meshes[1].default_bone_index = head_idx
                if len(flv.meshes) > 2:
                    flv.meshes[2].default_bone_index = head_idx
            else:
                spine2_idx = next((i for i, bn in enumerate(flv.bones) if bn.name == "Spine2"), 2)
                neck_idx = next((i for i, bn in enumerate(flv.bones) if bn.name == "Neck"), 21)
                for bn in flv.bones:
                    if "mantle" in bn.name.lower() or "scarf" in bn.name.lower() or "9300" in bn.name or "dummy" in bn.name.lower():
                        if bn.parent_bone_index == -1:
                            bn.parent_bone_index = spine2_idx
                for mi in [2, 3, 4, 5]:
                    if mi < len(flv.meshes):
                        flv.meshes[mi].default_bone_index = spine2_idx
                for mi in [6, 7, 8]:
                    if mi < len(flv.meshes):
                        flv.meshes[mi].default_bone_index = neck_idx

            update_flver_bounding_boxes(flv)
            flv_e.set_uncompressed_data(flv.to_bytes())

        data = b.to_bytes()
        dest_stiff = stiff_parts_dir / fname
        dest_stiff.parent.mkdir(parents=True, exist_ok=True)
        dest_stiff.write_bytes(data)
        print(f"  [STIFF] {fname}: Rigid anchored bones and default indices deployed ({len(data)} bytes)")


def write_mod_metadata(mod_dir: Path, is_cloth: bool, file_count: int = 796):
    """Writes standard mod.json and README.txt into the mod folder."""
    name = CLOTH_MOD_NAME if is_cloth else STIFF_MOD_NAME
    display_title = "Bloodborne: Retro Armors (Cloth Physics)" if is_cloth else "Bloodborne: Retro Armors (Flat Stiff)"
    desc = (
        "PSX demake for all 796 player armors with preserved Havok dynamic cloth physics: "
        "capes, skirts, and mantles flutter dynamically while rigid armor plates are decimated "
        "with retro flat facet shading and 128px textures."
        if is_cloth
        else "Authentic PSX demake for all 796 player armors: crisp facet split normals, "
        "128px quantized RGB555 albedo, neutralized flat normal maps, zero specular sheen, "
        "and 100% decoupled stiff retro cloth (zero Havok physics overhead, maximum stability)."
    )

    mod_json = {
        "name": display_title,
        "version": "1.0.0",
        "game_version": "1.09",
        "description": desc,
        "file_count": file_count,
        "folders": {
            "parts": file_count
        }
    }

    (mod_dir / "mod.json").write_text(json.dumps(mod_json, indent=2) + "\n", encoding="utf-8")

    edition_title = "Havok Cloth Physics Edition" if is_cloth else "Flat Stiff Edition"
    readme_content = f"""Bloodborne PSX Demake: Retro Armors ({edition_title})
==================================================================
Features:
- Complete coverage of all 796 player armor archives (helmets, chests, gauntlets, trousers).
- Retro hard-split facet normals (zero smooth shading, authentic PS1 polygon look).
- Decimated mesh topology (~0.08 ratio, ~92% triangle reduction).
- 128x128 quantized 15-bit RGB555 albedo textures.
- Neutralized flat normal maps (eliminating micro-wrinkles and modern bump mapping).
- Zeroed specular reflectance and gloss (killing oily PBR shine for matte retro rendering).
{'- Preserved Havok cloth physics on 156 cloth-bearing armors (capes/skirts flutter without solver crash).' if is_cloth else '- Decoupled Havok cloth: All capes/skirts converted to skeletal skinning (zero Havok overhead).'}

How to Use:
Enable this mod in mods.json or via your mod manager.
When loaded alongside 'Bloodborne Low-Poly Overhaul', it layers on top and updates all player armors.
"""
    (mod_dir / "README.txt").write_text(readme_content, encoding="utf-8")


def update_mods_config(config_path: Path, active_choice: str):
    """Updates mods.json to activate the chosen armor version."""
    if not config_path.is_file():
        print(f"Notice: Config {config_path} not found. Skipping config update.")
        return

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Warning: Could not parse {config_path}: {e}")
        return

    order = data.get("order", [])
    disabled = data.get("disabled", [])

    # Ensure required mod names are in order
    for mod in [BASE_MOD_NAME, STIFF_MOD_NAME, CLOTH_MOD_NAME]:
        if mod not in order:
            order.append(mod)

    # Position armor mods after base mod
    order = [m for m in order if m not in (STIFF_MOD_NAME, CLOTH_MOD_NAME)]
    if BASE_MOD_NAME in order:
        base_idx = order.index(BASE_MOD_NAME)
        order.insert(base_idx + 1, STIFF_MOD_NAME)
        order.insert(base_idx + 2, CLOTH_MOD_NAME)
    else:
        order.extend([STIFF_MOD_NAME, CLOTH_MOD_NAME])

    disabled_set = set(disabled)
    if active_choice == "cloth":
        disabled_set.discard(CLOTH_MOD_NAME)
        disabled_set.add(STIFF_MOD_NAME)
    elif active_choice == "stiff":
        disabled_set.discard(STIFF_MOD_NAME)
        disabled_set.add(CLOTH_MOD_NAME)
    elif active_choice == "none":
        disabled_set.add(CLOTH_MOD_NAME)
        disabled_set.add(STIFF_MOD_NAME)

    data["order"] = order
    data["disabled"] = sorted(list(disabled_set))

    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"[CONFIG] Updated {config_path}: active armor mod is '{active_choice}'.")


def main():
    parser = argparse.ArgumentParser(description="Retro Armor Packaging & Deployment Pipeline")
    parser.add_argument("--mode", choices=["cloth", "stiff", "both"], default="both", help="Build mode")
    parser.add_argument("--active", choices=["cloth", "stiff", "none"], default="cloth", help="Active mod in mods.json")
    parser.add_argument("--workers", type=int, default=12, help="Parallel worker threads")
    parser.add_argument("--ratio-armor", type=float, default=0.08, help="Decimation ratio for armors")
    parser.add_argument("--mods-dir", type=Path, default=DEFAULT_MODS_DIR, help="Target mods root directory")
    parser.add_argument("--config", type=Path, default=DEFAULT_MODS_JSON, help="Target mods.json config path")
    parser.add_argument("--vanilla-parts", type=Path, default=DEFAULT_VANILLA_PARTS, help="Path to vanilla parts")
    parser.add_argument("--sandbox-parts", type=Path, default=DEFAULT_SANDBOX_PARTS, help="Path to sandbox parts (CUSA03173-PSX)")
    parser.add_argument("--fix-maria-only", action="store_true", help="Only synchronize Lady Maria (set 9300) cloth & bones")
    args = parser.parse_args()

    mods_dir = args.mods_dir.resolve()
    mods_dir.mkdir(parents=True, exist_ok=True)
    stiff_parts_dir = mods_dir / STIFF_MOD_NAME / "dvdroot_ps4" / "parts"
    cloth_parts_dir = mods_dir / CLOTH_MOD_NAME / "dvdroot_ps4" / "parts"
    sandbox_parts_dir = args.sandbox_parts.resolve()

    if args.fix_maria_only:
        fix_maria_cloth_and_hat(cloth_parts_dir, stiff_parts_dir, sandbox_parts_dir)
        print("\n[OK] Lady Maria fixes applied successfully.")
        return

    batch_script = PIPELINE_DIR / "batch_blender_demake_parts.py"
    if not batch_script.is_file():
        print(f"Error: Could not find {batch_script}", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()

    # Step 1: Build Stiff Edition
    if args.mode in ("stiff", "both"):
        print(f"\n=== Building {STIFF_MOD_NAME} ===")
        stiff_parts_dir.mkdir(parents=True, exist_ok=True)
        cmd_stiff = [
            sys.executable,
            str(batch_script),
            "--armors-only",
            "--out-dir", str(stiff_parts_dir),
            "--workers", str(args.workers),
            "--ratio-armor", str(args.ratio_armor),
        ]
        res = subprocess.run(cmd_stiff)
        if res.returncode != 0:
            print("Error: Stiff armor build failed.", file=sys.stderr)
            sys.exit(res.returncode)

        write_mod_metadata(mods_dir / STIFF_MOD_NAME, is_cloth=False)
        print(f"[OK] Stiff Edition packaged in {mods_dir / STIFF_MOD_NAME}")

    # Step 2: Build Cloth Physics Edition
    if args.mode in ("cloth", "both"):
        print(f"\n=== Building {CLOTH_MOD_NAME} ===")
        cloth_parts_dir.mkdir(parents=True, exist_ok=True)

        # If stiff was built or exists, copy non-cloth armors to avoid redundant Blender processing
        if stiff_parts_dir.is_dir() and len(list(stiff_parts_dir.glob("*.partsbnd.dcx"))) >= 700:
            print("Copying baseline non-cloth armors from Stiff build...")
            for f in stiff_parts_dir.glob("*.partsbnd.dcx"):
                dest = cloth_parts_dir / f.name
                if not dest.exists():
                    shutil.copy2(f, dest)

        cmd_cloth = [
            sys.executable,
            str(batch_script),
            "--cloth-only",
            "--keep-cloth",
            "--out-dir", str(cloth_parts_dir),
            "--workers", str(args.workers),
            "--ratio-armor", str(args.ratio_armor),
        ]
        res = subprocess.run(cmd_cloth)
        if res.returncode != 0:
            print("Error: Cloth physics armor build failed.", file=sys.stderr)
            sys.exit(res.returncode)

        # Clean any Soulstruct backup files
        for bak in cloth_parts_dir.glob("*.bak"):
            bak.unlink()

        write_mod_metadata(mods_dir / CLOTH_MOD_NAME, is_cloth=True)
        print(f"[OK] Cloth Physics Edition packaged in {mods_dir / CLOTH_MOD_NAME}")

    # Synchronize Lady Maria hat and garb
    fix_maria_cloth_and_hat(cloth_parts_dir, stiff_parts_dir, sandbox_parts_dir)

    # Step 3: Update mods.json configuration
    update_mods_config(args.config, args.active)

    dt = time.time() - t0
    print(f"\n=== Retro Armor Pipeline Finished in {dt:.1f}s ===")


if __name__ == "__main__":
    main()
