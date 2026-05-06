# Monday Binder Rebuild — Unified Intelligence Pass (FINAL)

## What we're actually building

Ross Built has four data sources that today live in separate silos:

1. **Daily logs** (Buildertrend) — who was on site, when, doing what
2. **Meeting transcripts** (Plaud, processed weekly per PM) — commitments, blockers, client items, sub issues
3. **Action items / open issues** (per-PM JSON binders) — typed, aged, prioritized
4. **Job data** (BT schedule, contract values, CO targets, PM assignments)

Right now each one runs its own pipeline and the Monday Binder shows them as separate sections. They don't talk to each other. That's the failure.

This rebuild fuses all four sources into a single intelligence layer that does three things:

1. **Builds accurate schedules** from historical phase/sub/density data
2. **Runs PM meetings predictively** — surfaces watch-outs, missing commitments, sequencing risks before the meeting starts
3. **Gets smarter every week** — every transcript, every log, every closed action item feeds the next one

The deliverable is one rebuilt binder system where every page reads from the unified data model. No more "the analytics page" vs "the meeting page" vs "the open items page." They're three views of the same brain.

---

## PART 1 — Unified data model

Build one normalized data layer that all views read from. Every record links to every other relevant record.

### Core entities

```
JOB
  id, name, address, contract_value, pm, current_stage, co_target_date

PHASE_INSTANCE
  id, job_id, phase_code (e.g. "6.1 Plumbing Top-Out"), 
  status (complete|ongoing|scheduled|not_started),
  active_days, span_days, density, burst_count,
  predecessor_phase_codes[], successor_phase_codes[]

DAILY_LOG_ENTRY
  id, job_id, date, sub_id, derived_phase_code, 
  description, notes, person_count,
  classification_confidence (high|low_review)

SUB
  id, name, derived_phases[] (with avg active days, density, reliability per phase),
  overall_density, overall_reliability,
  current_active_jobs[]

ACTION_ITEM
  id, job_id, pm, owner, type (SELECTION|CONFIRMATION|PRICING|SCHEDULE|CO_INVOICE|FIELD|FOLLOWUP),
  action_text, status (TODO|IN_PROGRESS|BLOCKED|DONE),
  priority (URGENT|HIGH|NORMAL),
  opened, due, closed_date,
  days_open, aging_flag (fresh|aging|stale|abandoned),
  source_transcript_id (which meeting it came from),
  related_phase_code (if applicable),
  related_sub_id (if applicable)

MEETING_TRANSCRIPT
  id, job_id, pm, date, type (office|site),
  raw_text, processed_summary,
  extracted_action_items[], extracted_commitments[],
  extracted_subs_mentioned[], extracted_phases_mentioned[],
  client_sentiment, sub_sentiment[]

INSIGHT (the new entity — the unified output)
  id, generated_at, scope (job|pm|company|sub|phase),
  type (watchout|risk|missed_commitment|sequencing|sub_dragging|client_signal|opportunity),
  severity (info|warn|critical),
  message, evidence[] (links to logs, transcripts, action items, phase data),
  suggested_talking_point (for next meeting),
  status (open|acknowledged|resolved)
```

### Why INSIGHT is the centerpiece

Today, every data source produces its own output (PPC%, action item count, sub-on-site days). None of them produce a *deduction*. The INSIGHT entity is where the system says:

> "Stucco Fish has been ongoing 45 days at 35% density. Watts mentioned 'staffing issues' in 3 of last 4 transcripts. Drywall hang is scheduled to start in 12 days. RISK: stucco won't finish before drywall is supposed to start. SUGGESTED TALKING POINT: confirm Watts crew size for next week, hold drywall start until brown coat passes."

That's not in any current view. That's what we're unlocking.

---

## PART 2 — Sub classification (rebuild from log descriptions)

Every sub's trade(s) get re-derived from log description text, not from the existing category tags.

### Method

1. For every daily log entry, read the **activity description**, **notes**, and **comment** fields. Activity tags lie; description text tells the truth.
2. Match against the phase keyword library (Part 3). The keyword that matches the action verb + material wins.
3. Assign each log entry a `derived_phase_code`. A sub can have multiple derived phases across history.
4. Filter out non-subs entirely (utilities, scraper artifacts, credit cards).

### Concrete fixes Jake called out

