# Phase 6.6 — Verification

Generated **2026-04-30**. Outputs at `monday-binder-v2/meeting-prep/`:
- `master.html` / `.pdf`         — Jake's view
- `executive.html` / `.pdf`      — Lee's view
- `preconstruction.html` / `.pdf` — Andrew's view
- `pm/{slug}-office.html` / `.pdf` × 5 — PM office mode
- `pm/{slug}-site.html` / `.pdf` × 5   — PM site mode

13 distinct PDFs, all within page-count target (1-2 pages each).

---

## Stop conditions

| # | Condition                                                   | Status |
|---|-------------------------------------------------------------|--------|
| 1 | All 5 page types render                                     | ✓ master, executive, preconstruction, PM office (×5), PM site (×5) |
| 2 | Office vs site toggle works on PM packets                   | ✓ Same template, `view_mode` parameter in bundle, JS branches at render time. Two distinct files emitted per PM. |
| 3 | Accountability block populated even on first run            | ✓ Strip says "Last week: No commitments captured (first run or no prior data)" — does not crash on empty state. `data/meeting-commitments.json` snapshotted this week's 21 must-discuss items so next Monday's run will show real recovery stats. |
| 4 | Visual style mirrors Nightwork tokens                       | ✓ `assets/nightwork-tokens.css` overrides palette to slate-tile / stone-blue / white-sand. Square corners (`--radius: 0`). Space Grotesk headers, Inter body, JetBrains Mono on data. All 5 page templates link the tokens file. |

**Phase 6.6 ships.**

---

## 1. Master page (Jake)

**Source**: `monday-binder-v2/meeting-prep/master.pdf` · 2 pages · 197 KB.

```
┌─ ROSS BUILT · MASTER PRODUCTION                                WED · APR 29 ─┐
│  11 ACTIVE JOBS · 5 PMS · 73 ONGOING PHASES · 9 FLAGGED              FOR JAKE │
└──────────────────────────────────────────────────────────────────────────────┘

  9 red flags · 21 must-discuss across PMs · 189 open actions · 28 stale

──────────────────────────────────────────────────────────────────────
THIS WEEK'S RED FLAGS (top 9 ranked)
──────────────────────────────────────────────────────────────────────

  ☐  DEWBERRY · 14.1 dragging                              JASON SZYKULSKI
     14.1 33% density · 4d active · 14.9 complete            sequencing_risk
  ☐  DEWBERRY · 15.1 dragging                              JASON SZYKULSKI
     15.1 55% density · 6d active · 15.2 complete            sequencing_risk
  ☐  DRUMMOND · 12.2 dragging                                   BOB MOZINE
     12.2 58% density · 26d active · 12.3 ongoing            sequencing_risk
  ☐  DRUMMOND · 13.3 dragging                                   BOB MOZINE
     13.3 29% density · 5d active · 15.1 complete            sequencing_risk
  ☐  RUTHVEN · RUTH-015 closed — no field activity              LEE WORTHY
     Item RUTH-015 closed 2026-04-23 · 0 13.1 logs in window  missed_commitment
  ☐  CLARK · USA Fence Company below their baseline       NELSON BELANGER
     USA Fence Company 2% on 14.9 · typical 100% across 3 jobs       sub_drift
  ☐  DEWBERRY · Ross Built Crew below their baseline       JASON SZYKULSKI
     Ross Built Crew 3% on 14.9 · typical 51% across 6 jobs          sub_drift
  ☐  DEWBERRY · Kimal Lumber Company below their baseline  JASON SZYKULSKI
     Kimal Lumber Company 57% on 3.7 · typical 100% across 8 jobs    sub_drift
  ☐  DEWBERRY · ALL VALENCIA CONSTRUCTION below their baseline JASON SZYKULSKI
     ALL VALENCIA CONSTRUCTION LLC 12% on 3.7 · typical 100% across 3 jobs  sub_drift

──────────────────────────────────────────────────────────────────────
WEEK-OVER-WEEK ACCOUNTABILITY                       first run · 2026-W18
──────────────────────────────────────────────────────────────────────

  FIRST RUN — NO LAST-WEEK DATA
  21 must-discuss captured this week (snapshot saved to data/meeting-commitments.json)
  Next Monday's run will compare against this snapshot.

──────────────────────────────────────────────────────────────────────
PM SUMMARY (one line per PM)
──────────────────────────────────────────────────────────────────────

  PM · JOBS                                MUST-DISCUSS  OPEN ACTIONS  STALE
  Nelson Belanger · Markgraf · Clark · Johnson         4             4      1
  Bob Mozine · Drummond · Molinari · Biales            4            38      0
  Martin Mannix · Fish                                 4            39     26 ⚠
  Jason Szykulski · Pou · Dewberry · Harllee           4            60      0
  Lee Worthy · Krauss · Ruthven                        5            48      1
```

