# Ross Built Monday Binder — v1 archive

Replaced **2026-04-30** by `monday-binder/` (formerly `monday-binder-v2/`).
Read-only, retained for reference. Do not modify.

## What v1 was

The first production Monday meeting system, shipped 2026-04-27. A Flask
server at `localhost:8765` rendered a single Slate Light HTML page
(`monday-binder.html`) containing every PM's binder. `email_sender.py`
drove Edge headless to print per-PM PDFs and dropped them into Outlook
draft emails.

## What's in here

### Python (rendering layer)
- `email_sender.py` — Outlook COM draft flow + Edge `Page.printToPDF` per PM
- `generate_monday_binder.py` — renders `monday-binder.html` with the 9-section meeting flow
- `server.py` — Flask app on port 8765, hosts the binder + `/ledger` endpoint

### Rendered output (snapshots from final v1 run, 2026-04-29 10:36)
- `monday-binder.html` — master binder page
- `pm-packet-{bob-mozine,jason-szykulski,lee-worthy,martin-mannix,nelson-belanger}.html` — per-PM packets
- `meeting-playbook.html` — meeting flow guide

### Entry points
- `start-monday.bat` — server launcher
- `run-weekly.bat` — weekly transcript-processor launcher (called `process.py`)
- `Monday Binder.lnk` — desktop shortcut to `start-monday.bat`

### Docs
- `QUICKSTART.md` — v1 setup guide

## What v1 left behind (still at project root, used by v2)

- `process.py` — transcript ingestion → `binders/*.json` (upstream of both v1 and v2)
- `constants.py` — PM/job mappings
- `fetch_daily_logs.py` — daily-logs utility
- `weekly-prompt.md` — prompt loaded by `process.py` for transcript processing
- `binders/`, `data/`, `config/`, `transcripts/`, `state/`, `logs/` — shared data

## Why archived, not deleted

The Monday cycle (transcript → binder JSON) is unchanged — only the
*rendering layer* moved to v2's multi-audience views. The v1 HTML output
is a useful reference for "what the binder looked like before the
schedule-intelligence layer." The Flask server is a useful reference for
how the ledger endpoint worked.

If you want to revive the v1 server temporarily, set `cd
monday-binder-v1-archive` and run `python server.py`. Note the rendered
HTML files reference relative paths that may not resolve after the move.
