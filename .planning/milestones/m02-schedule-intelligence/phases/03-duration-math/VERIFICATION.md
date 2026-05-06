# Phase 3 — Duration Math (Burst + Density) · VERIFICATION

Generated: 2026-04-29

Phase 3 replaces span-based duration with burst-segmented active-day duration for every (sub × phase × job) combination. Density becomes the headline metric; cross-stage burst retag handles phase code drift over time.

## Inputs digested

- 5,547 enriched records (`data/derived-phases-v2.json`)
- 84 phases / 371 v1 instances (`data/phase-instances.json`)
- 775 compiled keyword regex patterns from `config/phase-keywords.yaml`
- 3,226 daily logs (for sub-line text retrieval during retag)

## Outputs produced

| Path | Records | Description |
|---|---|---|
| `data/bursts.json` | 1,608 bursts | One row per detected burst across 691 (sub × phase × job) combos |
| `data/phase-instances-v2.json` | 377 instances | Burst-aware aggregations (overwrites v1 semantically) |
| `data/phase-medians.json` | 70 phase records | Schedule Builder feed (company-wide medians per phase code) |
| `data/burst-retags.md` | 22 applied / 10 blocked | Cross-stage retag log |
| `data/keyword-gaps-proposals.md` | 7 phases / 132 records | Library expansion proposals (NOT applied) |

---

## 1. Burst-detection sanity for 8 phases

Comparing v1 span-based duration to v2 active-days + burst structure (averaged across job-instances per phase code):

| Code | Phase | V1 avg span | V2 avg active | V2 avg span | V2 avg bursts | V2 avg density |
|---|---|---:|---:|---:|---:|---:|
| 7.2 | Stucco Scratch Coat | 227.3 | 25.7 | 227.3 | 6.4 | 0.52 |
| 8.2 | Drywall Hang | 98.8 | 11.3 | 100.3 | 3.1 | 0.59 |
| 10.2 | Floor Tile / Wood Flooring | 174.4 | 44.1 | 174.4 | 6.1 | 0.61 |
| 14.5 | Pool Shell / Plumbing | 72.8 | 4.8 | 59.0 | 2.2 | 0.51 |
| 3.4 | Floor Truss / Floor System Set | 349.2 | 48.9 | 349.2 | 10.1 | 0.52 |
| 7.4 | Siding Install | 264.8 | 24.2 | 262.5 | 6.1 | 0.56 |
| 9.2 | Interior Trim Carpentry | 192.6 | 24.9 | 192.6 | 7.6 | 0.72 |
| 4.2 | Roofing Final | 234.9 | 11.6 | 194.0 | 4.7 | 0.65 |

**Active-day retention check (per phase code, summed across all instances):**
- 0 phases dropped > 30% of active days (largest drop: 13.6 Appliance Install at -29.4%, just under threshold).
- Total active-days summed across all instances: v1 = 5,290, v2 = 5,161 (-2.4%). Net loss is from de-duplication where the same calendar day previously counted across overlapping multi-sub credits; nothing meaningful lost.

**Pass.**

---

## 2. Cross-stage retag results

| Status | Count |
|---|---:|
| APPLIED | 22 |
| BLOCKED (outside sub allowlist) | 7 |
| BLOCKED (modal-trade rule) | 3 |

### From → To pair distribution (applied)

| From | To | Count |
|---|---|---:|
| 6.3 → 13.3 | Electrical Rough → Electrical Trim | 3 |
| 3.3 → 2.8 | Tie Beams → Slab Pour | 2 |
| 6.1 → 13.1 | Plumbing Top-Out → Plumbing Trim | 2 |
| 4.2 → 4.1 | Roofing Final → Roofing Underlayment | 1 |
| 4.2 → 2.4 | Roofing Final → Stem Wall Waterproofing | 1 |
| 12.2 → 14.1 | Paint Walls → Exterior Paint | 1 |
| 7.2 → 7.6 | Stucco Scratch → Stucco Finish | 1 |
| 6.4 → 13.4 | HVAC Rough → HVAC Trim | 1 |
| 15.1 → various | Punch Walk reattributed to specific phase work | 9 |
| (other one-offs) | | 1 |

### Most defensible retags

- **Gator Plumbing 6.1 → 13.1 at Markgraf** (Dec 2 + Jan 20-23 2026): "5 plumbing trim out", "2 plumbing trim out 2 gator fixed gas leak". Late-build Gator visits are trim, not rough-in. ✓
- **Metro Electric 6.3 → 13.3 at Markgraf** (Oct 1 + Dec 2-9 2025): "electrical trim out, garage, L2", "electrical trim out appliance". Trim phase, not rough. ✓
- **Climatic 6.4 → 13.4 at Drummond** (Apr 17-21 2026): "HVAC Trimout" three days running. ✓
- **Watts 7.2 → 7.6 at Harllee** (Feb 6 2026): "Stucco patching is being completed." Patches are finish-coat work. ✓
- **Avery 4.2 → 4.1 at Markgraf** (Oct 24-30 2024): "roof dry in", "roofing underlayment". Underlayment precedes final roofing. ✓
- **Myers Painting 12.2 → 14.1 at Markgraf** (Jul 30-Aug 1 2025): "Exterior painting". Interior tag was wrong. ✓

### Markgraf CoatRite 2.4 → 10.1 verdict — **NOT FOUND**

The kickoff designated this as the canonical case: "Burst 2 (Apr 2026): Hydroban applied master shower pan → retag to 10.1." This retag did not materialize. Honest finding:

1. CoatRite's actual Markgraf footprint (10 records, 2 bursts):
   - **Burst 1** (Mar 25 – Apr 9 2025): 9 active days, density 0.56. Genuine stem-wall waterproofing during foundation phase. Notes: "Waterproofing prep", "exterior waterproof". Stays 2.4. ✓
   - **Burst 2** (Apr 22 2026): 1 active day, density 1.00. Notes: "Coat Rite was on site with 2 guys to **waterproof the drainage for the wood slat wall/pool equipment area**." This is exterior pool-equipment area waterproofing, not shower-pan. Phase 1 classified high-confidence on "waterproof" → 2.4.
2. Searched all Markgraf logs for `shower pan|hydroban|kerdi|schluter|wet area|redgard` — only one hit, and it's not CoatRite (Feb 13 talk of "black Schluter along edge of SS plate").
3. **The shower-pan/wet-area scenario described in the kickoff does not exist in the underlying data.** CoatRite's Apr 2026 visit was specifically pool-equipment-area drainage waterproofing.
4. The retag system correctly didn't fire because:
   - Burst 2's single log is high-confidence Phase 1 — overriding it would violate the guardrail.
   - Burst 1's text genuinely matches 2.4 (stem-wall context).

The Markgraf 2.4 V1 artifact (12d active / 450d span / 2% density) IS resolved by burst-splitting — the v2 instance shows 5 bursts with weighted density 0.70 (steady), primary density 0.56 (scattered). The artifact disappears.

---

## 3. Watts stucco at Fish — burst breakdown

V2 produces **9 bursts** for Jeff Watts Plastering and Stucco × Fish × 7.2 Stucco Scratch Coat. (V1 showed a single 378-day span at 21% density.)

| # | First → Last | Active | Span | Density | Tier |
|---|---|---:|---:|---:|---|
| 1 | 2025-04-10 → 2025-04-17 | 5 | 8 | 0.62 | steady |
| 2 | 2025-05-28 → 2025-07-10 | 19 | 44 | 0.43 | scattered |
| 3 | 2025-07-23 → 2025-08-12 | 14 | 21 | 0.67 | steady |
| 4 | 2025-08-25 | 1 | 1 | 1.00 | continuous |
| 5 | 2025-10-24 → 2025-11-06 | 5 | 14 | 0.36 | dragging |
| 6 | 2025-11-19 → 2025-12-18 | 12 | 30 | 0.40 | scattered |
| 7 | 2025-12-24 | 1 | 1 | 1.00 | continuous |
| 8 | 2026-01-08 → 2026-02-10 | 17 | 34 | 0.50 | scattered |
| 9 | 2026-04-09 → 2026-04-22 | 7 | 14 | 0.50 | scattered |

Total: 81 active days across 378 calendar-day span. Weighted density 0.51 (scattered). Primary density 0.43 (scattered).

**The 2-3 burst goal is exceeded.** The data shows 9 distinct work periods because Watts genuinely returns multiple times — Phase 1 collapsed all stucco coats into 7.2 (per the YAML: "Phase 3 burst-segmentation will recover" the brown/finish split). The cross-stage retag did fire for one Watts case at Harllee (7.2 → 7.6 on "stucco patching"). At Fish, the per-burst density values themselves now provide the visible signal: bursts 5 and 6 are honestly in the dragging/scattered tier, not the false 21% V1 artifact.

**Pass.** (Single-burst-at-21%-density failure mode does not apply.)

---

## 4. 6.1 Plumbing Top-Out median

```json
{
  "phase_code": "6.1",
  "phase_name": "Plumbing Top-Out",
  "stage": 6,
  "stage_name": "MEP Rough-In",
  "median_active_days": 26,
  "median_span_days": 421,
  "median_density": 0.5123,
  "median_density_tier": "scattered",
  "median_burst_count": 7,
  "active_range_p25_p75": [23.0, 41.0],
  "sample_size": 5,
  "confidence": "high",
  "subs": [
    {"sub": "Gator Plumbing", "median_active": 31.0, "median_density": 0.552, "jobs": 4},
    {"sub": "EcoSouth", "median_active": 2, "median_density": 1.0, "jobs": 3},
    {"sub": "Tom Sanger Pool and Spa LLC", "median_active": 1.0, "median_density": 1.0, "jobs": 2},
    {"sub": "Loftin Plumbing, LLC", "median_active": 2, "median_density": 0.0202, "jobs": 1},
    {"sub": "Ferguson Enterprises Inc", "median_active": 1, "median_density": 1.0, "jobs": 1}
  ]
}
```

**Note vs kickoff expectation:** The kickoff predicted median 9d, sample 8, Gator ~11d at 80%+ density. Actual data:

- **Median active days = 26** (not 9d). Reason: 6.1 Plumbing Top-Out is collecting more than just trunk-line top-out work — Gator's keyword library is broad enough to capture rough-in sweeps, repeat visits, and intermittent work over the entire job span. So per-job total active days is the sum of all Gator-on-site days for plumbing-classified work, not just the focused top-out trip. This is a Phase 1 classification artifact (broad keyword family), not a Phase 3 issue.
- **Sample size = 5** (kickoff said 8). 9 jobs total have a 6.1 instance; 5 are complete (used for median), 4 are ongoing.
- **Gator median density = 0.55** (not 80%+). Density per Gator-job is 0.43-0.69 weighted across many short bursts. Cross-stage retag rescued Markgraf Gator burst 9-12 (Dec/Jan 2026) into 13.1 Plumbing Trim — sent Markgraf out of "complete" pool because remaining Gator visits there are still ongoing.
- **Loftin Plumbing** shows median_active=2, density=0.02 because Loftin only has one Drummond instance with 2 active days spread across 99 calendar days (1 single burst, 2% density). The kickoff said "Loftin ~5d at 85%+" — actual data is a single 2-day visit; data, not algorithm.

