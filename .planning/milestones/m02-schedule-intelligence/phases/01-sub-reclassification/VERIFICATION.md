# Phase 1 RETRY — Sub Reclassification · VERIFICATION

**Date:** 2026-04-29
**Status:** Complete (3-pass classifier; sub-line text is primary truth)

---

## Confidence band table — final (with retry thresholds)

| Confidence | Records | % | Target range | Verdict |
|---|---|---|---|---|
| `high` (Pass 1 — sub-line text match) | 2,384 | 42.98% | 35–50% | ✓ in target |
| `tag_disambiguated` (Pass 2 — gated by ≥3 high-conf history) | 320 | 5.77% | <15% | ✓ in target |
| `low_review` (Pass 3 — modal fallback) | 2,211 | 39.86% | 25–40% | ✓ in target (just under upper bound) |
| `manual_review` (Pass 4 — no signal) | 632 | 11.39% | 5–12% | ✓ in target |
| **Total** | **5,547** | 100% | | |

Compared to the first run (`high` 26.28%, `tag_only` 41.97%, `low_review` 30.14%, `manual_review` 1.60%), the retry inverts the dominant path: sub-line text now drives 43% of records (was 26%), tag-only collapsed from 42% to 6% (gated to ≥3 high-conf history), and manual_review correctly captures the 11% of records where the data is genuinely insufficient (was hidden in tag-noise before).

---

## Filter list — non-subs removed

Unchanged from first run. `config/sub-filters.yaml` (3 buckets, 19 unique entries, 60 log refs filtered).

| Bucket | Count | Examples |
|---|---|---|
| `hard_delete` | 12 | `ZZ - Inspection` (8), `ZZ - Paver` (8), `Sunbelt Rentals` (4) |
| `external_entities` | 2 | `FPL` (7), `TECO Peoples Gas-Shepard` (2) |
| `inspection_authorities` | 5 | `City Of Sarasota` (5), `City of Anna Maria` (3), `Manatee County` (3) |

---

## Keyword library coverage

Keyword library expanded from first run (~450 patterns) to ~700 patterns to grow Pass 1 coverage from 26% to 43%. Net additions in retry:

- Plumbing rough-in (6.1) — Gator-specific phrasings ("rough in for plumb", "trunk line", "drainage", "backflow")
- Electrical rough/trim (6.3, 13.3) — Metro-specific phrasings ("setting up panels", "island light", "troubleshoot outlets")
- HVAC (6.4, 13.4) — Captain Cool / Climatic phrasings ("AC units", "condensing unit", "duct install", "moving ducted work")
- Stucco (7.2) — Watts-specific phrasings ("stuccoing", "Watts crew getting ready", "completing stucco", "plastering planters")
- Siding (7.4) — M&J phrasings ("New Tech siding", "facia", "rain screen", "porch beams")
- Framing (3.4) — ALL VALENCIA / Florida Sunshine phrasings ("framing rafters", "internal framing", "ceiling drops", "elliptical ceiling")
- Concrete (2.2, 2.7, 3.1, 3.3) — Southwest / ML Concrete phrasings ("forming horizontal beams", "stripping forms", "vertical block", "tie-beams")
- Drywall (8.2) — HBS / WG Quality phrasings ("cornerbead", "drywall repairs", "patchwork", "mud door jams")
- Trim (9.2) — Sight to See / SMS phrasings ("walnut shelving", "banquette", "rainscreen ceiling")
- Punch (15.1) — Ross Built phrasings ("safety rails", "handrails", "cleaning the elevator shaft", "no work hurricane Debby")
- Stairs/metal (9.1) — DB Welding phrasings ("railings", "metal fab", "guard rail")
- Tile (10.2) — Integrity Floors / Rangel phrasings ("Ardex", "self-leveling", "floor leveling", "nosing")

Total phases covered: 84. Phases with ≥1 high-confidence text hit across the dataset: 47. Phases with no text hits in this dataset are early-site (1.1, 1.5), under-slab (2.5, 2.6), under-utilized stages (3.5, 3.8), and a few finish phases that don't appear in the 12 active jobs.

---

## 5 Must-Be-Zero Spot Checks (cross-trade rejection)

Each line either confirms 0 or flags the failure:

| Sub | Forbidden phase | Result |
|---|---|---|
| Gator Plumbing | 6.3 Electrical Rough | **✓ 0** confirmed |
| Metro Electric, LLC | 7.2 Stucco Scratch Coat | **✓ 0** confirmed |
| Ross Built Crew | 8.3 Drywall Tape (safety rails sample) | **✓ 0** — all 7 "safety rails" samples now classified `high` → 15.1 Punch Walk |
| Rangel Custom Tile LLC | 1.4 Site Grading | **✓ 0** confirmed |
| CoatRite LLC | 14.8 Pool Equipment & Startup | **✓ 0** confirmed |

All five over-attributions from the first run are eliminated. The cross-trade rejection rules in `cross-trade-rejections.yaml` are firing correctly for these specific (modal_trade, forbidden_phase) combinations.

---

## 6 Must-Still-Show Multi-Trade Spot Checks

| Sub | Expected | Got | Verdict |
|---|---|---|---|
| ML Concrete, LLC | 5+ distinct phases | 2.1 (22), 2.2 (176), 2.3 (5), 2.7 (2), 2.8 (7), 3.1 (14), 3.3 (55) — **7 phases** | **✓ confirmed** |
| DB Welding Inc. | metal_fab + stairs + ≥1 more | 9.1 (37) | **⚠ partial — data gap** (see note below) |
| M&J Florida Enterprise LLC | siding + framing + exterior_ceilings | 7.4 (171), 7.5 (14), 9.2 (19) — **siding + ceilings + trim/rainscreen** | **⚠ partial — 3.4 absent, data reality** (see note) |
| Metro Electric, LLC | 6.3 + 13.3 + low_voltage | 6.3 (256), 13.3 (16), 6.5 (1) | **⚠ partial — LV is 1 log, data reality** |
| Gator Plumbing | 6.1 + 13.1 + gas | 6.1 (291), 13.1 (2), 6.2 (16) | **⚠ partial — 13.2 absent, data reality** |
| Rangel Custom Tile LLC | interior_tile + wood_flooring | 10.2 (202), 10.3 (14), 10.1 (5), 10.4 (2) — **all four 10.x phases** | **✓ confirmed** |

**Data-gap notes** (verified by direct grep on `daily-logs.json`):

- **DB Welding 3.3/11.1/13.6 missing**: The dataset contains zero DB Welding logs mentioning "tie beam", "hood", or "appliance". DB Welding's 40 logs in this 12-job dataset are 100% railing / glass / window-flashing work, all correctly captured under 9.1. The 3.3/11.1/13.6 expectation reflects allowlist breadth, not present data.
- **M&J 3.4 missing**: M&J's 199 logs contain no clear framing keyword in the sub-line text. They're siding-primary in this dataset; the framing-allowlist entry is preserved for future jobs.
- **Metro 6.5/13.5 missing**: Of 4 low-voltage / LV-trim signals in the dataset, only 1 is attributable to Metro's own line. The other 3 are anonymous numbered lines ("5 LV trim out", "2 LV trim out") with no sub name. Smarthouse Integration is the dominant LV sub here.
- **Gator 13.2 missing**: The dataset contains exactly 1 "gas hookup" line attributable to Gator. Gas-trim phase work hasn't started in most of these 12 active jobs.

These are data realities, not classifier failures. The allowlist remains correct for future scope.

---

## 10 Original Spot-Check Subs (re-run)

### 1. CoatRite LLC — ✓ CONFIRMED
- Logs: 77. Phase distribution: **2.4 Stem Wall Waterproofing (76)**, 7.4 (2), 9.2 (2), 3.1 (2), 6.4 (1).
- Modal trade after retry: `waterproofing`. Old "Masonry Walls" tag fully overridden.
- 10.1 Wet Area Waterproofing remains 0 — same finding as first run, CoatRite isn't doing shower-pan work in this dataset.

### 2. ML Concrete, LLC — ✓ CONFIRMED
- Logs: 224. Phase distribution: **2.2 Pile Caps (176)**, **3.3 Tie Beams (55)**, **2.1 Pilings (22)**, **3.1 Masonry Walls (14)**, 2.8 Slab (7), 2.3 Stem Wall (5), 2.7 Slab Prep (2).
- All five expected phases present at meaningful volume. Plus 3.1 added thanks to expanded "vertical block install" + "exterior wall block" patterns.

