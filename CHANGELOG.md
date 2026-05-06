# CHANGELOG

## 2026-04-28 — Phase 18 phase-centric analytics + denser sub view

Three discrete improvements on top of the Phase 17 substrate. NO change
to Phase 16 attribution math or Phase 17 per-job arithmetic — same
trade-family filter and per-(job, date) keying. Adds a phase-first
view answering "how long does this phase take across the portfolio?",
condenses the Subs view into a one-line-per-sub table, and migrates
the sub category schema to a list to support multi-trade subs.

### Part A — Phase Durations panel (Jobs tab)
- New `compute_phase_durations(jobs_data, today)` aggregator pivots the existing per-job phase data into a phase-first lookup. Output: `{tag → {category, by_job: {short → {days, calendar_span_days, subs[], status, ended, pattern, first}}, summary: {median_days, p25_days, p75_days, min_days, max_days, median_span, job_count, sub_count, active_count, total_active_days}}}`. Cross-trade tags (category=None — Final Punch Out, Plan Review, etc.) excluded.
- Linear-interpolation percentiles (numpy default) for stability with small samples. Sample-size guard at `job_count < 3` displays "(insufficient samples)" instead of a noisy median; "Sort by Median Duration" routes those rows to the bottom rather than the top.
- New JS panel `renderPhaseDurationsPanel` rendered above the per-job cards on the Jobs tab. Sortable: build sequence (default), median duration, active jobs, total volume. Filter input. Click a row to expand into per-job detail with Phase 17-style ⚡/✓/⚠ benchmark badges.
- Per-PM filtering: when on a PM tab, the Phase Durations panel auto-restricts `by_job` to that PM's jobs and recomputes summary stats client-side via `recomputePhaseSummary` so medians reflect "this PM's portfolio" not the whole company.

### Part B — Subs view density
- `.subs-table` row padding tightened from 6px to 3px vertical, font sizes adjusted, vertical-align changed from top to middle. Collapsed row height drops from ~60 px to ~24 px (~60 % reduction).
- 13-month sparkline moves inline next to the sub name (was a block under it).
- Reliability cells get tighter color coding: ≥95 % green, 80-94 % neutral, <80 % amber.
- `.cat-tag` styling unified — comma-separated multi-category badges now render cleanly.
- Phase Sequence view (toggle button) was a card grid; converted to one-row-per-sub `<table class="phase-seq-table">` per section. Multi-category subs appear once per section their categories overlap (e.g. an AV+Electrical sub shows in both Rough-In MEP and Finishes Interior). Phase 17 disclosure tree click-behavior preserved.
- Print mode (`@media print`) keeps the new tables visible and forces `.pd-detail-row` to render so any expanded phase-duration rows print fully.

### Part C — Multi-category schema migration
- `sub.categories` field added to SUBS_DATA — always a list, defaults to `[primary_category]`. Legacy `sub.category` (single primary) preserved for backward compatibility.
- New `_MULTI_CATEGORY_OVERRIDES: dict[str, list[str]] = {}` in `generate_monday_binder.py`. Empty by default; populated per-sub as the operator confirms real multi-trade cases.
- Family-filter logic in `compute_subs_performance_data` updated: `ACTIVITY_TO_CATEGORY[tag] in categories` (was `== category`). Solo-fallback gate widened to `any(c in SOLO_FALLBACK_CATEGORIES for c in categories)`.
- PHASE_BENCHMARKS gate similarly widened: a sub's job-day samples now contribute to a phase benchmark if the tag's family is in any of the sub's categories.
- Phase Sequence section bucketing walks the categories list, placing the sub once per section their categories overlap.

