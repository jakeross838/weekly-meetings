# Phase 12 — Integrated Redesign (Sub/Job UI + Meeting Structure + Integration Vision)

**Status:** NOT STARTED — PROPOSING ONLY · drafted 2026-05-01
**Stage:** 1 (planning only). No code, no template, no generator changes.
**Decision gate:** Jake reads this doc, approves Parts A / B / C *independently*, then Stage 2 begins on whatever was approved.

---

## Executive summary

Phase 12 fuses three redesigns that the m02 system has been quietly preparing for:

- **Part A** rebuilds the `/subs` and `/jobs` views around a **RED / YELLOW / GREEN / GRAY** sub-status pill, with thresholds derived empirically from the 68-rollup × 34-sub population (not forced into thirds). Stronger asks. Less flag-score noise on the headline.
- **Part B** replaces the current "PM checklist" framing with two real **production meetings** — Office (paperwork/planning, ~75 min) and Site (quality/progress, ~60 min) — structured around PPC%, cascading look-ahead horizons (2/4/8 wk), and an **8-category action item taxonomy** (SCHEDULE / PROCUREMENT / SUB-TRADE / CLIENT / QUALITY / BUDGET / ADMIN / SELECTION). The 6-section sketch from prior chats is the seed; this plan formalizes it as 7 office sections + 6 site sections.
- **Part C** is the **integration vision** — the load-bearing part. Every concrete piece in A and B exists to feed the C2 example list (12 cross-domain integrations), the C3 four feedback loops (transcript → binder → meeting; logs → instances → walk; lessons → checklist → pre-con; sub × jobs → standby → buyout), and the AI Blueprint long-term arc. Sub status pills should drive walk priorities. Transcript processing should cross-check against historical patterns. Meeting agendas should preview risks the data has already detected.

**Phased rollout:** Phase 12 Stage 2 ships A + B with 4-5 of the C2 integrations that already have data. **Phase 13** adds preflight prediction (system writes meeting agenda before meeting). **Phase 14+** is cross-project pattern learning and the agent-architecture vision.

---

## Prior thinking — what's load-bearing, what's new

**Confirmed already in the repo (cite-able):**
- Office vs Site distinction — `OPERATOR.md:29-30`, `phases/06.6/PLAN.md`
- Action item Monday Morning Test — `weekly-prompt.md:27-33` ("specific person, specific verb + deliverable, hard due date")
- Markgraf-lesson trigger framework — `SPEC.md:371-381`, `phase-taxonomy.yaml:1405,1536`
- PPC% definition — `monday-binder-v1-archive/generate_monday_binder.py:92`
- 2/4/8-week look-ahead horizons — `weekly-prompt.md:74-78`
- Phase predecessors/successors — `phase-taxonomy.yaml` (full graph)
- Density tiers (🟢🟡🟠🔴) — `SPEC.md:287-292`
- 7-type action item taxonomy in v1: `SELECTION / CONFIRMATION / PRICING / SCHEDULE / CO_INVOICE / FIELD / FOLLOWUP` — `weekly-prompt.md:174-181`

**Lives only in chat history (not yet formalized):**
- The **8-category** action item system (kickoff names: SCHEDULE / PROCUREMENT / SUB-TRADE / CLIENT / QUALITY / BUDGET / ADMIN / SELECTION). The repo has the **7-type** v1 taxonomy. Section B5 reconciles these — Jake should confirm whether the 8-cat is a replacement, an additional axis, or a renaming.
- The **AI Blueprint** (103 agents / 14 departments / 12 per job). Treated here as a Phase 14+ horizon vision.
- **Pull scheduling** (Lean/IPD subs commit start dates) — added in Section B1 as industry context.
- **Sub status pills** (RED/YELLOW/GREEN/GRAY) — color tiers exist for density; the *sub-level* aggregated status pill is new in Part A.

**Where prior thinking conflicts with current code (flagged):**
1. Kickoff says "all 95 subs." Actual qualifying universe is **34 subs** (the rollup pipeline already filters to phases where the sub has ≥3 jobs). The other ~60 subs in the daily-logs corpus exist but are GRAY-by-exclusion. Section A1 reconciles.
2. Phase 6 build_meeting_prep.py emits PM-facing checklists. Jake's recent feedback: "checklists don't work; we need a real production meeting." Part B replaces — does not augment — those packets. Section B6 asks Jake to confirm before any code change.
3. v1 9-section meeting flow (`OPERATOR.md:11`) overlaps but does not match the proposed 7-section office structure. Section B2 explicitly maps old → new.

---

## PART A — Sub/Job UI Redesign + GREEN/YELLOW/RED thresholds

### A1. Distribution analysis (empirical)

Source: `data/sub-phase-rollups.json` — 68 rollups, 34 distinct subs, generated 2026-04-29.
Filter: rollups already require `jobs_performed ≥ 3` per phase to qualify.

**Rollup-level distributions (n=68):**

| Metric | min | p25 | p50 | p75 | p90 | max |
|---|---:|---:|---:|---:|---:|---:|
| `vs_phase_median_density` | -0.734 | -0.090 | 0.000 | +0.091 | +0.552 | +0.938 |
| `primary_density` | 0.041 | 0.467 | 0.556 | 1.000 | 1.000 | 1.000 |
| `return_burst_rate` | 0.000 | 0.000 | 0.000 | 0.407 | 0.645 | 1.000 |
| `punch_burst_rate` | 0.000 | 0.000 | 0.354 | 0.667 | 0.800 | 1.000 |
| `jobs_performed` | 3 | 3 | 4 | 6 | 7 | 11 |
| `flag_score` | 0 | 0 | 1 | 2 | 3 | 4 |

