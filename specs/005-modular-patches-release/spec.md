# Feature Specification: Modular Mod Release & Patch Distribution Artifacts

**Feature Branch**: `005-modular-patches-release`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "Artifacts and release of the patches and update documentation for the distribution of the modular mod"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Standalone Modular Mod Reconstruction by Players (Priority: P1)

A player owning a legal retail copy of Bloodborne (CUSA03173 v1.09) wants to reconstruct any combination of the 5 modular mod pillars or the master overhaul packages using lightweight `.patch` files and `apply_patch.py` without needing external modding tools, compiler toolchains, or third-party Python packages, so that they can customize their visual demake experience with zero risk to their vanilla game files.

**Why this priority**: Core purpose of release distribution. Players require a fast, safe, dependency-free method to convert legal base game files and delta patch containers into verified, runnable mod folders.

**Independent Test**: Reconstruct an individual modular mod (such as `bloodborne_retro_hud.patch` or `bloodborne_retro_props.patch`) using `python3 apply_patch.py` against pristine `CUSA03173`, verifying that all output files are placed into the corresponding mod directory and match target SHA256 checksums exactly.

**Acceptance Scenarios**:

1. **Given** pristine `CUSA03173` and `bloodborne_retro_hud.patch`, **When** the player executes `python3 apply_patch.py --game CUSA03173 --patch bloodborne_retro_hud.patch`, **Then** the tool automatically resolves destination folder `Bloodborne Retro HUD and UI` (when `--out` is omitted) and extracts bit-exact assets.
2. **Given** any of the 6 modular patch files (`maps`, `props`, `armors_cloth`, `armors_stiff`, `characters`, `hud`), **When** reconstructed with `apply_patch.py`, **Then** 100% of reconstructed files match source mod hashes with zero integrity errors.
3. **Given** a corrupted vanilla file or mismatched game version, **When** patch reconstruction executes, **Then** `apply_patch.py` halts immediately with an explicit error reporting the offending file path and expected vs actual hash without writing corrupt files.
4. **Given** a player wishing to unpack all modular patches into a single `mods/` directory, **When** invoking batch mode (`--all-patches` or `--patch-dir dist/`), **Then** each patch extracts into its designated modular pillar folder under the target directory.

---

### User Story 2 - Automated Release Verification & Cryptographic Manifest (Priority: P2)

A release maintainer or packager wants an automated release verification script and manifest generator (`SHA256SUMS.txt`), so that all patch packages in `dist/` can be mathematically verified for release readiness, checked against modular separation rules, and published with tamper-proof checksums.

**Why this priority**: Prevents distributing corrupt, out-of-sync, or cross-contaminated patch files. Guarantees that public release artifacts are reproducible, complete, and verified against the clean state of the repository.

**Independent Test**: Execute the automated release verification tool (`tools/pipeline/verify_release_artifacts.py`) across all patch containers in `dist/`, generating `dist/SHA256SUMS.txt` and verifying that all 6 modular patches and master overhaul packages pass roundtrip XOR decodes against `CUSA03173` with exit code 0.

**Acceptance Scenarios**:

1. **Given** all `.patch` files in `dist/`, **When** the release verification suite runs, **Then** all patches pass internal container checksum verification (`MAGIC`, metadata JSON, payload boundaries, XOR inversion) with exit code 0.
2. **Given** validated patches, **When** manifest generation completes, **Then** an authoritative `dist/SHA256SUMS.txt` is generated containing SHA256 digests for all `.patch` containers and `apply_patch.py`.
3. **Given** the clean state of `mods/` (with Talk ESD clean-up applied), **When** verifying `bloodborne_retro_hud.patch`, **Then** the patch container strictly excludes talk scripts, messages, and temporary files, matching clean UI-only assets.

---

### User Story 3 - Distribution & Modding Documentation (Priority: P3)

