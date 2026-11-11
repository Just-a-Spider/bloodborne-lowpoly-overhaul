# Quickstart Validation Guide: Retro HUD & Interaction Elements

## Overview

This guide details how to execute, validate, and verify the retro HUD and interaction elements demake pipeline.

---

## 1. Prerequisites

- Python 3.12+ managed via `uv`
- Legal copy of Bloodborne v1.09 in `CUSA03173/` (strictly read-only)
- Virtual environment installed (`uv sync`)

---

## 2. Execution

### Step 1: Run HUD Demake Pipeline

Execute the master HUD demake batch runner to process all vitals, icons, prompt boxes, and announcement banners:

```bash
uv run python tools/pipeline/batch_demake_hud.py --vanilla CUSA03173 --sandbox CUSA03173-PSX --factor 2
```

**Expected Result**:
- 38 texture atlases demaked (`MENU_Common_*`, `MENU_Icon_*`) with 15-bit RGB555 quantization.
- 27 button prompt and language textures preserved pristine (`KG_*`, `MENU_LNG_*`).
- Repacked container written to `CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx`.
- Pre-modification backup created at `CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx.bak`.
- Total execution time under 5.0 seconds.

---

## 3. Automated Verification

### Step 2: Execute Automated Verification Test Suite

Run the 4-tier acceptance test suite across the repacked container:

```bash
uv run python tools/verify_hud_demake.py --target CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx
```

**Expected Output**:
```text
================================================================================
HUD DEMAKE ACCEPTANCE SUITE: common.tpf.dcx
================================================================================
Tier 1: Container & Header Invariants
  [PASS] T1.1 TPF Magic & Header Integrity
  [PASS] T1.2 Texture Count Parity (65/65)
  [PASS] T1.3 Payload Offset Monotonicity & Boundary Check
  [PASS] T1.4 DCX Compression Valid (DCX_DFPR)

Tier 2: Scaleform Canvas & UV Compatibility
  [PASS] T2.1 Canvas Dimensions Match Vanilla Bit-for-Bit
  [PASS] T2.2 Single Mip Level Invariant (num_mips == 1)
  [PASS] T2.3 Block Compression Formats Valid (BC7 / BC1)
  [PASS] T2.4 Zero-Padding Alignment Invariant

Tier 3: Retro Styling & Prompt Whitelist Audit
  [PASS] T3.1 15-Bit RGB555 Color Quantization (Step 8 on Common Atlases)
  [PASS] T3.2 Nearest-Neighbor Texel Stepping (No Bilinear Smear)
  [PASS] T3.3 Controller Prompts (KG_*) 100% Pristine Byte Match
  [PASS] T3.4 Alpha Channel Transparency Maintained

Tier 4: Immutability & Safety
  [PASS] T4.1 Pristine CUSA03173/ Remains Bit-for-Bit Untouched
  [PASS] T4.2 Fallback Backup common.tpf.dcx.bak Present & Valid
  [PASS] T4.3 Mod Packaging Path Updated
--------------------------------------------------------------------------------
SUMMARY: 15 Tests | 15 Passed | 0 Failed | 0 Skipped | Exit Code 0
================================================================================
```

---

## 4. Visual In-Game Acceptance Scenarios

Launch the game in sandbox via `shadPS4` / `bbhost`:

1. **Player Vitals (Combat HUD)**:
   - Verify health bar (red) and stamina bar (green) have crisp pixelated stepped borders and quantized fill colors.
   - Verify Quicksilver Bullet and Blood Vial count digits render with clear pixel typography.
2. **Environmental Interaction**:
   - Approach the workshop door or the Plain Doll in Hunter's Dream.
   - Verify the interaction prompt box appears with chunky retro framing, while the controller button icon (e.g. Cross `X`) remains sharp and legible.
3. **Boss Health Bar & Milestone Banners**:
   - Engage Cleric Beast or Father Gascoigne.
   - Verify the wide boss health gauge displays with retro framed border.
   - Trigger death or defeat state: verify "YOU DIED" or "PREY SLAUGHTERED" banner renders with dithered retro backdrop.

---

## 5. Rollback Procedure

If any unexpected visual or layout defect occurs, restore the pristine container immediately:

```bash
cp CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx.bak CUSA03173-PSX/dvdroot_ps4/menu/common.tpf.dcx
```