**Sub-level (jobs-weighted aggregation, n=34):**

| Metric | min | p25 | p50 | p75 | p90 | max |
|---|---:|---:|---:|---:|---:|---:|
| `avg_vs_phase` (weighted) | -0.677 | -0.095 | -0.008 | +0.084 | +0.185 | +0.938 |
| `avg_density` | 0.323 | 0.496 | 0.576 | 0.736 | 1.000 | 1.000 |
| `avg_return` | 0.000 | 0.139 | 0.250 | 0.475 | 0.539 | 0.667 |
| `avg_punch` | 0.000 | 0.375 | 0.432 | 0.500 | 0.760 | 1.000 |
| `max_flag_across_phases` | 0 | 1 | 2 | 3 | 3 | 4 |

**Natural breaks observed:**
- `vs_phase_median_density` is approximately symmetric around zero with median = 0.000 and IQR ±0.09. Natural breaks at **-0.10** (worst quartile cliff) and **-0.05** (warning band start).
- `flag_score` clusters tightly at 0–3 with a single outlier at 4 (Ross Built Crew); max_flag = 4 means *all four* flag reasons hit on a single phase, which is rare and meaningful.
- `punch_burst_rate` jumps from 0.667 (p75) to 0.800 (p90) — natural break at **0.80** for "always punching."
- `return_burst_rate` p75 is 0.407, p90 is 0.645 — natural break at **0.50** for "comes back too often."

**Low sample size:** zero subs with `jobs_performed < 3` in the rollup file (already filtered upstream). The broader ~60-sub corpus *outside* rollups is GRAY-by-exclusion — represented as a separate "Insufficient data" tab in the roster, not mixed in.

### A2. Proposed thresholds

```
RED   — auto if max_flag = 4
      OR (max_flag ≥ 3 AND avg_vs_phase ≤ -0.10)

YELLOW — max_flag = 3 with avg_vs_phase > -0.10
       OR max_flag = 2
       OR avg_vs_phase ≤ -0.05
       OR avg_return ≥ 0.50
       OR avg_punch ≥ 0.80

GREEN  — max_flag ≤ 1 AND avg_vs_phase ≥ -0.05 AND avg_punch < 0.80 AND avg_return < 0.50

GRAY   — jobs_performed (max across phases) < 3
       OR sub not in rollup pipeline at all (separate roster tab)
```

**Justification:** Each cutoff is anchored to a percentile (not a forced "worst third"). `-0.10` = roughly p25 of avg_vs_phase. `max_flag = 4` = the single-phase worst-case. Punch ≥ 0.80 and return ≥ 0.50 align with p90/p75 of the distribution. No forced bucket sizes.

**Resulting classification (current dataset, n=34):**

```
RED  (8, 24%)   YELLOW  (18, 53%)              GREEN  (8, 24%)
─────────────   ──────────────────             ──────────────
Sarasota Cab    Integrity Floors               USA Fence (+0.94)
RC Grade        Paradise Foam                  EcoSouth (+0.68)
Tom Sanger ✓    M&J Florida                    Avery Roof (+0.28)
CoatRite        Rangel Custom Tile             West Coast Found
SW Concrete     WG QUALITY                     Kimal Lumber
ML Concrete     Elizabeth K. Rosser            Precision Stairs
Metro Electric  ALL VALENCIA                   DB Welding
Ross Built Crew Doug Naeher Drywall            Fuse Specialty
                Climatic Conditioning
                Florida Sunshine Carp
                Gonzalez Construction
                SmartShield Homes ✓
                TNT Custom Painting
                Universal Window
                Captain Cool
                Blue Vision Roofing
                Gator Plumbing
                Jeff Watts ✓
```

(✓ = matches kickoff expectation)

### A3. Spot-check classifications (kickoff requested)

| Sub | Status | Reasoning | Matches expectation? |
|---|---|---|---|
| **Tom Sanger Pool & Spa** | **RED** | max_flag=3 (Pool Equipment & Startup), avg_vs_phase = -0.21, sum_flag = 8. | ✓ kickoff: "currently flag score 8" |
| **SmartShield Homes** ("Smart House/Mark") | **YELLOW** | max_flag=3 on Electrical Rough, avg_vs_phase = 0.00, avg_return = 0.50. Mixed picture. | ✓ memory "problematic" but not catastrophic |
| **Jeff Watts Plastering** | **YELLOW** | max_flag=3 on Stucco Scratch (9 jobs, density 0.38), but avg_vs_phase = **+0.15** overall. Flagged at sub level because scratch-coat dragging is a real signal, even though the trim/finish work is fine. | ✓ kickoff: "flagged on Krauss only — strong elsewhere" — partially. The scratch-coat pattern is wider than Krauss in the data. |
| **USA Fence Company** | **GREEN** | max_flag=0, avg_vs_phase = +0.94, no return/punch issues. | ✓ expected GREEN |
| **EcoSouth** | **GREEN** | max_flag=1, avg_vs_phase = +0.68, density 1.00. | ✓ bonus expected GREEN |
| **Ross Built Crew** | **RED** (auto) | max_flag = 4 on Punch Walk & List (every flag reason triggered: density below threshold, return rate high, punch rate high, vs median below). 9 phases, 11 jobs. | ⚠ Internal crew flagged. Worth Jake's attention. |

### A4. Page structure proposals

#### `/subs` (sub roster)