A player, modder, or mod-pack curator wants clear, comprehensive documentation in `README.md` and `BB_PSX_DEMAKE_GUIDE.md` detailing the modular pillar architecture, installation instructions for single and multiple pillars, conflict guidance (Cloth vs Flat Stiff armors), and mod manager configuration, so that they can install and manage mods without confusion or game crashes.

**Why this priority**: Documentation is the primary interface for users to discover, configure, and troubleshoot modular releases.

**Independent Test**: A user follows the updated `README.md` instructions from start to finish to install two decoupled pillars (e.g. `Maps` + `HUD`), configure `mods.json`, and run the game successfully.

**Acceptance Scenarios**:

1. **Given** `README.md`, **When** read by a player, **Then** it provides:
   - System prerequisites (Python 3.9+, retail Bloodborne v1.09 `CUSA03173`).
   - Instructions for reconstructing individual modular pillars vs full overhaul bundles.
   - Clarification on armors selection (Cloth physics vs Flat Stiff for performance).
   - Valid `mods.json` configuration examples for `bbport`.
   - Complete release artifact summary table (filename, size, SHA256, target folder, description).
   - Troubleshooting for common issues (missing base game files, hash mismatch, conflicting armor mods).
2. **Given** `BB_PSX_DEMAKE_GUIDE.md`, **When** read by a developer, **Then** it provides:
   - Modular packaging pipeline workflow (`package_modular_mods.py`, `create_patch.py`).
   - Architectural invariant rules (subpath isolation, Talk ESD caveats, no cross-contamination).
   - Release audit commands and validation gates.

---

### Edge Cases

- **Mismatched Vanilla Game Version**: User runs `apply_patch.py` against base game version other than v1.09 (e.g., v1.00 or unpatched dump). Patcher must detect vanilla SHA256 mismatch early and abort cleanly without partial writes.
- **Mutual Exclusivity of Armor Variants**: User attempts to install both `Cloth Physics` and `Flat Stiff` armors simultaneously. Patcher and documentation must warn about collision in `dvdroot_ps4/parts/` and explain priority.
- **Path Separation in Modular Tree**: Modular mod packaging must guarantee zero leakage (e.g. `Bloodborne Retro Props and Objects` must never contain `map/`, `parts/`, `chr/`, or `menu/`).
- **Disk Space Exhaustion**: If the target volume runs out of disk space during reconstruction of multi-gigabyte overhaul patches, `apply_patch.py` must catch I/O errors and report remaining space needed rather than crashing unhandled.
- **Default Output Folder Disambiguation**: When running `python3 apply_patch.py -g /path -p bloodborne_retro_maps.patch` without `-o`, the tool must deduce the output directory from the patch metadata or filename (e.g. `Bloodborne Retro Maps`) rather than dumping files into a generic `Bloodborne Low-Poly Overhaul` directory.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `apply_patch.py` MUST deduce the default output folder name from the patch metadata or filename when `--out` is not explicitly provided, mapping each modular patch to its canonical folder name under `mods/`.
- **FR-002**: `apply_patch.py` MUST support a batch mode or multiple `--patch` inputs to reconstruct multiple modular pillars into a target mods directory in a single invocation.
- **FR-003**: The distribution tooling MUST provide an automated release verification script (`tools/pipeline/verify_release_artifacts.py`) that audits all patch files in `dist/` against `CUSA03173` and `mods/`, validating:
  1. Patch header magic (`BBLPO01\x00`) and metadata JSON integrity.
  2. Byte-exact roundtrip reconstruction against source mod files.
  3. Zero forbidden cross-contamination paths per pillar definition.
  4. Generation of an authoritative `dist/SHA256SUMS.txt`.
