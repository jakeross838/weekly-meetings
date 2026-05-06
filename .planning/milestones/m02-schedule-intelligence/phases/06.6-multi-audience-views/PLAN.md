# Phase 6.6 — Meeting Workflow & Multi-Audience Views

The data is right. The format is now a checklist. Next: make it a real meeting workflow that serves four audiences (Jake, Lee, Andrew, PMs) across two meeting types (office, site), with an accountability loop that closes week-over-week.

Adopt Nightwork's visual style for this binder system. Same data layer, separate application. CSS/typography mirror only — don't fork code.

## The four audiences and what they need

```
  Jake          Runs office meetings. Master view across jobs. Accountability tracker.
  Lee Ross      Owner. Exception-only summary. "What's red this week."
  Andrew Ross   Pre-construction. Upcoming jobs + sub commitments + schedule realism.
  PMs (5)       Their own jobs. Same data, scoped to their packet.
```

## The two meeting types

```
  OFFICE PRODUCTION (weekly with Jake/Lee/Andrew + PMs)
    Focus: week-over-week trajectory, GP exposure, sub performance,
           decisions needed, commitments closure
    Cadence: weekly
    
  SITE PRODUCTION (PM with field crew/subs)
    Focus: today's work, 7-day coordination, immediate blockers, sequencing
    Cadence: per-job, typically weekly
```

Same data, different lens. One template that toggles via a `view_mode` parameter, not two separate systems.

## Required deliverables

### 1. Five page types

```
  /master.html              Jake's view — all jobs, all PMs, master accountability
  /executive.html           Lee's view — exception summary, red flags only
  /preconstruction.html     Andrew's view — upcoming jobs, sub readiness, scope
  /pm/{slug}-office.html    PM's office meeting packet (current style, refined)
  /pm/{slug}-site.html      PM's site meeting packet (different focus, same data)
```

Plus the existing PDFs for each.

### 2. Accountability loop (the missing piece)

Every meeting page tracks three week-over-week states:

```
  COMMITTED LAST WEEK     items raised in last meeting, with owner + due date
  RESOLVED THIS WEEK      items now closed (with field confirmation)
  CARRIED OVER            items still open, age incremented
```

Implementation: every must-discuss item resolved in the meeting either (a) gets marked done, (b) generates an action item with owner + due date, or (c) escalates. Track in a new file: `data/meeting-commitments.json`.

When next week's page renders, the COMMITTED LAST WEEK block shows what was committed and whether each closed. If the same item appears for 3 consecutive weeks, it auto-flags as "stuck" and bumps to top of must-discuss with severity=critical.

### 3. View toggle (office vs site)

PM packets render with `?view=office` or `?view=site` query parameter. Same template, different sections shown:

**Office mode shows:**
- Must-discuss (top 5)
- Open actions by aging
- Commitments verification
- Week-over-week accountability block
- GP exposure flags (when we have that data)
- Schedule trajectory (current vs CO target)

