# Phase 6.5 — Meeting Prep Format Redesign + Open Item Cleanup

The Meeting Prep page works as a data dump but doesn't work as a meeting tool. PMs need a checklist, not a report. Plus 4 open items from VERIFICATION.md need disposition before Phase 7.

## Part A — Open item disposition

1. **Sequencing_violation grouping** — split into separate "Data Quality" bucket. These aren't field signals; they're classifier artifacts pretending to be field signals. Move out of the must-discuss ranking entirely. Surface them in a separate compact list at the bottom of the page (or hide behind a toggle). Don't let them dilute the must-discuss top 5.

2. **Top-N is 100% sequencing_risk** — add per-type quotas to ranking. The top 5 must-discuss should be diversified: max 2 of any single insight type. Forces drift, missed commitment, and other signals into the top 5 even when one generator is loud.

3. **Enrichment phase mismatches (HARL-009, RUTH-010)** — add confidence score to enrichment. If confidence <0.7, skip enrichment for that item rather than guessing. Existing inferred fields stay; new enrichment runs use the threshold.

4. **FieldCrew unmapped PM** — fine to leave unmapped. FieldCrew is internal Ross Built crew, not a real job. Filter it out of insight generation entirely. Add to a `excluded_jobs` list in config.

## Part B — Meeting Prep redesign

### What's wrong with the current format

- Reads like a report, not a checklist
- Long-winded narrative blocks
- No clear "work through this in order" structure
- Hard to mark progress during a meeting
- Action items separated from the insights they relate to (PM has to cross-reference manually)

### Target format — single-page meeting checklist

The page is one column, top-to-bottom workflow. PM walks through it in order. Each item is a discrete checkbox-style block they can work through, mark, and move on.

```
┌─────────────────────────────────────────────────────────────────┐
│  NELSON BELANGER                              MON · APR 29       │
│  CLARK · MARKGRAF                  Last meeting: 7d ago          │
└─────────────────────────────────────────────────────────────────┘

5 must-discuss · 8 open actions · 3 commitments to verify

────────────────────────────────────────────────────────────────────
MUST DISCUSS
────────────────────────────────────────────────────────────────────

  ☐  MARKGRAF · Punch dragging
     TNT 53% density · 23d ongoing · 4d active in last 14d
     ASK: Is TNT pulling crew, or is the punch list shrinking?

  ☐  MARKGRAF · MK-014 Smarthouse closed without field activity
     Item closed 4/22 · 0 Smarthouse logs in confirmation window
     ASK: Was Smarthouse actually here Friday?

  ☐  CLARK · 2.1 Pilings still ongoing while 2.2 has logs
     ASK: Pile caps started before pilings done?

  ☐  MARKGRAF · TNT below their own baseline
     14.1 at 2% density vs typical 49%
     ASK: Sub issue or job-specific?

  ☐  MARKGRAF · Owner walk in 5d, cleaning not logged
     Last cleaning log 4/24 · Owner walk 4/27
     ASK: Who's running final clean? Confirmed Friday?

────────────────────────────────────────────────────────────────────
OPEN ACTIONS — by aging
────────────────────────────────────────────────────────────────────

  STALE (>14d)
  ☐  MK-014  Confirm Smarthouse Friday              URGENT  15d
  ☐  MK-018  First Choice cabinets touch-up         HIGH    16d
  ☐  CL-002  Capstone shop drawings                 URGENT  32d

  AGING (8-14d)
  ☐  MK-021  Order replacement weatherstrip         NORMAL  10d
  ☐  CL-008  Confirm pile cap pour date             HIGH    12d

  FRESH (<8d) [4]   ▸ expand

────────────────────────────────────────────────────────────────────
VERIFY LAST MEETING'S COMMITMENTS
────────────────────────────────────────────────────────────────────

  ☐  MK-009  Order weatherstrip                      ✓ confirmed in field
  ☐  MK-010  Confirm DB Welding measurements         ⚠ marked done, no field log
  ☐  CL-005  Capstone proposal                       ⏵ in progress

────────────────────────────────────────────────────────────────────
DATA QUALITY (review when time permits)                       [12]  ▸
────────────────────────────────────────────────────────────────────
```

### Design rules

- **One column.** No side-by-side anything.
- **Every must-discuss item has 3 lines max.** Title, one-line evidence summary, ask. The full evidence chain stays in the underlying data but doesn't print.
- **Action items are inline checkboxes** with ID, description, priority, age. No separate "narrative" per action.
- **Commitments verification is its own block** because it answers a different question ("did last week's commitments actually happen") than open actions.
- **Data quality bucket is collapsed by default.** It's not for the meeting. It's for cleanup later.
- **Print on one landscape page.** Shorter is better. If a PM has 15 must-discuss items, show top 5 inline + collapse the rest. The meeting can't cover 15 anyway.

### Tone shift

Current asks read like reports: "Confirm whether TNT is allocating sufficient crew resources to the punch repair phase given the current density measurement of 53% over a 23-day ongoing period."

Replace with: "Is TNT pulling crew, or is the punch list shrinking?"

Plain conversational questions. The kind of thing Jake or a PM would actually say in a meeting.

## Step order

1. Apply Part A open item fixes:
   - Move sequencing_violation to data quality bucket
   - Add per-type quotas to top-N ranking (max 2 per type)
   - Add confidence threshold to enrichment (skip <0.7)
   - Filter FieldCrew from insight generation
2. Re-run all 3 generators with new rules
3. Rebuild meeting-prep template per Part B layout
4. Re-render all 5 PM pages + PDFs
5. Update VERIFICATION.md with before/after comparison

## Verification (paste-back required)

1. **New top 10 insights across company** — should now be diversified (not 100% sequencing_risk). Show type breakdown.
2. **Nelson's new Meeting Prep page** — paste full content. Confirm:
   - Top 5 must-discuss diversified (≥2 different insight types)
   - Each item is 3 lines max
   - Asks read conversationally
   - One landscape page (or two max if data is dense)
3. **Bob's new Meeting Prep page** — same paste, different PM. Same constraints.
4. **Data quality bucket count** — how many sequencing_violation insights are there per PM? Should be substantial (the 76 from before move here).
5. **Enrichment confidence stats** — what % of action items now have enriched fields, vs skipped due to <0.7 confidence?
6. **PDF page count** — Nelson and Bob's PDFs should each be 1 page (or 2 max).

## Stop conditions

Phase 6.5 ships when:
- Top 5 must-discuss is diversified across insight types
- Meeting Prep PDFs print on 1 page (or 2 max when truly necessary)
- Asks read conversationally, not like reports
- Sequencing_violation insights are quarantined to data quality bucket
- FieldCrew is filtered out

If the redesigned page still reads like a report, iterate on the design before shipping. The format IS the deliverable.

Begin.