- **CoatRite LLC** = Waterproofing (NOT Masonry). They waterproof stem walls, foundations, shower pans. Every "Masonry Walls" log for them retags to `2.4 Stem Wall Waterproofing` or `10.1 Wet Area Waterproofing`.
- **ML Concrete LLC** = pilings, foundation, slabs, masonry walls, CIP beams.
- **Jeff Watts Plastering** = stucco scratch + brown + finish. Multiple bursts per job.
- **Metro Electric** = electrical rough + trim + low voltage on some jobs. Three derived phases.
- **Gator Plumbing** = plumbing rough + trim + gas. Three derived phases.
- **Ross Built Crew** = tag per log entry, never bucket as one trade.
- **DB Welding** = metal fab + stair railings + custom hoods.
- **Rangel Custom Tile** = interior tile + wood flooring on some jobs.
- **M&J Florida Enterprise** = siding + framing + exterior ceilings (per log).
- **ALL VALENCIA** = framing + windows + siding (per log).

### Filter list (remove entirely from subs view)

`PilingsFoundation`, `Plan Review`, `Plan ReviewEstimating`, `Plan ReviewPre-Construction`, `Documents`, `1Passed.Inspection for Framing`, `Yes`, `Multi-sub days (not solo-attributable)`, `City of Anna Maria - Building Department`, `Town of Longboat Key`, `City Of Sarasota` (move to `external_entities` for inspection tracking), `FPL`, `TECO Peoples Gas-Shepard` (utilities — separate `utilities` entity), `Sunbelt Rentals` (equipment), `American Express Simply Cash Business CC`.

### QA output (paste back before applying)

Print the full reclassification diff: sub × log entry × old phase × new phase × sample description text. I want to spot-check CoatRite, ML Concrete, M&J, ALL VALENCIA, Ross Built Crew before it's permanent.

---

## PART 3 — Canonical 15-stage build sequence (the spine)

Every page reads in this order. Stem Wall Waterproofing sits between stem walls and slab. Floor trusses come after tie beams. Roof trusses set after the second-level shell completes.

### Master phase sequence

```
STAGE 1 — PRE-CONSTRUCTION & SITE
  1.1 Permits & Plan Review
  1.2 Site Clearing / Demo
  1.3 Temporary Fencing & Erosion Control
  1.4 Site Grading & Pad Prep
  1.5 Surveying & Layout

STAGE 2 — FOUNDATION
  2.1 Pilings (drilled / driven)
  2.2 Pile Caps & Grade Beams
  2.3 Stem Walls
  2.4 Stem Wall Waterproofing                  ← CoatRite
  2.5 Under-Slab Plumbing Rough
  2.6 Under-Slab Electrical (if any)
  2.7 Slab Prep (vapor barrier, rebar, inspection)
  2.8 Slab Pour

STAGE 3 — STRUCTURAL SHELL (per level)
  3.1 Masonry Walls (CMU)
  3.2 Wall Reinforcement & Cell Fill
  3.3 Tie Beams (CIP)
  3.4 Floor Truss / Floor System Set            ← framers, after 3.3
  3.5 Floor Sheathing
  3.6 Repeat 3.1–3.5 for next level
  3.7 Roof Truss Set
  3.8 Roof Sheathing
  3.9 Hurricane Strapping & Tie-Down Inspection

STAGE 4 — DRY-IN
  4.1 Roofing Underlayment
  4.2 Roofing Final
  4.3 Exterior Windows
  4.4 Exterior Doors

STAGE 5 — EXTERIOR ROUGH
  5.1 Exterior Wall Sheathing & Wrap
  5.2 Exterior Decking Framing
  5.3 Exterior Stair Framing

STAGE 6 — MEP ROUGH-IN
  6.1 Plumbing Top-Out
  6.2 Gas Rough
  6.3 Electrical Rough
  6.4 HVAC Rough
  6.5 Low Voltage Rough
  6.6 Fire Sprinkler Rough (if applicable)
  6.7 MEP Inspections

STAGE 7 — ENVELOPE CLOSE-UP
  7.1 Stucco Lath / Wire
  7.2 Stucco Scratch Coat
  7.3 Stucco Brown Coat
  7.4 Siding Install
  7.5 Soffit / Exterior Ceilings
  7.6 Stucco Finish Coat
  7.7 Exterior Trim & Bandings

STAGE 8 — INSULATION & DRYWALL
  8.1 Insulation
  8.2 Drywall Hang
  8.3 Drywall Tape & Mud
  8.4 Drywall Texture / Finish
  8.5 Prime Walls

STAGE 9 — INTERIOR ROUGH FINISH
  9.1 Interior Stair Framing & Treads
  9.2 Interior Trim Carpentry
  9.3 Interior Doors Hung

STAGE 10 — TILE & STONE
  10.1 Wet Area Waterproofing                    ← CoatRite
  10.2 Floor Tile / Wood Flooring
  10.3 Wall Tile
  10.4 Stone / Slab Install

STAGE 11 — CABINETRY & STONE TOPS
  11.1 Cabinet Install
  11.2 Countertop Template
  11.3 Countertop Install
  11.4 Backsplash Install

STAGE 12 — INTERIOR PAINT
  12.1 Caulk & Putty
  12.2 Paint Walls
  12.3 Paint Trim & Doors

STAGE 13 — MEP TRIM
  13.1 Plumbing Trim
  13.2 Gas Trim
  13.3 Electrical Trim
  13.4 HVAC Trim
  13.5 Low Voltage Trim
  13.6 Appliance Install

STAGE 14 — EXTERIOR FINISH
  14.1 Exterior Paint
  14.2 Exterior Decking Finish
  14.3 Driveway / Hardscape
  14.4 Exterior Pavers / Walkways
  14.5 Pool Shell / Plumbing
  14.6 Pool Tile & Coping
  14.7 Pool Plaster / Pebbletec
  14.8 Pool Equipment & Startup
  14.9 Final Fencing / Gates
  14.10 Landscaping
  14.11 Irrigation

STAGE 15 — CLOSEOUT
  15.1 Punch Walk & List
  15.2 Punch Repairs
  15.3 Final Cleaning
  15.4 Final Inspections
  15.5 C.O. Issuance
  15.6 Owner Walk & Move-In
```