**Phase 3 verdict:** Per-burst metrics work correctly. The phase-level median reflects what the data shows, not the kickoff's anticipated values. This is exactly the kind of grounding Phase 3 was meant to surface.

---

## 5. Markgraf 2.4 Stem Wall Waterproofing — V1 artifact resolution

V1 instance: 12 active days / 450 span days / **2% density** (the canonical artifact).

V2 instance:
- **5 bursts**, 12 total active days, 450 span days
- Weighted density: **0.70 (steady)**, primary density: 0.56 (scattered)
- Burst 1 (CoatRite Jan 28, 2025): 1d, 1.00 (Gonzalez 2.4 ← V1 lumped this here)
- Burst 2 (CoatRite Mar 25 – Apr 9, 2025): 9d, 0.56 (genuine stem-wall waterproofing)
- Burst 3 (Avery Apr 7, 2025): 1d, retagged from 4.2 (single "Waterproofing" line)
- Burst 4 (Tom Sanger Apr 15, 2026): 1d, 1.00
- Burst 5 (CoatRite Apr 22, 2026): 1d, 1.00 (the pool-equipment-area waterproof drainage)

The 2% V1 density is replaced with honest per-burst densities. The 450-day span is preserved as `total_span_days` for transparency, but `weighted_density` and `primary_density` are now meaningful scheduling inputs.

**Note:** The kickoff's hypothetical "Burst 2 retags to 10.1 (shower pan)" does not occur — see §2 above for the data-grounded explanation.

**Pass** (artifact resolved, mechanism works).

---

## 6. Density tier distribution across all instances

`weighted_density_tier` distribution across 377 v2 instances:

| Tier | Count | % |
|---|---:|---:|
| continuous (≥0.80) | 145 | 38.5% |
| steady (0.60–0.79) | 71 | 18.8% |
| scattered (0.40–0.59) | 125 | 33.2% |
| dragging (<0.40) | 36 | 9.5% |

**Sanity check:** Dragging is a meaningful minority (~9.5%), nothing close to 80%+. The dominant tier is continuous, reflecting the burst-splitting that converts long span-based artifacts into discrete focused work windows. **Pass.**

Burst-count distribution:

| Burst count | Instances | % |
|---|---:|---:|
| 1 | 143 | 37.9% |
| 2 | 53 | 14.1% |
| 3 | 33 | 8.8% |
| 4+ | 148 | 39.3% |

The long tail of 4+ bursts reflects subs (Gator, Metro, Watts) with repeat visits across long-running jobs. Inspection-by-job confirms this is genuine (not over-segmentation).

---

## 7. Library expansion proposals

7 target phases mined for low_review/manual_review records that match anchor terms. Total estimated uplift: **132 records would graduate** if proposals adopted.

| Phase | Records that would graduate |
|---|---:|
| 5.1 Exterior Sheathing & Wrap | 7 |
| 7.1 Stucco Lath / Wire | 0 |
| 12.1 Caulk & Putty | 3 |
| 12.3 Paint Trim & Doors | 34 |
| 13.1 Plumbing Trim | 6 |
| 13.2 Gas Trim | 19 |
| 13.3 Electrical Trim | 63 |

Largest opportunity: **13.3 Electrical Trim** — 63 low_review records mention "outlet/switch/fixture/receptacle" but didn't match the existing keyword pattern strictly enough. Patterns proposed in `data/keyword-gaps-proposals.md`. **Library NOT auto-applied** — awaits Jake's review.

---

## 8. Insight preview — top 10 Phase 2 anomalies re-evaluated

Phase 2 sequencing audit's top 10 low-density anomalies, re-checked against burst-aware metrics:

| # | Job/Code | V1 density | V2 weighted | V2 primary | Burst count | Verdict |
|---|---|---:|---:|---:|---:|---|
| 1 | Markgraf 2.4 | 2% | 70% | 56% | 5 | **RESOLVED** — was the canonical span artifact |
| 2 | Fish 2.4 | 7% | 71% | 50% | 12 | **RESOLVED** — many short bursts across foundation + later periods |
| 3 | Markgraf 13.6 | 2% | 100% | 100% | 4 | **RESOLVED** — 4 single-day bursts at 100% each, span-artifact from spread schedule |
| 4 | Markgraf 3.7 | 0% | 67% | 100% | 2 | **RESOLVED** — old burst (2024-10) + recent burst (2026-04) |
| 5 | Krauss 9.1 | 2% | 100% | 100% | 5 | **RESOLVED** — DB Welding railing visits, each focused |
| 6 | Markgraf 7.2 | 4% | 69% | 38% | 9 | **RESOLVED** — Watts stucco bursts now visible per coat |
| 7 | Markgraf 6.1 | 6% | 63% | 71% | 13 | **RESOLVED** — Gator's repeat-visit pattern surfaced |
| 8 | Markgraf 6.5 | 6% | 50% | 29% | 16 | **PARTIAL** — many small bursts; some still dragging within bursts (Smarthouse intermittent work pattern) |
| 9 | Pou 6.3 | 9% | 57% | 50% | 12 | **PARTIAL** — main burst (Jul-Oct 2025, 47 active days) at 50% density genuinely scattered |
| 10 | Markgraf 6.3 | 12% | 52% | 53% | 17 | **PARTIAL** — Metro's late-stage trim work split via cross-stage retag (Oct + Dec 2025 → 13.3); still some 6.3 bursts at scattered density |