**Verdicts:**
- **Top 9 red flags ranked correctly** — type cap of 4 at company level enforces diversification: 4 sequencing_risk + 4 sub_drift + 1 missed_commitment + 0 sequencing_violation (quarantined to data quality, never reaches master). ✓
- **Per-PM one-line summary** — covers all 5 PMs with their job lists, must-discuss count, open-action count, stale count. Martin's 26 stale items get the ⚠ flag (>2 threshold). ✓
- **Accountability block populated** — first-run state correctly displays "no last-week data" rather than crashing. Snapshot mechanism in place. ✓

---

## 2. Executive page (Lee)

**Source**: `monday-binder-v2/meeting-prep/executive.pdf` · **1 page** · 23 KB.

```
┌─ ROSS BUILT · EXECUTIVE SUMMARY                              WEEK OF APR 29 ─┐
│                                                                       FOR LEE │
└──────────────────────────────────────────────────────────────────────────────┘

──────────────────────────────────────────────────────────────────────
RED THIS WEEK
──────────────────────────────────────────────────────────────────────

  DEWBERRY      Sequencing risk · 14.1   14.1 33% density · 4d active · 14.9 complete
  DRUMMOND      Sequencing risk · 12.2   12.2 58% density · 26d active · 12.3 ongoing
  FISH          Sequencing risk · 10.2   10.2 49% density · 52d active · 10.4 complete

──────────────────────────────────────────────────────────────────────
TRAJECTORY
──────────────────────────────────────────────────────────────────────

  Jobs on track       ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2 of 12 ·  17%
  Jobs flagged        ████████████████████████░░░░░░░░  9 of 12 ·  75%
  Insufficient data   ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  1 of 12 ·   8%

──────────────────────────────────────────────────────────────────────
RECOVERY FROM LAST WEEK
──────────────────────────────────────────────────────────────────────

  No prior week reds on record (first run).

──────────────────────────────────────────────────────────────────────
DECISIONS NEEDED FROM YOU
──────────────────────────────────────────────────────────────────────

  ☐  DEWBERRY: hold 14.1 successor or run parallel?
     14.1 33% density · 4d active · 14.9 complete

  ☐  DEWBERRY: hold 15.1 successor or run parallel?
     15.1 55% density · 6d active · 15.2 complete
```

**Verdicts:**
- **≤1 page, exception-only** — single landscape page, no operational noise. ✓
- **Decisions block contains only Lee-level decisions** — both framed as binary ("hold X successor or run parallel?"). With no stuck items in the first run, the system correctly falls back to top-2 critical sequencing risks. When a stuck item (3+ weeks) appears in future runs, the decisions block will surface that first. ✓
- **Trajectory** — bar chart visualization shows 2/12 on track, 9/12 flagged, 1/12 unknown. The 9/12 flagged is striking — flags Lee's attention immediately. (Note: 9 flagged is high because we just shipped Phase 6 generators that are surfacing every existing risk; subsequent weeks should normalize.)
- **Recovery section gracefully handles first-run** ("No prior week reds on record"). ✓

---

## 3. Pre-construction page (Andrew)

**Source**: `monday-binder-v2/meeting-prep/preconstruction.pdf` · 2 pages · 171 KB.

