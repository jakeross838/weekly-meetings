# m02 — Schedule Intelligence — Milestone Summary

**Status:** Shipped 2026-04-30. Locked. Subsequent schedule-intelligence work moves to `m03-schedule-generation`.

## What shipped

A new layer on top of the v1 Monday Binder that analyzes Phase 3 schedule data, generates four classes of insights, and renders meeting-ready PDFs for five distinct audiences.

```
v1 (archived)                      v2 (now monday-binder/)
─────────────────────────          ─────────────────────────
process.py — transcripts → binders/    (UNCHANGED — upstream of both)
                  │
                  ▼
binders/*.json (PM action items)
                  │
                  ▼                ┌────────────────────────────┐
generate_monday_binder.py          │ scripts/build_phase_artifacts.py
   → monday-binder.html            │   → data/phase-instances-v2.json
   → pm-packet-{slug}.html         │     data/phase-medians.json
                                   │     data/sub-phase-rollups.json
                                   │     data/job-stages.json
                                   │     data/bursts.json
                                   └────────────────────────────┘
                                                  │
                                                  ▼
                                   generators/{g1,g2,g3,enrich,…}.py
                                     → data/insights.json
                                     → binders/enriched/*.json
                                     → data/meeting-commitments.json
                                                  │
                                                  ▼
                                   monday-binder/build_meeting_prep.py
                                     → meeting-prep/master.html
                                     → meeting-prep/executive.html
                                     → meeting-prep/preconstruction.html
                                     → meeting-prep/pm/{slug}-{office,site}.html
                                     → 13 PDFs total (Edge headless)
```

## Phases shipped

| Phase | Name                                | Output |
|-------|-------------------------------------|--------|
| 00    | Mockups                             | Reference design sketches |
| 01    | Sub-reclassification                | Refined sub × phase classifier |
| 02    | Build sequence                      | Phase taxonomy ordering |
| 03    | Duration math                       | Phase 3 data layer (instances, medians, rollups, bursts, job-stages) |
| 04    | Phase Library View                  | `monday-binder/phase-library.html` |
| 05    | Job Page Rebuild                    | `monday-binder/jobs.html` |
| 06    | Generators + Meeting Prep MVP       | G1/G2/G3 generators + first per-PM HTML packets |
| 06.5  | Meeting Prep Polish                 | Checklist redesign · 4 open-item fixes (data-quality bucket, type quotas, enrichment confidence, FieldCrew filter) · conversational asks |
| 06.6  | Multi-audience Views                | 5 page types (Master/Executive/Preconstruction/PM-office/PM-site) + accountability loop + Nightwork visual mirror |
| 8     | Cutover                             | v1 archived to `monday-binder-v1-archive/`. v2 promoted to `monday-binder/`. Local Monday automation. m03 stub. |

(Phase 7 was originally scoped as Schedule Builder but deferred — see "Deferred to m03" below.)

## Key artifacts

### Code
- `monday-binder/` — v2 production system (renamed from monday-binder-v2/ in Phase 8)
  - `build_pages.py` — Phase Library + Jobs renderer
  - `build_meeting_prep.py` — 5-audience meeting-prep renderer
  - `meeting-prep.template.html` — PM template (office | site view-mode)
  - `master.template.html`, `executive.template.html`, `preconstruction.template.html`
  - `assets/styles.css`, `assets/components.js`, `assets/nightwork-tokens.css`
- `generators/` — insight generators + commitment tracker
  - `g1_sequencing.py` (sequencing_risk + sequencing_violation, 90-day recency filter, data_quality bucket)
  - `g2_sub_drift.py` (sub × phase × job density vs sub baseline, threshold=0.20, jobs_performed >= 3)
  - `g3_missed_commitment.py` (DONE + field-confirmation window [-21, +7])
  - `enrich_action_items.py` (phase + sub inference with 0.7 confidence threshold)
  - `commitment_tracker.py` (week-over-week persistence, 3-week stuck detection)
  - `_common.py` (shared loaders, INSIGHT factory, sub/phase matchers, excluded_jobs filter)
  - `run_all.py` (orchestrator)
