# Ross Built · Monday Binder v2 — Operator Guide

The system is automated end-to-end on Monday morning. PMs receive PDFs at the start of their week and don't need to open the terminal or Claude Code. Jake handles transcripts on Tuesday.

If something looks broken, see *When something looks wrong* at the end.

---

## The weekly cycle

```
                   MONDAY                                    TUESDAY                  WED-FRI
        ┌──────────────────────────┐         ┌────────────────────────┐    (PMs working their packets)
   7:30 │ run_weekly.bat fires      │         │  Jake processes        │
   am   │  → build_meeting_prep     │         │  transcripts via       │
        │  → validate_accountability│         │  process.py            │
        │  → state/LAST_RUN_STATUS  │         │                         │
        └──────────────────────────┘         └────────────────────────┘
                       │                                    │
                       ▼                                    ▼
        13 PDFs in monday-binder/         binders/*.json updated
        meeting-prep/  (master, exec,    (action items refreshed
        precon, PM × office+site)         from meeting transcripts)
                       │
                       ▼
                Jake reviews master.pdf
                Lee reviews executive.pdf
                Andrew reviews preconstruction.pdf
                PMs review pm/{slug}-office.pdf  (for office meetings)
                       and pm/{slug}-site.pdf    (for site meetings)
                       │
                       ▼
                 Run the meeting.
                 Mark commitments / new items / closures (in transcripts).

                 NEXT MONDAY: automation diffs against this week's snapshot.
```

---

## Setup (one-time)

### Schedule the Monday automation

The `run_weekly.bat` script lives at the project root. Schedule it via Windows Task Scheduler:

**Quickest path — schtasks (no admin needed if running as the current user):**

```
schtasks /create ^
  /tn "RossBuilt-Monday-Binder" ^
  /tr "C:\Users\Jake\weekly-meetings\run_weekly.bat" ^
  /sc weekly /d MON /st 07:30 ^
  /f
```

Run that once in `cmd.exe`. Replace 07:30 with your preferred time. The `/f` flag overwrites any existing task with the same name. The task fires every Monday at 7:30am (your local time, which Task Scheduler uses by default — no UTC conversion needed).

**First run scheduled for: Monday May 4, 2026 at 7:30am ET.**

If schtasks reports access denied, open Task Scheduler GUI (`taskschd.msc`) and create the task by hand:
- Action: Start a program → `C:\Users\Jake\weekly-meetings\run_weekly.bat`
- Trigger: Weekly on Monday at 7:30am, starting 2026-05-04
- Settings: "Run only when user is logged on" (default)

To verify the task exists:

```
schtasks /query /tn "RossBuilt-Monday-Binder"
```

To remove later:

```
schtasks /delete /tn "RossBuilt-Monday-Binder" /f
```

---

## What gets generated each Monday

`monday-binder/meeting-prep/` after `run_weekly.bat` runs:

| Audience    | File                                              | Pages |
|-------------|---------------------------------------------------|-------|
| Jake        | `master.pdf`                                      | ≤2    |
| Lee         | `executive.pdf`                                   | 1     |
| Andrew      | `preconstruction.pdf`                             | ≤2    |
| Each PM     | `pm/{nelson-belanger,bob-mozine,...}-office.pdf`  | ≤2    |
| Each PM     | `pm/{nelson-belanger,...}-site.pdf`               | ≤2    |

Plus the accountability report at `data/accountability-week-{iso_week}.md` (e.g., `accountability-week-2026-W18.md`).

---

## Verifying Monday's run succeeded

After Task Scheduler fires (or after running `run_weekly.bat` manually):

```bash
# Single-line status
type state\LAST_RUN_STATUS.txt
```

You should see:

```
last_run_at=2026-MM-DDTHH:MM:SS
overall=PASS
build_meeting_prep_exit=0
validate_accountability_exit=0
banner=OK iso_week=2026-WNN last=N this=N closed=N carried=N new=N stuck=N near_miss=N -> ...
log_file=logs\monday-run-YYYYMMDD-HHMMSS.log
```

If `overall=PASS` and exit codes are both 0, you're good. The `banner=` line tells you the accountability diff at a glance.

If anything fails:
- `overall=BUILD_FAIL` → check the log file for the build_meeting_prep.py traceback
- `overall=VALIDATE_FAIL` → check the log for validate_accountability.py traceback
- `banner=NO_BANNER` → the validate script didn't emit its single-line summary; check for a Python exception

---

## Manual rebuild (any time)

If you want to regenerate without waiting for Monday:

```bash
cd C:\Users\Jake\weekly-meetings
run_weekly.bat
```

The build is idempotent — running it twice on the same Monday updates the snapshot rather than appending. Running it on a Tuesday creates a new ISO-week snapshot only if a week boundary has passed.

To run only the build (no accountability validation):

```bash
python monday-binder\build_meeting_prep.py
```

---

## Adding new transcripts (Jake's Tuesday job)

The transcript pipeline (`process.py`) is unchanged from v1. After a meeting, drop the Plaud `.txt` into `transcripts/inbox/`, then run:

```bash
python process.py
```

This:
1. SHA-dedupes against `state/processing-ledger.jsonl` (skips re-processing identical files)
2. Sends each new transcript to Claude Opus 4.7 for binder-update extraction
3. Writes the updated PM binder JSON to `binders/{PM_Last}.json`
4. Moves the transcript to `transcripts/processed/`
5. Logs the result to `logs/{date}.log`

