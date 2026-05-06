# m04 — Schedule Prediction from Daily Log Activity

**Status:** NOT STARTED — ticketed only (2026-05-01)

> Phase 11 work. Distinct from `m03-schedule-generation` (plan-aware schedule builder, blocked on plan ingest). m04 derives forward predictions from *what's actually happening on site* — daily-log activity vs. historical phase medians — without depending on Buildertrend's planned schedule (which is unreliable at Ross Built).

## Premise

Buildertrend planned schedules are inaccurate at Ross Built. Forward-looking schedule must be derived from **actual daily-log activity** (subs physically on site), not BT's plan dates. The Phase 3 data layer is the foundation:

- `data/phase-instances-v2.json` — per-(job, phase) `first_log_date`, `last_log_date`, `primary_active_days`, `primary_density`, `bursts[]`
- `data/phase-medians.json` — 72 phase medians: `median_active_days`, `median_span_days`, P25-P75 range, sample size, confidence
- `config/phase-taxonomy.yaml` — 84 phases with `predecessors`, `successors`, `parallel_with` (the dependency graph)

Plus the sub-side data from m02:
- `data/sub-phase-rollups.json` — sub-level `primary_active_days_median` per phase, used to adjust forward estimate based on which sub is on a given phase

## Scope

1. **Predictive layer that estimates "phase X is N% through"**

   For each ongoing phase instance: `progress_pct = primary_active_days / phase_median.median_active_days`. Cap at 100%; flag values >150% as "dragging beyond median + tail".

   Open question: pure days-vs-median, or weighted by density? An ongoing phase with high density (continuous work) at 80% of median is in different shape than one at 80% of median with scattered work.

2. **Forward CO estimation**

   For each job: take `current_stage` + `ongoing_phases[]` + remaining phases per `phase-taxonomy.yaml` → walk the dependency graph forward. For each remaining phase, draw the duration from its phase-median distribution. Sum (with parallelization where `parallel_with` allows). Output: a calendar-day estimate of when the job hits stage 15 (closeout) → CO.

3. **Confidence bands**

   - Size-class adjustment — small house (4k sqft) ≠ medium (8k) ≠ large (14k+). Phase 3 medians lump everything together. m04 needs to bucket if we want narrow bands.
   - Sub-mix adjustment — `phase_median * (sub_specific_median / phase_median)` if the assigned sub deviates from the phase-wide median.
   - Output an `(P25, P50, P75)` triple, not a point estimate. Don't claim more precision than the data supports.

4. **Per-job forward timeline UI**

   NOT a gantt chart. More like:
   > **Fish · Closeout estimate: mid-July to early August**
   > 
   > You're here: stage 14 Exterior Finish (Pool Equipment 50%, Stucco Finish 30%)
   > Next phases: 15.1 Punch Walk (typical 6d) · 15.2 Punch Repairs (typical 18d) · 15.3 Final Cleaning (typical 4d)
   > 
   > Confidence: medium — sub mix typical for these phases at Ross Built, but no size-class baseline yet.

   Render in the existing dashboard (likely a new section on `/jobs/<slug>` job detail page, or a dedicated `/predict` view).

## Blockers / unknowns

1. **Calibration data needed.** How accurate are existing phase medians as predictors? Backtest before committing to the build. Take 5 jobs that completed in 2024-2025, run the predictor against the data state at their start date, compare predicted CO against actual CO. If MAE > 30 days, the foundation isn't strong enough for the v1 UI claim.

2. **"Phase X% complete" formal definition.** Candidates:
   - `active_days / median_active_days` — simple, biases toward over-confidence on dense phases
   - `(active_days × density) / (median_active_days × phase_median_density)` — accounts for density, but the math gets hand-wavy
   - Burst-based — "this phase typically has N bursts; we've seen M; we're at M/N"
   
   Decision needed before any predictor code.

3. **Size-class buckets — now or later?** The first version could use global medians and ship faster. The downside is wide confidence bands. The size-class approach forces a job-classification step (4k / 8k / 14k+) that doesn't exist anywhere yet. Lean toward starting with global medians and adding size-class adjustment in v2.

4. **Sub-mix adjustment math.** `phase_median × (sub_specific_median / phase_median)` is a naïve ratio. Real-world sub variance is bigger than the math implies — Watts on stucco is faster than the phase median, but his variance per-job is also wider than the phase variance. Need to think about whether to predict a wider or narrower band when a "fast sub" is assigned.

## Out of scope

- **Buildertrend planned schedule capture** — intentionally abandoned. The deprecated `_archived/sheets-writers/scrape-schedules-to-sheets.js` in the buildertrend-scraper project preserves the page selectors if anyone ever revives this path; m04 does not depend on it.
- **Plan ingest from external sources** — that's the m03 stub's concern. m04 works without plans.
- **Real-time critical path computation** — nice-to-have, not v1. The dependency graph in `phase-taxonomy.yaml` is enough for "next phases" walk; full CPM math is a separate exercise.
- **Per-sub schedule recommendations** — "you should book Watts for week of X" is downstream of the predictor, not part of v1.

## Estimated effort

**2–3 weeks of focused work AFTER calibration spike.**

Calibration spike is the gate. If it shows the foundation is solid, the build is mostly UI + API endpoints (similar in shape to Phase 10's `/jobs/<slug>` detail). If it shows the foundation is weak, the next move is investing in better median data (size-class buckets, log-inference for missed days) before any predictor work.

## Recommended kickoff sequence

1. **Day 1 — calibration spike** (read-only):
   - Pick the 5 most recently-completed Ross Built jobs (Markgraf will be one once it CO's; Drummond likely; need to check completion dates).
   - For each, capture the data state as of the job's actual start (need to backfill `first_log_date` of stage-1 phase as the "now" for the simulation).
   - Run a naïve predictor against each → predict CO.
   - Compare predicted CO vs. actual CO. Compute MAE in days, also track over-prediction vs. under-prediction bias.
   - Decision gate: MAE < 30 days → proceed to build; > 30 days → invest in better medians first.

2. **Week 1 — predictor module**:
   - `generators/g7_schedule_predictor.py` (new) — reads phase-instances + medians + taxonomy, produces `data/job-predictions.json` with per-job `(predicted_co_p25, predicted_co_p50, predicted_co_p75, current_progress_pct, next_phases[])`.
   - Decision: which "% complete" formula. Document in module docstring.
   - Run end-to-end against current 12 jobs. Spot-check by hand against real status.

3. **Week 2 — UI integration**:
   - Add a "Forward estimate" section to `/jobs/<slug>` (one section, not a new page).
   - Show: estimate range, confidence label, current progress per ongoing phase, next-3-phases preview.
   - Cross-link from master.pdf ("3 jobs flagged as predicted-late vs. CO target") if/when targetCO data is reliably populated.

4. **Week 3 — confidence bands + monitoring**:
   - Size-class bucketing (if calibration spike showed bias by size).
   - Sub-mix adjustment.
   - Optional: weekly diff — "this week's prediction shifted Markgraf's CO by N days, why?"

## Out-of-band notes

- This milestone explicitly does NOT use BT's planned dates. If at any point the team adds plan ingest (m03 unblocks), m04's predictor can be cross-validated against plan dates as a sanity check. Predictor output stays the source of truth.
- If the calibration spike shows the predictor is reliably off in a known direction (e.g., always under-estimates by 2-3 weeks), apply a global correction factor — don't pretend that's a confidence band issue.
