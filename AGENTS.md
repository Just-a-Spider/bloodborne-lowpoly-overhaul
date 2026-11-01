# Agent Rules for Bloodborne PSX Demake Project

## Execution Standards
- **Python Environment**: Always use `uv run python ...` for running any Python scripts, CLI tools, tests, or benchmarks (e.g. `uv run python tools/verify_c8030_doll.py`). Never invoke `python` or `python3` directly without `uv run`.
- **Baseline Immutability**: `CUSA03173/` is the pristine base game and MUST NEVER be modified. All mod experiments and outputs must be written only to `CUSA03173-PSX/`.
- **Save Protection**: Never modify saves in `~/.local/share/bbhost/data/saves`.
- **Library Quirks & Workarounds Documentation**: Whenever a library discrepancy, API mismatch, or serialization quirk (Soulstruct, pyfqmr, scipy, etc.) is identified, immediately append the technical root cause and workaround to `BB_PSX_DEMAKE_GUIDE.md` (and `BB_PSX_DEMAKE_MATH_AND_FINDINGS.md` if binary layout or math). Do not discard or solve silently.
