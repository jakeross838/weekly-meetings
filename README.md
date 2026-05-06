# Ross Built — weekly-meetings

Private internal codebase for the Ross Built Monday Binder pipeline. It
ingests Buildertrend daily-log scrapes plus weekly meeting transcripts,
runs a multi-stage data layer (phase classification → instances → medians
→ sub-phase rollups → cross-data insights) over the company's 11 active
construction jobs, and produces a Monday-morning meeting binder served
via a local Flask dashboard at `http://localhost:8765`. Five documents
land per week (master, executive for Lee, pre-construction for Andrew,
five PM packets) — each rendered live from the data layer rather than
pre-built. Everything in this repo is the source code for that pipeline;
client, sub, and financial data live in gitignored directories.

## How to run the weekly pipeline

One command runs the full Monday Binder pipeline end-to-end:

```
python scripts/run_weekly_pipeline.py
```

Operator notes, manual-input checklist (transcripts, BT scrape recency,
ANTHROPIC_API_KEY, etc.), and known issues are in
[`scripts/run_weekly_pipeline.README.md`](scripts/run_weekly_pipeline.README.md).
The legacy `run_weekly.bat` runs only the meeting-prep + accountability
subset and is preserved for the existing Task Scheduler hook; the
orchestrator script is the new full-pipeline entry point.

## How to start the dashboard

```
start_dashboard.bat
```

Opens `http://localhost:8765/` in the default browser. The Flask app
serves transcript intake, sub/job dashboards, and on-click PDF rendering
for the meeting-prep binder. Closing the console window stops the server.
The orchestrator script restarts the server at the end of each weekly
run so newly-edited templates and `render_helpers.py` changes are picked
up automatically.

## Sensitive data

**`data/`, `binders/`, `transcripts/`, `api-responses/`, `state/`,
`logs/`, `tmp-pdfs/`, `exports/`, and `print/` are intentionally
gitignored.** They contain client, subcontractor, and financial detail
extracted from meeting transcripts and Buildertrend daily logs — not
material that should ever propagate to a remote repo. The full ignore
list is in [`.gitignore`](.gitignore).

This means a clean `git clone` of this repo will NOT have working data
to operate on. To recover a working environment after a fresh clone:

1. Restore `binders/<PM>.json` (the per-PM action item state) from a
   local backup. These are the only true "source of truth" data files —
   everything else under `data/` is regenerated.
2. Confirm the sibling `C:\Users\Jake\buildertrend-scraper\` repo is
   present and has a recent `data/daily-logs.json` (its own scraper
   pipeline, separately maintained).
3. Run `python scripts/run_weekly_pipeline.py`. The orchestrator
   regenerates `data/derived-phases*.json`, `phase-instances*.json`,
   `phase-medians.json`, `sub-phase-rollups.json`, `bursts.json`,
   `job-stages.json`, `insights.json`, and `meeting-commitments.json`
   from those two sources.

**There is no automated backup of `binders/` to anywhere off this
machine.** Treat them as the only irreplaceable artifact in the system
and back them up manually until that gap is closed.

## License

All Rights Reserved — Ross Built Custom Homes. See [`LICENSE`](LICENSE).
This is private internal code, not open source.