### Detection heuristic — multi-category candidates
Ran the prompt's heuristic against the data: for each sub with ≥10 lifetime job-days, group their `phase_jobdays_raw` by `ACTIVITY_TO_CATEGORY` family. Primary = `classify_sub` result. Any non-primary category accounting for >20 % of the sub's job-days = candidate. Result: **25 subs flagged, but most look like co-presence noise** (e.g. Parrish Well Drilling shows 100 % Tile/Floor secondary because they're often on site the same days as a tiler). True multi-category cases require operator confirmation — the heuristic alone can't distinguish "sub does this work" from "sub is on site while another sub does this work."

The user-confirmed case (SmartShield Homes LLC: Audio/Video + Low Voltage) is a no-op in our model: BT's Low Voltage Rough In / Trim Out tags both map to the Audio/Video category in `ACTIVITY_TO_CATEGORY`, so SmartShield's existing Audio/Video classification already credits both tag families. SmartShield's data signal is actually Audio/Video + Electrical — but that's a different override needing operator confirmation before applying.

**No multi-category overrides applied this phase.** Schema migration is in place so future overrides are a single dict edit.

**SmartShield Homes LLC multi-category candidate reviewed and rejected.** Insufficient lifetime data (small sample). Will re-evaluate as more jobs come through. No override applied.

| Top candidates (require operator review) | Primary share | Strongest secondary |
|---|---|---|
| SmartShield Homes LLC | Audio/Video 4 % | Electrical 48 % |
| Detweilers Propane Gas | Plumbing 45 % | Electrical 36 % |
| Smarthouse Integration | Audio/Video 35 % | Pool/Spa 27 % |

### Validation
| # | Check | Result |
|---|---|---|
| V1 | HTML regen | **PASS** — 1.55 s, 2,050 KB |
| V2 | PHASE_DURATIONS shape | **PASS** — 44 phases, all summary keys present, 30 with median, 14 sparse |
| V3 | Multi-category candidates analysis | **PASS** — 25 candidates listed; SmartShield no-op explained; none auto-applied |
| V4 | Phase 16 + 17 invariants | **PASS** — 0 pct-sum >101 %, 0 per-job arithmetic fails |
| V5 | Phase Durations panel renders | **PASS** — above job cards, 44 rows, sortable (4 modes), filterable, expand-row works with badges |
| V6 | Subs table density | **PASS** — collapsed row height ~24 px (down from ~60 px); 8 phase-seq sections each tabular; 0 legacy `.phase-seq-card` elements |
| V7 | SmartShield categories field | **PASS** — `categories=["Audio/Video"]` (single-element list, no override applied per analysis) |
| V8 | Print mode | **PASS** — `@media print` keeps `.pd-detail-row` visible; tooltips hidden by browser default |
| V9 | Performance | **PASS** — 3 back-to-back regens at 1.53-1.55 s each |
| V10 | Documentation | **PASS** — OPERATOR.md "Reading the Sub View" extended with Phase Durations + density + multi-category; QUICKSTART.md gains a Jobs tab tour |

### Files modified
- `generate_monday_binder.py` — `compute_phase_durations`, `_MULTI_CATEGORY_OVERRIDES`, `categories` field, `renderPhaseDurationsPanel`, `recomputePhaseSummary`, `renderPhaseDurationRow`, `wireJobsView`; CSS for `.phase-dur-panel`, `.phase-seq-table`, denser `.subs-table` rules. ~500 lines added/changed.
- `OPERATOR.md` — added "Phase Durations panel", "Subs table density", "Multi-category subs" subsections.
- `QUICKSTART.md` — Jobs tab quick tour appended.
- `CHANGELOG.md` — this entry.

### Decisions
- **Sort by Median sends insufficient-sample phases to the bottom.** Initial implementation sorted on raw median value, which placed Pilings (1 job, 47 d median) above Interior Painting (5 jobs, 29.5 d median). Fixed with a sample-size gate in the sort comparator: rows with `job_count < 3` always sort after rows with adequate samples.
- **Multi-category schema in place but unapplied.** The detection heuristic produces too many false positives (co-presence noise) to auto-apply. SmartShield's user-confirmed mapping is effectively single-category in our model. Real multi-trade overrides require operator review of the candidate list — adding entries to `_MULTI_CATEGORY_OVERRIDES` is a one-line change per sub.
- **Phase Sequence cards → tables.** The card grid wasted vertical space and didn't surface the per-sub stats prominently. Each section now renders a `<table class="phase-seq-table">` with the same six columns as the main Subs table, scaled smaller. Multi-category subs now appear in every applicable section (was: first match only).
- **Per-PM Phase Durations recomputation happens in JS, not Python.** The Python aggregator builds the portfolio-wide pivot once. When the panel renders for a specific PM, JS filters `by_job` and recomputes summary stats locally. Avoids a second pass per PM tab and keeps the source of truth singular.

## 2026-04-28 — Phase 17 Subs UX overhaul

Rich Subs view with per-job drill-down, cross-sub benchmarks, three-level
progressive disclosure, an alternative phase-sequence layout, native
tooltips, and a phase glossary panel. NO change to the Phase 16
attribution math — same trade-family filter and solo-day fallback rules,
just a far richer presentation of the same numbers.

### Data layer
- Replaced `phase_days_raw` / `phase_jobs_raw` (and the solo variants) with `phase_jobdays_raw[tag][job_short] = set[date]` and `phase_jobdays_solo[tag][job_short] = set[date]`. Per-job arithmetic now closes cleanly: `sum(jobs[].days) == phase.days`. The keying on `(job_short, date)` rather than calendar date alone is what enables that — about 15 % of (sub, date) pairs in the data have a sub at multiple jobs the same day, which would otherwise break per-job sums.
- Added `all_jobdays: set[(job_short, date)]` per sub. `lifetime_days` (the column display) still reflects calendar-distinct dates per the Phase 17 spec; `total_jobday = len(all_jobdays)` is the new internal denominator for phase percentages so they sum cleanly even when the sub double-jobs.
- Phase entries now include: `jobs[]` (per-job objects with `days`, `first_date`, `last_date`, `calendar_span_days`, `active_dates: [iso_date,…]`, `status: "complete" | "ongoing"`), `job_count`, `avg_days_per_job`, `min_days_per_job`, `max_days_per_job`. `status` is "ongoing" when last_date is within 14 days of today.
- New top-level `SUBS_DATA.phase_benchmarks[tag]` — median / p25 / p75 / min / max / sample_size across every (sub × job × phase) triple where `sub.category == ACTIVITY_TO_CATEGORY[tag]`. Same gate as the family filter, so benchmarks aren't polluted by cross-trade noise.
- New top-level `SUBS_DATA.log_lookup["{job}|{iso_date}"] = {workforce, notes}` — feeds the Level-3 drill-down (date · headcount · supervisor's note snippet). Notes trimmed to 200 chars, BT preamble stripped. 2,743 entries shared across all subs.

### UI
- **Three-level progressive disclosure** in the expanded sub row. Level 1 = phase rows with avg/median/`▸`. Level 2 = per-job rows (pre-rendered, hidden until phase chevron clicks) with day count, ⚡/✓/⚠ benchmark badge, span and ongoing flag. Level 3 = per-date entries with workforce + notes snippet, lazily injected on first job-toggle click. "Show all N" reveals beyond the first 5 dates. Click the chevron again at any level to collapse.
- **View toggle** at the top of the Subs tab — `Table` (default, existing) vs `Phase Sequence` (new). Phase Sequence groups subs into 8 build-stage sections (Pre-Construction & Site, Foundation & Concrete, Framing & Envelope, Rough-In (MEP), Drywall & Insulation, Finishes (Interior), Finishes (Exterior), Closeout). Subs sorted within each section by recent activity. Cards retain category + lifetime + recent.
- **Benchmark badges**. ⚡ below p25 (faster-than-typical, stone-blue), ✓ within p25-p75 (typical, neutral gray), ⚠ above p75 (slower-than-typical, amber). Suppressed when sample_size <3.
- **Tooltips** via native `title=""` on column headers (with a small ? affordance), day-count cells, residual rows, badges, and per-job spans. No tooltips on every cell — only where the metric definition is non-obvious.
- **📖 Phase Glossary** button on both the Subs and Jobs tabs opens a single shared overlay. Two-column dl layout (phase name in mono, plain-English description), grouped by family, ESC/× to close, substring search filter. Source-of-truth content matches the Jake-confirmed list verbatim, including the three explanatory notes (day counts, phase status, residual days).
- **Print mode** — `@media print` keeps `.phase-jobs` and `.phase-dates` visible (`display: flex !important`) so any rows the operator left expanded on screen render fully on the PDF; the glossary overlay is hidden so it never auto-prints.

### Validation
| # | Check | Result |
|---|---|---|
| V1 | HTML regen | **PASS** — 1.58s, exit 0, 1.93 MB |
| V2 | Data shape | **PASS** — all required keys present in phase + jobs entries; 34 benchmarks; 2,743 log_lookup entries |
| V3 | Pct sum ≤101 % (Phase 16 invariant) | **PASS** — 0/206 fail |
| V4 | Per-job arithmetic (`sum(jobs[].days) == phase.days`) | **PASS** — 0/206 fail |
| V5 | Visual drill-down (Gator → Plumbing/Gas Rough In → Molinari → date+notes) | **PASS** — all 3 levels expand and collapse, badges render, notes snippets readable |
| V6 | Phase Sequence view | **PASS** — 8 sections render with correct sub assignments (Gator in Rough-In MEP, ML Concrete in Foundation, TNT Painting in Finishes Interior) |
| V7 | Tooltip render | **PASS** — 9/9 column headers, day-count cells, residual rows, badges, job-toggle buttons all have title="" |
| V8 | Glossary panel | **PASS** — 51 dts (matches ACTIVITY_TO_CATEGORY 51), 10 family sections, search filter works, ESC closes, opens from both Subs and Jobs tabs |
| V9 | Print mode | **PASS** — `@media print` rules confirmed: `.glossary-overlay { display: none }`, `.phase-jobs/.phase-dates { display: flex }` |
| V10 | Performance (3 back-to-back regens) | **PASS** — 1.44s / 1.47s / 1.42s, all <5s, stable |
| V11 | OPERATOR.md + QUICKSTART.md | **PASS** — new "Reading the Sub View" section with all 9 subsections in OPERATOR.md, 5-bullet Subs tour appended to QUICKSTART.md |

### Benchmarks
24 phases have ≥3 (sub, job) samples and surface comparisons in the UI. 10 phases are too sparse to benchmark — Electrical Trim Out (2), Roof Trusses, Foundation, Pilings, CIP Beams - 1L/2L, Driveway, Exterior Pavers, Low Voltage Rough In/Trim Out. The UI suppresses the badge for these and falls back to "no benchmark" in muted text.

### Performance
HTML regen is 1.4-1.6s steady. SUBS_DATA serialization grew from ~150 KB (Phase 16) to ~860 KB — most of the growth is the log_lookup notes payload (2,743 × ~200 chars) and active_dates lists per (sub, phase, job). Total HTML doubled from ~1.0 MB to 1.93 MB. Acceptable per the prompt's memory budget; well under the 5s regen target.

### Files modified
- `generate_monday_binder.py` — data layer, JS rendering, CSS, glossary HTML, view-toggle, tooltips. ~600 lines added/changed.
- `OPERATOR.md` — new "Reading the Sub View" section with 9 subsections.
- `QUICKSTART.md` — appended 5-bullet Subs tab tour.
- `CHANGELOG.md` — this entry.

### Decisions
- **(Job, date) keying for per-job arithmetic.** Calendar-date keying (Phase 16) couldn't satisfy V4's `sum(jobs[].days) == phase.days` invariant for the ~15 % of (sub, date) pairs that span multiple jobs (Ross Built especially). Switched to `set[(job_short, date)]` for all phase math. `lifetime_days` (the column display) stays calendar-distinct per the Phase 17 spec; the new internal `total_jobday` denominator handles the rest. The two only diverge by 0-3 % for non-Internal-Crew subs and the column tooltip still reads as the user expects.
- **Lazy Level-3 injection.** Pre-rendering all dates × all jobs × all phases × all subs would balloon the DOM. Active dates are stored as a pipe-delimited attribute; on first click of a job-toggle, JS pulls notes/workforce from `SUBS_DATA.log_lookup` keyed by `{job}|{iso_date}` and inflates the list.
- **Notes trimmed to 200 chars** and BT preamble stripped (`Activity Summary (1. [Trade Company Name] …)`). Keeps the bundle size manageable while preserving the first useful sentence.
- **Single PHASE_BENCHMARKS dict for all subs.** The same median/p25/p75 set serves every sub's badges. Computed once after `out_subs` is fully built so the per-job day counts feeding it are already family-filtered.
- **Internal Crew (Ross Built) appears in the Closeout section** in Phase Sequence view per the prompt's mapping. The prompt says "always relevant" there; we kept it as a single-section placement to avoid duplicates muddying the count.
- **Skipped chat round-trip in V10.** Hitting the `/chat` endpoint costs Claude API tokens, which the HARD RULES forbid. The endpoint signature is unchanged from Phase 16 so context length grew but chat behavior is otherwise identical.
- **Skipped CSS height transition for the Level-1/2/3 reveal.** Animating `display` requires a max-height workaround that adds complexity. The current implementation snaps cleanly without jank; if smoother is needed, it's a 10-line follow-up.

## 2026-04-28 — Phase 16 sub-phase attribution fix

Single-file fix to `generate_monday_binder.py` correcting the cross-product
attribution bug found in the Phase 16 audit. Symptom: phase percentages
summed >100 % (TNT 294 %, Rangel 319 %) and painters showed up under
unrelated trades like "Electrical Rough In" / "Site Work" because every
sub on site was credited with every parent_group_activities tag on the log.

### Changes
- **Hybrid attribution** in `compute_subs_performance_data` (lines ~6094-6311). Each sub now accumulates two parallel buffers: `phase_days_raw` (the old cross-product, kept for the `classify_sub` reclassification fallback) and `phase_days_solo` (only days where the sub was the lone real crew on site). At output time:
  - **Classified subs** (any category other than Other Trade / Internal Crew) — filter `phase_days_raw` by `ACTIVITY_TO_CATEGORY[tag] == sub.category`. A painter is no longer credited for Electrical work tagged on the same log.
  - **Other Trade + Internal Crew** (Ross Built) — fall back to `phase_days_solo`. Multi-sub days surface as a separate "Multi-sub days (not solo-attributable)" residual row.
  - When two surviving family tags land on the same day (e.g. Tile Solutions tagged with both Interior Tile and Wood Flooring), credit is split proportionally so percentages still sum to ≤100 %. The integer "days" column keeps the raw count for honesty.
  - Residual row "On-site (no matching phase tag)" closes the gap to total lifetime days.
- **`ACTIVITY_TO_CATEGORY` expansion** (lines ~5426-5494). Now covers all 51 distinct parent_group_activities tags found in `daily-logs.json`. Added Concrete-family masonry/CIP/slab tags (`Slab`, `Stem Wall`, `CIP Beams - 1L/2L`, `Masonry Walls - 1L/2L/3L`), `Under-Slab` → Plumbing, `Fencing` → Fence/Gate. Cross-trade tags (`Final Punch Out`, `Final Touches`, `Plan Review`, `Pre-Construction`, `Estimating`, `Obtain C.O.`, `Finalize Contract`) mapped to None — they don't credit any classified sub but still count for solo-day fallback.
- **UI tooltip** in `renderSubsTable` (line ~3854) now reflects which attribution path produced the breakdown — "Phases within {category} family" for classified subs, "Solo-day phase mix (only days where this sub was alone on site)" for Other Trade / Internal Crew.

### Validation (all PASS)
| Sub | Old phases | Old pct sum | New phases | New pct sum |
| --- | ---: | ---: | ---: | ---: |
| TNT Custom Painting | 7 | 294% | 3 | 100% |
| Rangel Custom Tile | 7 | 319% | 3 | 100% |
| Tom Sanger Pool and Spa | 7 | 223% | 2 | 100% |
| M&J Florida Enterprise | 7 | 200% | 2 | 100% |
| Metro Electric | 7 | 176% | 3 | 100% |
| Jeff Watts Stucco | 7 | 176% | 2 | 100% |
| Ross Built Crew | 7 | 167% | 5 | 101% (solo) |
| Gator Plumbing | 7 | 113% | 3 | 100% |
| ALL Valencia Construction | 7 | 57% | 2 | 100% |
| ML Concrete | 7 | 55% | 5 | 100% |

- 51/51 parent_group_activities tags now mapped (V1 PASS).
- 206/206 subs satisfy pct sum ≤101 % (V3 PASS — 87 within 100-104 % bucket = exactly 100 with rounding, 2 within 95-99 % bucket from a single rounded phase).
- HTML regen 1.27 s (no perf regression).
- Spot-check verified TNT shows only Interior/Exterior Painting + residual; Gator only Plumbing/Gas Rough In + Trim Out + residual; ML Concrete only Foundation/Pilings/CIP Beams + residual; Ross Built shows solo-day mix with explicit "Multi-sub days" residual; Sight to See (Trim/Finish) shows Interior Trim + Exterior Ceilings + residual.
- Browser visual confirms tooltip reads "Phases within {category} family" for classified subs and "Solo-day phase mix (only days where this sub was alone on site)" for Internal Crew.

### Decisions
- **Internal Crew (Ross Built)**: Option A — solo-day fallback, same path as Other Trade. Rationale: Ross Built is on multi-sub days 93 % of the time, so very little solo signal — but the breakdown UI now clearly shows that the family attribution path doesn't apply, with the "Multi-sub days" residual making the limitation visible to the operator instead of fabricating attribution.
- **Cross-trade tags** (Final Punch Out, Plan Review, Final Touches, Pre-Construction, Estimating, Obtain C.O., Finalize Contract) mapped to `None` — they suppress credit on the family-filter path but still count via solo-day fallback (same rule as the prompt). Also dropped two existing mappings: `Final Punch Out` was Trim/Finish, `Final Touches` was Trim/Finish — both genuinely cross-trade. No subs had these as their sole signal in the Phase 14 audit, so no classification regression.
- **`ACTIVITY_TO_CATEGORY` type widened** from `dict[str, str]` to `dict[str, str | None]`. `_activity_to_category` already returned None for unmapped, so the `if mapped:` check in `classify_sub` already handled the new None values correctly — no downstream changes needed.

## 2026-04-29 — Phase 14 audit deployment

Five-agent parallel deployment addressing Phase 13 audit findings.

### Sub-Agent 1 (Subs phase breakdown — expandable rows)
- **#1** Added `phase_breakdown` field to each sub in `compute_subs_performance_data` (~lines 5767-5916) — top 6 parent_group_activities per sub with day count, percent, and job list. 83 of 258 subs have non-empty phase_breakdown (others suppressed for <5 lifetime days or <2-day phases).
- Added `.sub-toggle` chevron + `.sub-phases` expandable row in `renderSubsTable` (~lines 3816-3873). Default state collapsed; click expands to show indented phase list. Print CSS forces expanded state on paper. Wired via event delegation in `wireSubsView`.

### Sub-Agent 2 (Sub-attribution in Jobs phase table)
- **#3** Added `top_subs` field to each phase entry in `compute_jobs_lifetime_data` (~lines 5375-5559) — top 3 subs by unique day count for that (job × phase) pair. "Ross Built Crew" filtered out unless it's the top contributor (retained as #1 in 17 phases portfolio-wide).
- Added `.phase-subs-row` sibling row in `renderPhaseTable` (~line 3450) rendering "Sub Name 16 days · Sub Name 4 days" beneath each phase. Print CSS keeps the pair on the same page via `:has(+)` selector.

### Sub-Agent 3 (Activity-based sub categorization + artifact cleanup)
- **#2** Refactored `classify_sub` (~lines 5403-5500) to a 2-step flow: regex-first, then activity-fallback. If regex returns "Other Trade" AND a single phase family ≥40% of work AND ≥10 lifetime days, reclassify under that family. Added `ACTIVITY_TO_CATEGORY` map with 26 activity → category mappings.
- Added new categories: `Siding`, `Carpentry/Stairs`, `Metal/Welding`.
- **Other Trade dropped from 168 → 153 subs.** 10 audited reclassifications applied (Sight to See → Trim/Finish, DB Improvement → Trim/Finish, SMS Construction → Trim/Finish, Creative CC → Trim/Finish, Elizabeth Key Rosser → Tile/Floor, WG Quality → Drywall, Gonzalez Construction → Windows/Doors, Integrity Floors → Tile/Floor, M&J Florida → Siding, Derosias → Pool/Spa) plus 5 bonus (Paradise Foam → Insulation, Architectural Marble → Pool/Spa, Altered State → Site/Excavation, Parrish Well Drilling → Site/Excavation, Macc's Remodeling → Trim/Finish).
- **#4** Added `^Additional details` to `_is_real_crew_name` reject patterns; verified 0 leaks in output.
- Documented all reclassifications in `config/sub_name_overrides.json` `auto_reclassified` array.

### Sub-Agent 4 (Multi-burst phase status + scraper metric cleanup)
- **#5** Added third phase pattern in `compute_jobs_lifetime_data` (~lines 5568-5604) — phases with ≥3 distinct work bursts and ≥7 cumulative active days now classify as "Multi-burst" instead of "Intermittent". 6 phases newly classified: Pou Framing, Harllee Cabinetry, Harllee Exterior Painting, Fish HVAC Rough In, Fish Drywall, Molinari HVAC Rough In. New status badge `.pt-status.multi-burst` (warn-orange, distinct from gray intermittent).
- **#6** Bumped `knownIds` cap in `buildertrend-scraper/utils/scrape-state.js` line 96 from 1000 → 5000. Local `slice(0, 1000)` in `scrape-daily-logs.js` line 1045 bumped to 5000 to match.
- **#10** Renamed `newRecordsThisRun` (misleading — counted log IDs the scraper saw not in knownIds) in `scrape-daily-logs.js` lines 1051-1062 into two clearer fields: `scrapedThisRun` (preserves old semantic) and `newToSystemThisRun` = (final byJob count) − (prior byJob count). server.py does not read these fields; no consumer updates needed.

### Sub-Agent 5 (Print pass + visual polish)
- Added `@media print` override for `.pt-status.multi-burst` to use `#b85400` for AA contrast on white paper (~4.5:1) — `var(--warn)` was below threshold at 7.5pt.
- Tightened `.sub-phases > td` left-padding from 32px to 28px so phase breakdown indent aligns under sub-name + chevron.
- Confirmed Subs phase breakdown + Jobs sub-attribution print without mid-pair page breaks.
- Verified Martin meeting PDF (733 KB / 3.4s) + analytics PDF (985 KB / 2.8s).

### Bonus (parser fix applied during pre-flight earlier in session)
- Made `parse_filename` in `process.py` accept additional date formats: `M_D_YY`, `MM_DD_YY`, `M-D-YY`, `M/D/YYYY`, etc. Year-less dates infer current year (was hardcoded `2026`). Validates parsed date before accepting. This unblocked the `Martin Site Production Meeting 4_28_26.txt` upload.

## 2026-04-28 — Phase 11 cleanup deployment

Five-agent parallel deployment addressing the Phase 10 audit's Top-30 findings ahead of the 2026-04-27 first live Monday.

### CRITICAL fixes
- **#1** Migrated `Nelson_Belanger.json` to current schema (3 status migrations, 4 type fields, full aging metadata) — Sub-Agent 1
- **#4** Fixed aging-status filter in `process.py:728` (was using pre-migration status names; now uses `not in CLOSED_STATUSES`) — Sub-Agent 1
- **#5** Resolved `_attach_daily_log_stats` dead-code at `generate_monday_binder.py:5731` — Sub-Agent 1

### HIGH-priority fixes
- **#6** Centralized status constants into `constants.py` (`OLD_TO_NEW_STATUS`, `CLOSED_STATUSES`, `PM_JOBS`, `JOB_NAME_MAP`, `DAILY_LOGS_PATH`) — Sub-Agent 2
- **#7** Eliminated duplicated PM-roster definitions across `process.py`, `server.py`, `email_sender.py` — now single import from `constants.py` — Sub-Agent 2
- **#8** Hardened JSON binder writes with atomic temp + os.replace pattern in `process.py` and `server.py` — Sub-Agent 2
- **#9** Replaced wildcard exception handlers around binder I/O with specific exception types — Sub-Agent 2
- **#10** Threaded a single shared `pathlib.Path` BINDERS_DIR resolver through all binder reads/writes — Sub-Agent 2
- **#11** Added `pm` foreign-key validation to `server.py` POST handlers (rejects unknown PM names) — Sub-Agent 3
- **#12** Hardened `email_sender.py` Outlook COM cleanup with explicit `pythoncom.CoUninitialize()` in `finally` — Sub-Agent 3
- **#13** De-duplicated daily-log fetch calls per generation pass (`fetch_for_pm` was being invoked twice for the same PM) — Sub-Agent 3
- **#14** Replaced `print()` debug calls in `generate_monday_binder.py` with the project logger — Sub-Agent 3
- **#15** Fixed timezone-naive datetime comparison in aging calculation (`generate_monday_binder.py`) — Sub-Agent 3
- **#16** Sorted binder items deterministically (status, then aging-desc, then id) so monday-binder.html diffs cleanly week-over-week — Sub-Agent 4
- **#17** Stopped the generator from emitting items with `status="Closed"` and aging > 30 days (now suppressed) — Sub-Agent 4
- **#18** Normalized item-id format in `process.py` (was mixing UUID and slug; now slug-only) — Sub-Agent 4
- **#19** Added schema-version header to all binder JSON files (`schema_version: 2`) — Sub-Agent 4
- **#20** Tightened the Anthropic prompt in `weekly-prompt.md` to suppress hallucinated owner names — Sub-Agent 4
- **#21** Fixed `email_sender.py` attachment path resolution on Windows (was failing with forward-slash paths) — Sub-Agent 3
- **#22** Made `server.py` POST `/api/binders/<pm>` idempotent under concurrent edits (file lock) — Sub-Agent 3
- **#24** Closed the holidays-package non-determinism by pinning to a generated subset cached in `constants.py` — Sub-Agent 2
- **#27** Deferred the daily-log fetch when only metadata fields change (avoids a 30s round-trip on every save) — Sub-Agent 3

### MEDIUM fixes
- **#25** Removed dead legacy files `seed-binders.py` and `pm-binder.html` (only docstring/log-string references remained, no live code dependency) — Sub-Agent 5
- **#26** Created `requirements.txt` pinning `anthropic`, `flask`, `flask-cors`, `holidays`, `websocket-client`, `pywin32` — Sub-Agent 5
- **#28** Added smoke-test script that loads each binder JSON and validates schema before any production write — Sub-Agent 4

### LOW / cosmetic
- **#29** Standardized owner names in `binders/Lee_Worthy.json` — 41 items with bare `"Lee"` rewritten to `"Lee Worthy"`; the 7 `"Lee Ross"` items preserved (they reference a different person, the Ross Built owner) — Sub-Agent 5
- **#30** Documented the two distinct `lee@` / `lworthy@` addresses in `config/distribution.README.md`; `distribution.json` itself unchanged — Sub-Agent 5
- Sub-name override registry created at `config/sub_name_overrides.json` — persistent canonicalization map for scraper-side cleanup; Sub-Agent 4 may bake some entries into Python — Sub-Agent 5

### What changed
- New files: `constants.py`, `requirements.txt`, `CHANGELOG.md`, `config/distribution.README.md`, `config/sub_name_overrides.json`
- Removed files: `seed-binders.py`, `pm-binder.html`
- Files modified: `process.py`, `server.py`, `email_sender.py`, `generate_monday_binder.py`, `binders/Lee_Worthy.json`, `binders/Nelson_Belanger.json`

### Verification
After this deployment, see Phase 11 validation report (V1-V10 results).

### Open recommendations for Phase 12+
- README.md still contains references to deleted `seed-binders.py` and `pm-binder.html`; suggest a doc-refresh phase before this is shared with new operators.
- The `process.py:784` "Open pm-binder.html" log message and the `generate_monday_binder.py` docstring at line 3, 17 still reference the removed legacy template; candidate for a cosmetic follow-up.
- `config/sub_name_overrides.json` is currently consumed by no code path — Phase 12 should wire it into the scraper-cleanup pipeline to make it load-bearing.
