# Implementation Plan: Native In-Game Lantern Mod Switcher (MOAL-Style)

**Branch**: `004-native-lantern-switcher` | **Date**: 2026-11-10 (Revised) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [spec.md](spec.md) post-adversarial analysis.

---

## Summary

Implement a diegetic native lantern presentation switcher for Bloodborne. Interacting with any active lit lantern presents dialogue options ("Switch to Retro 32-Bit Demake" / "Restore Modern High-Definition") alongside standard warp options. Selecting the toggle sets event flag `999901` or `999902`, triggers FromSoftware's authentic lantern kneeling/warp sequence, and synchronizes the visual presentation mode across `out/retro_toggle_state.json`, `bbport.ini` (`retro_mode`), and `mods.json`. Unlit lamps preserve standard ignition routine (`SM 2147483639`) bit-for-bit without menu pollution. Supports both standalone vanilla play and MOAL integration.

---

## Technical Context

**Language/Version**: Python 3.9+ (tooling, FMG injection, test harness), FromSoftware ESD/FMG binary formats.  
**Primary Dependencies**: `soulstruct` (Binder, FMG, MSGBND, TalkESDBND), Linux VFS (`os.replace`), `bbport` runtime.  
**Storage**: Injected `msg/engus/menu.msgbnd.dcx` text records, `script/talk/*.talkesdbnd.dcx`, `out/retro_toggle_state.json`, `bbport.ini`.  
**Testing**: Multi-tier test suite (`tools/verify_lantern_mod.py`) verifying EzState condition graph, FMG strings, persistence, and MOAL compatibility via `uv run python`.  
**Target Platform**: Linux x86_64 (`bbhost` native Vulkan runner, `bbport` / `bb-probe`).  
**Project Type**: Native Game Mod (`msg/`, `script/talk/`) & Presentation Sync Coordinator.  
**Performance Goals**: < 2.5s total reload cycle, < 0.2ms atomic VFS swap, 60+ FPS in gameplay.  
**Constraints**:  
- Zero modification to `CUSA03173/` (Principle I).
- Zero modification to save files in `~/.local/share/bbhost/data/saves` (Principle I).
- Unlit lamp ignition routine (`SM 2147483644 State 7 -> SM 2147483639`) MUST NOT be hijacked.
- Frame 0 menu abort (`IsTalkExclusiveMenuOpen() == 0`) MUST NOT be present in State 0 conditions.
- Test suites MUST execute automated verification gates with exit code 0 without mock tautologies (Principle IV).

---

## Constitution Check

*GATE: All principles evaluated and satisfied post-redesign.*

| Principle | Requirement | Plan Compliance | Verdict |
| :--- | :--- | :--- | :--- |
| **I. Baseline Immutability** | `CUSA03173/` read-only, saves untouched | Mod assets packaged strictly into `mods/` overlays; base game untouched | **PASS** |
| **II. Tooling Rigor (`uv run`)** | All Python tools run via `uv run` | All Soulstruct injection and verification scripts run with `uv run python` | **PASS** |
| **III. Engine Invariants & Havok** | Physics (`.hkx`), AABBs, FaceSets preserved | Native bonfire warp cycle preserves Havok solvers and collision meshes | **PASS** |
| **IV. Automated Verification** | Automated test suites prior to merge | Rewritten `tools/verify_lantern_mod.py` validates EzState condition graph, unlit safety, and MOAL integrity | **PASS** |
| **V. Empirical Documentation** | Record quirks & solutions in guides | Revised `BB_PSX_DEMAKE_GUIDE.md` Section 17 and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md` Section 32 | **PASS** |
| **VI. Multi-Model Quality Audit** | Independent quality audit (Sonnet 4.6) | Full pipeline and talk binders audited against adversarial findings | **PASS** |

---

## Project Structure

### Documentation & Specifications

```text
specs/004-native-lantern-switcher/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this document)
├── research.md          # Architecture decisions & root cause analysis
├── data-model.md        # Entities, state machine & invariants
├── quickstart.md        # Verification and execution guide
├── contracts/
│   ├── lantern_menu_contract.json  # Schema for injected FMG dialogue items
│   └── event_flag_registry.json    # Schema for reserved event flags
└── tasks.md             # Actionable task ledger (Phase 2 output)
```

### Source Code & Tooling Layout

```text
tools/
├── pipeline/
│   ├── inject_lantern_menu_text.py # Injects text IDs 70011010/70011011 into menu.msgbnd.dcx
│   ├── inject_lantern_talk_esd.py  # Patches lamp Talk ESDs (State 6 hook only, canonical conds)
│   ├── lantern_event_listener.py   # Event flag coordinator & settings synchronizer
│   └── lantern_mod_types.py        # Shared domain types, constants, flags
└── verify_lantern_mod.py           # Automated test suite (FMG, ESD graph, persistence, MOAL)

mods/Bloodborne Retro HUD and UI/dvdroot_ps4/
├── msg/engus/
│   └── menu.msgbnd.dcx             # Modified menu text with lantern toggle prompts
└── script/talk/
    └── mXX_00_00_00.talkesdbnd.dcx # 16 patched lamp Talk ESD binders (State 6 only)
```

---

## Implementation Phases

### Phase 0: Outline & Research *(Completed)*
- Reverse-engineered FromSoftware lamp Talk ESD state machines (`SM 2147483646`, `SM 2147483644`, `SM 2147483639`).
- Diagnosed unlit lamp breakage: State 7 is `非稼動状態_非マルチ中` (ignition), State 6 is `稼動状態_非マルチ中` (lit warp). Hooking State 7 destroys unlit lamp interaction.
- Diagnosed frame 0 menu abort: `IsTalkExclusiveMenuOpen() == 0` evaluates true on tick 0. Replaced with canonical choice/cancel condition graph.
- Documented in [research.md](research.md).

### Phase 1: Design & Contracts *(Completed)*
- Defined domain entities and updated state machine in [data-model.md](data-model.md).
- Updated contracts in [contracts/lantern_menu_contract.json](contracts/lantern_menu_contract.json) and [contracts/event_flag_registry.json](contracts/event_flag_registry.json).
- Authored verification workflows in [quickstart.md](quickstart.md).

### Phase 2: Tasks & Implementation *(Next Step via `/speckit-tasks`)*
- Task 1: Revert in-place edits to MOAL talk binders (`bbport-src/mods/MOAL .../*.bak`).
- Task 2: Fix `tools/pipeline/inject_lantern_talk_esd.py`:
  - Preserve State 7 calling `SM 2147483639` for all lamps.
  - Redirect ONLY State 6 to `SM 2147483500`.
  - Rewrite SM `2147483500` State 0 condition evaluation to eliminate frame 0 exit.
- Task 3: Re-inject all 16 vanilla map binders into `mods/Bloodborne Retro HUD and UI/` and `bbport-src/mods/`.
- Task 4: Fix `tools/pipeline/lantern_event_listener.py` to handle parent-child ptrace, file IPC, `bbport.ini` retro mode sync, and safe directory handling.
- Task 5: Rewrite `tools/verify_lantern_mod.py` test harness to validate EzState condition graph, unlit lamp safety, and MOAL integrity without mock tautologies.
- Task 6: Correct documentation in `BB_PSX_DEMAKE_GUIDE.md` Section 17 and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md` Section 32.