**Site mode shows:**
- Today's active phases per job
- 7-day look-ahead (sequencing, who's on site)
- Immediate blockers
- Sub coordination needs
- Field-only action items (filter by type=FIELD)

Both modes share the same header and footer.

## Page-by-page structure

### Master (Jake's view)

```
┌─────────────────────────────────────────────────────────────────┐
│  ROSS BUILT · MASTER PRODUCTION              MON · APR 29        │
│  12 active jobs · 5 PMs · 23 ongoing phases · 6 flagged          │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
THIS WEEK'S RED FLAGS (across all jobs)
────────────────────────────────────────────────────────────────────

  ☐  MARKGRAF · Punch dragging · Nelson
     TNT 53% density · CO target 4/27 (in 5d)
     OWNER: Nelson · NEXT: confirm crew Friday

  ☐  DRUMMOND · TNT below own baseline · Bob
     14.1 at 2% density vs typical 49%
     OWNER: Bob · NEXT: site visit, decide replacement

  ☐  CLARK · Capstone shop drawings 32d open · Nelson
     STALE · escalating to Andrew if not closed this week
     OWNER: Nelson → Andrew · NEXT: hard call today

  [up to 10, ranked by severity × age]

────────────────────────────────────────────────────────────────────
WEEK-OVER-WEEK ACCOUNTABILITY
────────────────────────────────────────────────────────────────────

  Last week: 18 must-discuss items raised
    14 resolved   · 78%  ✓
     3 carried    · stale watch
     1 escalated  · Capstone shop drawings

  This week: 22 must-discuss items
    [count breakdown by job]

────────────────────────────────────────────────────────────────────
PM SUMMARY · ONE LINE PER PM
────────────────────────────────────────────────────────────────────

  Nelson    2 jobs · 6 must-discuss · 11 open actions · 2 stale
  Bob       4 jobs · 9 must-discuss · 18 open actions · 4 stale  ⚠
  Martin    1 job  · 3 must-discuss · 4 open actions  · 0 stale
  Jason     3 jobs · 7 must-discuss · 12 open actions · 1 stale
  Lee W.    2 jobs · 4 must-discuss · 7 open actions  · 1 stale

  Click any PM row → expand to their full packet inline
```

### Executive (Lee Ross's view)

Strict exception-only. No noise.

```
┌─────────────────────────────────────────────────────────────────┐
│  ROSS BUILT · EXECUTIVE SUMMARY              WEEK OF APR 29      │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
RED THIS WEEK (3)
────────────────────────────────────────────────────────────────────

  MARKGRAF      CO at risk            5d to walk · 4 phases ongoing
  DRUMMOND      Sub performance       TNT below baseline, paint stalled
  CLARK         Sub commitment        Capstone 32d open, no movement

────────────────────────────────────────────────────────────────────
TRAJECTORY
────────────────────────────────────────────────────────────────────

  Jobs on track ........... 8 of 12  (67%)
  Jobs flagged ............ 3 of 12
  Jobs unknown ............ 1 of 12  (insufficient recent data)

────────────────────────────────────────────────────────────────────
RECOVERY FROM LAST WEEK
────────────────────────────────────────────────────────────────────

  Last week's red items: 4
    Closed:       2  (Markgraf cabinets, Pou framing)
    Improved:     1  (Drummond paint - now Bob's call)
    Worse:        1  (Clark Capstone)

────────────────────────────────────────────────────────────────────
DECISIONS NEEDED FROM YOU
────────────────────────────────────────────────────────────────────

  ☐  Drummond: replace TNT or stay course?
  ☐  Capstone escalation: Andrew take over or hard close?
```

### Pre-Construction (Andrew's view)

Different time horizon — looks forward, not at active jobs.

```
┌─────────────────────────────────────────────────────────────────┐
│  ROSS BUILT · PRE-CONSTRUCTION               WEEK OF APR 29      │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
JOBS ENTERING FIELD IN NEXT 60 DAYS
────────────────────────────────────────────────────────────────────

  [Job]            [Stage entry]    [Days out]    [Sub readiness]
  Biales           Site Work         12d           7/10 subs locked
  [job]            [stage]           [days]        [N/N subs]

────────────────────────────────────────────────────────────────────
SUB COMMITMENTS — GAPS
────────────────────────────────────────────────────────────────────

  Subs not yet locked for jobs starting in 60d:
  [list with job/phase/days-out]

────────────────────────────────────────────────────────────────────
SCHEDULE REALISM CHECK
────────────────────────────────────────────────────────────────────

  Active jobs where current pace vs schedule shows slip:
  [job · phase · pace · projected slip]

────────────────────────────────────────────────────────────────────
OPEN PROPOSALS / ESTIMATING ACTIONS
────────────────────────────────────────────────────────────────────

  [from action items where owner=Andrew or type=PRICING/ESTIMATE]
```

### PM Office (existing style, refined)

Keep the Phase 6.5 design. Add at top:

```
LAST WEEK · COMMITMENTS RECAP
  ✓ 4 of 6 closed
  ⚠ 2 carried over to this week (highlighted in must-discuss)
```

### PM Site (new view)

Different focus. Same template, different sections.

```
┌─────────────────────────────────────────────────────────────────┐
│  NELSON BELANGER · SITE MEETING              MON · APR 29        │
│  CLARK · MARKGRAF                                                │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
TODAY ON SITE
────────────────────────────────────────────────────────────────────

  MARKGRAF
    Active phases: 15.2 Punch Repairs (TNT, day 23)
    Subs expected: TNT, SmartShield
    Subs unconfirmed: Smarthouse (per MK-014)

  CLARK
    Active phases: 2.1 Pilings (West Coast, day 8)
    Subs expected: West Coast, ML Concrete
    Subs unconfirmed: none

────────────────────────────────────────────────────────────────────
NEXT 7 DAYS — WHO NEEDS TO BE WHERE
────────────────────────────────────────────────────────────────────

  [Phase × sub × job × scheduled days, sequenced]

────────────────────────────────────────────────────────────────────
IMMEDIATE BLOCKERS
────────────────────────────────────────────────────────────────────

  [Action items where type=FIELD AND priority=URGENT]

────────────────────────────────────────────────────────────────────
SEQUENCING WATCH
────────────────────────────────────────────────────────────────────

  [Phases where successor is scheduled but predecessor incomplete]
```

## Visual style — Nightwork mirror

Apply Nightwork's design system:
- Slate-tile, stone-blue, white-sand palette (`#3B5864`, `#5B8699`, `#F7F5EC`)
- Space Grotesk for headers, Inter for body, JetBrains Mono for data
- Square corners, no rounded
- Drafting-stock aesthetic
- Density chips and status icons stay (functional)

Save Nightwork-style tokens to `monday-binder-v2/assets/nightwork-tokens.css`. Don't fork Nightwork code; just mirror the look.

## Step order

1. Build `data/meeting-commitments.json` schema + migration logic that captures must-discuss items from current week's pages as commitments
2. Add `view_mode` parameter to PM template (office | site)
3. Build master.html template (Jake's view)
4. Build executive.html template (Lee's view)
5. Build preconstruction.html template (Andrew's view)
6. Add accountability block to all PM pages
7. Apply Nightwork visual tokens across all pages
8. Re-render everything
9. Update VERIFICATION.md

## Verification (paste-back required)

1. **Master page** — paste rendered content for Jake. Confirm: top 10 red flags ranked correctly, PM summary one line per PM, accountability block populated
2. **Executive page** — Lee's view. Confirm: ≤1 page, exception-only, decisions block contains only Lee-level decisions
3. **Pre-construction page** — Andrew's view. Confirm: forward-looking, sub readiness visible, no active-job punch list noise
4. **Nelson office vs site** — paste both. Same Nelson data, different focus. Site page should show today's expected subs; office page should show week-over-week
5. **Visual style applied** — paste a screenshot or describe the styling. Slate/stone/sand palette, Space Grotesk, JetBrains Mono on data
6. **Page count audit** — every PM packet ≤2 pages each. Master ≤2. Executive 1. Pre-con ≤2.

## Stop conditions

- All 5 page types render
- Office vs site toggle works on PM packets
- Accountability block populated (even if first week shows zero last-week items)
- Visual style mirrors Nightwork tokens

If a page is unclear who it's for or has more than one purpose, redesign before shipping. Each page serves one audience in one mode.

Begin.
