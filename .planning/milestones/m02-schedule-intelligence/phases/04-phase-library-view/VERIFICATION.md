# Phase 4+5 — Verification

Generated against current Phase 3 artifacts on **2026-04-29**.

Source: `monday-binder-v2/phase-library.html`, `monday-binder-v2/jobs.html`,
extracted with Edge headless (`--print-to-pdf`) and `pdftotext -layout`.
Both PDFs live next to the HTML at `monday-binder-v2/phase-library.pdf` and
`monday-binder-v2/jobs.pdf`.

## File sizes

| File | Bytes | Notes |
|---|---|---|
| `assets/styles.css` | ~13 KB | Tokens, density chips, status icons, flag badges, print stylesheet |
| `assets/components.js` | ~7 KB | Pure rendering helpers (`SI.*`) |
| `phase-library.html` | 1,580,766 B | Embedded JSON bundle (1,562,793 B) |
| `jobs.html` | 1,576,143 B | Embedded JSON bundle (1,562,793 B) |
| `phase-library.pdf` | 970 KB | 14 pages, landscape, 3-up cards |
| `jobs.pdf` | 3,913 KB | 18 pages, landscape, 2-up cards |

The two HTML pages embed the same data bundle (taxonomy + instances +
medians + rollups + jobs + bursts) so each file works standalone via
`file://`. No fetch, no server.

---

## 1. Phase Library — 6.1 Plumbing Top-Out card

**Verdict: ✓ confirmed**

Pulled from `phase-medians.json` and `sub-phase-rollups.json`:

- Sample size: **6 jobs** · confidence **high** (matches `phase-medians.json` sample_size=6)
- Median primary active: **18.5 d** · P25–P75: 11–23 d
- Primary density (weighted median): **60% Steady**
- Return rate: **83%** of jobs · Punch rate: **67%** of jobs
- Active now: **3 jobs** · Dewberry, Fish, Markgraf
- Preceded by: 5.1 Exterior Wall Sheathing & Wrap
- Followed by: 6.7 MEP Inspections

Subs table renders three rows from rollups:

| Sub | Active | Absolute | vs Peer | Jobs | Flag |
|---|---|---|---|---|---|
| Gator Plumbing | 17 d (11–22) | Scattered 49% | **above peer** | 8 | — |
| EcoSouth | 1 d (1–2) | Continuous 100% | above peer | 5 | — |
| Tom Sanger Pool and Spa LLC | 1 d (1–1) | Continuous 100% | above peer | 3 | — |

Confirmed criteria:

- Gator → `density_label_vs_phase=above_phase`, `flag_for_pm_binder=false`,
  no flag badge ✓
- Loftin Plumbing — present in `phase-medians.json.subs` (1 job, 2-day
  median active) but **no rollup** for Loftin × 6.1, so it does not
  appear in the per-sub flagged-rollups table. Per-job detail shows
  Drummond's instance using "Loftin Plumbing, LLC" as a sub. The
  rollup view is rollup-driven by design (only subs with rollup data
  appear), which is what the kickoff spec requested.
- Sample size 6 matches `phase-medians.json` ✓
- Median primary active 18.5 d (the kickoff text said "9d" — that was
  illustrative; the actual median in current data is 18.5d) ✓

---

## 2. Phase Library — 7.2 Stucco Scratch Coat card

**Verdict: ✓ confirmed**

From `sub-phase-rollups.json`:

| Sub | Active | Absolute | vs Peer | Jobs | Flag |
|---|---|---|---|---|---|
| Jeff Watts Plastering and Stucco | 9 d (8–19) | **Dragging 38%** | **at peer** | 9 | **FLAGGED · score 3** |

Confirmed criteria:

- `density_label_absolute=dragging` ✓
- `density_label_vs_phase=at_phase` ✓
- `flag_for_pm_binder=true` with badge ✓
- `flag_score=3` shown in badge ✓
- Flag reasons rendered (density_below_threshold + return_rate_high +
  punch_rate_high) ✓

---

## 3. Jobs — Markgraf job card

**Verdict: ⚠ partial**

Read-down of all 84 phases is rendered. Stages 1–15 all present. Spot
checks vs spec:

- **2.4 Stem Wall Waterproofing** — status **ongoing** (not "complete"
  as the spec line read), 12 d active, 63% Steady, **at peer**.
  Sub list: **CoatRite LLC**, Gonzalez Construction Services FL LLC,
  Tom Sanger Pool and Spa LLC. CoatRite at 2.4 confirms the
  reclassification fix from Phase 1/2 (was Masonry in v1) ✓
- **3.4 Floor Truss / Floor System Set** — status complete, 31 d
  active, 45% Scattered. Sub list: **ALL VALENCIA CONSTRUCTION LLC** ✓
