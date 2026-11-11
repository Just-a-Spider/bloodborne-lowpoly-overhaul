# Research & Architectural Decisions: Native In-Game Lantern Mod Switcher (MOAL-Style)

**Feature Branch**: `004-native-lantern-switcher`  
**Date**: 2026-11-10 (Revised Post-Analysis)  
**Status**: Ready  

---

## 1. Executive Summary & Problem Formulation

Interacting with lanterns in Bloodborne provides an authentic in-game mechanism to toggle between Retro 32-Bit Demake and Modern HD presentation. The previous implementation failed in live testing because:
1. It hijacked State 7 in Talk ESD SM `2147483644` (the unlit lamp ignition routine calling SM `2147483639`), preventing unlit lamps from ever being ignited.
2. SM `2147483500` State 0 condition 0 checked `IsTalkExclusiveMenuOpen() == 0` on frame 0, aborting the interaction menu immediately upon opening.
3. The background memory watcher attempted raw `/proc/<pid>/mem` reading without parent ptrace permissions, failing silently under Linux Yama ptrace scope (`yama.ptrace_scope = 1`).
4. The file swap logic attempted `os.replace` on non-empty directories materialized by `bbport`'s `scripts/mods.py`, raising `EISDIR`.
5. The automated verification suite (`verify_lantern_mod.py`) contained malformed mock tests that passed 100% despite broken runtime behavior.

This revision redesigns the Talk ESD state machine topology, fixes condition evaluation semantics, resolves host-guest signaling, and provides genuine verification gates complying with Constitution Principle IV.

---

## 2. Research Decisions & Findings

### Decision 1: Talk ESD State Machine Topology & Unlit Lamp Safety
- **Investigation**:
  - In FromSoftware's engine, lamp interaction begins in SM `2147483646`:
    - State 1: `地上子ワープ椅子_マルチ中` (Multiplayer) -> calls SM `2147483645`.
    - State 2: `地上子ワープ椅子_非マルチ中` (Non-Multiplayer) -> calls SM `2147483644`.
  - In SM `2147483644`:
    - State 1: `非稼動状態_非マルチ中` (Unlit/Inactive Lamp) -> transitions to State 4 -> State 7.
      - **State 7 calls SM 2147483639**: Plays ignition animation, writes ignition flag, ignites lamp.
      - **CRITICAL INVARIANT**: State 7 MUST NEVER BE REDIRECTED. Overriding State 7 destroys lamp ignition entirely.
    - State 2: `稼動状態_非マルチ中` (Lit/Active Lamp) -> transitions to State 3 -> State 6.
      - In vanilla: State 6 calls SM `2147483643` (warp dialog).
      - In MOAL: State 6 calls SM `2147483500` (custom list menu).
      - **HOOK POINT**: State 6 is the SOLE valid hook point for custom lantern menus.
- **Decision**:
  - In vanilla ESDs: Redirect **only State 6** to SM `2147483500`. Leave State 7 calling SM `2147483639` untouched.
  - In MOAL ESDs: Restore pristine MOAL talk binders from `.bak`. Inject choices directly into MOAL's existing SM `2147483500`. Leave State 7 calling SM `2147483639` untouched.
- **Rationale**: Preserves 100% of FromSoftware's lamp ignition logic across all 56 lamps in all 16 maps.

### Decision 2: EzState State 0 Condition Evaluation (Frame 0 Exit Elimination)
- **Investigation**:
  - EzState evaluates state conditions every frame.
  - In SM `2147483500` State 0, `ShowShopMessage(0, 0, 0)` requests the UI system to open the talk list menu asynchronously.
  - On frame 0, `IsTalkExclusiveMenuOpen()` evaluates to 0 because the menu is not yet rendered.
  - Checking `IsTalkExclusiveMenuOpen() == 0` in Condition 0 causes an immediate transition to terminal State 19 on frame 0, aborting the menu before the player sees it.
  - In canonical FromSoftware talk scripts (e.g. `t100000.esd`), menus do NOT check `IsTalkExclusiveMenuOpen() == 0`. Instead, `GetTalkListEntryResult()` returns `-1` while awaiting input, `0` on Cancel (Circle), and positive integers on selection.
