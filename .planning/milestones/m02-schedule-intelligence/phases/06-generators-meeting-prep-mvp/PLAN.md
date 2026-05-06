# Phase 6 — Generators 1/2/3 + MVP Meeting Prep

Phase 4+5 shipped clean. Two new threads opened upstream (log inference, schedule realism) — both deferred to a future milestone after plan data lands. Phase 6 ships with 3 generators, not 4.

## Scope change from original spec

- **Generator 4 (stage-should-be-doing) deferred** to future milestone `m03-schedule-generation`. Requires size-class baselines we don't have yet.
- **Generator 7 (schedule reality check) deferred** to same future milestone. Today's BT schedules are placeholder, not ground truth.
- **Phase 6 ships with Generators 1, 2, 3** + MVP Meeting Prep page.

Generators 5 (transcript pattern), 6 (Markgraf-lesson triggers) stay in their original Phase 9 home.

## Goal

Three generators producing INSIGHT records that surface in an MVP Meeting Prep page. Insights cite evidence. PMs walk into meetings with a ranked top-5 talking points.

## Inputs

- All Phase 3 data (instances, medians, rollups, bursts, job-stages)
- Existing per-PM action item JSON binders (location TBD by Claude Code — search for them)
- Existing meeting transcript JSON exports if present (search; if missing, Generator 3 runs degraded)

## Generator 1 — Sequencing Risk

For every job's ongoing phase, check if a successor is scheduled OR has logs already AND the predecessor isn't actually done.

```
IF phase_X.status = "ongoing"
  AND phase_X.primary_density < 0.65
  AND ANY successor phase has logs OR has scheduled date within (median_active_days_X * 1.2) days
THEN INSIGHT(
  type: "sequencing_risk",
  severity: warn|critical (critical if successor already started),
  message: "[X] dragging at [density]%. Successor [Y] [scheduled/started]. Risk of overlap.",
  evidence: [phase: X, phase: Y, schedule: Y.start],
  ask: "Confirm sub for X. Decide whether to hold Y or stage parallel."
)
```

Also fire when a phase shows complete but predecessor has zero log entries (taxonomy violation):

```
IF phase_X.status = "complete"
  AND ANY predecessor phase has zero logs AND zero scheduled date
THEN INSIGHT(
  type: "sequencing_violation",
  severity: warn,
  message: "[X] complete but predecessor [W] has no logs. Likely classification miss or skipped scope.",
  evidence: [phase: X, phase: W],
  ask: "Verify [W] was performed or update taxonomy."
)
```

## Generator 2 — Sub Performance Drift

Compare current job's sub-phase density to that sub's overall median for that phase across all their jobs.

```
FOR each (sub × phase × job) where status in [ongoing, complete] AND sub.jobs_for_phase >= 3:
  current = primary_density on this job
  baseline = sub's median primary_density across all their jobs for this phase
  
  IF current < baseline - 0.20:
    INSIGHT(
      type: "sub_drift",
      severity: warn,
      message: "[Sub] running [current]% on [phase] at [job], vs their typical [baseline]%.",
      evidence: [phase: X@job, sub-phase-rollup: Sub × X],
      ask: "Ask PM what changed. Sub issue or job-specific?"
    )
```

This is the cross-data signal — "Watts is below his own baseline on this job." Different from "Watts is below industry average" — that's Generator 1's territory via vs_phase_median.

## Generator 3 — Missed Commitment

For action items closed in last 14 days, verify field activity backs them up.

```
FOR each action_item where status changed to DONE in last 14 days
  AND action_item.requires_field_confirmation = true:
  
  Check if any daily log entry references the related sub or phase 
  in the [DONE date - 7 days, DONE date + 7 days] window.
  
  IF zero matching log entries:
    INSIGHT(
      type: "missed_commitment",
      severity: warn,
      message: "Item [ID] marked DONE [date] but no field activity confirms.",
      evidence: [action: ID, log: window-empty],
      ask: "Verify in field. Was [item description] actually completed?"
    )
```

If action items don't have `requires_field_confirmation` or `related_sub` / `related_phase` fields, run a lightweight one-time enrichment pass: for every existing action item, infer phase/sub from item text + job context. Save enriched binders alongside originals (don't overwrite). Mark inferred fields as `inferred=true` so PMs can see what was guessed.

If enrichment can't infer with confidence, skip that item (don't run Generator 3 on it).