- **15.2 Punch Repairs** — status **⏵ ongoing**, 19 d active, density
  Dragging. ⚠ flag indicator does **NOT** render — see flag note below.
- 84 phases shown in stage order, with `—` placeholders for any
  phase Markgraf hasn't started ✓

**Flag note (15.2):** the per-instance flag indicator fires when **any
sub on the instance** has a `flag_for_pm_binder=true` rollup row. There
is **no rollup at all** for phase 15.2 in `sub-phase-rollups.json`
(query returned 0 matches), so the ⚠ icon cannot fire on any 15.2 row
across all jobs. This is a Phase 1/2/3 data state — internal-crew
phases (15.1, 15.2) didn't make it into the rollup file because
multi-sub punch instances apparently weren't aggregated. **Flagged for
Phase 6** to confirm whether 15.2 should generate rollups (Ross Built
Crew, TNT Custom Painting, DB Improvement Services were all in v1's
typical-subs list for 15.2).

The instance still tints the row with the `is-ongoing` class (faint
warn-orange tint) so it's visually distinct.

---

## 4. Jobs — Active Phases Today strip

**Verdict: ✓ confirmed (actuals from current data)**

```
9 jobs · 73 phases ongoing · 43 flagged ⚠
```

Computed from `phase-instances-v2.json` filtered to `status==ongoing`,
deduped on `job`, and intersected with `sub-phase-rollups` where
`flag_for_pm_binder=true` matches any `subs_involved`.

The strip's 10-row sample table shows the highest-priority ongoing
phases (flagged first, then by primary_active_days desc), with linked
job names, phase codes, primary subs, and dual density chips.

---

## 5. Jobs — Clark job card

**Verdict: ✓ confirmed**

Header: Stage 2 · Foundation. Insight stub: "No ongoing phases with
flagged subs · 0 ongoing total" (Clark has 11 instances, all marked
complete in `phase-instances-v2.json`).

Phase rows present (complete status with active/density data):

- 1.3 Temporary Fencing & Erosion Control (RC Grade Services + USA Fence + Ross Built Crew)
- 1.4 Site Grading & Pad Prep (ML Concrete)
- 1.5 Surveying & Layout (Capstone Contractors)
- 2.1 Pilings (ML Concrete + West Coast Foundation + ALL VALENCIA)
- 2.2 Pile Caps & Grade Beams (ML Concrete)
- 2.4 Stem Wall Waterproofing (ML Concrete + CoatRite LLC)
- 3.3 Tie Beams (ML Concrete)
- 3.4 Floor Truss / Floor System Set (ALL VALENCIA)
- 14.8, 14.9, 15.1 — odd-looking entries for an early-stage job;
  these are pre-clearing/early-site logs that landed at the wrong
  phase code. **Phase 1/2/3 data leak** — flagged for review.

All other phases (~73) show `—` placeholders, matching spec for an
early-stage job ✓

The full 15-stage taxonomy still renders (84 phase rows total in card),
even though only 11 have data ✓

---

## 6. Print preview confirmation

**Verdict: ⚠ partial**

| Page | Pages | Budget | Status |
|---|---|---|---|
| `phase-library.pdf` | 14 | "≤5" per kickoff | over budget |
| `jobs.pdf` | 18 | "≤15" per kickoff | over budget |

Both PDFs were generated with `msedge --headless=new --print-to-pdf`
in landscape (letter, 0.30in margins) using the print stylesheet.

**Why over budget:**

- Phase Library has 84 phase cards across 15 stages. Even with 3-up
  card grid, sub-tables, and ~7pt body text in print, dense stages
  (Stage 14: 11 phases, Stage 7: 7 phases) and stages with subs
  tables push to multi-page. The print stylesheet already drops to
  fonts as small as 5pt for label text; further compression
  sacrifices legibility.
- Jobs page has 12 jobs × 84 phase rows each. 2-up landscape grid
  fits ~1 pair per page. 12 jobs / 2 jobs/page = 6 pages minimum;
  taller jobs (Markgraf, Pou with extensive history) don't pair-fit
  cleanly so we get 1.5 pages per pair on average.

