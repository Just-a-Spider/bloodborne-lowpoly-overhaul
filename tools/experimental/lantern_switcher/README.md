# Experimental / Paused: Native In-Game Lantern Switcher (Feature 004)

## Status: PAUSED
This subsystem is experimental and currently paused due to an upstream compiler defect in the Soulstruct ESD binary writer.

### Known Defect: Soulstruct `state_id_offsets` Collision
- **Root Cause**: In `soulstruct.esd.to_writer`, the serializer records `state_id_offsets` as a flat `dict[int, int]` keyed only by `state_id` (`0..7`), rather than scoping by `(state_machine_index, state_id)`.
- **Symptom**: Every subsequent state machine in `esd.state_machines` overwrites `state_id_offsets` with its own offsets. Cross-state-machine jump pointers are misdirected, causing FromSoftware's Talk script interpreter to abort and rendering in-game lamps inert (cannot prompt interaction or ignite).
- **Remediation**: Paused until a compiler-level patch is implemented in Soulstruct or direct bytecode patching is developed.

### Quarantined Modules
- `inject_lantern_talk_esd.py`: Injects choice entries into map Talk ESDs.
- `inject_lantern_menu_text.py`: Injects dialogue text into `menu.msgbnd.dcx`.
- `lantern_event_listener.py`: Memory scanning daemon for lamp event flags.
- `lantern_mod_types.py`: Domain data models and constants.
- `verify_lantern_mod.py`: Integration test suite for the paused switcher.
- `fixtures/`: Schema validation fixtures.
