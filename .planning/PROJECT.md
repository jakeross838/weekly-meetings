# Ross Built — Weekly Meetings System

## What this is
A PM meeting orchestration system for Ross Built's project managers. Turns Buildertrend daily logs, Plaud meeting transcripts, action-item binders, and BT job data into a Monday morning binder + per-PM meeting packets.

Currently shipped (v1):
- Flask server on port 8765 (`server.py`)
- `process.py` — transcript → Claude Opus 4.7 → per-PM JSON binders
- `generate_monday_binder.py` — renders `monday-binder.html` (Slate Light design system)
- `email_sender.py` — Outlook COM draft flow with PDF attachments
- 9-section meeting flow (open items, last-2-weeks, site activity, heads-up, look-ahead, issues, financial)
- 5 PMs, ~12 active jobs, ~250+ subs in the daily-logs corpus

## Active milestone
**m02 — Schedule Intelligence** (`.planning/milestones/m02-schedule-intelligence/`)
Unifies the four data silos (logs / transcripts / action items / job data) into a single intelligence layer with: rebuilt sub classifier from log description text, canonical 15-stage build sequence, burst+density duration math, insight engine, rebuilt views, Schedule Builder, Meeting Prep view. Powers binders, meeting prep, and downstream schedule generation — not just a binder rebuild.

Output goes to `monday-binder-v2.html` alongside the v1 system. v1 stays live until cutover (Phase 10).

## Reference data
- `C:\Users\Jake\buildertrend-scraper\data\daily-logs.json` — canonical crew names (`crews_clean` arrays) and parent_group_activities tags
- `binders/*.json` — per-PM action-item state
- `transcripts/processed/` — historical Plaud transcripts (audited via processing-ledger.jsonl)

## Standing rules
- v1 stays live; do not modify until Phase 10 cutover
- Recalculate, don't increment — every phase reads source data
- Org-configurable, not hardcoded — phase keywords, density tiers, burst gap days, aging windows in config files
- Backward-compatible action-item JSON schema (additive migrations only)
- Print-legible — density flags carry text labels, not emoji-only
- Every insight cites evidence (log/transcript/phase reference)
