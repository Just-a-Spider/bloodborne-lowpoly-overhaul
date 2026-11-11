# Implementation Plan: bbhost Migration & Pure Retro Shaders Plugin

**Branch**: `006-bbhost-retro-plugin` | **Date**: 2026-11-11 | **Spec**: [specs/006-bbhost-retro-plugin/spec.md](spec.md)

## Summary

Migrate the Bloodborne runner environment from `bbport` to `bbhost v0.2.32` by safely replacing the obsolete local `bbhost v0.2.18` installation, configuring Steam and GPU offload execution wrappers, safely importing campaign saves from `bbport` into `bbhost`, and delivering a self-contained pure C++ plugin (`lowpoly_overhaul.so`) that achieves 100% visual parity with `bbport` PR #419 retro shaders (vertex coordinate jitter, affine texture mapping, nearest-neighbor sampling, and luminance-locked 4x4 Bayer dithering) with zero modifications to the `bbhost` core repository.

## Technical Context

**Language/Version**: C++20 (GCC 13+ / Clang 17+), Bash, GLSL / SPIR-V
**Primary Dependencies**: `bbhost` Plugin API 28 (`include/bbhost_plugin.h`), Vulkan SDK 1.3+, CMake 3.25+, Ninja
**Storage**: Host configuration (`bbhost.toml`), local save directory (`~/.local/share/bbhost/data/saves`, protected)
**Testing**: Acceptance tests (`quickstart.md`), symbol table inspection (`nm -D`), headless/live render verification
**Target Platform**: Linux x86-64 (Arch/Debian/Fedora), NVIDIA GeForce GTX 1650 Max-Q (Vulkan 1.3)
**Project Type**: Standalone dynamic plugin library (`.so`), executable wrapper scripts, desktop shortcut integration
**Performance Goals**: Sustained 60 FPS in Hunter's Dream and Central Yharnam; < 0.2 ms dither compute dispatch latency; sub-2GiB VRAM usage
**Constraints**: Core `bbhost` engine files MUST NOT be modified; base game `CUSA03173/` is pristine/immutable; player saves MUST remain 100% untouched
**Scale/Scope**: 1 dynamic plugin module (`lowpoly_overhaul.so`), 1 launcher wrapper script, 1 desktop shortcut file, host runner rebuild

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I: Baseline Immutability & Safe Mod Isolation**
  `CUSA03173/` pristine base game is completely untouched. Saves in `~/.local/share/bbhost/data/saves` are strictly decoupled from binary replacement and remain protected.
- [x] **Principle II: Tooling Rigor & Unified Runtime**
  All repo Python scripts run via `uv run python ...`. Build uses reproducible CMake + Ninja pipelines.
- [x] **Principle III: Engine Invariants & Havok Physics Preservation**
  No game assets, collisions, or physics meshes are modified.
- [x] **Principle IV: Automated Verification & Gate Enforcement**
  Verification scenarios documented in `quickstart.md`; symbol tables and binaries validated before launch.
- [x] **Principle V: Empirical Documentation & Knowledge Retention**
  Findings regarding `bbhost` Plugin API evolution (API 11 -> API 28) and luminance vs RGB dithering documented in `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/006-bbhost-retro-plugin/
├── plan.md              # This file
├── research.md          # Technical decisions and rationale
├── data-model.md        # Configuration schema and entity models
├── quickstart.md        # Step-by-step verification guide
├── contracts/           # API and launcher contracts
│   ├── plugin-api.md
│   └── launcher-contract.md
├── checklists/
│   └── requirements.md  # Quality validation checklist
└── tasks.md             # Implementation tasks (/speckit-tasks output)
```

### Source Code Layout

```text
/home/andre/Games/
├── bbhost/                         # Upgraded runner installation (v0.2.32)
│   ├── bbhost                      # Native execution binary
│   ├── run-bbhost.sh               # Execution script with GPU offload flags
│   ├── include/bbhost_plugin.h     # Host Plugin API (v28)
│   └── plugins/
│       └── lowpoly_overhaul.so     # Built retro graphics plugin
├── reference/                      # External feature & tool workspace (outside mod repo)
│   ├── tools/
│   │   └── import_bbport_saves.py  # Save backup and sync utility
│   └── plugins/
│       └── lowpoly_overhaul/       # Plugin source directory
│           ├── lowpoly_overhaul.cpp
│           ├── dither_pipeline.h
│           ├── shaders/
│           │   ├── dither_luma.comp
│           │   └── dither_luma.spv.h
│           └── Makefile
├── Bloodborne/                     # Low-Poly Overhaul mod repository (clean)
│   └── specs/006-bbhost-retro-plugin/
└── ~/.local/bin/
    └── bbhost                      # System wrapper script (offload --no-boost)
```

**Structure Decision**: Clean separation: all tools, migration scripts, and plugin sources live outside the mod repository under `/home/andre/Games/reference/`. The `Bloodborne/` repository remains pristine with zero non-mod tooling contamination.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| None | All operations adhere strictly to Constitution and user rules | N/A |