### Phase keyword library

For every phase, define keyword patterns (action verb + material/element). Build the full library and **print before applying**. Examples:

- `2.4` → "waterproof" + ("stem wall" | "foundation wall" | "below grade") | "Tremco" | "Henry"
- `3.4` → "floor truss" | "floor system" | "TJI" | "I-joist" | "set joists"
- `7.2` → "scratch" + "stucco" | "first coat stucco"
- `7.3` → "brown coat" | "second coat stucco"
- `7.6` → "finish coat" | "color coat" | "texture coat"
- `10.1` → "Schluter" | "Kerdi" | "Hydroban" | "Redgard" | "shower pan waterproof"
- `15.1` → "punch list" | "punch walk" | "deficiency"

### Two-pass classification

1. **Pass 1:** description-based keyword match (high confidence)
2. **Pass 2:** for unmatched, fall back to sub's most-common derived phase × current job stage. Mark `low_confidence_match: true`.
3. Anything still unclassified → `requires_manual_review` table, excluded from analytics.

---

## PART 4 — Duration math (burst + density)

Every (sub × phase × job) combo computes:

```
active_days   = distinct workdays the sub logged this phase on this job
span_days     = workdays between first and last log
density       = active_days / span_days
```

### Burst detection

A burst is a continuous work window. Split when there's a gap of **≥6 working days** with no logged work. For phases that genuinely require multiple trips (stucco scratch/brown/finish, paint primer/finish, pool shell/plaster), expect 2–3 bursts. Show separately:

```
Stucco — Fish · 3 bursts
  Burst 1: Nov 12–Nov 26  span 11d, active 9d, density 82%   — scratch + lath
  Burst 2: Jan 8–Jan 22   span 11d, active 8d, density 73%   — brown coat
  Burst 3: Apr 8–Apr 22   span 11d, active 9d, density 82%   — finish coat
  Total active: 26d  ·  Stage span: 162d  ·  Working density: 79%
```

### Density tiers (single source of truth)

| Density | Label | Schedule implication |
|---|---|---|
| ≥80% | 🟢 Continuous | Use as baseline |
| 60–79% | 🟡 Steady | Mild buffer |
| 40–59% | 🟠 Scattered | Add 25% buffer |
| <40% | 🔴 Dragging | Don't schedule against this sub for this phase |

### Reliability (separate metric)

```
reliability = days_committed_and_showed / days_committed
```

If commit dates aren't available, use proxy: `active_days / (active_days + no_show_logged_days)`. Mark as proxy.

---

