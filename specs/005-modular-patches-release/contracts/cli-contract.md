# CLI Contract: Modular Mod Reconstructor & Release Tooling

**Feature**: Modular Mod Release & Patch Distribution Artifacts (`005-modular-patches-release`)
**Date**: 2026-11-11

## 1. `apply_patch.py` (Client Standalone Tool)

### Synopsis
```bash
python3 apply_patch.py --game <PATH> [OPTIONS]
```

### Options
| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--game` | `-g` | `Path` (Required) | None | Path to retail Bloodborne directory containing `dvdroot_ps4/` |
| `--patch` | `-p` | `Path` | Auto-detect | Path to specific `.patch` container file |
| `--out` | `-o` | `Path` | Inferred | Destination directory for reconstructed mod. If omitted, deduced from patch metadata or filename mapping |
| `--mods-dir` | `-m` | `Path` | None | Base directory where reconstructed modular mod folders are placed |
| `--all-patches` | `-a` | Flag | False | Process all detected `.patch` files in current directory or `dist/` |
| `--workers` | `-w` | `int` | CPU count | Worker threads for parallel XOR decoding and verification |
| `--no-verify` | | Flag | False | Skip SHA256 integrity verification (for low-power CPUs) |

### Auto-Inference Rules for `--out`
If `--out` is not specified:
1. If patch manifest contains `"mod_name"`, destination is `<target_dir>/<mod_name>`.
2. Otherwise, infer from patch filename:
   - `*hud*.patch` -> `Bloodborne Retro HUD and UI`
   - `*maps*.patch` -> `Bloodborne Retro Maps`
   - `*props*.patch` -> `Bloodborne Retro Props and Objects`
   - `*armors_cloth*.patch` -> `Bloodborne Retro Armors and Weapons - Cloth Physics`
   - `*armors_stiff*.patch` -> `Bloodborne Retro Armors and Weapons - Flat Stiff`
   - `*characters*.patch` -> `Bloodborne Retro Characters`
   - `*lowpoly_overhaul_cloth*.patch` -> `Bloodborne Low-Poly Overhaul (Cloth Physics)`
   - `*lowpoly_overhaul_stiff*.patch` -> `Bloodborne Low-Poly Overhaul (Flat Stiff)`
   - `*lowpoly_overhaul*.patch` -> `Bloodborne Low-Poly Overhaul`
3. Fallback: `Bloodborne Low-Poly Overhaul`.

---

## 2. `verify_release_artifacts.py` (Release Verification Tool)

### Synopsis
```bash
uv run python tools/pipeline/verify_release_artifacts.py [OPTIONS]
```

### Options
| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--vanilla` | `-v` | `Path` | `CUSA03173` | Pristine base game directory (strictly read-only) |
| `--dist` | `-d` | `Path` | `dist` | Directory containing `.patch` files |
| `--manifest` | `-m` | `Path` | `dist/SHA256SUMS.txt` | Output path for cryptographic checksum manifest |
| `--check-structure` | | Flag | True | Enforce pillar path isolation rules |
| `--workers` | `-w` | `int` | CPU count | Verification worker concurrency |

### Exit Codes
- `0`: All patches valid, 100% hashes verified, zero path leakage, manifest generated.
- `1`: Magic mismatch, corrupted JSON, missing file, hash mismatch, or pillar path cross-contamination.
