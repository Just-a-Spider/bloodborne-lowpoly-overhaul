# Quickstart & Verification Guide: Native In-Game Lantern Mod Switcher

**Feature Branch**: `004-native-lantern-switcher`  
**Date**: 2026-11-10 (Revised)  
**Status**: Ready  

---

## 1. Overview & Prerequisites

This guide defines automated and interactive verification for the MOAL-style native lantern mod switcher.

### Prerequisites
- Pristine base game: `CUSA03173/` (strictly read-only).
- 5-Pillar Modular Mod: `mods/` verified via `uv run python tools/verify_modular_mods.py`.
- Soulstruct Bloodborne library available in `uv`.
- Always execute commands using `uv run python ...`.

---

## 2. Automated Test Suite

Run the full automated verification suite:
```bash
uv run python tools/verify_lantern_mod.py --all
```

### Test Breakdown
- **Test 1: FMG Text Injection (`menu.msgbnd.dcx`)**:
  - Validates that Entry 30 contains Text IDs `70011010` ("Switch to Retro 32-Bit Demake") and `70011011` ("Restore Modern High-Definition") across local `mods/` and `bbport-src/mods/`.
- **Test 2: Talk ESD State Machine Topology & Unlit Lamp Safety**:
  - Validates that SM `2147483644` State 7 retains call to SM `2147483639` (preserves unlit lamp ignition).
  - Validates that State 6 calls SM `2147483500`.
  - Validates that SM `2147483500` State 0 condition 0 does NOT evaluate `IsTalkExclusiveMenuOpen() == 0` (eliminates frame 0 abort).
  - Validates choice IDs `1`, `20`, `21`, `99` and their target states.
- **Test 3: MOAL Compatibility Verification**:
  - If MOAL is present, verifies that MOAL's State 7 is untouched and choices 20/21 are integrated cleanly into MOAL's SM `2147483500`.
- **Test 4: State Persistence & Config Sync**:
  - Verifies mode tracking in `out/retro_toggle_state.json`, `bbport.ini` (`retro_mode`), and `mods.json`.

---

## 3. Interactive In-Game Playtest

1. **Verify Base State & Launch Game**:
   ```bash
   cd /home/andre/Games/bbport-src && bash run.sh
   ```
2. **Test 1: Unlit Lamp Ignition**:
   - Approach any unignited lamp (e.g. 1st Floor Sickroom or Central Yharnam).
   - Verify prompt displays "Light Lamp" (`70011000`).
   - Press **Cross**: verify Hunter plays ignition animation and lamp ignites.
3. **Test 2: Lit Lamp Custom Menu**:
   - Approach the lit lamp.
   - Press **Cross**: verify menu displays:
     - `Return to the Hunter's Dream`
     - `Switch to Retro 32-Bit Demake` (or `Restore Modern High-Definition`)
     - `Leave`
   - Press **Circle**: verify menu closes gracefully without reload.
4. **Test 3: Mode Switch Execution**:
   - Select `Switch to Retro 32-Bit Demake`.
   - Verify Hunter plays native kneeling/warp sequence.
   - Verify screen fades to black and reloads at the lamp.
   - Verify graphics presentation reflects retro mode.
   - Verify echoes, inventory, and insight are preserved.