## PART 5 — The Insight Engine (the new brain)

This is the part that didn't exist before. After every nightly data refresh AND on demand before each meeting, run insight generators that cross-reference all four data sources.

### Generator 1 — Sequencing Risk

For every job's ongoing phase, check predecessors and successors:

```
IF phase_X is ongoing at density <60%
AND successor_phase_Y is scheduled to start within (median_active_days_X * 1.2) days
THEN INSIGHT: "Phase X dragging — successor Y scheduled to start before X likely completes.
              Suggested action: confirm sub for X, hold Y start, or stage parallel work."
```

```
IF phase_X is complete
AND any predecessor phase has no log entries
THEN INSIGHT: "Phase X marked complete but predecessor not logged. 
              Likely classification miss — review."
```

### Generator 2 — Sub Performance Drift

For every active sub × phase × job:

```
IF current density < (sub's historical avg density for this phase) - 20%
THEN INSIGHT: "Sub trending below their own baseline. Last 4 transcripts mention X.
              Suggested talking point: ask PM what changed."
```

### Generator 3 — Missed Commitment

For every action item closed in the last 14 days:

```
IF action_item.status changed to DONE
AND no daily log entry references the related sub or phase in the next 7 days
THEN INSIGHT: "Item marked done but no field activity confirms. 
              Ask in next meeting: was it actually completed?"
```

### Generator 4 — Stage-Should-Be-Doing

This is the one Jake specifically asked for — deduce what *should* be happening based on the build sequence:

```
FOR every active job:
  Determine current_stage from most recent ongoing phases
  Look up typical concurrent phases at this stage
  IF a typical concurrent phase has no recent logs OR no scheduled date
  THEN INSIGHT: "At this stage, [phase] typically running concurrently. 
                 No activity logged. Confirm with PM whether scheduled or behind."
```

Example: Markgraf is at Stage 15 Closeout. At this stage, owner walkthrough prep, warranty binder assembly, and final cleaning are typically concurrent with punch repairs. If there's no log activity for cleaning and the owner walk is in 7 days, INSIGHT fires.

### Generator 5 — Transcript Pattern Match

For every meeting transcript processed in the last 4 weeks, scan for:

- Sub names mentioned with negative sentiment ("not responsive," "didn't show," "behind") → cross-reference with that sub's current density on that job
- Client decisions mentioned as "pending" or "waiting on" → check if it's been raised before; flag if mentioned 3+ times
- Material/selection items mentioned with a date → check if action item exists; create one if missing
- Schedule references ("by next week," "two weeks out") → cross-reference with phase data; flag if unrealistic given sub's typical density

### Generator 6 — Markgraf-Lesson Triggers

For every active job, scan for the field mistakes that became QC checklist entries:

- Stucco scheduled before exterior paint? → fine
- Granite polish scheduled before PebbleTec? → INSIGHT (PebbleTec dust ruins polish)
- Caulk on weep holes? → check siding/stucco logs for "caulk weeps" mentions
- Railings installed before deck board cuts? → INSIGHT
- Sub non-responsiveness flagged in log notes? → escalate

This list grows. Every time a Markgraf-style lesson is captured, it becomes a generator rule.

### Generator 7 — Schedule Reality Check

For every job's BT schedule:

```
FOR each upcoming phase in next 30 days:
  Compare scheduled duration to historical median active duration for that phase
  IF scheduled < (historical_median * 0.7)
  THEN INSIGHT: "Phase scheduled tighter than historical. Watch for slip."
  IF scheduled > (historical_median * 1.5) and confidence high
  THEN INSIGHT: "Phase scheduled longer than typical. Review for opportunity to compress."
```

### Insight output

Every insight is:

```
{
  type: "sequencing_risk",
  severity: "warn",
  job: "Fish",
  message: "Stucco at 35% density, ongoing 45 days. Drywall scheduled in 12 days. 
            Successor at risk.",
  evidence: [
    "phase:7.3 active=14d span=40d density=35%",
    "transcript:2026-04-15 'Watts said two-man crew this week'",
    "phase:8.2 scheduled_start=2026-05-10",
  ],
  suggested_talking_point: "Confirm Watts crew size for next 2 weeks. 
                            Decide whether to hold drywall hang or stage rooms 
                            where stucco is complete."
}
```

These flow into PM packets, the Monday Binder, and the Meeting Prep view.

---

## PART 6 — Phase Library view (rebuilt)