- `validate_accountability.py` — week-over-week diff report
- `run_weekly.bat` — Monday automation entry point
- `config/excluded_jobs.yaml` — FieldCrew filter

### Data
- `data/insights.json` — 153 insights (77 field bucket, 76 data_quality)
- `data/meeting-commitments.json` — week-over-week snapshot, 21 commitments captured for 2026-W18
- `data/accountability-week-{iso_week}.md` — auto-generated weekly report

### Outputs
- 13 PDFs in `monday-binder/meeting-prep/` (Master, Executive, Preconstruction + PM × 2 modes)
- All within 1-2 page target

## Known limits

1. **Sequencing_violation classification noise (76 items in data_quality bucket)** — these are predecessor phases with zero log entries on a job whose successor is complete. They're useful as classifier signal but not actionable for meetings. They're print-hidden by design.
2. **Enrichment heuristic is regex-based** — single-word keyword matches (e.g., "putty", "railing") penalized to 0.65 confidence (below the 0.7 keep threshold) but multi-word matches (e.g., "interior stair") pass at 0.85. Catches obvious wrong-classifications but won't beat a real classifier.
3. **G3 (missed_commitment) currently fires 1 insight at 4.2% rate** — well within the 2-20% target band. If more PMs adopt the system or transcripts get more thorough, expect this rate to climb.
4. **Watts at Fish doesn't fire G2** — kickoff prediction was speculative; actual data shows Watts is at-or-above his stucco baseline at Fish. Re-checks each Monday.
5. **Pre-construction page surfaces only 1 upcoming job (Biales)** — strict `current_stage <= 1` filter. Phase 7+ could relax to include current_stage missing.
6. **Master / executive recovery sections need 2+ runs to populate** — first-run state is empty. Phase 8 adds the Monday automation that produces the second run.
7. **Nightwork visual mirror has not been visually inspected in Acrobat** — verified in browser screenshot (palette, fonts, square corners, no overflow). Acrobat may render minor differences in font kerning or color profile. Confirm before next Monday's print run.

## Deferred to m03 (or later)

The following were scoped during m02 but punted to `m03-schedule-generation`:

- **Generator 4 — stage-should-be-doing** (requires size-class baselines)
- **Generator 7 — schedule reality check** (requires per-phase scheduled dates)
- **Schedule Builder (plan-aware)** — original Phase 7 scope. Building from historical medians is the wrong foundation; schedules need to be plan-aware (size, scope, specs).
- **Log inference for missed days** — fill in days where field activity happened but no log was filed
- **Size-class baselines** — different schedule expectations for 4k vs 8k vs 14k sqft

The following stay in their original Phase 9 home (within m02 if revived, or moved to m03):

- **Generator 5** — transcript pattern detection
- **Generator 6** — Markgraf-lesson triggers (one-off lesson encoding)

## Production cadence

See `OPERATOR.md` at the project root for the operating manual.

Weekly cycle:
1. **Monday before 8am ET** — `run_weekly.bat` fires (Task Scheduler) → builds packets + writes accountability report
2. **Monday morning** — PMs review their `pm/{slug}-office.pdf` packet, run their meetings
3. **During meeting** — PMs mark commitments / new items / closures
4. **Tuesday** — Jake processes transcripts via `process.py` (not yet automated)
5. **Next Monday** — automation diffs against last week's snapshot, surfaces resolved/carried/stuck items

## Deferred automation decisions

### process.py Tuesday automation — KEEP MANUAL (decided 2026-05-01)

**Verdict: (b) review-before-PM-impact, with (a) cost as a secondary consideration. Stay manual until the guardrails listed below land.**

#### Evidence reviewed

- **Extraction reliability** — `state/processing-ledger.jsonl`: 18 records over 2026-04-23 → 2026-04-28, **0 errors**, 0 validation failures. process.py already runs `validate_binder()` before save.
- **Binder quality** — sampled `binders/Bob_Mozine.json` (42 items): 0 short-actions (<20 chars), 0 missing owner, 0 missing due, 0 bad status, 0 bad priority. Action items pass the v1 prompt's "Monday Morning Test" cleanly.
- **API cost** — Claude Opus 4.7 at `MAX_TOKENS=32000`, streaming. Roughly $0.50-1.00 per transcript × ~5/week ≈ $10-25/month. Not material as a constraint.