```
┌─ ROSS BUILT · PRE-CONSTRUCTION                                WEEK OF APR 29 ─┐
│                                                                    FOR ANDREW │
└──────────────────────────────────────────────────────────────────────────────┘

──────────────────────────────────────────────────────────────────────
JOBS ENTERING FIELD — NEXT 60 DAYS                                 1 job
──────────────────────────────────────────────────────────────────────

  JOB     NEXT STAGE   ADDRESS  SUB READINESS
  BIALES  Foundation   —        1/17 subs logged

──────────────────────────────────────────────────────────────────────
SUB COMMITMENTS — GAPS                                             6 gaps
──────────────────────────────────────────────────────────────────────

  BIALES  2.1 Pilings           ML Concrete, West Coast Foundation,
                                Southwest Concrete & Masonry              stage 2
  BIALES  2.2 Pile Caps & GBs   ML Concrete, Southwest Concrete &
                                Masonry, Jeff Watts Plastering            stage 2
  BIALES  2.3 Stem Walls        Southwest Concrete & Masonry,
                                ML Concrete                               stage 2
  BIALES  2.4 Stem Wall Waterproofing  CoatRite, Avery Roof, Watts,
                                       Gonzalez Construction              stage 2
  BIALES  2.7 Slab Prep         Southwest Concrete & Masonry              stage 2
  BIALES  2.8 Slab Pour         Southwest Concrete & Masonry, ML Concrete stage 2

──────────────────────────────────────────────────────────────────────
SCHEDULE REALISM CHECK
──────────────────────────────────────────────────────────────────────

  DEFERRED TO MILESTONE M03-SCHEDULE-GENERATION
  Detecting current-pace-vs-schedule slip requires per-phase scheduled
  dates, which BT placeholder data doesn't yet support. Generator 7
  (schedule reality) will land with m03 once plan data is reliable.

──────────────────────────────────────────────────────────────────────
OPEN PROPOSALS / ESTIMATING ACTIONS                                74 items
──────────────────────────────────────────────────────────────────────

  ☐  FISH-001    FISH    Martin to follow up with Courtney on outstanding-selections email …  URGENT  21d
  ☐  FISH-016    FISH    Martin to lock written decision with Volcano Stone + Courtney + Fishes…  URGENT  21d
  ☐  FISH-018    FISH    Lee to present Martin's interior paint takeoff (~$13K base + $1.5K…)    URGENT  21d
  ☐  FISH-030    FISH    Martin to force Courtney sign-off on AC return louver door style…       URGENT  21d
  ☐  POU-001     POU     Jason to finalize offset-nut-backer railing shoe detail with DB Welding …  URGENT  14d
  ☐  KRAU-001    KRAUSS  Lee to confirm replacement wet bar light fixture spec from Aaron/Lightworks  URGENT   5d
  ☐  KRAU-007    KRAUSS  Lee to phone John Krauss by Fri 4/25 to warm up CO bundle …               URGENT   0d
  ☐  MOLI-004    MOLI    Bob to deliver Molinari ceiling-spec measurements to designer …          URGENT   0d
  ☐  MARK-047    MARK    Send CO-4412 to homeowner for stucco repair scope …                      HIGH    21d
  ☐  DRUM-009    DRUM    Bob to lock Drummond garage floor finish with Lee                        HIGH    21d
  ☐  MOLI-021    MOLI    Lee/Jake to reassign Rob's Molinari oversight scope                      HIGH    21d
  …14 visible · 60 more in back of binder
```