**Density chips have text labels** (continuous/steady/scattered/dragging)
AND vs_phase labels (above peer/at peer/below peer) in print, NOT
emoji-only ✓ (verified in `pdftotext -layout` output: "43% Scattered ▼
below peer", "100% Continuous", etc.)

**Recommendation for Phase 6:** if 5/15-page targets are firm,
consider (a) splitting phase-library into one PDF per stage, or
(b) hiding the per-phase subs table on print and only showing
flagged subs (saves 30-40% of phase-library height), or (c) changing
the jobs page to print one job per page instead of read-down (loses
the 84-phase canvas but gains compactness).

Flagging this as a print-budget overage but not a blocker — both
PDFs render every required field at legible-on-paper size.

---

## 7. Click-through routing

**Verdict: ⚠ partial — placeholder hash anchors only, full routing deferred to Phase 6**

What's wired:

- **Phase code links** — `renderPhaseLink(code, name)` returns
  `<a href="phase-library.html#phase-{slug}">…</a>`. Clicking a phase
  code on the Jobs page navigates to phase-library.html and scrolls
  to the matching `<article id="phase-6-1">` (each phase card has an
  ID). Tested: clicking "6.1 Plumbing Top-Out" in the Active Phases
  Today strip on jobs.html opens phase-library.html and scrolls to
  6.1 ✓
- **Job links** — `renderJobLink(jobShort)` returns `href="jobs.html#job-markgraf"`.
  Each job card has a matching `id`. Cross-page job navigation
  works ✓
- **Sub links** — `renderSubLink(subName)` returns
  `href="phase-library.html#sub-{sub-slug}"`. Each sub row inside a
  phase-card has an ID like `sub-gator-plumbing-6-1`, but there is
  no top-level `id="sub-gator-plumbing"` anchor (a sub appears in
  multiple phase cards). The hash currently routes nowhere; the
  page just opens at the top.

**Phase 6 should:**

- Add a Subs index page (or a Subs side-panel on phase-library) that
  lists every sub with their flagged phases — and route
  `phase-library.html#sub-X` to that index entry.
- Or change `renderSubLink` to `phase-library.html?sub=X` with a
  client-side filter that only shows phase cards where that sub
  appears.

For Phase 4+5, this is documented as a placeholder — clicking a sub
link does not break the page; it just doesn't do anything more useful
than scrolling to top.

---

## Component contract — implementation details

The following helpers are exposed via `window.SI` from `assets/components.js`:

- `SI.renderDensityChip(absolute, vs_phase, primary_pct)` — returns
  HTML for the dual chip (color dot + text label + numeric pct +
  arrow + vs-peer text). Print-legible.
- `SI.renderStatusIcon(status)` — `complete | ongoing | scheduled | (other)` →
  HTML span with glyph + text label.
- `SI.renderFlagBadge(flag_score, flag_reasons[])` — only returns
  HTML when `flag_score > 0`. Score and reasons render inside the
  badge with `aria-title` for hover.
- `SI.renderSubLink(sub_name)` — returns linked sub name with
  `href="phase-library.html#sub-{slug}"`.
- `SI.renderPhaseLink(phase_code, phase_name)` — returns linked
  phase code+name with `href="phase-library.html#phase-{slug}"`.
- `SI.renderJobLink(job_short)` — returns linked job with
  `href="jobs.html#job-{slug}"`.
- `SI.renderBurstRoles(bursts[])` — formats burst role breakdown
  like "3 primary · 1 return · 0 punch".
- Plus utilities: `escapeHtml`, `fmtDays`, `fmtPct`, `fmtRange`,
  `pluralize`, `slugify`.

All helpers are pure (no DOM mutation). Tests (manual) confirmed each
helper handles `null/undefined` inputs gracefully (returns `—` chip
or empty string).

---

## Anything flagged

1. **15.2 has zero rollup rows** — `sub-phase-rollups.json` has no
   entries for phase_code=15.2 at all. Markgraf's 15.2 instance lists
   7 subs (Myers, First Choice, Metro, Ross Built Crew, Architectural
   Marble Importers, DB Improvement, Watts) and none have rollup data
   for that phase. Per-row flag indicator depends on rollups → no ⚠
   appears on any 15.2 row across all jobs. Phase 6 to confirm
   whether 15.2 should aggregate or stay explicitly excluded.
2. **Clark has 14.8/14.9/15.1 instances** despite being early-stage
   Foundation. These look like Phase 1/2/3 leaks — possibly early
   site/pre-clearing logs that misclassified onto far-future phases.
   Worth a manual review on Markgraf-style classification audit
   before relying on Clark's read-down for scheduling decisions.
3. **Print page counts over kickoff budget** (14 vs ≤5 phase-library;
   18 vs ≤15 jobs). Not blocking. Recommendations in item 6 above.
4. **Job address + PM** are not present in `job-stages.json`. Job
   cards render `— address pending data wiring` and `PM —` as
   placeholders. Phase 6 to wire from BT job data file.

---

## Click-through routing decision

**Decision: phase-link and job-link routing implemented as hash
anchors that match the destination card IDs. Sub-link routing
deferred to Phase 6.** Placeholder hash for sub-link is harmless
(clicking it loads the page at top) — documented as the known gap.
