# Implementation Plan: In-Game On-Demand Retro Mod Switcher

**Branch**: `003-realtime-graphics-toggle` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [spec.md](spec.md)

---

## Summary

Implement an in-engine on-demand retro mod switcher that allows players to toggle between pristine Vanilla HD graphics (`CUSA03173/`) and the 5-Pillar 32-Bit Retro Overhaul (`mods/`) during gameplay. Pressing **L3 + R3** simultaneously initiates a **200ms cross-dissolve fade-out**, atomically pivots the active virtual overlay in `out/mod-game-*`, and triggers a fast checkpoint reload (~1.5–2s) that reconstructs scene resources in memory with bit-for-bit player state preservation and zero process restarts.

---

## Technical Context

**Language/Version**: Python 3.9+ (tools, test harness, overlay coordinator), C/C++ (guest hooks in `runtime_pad.c` / `bbsc_cinematic.cpp`).  
**Primary Dependencies**: `SDL3` (gamepad sampling), standard Linux VFS (`os.symlink`, `os.replace`), `jsonschema` (contract verification).  
**Storage**: Atomic JSON configuration file (`out/retro_toggle_state.json`) and Linux symlink trees (`out/mod-game-*`).  
**Testing**: Hermetic Python test suite (`tools/verify_mod_switcher.py`) executed via `uv run python`.  
**Target Platform**: Linux x86_64 (`bbhost` native Vulkan runner, `shadPS4`).  
**Project Type**: In-Engine Mod Switcher & Dynamic VFS Coordinator.  
**Performance Goals**: < 200ms fade transition, < 5ms atomic overlay swap, < 2.5s total reload cycle, 60+ FPS in gameplay.  
**Constraints**: Zero modification to `CUSA03173/`, zero modification to save files in `~/.local/share/bbhost/data/saves`, < 2,048 MiB total GPU VRAM footprint on 4GB hardware.  
**Scale/Scope**: 5 modular pillars (146 map files, 867 prop files, 1,125 armor files, 269 character files, 1 HUD file) swapped in synchrony.

---

## Constitution Check

*GATE: All principles evaluated and satisfied.*

| Principle | Requirement | Plan Compliance | Verdict |
| :--- | :--- | :--- | :--- |
| **I. Baseline Immutability** | `CUSA03173/` read-only, saves untouched | Switcher operates strictly via symlink redirection in `out/mod-game-*`; saves untouched | **PASS** |
| **II. Tooling Rigor (`uv run`)** | All Python tools run via `uv run` | Test harness and coordinator use `uv run python` exclusively | **PASS** |
| **III. Engine Invariants & Havok** | Physics (`.hkx`), AABBs, FaceSets preserved | Checkpoint reload re-initializes engine cleanly without tearing in-flight Havok solvers | **PASS** |
| **IV. Automated Verification** | Automated test suites prior to merge | Automated test harness (`tools/verify_mod_switcher.py`) for chord, swap, and persistence | **PASS** |
| **V. Empirical Documentation** | Record quirks & solutions in guides | Findings documented in `BB_PSX_DEMAKE_GUIDE.md` and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md` | **PASS** |
| **VI. Multi-Model Quality Audit** | Independent quality audit (Sonnet 4.6) | Final milestone subject to adversarial verification audit | **PASS** |

---

## Project Structure

### Documentation & Specifications

```text
specs/003-realtime-graphics-toggle/
├── spec.md              # Clarified feature specification
├── plan.md              # Implementation plan (this document)
├── research.md          # Phase 0 architectural decisions & investigation
├── data-model.md        # Phase 1 entities, state machine & invariants
├── quickstart.md        # Phase 1 verification and execution guide
├── contracts/
│   ├── toggle_state_schema.json  # JSON schema for persistent state
│   └── switcher_ipc_contract.json # Schema for IPC/CLI switch commands
└── tasks.md             # Phase 2 output (generated via /speckit-tasks)
```

### Source Code & Tooling Layout

```text
tools/
├── pipeline/
│   └── mod_overlay_manager.py     # Atomic symlink overlay coordinator
└── verify_mod_switcher.py         # Automated test suite (chord, swap, persistence)

/home/andre/Games/bbport-src/
├── src/
│   └── runtime_pad.c              # Pad input chord hook (L3 + R3 detection)
└── scripts/
    └── mods.py                    # Dynamic dual-profile overlay generator
```

---

## Implementation Phases

### Phase 0: Outline & Research *(Completed)*
- Analyzed `bbport` mod overlay architecture in `scripts/mods.py` and `run.py`.
- Reverse-engineered pad input sampling in `src/runtime_pad.c` (`BTN_L3 | BTN_R3`).
- Verified in-engine checkpoint warp infrastructure in `bloodborne_re.cpp`.
- Documented findings in [research.md](research.md).

### Phase 1: Design & Contracts *(Completed)*
- Defined domain entities and state machine in [data-model.md](data-model.md).
- Authored contract schemas in [contracts/toggle_state_schema.json](contracts/toggle_state_schema.json) and [contracts/switcher_ipc_contract.json](contracts/switcher_ipc_contract.json).
- Authored end-to-end verification workflows in [quickstart.md](quickstart.md).

### Phase 2: Tasks & Implementation *(Next Step via `/speckit-tasks`)*
- Task 1: Implement `tools/pipeline/mod_overlay_manager.py` for atomic VFS profile switching.
- Task 2: Implement test harness `tools/verify_mod_switcher.py` with mock input and overlay verification.
- Task 3: Integrate L3+R3 chord handler in `bbport` pad runtime / coordinator hook.
- Task 4: Connect smooth 200ms fade transition and checkpoint reload trigger.
- Task 5: End-to-end verification and adversarial audit.