- **FR-004**: Distribution patch containers MUST cover all defined release deliverables:
  1. Modular Pillar 1: `bloodborne_retro_maps.patch` (`mods/Bloodborne Retro Maps`)
  2. Modular Pillar 2: `bloodborne_retro_props.patch` (`mods/Bloodborne Retro Props and Objects`)
  3. Modular Pillar 3A: `bloodborne_retro_armors_cloth.patch` (`mods/Bloodborne Retro Armors and Weapons - Cloth Physics`)
  4. Modular Pillar 3B: `bloodborne_retro_armors_stiff.patch` (`mods/Bloodborne Retro Armors and Weapons - Flat Stiff`)
  5. Modular Pillar 4: `bloodborne_retro_characters.patch` (`mods/Bloodborne Retro Characters`)
  6. Modular Pillar 5: `bloodborne_retro_hud.patch` (`mods/Bloodborne Retro HUD and UI`)
  7. Master Overhaul Bundles: `bloodborne_lowpoly_overhaul.patch`, `bloodborne_lowpoly_overhaul_cloth.patch`, `bloodborne_lowpoly_overhaul_stiff.patch`
- **FR-005**: All generated `.patch` containers in `dist/` MUST be synchronized with the latest clean state of `mods/` (ensuring broken Talk ESD or obsolete test files are 100% excluded).
- **FR-006**: `README.md` MUST be updated with comprehensive player and modular distribution documentation:
  - Architecture overview of the 5 decoupled pillars.
  - Quick-start guide for single-pillar and multi-pillar installations using `apply_patch.py`.
  - Detailed release artifact inventory table (filename, size, SHA256, target folder, description).
  - Recommended `mods.json` load order configurations for `bbport`.
  - Troubleshooting section for common setup errors (missing base game files, hash mismatch, conflicting armor mods).
- **FR-007**: `BB_PSX_DEMAKE_GUIDE.md` MUST be updated with developer distribution documentation:
  - Workflow for building, packaging, and verifying modular mods from scratch.
  - Release artifact packaging commands (`package_modular_mods.py`, `create_patch.py`).
  - Validation commands and quality gates.
  - Known quirks and architectural invariants for distribution.

### Key Entities

- **Modular Mod Pillar**: One of 5 decoupled content packages (`Maps`, `Props and Objects`, `Armors and Weapons`, `Characters`, `HUD and UI`) that can be loaded independently or in combination without breaking game logic.
- **Patch Container (`.patch`)**: A single binary file format (`MAGIC: BBLPO01\x00`) containing JSON metadata, file manifests, SHA256 checksums, and vectorized XOR differential payloads against retail Bloodborne v1.09.
- **Release Manifest (`dist/SHA256SUMS.txt`)**: Cryptographic checksum manifest containing the SHA256 digest and file name of every distributable patch artifact and standalone client script.
- **Mod Configuration (`mods.json`)**: JSON file utilized by `bbport` and mod managers specifying the execution priority order and enabled/disabled state of installed mod pillars.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the 6 modular patches and 3 master overhaul patches in `dist/` pass automated verification, with 0 hash mismatches and 0 missing assets.
- **SC-002**: Reconstructing any individual modular pillar from scratch using `apply_patch.py` completes in under 15 seconds on standard hardware.
- **SC-003**: Cryptographic manifest `dist/SHA256SUMS.txt` accurately reflects all current `.patch` containers and `apply_patch.py`, verifiable via standard `sha256sum -c`.
- **SC-004**: Zero cross-contamination across modular pillars: `modular_structure_validator.py` reports 100% compliance across all 5 pillars.
- **SC-005**: Updated documentation (`README.md` and `BB_PSX_DEMAKE_GUIDE.md`) provides complete, copy-paste runnable commands for installing each modular pillar and configuring `mods.json`.

## Assumptions

- The base game is Bloodborne PS4 retail disc/digital image (CUSA03173) updated to v1.09.
- Python 3.9+ standard library is available on the user's host system (Linux, Windows, macOS).
- `bbport` / PC port mod loader loads loose files from `<game_root>/mods/<Mod Name>/dvdroot_ps4/...`.
- `apply_patch.py` remains zero-dependency (no pip packages required by players).