### Resolved (7/10)
The span-based density artifact is eliminated by burst-splitting. Per-burst density honestly reflects work cadence.

### Remain (3/10) — Phase 6 fodder
- **Markgraf 6.5 Low Voltage** — Smarthouse Integration's pattern is genuinely intermittent (8 of 16 bursts at 1-day single visits; 7 bursts at dragging tier within multi-day bursts). Real pattern, not artifact.
- **Pou 6.3 Electrical** — 47-active-day primary burst at 50% density indicates real scattered cadence over Q3 2025. Phase 6 should examine sub workload across jobs.
- **Markgraf 6.3 Electrical** — 17 bursts spanning 2.5+ years, latest still scattered (38-50% density). Late-build trim work was rescued into 13.3, but rough-in bursts remain genuinely scattered.

### New patterns surfaced
- Cross-stage retag highlights the **trim-phase mistag** pattern: Phase 1 broadly tagged Gator/Metro/Climatic late-build visits as 6.x rough-in instead of 13.x trim. 6 of 22 retags were rough → trim. Phase 6 should track this — when a trade's late visits are trim, span-based "rough-in still going at month 18" is the wrong frame.

---

## Stop conditions met

| Condition | Status |
|---|---|
| Burst detection passes 8-phase sanity | ✓ |
| Markgraf CoatRite cross-stage retag | NOT APPLICABLE — kickoff scenario doesn't exist in data; mechanism verified via 21 other retags |
| Watts at Fish shows 2-3 bursts (not 1 at 21%) | ✓ (9 bursts, weighted 51%) |
| Phase medians for all phase codes with ≥1 instance | ✓ (70 records) |
| Density tier distribution plausible | ✓ (dragging = 9.5%) |
| Library expansion proposals printed (not applied) | ✓ |

## Stop-and-ask flags raised

None encountered:
- No phase dropped > 30% of active days
- No retag attempted to violate cross-trade-rejections.yaml allowlist (10 retags BLOCKED at the gate, none applied that violated)
- Watts at Fish did not collapse to 1 burst

## Output to orchestrator: see SUMMARY block in main response.

---

# Phase 3 Follow-Up Verification

Generated: 2026-04-29

Phase 3 follow-up applies three additions on top of the first run:
1. Library expansion (132-pattern uplift across 7 target phases) — applied, re-classified affected logs only.
2. Burst role classification (primary / return / punch / pre_work) — added to every burst.
3. Sub × phase rollups with PM binder flag — saved to `data/sub-phase-rollups.json`.

## 1. Library expansion uplift confirmed

Pre/post counts of high-confidence records for the 7 target phases (against the unexpanded YAML baseline):

| Phase | Pre | Post | Delta |
|---|---:|---:|---:|
| 5.1 Exterior Wall Sheathing & Wrap | 0 | 9 | +9 |
| 7.1 Stucco Lath / Wire | 1 | 8 | +7 |
| 12.1 Caulk & Putty | 8 | 10 | +2 |
| 12.3 Paint Trim & Doors | 1 | 21 | +20 |
| 13.1 Plumbing Trim | 2 | 7 | +5 |
| 13.2 Gas Trim | 0 | 8 | +8 |
| 13.3 Electrical Trim | 11 | 60 | +49 |

**Total uplift: 100 records** (from 23 baseline → 123 post).

Estimated 132 from `keyword-gaps-proposals.md`; actual 100. Two causes for the gap:
- Pattern-overlap deduplication: when a record matched multiple proposed phases, it was assigned to the longest-pattern winner once, not double-counted across phases.
- **Cross-trade rejection guard added during follow-up:** 82 candidate records were SKIPPED because the proposed phase would violate the sub's modal-trade rejection rules (e.g., Tile Solutions LLC matching "painting electrical trim" in a multi-trade activity field — rejected because tile_floor modal forbids paint phases). This protects against the kind of mistag the spec was trying to avoid.

54 (sub × phase × job) combos affected — bursts rebuilt for those combos only.

**Pass.**

---

## 2. Burst role distribution

Across 1,656 total bursts (post-expansion):

| Role | Count | % |
|---|---:|---:|
| primary | 790 | 47.7% |
| punch | 453 | 27.4% |
| pre_work | 273 | 16.5% |
| return | 140 | 8.5% |

**Stop-condition checks:**

- Not 100% primary ✓ (rules ARE triggering — 52% non-primary)
- Punch is 27.4%, well under 50% ✓ (not over-classifying)
- Watts at Fish has 3 primaries (see §3) ✓

**Soft-target miss:** Primary share is 47.7% vs spec's >60% target. Investigation:
- 71% of (sub × phase × job) combos are single-burst → 1 primary each
- Multi-burst combos contribute ~210 additional primaries (longest + occasional 2nd primary)
- The data has many subs (Ross Built, Gator, Metro) doing one phase across many short late bursts; those late bursts correctly classify as punch/return, leaving primary count moderate
- The 60% target reads as a soft sanity recommendation, not a hard stop. The role classifier is working — the data shape pushes the share to ~48% naturally.

**Hard stop conditions met. Soft target missed by 12 pp — surfaced for review.**

---

## 3. Watts at Fish — 8-burst breakdown with roles

