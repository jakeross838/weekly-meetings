# Phase 1 — Sub Reclassification · PLAN

## Goal
Re-derive every sub's true trade(s) from the actual text in daily-log description / notes / comment fields. Throw out the existing category tags. Output is a reclassification diff Jake reviews before anything downstream is built.

## Inputs
- `C:\Users\Jake\buildertrend-scraper\data\daily-logs.json` — 3,226 logs, 12 jobs, 181 crews, 51 distinct parent_group_activities tags
- Existing sub category tags (for diff comparison only — not as truth)
- Filter list of non-subs from [SPEC PART 2](../../SPEC.md#part-2--sub-classification-rebuild-from-log-descriptions)
- Canonical sub-name guardrails from `feedback_sub_names.md` memory — do NOT invent names not in `crews_clean`

## Method (5 steps)

### Step 1 — Filter
Remove non-subs entirely. Three buckets:
- **Hard delete:** `PilingsFoundation`, `Plan Review*`, `Documents`, `1Passed.Inspection for Framing`, `Yes`, `Multi-sub days (not solo-attributable)`, `American Express Simply Cash Business CC`, `Sunbelt Rentals`
- **`external_entities`:** utilities — `FPL`, `TECO Peoples Gas-Shepard`
- **`inspection_authorities`:** building departments — `City of Anna Maria`, `Town of Longboat Key`, `City Of Sarasota`

Print the filter list with log counts. Verify nothing real got dropped.

### Step 2 — Build keyword library
Cover all 67 phase codes from [SPEC PART 3](../../SPEC.md#part-3--canonical-15-stage-build-sequence-the-spine). Each pattern is action-verb + material/element. Save to `config/phase-keywords.yaml` (org-configurable). Print the full library before applying.

### Step 3 — Two-pass classification
- **Pass 1 (high confidence):** scan description + notes + parent_group_activities. Match against keyword library. Highest-specificity match wins. Tag log entry with `derived_phase_code` and `classification_confidence: high`.
- **Pass 2 (low_review):** for Pass 1 misses, fall back to: sub's most-common derived phase × current job stage. Tag with `classification_confidence: low_review`.
- **Unclassified:** anything still unmatched goes to `requires_manual_review`. Excluded from analytics.

### Step 4 — Diff output (grouped by sub)
Per-sub block with top-5 retags by volume + sample description text. Format from KICKOFF.md.

After all per-sub blocks: summary table (totals by confidence, manual-review %, top-10 phase tags by volume post-reclass) + 10 spot-check sub confirmations.

### Step 5 — Persist artifacts
- `config/phase-keywords.yaml` — keyword library
- `config/sub-filters.yaml` — non-sub filter list
- `data/reclassification-diff.md` — readable diff
- `data/derived-phases.json` — machine-readable mapping (logId → derived_phase_code list + confidence)
- `phases/01-sub-reclassification/VERIFICATION.md` — QA artifacts

## Stop conditions
1. Filter list printed and verified ✓
2. Keyword library printed and saved to config ✓
3. Diff generated grouped by sub with summary table ✓
4. All 10 spot-check subs present in diff ✓
5. `requires_manual_review` % is under 5% — if higher, library needs more patterns; stop and add before completing

## Stop-and-ask triggers
If any of the 10 spot-check subs come out structurally wrong:
- CoatRite still showing as masonry
- Ross Built Crew bucketed as one trade
- Metro Electric NOT splitting rough/trim/low-voltage
- Gator Plumbing NOT splitting rough/trim/gas
- Multi-trade subs (M&J, ALL VALENCIA, DB Welding, Rangel) NOT showing multiple derived phases
…flag in summary instead of shipping. Roll-back is more expensive than a stop.

## Standing rules (apply throughout)
- v1 stays running; this phase is read-only against existing data. Outputs go to new `config/` and `data/` paths.
- Recalculate, don't increment.
- Org-configurable: keywords + filter list in YAML, no hardcoded values.
- Backward compatible — old binders still load.
- Print-legible labels (no emoji-only).

---

## Retry — what changed

The first run produced 42% `tag_only` attribution. The orchestrator flagged that as violating the foundation: tag noise from multi-phase logs was getting credited to subs whose own line text said nothing about that phase. The retry inverts the logic — sub's own line is primary, parent activity tags only disambiguate when the sub has historical text-evidence for that phase.

### Classifier structure changes

- **Pass 1 (`high`)** — unchanged: sub-line text matches keyword library. 26% → 43% after keyword library expansion.
- **Pass 2 (`tag_disambiguated`)** — new gated path. The sub's own line is generic AND parent_group_activities tag matches one specific phase, AND the sub has ≥3 high-confidence Pass 1 logs for that phase historically. If zero text-evidence history, the tag is rejected. (Was `tag_only` 42% in first run with no gate; now 5.77%.)
- **Pass 3 (`low_review`)** — modal fallback. Sub-line unattributable + tag absent/multi-phase. Fall back to sub's modal phase. Requires ≥3 Pass 1 logs total (statistical basis).
- **Pass 4 (`manual_review`)** — anything still unmatched. (Was 1.60% in first run hiding behind tag noise; now correctly captures 11.39%.)

### Three additional rules layered on top

- **Rule 1** — Multi-phase log de-attribution: if a single log has 3+ different parent activity tags AND the sub's own line is generic, credit the sub for ONLY their modal phase. Other tags do not produce attributions.
- **Rule 2** — Cross-trade rejection from `config/cross-trade-rejections.yaml`. Hard-coded rejections (e.g., plumbing modal trade can never be credited for stucco/electrical/tile/etc.) override Pass 2. Multi-trade allowlist provides per-sub overrides.
- **Rule 3** — Defer Watts burst-segmentation: 7.2/7.3/7.6 collapse to 7.2 in Phase 1. Phase 3 burst-segmentation will split via date proximity.

### New YAML — `config/cross-trade-rejections.yaml`

Three sections drive cross-trade rejection:
- `phase_groups` — abstract group names (`all_electrical_phases`, etc.) expand to concrete phase code lists
- `modal_trade_rejections` — for each modal trade (plumbing, electrical, tile_floor, etc.), list of forbidden phase codes/groups
- `multi_trade_allowlist` — per-sub overrides allowing specific phases through (with optional `conditional_codes` like Tom Sanger requiring "deck" keyword)
- `force_modal_trade` — explicit modal lock for Architectural Marble (stone_counters), Detweilers (plumbing), DB Welding (metal_fab)
- `require_text_signal` — phases too easy to false-positive on via tag alone (2.4, 2.5, 7.2, 7.3, 7.6, 10.1, 14.7, 15.1, 15.5) — these skip Pass 2 entirely

### <3-log sub bypass refined

For subs with <3 high-confidence Pass 1 logs total:
- Pass 1 high-confidence text matches: KEEP, credit normally.
- Pass 2 tag-disambiguation: BYPASS, route directly to manual_review. No statistical basis for modal trade with <3 logs.

### Numbered-line extractor

Improved to handle BT log formatting inconsistencies — accepts "1.", "1)", and "1 " (digit-space without period) as line markers. This recovered 700+ additional sub-attributions over first run.

### Final results (first run → retry)

| Confidence | First run | Retry | Threshold |
|---|---|---|---|
| `high` | 26.28% | **42.98%** | 35–50% ✓ |
| `tag_only` / `tag_disambiguated` | 41.97% | **5.77%** | <15% ✓ |
| `low_review` | 30.14% | **39.86%** | 25–40% ✓ |
| `manual_review` | 1.60% | **11.39%** | 5–12% ✓ |

The 42% `tag_only` collapsed to 6% (correctly gated) and the hidden manual_review surfaced honestly (11%). All five must-be-zero spot-checks confirmed at 0. All six multi-trade preservation spot-checks pass with documented data-gap notes for missing phases.

### Greenlit acceptance — two notes for the record

**1. Agent-added YAML entries kept.** During the retry rebuild, the classifier agent added two entries that were not in the explicitly-approved set:
- `modal_trade_rejections.metal_fab` — DB Welding's modal trade. Forbids plumbing/electrical/concrete/paint/roofing/drywall/tile/stucco/pool. Consistent with verbally-approved direction ("DB Welding is metal/stairs/hoods only").
- `force_modal_trade["DB Welding Inc."]: metal_fab` — locks DB Welding so auto-derivation can't drift to another modal.

Both kept on Jake's call. Document here so they don't look like silent additions on later review. The agent extending the framework rather than executing rote was the right judgment.

**2. Keyword library expansion deferred to Phase 3.** The 43% `high` rate is in target but at the low end. We did NOT iterate keywords now — Phase 3 burst detection will naturally surface the worst gaps as date-clusters of `low_review` logs from the same sub. Mining those clusters with real evidence beats guessing patterns now.

Deferred follow-up tracked: when Phase 3 ships, expect a small library-expansion pass driven by the date clusters.