```
SUB ROSTER · 34 subs (8 RED · 18 YELLOW · 8 GREEN)            [+ Insufficient data ▾]

[ All ] [ Red 8 ] [ Yellow 18 ] [ Green 8 ] [ Gray ]   sort: most-RED-issues first  ▾

🔴 Tom Sanger Pool & Spa LLC          7 jobs · 4 phases · 3 open items     view ▸
   Pool work consistently behind median, dominant punch pattern across 3 jobs.
🔴 CoatRite LLC                       8 jobs · 1 phase  · 1 open item      view ▸
   Stem-wall waterproofing dragging on 4 of 8 jobs.
🔴 ML Concrete, LLC                   4 jobs · 4 phases · 2 open items     view ▸
   Pile caps and tie beams below typical; masonry uneven.
… (RED block continues)

🟡 Jeff Watts Plastering and Stucco   9 jobs · 2 phases · 0 open items     view ▸
   Strong on framing/finish; scratch coat pattern dragging across 9 jobs.
… (YELLOW block continues)

🟢 USA Fence Company                  3 jobs · 1 phase  · 0 open items     view ▸
🟢 EcoSouth                           5 jobs · 1 phase  · 0 open items     view ▸
…
```

**Rules:**
- Status pill is the lead, not flag score
- One-line verdict under sub name (auto-generated from worst signal — see A4-asks)
- Action items count comes from `binders/*.json` filtered by `related_sub`
- Default sort: RED → YELLOW (by avg_vs_phase ascending) → GREEN → GRAY
- Filter chips switch the visible block
- Flag scores live on the detail page, not the headline

#### `/subs/<slug>` (sub detail)

```
🔴 TOM SANGER POOL & SPA LLC                         Last seen: 2026-04-26
─────────────────────────────────────────────────────────────────────────
Pool work consistently behind typical, with a recurring punch-list pattern.
Status RED on 3 of 4 phases; 8 cumulative flag points across the sub's footprint.

ACTION ITEMS (3)
  Owner       Item                                  Job        Aging  Pri
  Nelson B.   Confirm Tom Sanger Friday startup     Markgraf    9d   URGENT
  Nelson B.   Pool plaster touch-up scheduling      Markgraf   17d   HIGH
  Bob M.      Confirm pebbletec timing              Pou         3d   NORMAL

PERFORMANCE SNAPSHOT
  Jobs worked:        7 (Markgraf, Pou, Drummond, Fish, Krauss, Clark, Bishops)
  Phases:             14.5 Pool Shell, 14.7 Plaster, 14.8 Equipment, 15.1 Punch
  Worst phase:        14.8 Pool Equipment & Startup — 7 jobs, density 44%, vs typical -56%
  Best phase:         6.1 Plumbing Top-Out — 3 jobs, density 100%, +68% vs typical
  
TOP 3 ACTIONABLE ROLLUPS (not all 4)
  1. 14.8 Pool Equipment & Startup (Pou, Krauss, Clark)
     Why: 7 jobs at 44% density, 56% below typical for this phase
     Ask: "Tom's pool startups consistently take 2× the typical span. Is this
           crew capacity, sequencing with electrical trim, or scope creep on
           equipment? Pou is mid-startup now — confirm a hard finish date."
  2. 15.1 Punch Walk & List (3 jobs, density 4%)
     Why: Returns for punch repeatedly, can't close out
     Ask: "Tom's punch-walk closure pattern blocks Markgraf C.O. Are punch
           items being deferred to startup, or is this a checklist gap?"
  3. 14.5 Pool Shell / Plumbing (4 jobs at 40% density)
     Why: Shell work scattered across calendar, predicted finishes slipping
     Ask: "What's the actual coordination block between shell and plumbing
           rough? Is Tom waiting on us, or is the crew the bottleneck?"

PHASE INSTANCES (collapsed by default)
  ▸ Show all 8 sub-phase rollups + per-job density breakdown
```

**Note on rewritten asks:** the kickoff specifically called out "lead with hypothesis, not 'what's different about X?'" — every ask in the example above proposes a possible cause and a concrete next step.

#### `/jobs` (job roster)

```
JOB ROSTER · 12 active jobs                               [+ Closed]

[ All ] [ At-risk 3 ] [ Healthy 9 ]   sort: most-RED-subs first ▾

JOB              PM           STAGE     RED  YELLOW  AGING ITEMS
Markgraf         Nelson B.    15 Closeout    3       4        7 ⚠
Fish             Lee W.       7 Envelope     2       3        4 ⚠
Pou              Bob M.       13 MEP Trim    2       4        2
Krauss           Nelson B.    14 Exterior    1       5        3
Drummond         Lee W.       12 Paint       1       3        2
Clark            Nelson B.    2 Foundation   1       2        1
Dewberry         Jason S.     6 MEP Rough    0       4        2
…
```

#### `/jobs/<slug>` (job detail)

```
MARKGRAF · 5939 RIVER FOREST CIR                  Nelson B. · Stage 15 Closeout
──────────────────────────────────────────────────────────────────────────────
CO target: 2026-04-27 (-4 days, OVERDUE) ⚠

ACTION ITEMS BY AGING (7 open)
  ABANDONED (>30d)
    Confirm Capstone shop drawings    Nelson  32d open  URGENT
  STALE (15-30d)
    Confirm Smarthouse Friday          Nelson  15d open  URGENT
    First Choice cabinet touch-up      Nelson  16d open  HIGH
  AGING (8-14d)
    …

SUBS WORKING (RED first)
  🔴 Tom Sanger Pool & Spa     14.8 Pool Equipment   23d active, 44% density
  🔴 SmartShield Homes (LV)    6.5 LV Trim           13d active, 38% density
  🟡 TNT Custom Painting       12.2 Paint Walls      10d, 53% density (52% typical)
  🟢 Ross Built Crew (punch)   15.1 Punch            ongoing, mixed coverage

PHASE ACTIVITY (collapsed by default)
  ▸ Show 23 phase instances · 5 ongoing · 18 complete
```

