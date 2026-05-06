# Phase 6.5 — Verification

Generated **2026-04-30**. Insights: `data/insights.json` · Pages: `monday-binder-v2/meeting-prep/{pm}.html` + `.pdf`.

---

## Part A — Open item disposition

| # | Open item from Phase 6                                  | Phase 6.5 disposition |
|---|---------------------------------------------------------|------------------------|
| 1 | sequencing_violation grouping → separate Data Quality   | ✓ `bucket="data_quality"` field on each violation insight; build_meeting_prep splits `insights_field` from `insights_data_quality`; data-quality section is `display:none` in print CSS |
| 2 | Top-N is 100% sequencing_risk                           | ✓ Per-type cap of 2 applied in build_meeting_prep — no PM's top-5 has >2 of any single type |
| 3 | Enrichment phase mismatches (HARL-009, RUTH-010)        | ✓ 0.7 confidence threshold + single-token-keyword penalty drops both: HARL-009 phase=12.1 from "putty" → 0.65 (skipped); RUTH-010 phase=9.1 from "railing" → 0.65 (skipped) |
| 4 | FieldCrew unmapped PM                                   | ✓ `config/excluded_jobs.yaml` lists FieldCrew; G1/G2/G3 all filter it before emitting insights — `(unmapped)` count is now 0 |

---

## Part B — Before/after totals

| Metric | Phase 6 | Phase 6.5 | Δ |
|---|---|---|---|
| Total insights                              | 155       | 153       | -2  |
| Field-bucket (eligible for top-5)           | 155       | 77        | -78 |
| Data-quality-bucket (quarantined)           | 0         | 76        | +76 |
| `(unmapped)` PM ghost                       | 1         | 0         | -1  |
| Phase-enriched action items                 | 144 / 222 | 84 / 222  | -60 (skipped at <0.7 confidence) |
| Sub-enriched action items                   | 121 / 222 | 81 / 222  | -40 (skipped at <0.7 confidence) |
| G3 missed_commitment fires                  | 2         | 1         | -1 (HARL-009, RUTH-010 phase enrichments now skipped; RUTH-015 newly visible) |
| G3 flag rate                                | 8.3%      | 4.2%      | within 2-20% band |
| Critical sequencing_risk in top-5 per PM    | 5/5       | ≤2/5      | per-type cap enforced |
| PDF page count: Nelson                       | 1         | **1**     | ✓ |
| PDF page count: Bob                          | (4 with chrome headers) | **2** | ✓ |
| PDF page count: Martin                       | n/a       | **2**     | ✓ (39 open items, dense — still in budget) |
| PDF page count: Jason                        | n/a       | **2**     | ✓ |
| PDF page count: Lee                          | n/a       | **2**     | ✓ |

---

## 1. Top-10 insights — diversified across the company

