# Quickstart & Verification Guide: In-Game On-Demand Retro Mod Switcher

**Feature Branch**: `003-realtime-graphics-toggle`  
**Date**: 2026-11-09  
**Status**: Ready  

---

## 1. Overview & Prerequisites

This guide defines the automated and interactive validation workflows for the in-engine on-demand retro mod switcher.

### Prerequisites
- Pristine base game: `CUSA03173/` (strictly read-only).
- 5-Pillar Modular Mod: `mods/` verified via `uv run python tools/verify_modular_mods.py`.
- `bbport` / `bbhost` Linux runner environment.
- Python execution: Always execute with `uv run python ...`.

---

## 2. Automated Test Suite

### Scenario 1: Pad Input Chord Detection & Debounce
Simulates gamepad input sequences (single L3, single R3, simultaneous L3+R3 chord, and rapid spam):
```bash
uv run python tools/verify_mod_switcher.py --test pad-chord
```
- **Expected Outcome**:
  - Single L3 or R3 returns `chord_active = False` (normal lock-on / sprint functions preserved).
  - Simultaneous L3 + R3 triggers `TOGGLE` action.
  - Subsequent L3 + R3 presses within 3000ms return `is_locked = True` (debounced, 0 duplicate reloads).

### Scenario 2: Atomic Overlay Redirection
Tests atomic symlink redirection between Vanilla baseline and the 5 modular pillars without broken links or race conditions:
```bash
uv run python tools/verify_mod_switcher.py --test overlay-swap
```
- **Expected Outcome**:
  - `out/mod-game-*/dvdroot_ps4` updates atomically in < 5ms.
  - In `VANILLA_HD` mode: target files resolve to `CUSA03173/dvdroot_ps4/`.
  - In `RETRO_5PILLAR` mode: target files resolve to `mods/*/dvdroot_ps4/`.
  - Zero partial pillar mounts; all 5 pillars swap simultaneously.

### Scenario 3: State Persistence Across Reloads
Validates that active mode is saved to `out/retro_toggle_state.json` and conforms to [toggle_state_schema.json](contracts/toggle_state_schema.json):
```bash
uv run python tools/verify_mod_switcher.py --test persistence
```
- **Expected Outcome**:
  - State file valid against JSON schema.
  - Subsequent simulated map warp or reboot initializes in the persisted mode.

---

## 3. Interactive In-Game Verification

1. **Launch Game with Switcher Active**:
   ```bash
   bash run.sh
   ```
2. **In Hunter's Dream / Central Yharnam**:
   - Confirm game starts in default `RETRO_5PILLAR` mode (low-poly Doll, chunky texels, retro HUD).
3. **Press L3 + R3 Simultaneously**:
   - Observe smooth 200ms fade-out.
   - Quick checkpoint reload screen executes (~1.5–2s).
   - Game returns with `VANILLA_HD` presentation active (high-poly models, retail HUD).
   - Player position, echoes, and HP remain 100% intact.
4. **Press L3 + R3 Again**:
   - Observe 200ms fade-out.
   - Scene reloads back into `RETRO_5PILLAR` mode.