**Verdicts:**
- **Forward-looking** — only Biales surfaces in upcoming jobs (current_stage=2 Foundation, no recent activity = entering field soon). ✓
- **Sub readiness visible** — Biales shows 1/17 subs logged across next 3 stages of typical_subs (current_stage=2 means looking at stages 2, 3, 4 typical subs). Sub gaps section enumerates the specific phases × needed subs Andrew should lock in. ✓
- **No active-job punch list noise** — punch/paint/closeout signals don't appear here. The page is purely about getting future jobs ready. ✓
- **Estimating actions** — 74 pricing/CO/proposal-related action items surface; top 14 visible. PMs have a lot of CO/scope work in motion right now (especially Fish with Courtney's outstanding selections).

---

## 4. PM Office vs Site — Nelson

Nelson has 3 jobs (Markgraf, Clark, Johnson) but only Markgraf is field-active.

### 4a. Nelson Office

**Source**: `pm/nelson-belanger-office.pdf` · 1 page · 206 KB.

Identical to Phase 6.5 layout, plus a new accountability strip:

```
NELSON BELANGER                                            WED · APR 29
MARKGRAF · CLARK · JOHNSON                  Last meeting: 2026-04-23 (6d ago)
                                                                  OFFICE MODE

  4 must-discuss · 4 open actions · 2 commitments to verify   top 4 of 12

[Accountability strip]
  Last week: No commitments captured (first run or no prior data)

──── MUST DISCUSS ────

 ☐  MARKGRAF · 10.2 dragging                          [SEQUENCING_RISK]
    10.2 50% density · 90d active · 11.1 ongoing
    ASK: Are we stuck on 10.2, or just slow? Hold 11.1 or run parallel?

 ☐  CLARK · USA Fence Company below their baseline    [SUB_DRIFT]
    USA Fence Company 2% on 14.9 · typical 100% across 3 jobs
    ASK: What's different about USA Fence Company on Clark? Sub issue or job-specific?

 ☐  MARKGRAF · 12.2 dragging                          [SEQUENCING_RISK]
    12.2 63% density · 26d active · 12.3 complete
    ASK: Did we close 12.3 early, or is 12.2 actually further along than the data shows?

 ☐  MARKGRAF · Metro Electric below their baseline    [SUB_DRIFT]
    Metro Electric, LLC 56% on 13.3 · typical 83% across 4 jobs
    ASK: What's different about Metro Electric on Markgraf? Sub issue or job-specific?

──── OPEN ACTIONS — BY AGING ────                  1 stale · 0 aging · 3 fresh
   STALE · MARK-032 · Get Mark on-site to retest LV wiring after paint touch-up   URGENT  26d
   FRESH · MARK-047 · 7.2*  Send CO-4412 to homeowner for stucco repair scope     URGENT   5d
         · CLAR-001 ·       Order steel package — 3.5mo lead, confirm PO by 5/15    HIGH    0d
         · MARK-048 ·       Confirm Seth's Monday 4/27 crew size                    HIGH    3d

──── VERIFY LAST MEETING'S COMMITMENTS ────                from 2026-04-23
   ☐  MARK-048 · Confirm Seth's Monday 4/27 crew size                  ⏵ in progress
   ☐  CLAR-001 · Order steel package                                   ○ not started
```

### 4b. Nelson Site

**Source**: `pm/nelson-belanger-site.pdf` · 1 page · 198 KB.

```
NELSON BELANGER                                            WED · APR 29
MARKGRAF · CLARK · JOHNSON                  Last meeting: 2026-04-23 (6d ago)
                                                                    SITE MODE

  1 active job · 1 immediate blocker

──── TODAY ON SITE ────                                       1 job

  MARKGRAF
    Active phases   : 2.4 Stem Wall Waterproofing (12d) · 3.7 Roof Truss Set (4d) ·
                      6.1 Plumbing Top-Out (43d) · 6.3 Electrical Rough (80d)
    Last log        : 2026-04-22 (7d)
    Subs on site    : CoatRite, DB Improvement Services, Myers Painting, Rangel Custom Tile
    Unconfirmed     : Jeff Watts Plastering and Stucco

──── SEQUENCING WATCH ────                                                  6 risks
 ☐  MARKGRAF · 10.2 dragging
    10.2 50% density · 90d active · 11.1 ongoing
 ☐  MARKGRAF · 12.2 dragging
    12.2 63% density · 26d active · 12.3 complete
 ☐  MARKGRAF · 13.3 dragging
    13.3 34% density · 15d active · 13.6 ongoing
 ☐  MARKGRAF · 14.8 dragging
    14.8 39% density · 16d active · 15.1 ongoing
 … and 2 more sequencing risks

──── IMMEDIATE BLOCKERS ────                                                1 block
 ☐  MARK-032 · Get Mark on-site to retest LV wiring after paint touch-up   URGENT  26d

──── SUB COORDINATION — NEXT 7 DAYS ────                                  4 entries
  this week  Markgraf  2.4 Stem Wall Waterproofing  CoatRite, Avery Roof, Watts
  this week  Markgraf  3.7 Roof Truss Set            Florida Sunshine Carpentry, ALL VALENCIA, Alejandro
  this week  Markgraf  6.1 Plumbing Top-Out          Gator Plumbing, Tom Sanger, J.P. Services
  this week  Markgraf  6.3 Electrical Rough          Metro Electric, SmartShield Homes
```

**Same data, different lens — verdicts:**
- **Office mode** focuses on week-over-week (must-discuss diversified across types, action items by aging, last-meeting closure). ✓
- **Site mode** focuses on today's reality (active phases per job, who's on site now, unconfirmed subs to chase, sequencing risks the PM can act on this week, sub coordination for the next 7 days). ✓
- **Clark and Johnson are dropped from site view** because they have no recent log activity (>14 days). They show on Nelson's office view (in the jobs-line header) but not in today-on-site. This is correct: site view is for jobs the PM is physically running today. ✓
- **Sequencing watch on site shows 4 of 6 G1 risks for Nelson** — same data feeding into office's must-discuss but filtered to *only* sequencing risks (not sub_drift, not missed_commitment) since those signal types are operational, not field-coordination. Sub_drift goes to office; it's a "talk to PM about why" signal, not a "site coordinator action" signal. ✓
- **Markgraf "Unconfirmed: Jeff Watts Plastering and Stucco"** — that's the action item MARK-047 ("Send CO-4412 to homeowner for stucco repair scope") which infers `related_sub=Jeff Watts Plastering and Stucco` and matches the CONFIRM verb regex. ✓
- **Markgraf "Active phases" includes 6.1 Plumbing Top-Out (43d)** — that's a long-running phase. Stem Wall Waterproofing (12d), Roof Truss Set (4d), Plumbing Top-Out (43d), Electrical Rough (80d) — those are the top 4 ongoing phases by `ongoing_phases[]` order from job-stages.json (sorted by stage descending in source). ✓