### A4-questions. Open questions for Jake (Part A)

1. **GRAY default behavior** — show in roster as a separate filter (current proposal), filter out by default, or surface only when actively logged this week?
2. **Punch pattern weight** — `avg_punch ≥ 0.80` lifts to YELLOW. Some subs (drywall punch sub, Ross Built Crew internal) inherently *do* punch work and aren't lower-quality for it. Should "punch is the trade" subs be exempted via a config flag?
3. **Internal crew (Ross Built Crew = max_flag 4 → RED)** — accurate signal that internal punch work is dragging, but the RED pill on internal crew may be discouraging. Show separately, or treat as a special category ("In-house")?
4. **Single-phase RED subs** — Sarasota Cabinetry (1 phase, 3 jobs, max_flag=3) is RED on its only phase. Are 3 jobs enough to label, or do we want 5+ for RED?
5. **Decay** — should status pills auto-improve if a sub has 3 consecutive jobs without a flag, or only on the next full rollup recompute?

---

## PART B — Production Meeting Structure (Office + Site)

### B1. Research synthesis

**Ross Built prior thinking (from `weekly-prompt.md`, `OPERATOR.md`, `SPEC.md`):**
- v1's 9-section flow is a checklist, not a meeting. Jake's recent verdict: "doesn't work."
- Office vs Site is a **scope** distinction: Office runs every job in the PM's portfolio; Site runs the jobs the PM is physically on this week.
- Action items must pass the Monday Morning Test (specific person, verb, deliverable, hard date).
- 2/4/8 wk look-ahead horizons exist in `weekly-prompt.md:74-78`.

**Industry best practices (residential luxury custom GC):**
- **PPC%** (Percent Plan Complete, Lean construction): of items committed last week, what fraction were actually completed. Schedule-reliability metric. <70% = chronic over-promising.
- **Pull scheduling** (Last Planner System): subs commit to start dates *they* believe; PM blocks-and-tackles obstacles; doesn't impose top-down dates. Improves PPC% by 20-40% in studies.
- **Cascading look-ahead** (different focus per horizon):
  - **2-wk = EXECUTION** — sub start confirmed, materials on site, predecessor complete, blockers resolved
  - **4-wk = COORDINATION** — sequencing dependencies, what needs confirming this week to enable next-month work
  - **8-wk = PROCUREMENT/SELECTIONS** — long-lead items, submittals, locked selections
- **Quality hold points** — specific phase transitions where a third party (PM, inspector, owner) signs off before the next trade starts (e.g., post-drywall before tape; post-tape before paint).
- **Pre-con per trade** — short scoping meeting before each major trade arrives, covering quality expectations and hold points specific to that trade.

**Both Office AND Site must be REAL production meetings driving the whole job, not checklists.**

### B2. Office meeting structure

**Total target duration: ~75 min** (12 jobs × ~6 min/job over 5 PMs = 75 min average per Office).

| § | Section | Purpose | Data sources | Output | Time |
|---|---|---|---|---|---|
| 1 | **Last Week PPC%** | Reliability check: what we promised vs what shipped | `meeting-commitments.json` (last week) ↔ `daily-logs.json` activity ↔ `binders/*.json` closed items | Single number per PM, with closed/carried/abandoned breakdown. Stays on the executive dashboard week-over-week. | 5 min |
| 2 | **Look-Ahead 2-wk EXECUTION** | Confirm next 14 days are committed: sub start dates, materials on site, predecessors complete, blockers cleared | Phase taxonomy successors, `phase-instances-v2.json` ongoing/scheduled, sub status pill | "Confirmed" / "Blocked" / "Unknown" per upcoming phase. Output: list of confirmations to obtain *this week*. | 20 min |
| 3 | **Look-Ahead 4-wk COORDINATION** | Sequencing dependencies between trades, gates that must close in next 14 days to enable wk-3-4 work | Same as §2 but window 15-28d, predecessors_missing array | List of *dependency confirmations* needed (e.g., "drywall tape needs scheduling decision by Friday to enable paint start in 4 wks"). | 10 min |
| 4 | **Look-Ahead 8-wk PROCUREMENT/SELECTIONS** | Long-lead items, submittals, locked selections | `binders/*.json` items typed SELECTION + PROCUREMENT, 29-56d window | Selections-still-open list with "needed by" date impact. | 5 min |
| 5 | **Open Action Items by category** | Roll forward last meeting's items, by 8-cat taxonomy | `binders/*.json` enriched + categorized | Updated items with status. New items captured. | 15 min |
| 6 | **Outstanding Selections & Issues roundup** | Anything that didn't fit cleanly above (sub issues escalating, client signals, design questions) | Insights bucket=field, severity=warn|critical | New action items by category. | 10 min |
| 7 | **Financial Review** | GP vs budgeted, open COs, pay app status, budget exposure | (Future — currently not in system; placeholder) | Budget flags by job. | 10 min |

**Note:** 7 sections (kickoff proposed 6 — added §3 4-wk-coordination as a separate section because the 14-day and 15-28d windows have different decision rhythms).

### B3. Site meeting structure

