# Phase 4+5 — Phase Library + Job Page (Combined) · PLAN

## Goal
Two production HTML pages reading from Phase 3 data artifacts. Shared scaffold, two pages, shared components.

Save to:
- `monday-binder-v2/phase-library.html` (Phase 4)
- `monday-binder-v2/jobs.html` (Phase 5)

v1 stays running untouched.

## Inputs
All Phase 3 outputs. Pure rendering — no new data math:
- `data/phase-instances-v2.json` — 398 burst-aware instances with primary/return/punch density + labels
- `data/phase-medians.json` — 72 phase medians (primary_density default)
- `data/sub-phase-rollups.json` — 68 rollups, 31 flagged, both density labels populated
- `data/job-stages.json` — 12 jobs with current_stage + ongoing_phases
- `data/bursts.json` — 1,656 bursts with role classification
- `config/phase-taxonomy.yaml` — 84 phases with predecessors/successors

## Shared scaffold

Build once, both pages use:
- Tailwind CSS via CDN
- `monday-binder-v2/assets/styles.css` — tokens (colors, density chips, status icons), print stylesheet
- `monday-binder-v2/assets/components.js` — shared rendering: density chip, status icon, sub-link, phase-link, flag badge

### Density chip component
Absolute label + vs_phase label rendered side-by-side:
- 🟢 Continuous 78% (absolute=continuous, ≥0.80)
- 🟡 Steady 65% (absolute=steady, 0.60-0.79)
- 🟠 Scattered 52% (absolute=scattered, 0.40-0.59)
- 🔴 Dragging 38% (absolute=dragging, <0.40)
- ▲ above peer (vs_phase=above_phase, > +0.10)
- ● at peer (vs_phase=at_phase, ±0.10)
- ▼ below peer (vs_phase=below_phase, < −0.10)

Sub-phase pairs show BOTH labels: `🟠 Scattered 52% · ▼ below peer`. Print-legible (text labels not emoji-only).

### Flag badge
Compact: `⚠ FLAGGED · score 3 · density_below + return_high + vs_median_below`. Hover details optional.

## Phase Library page (Phase 4)

### Layout
- Top: 14-stage filter bar (1 button per stage + "All")
- Body: one card per phase code, grouped by stage, in build sequence order

### Phase card content
- Header: phase code + name + stage + sample size (jobs)
- Stats row: primary active days (with P25-P75), primary density chip, return rate %, punch rate %, active now (count + sample)
- Sequence chips: Preceded By / Followed By
- Subs table: sub name, primary active days, density chips (absolute + vs_phase), jobs touched, flag badge
- Per-job detail expander: every job that ran this phase with bursts breakdown, status, vs phase median active days

### Sort + filter
- Default: stage order ascending
- Toggle: sort by sample size, by median active days, by primary density
- Filter: "Has flagged subs only"

### Removed (vs v1 / vs early mockup)
- No reliability badges
- No last-seen
- No recent-activity counts
- No trade category headers (replaced by stage filter)

## Jobs page (Phase 5)

### Layout
- Top strip: "Active Phases Today" — count of jobs, ongoing phases, flagged ongoing
- Body: one card per job, default expanded
- Sort: current_stage ascending; within stage, by CO target

### Job card content
- Header: job name + address + PM + current stage + CO target
- Inline insight stub: count of ongoing phases with flagged subs (Phase 6 placeholder)
- Phase read-down: every phase from 15-stage taxonomy shown, even if not started (— for empty)
- Status icons: ✓ complete / ⏵ ongoing (row tint) / ▢ scheduled / — none
- Ongoing flagged phases get ⚠ at end of row
- Rows clickable to expand into sub list + bursts inline

### Removed (vs v1)
- Total log-days
- Person-days
- Avg crew
- Unique subs count
- Workforce histogram
- Top-10 subs list
- Latest events
- Delivery/inspection counts

## Verification (paste-back required)

7 items in `VERIFICATION.md`:

1. **Phase Library — 6.1 Plumbing card** — Confirm Gator shows above_phase, no flag badge; Loftin renders correctly; sample size matches.
2. **Phase Library — 7.2 Stucco card** — Watts at_phase scattered WITH flag badge.
3. **Jobs — Markgraf card** — full read-down. CoatRite at 2.4 (not 3.1). Floor Trusses at 3.4 (not 3.7). 15.2 ongoing flagged.
4. **Jobs — Active Phases Today strip** — actual current numbers from data.
5. **Jobs — Clark card** — Stage 2 Foundation, mostly empty rows (correct, job is early).
6. **Print preview** — both pages render clean on paper. Density chips have text labels.
7. **Click-through** — Phase Library sub → sub's flagged phases; Jobs phase code → phase library card. If routing nontrivial, defer to Phase 6 (flag and skip).

## Standing rules
- v2 paths only. v1 untouched.
- Pure rendering — no new data math.
- Print-legible.
- One thing per row, max 5 columns.
- 4-color density + 3-arrow vs_phase, nothing else.

## Stop conditions
- Both pages render without errors against current data
- All 7 verification items pass
- Print preview confirms legibility on both pages

## Stop-and-flag triggers
- Card renders but data looks wrong (e.g., CoatRite under masonry on Markgraf) → Phase 1/2/3 leak, flag don't paper over
- Click-through routing is nontrivial → flag and defer to Phase 6
- Print stylesheet conflicts with Tailwind base → flag and surface