- **Decision**:
  - Restructure SM `2147483500` State 0 conditions:
    - `cond 0`: `GetTalkListEntryResult() == 1` -> State 1 (Hunter's Dream warp via SM 2147483643).
    - `cond 1`: `GetTalkListEntryResult() == 20` -> State 20 (Retro switch: flag 999901 + warp).
    - `cond 2`: `GetTalkListEntryResult() == 21` -> State 21 (Modern restore: flag 999902 + warp).
    - `cond 3`: `GetTalkListEntryResult() == 0 or GetTalkListEntryResult() == 99` -> State 19 (Cancel / Leave).
  - Eliminate `IsTalkExclusiveMenuOpen() == 0` test entirely.
- **Rationale**: Conforms to standard FromSoftware talk list menu architecture, eliminating frame 0 aborts.

### Decision 3: Host Signaling & Linux Permission Architecture
- **Investigation**:
  - Linux Yama ptrace scope (`/proc/sys/kernel/yama/ptrace_scope = 1`) forbids opening `/proc/<pid>/mem` with `r+b` and blocks `process_vm_readv` between un-traced sibling processes, raising `EACCES` / `EPERM`.
  - An independent background daemon cannot sample guest memory without `CAP_SYS_PTRACE` or being the parent process.
  - However, when the game runs under a wrapper/parent (e.g. `run_with_retro_daemon.sh` or launcher), parent-child ptrace permissions are valid.
  - Additionally, file-based IPC (`out/flag_signal.txt`, `out/retro_toggle_state.json`) and `bbport.ini` settings (`retro_mode=1` vs `retro_mode=0`) provide deterministic, permission-free coordination.
- **Decision**:
  - Support dual signaling:
    1. Parent-traced memory observation when launched via `run_with_retro_daemon.sh`.
    2. File-based IPC (`out/flag_signal.txt`) and `out/retro_toggle_state.json` persistence.
    3. Update `bbport.ini` `retro_mode` flag to sync Vulkan point-filtering and dithering.
- **Rationale**: Eliminates silent permission failures on Linux.

### Decision 4: VFS Directory Handling & Engine Texture Invariants
- **Investigation**:
  - `bbport`'s `scripts/mods.py` creates materialized directory trees (`dvdroot_ps4/map/`, etc.) rather than top-level symlinks when loose files are replaced.
  - Calling `os.replace` on a materialized directory raises `EISDIR`.
  - FromSoftware's engine reloads map geometry and entities on a checkpoint warp, but UI textures (`common.tpf.dcx`) are initialized once at boot.
- **Decision**:
  - In `ModOverlayManager`, maintain top-level atomic symlink pivoting at the `dvdroot_ps4` level (`out/vfs_overlay/dvdroot_ps4`), where `os.replace` is kernel-atomic.
  - In `bbport`, sync `mods.json` and `bbport.ini` so presentation profile is persistent across sessions and area reloads.
- **Rationale**: Avoids `EISDIR` errors while respecting FromSoftware's memory caching behavior.

### Decision 5: Non-Malformed Verification Suite
- **Decision**:
  - Redesign `tools/verify_lantern_mod.py`:
    1. Validate FMG Entry 30 text IDs and strings.
    2. Validate Talk ESD state machine graph: assert State 7 calls SM 2147483639 (unlit lamp protection); assert State 6 calls SM 2147483500; assert State 0 does NOT contain frame 0 exit condition `IsTalkExclusiveMenuOpen() == 0`.
    3. Validate MOAL talk binders: assert State 7 intact, choices 20/21 present.
    4. Validate state persistence and `mods.json` synchronization.
- **Rationale**: Satisfies Constitution Principle IV with zero false positives.