Replace the entire Subs page. Build sequence is the spine. Subs nest inside.

### Filter bar

```
[ All ]  [ Pre-Con & Site ]  [ Foundation ]  [ Shell ]  [ Dry-In ]
[ MEP Rough ]  [ Envelope ]  [ Drywall ]  [ Tile ]  [ Cabinets ]
[ Paint ]  [ MEP Trim ]  [ Exterior ]  [ Closeout ]
```

### Per-phase card

```
┌─ 6.1 PLUMBING TOP-OUT ──────────────────────────────── 8 jobs ─┐
│                                                                 │
│  TYPICAL ACTIVE      9 days       (range 4–22)                  │
│  TYPICAL DENSITY     🟢 78%                                     │
│  TYPICAL SPAN        12 calendar days                           │
│  ACTIVE NOW          1 job (Dewberry, day 1)                    │
│                                                                 │
│  ┌────────────── density bar ──────────────────────┐            │
│  │  ████████████████████░░░░░  78%                  │            │
│  └──────────────────────────────────────────────────┘            │
│                                                                 │
│  TYPICAL SUBS                                                   │
│  Sub                       Active   Density   Reliability  Jobs │
│  Gator Plumbing               11d   🟢 82%    🟢 91%        7   │
│  Loftin Plumbing               5d   🟢 88%    🟢 100%       1   │
│                                                                 │
│  PRECEDED BY: 5.1 Exterior Sheathing, 4.2 Roofing Final         │
│  FOLLOWED BY: 6.3 Electrical Rough, 8.1 Insulation              │
│                                                                 │
│  ⚠ INSIGHTS (1)                                                 │
│  · Dewberry: scheduled 7d, historical median 9d. Watch for slip │
│                                                                 │
│  ▸ Per-job detail (click to expand)                             │
└─────────────────────────────────────────────────────────────────┘
```

Per-job detail when expanded shows the per-burst breakdown and density per row.

---

## PART 7 — Job page rebuild

Every job is a clean read-down of the 15-stage sequence. Every phase shown, even if not started.

### Job card layout

```
┌─ MARKGRAF · 5939 RIVER FOREST CIR ───────────────────────────────┐
│ PM: Nelson Belanger    Stage: 15 Closeout    CO target: 4/27/26  │
│                                                                  │
│  ⚠ INSIGHTS (3)                                                  │
│  · 15.2 Punch Repairs at 53% density — sub dragging              │
│  · Owner walk in 5d, no cleaning logged in 4d                    │
│  · 3 action items aged "stale" (>14d open)                       │
│                                                                  │
│  STAGE       PHASE                    STATUS      ACT  DENSITY   │
│  ──────────────────────────────────────────────────────────────  │
│  1 Site      1.4 Site Grading         ✓ complete  4d   🟢 80%    │
│  2 Found     2.3 Stem Walls           ✓ complete  1d   🟢 100%    │
│              2.4 Waterproofing        ✓ complete  3d   🟡 75%    │
│              2.7 Slab Pour            ✓ complete  1d   🟢 100%    │
│  3 Shell     3.1 Masonry 1L           ✓ complete  1d   🟢 100%    │
│              3.3 Tie Beams 1L         ✓ complete  4d   🟢 100%    │
│              3.4 Floor Trusses        ✓ complete  3d   🟢 100%    │
│  ...                                                             │
│  15 Closeout 15.2 Punch Repairs       ⏵ ongoing   23d  🟠 53% ⚠  │
│              15.5 C.O. Issuance       ▢ scheduled —    —          │
│                                                                  │
│  OPEN ACTION ITEMS (5)                                           │
│  · MK-014 Confirm Smarthouse Friday    Nelson  due 4/26  URGENT  │
│  · MK-018 First Choice cabinets touch  Nelson  due 4/24  HIGH    │
│  · ...                                                           │
└──────────────────────────────────────────────────────────────────┘
```

### Rules

- Every phase from the master sequence shown, in order, even if not started
- Insights for this job appear at the top
- Action items for this job appear at the bottom (top 10, sorted by aging × priority)
- Drop the noise: total log-days, person-days, avg crew, unique subs count, workforce histogram, top-10 subs list, latest events block. None of it builds schedules or runs meetings.

### Top-of-page strip — "What's running today"

