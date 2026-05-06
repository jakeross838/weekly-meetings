# Phase 3 — Duration Math (Burst + Density) · PLAN

## Goal
Replace span-based duration with **burst-segmented active-day duration** for every (sub × phase × job) combination. Density becomes the headline metric. Cross-stage burst retag handles phase code drift over time. Output is the data structure every downstream view reads from.

## Inputs
- `data/derived-phases-v2.json` — 5,547 enriched records from Phase 2
- `data/phase-instances.json` — 371 per-(job × phase) aggregations
- `config/phase-taxonomy.yaml` — taxonomy with predecessors/successors
- `config/phase-keywords.yaml` — for cross-stage burst retag matching
- `config/cross-trade-rejections.yaml` — multi-trade allowlists (gates retag rejections)

## Method (7 steps)

### Step 1 — Burst detection
For every (sub × phase × job) combo, walk log dates chronologically:
- Burst starts on a day with logged work
- Burst ends on the last day before a gap of **≥6 working days** (Sat/Sun off doesn't end a burst; full week off does)
- A burst must contain ≥3 active days OR represent the only logged work for that phase

Output: `data/bursts.json` with one record per detected burst.

### Step 2 — Cross-stage burst retag
For multi-burst phase instances where bursts are >60 days apart, retag each burst:
1. Aggregate burst text from log descriptions
2. Run text through Phase 1 keyword library
3. If highest-confidence match is a DIFFERENT phase code, retag the burst
4. Log every retag

**Guardrails:**
- Only retag when keyword match confidence ≥80% on aggregate burst text
- Never override `high`-confidence Phase 1 classifications
- Block retag if new phase code violates sub's allowlist in `cross-trade-rejections.yaml` — route to manual review instead
- Print every retag with old phase / new phase / sample text in `data/burst-retags.md` for QA

**Canonical case to handle:** Markgraf 2.4 Stem Wall Waterproofing currently shows 12 active days / 450 span / 2% density. Two bursts:
- Burst 1 (Aug 2025): "Waterproofed stem wall, applied membrane" → keep 2.4
- Burst 2 (Apr 2026): "Hydroban applied master shower pan" → retag to 10.1

### Step 3 — Aggregate to phase instance
Rebuild `phase-instances.json` (overwrites v1) with burst-aware metrics:
- `bursts[]` — per-burst stats (first, last, active, span, density)
- `burst_count`, `total_active_days`, `total_span_days`
- `weighted_density` — average across bursts weighted by active days
- `primary_density` — density of the largest burst (less polluted by tail bursts)
- preserve existing `subs_involved`, `predecessors`, `successors`, `_complete`/`_started` flags

Save to `data/phase-instances-v2.json`.

### Step 4 — Aggregate to phase median (Schedule Builder feed)
For every phase code, company-wide medians across completed instances:
- `median_active_days`, `median_span_days`, `median_density`, `median_burst_count`
- `active_range_p25_p75`
- `sample_size`, `confidence` (high ≥5 jobs, medium 3-4, low <3)
- `subs[]` — top contributors with their medians

Save to `data/phase-medians.json`.

### Step 5 — Density tier assignment
Apply tier labels to every density value (used by all downstream views):

| Density | Label |
|---|---|
| ≥0.80 | continuous |
| 0.60–0.79 | steady |
| 0.40–0.59 | scattered |
| <0.40 | dragging |

Persist labels in JSON; downstream reads the label not the raw threshold.

### Step 6 — Library expansion (deferred from Phase 1)
Mine `low_review` records for keyword library gaps. Targeted phases from Phase 2 audit:
- 5.1 Exterior Sheathing & Wrap
- 7.1 Stucco Lath/Wire
- 12.1 Caulk & Putty
- 12.3 Paint Trim & Doors
- 13.1 Plumbing Trim
- 13.2 Gas Trim
- 13.3 Electrical Trim

For each target phase: find low_review logs whose text suggests the phase, surface most-common unmatched terms, propose keyword additions.

Print to `data/keyword-gaps-proposals.md` for Jake's review. **Don't auto-apply.** After paste-back approval, apply additions and re-run classification on affected logs only (not the full pipeline).

### Step 7 — Persist artifacts
- `data/bursts.json`
- `data/phase-instances-v2.json` (overwrites v1)
- `data/phase-medians.json`
- `data/burst-retags.md`
- `data/keyword-gaps-proposals.md`
- `phases/03-duration-math/PLAN.md` — this file
- `phases/03-duration-math/VERIFICATION.md`

## Verification (paste-back required)

8 items in `VERIFICATION.md`:

1. **Burst detection sanity for 8 phases** — Stucco, Drywall, Interior Tile, Pool, Framing, Siding, Interior Trim, Roofing. For each: old span-based duration vs new active-days duration vs burst count vs avg density. Flag if new active days dropped >30% from old span (explain why).

2. **Cross-stage retag results** — total retags, broken down by from→to phase pair. Must include Markgraf CoatRite 2.4 → 10.1 Burst 2 retag.

3. **Watts stucco at Fish** — full burst breakdown. **Must show 2-3 bursts** (scratch, brown, finish) with separate density per burst. If it shows 1 burst at 21% density, burst detection failed; iterate before shipping.

4. **6.1 Plumbing Top-Out phase median** — full record. Should show median 9d, Gator ~11d at 80%+ density, Loftin ~5d at 85%+ density, sample size 8, confidence high.

5. **Markgraf 2.4 Waterproofing** — must show 2 bursts with burst 2 retagged to 10.1 and original 2.4 burst at honest density (not the 2% artifact).

6. **Density tier distribution** — count of continuous / steady / scattered / dragging across all instances. Dragging should be a meaningful minority (not 80%+).

7. **Library expansion proposals** — full list of proposed keyword additions for the 7 deferred phases. Sample text from low_review logs that would graduate.

8. **Insight preview** — top 10 Phase 2 sequencing anomalies re-evaluated against burst data. Many should resolve cleanly (e.g., Markgraf 2.4 artifact); some remain (Watts genuine dragging). Remaining set is what Phase 6 will formalize.

## Stop conditions
- Burst detection passes the 8-phase sanity check
- Markgraf CoatRite cross-stage retag works (2.4 burst 2 → 10.1)
- Watts stucco at Fish shows 2-3 bursts (not 1)
- Phase medians produced for all phase codes with ≥1 instance
- Density tier distribution plausible (not 80%+ dragging)
- Library expansion proposals printed for approval (do not auto-apply)

## Stop-and-ask triggers
- Burst detection produces single bursts on phases that obviously have multiple (Watts, paint primer/finish, pool shell/plaster) — gap threshold is wrong, flag don't ship
- Cross-stage retag tries to push a burst into a phase the sub's allowlist forbids — block + route to manual review
- Library expansion proposals diverge from Phase 1 keyword style (e.g., proposing tag-based fallback) — flag rather than apply

## Standing rules (unchanged)
- v1 stays running; output to v2 paths
- Recalculate, don't increment
- Org-configurable
- Backward compatible
- Print-legible