**Total target duration: ~60 min** (smaller scope — only jobs the PM is physically running this week).

| § | Section | Purpose | Data sources | Output | Time |
|---|---|---|---|---|---|
| 1 | **Open Action Items rollover** | Field-relevant items only (FIELD/QUALITY/SUB-TRADE categories) carried from last week | `binders/*.json` filtered | Status update on field-bucket items. | 10 min |
| 2 | **Walk by area or trade** | Quality issues, photos, on-site questions | Insights with related_sub on RED/YELLOW pills, transcripts mentioning specific rooms/areas | New punch items, re-classification of existing items. | 25 min |
| 3 | **This week's subs on site** | Coordinate handoffs between subs sharing the site | `daily-logs.json` last-7-days, `phase-instances-v2.json` ongoing | Hand-off confirmations, conflict resolution. | 10 min |
| 4 | **Quality hold points** | What gates must close this week before next trade | Phase taxonomy + Markgraf-lesson triggers | "Hold X until Y" list. | 5 min |
| 5 | **Field-discovered new items** | Anything walked-into not on the agenda | (live capture) | New items with category. | 5 min |
| 6 | **Closeout: WHO + WHAT + BY WHEN** | Restate every action with owner + deliverable + hard date | (computed from §1-5) | Final commitment list captured into `meeting-commitments.json`. | 5 min |

### B4. How meeting OUTPUT flows back into the system

```
Office meeting outputs:
  - PPC% ............... → state/ppc-history.json (new file)
  - Schedule confirms .. → phase-instances metadata: "confirmed_for_week" boolean
  - Updated action items → binders/*.json with category field added
  - New action items ... → binders/*.json append
  - Selections-needed .. → items[] with category=SELECTION, due dates
  - Financial flags .... → state/budget-flags.json (Phase 13+)

Site meeting outputs:
  - Punch additions .... → binders/*.json items[] category=QUALITY
  - Sub performance .... → state/sub-signals.json append (drift detection)
  - Quality issues ..... → binders/*.json items[] category=QUALITY
  - Hold points fired .. → phase-instances metadata: "hold_points_passed"

Both flow through process.py → binders/*.json → next Monday's build_meeting_prep.
The new field `category` on items[] is the schema delta this requires.
```

### B5. Action item categorization — 8-cat reconciliation

**Kickoff proposes:** SCHEDULE / PROCUREMENT / SUB-TRADE / CLIENT / QUALITY / BUDGET / ADMIN / SELECTION

**v1 currently has** (`weekly-prompt.md:174-181`): SELECTION / CONFIRMATION / PRICING / SCHEDULE / CO_INVOICE / FIELD / FOLLOWUP

**Proposed mapping (preserves v1 data, adds new axis):**

| New (8-cat) | Maps from v1 | Notes |
|---|---|---|
| SCHEDULE | SCHEDULE | direct |
| PROCUREMENT | (new) | extracted from FIELD/FOLLOWUP items mentioning materials/orders/long-lead |
| SUB-TRADE | (new) | items where related_sub is set; was buried inside FIELD |
| CLIENT | (new) | items where owner = client or content mentions client decision |
| QUALITY | FIELD (subset) | punch items, deficiencies, hold-point fails |
| BUDGET | CO_INVOICE + PRICING | merged: pay apps, COs, pricing approvals |
| ADMIN | FOLLOWUP (subset) | permits, inspections, paperwork |
| SELECTION | SELECTION | direct |
| (residual) | CONFIRMATION | most CONFIRMATION items map to SCHEDULE or SUB-TRADE based on content |

**Recommendation:** Add `category` as a NEW field on `items[]`, keep `type` (v1) for backward compat. process.py's prompt updates to emit both. Run a one-time backfill on existing binders.

**Buyouts question (kickoff mentions Jake added "buyouts"):** map to PROCUREMENT (sub buyouts) or BUDGET (financial buyouts) based on context. Worth a single Jake decision.

### B6. Open questions for Jake (Part B)

