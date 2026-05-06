# Relocation note — `build_phase3_followup.py`

**Date:** 2026-05-06 (wmp29 / wmp30)

`build_phase3_followup.py` graduated from this `.planning/` location to the
production `scripts/` directory and was renamed in the process:

- **Old:** `.planning/milestones/m02-schedule-intelligence/phases/03-duration-math/scripts/build_phase3_followup.py`
- **New:** `scripts/build_sub_phase_rollups.py`

The new name reflects what the script actually does (builds
`data/sub-phase-rollups.json`, plus updates `bursts.json`,
`phase-instances-v2.json`, `phase-medians.json`, and `derived-phases-v2.json`)
rather than the planning-phase number it was born in.

## Verification

The relocation was logic-only. Source diff between the old `.planning/` copy
and the new `scripts/` copy was confined to two path-related lines (the
`PHASE_DIR` constant and the debug-state file path) — no math, no output
shape changes. Both scripts were run under `PYTHONIOENCODING=utf-8` against
the same `data/` and `daily-logs.json` inputs; their five output files were
**byte-identical** (md5 match across `sub-phase-rollups.json`, `bursts.json`,
`phase-instances-v2.json`, `phase-medians.json`, `derived-phases-v2.json`).

## Notes for future readers

- `build_phase3.py` (the **first-pass** script in this same `.planning/scripts/`
  directory) was **not** relocated. It produces the initial bursts /
  instances / medians; the followup script reapplies library expansion and
  adds the rollups. The followup is what's needed for steady-state runs;
  the first-pass is a one-off that pre-dates the cleaned baseline.
- The followup script's debug state file (`_phase3_followup_state.json`)
  now lands in `scripts/` next to the new script. Its filename was not
  updated to match the new script name (deliberate: location-only move).
- The script still has a Windows cp1252 print-encoding issue on a `≥`
  character in STEP 5. The new home in `scripts/` doesn't fix this — it
  has to be run with `PYTHONIOENCODING=utf-8` set, or it crashes mid-run
  (after writing `derived-phases-v2.json` but before writing the other
  four). Future maintenance pass should fix the print statement.
- The orphaned `_phase3_followup_state.json` in this directory was last
  refreshed by the relocation verification run on 2026-05-06. It will go
  stale; safe to delete in a future cleanup.
