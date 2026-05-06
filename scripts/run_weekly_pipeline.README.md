# scripts/run_weekly_pipeline.py — operator notes

One command runs the full Monday Binder pipeline end-to-end:

```
cd C:\Users\Jake\weekly-meetings
python scripts/run_weekly_pipeline.py
```

That single command runs (in dependency order): `process.py` → `.planning/.../classifier.py` → `scripts/build_phase_artifacts.py` → `scripts/build_sub_phase_rollups.py` → `generators/run_all.py` → `monday-binder/build_meeting_prep.py` → `validate_accountability.py`. It then kills the existing dashboard server on port 8765, relaunches it so the new templates and data are live, and fetches `http://localhost:8765/meeting-prep/executive.pdf` to confirm the URL serves a freshly-rendered PDF (CreationDate within seconds of "now"). Total runtime is ~20–60 seconds depending on whether `process.py` calls the Anthropic API. The script aborts on the first step failure, leaves `data/` in whatever state that step produced (no auto-rollback), and prints a final report ending with either `READY FOR MONDAY` (exit 0) or `NEEDS ATTENTION: <reason>` (exit 1). Tunable thresholds live in `config/thresholds.yaml` under the `weekly_pipeline:` block. The legacy `run_weekly.bat` is unchanged and remains the Task-Scheduler entry point until retired.

## Manual-input checklist (do these BEFORE running)

- [ ] **Buildertrend scrape ran recently.** Open `C:\Users\Jake\buildertrend-scraper\data\daily-logs.json` and check the top-of-file `lastRun` timestamp. The pipeline warns if it's > 24 h old and aborts if it's > 168 h (1 week) old. Re-run the scraper if needed; it's a separate repo.
- [ ] **Transcripts in inbox (only if you have new ones).** Drop weekly meeting transcripts into `transcripts/inbox/` using the `MM-DD_<PMFirstName>_<Type>.txt` filename convention (e.g., `04-23_Nelson_Office.txt`, `04-23_Lee_Site.txt`). If the inbox is empty the pipeline still runs cleanly — `process.py` no-ops and the existing `binders/<PM>.json` files are reused for downstream steps.
- [ ] **`ANTHROPIC_API_KEY` set** *only if there are transcripts in the inbox*. The pipeline aborts pre-flight if the inbox is non-empty and the env var is missing. Set with `setx ANTHROPIC_API_KEY "sk-ant-..."` (then close + reopen the shell). If the inbox is empty, no key is needed.
- [ ] **All five PM binder files exist.** `binders/Bob_Mozine.json`, `binders/Jason_Szykulski.json`, `binders/Lee_Worthy.json`, `binders/Martin_Mannix.json`, `binders/Nelson_Belanger.json`. The pipeline aborts if any is missing. The required PM list lives in `config/thresholds.yaml` → `weekly_pipeline.required_pms`.
- [ ] **Microsoft Edge installed** (used by the dashboard for PDF rendering — `render_helpers.find_edge()` looks for it on disk). Pre-flight prints a WARN if not found; the URL-verification step will fail without it.

## Known things the orchestrator surfaces but does not fix

- **Hardcoded `TODAY = date(2026, 4, 29)`** in `scripts/build_phase_artifacts.py` and `scripts/build_sub_phase_rollups.py`. Outputs are stamped `today=2026-04-29` regardless of the actual run date. Tracked as a separate ticket; the orchestrator just flags it in the final report.
- **Dual-write of `data/derived-phases-v2.json`** by step 3 (`build_phase_artifacts.py`) and step 4 (`build_sub_phase_rollups.py`). Strict step ordering in the orchestrator masks the underlying duplication. Surfaced in the report's notes section every run.
- **`classifier.py` lives in `.planning/`** rather than `scripts/`. The orchestrator invokes it from there. Relocation is backlogged.

## When something looks wrong

The final report tells you the failed step, exit code, and last 15 lines of stderr. The full log is on stdout (redirect to a file with `> logs\monday-run-YYYYMMDD.log` if you want a permanent copy — the orchestrator does not auto-log). Check `state/LAST_RUN_STATUS.txt` for the legacy `run_weekly.bat` status; the new orchestrator does not touch that file.