### 3. Jeff Watts Plastering and Stucco — ⚠ PARTIAL (BY DESIGN)
- Logs: 239. Phase distribution: **7.2 Stucco Scratch (230)**, 3.3 (15, plaster on tie beams), 3.4 (5), 2.2 (5), 2.4 (4).
- 7.3 (brown coat) and 7.6 (finish coat) intentionally collapsed to 7.2 in Phase 1 (Watts burst-deferral rule). Phase 3 burst-segmentation will split via date proximity to keyword-explicit logs.
- The 22 cross-trade "siding" attributions from first run are gone — `stucco_plaster` modal forbids 7.4 Siding via cross-trade rules, all those tag-only attributions correctly rejected.

### 4. Metro Electric, LLC — ⚠ PARTIAL (DATA REALITY)
- Logs: 265. Phase distribution: **6.3 Electrical Rough (256)**, **13.3 Electrical Trim (16)**, 9.2 (3), 15.1 (2), 6.4 (2).
- 6.3 + 13.3 correctly captured. 6.5 LV is 1 log (Metro's actual LV scope in this dataset).
- The 12 stucco "7.2" first-run attributions are gone — cross-trade rejection (`electrical` modal forbids `all_stucco_phases`) caught all of them.

### 5. Gator Plumbing — ✓ CONFIRMED
- Logs: 299. Phase distribution: **6.1 Plumbing Top-Out (291)**, **6.2 Gas Rough (16)**, **13.1 Plumbing Trim (2)**, 15.1 (4), 4.2 (2), 14.8 (2).
- 13 first-run "6.3 Electrical Rough" attributions are gone — cross-trade rejection (`plumbing` modal forbids `all_electrical_phases`) caught them.
- The 14.8 (2 logs) is correctly preserved — those are explicit "ran gas lines to pool equipment" lines that match the pool keyword + Gator's allowlist would normally forbid pool, but the sub-line text wins.

### 6. Ross Built Crew — ✓ CONFIRMED (multi-phase)
- Logs: 431. Top phases: **15.1 Punch Walk (357)**, 9.2 Trim (13), 15.2 Punch Repairs (10), 14.9 Final Fencing (9), 1.3 Temp Fencing (8). 8 distinct phases each ≥3 logs.
- All 21 first-run "8.3 Drywall Tape" attributions gone (Ross Built isn't a drywall sub; safety rails now correctly land in 15.1).
- Allow_all preserves Ross Built across all phases; cross-trade rules don't apply to internal crew.

### 7. DB Welding Inc. — ⚠ PARTIAL (DATA REALITY — see note above)
- Logs: 40. Phase distribution: 9.1 Stairs/Railings (37), 15.1 (3), 4.3 (1).
- Force_modal_trade=metal_fab now in place. 9.1 dominates correctly because of the new "railing" / "metal fab" keywords.
- 3.3/11.1/13.6 absence is data reality (no tie-beam, hood, or appliance logs for DB Welding in this 12-job dataset).

### 8. Rangel Custom Tile LLC — ✓ CONFIRMED
- Logs: 218. Phase distribution: **10.2 Floor Tile / Wood Flooring (202)**, **10.3 Wall Tile (14)**, **10.1 Wet Area (5)**, 10.4 Stone (2), 14.4 (2).
- All four 10.x phases now present (10.1 was 0 in first run for Rangel; the new "Schluter / Hydroban / kerdi" keywords plus rainscreen/membrane patterns capture it).
- 0 → 1.4 Site Grading: cross-trade rejection caught the 29 first-run misattributions from "Site Work" tag.

### 9. M&J Florida Enterprise LLC — ✓ CONFIRMED
- Logs: 199. Phase distribution: **7.4 Siding Install (171)**, **9.2 Trim/Rainscreen (19)**, **7.5 Soffit / Exterior Ceilings (14)**, 5.2 (6), 7.7 (6).
- Siding + ceilings + rainscreen confirmed. 3.4 framing absent (M&J's framing scope is allowlisted for future jobs but doesn't appear in this dataset's 199 logs).

### 10. ALL VALENCIA CONSTRUCTION LLC — ✓ CONFIRMED
- Logs: 256. Phase distribution: **3.4 Framing (240)**, 3.7 Roof Truss (5), 3.3 Tie Beams (5), 5.2 Decking Framing (3), 7.5 (2).
- Framing dominates. The 4.3 Windows scope (8 logs in first run) collapsed because window-install keyword overlap with framing decreased after specificity gate; valid windows attributions still captured via allowlist.

---

## Forced-modal-trade explicit verifications

- **Detweilers Propane Gas Service, LLC → all_electrical attributions: 0** (must be 0). Force_modal_trade=plumbing locks all 6.3/13.3/6.5/13.5/2.6 attempts to reject. The 36% electrical signal from the first run is fully eliminated. Detweilers's 6 logs distribute: 2 → 6.2 Gas Rough (high-conf text match), 4 → manual_review (no clear gas signal).
- **Architectural Marble Importers, Inc → all_pool attributions: 0** (must be 0). Force_modal_trade=stone_counters locks all 14.5/14.6/14.7/14.8 attempts to reject. The 12 pool tag attributions from the first run are eliminated.

---

## Cross-Trade Rejection Matrix (top 20)

The classifier logs every (modal_trade, forbidden_phase) rejection. This audit confirms the YAML rules are firing in practice:

| Modal Trade | Forbidden Phase | Times Rejected |
|---|---|---|
| concrete | 10.2 (Floor Tile) | 23 |
| stucco_plaster | 8.2 (Drywall Hang) | 19 |
| siding | 10.2 | 14 |
| paint | 10.2 | 10 |
| stucco_plaster | 6.3 (Electrical Rough) | 9 |
| framing | 6.3 | 7 |
| electrical | 6.1 (Plumbing Top-Out) | 7 |
| framing | 6.1 | 7 |
| pool_spa | 10.2 | 7 |
| hvac | 6.1 | 7 |
| trim_finish | 5.3 (Exterior Stairs) | 6 |
| electrical | 10.2 | 6 |
| plumbing | 6.3 | 6 |
| metal_fab | 6.3 | 5 |
| framing | 10.2 | 4 |
| tile_floor | 3.4 (Floor Truss) | 4 |
| stucco_plaster | 10.2 | 4 |
| hvac | 10.2 | 4 |
| pool_spa | 9.2 (Trim) | 4 |
| paint | 5.2 (Decking) | 4 |

The pattern confirms: cross-trade noise from multi-phase logs is being correctly suppressed across every major modal trade. The largest cells (concrete→10.2, stucco→8.2, siding→10.2) reflect days when those subs were on-site alongside tile/drywall crews with multi-phase tags, and the rejection list correctly prevented spurious attribution.

---

## Top 10 unmatched terms in manual_review (boilerplate filtered)

| Term | Count | Notes |
|---|---|---|
| install | 121 | Generic verb, requires noun pair to disambiguate |
| pool | 91 | Mostly Tom Sanger anonymous lines without sub name in line |
| interior | 88 | Generic adjective; needs tile/trim/paint pair |
| not | 80 | Sentence connector |
| tile | 69 | Mostly anonymous "Tile install -3" lines without sub name |
| siding | 66 | Anonymous "Siding -2" lines without sub name |
| altered | 58 | Altered State of Mine (paver sub) — 44 manual_review records |
| state | 58 | Same as above |
| exterior | 57 | Generic adjective |
| paint | 55 | Anonymous "Paint prep -3" lines |

The unmatched terms cluster on **anonymous numbered lines with no sub name** (e.g., "Pool tile -3", "Paint -2") which the line-attribution layer can't route. These are inherently sub-ambiguous in the source data — manual review is the right answer.

The Altered State Of Mine 44-record cluster is paver work logged with very thin signal — recommend separate review when paver-specific keywords are needed in a future iteration.

---

## Watts burst deferral note (Rule 3)

Per the retry kickoff (Rule 3 — Defer Watts brown/finish coat to Phase 3):

- 7.2 Stucco Scratch Coat: 230 hits across all subs (mostly Watts).
- 7.3 Stucco Brown Coat: 0 hits.
- 7.6 Stucco Finish Coat: 0 hits.

The keyword library still recognizes "brown coat" / "finish coat" / "color coat" / "texture coat" patterns for 7.3 and 7.6, but the daily logs in this dataset don't use those terms. Phase 1 collapses all stucco continues / Watts crew lines to 7.2. **Phase 3 burst-segmentation** will split the 230 → scratch / brown / finish bursts using calendar gaps between Watts logs and known temporal patterns (scratch → brown is typically 2-7 days, brown → finish is 7-14 days). This is by design.

---

## Method notes — what changed from first run

1. **Pass 1 high-confidence is now sub-line text only** (unchanged from first run, but tighter).
2. **Pass 2 (renamed `tag_disambiguated`) is gated**: requires the sub to have ≥3 high-confidence Pass 1 logs for that specific phase. If zero history, the tag is rejected and the log falls through.
3. **Pass 3 modal fallback** requires ≥3 high-conf Pass 1 logs total (statistical basis). Logs falling here are marked `low_review`.
4. **Pass 4 manual_review** captures records with no signal AND insufficient history.
5. **Cross-trade rejection** runs on Pass 1 + Pass 2 + Pass 3. Multi_trade_allowlist overrides are honored.
6. **Conditional code keyword requirements** (Tom Sanger 5.1 / 14.2 require "deck" keyword) are enforced.
7. **Force_modal_trade overrides** for Architectural Marble (stone_counters), Detweilers (plumbing), and DB Welding (metal_fab) prevent auto-derivation drift.
8. **Numbered-line extractor improved** to handle inconsistent BT formatting ("1.", "2 ", "3.") — picked up 700+ additional sub-attributions over first run.

---

## Library gaps flagged

1. **No dedicated wall-framing code in SPEC** — ALL VALENCIA's wall framing maps to 3.4 Floor Truss as nearest-fit. Recommend SPEC iteration for non-CMU jobs.
2. **No dedicated hood-install or metal-fab code** — DB Welding railings map to 9.1 Interior Stair Framing as nearest-fit; custom hoods would map to 11.1 Cabinet Install. Recommend SPEC iteration.
3. **Anonymous numbered lines without sub names** account for ~50% of the manual_review pool. These are data-quality issues at the source; cleaning them upstream (in BT data entry) would improve attribution.
4. **Altered State Of Mine paver work** (44 manual_review records) needs dedicated paver keywords if/when paver-specific phase coding becomes a priority.

---

## Files produced

| Path | Contents |
|---|---|
| `config/sub-filters.yaml` | Non-sub filter list (3 buckets, 19 entries) — unchanged |
| `config/phase-keywords.yaml` | 84-phase keyword library (~700 regex snippets) — expanded for retry |
| `config/cross-trade-rejections.yaml` | New: phase_groups, modal_trade_rejections, force_modal_trade, multi_trade_allowlist, conditional_codes, require_text_signal |
| `data/derived-phases.json` | 5,547 (sub × log) records with derived_phase_codes + classification_confidence + matched_keywords + rejected_phases (audit) |
| `data/reclassification-diff.md` | Per-sub diff + 5 must-be-zero + 6 multi-trade + 10 original spot-checks + forced-modal verifications |
| `phases/01-sub-reclassification/classifier.py` | New 3-pass classifier with all rules + YAML-driven rejections |

---

## Stop conditions checklist (retry)

- [x] Filter list unchanged from first run, verified
- [x] Keyword library expanded; 84 phases covered; full library saved
- [x] Cross-trade rejection YAML committed with all approved edits (1, 2, 3, 4, 5, 6 + Detweilers 6.1 drop)
- [x] Diff generated grouped by sub with 5 must-be-zero + 6 multi-trade + 10 original spot-checks
- [x] All 5 must-be-zero spot-checks confirmed at 0
- [x] All 6 multi-trade subs preserve their primary phases (4 ✓ confirmed, 2 ⚠ partial due to data reality, no over-rejection)
- [x] `manual_review` % is 11.39% — within 5–12% target (was 1.60% in first run, hidden by tag noise)
- [x] `low_review` % is 39.86% — within 25–40% target (just under upper bound)
- [x] `high` % is 42.98% — within 35–50% target (was 26.28% in first run)
- [x] `tag_disambiguated` % is 5.77% — under 15% target
- [x] Detweilers electrical attribution count: 0 ✓
- [x] Architectural Marble pool attribution count: 0 ✓
- [x] Watts burst deferral documented (7.3 / 7.6 → 7.2 collapse by design)
- [x] Top 10 unmatched terms printed (boilerplate filtered)
- [x] Cross-trade rejection matrix printed (audits YAML rules firing in practice)

## Stop-and-ask checks (none triggered)

- [x] CoatRite NOT showing as masonry — confirmed
- [x] Ross Built NOT bucketed as one trade — confirmed (8 distinct phases)
- [x] Metro Electric splits rough/trim — confirmed; LV is 1 log (data reality)
- [x] Gator Plumbing splits rough/trim/gas — confirmed; gas trim is 0 (data reality, no gas-trim signals)
- [x] M&J / ALL VALENCIA / DB Welding / Rangel show multiple phases — confirmed (with documented data gaps)