1. **8 categories — confirm the list, or adjust?** Specifically: where does "communication" go (kickoff mentioned)? Is "buyouts" PROCUREMENT or its own?
2. **Time allocation** — per-job-within-meeting (every job gets 6 min) or per-meeting-as-whole (sections take fixed time, jobs get whatever's left)?
3. **Replace vs. supplement** — should the new meeting docs *replace* what `build_meeting_prep.py` emits today (PM packets), or be separate parallel outputs?
4. **Site walk decomposition** — by room (e.g., kitchen, master bath, exterior)? by trade (electrical, plumbing, finishes)? by area (interior front, interior back, exterior, site)? Probably context-dependent — should there be a per-job preference?
5. **PPC% denominator** — what counts as a "commitment" for the week? Only items captured in last Monday's transcript? Or also schedule expectations (phases that should have started/finished)?
6. **Financial Review section** — there's no budget data wired in yet. Add a placeholder section with "data not yet integrated" or omit until Phase 13?

---

## PART C — Integration Vision (load-bearing)

### C1. Vision statement

Ross Built operations should function as a single intelligent system, not a collection of tools. Every piece feeds every other piece. A meeting agenda predicts what to watch for. A transcript gets cross-checked against historical patterns. Sub performance flags route to the right walk areas. Phase predictions adjust based on current sub mix and outstanding selections. The system gets smarter with every project, transcript, and daily log — building a 12-job × 14-department × 103-agent capability over time (the AI Blueprint horizon).

### C2. Concrete integration examples (12)

#### C2-1. Meeting agenda predicts upcoming sub activity
- **Trigger:** Monday `run_weekly.bat` fires
- **Data sources:** `phase-instances-v2.json` (current_stage), `phase-taxonomy.yaml` (successors), `sub-phase-rollups.json` (typical sub per phase)
- **Output:** Office meeting §2 (2-wk look-ahead) auto-populated with "Phase X likely needs sub Y this week" rows
- **Action:** PM confirms or flags during meeting; result writes back to phase metadata
- **Today:** Phase taxonomy + instances exist. **Missing:** the join logic and Office §2 rendering.

#### C2-2. Transcript cross-check against historical sub patterns
- **Trigger:** Tuesday `process.py` runs against new transcript
- **Data sources:** `sub-phase-rollups.json` (return/punch rates per sub × phase), transcript text
- **Output:** "TNT typically returns 3× during paint, transcript only mentions 1 — verify nothing missed" flag in process.py output
- **Action:** Jake reviews flagged items before binder save
- **Today:** Rollups exist, process.py prompt-only flow. **Missing:** post-extraction cross-check pass; new field on quarantined items.

#### C2-3. Sequencing risk from daily logs (real-time)
- **Trigger:** New daily log arrives, classifier assigns phase
- **Data sources:** `daily-logs.json` (today), `phase-taxonomy.yaml` (predecessors), `phase-instances-v2.json` (current ongoing)
- **Output:** Insight (already partly in g1_sequencing.py) — but extend to "Watts scheduled before Tile materials ordered"
- **Action:** Surfaces in Office §3 (4-wk coordination)
- **Today:** g1 fires for sequencing_risk on density. **Missing:** materials/order tracking integration.

#### C2-4. Selection blocker propagation
- **Trigger:** Action item with category=SELECTION ages past 14 days
- **Data sources:** `binders/*.json` (item with related_phase), `phase-taxonomy.yaml` (downstream successors)
- **Output:** "Bishops haven't picked S2/S3 plaster — affects 4 upcoming phases at Markgraf" insight
- **Action:** PM packet §4 (8-wk procurement/selections gate) flags
- **Today:** items have related_phase. **Missing:** propagation through successor graph.

#### C2-5. Forward CO estimation (Phase 12 stub, Phase 14 full)
- **Trigger:** Weekly recompute
- **Data sources:** `phase-medians.json`, `phase-taxonomy.yaml` dependencies, current sub mix per job, outstanding selections list
- **Output:** Predicted CO date per job with confidence band
- **Action:** Drives Master/Executive packet "On track / Slipping / At risk" headline
- **Today:** Medians exist. **Missing:** the prediction engine itself (this is Phase 14 territory; Phase 12 ships only the "based on current ongoing density, Markgraf will overshoot CO target by 11±5 days" naive estimate).

#### C2-6. Cross-job sub coordination
- **Trigger:** Sub's name appears in two job schedules within the same week
- **Data sources:** `phase-instances-v2.json` ongoing across all jobs, sub status pill
- **Output:** "Watts at Krauss next Tuesday, but currently dragging on Pou — flag for Lee Worthy" cross-job conflict
- **Action:** Office meeting §2 cross-PM coordination row
- **Today:** Instances + sub names exist. **Missing:** cross-job conflict detector.

#### C2-7. Quality hold point detection
- **Trigger:** Successor phase logs activity before predecessor passes hold point
- **Data sources:** `phase-taxonomy.yaml` (parallel_with vs successors), `daily-logs.json`
- **Output:** "Interior trim items in transcript indicate sequence is starting before paint prep complete in 2 areas" insight
- **Action:** Site meeting §4 (quality hold points)
- **Today:** Taxonomy has predecessors/successors; doesn't have explicit "hold points." **Missing:** hold-point declarations in taxonomy.

#### C2-8. Punchlist → QC checklist promotion
- **Trigger:** Same punch item resolved on 3+ jobs (= recurring issue pattern)
- **Data sources:** `binders/*.json` history, transcript closeouts
- **Output:** "Smart House LV issue resolved on Markgraf — propose adding to permanent pre-MEP-rough check on all future jobs" suggestion
- **Action:** Pre-con meeting per trade picks up the new check
- **Today:** Markgraf-lesson triggers exist as static rules. **Missing:** auto-promotion engine; this is Phase 13/14 work.

#### C2-9. Financial exposure alerting
- **Trigger:** New CO captured in transcript, total project COs cross threshold
- **Data sources:** `binders/*.json` items category=BUDGET, contract value (not yet in system)
- **Output:** "Fish CO total at 11.3% of contract, threshold 10% — exposure flag"
- **Action:** Office §7 (Financial Review) headline
- **Today:** No budget data wired. **Phase 13+ requires** contract-value integration.

#### C2-10. Sub performance trend detection (week-over-week)
- **Trigger:** Weekly recompute compares current sub status to prior 2 weeks
- **Data sources:** `state/sub-signals.json` (history file, new), `sub-phase-rollups.json` (current)
- **Output:** "Watts has degraded 3 weeks in a row across 2 jobs — escalation signal"
- **Action:** Office §6 (issues roundup) escalation row
- **Today:** Single-week rollups exist. **Missing:** historical sub-status snapshots, trend detection.

#### C2-11. Transcript sentiment → client re-engagement
- **Trigger:** Transcript scan, client name absent for 3+ consecutive weekly transcripts
- **Data sources:** `transcripts/processed/*.txt` window, transcript metadata
- **Output:** "Clark owner not mentioned in last 3 transcripts — re-engage?" insight
- **Action:** Office §6 client signals row
- **Today:** Transcripts exist as flat text. **Missing:** transcript indexing by job/owner mention.

#### C2-12. Predecessor-missing classifier nudge
- **Trigger:** Phase complete with predecessor no-logs (g1 sequencing_violation already fires)
- **Data sources:** `phase-instances-v2.json`, `daily-logs.json`
- **Output:** Today: insight in data_quality bucket (print-hidden). Vision: triggers a re-classification suggestion to the keyword library
- **Action:** Auto-proposes new keywords for `config/phase-keywords.yaml`
- **Today:** g1 fires the insight. **Missing:** the keyword-suggestion auto-loop.

### C3. Data feedback loops

#### Loop 1 — Operational (transcript → meeting → transcript)
```
Transcript captures items
   → process.py extracts to binders/*.json with category
      → next Monday: build_meeting_prep reads, renders office/site packets
         → meeting captures updates + new items
            → transcript writes back to processed/
               → process.py picks up next week
```
**Working today:** transcript → binder → packet (without category).
**Missing:** category field; meeting-output → transcript loop closure.
**Parts that close it:** Part B5 (category schema), Part B4 (output flow).

#### Loop 2 — Operational (logs → instances → walk)
```
Daily log filed (Buildertrend)
   → fetch_daily_logs.py pulls
      → build_phase_artifacts classifies, updates phase-instances-v2.json
         → sub-phase-rollups.json recomputed
            → sub status pill on /subs roster
               → drives Site meeting §2 walk priorities
                  → walk findings → new punch items in transcript
                     → loop closes
```
**Working today:** log → instances → rollups.
**Missing:** sub status pill (Part A), walk-priority rendering (Part B).
**Parts that close it:** Part A2-A4 (status pill) + Part B3 §2 (walk by area or trade).

#### Loop 3 — Learning (lessons → checklist → pre-con)
```
Markgraf-style mistake captured
   → Generator 6 hard-codes the rule
      → fires as insight on future jobs
         → pre-con meeting per trade adopts the check
            → next mistake learned, rule added
```
**Working today:** Generator 6 framework + 4 hand-coded rules.
**Missing:** auto-promotion (C2-8), pre-con meeting structure (Phase 13).
**Parts that close it:** None in Phase 12. **This is Phase 13 territory.**

#### Loop 4 — Supplier (sub × jobs → standby → buyout)
```
Sub status RED across 3+ jobs
   → standby flag set
      → next job buyout decision: skip, escalate, or swap
         → transcript captures buyout choice
            → binder logs sub-relationship change
               → future status calc weights recent jobs higher
```
**Working today:** sub-phase rollups are point-in-time.
**Missing:** standby flag, buyout decision capture, recency-weighted rollups.
**Parts that close it:** None directly in Phase 12. Part A status pill is precondition. **Loop closure is Phase 13/14.**

### C4. Architecture implications for Parts A and B

These are the questions that shouldn't be answered independently per part:

| Question | Answer | Implication |
|---|---|---|
| Does the meeting agenda need a "Predictions" section? | **Yes** — Office §2 IS the predictions section (2-wk lookahead drives expected sub activity). No separate section. | Part B2 §2 is load-bearing; don't dilute. |
| Does the action item category need a "Predicted/Suggested by System" status separate from "Captured in Meeting"? | **Yes — add `source` field** alongside `category`. Values: `transcript` / `system_predicted` / `manual`. System-predicted items show with a different visual marker. | Part B5 schema delta needs `source` in addition to `category`. |
| Do sub status pills update real-time or weekly batch? | **Weekly batch (Phase 12)**. Real-time recompute is Phase 13. | Part A status pill computed only by `run_weekly.bat`; UI reads from rollups file. No live recompute. |
| Does process.py do cross-referencing during extraction, or post-process? | **Post-process** (separate step after extraction). Keeps process.py prompt-pure; cross-check pass is its own module that reads binder + rollups + flags. | Part C2-2 is a new module, not a process.py change. |
| Should there be a "preflight" step before each meeting (system writes agenda) vs. post-hoc (system records what happened)? | **Phase 12 = post-hoc**. Office/Site meetings are templated and rendered by build_meeting_prep on Monday. Preflight (system *predicts* the agenda topics) is **Phase 13**. | Don't try to ship preflight in Phase 12. The 7-section + 6-section structures are fixed; data fills them. |

### C5. Phase roadmap implications

#### What ships in Phase 12 Stage 2 (this build)

- Part A: Sub status pill, /subs and /jobs redesign, threshold thresholds, rewritten asks
- Part B: Office and Site templates rendered by `build_meeting_prep.py`, 8-cat schema with backfill, PPC% computed and displayed, look-ahead windows wired to `phase-instances-v2.json` + taxonomy
- Part C integrations achievable now (data exists today):
  - C2-1 meeting agenda predicts sub activity (Office §2)
  - C2-3 sequencing risk in 4-wk window (extends g1)
  - C2-4 selection blocker propagation (binder + taxonomy)
  - C2-6 cross-job sub conflict detector
  - C2-12 predecessor-missing classifier nudge surfaced (not auto-applied)

#### What requires Phase 13

- Real-time sub status recompute (currently weekly batch)
- Preflight: system *writes* the meeting agenda before the meeting happens
- C2-7 quality hold points (needs hold-point declarations in taxonomy)
- C2-9 financial exposure alerting (needs budget data integration)
- C2-10 sub performance trend (needs `sub-signals.json` history)
- C2-11 transcript sentiment indexing (needs transcript indexing by job/owner)
- Loop 4 standby/buyout closure
- 8-cat enforcement at process.py extraction time (currently post-hoc backfill)

#### What requires Phase 14+ (or beyond — AI Blueprint horizon)

- C2-5 forward CO estimation engine (full prediction, not naive)
- C2-8 punchlist → QC checklist auto-promotion
- Loop 3 learning closure (auto-rule generation)
- Cross-project pattern detection
- The 14-department × 103-agent architecture (Jake's stated long-term vision)
- Pre-con meeting structure per trade (Lean/IPD methodology)
- Pull scheduling commitment capture

#### What is explicitly NOT in Phase 12 (scope discipline)

- Real-time anything (all batch; weekly recompute)
- Budget/financial integration (no contract-value wiring)
- Auto-rule promotion from punch patterns
- Transcript sentiment analysis
- Pre-con per trade
- Plan ingest
- Schedule prediction (size-class baselines, plan-aware)
- Any agent/department/AI Blueprint scaffolding

### C6. Open questions for Jake (Part C)

1. **Top 3-5 C2 integrations for Stage 2** — the C5 "achievable now" list has 5 (C2-1, C2-3, C2-4, C2-6, C2-12). Drop any? Add C2-2 (transcript cross-check)?
2. **Preflight vs post-hoc emphasis** — Phase 12 default is post-hoc (system renders, doesn't predict). Do you want one preflight feature snuck in (e.g., "predict what sub Office §2 should call out before the meeting")?
3. **Sub status pill cadence** — weekly batch (current proposal) or worth investing now in a daily recompute via dashboard?
4. **C2 list completeness** — anything you've described in chats that's not on the list?
5. **AI Blueprint roadmap** — for Phase 13/14: which agents/departments are next-up? The current phases (PM Office Manager, Site Walk Manager, Schedule Predictor, Sub Performance Tracker) are implicit in Parts A/B. Worth surfacing as named "agents" even pre-AI?

---

## Stage 2 implementation plan

### Effort estimates (independent)

| Part | Effort | Comment |
|---|---|---|
| Part A only | **8-12 hours** | Sub status pill calc, /subs and /jobs templates, ask rewrites. Builds on existing rollups + binders. |
| Part B only | **16-24 hours** | New office/site templates, PPC% computation (new file), look-ahead wiring, 8-cat schema delta + backfill, build_meeting_prep refactor. |
| Part C (Phase 12 subset, 5 integrations) | **12-18 hours** | C2-1, C2-3 ext, C2-4, C2-6, C2-12 surfaced. Each integration is a discrete generator extension. |
| **All three combined** | **30-45 hours** | Saves ~5 hours via shared schema work and parallel template development. |

### Dependencies between parts

- Part B §2 depends on **Part A** sub status pill (used to flag risky upcoming sub activity)
- Part B §5 depends on **8-cat schema** (Part B5 itself)
- Part C C2-1 (meeting agenda prediction) depends on **Part A + Part B** both
- Part C C2-4 (selection propagation) depends on **Part B5** category=SELECTION
- Part A is the only part shippable fully alone (would deliver sub roster + asks but no meeting structure changes)

### Recommended sequence if all approved

1. **Schema first (Day 1):** add `category` and `source` to `items[]`, write backfill script, update process.py prompt
2. **Part A in parallel (Day 1-2):** sub status pill calc + /subs template (read-only, doesn't depend on schema)
3. **Part B templates (Day 2-3):** office.html + site.html, wire look-ahead to phase-instances-v2.json
4. **Part C integrations (Day 4-5):** the 5 listed C2 items, one per build_meeting_prep section
5. **Verification + rollback test (Day 5)** — Monday packet generation, regression check, last-week diff

---

## Decision gate

Each part is independently approvable:

- ✅ **Part A only** → ship the sub roster redesign without touching meeting structure. Useful as a discrete improvement; status pills inform PMs even without 8-cat or look-ahead changes.
- ✅ **Part B only** → meeting structure overhaul; status pills inferred ad-hoc. Less integrated but doesn't require Part A first.
- ✅ **Part C only** → roadmap-only commit. No code in Phase 12; integrations get scheduled to Phase 13/14. Still valuable as alignment.
- ✅ **A + B without C** → fully functional rebuild. Risk: silos persist; C2-1 prediction missing means Office §2 is just a list, not a forecast.
- ✅ **All three** → recommended path. Highest combined value, but largest effort.

**Default if no approval:** nothing changes. Phase 12 closes as a planning artifact.

---

## Appendix — files this plan touches if approved

**New:**
- `state/ppc-history.json` — week-over-week PPC% snapshots
- `state/sub-signals.json` — historical sub-status snapshots (Phase 13 prereq)
- `monday-binder/site.template.html` — new (or refactor of existing meeting-prep with view_mode)
- `generators/sub_status_pill.py` — RED/YELLOW/GREEN/GRAY classifier
- `generators/cross_job_sub_conflict.py` — C2-6
- `scripts/backfill_item_category.py` — one-time

**Modified:**
- `weekly-prompt.md` — emit category + source field
- `process.py` — pass through new fields
- `monday-binder/build_meeting_prep.py` — render new sections, query taxonomy successors
- `monday-binder/transcript-ui/server.py` — /subs and /jobs route handlers
- `binders/*.json` — backfilled (additive only)

**Untouched (per kickoff DO NOT list):**
- `run_weekly.bat`
- `validate_accountability.py`
- `phase-taxonomy.yaml`
- `config/phase-keywords.yaml` (suggested updates from C2-12 are *proposals*, not auto-applied)