The next Monday's `run_weekly.bat` will pick up the updated `binders/*.json` automatically.

### Filename formats process.py accepts

- `MM-DD_<FirstName>_<Site|Office>.txt` — canonical (`04-23_Lee_Office.txt`)
- Plaud defaults — `04-23 Lee Worthy Office Production Meeting (Krauss_Ruthven)-transcript.txt`
- Mixed underscored — `Martin Site Production Meeting 4_28_26.txt`

If the parser can't figure out PM/Date/Type, the file moves to `transcripts/skipped/` with a note.

---

## Where the data lives

| What                            | Path                                          |
|---------------------------------|-----------------------------------------------|
| Action items per PM             | `binders/{PM_Last}.json`                      |
| Enriched action items           | `binders/enriched/{PM_Last}.enriched.json`    |
| Phase 3 schedule data           | `data/phase-instances-v2.json`, etc.          |
| Insights output                 | `data/insights.json`                          |
| Commitment snapshots            | `data/meeting-commitments.json`               |
| Weekly accountability reports   | `data/accountability-week-{iso_week}.md`      |
| Daily logs (BT scraper)         | `../buildertrend-scraper/data/daily-logs.json`|
| Monday automation log           | `logs/monday-run-{ts}.log`                    |
| Last-run status                 | `state/LAST_RUN_STATUS.txt`                   |
| Meeting prep PDFs               | `monday-binder/meeting-prep/`                 |
| v1 system (archived)            | `monday-binder-v1-archive/`                   |

---

## When something looks wrong

### "I ran run_weekly.bat manually but no PDFs appeared"

The `.bat` only generates HTML files via `build_meeting_prep.py`. PDFs are produced by Edge headless when the bat runs, but only if your `monday-binder/meeting-prep/` folder is not write-locked. Check:

```bash
ls monday-binder/meeting-prep/*.pdf
ls monday-binder/meeting-prep/pm/*.pdf
```

If HTML exists but no PDF, regenerate PDFs manually with the snippet from `monday-binder/build_meeting_prep.py` (or rerun the bat — it's idempotent).

### "The accountability report shows zero everything"

If it's the first Monday after a fresh setup or after `data/meeting-commitments.json` was deleted, this is expected. The first run captures a snapshot. The second run (next Monday) starts diffing.

### "Stuck-3w+ flags items I closed last week"

Check the underlying insight in `data/insights.json` — the system flags an item as stuck when its `content_hash` (deterministic from `type + related_job + related_phase + related_sub + related_action_id`) appears in 3 consecutive weekly snapshots. If you closed the action but the underlying signal is still firing (e.g., G2 sub_drift is still computing the same TNT-on-Drummond drift), the content_hash matches and it counts as stuck. Resolution: address the underlying signal (the dragging sub), not just the action item.

### "I changed a binder JSON by hand and want to see the change"

Re-run `run_weekly.bat`. The build always re-reads `binders/*.json` and re-enriches.

### "The v1 server (localhost:8765) doesn't start"

It's archived. The Flask server at `monday-binder-v1-archive/server.py` is reference-only. To revive temporarily:

```bash
cd monday-binder-v1-archive
python server.py
```

But the rendered HTML in that folder may have broken relative paths after the move. Use v2 PDFs instead.

### "Buildertrend daily-logs are stale"

The BT scraper lives at `../buildertrend-scraper/`. To refresh:

```bash
cd ../buildertrend-scraper
node scrape-daily-logs.js
```

This is a separate Node process, not part of the Monday automation. Run it before `run_weekly.bat` if you want fresh log data.

---

## File map

```
weekly-meetings/
  run_weekly.bat                  ← Monday automation entry point
  validate_accountability.py      ← week-over-week diff
  process.py                      ← transcript ingestion (unchanged from v1)
  constants.py, fetch_daily_logs.py, weekly-prompt.md   ← shared utilities
  README.md, CHANGELOG.md, OPERATOR.md (this file)

  binders/                        ← per-PM action items (process.py output)
  binders/enriched/               ← inferred phase/sub/field-flag (build output)
  data/                           ← Phase 3 outputs + insights + commitments
  config/                         ← phase taxonomy, keywords, excluded_jobs
  transcripts/inbox/              ← drop new transcripts here
  transcripts/processed/          ← moved here after process.py
  state/                          ← processing ledger + LAST_RUN_STATUS.txt
  logs/                           ← daily + monday-run logs

  monday-binder/                  ← v2 (formerly monday-binder-v2/)
    build_meeting_prep.py
    build_pages.py
    *.template.html               ← master, executive, preconstruction, meeting-prep
    assets/                       ← styles.css + components.js + nightwork-tokens.css
    meeting-prep/                 ← rendered HTML + PDFs (output of build_meeting_prep)
      master.html / .pdf
      executive.html / .pdf
      preconstruction.html / .pdf
      pm/
        {slug}-office.html / .pdf
        {slug}-site.html / .pdf

  monday-binder-v1-archive/       ← Replaced 2026-04-30. Reference only.
    README.md (explains contents)

  generators/                     ← Phase 6+ insight generators
    g1_sequencing.py
    g2_sub_drift.py
    g3_missed_commitment.py
    enrich_action_items.py
    commitment_tracker.py
    _common.py
    run_all.py

  scripts/                        ← Phase 3 build_phase_artifacts.py
  api-responses/, exports/, print/  ← misc data
```

---

*Last updated 2026-04-30 during Phase 8 cutover.*
