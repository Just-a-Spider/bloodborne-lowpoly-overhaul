# Quickstart & Verification Guide: Modular Mod Release

**Feature**: Modular Mod Release & Patch Distribution Artifacts (`005-modular-patches-release`)
**Date**: 2026-11-11

## Prerequisites

- Python 3.9+ installed
- Repository cloned with `CUSA03173/` (pristine base game) present
- `uv` installed (`uv --version`)

---

## Scenario 1: Validate Release Patches & Generate Checksums

Verifies all patch files in `dist/` against pristine game and modular source trees.

```bash
uv run python tools/pipeline/verify_release_artifacts.py --vanilla CUSA03173 --dist dist --manifest dist/SHA256SUMS.txt
```

**Expected Outcome**:
- Audits 6 modular patches + 3 overhaul bundles.
- Verifies header magic `BBLPO01\x00` and metadata JSON.
- Confirms bit-exact reconstruction against target hashes.
- Enforces strict modular subpath isolation (no cross-contamination).
- Writes `dist/SHA256SUMS.txt`.
- Exit code 0.

---

## Scenario 2: Test End-User Single-Pillar Reconstruction

Tests client-side reconstruction of an individual modular mod (e.g. HUD demake) using pure Python standard library.

```bash
python3 apply_patch.py --game CUSA03173 --patch dist/bloodborne_retro_hud.patch
```

**Expected Outcome**:
- Tool automatically deduces target directory `Bloodborne Retro HUD and UI/`.
- Reconstructs assets into `./Bloodborne Retro HUD and UI/dvdroot_ps4/menu/`.
- 100% SHA256 integrity checks pass.
- Reconstruction completes in < 2 seconds.

---

## Scenario 3: Verify Batch Reconstruction to Mod Manager Directory

Tests unpacking all modular pillars into a target `mods/` directory.

```bash
python3 apply_patch.py --game CUSA03173 --all-patches --mods-dir test_mods/
```

**Expected Outcome**:
- Reconstructs each pillar into its dedicated subfolder under `test_mods/`:
  - `test_mods/Bloodborne Retro Maps/`
  - `test_mods/Bloodborne Retro Props and Objects/`
  - `test_mods/Bloodborne Retro Characters/`
  - `test_mods/Bloodborne Retro HUD and UI/`
  - `test_mods/Bloodborne Retro Armors and Weapons - Cloth Physics/`
- Every file matches target hash.
- Zero cross-contamination between folders.

---

## Scenario 4: Verify Distribution Checksums

Verify published manifest integrity using standard UNIX utility:

```bash
cd dist && sha256sum -c SHA256SUMS.txt
```

**Expected Outcome**:
- All listed patch containers and client script report `OK`.