## MVP Meeting Prep page

One HTML page per PM, generated on demand. Save to `monday-binder-v2/meeting-prep/{pm_slug}.html`.

```
┌─ NELSON BELANGER · MEETING PREP · MONDAY 2026-04-29 ────────────┐
│ Jobs: Clark, Markgraf · Last meeting: 2026-04-22 (7d ago)       │
│                                                                 │
│ ━━━ THIS WEEK'S MUST-DISCUSS (top 5) ━━━                        │
│                                                                 │
│  1. ⚠ MARKGRAF · Punch dragging — TNT below baseline            │
│     EVIDENCE: phase:15.2 active=23d density=53% | sub-rollup:   │
│       TNT median 71% across all jobs | log-window: 4d in 14d    │
│     ASK: "Is TNT pulling crew, or is the punch list shrinking?" │
│                                                                 │
│  2. ⚠ CLARK · 2.1 Pilings still ongoing, 2.2 has logs           │
│     EVIDENCE: phase:2.1 status=ongoing | phase:2.2 first log    │
│       2026-04-15 | predecessor not complete                     │
│     ASK: "Pile caps started before pilings done?"               │
│                                                                 │
│  3. ⚠ MARKGRAF · MK-014 Smarthouse marked DONE no field         │
│     EVIDENCE: action:MK-014 closed 2026-04-22 |                 │
│       log-window: zero Smarthouse logs 2026-04-15 to 2026-04-29 │
│     ASK: "Was Smarthouse actually here Friday?"                 │
│                                                                 │
│  4-5. ...                                                       │
│                                                                 │
│ ━━━ ALL OPEN INSIGHTS (this PM, by severity) ━━━                │
│  [grouped list of every insight scoped to this PM's jobs]       │
│                                                                 │
│ ━━━ ACTION ITEMS (this PM, by aging) ━━━                        │
│  [from existing per-PM JSON binder, sorted by aging]            │
│                                                                 │
│ ━━━ COMMITMENTS FROM LAST MEETING (closure check) ━━━           │
│  [done / suspect (G3 fired) / wip]                              │
└─────────────────────────────────────────────────────────────────┘
```

Build a per-PM page for each PM with active jobs (Nelson, Bob, Martin, Jason, Lee Worthy).

## Step order

1. **Build INSIGHT data structure** — one JSON file: `data/insights.json`. Schema: id, type, severity, scope, message, evidence[], ask, generated_at, status (default open), related_job, related_pm, related_phase, related_sub
2. **Build Generators 1, 2, 3** as separate Python modules under `generators/`. Each generator reads Phase 3 data + writes to insights.json
3. **Run all three generators**. Output total insights generated, by type, by severity, by PM
4. **Build Meeting Prep HTML template** — same scaffold/style as Phase 4+5 pages
5. **Render one page per active PM**
6. **Write VERIFICATION.md**

## Verification (paste-back required)

1. **Insights generated** — total count, breakdown by type/severity/PM
2. **Top 10 insights** across the company, full text + evidence + ask. Sanity check: do they match field reality? Watts at Fish should fire G1+G2. Markgraf punch should fire G1.
3. **Generator 3 stats** — action items checked, % requiring field confirmation, % flagged as missed commitment. If <2% flagged, Generator 3 may be too lax. If >20%, too aggressive.
4. **Nelson's Meeting Prep page** — paste full rendered content. Confirm 5 must-discuss items ranked correctly, evidence cites real records, asks are specific
5. **Bob's Meeting Prep page** — same paste, different PM (multiple jobs, different ratio of generators firing)
6. **Insight noise check** — for the top 20 insights, would each one change a meeting decision? If <70% would, generators need tuning before Phase 7

## Stop conditions

Phase 6 ships when:
- All 3 generators run without errors
- Meeting Prep pages render for all active PMs
- Top 20 insights pass the noise check (≥70% would change a decision)
- Generator 3 flagged rate is in 2-20% band

If insights are noisy or PMs would ignore them, stop and tune. Don't ship a system PMs won't trust.

## Standing rules

- v2 paths only
- Insights are append-only — re-running generators creates new insight records, doesn't overwrite (status field tracks acknowledgment)
- Every insight cites evidence from real records (no synthesized references)
- Print-legible
- Defer Gen 4, 5, 6, 7 — explicitly note these are not in scope for Phase 6

Begin.