```
ACTIVE PHASES TODAY: 14 jobs · 23 phases ongoing · 4 flagged ⚠

  JOB         PHASE                  SUB                ACT   DENSITY
  Markgraf    15.2 Punch Repairs     TNT/SmartShield    23d   🟠 53% ⚠
  Drummond    14.1 Exterior Paint    TNT Custom         27d   🟠 49% ⚠
  Fish        7.6 Stucco Finish      Watts Stucco       45d   🔴 35% ⚠
  Pou         13.6 Appliances        Cucine Ricci       13d   🟠 45% ⚠
```

That's the Monday morning focus list.

---

## PART 8 — Schedule Builder view

The deliverable for downstream AI scheduling.

```
SCHEDULE BUILDER — typical durations for a new elevated coastal job
─────────────────────────────────────────────────────────────────────

STAGE  PHASE                       ACTIVE  SPAN   DENSITY   CONFIDENCE   DEFAULT SUB           STARTS AFTER
1.4    Site Grading                  4d     5d    🟢 78%    High (9)     Altered State Of Mine —
2.1    Pilings                      47d    62d    🟡 71%    Low (1)      ML Concrete           1.4
2.3    Stem Walls                    8d    11d    🟢 81%    Med (4)      ML Concrete           2.1
2.4    Stem Wall Waterproofing       3d     4d    🟢 85%    Med (4)      CoatRite              2.3
2.5    Under-Slab Plumbing           2d     3d    🟢 90%    Med (3)      Gator Plumbing        2.4
2.7    Slab Pour                     1d     1d    🟢 100%   High (5)     ML Concrete           2.5
3.1    Masonry Walls 1L              7d     9d    🟡 78%    High (5)     ML Concrete           2.7
... (full 60-step sequence) ...
6.1    Plumbing Top-Out              9d    12d    🟢 78%    High (8)     Gator Plumbing        5.1
8.2    Drywall Hang                 15d    17d    🟢 82%    High (7)     WG Quality            8.1
... etc ...
```

### Buttons

- **Generate Baseline Schedule** — exports CSV with start date input, calculates start/end per phase using span values + predecessors
- **Compare Subs** — for any phase, side-by-side sub comparison
- **Plan Scan** (future) — upload plan PDF, AI identifies scope, builds schedule from this table

---

## PART 9 — Meeting Prep view (THE NEW VIEW)

This is where the four data sources actually fuse into a meeting tool. One page per PM, generated the morning of their meeting.