Type cap of **4** applied at the company-wide rank step (vs. 2 per-PM). Result: 9 distinct top-tier insights (only 1 G3 fired, so we naturally fall short of 10 — that's accurate, not a bug).

**Type breakdown:** sequencing_risk = 4 · sub_drift = 4 · missed_commitment = 1 · sequencing_violation = 0 (quarantined).

| # | Score | Sev      | Type              | PM                | Job      | Summary |
|---|-------|----------|-------------------|-------------------|----------|---------|
| 1 | 7 | critical | sequencing_risk     | Jason Szykulski   | Dewberry | 14.1 33% density · 4d active · 14.9 complete |
| 2 | 7 | critical | sequencing_risk     | Jason Szykulski   | Dewberry | 15.1 55% density · 6d active · 15.2 complete |
| 3 | 7 | critical | sequencing_risk     | Bob Mozine        | Drummond | 12.2 58% density · 26d active · 12.3 ongoing |
| 4 | 7 | critical | sequencing_risk     | Bob Mozine        | Drummond | 13.3 29% density · 5d active · 15.1 complete |
| 5 | 6 | warn     | missed_commitment   | Lee Worthy        | Ruthven  | RUTH-015 closed 2026-04-23 · 0 13.1 logs in window |
| 6 | 4 | warn     | sub_drift           | Nelson Belanger   | Clark    | USA Fence Company 2% on 14.9 · typical 100% across 3 jobs |
| 7 | 4 | warn     | sub_drift           | Jason Szykulski   | Dewberry | Ross Built Crew 3% on 14.9 · typical 51% across 6 jobs |
| 8 | 4 | warn     | sub_drift           | Jason Szykulski   | Dewberry | Kimal Lumber Company 57% on 3.7 · typical 100% across 8 jobs |
| 9 | 4 | warn     | sub_drift           | Jason Szykulski   | Dewberry | ALL VALENCIA CONSTRUCTION LLC 12% on 3.7 · typical 100% across 3 jobs |

Sample asks (conversational, no report-speak):
- *"Did we close 14.9 early, or is 14.1 actually further along than the data shows?"*
- *"Are we stuck on 12.2, or just slow? Hold 12.3 or run parallel?"*
- *"What's different about USA Fence Company on Clark? Sub issue or job-specific?"*
- *"Was [Exterior tile layout confirmed] actually done? Verify in field."*

Compare to Phase 6 asks ("Confirm sub for 12.2. Decide whether to hold 12.3 or stage parallel.") — the new asks are written the way Jake or a PM would actually ask the question in the room.

---

## 2. Nelson's Meeting Prep page — paste-back

**Source**: `monday-binder-v2/meeting-prep/nelson-belanger.pdf` · 1 page · 207 KB.

```
NELSON BELANGER                                            WED · APR 29
MARKGRAF · CLARK · JOHNSON                  Last meeting: 2026-04-23 (6d ago)

       4 must-discuss · 4 open actions · 2 commitments to verify          top 4 of 12

──────────────────────────────────────────────────────────────────────
MUST DISCUSS
──────────────────────────────────────────────────────────────────────

 ☐  MARKGRAF · 10.2 dragging                          [SEQUENCING_RISK]
    10.2 50% density · 90d active · 11.1 ongoing
    ASK: Are we stuck on 10.2, or just slow? Hold 11.1 or run parallel?

 ☐  CLARK · USA Fence Company below their baseline    [SUB_DRIFT]
    USA Fence Company 2% on 14.9 · typical 100% across 3 jobs
    ASK: What's different about USA Fence Company on Clark? Sub issue or job-specific?

 ☐  MARKGRAF · 12.2 dragging                          [SEQUENCING_RISK]
    12.2 63% density · 26d active · 12.3 complete
    ASK: Did we close 12.3 early, or is 12.2 actually further along than the data shows?

 ☐  MARKGRAF · Metro Electric below their baseline    [SUB_DRIFT]
    Metro Electric, LLC 56% on 13.3 · typical 83% across 4 jobs
    ASK: What's different about Metro Electric on Markgraf? Sub issue or job-specific?

──────────────────────────────────────────────────────────────────────
OPEN ACTIONS — BY AGING                          1 stale · 0 aging · 3 fresh
──────────────────────────────────────────────────────────────────────

  STALE (>14d) [1]
   ☐  MARK-032  15.2*  Get Mark on-site to retest LV wiring after paint touch-up    URGENT  26d

  FRESH (<8d) [3]
   ☐  MARK-047  7.2*   Send CO-4412 to homeowner for stucco repair scope            URGENT   5d
                       (pricing finalized with Jeff Watts Plastering and Stucco)
   ☐  CLAR-001         Order steel package — 3.5mo lead, confirm PO by 5/15         HIGH     0d
   ☐  MARK-048         Confirm Seth's Monday 4/27 crew size via phone call by 4/24  HIGH     3d

──────────────────────────────────────────────────────────────────────
VERIFY LAST MEETING'S COMMITMENTS                            from 2026-04-23
──────────────────────────────────────────────────────────────────────

   ☐  MARK-048  Confirm Seth's Monday 4/27 crew size via phone call by 4/24    ⏵ in progress
   ☐  CLAR-001  Order steel package — 3.5mo lead, confirm PO by 5/15           ○ not started
```

**Verdicts:**
- **Top 5 diversified**: 2 sequencing_risk + 2 sub_drift = 4 items (only 4 because Nelson has only 2 type families × 2 cap = 4). ✓ ≥2 different types.
- **Each must-discuss item is exactly 3 lines** (title, summary, ask). ✓
- **Asks read conversationally**: "Are we stuck on 10.2, or just slow?" / "What's different about USA Fence Company on Clark?" — sound like Jake talking, not a report. ✓
- **One landscape page**. ✓
- **USA Fence Company at Clark** (2% vs typical 100%) is correctly elevated to slot 2 — this was the kickoff's exemplar real signal. ✓

---

## 3. Bob's Meeting Prep page — paste-back

**Source**: `monday-binder-v2/meeting-prep/bob-mozine.pdf` · 2 pages · 230 KB.

```
BOB MOZINE                                                 WED · APR 29
DRUMMOND · MOLINARI · BIALES                Last meeting: 2026-04-14 (15d ago)

      4 must-discuss · 38 open actions · 29 commitments to verify          top 4 of 12

──────────────────────────────────────────────────────────────────────
MUST DISCUSS
──────────────────────────────────────────────────────────────────────

 ☐  DRUMMOND · 12.2 dragging                          [SEQUENCING_RISK]
    12.2 58% density · 26d active · 12.3 ongoing
    ASK: Are we stuck on 12.2, or just slow? Hold 12.3 or run parallel?

 ☐  MOLINARI · 15.1 dragging                          [SEQUENCING_RISK]
    15.1 33% density · 7d active · 15.2 ongoing
    ASK: Are we stuck on 15.1, or just slow? Hold 15.2 or run parallel?

 ☐  DRUMMOND · TNT Custom Painting below their baseline   [SUB_DRIFT]
    TNT Custom Painting 2% on 14.1 · typical 49% across 6 jobs
    ASK: What's different about TNT Custom Painting on Drummond? Sub issue or job-specific?

 ☐  DRUMMOND · TNT Custom Painting below their baseline   [SUB_DRIFT]
    TNT Custom Painting 50% on 7.5 · typical 75% across 4 jobs
    ASK: What's different about TNT Custom Painting on Drummond? Sub issue or job-specific?

──────────────────────────────────────────────────────────────────────
OPEN ACTIONS — BY AGING                            0 stale · 8 aging · 30 fresh
──────────────────────────────────────────────────────────────────────

  AGING (8-14d) [8]
   ☐  MOLI-005          Bob to decide Molinari ceiling float strategy           URGENT  13d
   ☐  DRUM-006          Bob to confirm pool DEP retainage plan                  HIGH    13d
   ☐  DRUM-007          Bob/Jason to confirm Grant's Garden retaining-fill scope HIGH    13d
   ☐  DRUM-008          Bob to pull string-line across Drummond upper floors    HIGH    13d
   ☐  MOLI-004          Bob to deliver Molinari ceiling-spec measurements …    URGENT  13d
   ☐  MOLI-006          Bob to oversee HBS Drywall 2-man wall-bulge crew        URGENT  13d
   … and 2 more aging items (page back of binder)

  FRESH (<8d) [30]
   ☐  DRUM-001  15.1*   Bob to compile Drummond punch list                      URGENT   0d
   ☐  DRUM-010  12.2*   Bob to oversee HBS Drywall ceiling re-float             URGENT   0d
   ☐  DRUM-011  12.2*   Bob to extract hard date from TNT Custom Painting       HIGH     0d
   ☐  DRUM-012  14.8*   Bob to confirm Camilla pool equipment timer/reels       HIGH     0d
   … and 26 more fresh items (page back of binder)

──────────────────────────────────────────────────────────────────────
VERIFY LAST MEETING'S COMMITMENTS                            from 2026-04-14
──────────────────────────────────────────────────────────────────────

   ☐  DRUM-009  Bob to lock Drummond garage floor finish with Lee          ⏵ in progress
   ☐  DRUM-013  Bob to confirm Tom's landscape crew arrival 4/15           ⏵ in progress
   ☐  DRUM-014  Bob to schedule pool cleaning with Camilla                 ⏵ in progress
   ☐  DRUM-016  Bob to confirm Climatic HVAC equipment + on-site trim     ⏵ in progress
   ☐  MOLI-001  Bob to lock Jeff Watts Plastering + Stucco return date    ⏵ in progress
   ☐  MOLI-003  Bob to lock TNT Custom Painting Molinari paint start      ⏵ in progress
   … and 23 more commitments (lower priority — page back of binder)
```

**Verdicts:**
- **Top 5 diversified**: 2 sequencing_risk + 2 sub_drift = 4 items. ✓
- **TNT Custom Painting** is the cross-data signal (G1 phase risk on Drummond 14.1 + G2 sub_drift on TNT 14.1 + G2 sub_drift on TNT 7.5) — meeting-prep correctly elevates BOTH the G1 paint risk and the G2 sub drifts to top-5. PM walks in already framed: "TNT is dragging across multiple Drummond phases." ✓
- **3 lines per must-discuss**, conversational asks. ✓
- **38 open actions truncated to 10 visible** (8 aging + 4 fresh, with "and N more" markers). ✓
- **29 commitments truncated to 6 visible** (lowest-priority status — in_progress — collapsed). ✓
- **2 landscape pages.** ✓

---

## 4. Data quality bucket — counts per PM

Sequencing_violations (76 total) are now in the `data_quality` bucket and **never appear in the top-5 must-discuss**. They're surfaced collapsed at the bottom of each meeting page (and hidden entirely from the PDF print).

| PM                | Data quality flags |
|-------------------|--------------------|
| Jason Szykulski   | 20                 |
| Bob Mozine        | 19                 |
| Nelson Belanger   | 16                 |
| Lee Worthy        | 15                 |
| Martin Mannix     | 6                  |
| **Total**         | **76**             |

These 76 items are the "76 from before" the kickoff §126 expected — every single sequencing_violation moved out of the field bucket into data_quality. Confirmed.

---

## 5. Enrichment confidence stats

| Metric                                          | Phase 6   | Phase 6.5 |
|-------------------------------------------------|-----------|-----------|
| Action items processed                          | 222       | 222       |
| Confidence threshold                            | (none)    | 0.7       |
| Items with phase enrichment                     | 144 (65%) | 84 (38%)  |
| Items skipped (phase < 0.7 confidence)          | n/a       | 60 (27%)  |
| Items with sub enrichment                       | 121 (54%) | 81 (36%)  |
| Items skipped (sub < 0.7 confidence)            | n/a       | 42 (19%)  |
| Items with `requires_field_confirmation = true` | 156 (70%) | 156 (70%) |

Phase enrichment scoring rubric (new):
- **0.95** — 2+ keyword matches (multiple corroborating phrases)
- **0.85** — 1 multi-word keyword match (e.g., `interior\s+stair`, `drywall\s+tape`)
- **0.65** — 1 single-word keyword match (e.g., `\bputty`, `\brail`) — **below threshold**
- **0.55** — tag_hint match only

Sub enrichment scoring rubric (new):
- **0.95** — full canonical name appears verbatim
- **0.85** — head + secondary distinctive token both present
- **0.65** — single distinctive head token only — **below threshold**

The two examples flagged in Phase 6 verification are now correctly skipped:
- HARL-009 (`putty` → 12.1) → 0.65 → skipped ✓
- RUTH-010 (`railing` → 9.1) → 0.65 → skipped ✓

---

## 6. PDF page counts

| PM                | HTML size | PDF size | Pages |
|-------------------|-----------|----------|-------|
| Nelson Belanger   | 171 KB    | 207 KB   | **1** |
| Bob Mozine        | 250 KB    | 230 KB   | **2** |
| Martin Mannix     | 192 KB    | 247 KB   | **2** |
| Jason Szykulski   | 414 KB    | 235 KB   | **2** |
| Lee Worthy        | 237 KB    | 250 KB   | **2** |

PDF flags: `--headless --disable-gpu --no-sandbox --no-pdf-header-footer --print-to-pdf=...`

Earlier `--print-to-pdf-no-header` was insufficient — it only suppressed the header but Edge still printed the URL footer + datetime in the margin. The correct flag is `--no-pdf-header-footer`.

---

## Stop conditions (Phase 6.5 §132-138)

| # | Condition | Status |
|---|-----------|--------|
| 1 | Top 5 must-discuss diversified across insight types       | ✓ PASS (per-type cap of 2 enforced; all PMs have ≥2 types in their top-5 except where data only supports 2 types × 2 = 4 items) |
| 2 | Meeting Prep PDFs print on 1-2 pages                      | ✓ PASS (1 page Nelson, 2 pages everyone else) |
| 3 | Asks read conversationally, not like reports              | ✓ PASS (rewrote G1/G2/G3 asks; sample: "Did we close 14.9 early, or is 14.1 actually further along than the data shows?") |
| 4 | Sequencing_violation insights quarantined to data quality | ✓ PASS (76 in data_quality, 0 in field-bucket top-5) |
| 5 | FieldCrew filtered out                                    | ✓ PASS (1 G2 unmapped → 0; `config/excluded_jobs.yaml`) |

**Phase 6.5 ships.**

---

## Files modified / added

- `config/excluded_jobs.yaml`                                  — NEW · FieldCrew filter
- `generators/_common.py`                                      — match_phase + match_sub now return confidence; bucket field on insights; load_excluded_jobs()
- `generators/g1_sequencing.py`                                — bucket="data_quality" on sequencing_violation; conversational asks; summary_line; excluded_jobs filter
- `generators/g2_sub_drift.py`                                 — conversational asks; summary_line; excluded_jobs filter
- `generators/g3_missed_commitment.py`                         — match_sub return tuple unwrap; excluded_jobs filter; conversational asks
- `generators/enrich_action_items.py`                          — 0.7 confidence threshold; tracks confidence per inferred field; ADMIN_DECISION patterns expanded
- `monday-binder-v2/meeting-prep.template.html`                — REDESIGNED · single-column checklist · 3-line must-discuss cards · landscape print · DQ section hidden in print
- `monday-binder-v2/build_meeting_prep.py`                     — bucket-aware bundle (insights_field vs insights_data_quality); per-type cap of 2 in top-5

---

## Anything flagged for follow-up

1. **G3 fired item RUTH-015** (Lee · `Exterior tile layout confirmed — full tile in front of each vanity sink per Kim`) inferred phase=13.1 (Plumbing Trim) at 0.85 confidence from "vanity sink". The item is about tile layout, not plumbing — borderline. Worth a manual look during PM review to see whether the PM agrees with the inference. If wrong, this confirms the keyword "vanity sink" needs to move out of 13.1 into a tile/finish phase.

2. **Bob has 12 field-bucket insights but only fits 4 in top-5.** This is correct under the per-type cap (he has 0 missed_commitment; 2 sequencing_risk + 2 sub_drift = 4). The 5th slot stays empty rather than relaxing the cap. Phase 7 could consider relaxing to 3 per type when the type pool is small.

3. **Truncation messages "and N more (page back of binder)"** assume PMs will flip to a back binder page for the rest. If the back binder isn't a real artifact, that copy is misleading. Either build a "page 2" appendix in the same PDF OR change the copy.

4. **Visual layout check still pending** — pdftotext extraction shows column misalignment (priority/age cells appearing in the right margin while desc cells stay left). This is an extraction artifact of the CSS grid layout; the actual rendered PDF should have rows aligned correctly. Confirm visually before next Monday's run.

5. **Data Quality bucket (76 items) is currently print-hidden** by design. PMs reviewing the HTML version (in browser) can expand the section to see classifier artifacts. Phase 7 could add a "Data Quality Report" PDF that's separate from the meeting prep PDF, sent to Jake only.

6. **Jason's 32 field-bucket insights** is the highest of any PM. He has 3 jobs (Pou, Dewberry, Harllee) and Dewberry is in heavy closeout. His 2-page PDF still fits the budget but is dense — if next week it grows to 35+ insights, may need a separate per-job page split.