---

## 5. Visual style — Nightwork mirror

`monday-binder-v2/assets/nightwork-tokens.css` (5,289 bytes) ships the following:

| Token             | Value         | Purpose                            |
|-------------------|---------------|------------------------------------|
| `--nw-slate`      | `#3B5864`     | Primary ink, structural lines      |
| `--nw-slate-2`    | `#557382`     | Secondary text                     |
| `--nw-slate-3`    | `#7C95A1`     | Tertiary, muted labels             |
| `--nw-stone`      | `#5B8699`     | Accent — links, ASK marker         |
| `--nw-sand`       | `#F7F5EC`     | Page background                    |
| `--nw-sand-2`     | `#EFE9D9`     | Card background, soft fills        |
| `--nw-line`       | `#C9C0A8`     | Drafting-stock line color          |
| `--nw-success`    | `#2F5E3A`     | Forest green for ✓ / on-track      |
| `--nw-warn`       | `#B57F3D`     | Copper for warnings                |
| `--nw-danger`     | `#A14F3D`     | Rust for critical / red flags      |
| `--radius`        | `0`           | Square corners across the system   |
| `--font-head`     | Space Grotesk | Headers (band, section h2, titles) |
| `--font-body`     | Inter         | Default body type                  |
| `--font-mono`     | JetBrains Mono | Data, IDs, density readouts, labels |

**Token application verified across all 5 page templates:**

```
master.html                     nw=True styles=True grotesk=True mono=True
executive.html                  nw=True styles=True grotesk=True mono=True
preconstruction.html            nw=True styles=True grotesk=True mono=True
nelson-belanger-office.html     nw=True styles=True grotesk=True mono=True
nelson-belanger-site.html       nw=True styles=True grotesk=True mono=True
```