```
┌─ NELSON BELANGER · MEETING PREP · MONDAY 2026-04-29 ─────────────┐
│ Jobs: Clark, Markgraf · Last meeting: 2026-04-22 (7d ago)        │
│                                                                  │
│ ━━━ THIS WEEK'S MUST-DISCUSS (top 5, ranked by severity) ━━━     │
│                                                                  │
│  1. ⚠ MARKGRAF — Owner walk in 5 days, cleaning not logged      │
│     EVIDENCE: Last cleaning log 4/24. Owner walk 4/27.           │
│     ASK: "Who's running final clean? Confirmed for Friday?"      │
│                                                                  │
│  2. ⚠ MARKGRAF — Smarthouse mentioned 3 transcripts in a row    │
│     EVIDENCE: 4/8, 4/15, 4/22 transcripts all flag responsiveness│
│     ASK: "Is Mark coming Friday or do we escalate?"              │
│                                                                  │
│  3. ⚠ CLARK — Capstone shop drawings open since 4/14            │
│     EVIDENCE: Action CL-008 stale 15d. No log activity.          │
│     ASK: "Shop drawings status — call today, or escalate?"       │
│                                                                  │
│  4. ℹ MARKGRAF — Punch density 53%, 23d ongoing                 │
│     EVIDENCE: TNT 4d active in last 14 calendar days             │
│     ASK: "Is TNT pulling crew, or is the punch list shrinking?"  │
│                                                                  │
│  5. ℹ CLARK — Capstone foundation 47d span vs 30d industry      │
│     EVIDENCE: 36 active days, 76% density. On the long end.      │
│     ASK: "Pile cap pour scheduled? What's the look-ahead?"       │
│                                                                  │
│ ━━━ OPEN ACTION ITEMS (Nelson's, by aging) ━━━                  │
│                                                                  │
│  ABANDONED (>30d)                                                │
│  · CL-002 Confirm Capstone shop drawings (32d) — URGENT          │
│                                                                  │
│  STALE (15-30d)                                                  │
│  · MK-014 Confirm Smarthouse Friday (15d) — URGENT               │
│  · MK-018 First Choice cabinets touch-up (16d) — HIGH            │
│                                                                  │
│  AGING (8-14d)                                                   │
│  · ...                                                           │
│                                                                  │
│ ━━━ LOOK-AHEAD (next 14 days, by job) ━━━                       │
│                                                                  │
│  MARKGRAF: 15.5 C.O. Issuance scheduled, 15.6 Owner Move-In      │
│            ⚠ Risk: 4 phases still ongoing, CO target in 5d       │
│                                                                  │
│  CLARK: 2.2 Pile Caps & Grade Beams next                         │
│         Historical median: 8d active. Scheduled: 10d. Healthy.   │
│                                                                  │
│ ━━━ COMMITMENTS FROM LAST MEETING (closure check) ━━━            │
│                                                                  │
│  ✓ MK-009 Order weatherstrip — DONE (logged 4/24)                │
│  ⚠ MK-010 Confirm DB Welding measurements — DONE per binder      │
│           BUT no log entry confirms. ASK to verify.              │
│  ⏵ CL-005 Capstone proposal — IN PROGRESS                        │
│                                                                  │
│ ━━━ CLIENT SIGNALS (last 4 weeks of transcripts) ━━━            │
│                                                                  │
│  · Markgraf owner: positive, no escalation since 4/15            │
│  · Clark owner: not mentioned in last 3 transcripts — re-engage? │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### How it's generated

When the Meeting Prep view is requested for a PM, the system:

1. Pulls all open INSIGHTS scoped to that PM's jobs, ranked by severity × age
2. Pulls all open ACTION_ITEMS for that PM, sorted by aging × priority
3. Computes look-ahead from BT schedule + Schedule Builder medians
4. Re-checks last meeting's commitments against subsequent log activity
5. Scans last 4 weeks of transcripts for client/sub sentiment trends
6. Outputs the structured page above

Every "ASK" line is the suggested talking point — Jake walks into the meeting and the page tells him what to bring up, with evidence underneath.

### What this replaces

- The "open items" page (now embedded with insights wrapped around them)
- The "look-ahead" page (now contextualized with risk)
- The "issues" page (now derived, not manually entered)

PMs get a different version of this — same insights, plus their action items in detail, minus the company-wide subs/phase analytics. Same data layer, different scope filter.

---

## PART 10 — UI principles

- Build sequence is the spine across every page
- One thing per row, max 5 columns
- 4-color density scale, status icons, nothing else
- No tooltips, no hover-only data
- Charts only when they add information
- Active/ongoing always at top
- Print-legible — density flags have text labels
- Insights always cite evidence (which log, which transcript, which phase)
- Every page links downward — click an insight, see the underlying data; click a sub, see their phase history

---

## PART 11 — QA before deploying

Don't say "done." Paste these back:

1. **Reclassification diff** — every sub × log retagged, with old phase / new phase / sample text. Spot-check CoatRite, ML Concrete, M&J, Ross Built Crew.
2. **Filter list** — every entity removed as non-sub.
3. **Keyword library** — full table.
4. **`requires_manual_review` count** — % of total logs unclassified after both passes. If >5%, library needs more patterns.
5. **Burst sanity check** — Stucco, Drywall, Interior Tile, Pool, Framing, Siding, Interior Trim, Roofing. Old span vs new active vs density vs burst count. Flag anything that moved >30%.
6. **Plumbing Top-Out phase card** — full new card, with predecessors/successors and any active insights.
7. **Stucco phase card** — must show 2–3 bursts per job, density per burst.
8. **Markgraf job card** — full read-down. CoatRite at 2.4 not Masonry. Final Punch Out flagged. Insights at top. Action items at bottom.
9. **Active phases today strip** — actual current numbers.
10. **Schedule Builder table** — first 20 rows with predecessors verified.
11. **Nelson's Meeting Prep view** — full page. Every insight must cite evidence. Every "ASK" must be specific.
12. **Insight engine output sample** — print 10 insights generated across the company today, of varied types (sequencing, sub drift, missed commitment, client signal, etc.). Verify they're useful, not noise.
13. **Save to `monday-binder-v2.html`** alongside current.

If a median moved >25% from old number, explain why. If insights feel like noise (>30% of insights would not change a meeting decision), the generators need tuning before deploy.
