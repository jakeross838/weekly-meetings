# m03 — Schedule Generation

**Status:** Stub. Blocked on **plan ingestion**.

This milestone picks up the schedule-intelligence work that was deferred from m02. The unifying premise: schedules need to be **plan-aware** (size, scope, specs), not built from historical medians of disparate-sized jobs. Generic baselines were the wrong foundation.

## Trigger to start

m03 unblocks when:
1. Ross Built has a reliable per-job plan ingest (size-class, scope set, spec sheet linkable)
2. BT placeholder schedules are replaced with plan-derived schedules (or we have a parallel "intended schedule" data source)

If neither lands within ~3 months, revisit whether the deferred items can be partially delivered without plans (e.g., G4 with crude size-class proxies).

## Deferred from m02

### Generator 4 — Stage-Should-Be-Doing
- For each job × current stage, compare current activity density to what *similar-size jobs* have historically done at the same stage
- Requires **size-class baselines** which require plan ingest

### Generator 7 — Schedule Reality Check
- For each job, compare current pace vs. scheduled completion date
- Project slip in calendar days
- Requires per-phase scheduled dates that are reliable (BT placeholders aren't)

### Schedule Builder (plan-aware version)
- Generate a baseline schedule for a new job from plan inputs + historical sub performance + median active-day distributions
- Supersedes the original Phase 7 scope (which was historical-median-only and would have been wrong)
- Inputs: plan size class, scope set, spec sheet, sub commitments
- Outputs: per-phase scheduled-start + scheduled-end with confidence bands

### Log Inference for Missed Days
- Detect when field activity happened but no log was filed (e.g., subs worked Saturday, log filed Monday)
- Backfill inferred activity into Phase 3 instances so density math doesn't penalize the job for un-logged work
- Heuristics: weekday gap detection, sub continuity (sub here Mon + Wed → likely here Tue), inspector signoff dates

### Size-Class Baselines
- Bucket jobs by sqft / scope tier (4k, 8k, 14k+, mod, addition, custom)
- Compute per-bucket median active-days per phase
- Replace the current "all jobs averaged together" baseline in `phase-medians.json`
- Used by G4 (stage-should-be-doing), schedule builder, and tighter G2 sub-drift comparisons

## Out of scope for m03 (still in m02 backlog or elsewhere)

- **Generator 5** (transcript pattern detection) — different problem class, may move to its own m04 if revived
- **Generator 6** (Markgraf-lesson triggers) — one-off lesson encoding pattern, may roll into G5 work
- **PM-facing UI for the meeting prep system** — Phase 6.6 ships PDFs only; an interactive page is its own scope

## Dependencies

| Item                       | Blocks                                            |
|----------------------------|---------------------------------------------------|
| Plan ingest format         | G4 size-class · Schedule Builder · G7 baselines  |
| BT-or-other schedule data  | G7 reality check                                  |
| Saturday-log decision      | Log inference (when did field crew actually work?) |

## Success criteria (when m03 ships)

1. G4 fires reliable insights — flag rate within 5-15% target band on jobs with plan data
2. G7 fires reliable insights — paces project slips ±3 days vs. truth on closeout-stage jobs
3. Schedule Builder produces a baseline schedule for a new job within 30 minutes of plan ingest
4. Log inference fills gaps without inflating density metrics on real dragging phases
5. Size-class baselines reduce G2 sub-drift false-positive rate by 30%+

## Open questions for kickoff

- Where does plan data live? (Buildertrend, Excel takeoff, separate plan-management system?)
- Is the "intended schedule" coming from BT (post-cleanup), from a separate system, or built fresh by Schedule Builder?
- Do we backfill old jobs (Markgraf, Pou, etc.) with plan data, or only new jobs?
- Are size-class buckets static (4k / 8k / 14k+) or computed from scope set?

---

*Created 2026-04-30 during m02 cutover.*