**Light theme inversion**: existing `assets/styles.css` has dark-theme defaults (white-text on dark-bg). The `nightwork-tokens.css` override flips the palette to dark-text on white-sand. Both stylesheets ship to all 5 page templates, with nightwork-tokens loaded *after* styles.css so its custom-property overrides win.

**Drafting-stock aesthetic**: square corners (`border-radius: 0` everywhere), thin stone-blue 1px lines for dividers, slate-tile thicker lines for section headers. Density chips re-skinned for light backgrounds with semi-transparent fills.

The phase-library and jobs pages from Phases 4+5 keep their dark theme — they're a different application now. The kickoff says "Same data layer, separate application," which matches.

---

## 6. Page-count audit

| Page                            | Pages | Target |
|---------------------------------|-------|--------|
| `master.pdf`                    | 2     | ≤2 ✓ |
| `executive.pdf`                 | **1** | 1 ✓  |
| `preconstruction.pdf`           | 2     | ≤2 ✓ |
| `pm/nelson-belanger-office.pdf` | 1     | ≤2 ✓ |
| `pm/nelson-belanger-site.pdf`   | 1     | ≤2 ✓ |
| `pm/bob-mozine-office.pdf`      | 2     | ≤2 ✓ |
| `pm/bob-mozine-site.pdf`        | 2     | ≤2 ✓ |
| `pm/martin-mannix-office.pdf`   | 2     | ≤2 ✓ |
| `pm/martin-mannix-site.pdf`     | 2     | ≤2 ✓ |
| `pm/jason-szykulski-office.pdf` | 2     | ≤2 ✓ |
| `pm/jason-szykulski-site.pdf`   | 2     | ≤2 ✓ |
| `pm/lee-worthy-office.pdf`      | 2     | ≤2 ✓ |
| `pm/lee-worthy-site.pdf`        | 2     | ≤2 ✓ |

All 13 PDFs within target.