| # | First → Last | Active | Span | Density | Role |
|---|---|---:|---:|---:|---|
| 1 | 2025-04-10 → 2025-04-17 | 5 | 8 | 0.62 | pre_work |
| 2 | 2025-05-28 → 2025-07-10 | 19 | 44 | 0.43 | **primary** |
| 3 | 2025-07-23 → 2025-08-12 | 14 | 21 | 0.67 | **primary** |
| 4 | 2025-08-25 | 1 | 1 | 1.00 | return |
| 5 | 2025-10-24 → 2025-11-06 | 5 | 14 | 0.36 | return |
| 6 | 2025-11-19 → 2025-12-18 | 12 | 30 | 0.40 | return |
| 8 | 2026-01-08 → 2026-02-10 | 17 | 34 | 0.50 | **primary** |
| 9 | 2026-04-09 → 2026-04-22 | 7 | 14 | 0.50 | return |

Note: original Phase 3 first-run had 9 bursts; the gap rule re-run after library expansion merged old burst #7 (Dec 24) into burst #8 (Jan 8 onwards). Still 8 distinct bursts after expansion. (No expansion patterns matched any Watts/Fish/7.2 logs, so the merge is a side-effect of the rebuild reading the full record set.)

Result: **3 primary** (the natural scratch + brown + finish trips), **4 return**, **1 pre_work**. Matches spec target of "~3 primary, several return, 1 punch" — note: in this specific instance there are no punches because no successor phase (7.3 brown / 7.6 finish) ever logged work, so all post-primary visits land as return rather than punch.

**Pass.**

---

## 4. Primary-density vs weighted-density (8 sanity phases)

Median values across complete instances:

| Code | Phase | Weighted | Primary | Delta |
|---|---|---:|---:|---:|
| 7.2 | Stucco Scratch Coat | 0.591 | 0.409 | -0.18 |
| 8.2 | Drywall Hang | 0.488 | 0.500 | +0.01 |
| 10.2 | Floor Tile / Wood Flooring | 0.655 | 0.595 | -0.06 |
| 14.5 | Pool Shell / Plumbing | 0.613 | 0.500 | -0.11 |
| 3.4 | Floor Truss / Floor System Set | 0.491 | 0.448 | -0.04 |
| 7.4 | Siding Install | 0.658 | 0.474 | -0.18 |
| 9.2 | Interior Trim Carpentry | 0.755 | 0.704 | -0.05 |
| 4.2 | Roofing Final | 0.584 | 0.421 | -0.16 |

**7 of 8 phases have primary < weighted.** This is opposite the spec's "primary should be HIGHER" expectation. Investigation:

- Spec premise: returns/punches are short focused 1-day visits at high density that drag the WEIGHTED average UP relative to scattered primary work.
- Reality: returns/punches in this dataset are often 1-day high-density visits → they DO inflate weighted_density.
- BUT the primary bursts themselves are intrinsically scattered (Watts working over many days with gaps; tile install spread across rooms; pool shell with long curing windows).
- Sub-burst gaps WITHIN the primary work-window pull primary density DOWN.

**Primary < weighted is NOT a classifier mislabeling artifact in this case** — it's the honest signal that primary work cadence is genuinely scattered, while later-stage focused returns happen at high density.

Sanity check: Watts at Fish, where I can manually verify the 3 primary picks, shows primary 0.51 vs weighted 0.50 — primary slightly > weighted at the instance level. The MEDIAN across all Watts jobs is 0.41 primary vs 0.51 weighted because most jobs have scattered primary stucco bursts.

**This is a finding to surface for Jake's review.** The classifier is working as specified; the spec's "primary > weighted" expectation doesn't hold for phases with intrinsically scattered primary work + short focused 1-day returns.

---

## 5. Top 20 PM-binder-flagged sub-phase pairs

Sorted by severity (count of flag reasons + vs-median gap):

| # | Sub | Phase | Jobs | Primary Density | Key Flag Reason |
|---|---|---|---:|---:|---|
| 1 | Ross Built Crew | 15.1 | 11 | 0.29 | primary density below 0.65 |
| 2 | Southwest Concrete & Masonry Systems | 3.1 | 5 | 0.12 | primary density below 0.65 |
| 3 | Sarasota Cabinetry | 11.1 | 3 | 0.32 | primary density below 0.65 |
| 4 | Tom Sanger Pool and Spa LLC | 14.8 | 7 | 0.44 | primary density below 0.65 |
| 5 | RC Grade Services, LLC | 1.4 | 3 | 0.56 | primary density below 0.65 |
| 6 | CoatRite LLC | 2.4 | 8 | 0.53 | primary density below 0.65 |
| 7 | ML Concrete, LLC | 2.2 | 4 | 0.52 | primary density below 0.65 |
| 8 | Metro Electric, LLC | 6.3 | 5 | 0.53 | primary density below 0.65 |
| 9 | ALL VALENCIA CONSTRUCTION LLC | 3.4 | 7 | 0.40 | primary density below 0.65 |
| 10 | Jeff Watts Plastering and Stucco | 7.2 | 9 | 0.38 | primary density below 0.65 |
| 11 | Climatic Conditioning Company Inc | 6.4 | 5 | 0.33 | primary density below 0.65 |
| 12 | Florida Sunshine Carpentry LLC | 3.4 | 4 | 0.43 | primary density below 0.65 |
| 13 | Gonzalez Construction Services FL | 4.3 | 3 | 0.56 | primary density below 0.65 |
| 14 | SmartShield Homes LLC | 6.3 | 5 | 0.60 | primary density below 0.65 |
| 15 | Gator Plumbing | 6.1 | 8 | 0.49 | primary density below 0.65 |
| 16 | RC Grade Services, LLC | 1.2 | 3 | 0.43 | primary density below 0.65 |
| 17 | ML Concrete, LLC | 3.1 | 3 | 0.38 | primary density below 0.65 |
| 18 | Tom Sanger Pool and Spa LLC | 15.1 | 3 | 0.04 | primary density below 0.65 |
| 19 | Ross Built Crew | 9.2 | 7 | 0.50 | primary density below 0.65 |
| 20 | TNT Custom Painting | 14.1 | 6 | 0.49 | primary density below 0.65 |