#### Why manual gating is still right

The technical pipeline is reliable, but the *output destination* is high-leverage:

> Action items go directly into `binders/{PM_Last}.json` → next Monday's `build_meeting_prep.py` reads them → 13 PDFs distributed to 4 audiences.

A bad extraction (e.g., misread "Bob" as "Bill", wrong job, fabricated commitment) surfaces in PM-facing PDFs Monday morning. Highly visible, hard to retract, erodes trust.

The current manual step exists to give Jake a beat to:
1. Run `process.py` while watching the diff
2. Spot-check the new items before they go to print
3. Catch transcript-level issues (Plaud audio dropout, speaker confusion, partial recordings)

These are **review concerns**, not automation-readiness blockers. The pipeline could absolutely run on a Tuesday cron — it's the "what if it's wrong and I didn't catch it before Monday" risk that justifies the manual gate.

#### What would need to change before safe automation

A Tuesday `process.py` cron is safe to wire when these guardrails are in place:

1. **Pre-save diff** — `process.py` should print/save a summary of what changed (new items added, items modified, items closed) before writing the binder. Currently it overwrites. Diff lives in `state/binder-diffs/{PM}-{date}.diff` for review.
2. **Low-confidence quarantine** — items where the LLM left `?` markers or the update field is empty get held in `binders/quarantine/` and surface in the Monday packet as "REVIEW: extracted item awaiting confirmation."
3. **Notification on change volume spike** — if a single transcript produces >10 new items or >5 modifications, email/Slack Jake before saving.
4. **One-click rollback** — `backup_binder()` already exists in process.py. Expose a `python process.py --revert {PM} {date}` flag so a bad extraction can be undone without git.
5. **Anthropic API cost cap** — environment var `ANTHROPIC_WEEKLY_BUDGET_USD` (default $50). Process.py tracks weekly spend in `state/api-usage.json` and skips with a clear error if the cap is hit. Mostly a defense against accidental loops, not a primary cost concern.

#### When to revisit

Revisit this decision after one of:
- 4 consecutive Mondays where Jake's manual review caught zero issues (signal: review is no longer adding value)
- The first incident where a bad extraction reaches PMs (signal: review caught a real one, raise the bar)
- Plan ingest lands and the process.py role expands (signal: bigger system, time to design the guardrails properly)

Until then, OPERATOR.md correctly says "Tuesday — Jake processes transcripts via process.py (not yet automated)."

---

## Files moved during Phase 8 cutover (2026-04-30)

Archived to `monday-binder-v1-archive/`:

- `email_sender.py`
- `generate_monday_binder.py`
- `server.py`
- `monday-binder.html`
- `pm-packet-{bob-mozine,jason-szykulski,lee-worthy,martin-mannix,nelson-belanger}.html`
- `meeting-playbook.html`
- `start-monday.bat`
- `run-weekly.bat` (v1 entry point — replaced by `run_weekly.bat` at root)
- `Monday Binder.lnk`
- `QUICKSTART.md` (replaced by `OPERATOR.md`)

Renamed:
- `monday-binder-v2/` → `monday-binder/`
- `monday-binder/build_pages.py:14` and `monday-binder/build_meeting_prep.py:42` updated `OUT = ROOT / "monday-binder-v2"` → `OUT = ROOT / "monday-binder"`

Stayed at project root (shared upstream of both v1 and v2):
- `process.py`, `constants.py`, `fetch_daily_logs.py`, `weekly-prompt.md`
- `requirements.txt`, `README.md`, `CHANGELOG.md`, `OPERATOR.md`
- All data directories (`binders/`, `data/`, `config/`, `transcripts/`, `state/`, `logs/`, etc.)

Created:
- `run_weekly.bat`
- `validate_accountability.py`
- `monday-binder-v1-archive/README.md`
- `state/LAST_RUN_STATUS.txt` (single-line status from each Monday run)