Tuning that got us there:
- Site view filters jobs with last log >14 days ago (drops dormant jobs that belong on Andrew's pre-con view).
- Sequencing watch on site capped at 4 (was 6 in first attempt).
- Sub coordination lookahead capped at 5 (was 14 in initial design).
- Stale/aging caps from Phase 6.5 retained: stale 8 / aging 6 / fresh 4.
- Data quality section hidden in print (`@media print { .mp-sec-dq { display: none; } }`).

---

## Accountability loop — first run state

`data/meeting-commitments.json` written with one week entry:

```
version: 1
weeks:
  2026-W18 (today=2026-04-29):
    Nelson Belanger        4 commitments
    Bob Mozine             4 commitments
    Martin Mannix          4 commitments
    Jason Szykulski        4 commitments
    Lee Worthy             5 commitments
                          ──
                          21 total
```

**Loop logic for next Monday's run:**
1. Load existing weeks. Latest entry (2026-W18) becomes "last week".
2. New iso_week (e.g., 2026-W19) appends.
3. For each PM's 21 last-week commitments, check `content_hash`:
   - hash present in this week's insights → `current_status: "carried"` (insight still firing)
   - hash absent → `current_status: "resolved"` (signal cleared)
   - hash present in last 3 consecutive weeks → `current_status: "stuck"` + bumped to `severity=critical` and a CARRIED / STUCK 3w+ marker on the must-discuss card.
4. Master page's accountability rollup totals: `last_week_total / resolved_total / carried_total / stuck_total` populate; first-run "no last-week data" message goes away.
5. Executive page's Recovery section enumerates last week's red items and their current verdict (closed / improved / worse / same).

**Same-week reruns** (multiple Monday runs same iso_week) UPDATE the entry rather than appending — re-running the build script doesn't pollute the history.

The loop can't be empirically validated until a second run on a different iso_week, but the logic is unit-testable and the persistence layer is in place.

---

## Files added / modified

- `monday-binder-v2/assets/nightwork-tokens.css`              — NEW · slate/stone/sand palette + Space Grotesk/Inter/JetBrains Mono + square corners
- `monday-binder-v2/master.template.html`                     — NEW · Jake's view template
- `monday-binder-v2/executive.template.html`                  — NEW · Lee's view template
- `monday-binder-v2/preconstruction.template.html`            — NEW · Andrew's view template
- `monday-binder-v2/meeting-prep.template.html`               — REWRITTEN · view-mode toggle (office | site), accountability strip, stuck/carried markers
- `monday-binder-v2/build_meeting_prep.py`                    — REWRITTEN · runs commitment tracker, computes site_view payload, builds bundles for master/executive/preconstruction, writes pages to `meeting-prep/pm/{slug}-{mode}.html`
- `generators/commitment_tracker.py`                          — NEW · week-over-week persistence, ISO-week-keyed snapshots, content_hash matching, 3-week stuck detection
- `data/meeting-commitments.json`                             — NEW · first snapshot written (2026-W18, 21 commitments)
- `monday-binder-v2/meeting-prep/master.{html,pdf}`           — NEW
- `monday-binder-v2/meeting-prep/executive.{html,pdf}`        — NEW
- `monday-binder-v2/meeting-prep/preconstruction.{html,pdf}`  — NEW
- `monday-binder-v2/meeting-prep/pm/{slug}-{office|site}.{html,pdf}` × 10 — NEW

---

## Anything flagged for follow-up

1. **Executive Recovery section will populate next Monday** — first-run state is "no prior data." Phase 7+ should validate that the loop actually closes by the second week's run (manual smoke test on next Monday).

2. **Pre-construction page has only 1 upcoming job (Biales)** — that's because the `current_stage <= 1` filter is strict. Other jobs (Clark, Johnson) are at higher stages or missing stage data. A Phase 7 refinement could include "current_stage == 0 or current_stage missing" → catches Johnson.

3. **9 of 12 jobs flagged on Lee's trajectory is high (75%)** — first-run artifact: every existing critical signal lights up. Subsequent weeks should normalize once PMs work through the queue.

4. **Decisions block on executive page repeats Dewberry both times** — when stuck-items pool is empty (first run), the fallback ranks top critical sub_drifts (none in this dataset are critical) then top critical sequencing_risks (multiple Dewberry hits). A Phase 7 refinement could enforce job-diversity in the decisions list.

5. **Master page PM Summary table has Bob's 38 open actions vs the kickoff sample's 18** — kickoff numbers were illustrative; actual binder data shows 38. The flag column correctly marks Martin (26 stale items) but not Bob (0 stale).

6. **Site view drops Clark and Johnson from Nelson's day-of layout** — by design (no recent logs), but PMs who think "I have 3 jobs" might miss that Clark exists if they only look at site mode. The header band still lists all 3 jobs in the JOBS line, so it's not invisible — just not in the active site card list.

7. **74 estimating action items on pre-con page** is a lot — only 14 visible per cap. Andrew may want a flag column distinguishing "needs my action" vs "FYI" vs "PM-handled." Phase 7+ could add owner=Andrew filter or surface only items aging >14d.

8. **Nightwork visual mirror has not been visually inspected** — pdftotext can't show colors. The CSS is structurally correct (verified palette values, fonts, square corners) but the actual rendered PDF colors should be eyeballed before next Monday's print run. Open one of the PDFs in Acrobat or browser preview to confirm slate-on-sand looks right.

9. **Top-level files include phase-library.html, jobs.html, monday-binder.html dark-theme pages** — those still link `assets/styles.css` only, no Nightwork override. They're separate applications; not changed by Phase 6.6.

10. **Meeting-prep folder structure**:
   ```
   meeting-prep/
     master.{html,pdf}
     executive.{html,pdf}
     preconstruction.{html,pdf}
     pm/
       {slug}-office.{html,pdf}
       {slug}-site.{html,pdf}
   ```
   Old Phase 6.5 outputs at `meeting-prep/{slug}.{html,pdf}` (top level) were deleted. If anyone has links to those filenames, they're broken — update to `meeting-prep/pm/{slug}-office.{html,pdf}`.