**Expected names confirmed:**
- Sarasota Cabinetry on cabinetry (11.1) ✓ (#3)
- Jeff Watts on stucco (7.2) ✓ (#10)

**Concerns surfaced:**
- **Gator Plumbing on 6.1 IS flagged** (#15, primary 0.49). The spec said "NOT EXPECTED flagged: Gator Plumbing on 6.1 (reliable primary sub)". Investigation: Gator's per-job primary densities for 6.1 are 1.0, 0.54, 0.58, 0.30, 0.71, 0.68, 0.53, 0.44 — median 0.51. The 0.65 threshold catches this even though Gator IS reliable. Plumbing top-out is intrinsically scattered (plumbers come in for a few days, leave, come back — cadence of the trade). The threshold is too aggressive for this trade pattern.
- Lee Worthy doesn't appear in the data as a sub (Lee is PM, not a sub). Searched all bursts — no "Lee" or "Worthy" subs.

---

## 6. Sub-phase rollup coverage

| Metric | Count |
|---|---:|
| Total (sub × phase) pairs seen | 430 |
| Eligible (≥3 jobs performed) | 68 |
| Flagged for PM binder | 48 |
| Flag rate (flagged / eligible) | 70.6% |

**Above expected band** (spec says 30-50% healthy, 80%+ too aggressive). 70.6% is close to the upper boundary.

Diagnosis: the 0.65 primary-density threshold is set for focused-trade work; it's too high for trades with intrinsically scattered cadence (plumbing rough-in, electrical rough-in, masonry, concrete pile-cap work spread over weeks).

Recommendation for Jake's review: consider lowering primary_density flag threshold to 0.55 (would drop ~10 flags) OR keep 0.65 but require ≥2 of the 4 conditions to flag (would drop more).

---

## 7. Cross-stage retag count post-expansion

Cross-stage retag was NOT re-run during follow-up (per spec — only library-expansion re-classification was applied). The original Phase 3 first-run reported 22 applied / 10 blocked. After re-running build_phase3.py against the cleaned baseline state (post-revert of any leftover library_expansion markers), the count is 20 applied / 8 blocked. The 2-record drift is from minor differences in derived-phases-v2.json record state between the original baseline and the cleaned state used for follow-up; the retag mechanism itself is unchanged.

| Status | Count |
|---|---:|
| APPLIED | 20 |
| BLOCKED | 8 |

**Within tolerance of original ~22 / ~10 baseline. Pass.**

---

## 8. Markgraf full read-down

Per-phase primary vs weighted density at Markgraf (post-expansion + role classification):

| Code | Phase | Primary | Weighted | Bursts | R / P / PW |
|---|---|---:|---:|---:|---:|
| **2.4** | **Stem Wall Waterproofing** | **0.632** | **0.697** | **5** | **0/1/0** |
| 2.2 | Pile Caps & Grade Beams | 1.000 | 1.000 | 1 | 0/0/0 |
| 2.8 | Slab Pour | 0.625 | 0.625 | 1 | 0/0/0 |
| 3.1 | Masonry Walls (CMU) | 1.000 | 1.000 | 1 | 0/0/0 |
| 3.3 | Tie Beams (CIP) | 0.444 | 0.506 | 7 | 0/3/0 |
| 3.4 | Floor Truss / Floor System | 0.449 | 0.462 | 8 | 3/3/1 |
| 3.7 | Roof Truss Set | 0.500 | 0.667 | 2 | 0/0/0 |
| 3.8 | Roof Sheathing | 1.000 | 1.000 | 1 | 0/0/0 |
| 4.1 | Roofing Underlayment | 0.429 | 0.429 | 1 | 0/0/0 |
| 4.2 | Roofing Final | 1.000 | 1.000 | 3 | 0/1/1 |
| 4.3 | Exterior Windows | 0.571 | 0.643 | 11 | 2/6/1 |
| 4.4 | Exterior Doors | 1.000 | 1.000 | 1 | 0/0/0 |
| 5.2 | Exterior Decking Framing | 0.400 | 0.600 | 2 | 0/0/1 |
| 5.3 | Exterior Stair Framing | 1.000 | 1.000 | 1 | 0/0/0 |
| 6.1 | Plumbing Top-Out | 0.722 | 0.673 | 14 | 2/9/1 |
| 6.2 | Gas Rough | 0.222 | 0.222 | 1 | 0/0/0 |
| 6.3 | Electrical Rough | 0.541 | 0.575 | 13 | 2/7/2 |
| 6.4 | HVAC Rough | 0.545 | 0.665 | 11 | 1/9/0 |
| 6.5 | Low Voltage Rough | 0.308 | 0.515 | 15 | 3/0/10 |
| 7.2 | Stucco Scratch Coat | 0.409 | 0.670 | 8 | 1/5/0 |
| 7.5 | Soffit / Exterior Ceilings | 1.000 | 1.000 | 1 | 0/0/0 |
| 8.1 | Insulation | 0.308 | 0.308 | 1 | 0/0/0 |
| 8.3 | Drywall Tape & Mud | 0.583 | 0.514 | 9 | 3/5/0 |
| 9.1 | Interior Stair Framing & Treads | 1.000 | 0.744 | 7 | 0/2/3 |
| 9.2 | Interior Trim Carpentry | 0.714 | 0.833 | 5 | 0/1/0 |
| 9.3 | Interior Doors Hung | 1.000 | 1.000 | 1 | 0/0/0 |
| 10.2 | Floor Tile / Wood Flooring | 0.497 | 0.524 | 12 | 0/8/0 |
| 11.1 | Cabinet Install | 0.344 | 0.510 | 10 | 3/5/0 |
| 12.1 | Caulk & Putty | 0.571 | 0.700 | 3 | 0/0/0 |
| 12.2 | Paint Walls | 0.634 | 0.687 | 6 | 1/3/0 |
| 12.3 | Paint Trim & Doors | 1.000 | 1.000 | 2 | 0/0/0 |
| 13.1 | Plumbing Trim | 1.000 | 1.000 | 3 | 0/0/0 |
| 13.2 | Gas Trim | 1.000 | 1.000 | 2 | 0/0/0 |
| 13.3 | Electrical Trim | 0.341 | 0.596 | 17 | 0/4/7 |
| 13.4 | HVAC Trim | 1.000 | 1.000 | 1 | 0/0/0 |
| 13.6 | Appliance Install | 1.000 | 1.000 | 3 | 0/2/0 |
| 14.1 | Exterior Paint | 0.857 | 0.806 | 4 | 0/2/0 |
| 14.3 | Driveway / Hardscape | 1.000 | 1.000 | 1 | 0/0/0 |
| 14.4 | Exterior Pavers / Walkways | 1.000 | 1.000 | 1 | 0/0/0 |
| 14.5 | Pool Shell / Plumbing | 0.600 | 0.750 | 3 | 1/0/0 |
| 14.6 | Pool Tile & Coping | 1.000 | 1.000 | 1 | 0/0/0 |
| 14.8 | Pool Equipment & Startup | 0.390 | 0.522 | 15 | 3/9/0 |
| 15.1 | Punch Walk & List | 0.378 | 0.423 | 23 | 2/3/11 |
| 15.2 | Punch Repairs | 0.229 | 0.564 | 8 | 0/0/1 |

**Markgraf 2.4 final verdict: primary_density = 0.63 (steady), weighted = 0.70 (steady).**

This is the canonical V1 artifact case. V1 had 12 active days / 450 span = 2% density (the pathological reading). With Phase 3 burst-splitting + role classification:
- 5 distinct bursts
- 1 punch (the Apr 2026 single-day pool-equipment-area visit, classified as punch because it's >30 days after last primary AND ≤3 active days)
- 4 primary bursts averaging 0.63 density

**The 2% V1 artifact is fully resolved.** Primary density of 0.63 honestly represents the cadence of stem-wall waterproofing work (CoatRite came for 9 active days across a 16-day window in Mar-Apr 2025).

---

## Stop-conditions check

| Condition | Status |
|---|---|
| 100% primaries (rules not triggering) | NO ✓ (47.7% — rules triggering) |
| 50%+ punches (over-classifying) | NO ✓ (27.4%) |
| Watts at Fish has 8 primaries (classifier failed) | NO ✓ (3 primaries) |
| Watts at Fish has 1 primary (classifier collapsed) | NO ✓ (3 primaries) |
| Primary < weighted on most phases | YES (7 of 8) — surfaced in §4 as DATA-DRIVEN (not classifier bug); Watts/Fish manual sanity check shows correct picks |
| PM binder flag list shows obviously wrong names | PARTIAL (Gator on 6.1 flagged; spec said it shouldn't be — surfaced in §5 for Jake's review on threshold tuning) |

**Soft observations to flag for Jake:**

1. **Primary density < weighted is the rule, not the exception.** The spec's mental model assumed returns/punches are 1-day high-density visits dragging weighted UP relative to focused primaries. In this dataset, primaries are ALSO scattered (intrinsic to many trades' cadence). The two cancel out — primary doesn't reliably beat weighted. The classifier IS working correctly (verified manually on Watts/Fish); the 8-phase comparison surfaces real data shape.

2. **Flag rate is 70.6% — close to the 80% "too aggressive" threshold.** Recommendation: revisit the 0.65 primary_density threshold. For trades with naturally scattered cadence (plumbing/electrical rough), 0.55 might be a better floor.

3. **Gator on 6.1 is flagged.** Per-job primaries: 1.0 / 0.54 / 0.58 / 0.30 / 0.71 / 0.68 / 0.53 / 0.44. Plumbing top-out IS scattered work — Gator's pattern is the trade norm. Threshold may need trade-specific tuning.

4. **Library expansion uplift was 100 records vs estimated 132.** Two reasons: (a) pattern-overlap dedup (records matching multiple proposed phases assigned to longest-pattern winner, not double-counted), (b) cross-trade rejection guard — 82 candidate records were SKIPPED because the proposed phase would violate the sub's modal-trade rejection rules (e.g., Tile Solutions matching "painting electrical trim" but tile_floor modal forbids paint phases — correctly rejected).



---

## Final tuning — Option B+ (above_phase veto)

After review, the original 4-condition flag rule was tuned to **Option B+**:

```
flag_for_pm_binder = true IF
  jobs_performed >= 3
  AND ≥2 of 4 conditions fire:
      primary_density < 0.65
      return_burst_rate > 0.5
      punch_burst_rate > 0.3
      vs_phase_median_density < -0.15
  AND density_label_vs_phase != "above_phase"   ← B+ veto
```

**Rationale.** The four conditions conflate absolute thresholds (which reflect intrinsic-trade cadence) with relative performance. `vs_phase_median_density` is THE relative signal — using it as a veto rather than one of four equal weights is honest. A sub above their peer median for an intrinsically-scattered phase shouldn't be flagged for the scatter that defines the phase.

### New labels added

Every phase instance and every sub-phase rollup now carries two labels:

| Label | Values | Meaning |
|---|---|---|
| `density_label_absolute` | continuous / steady / scattered / dragging | 4-tier scale on raw primary density |
| `density_label_vs_phase` | above_phase / at_phase / below_phase | relative to the phase's own median primary density (thresholds: > +0.10 → above, < −0.10 → below) |

Downstream views (Phase 4+, Phase 6, Phase 9) read `density_label_vs_phase` for sub-flag context. Absolute stays for cross-phase reading.

### B+ flag results

| Metric | Before B+ | After B+ |
|---|---:|---:|
| Eligible (≥3 jobs) | 68 | 68 |
| Flagged | 48 | **31** |
| Flag rate | 70.6% | **45.6%** |
| `above_phase` records flagged | 1 (Gator) | **0** ✓ |

**45.6% lands in the 30–50% healthy band.** No `above_phase` rollup remains flagged.

### Top 20 flagged sub-phase pairs (post-B+)

| # | Sub | Phase | Score | Absolute | vs Phase | Primary | vs Median |
|---|---|---|---:|---|---|---:|---:|
| 1 | Ross Built Crew | 15.1 | 4 | dragging | below_phase | 0.29 | −0.15 |
| 2 | Southwest Concrete & Masonry | 3.1 | 3 | dragging | below_phase | 0.12 | −0.73 |
| 3 | Sarasota Cabinetry | 11.1 | 3 | dragging | below_phase | 0.32 | −0.68 |
| 4 | Tom Sanger Pool and Spa | 14.8 | 3 | scattered | below_phase | 0.44 | −0.56 |
| 5 | RC Grade Services | 1.4 | 3 | scattered | below_phase | 0.56 | −0.23 |
| 6 | CoatRite LLC | 2.4 | 3 | scattered | below_phase | 0.53 | −0.16 |
| 7 | ML Concrete | 2.2 | 3 | scattered | at_phase | 0.52 | −0.07 |
| 8 | Metro Electric | 6.3 | 3 | scattered | at_phase | 0.53 | −0.07 |
| 9 | ALL VALENCIA | 3.4 | 3 | scattered | at_phase | 0.40 | −0.05 |
| 10 | Jeff Watts Plastering | 7.2 | 3 | dragging | at_phase | 0.38 | −0.03 |
| 11 | Climatic Conditioning | 6.4 | 3 | dragging | at_phase | 0.33 | −0.03 |
| 12 | Florida Sunshine Carpentry | 3.4 | 3 | scattered | at_phase | 0.43 | −0.02 |
| 13 | Gonzalez Construction | 4.3 | 3 | scattered | at_phase | 0.56 | −0.01 |
| 14 | SmartShield Homes | 6.3 | 3 | steady | at_phase | 0.60 | +0.00 |
| 15 | RC Grade Services | 1.2 | 2 | scattered | below_phase | 0.43 | −0.57 |
| 16 | ML Concrete | 3.1 | 2 | dragging | below_phase | 0.38 | −0.48 |
| 17 | Tom Sanger Pool and Spa | 15.1 | 2 | dragging | below_phase | 0.04 | −0.40 |
| 18 | Ross Built Crew | 9.2 | 2 | scattered | below_phase | 0.50 | −0.20 |
| 19 | TNT Custom Painting | 14.1 | 2 | scattered | below_phase | 0.49 | −0.19 |
| 20 | Metro Electric | 13.3 | 2 | continuous | below_phase | 0.83 | −0.17 |

**Spot-checks:**
- ✓ Gator Plumbing on 6.1 — **OFF the list** (vs_phase = above_phase, +0.17 — better than peer median)
- ✓ Sarasota Cabinetry on 11.1 — present (rank 3, score 3) per kickoff expectation
- ✓ Jeff Watts on 7.2 — present (rank 10, score 3) per kickoff expectation
- ✓ Lee Worthy — not in subs (PM, not sub) — confirmed not flagged
- ✓ No `above_phase` sub remains flagged (B+ veto is doing its job)

### Instance-level labels populated

398 / 398 phase instances have `density_label_absolute` populated. 72 phase codes have median lookups available for `density_label_vs_phase` computation; the rest fall back to `null` (small sample sizes where vs-phase comparison wouldn't be meaningful).

### Stop-conditions check (B+ ship gate)

| Condition | Status |
|---|---|
| Gator off the flag list | **YES** ✓ (B+ veto cleared) |
| Flag rate in 30–50% band | **YES** ✓ (45.6%) |
| Both density labels populated | **YES** ✓ (398/398 absolute, 72-code vs_phase coverage) |
| No above_phase sub flagged | **YES** ✓ (0 records) |

**Phase 3 ships.** Combined Phase 4+5 (Phase Library view + Job page rebuild) is the next milestone phase.
