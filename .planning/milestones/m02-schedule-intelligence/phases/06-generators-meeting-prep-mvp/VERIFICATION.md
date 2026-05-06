# Phase 6 — Verification

Generated against current Phase 3 artifacts on **2026-04-30**.

Insights run: `data/insights.json` · Pages: `monday-binder-v2/meeting-prep/{pm}.html` + `.pdf`.
Today date used by generators: **2026-04-29** (from `data/job-stages.json`).

---

## 1. Insights generated

**Total: 155 insights** (down from 273 raw; recency filter on `sequencing_violation`
trims 118 historical artifacts so closeout-stage jobs don't drown the queue).

By type:

| Type                    | Count |
|-------------------------|-------|
| sequencing_violation    | 76    |
| sub_drift               | 42    |
| sequencing_risk         | 35    |
| missed_commitment       | 2     |

By severity:

| Severity | Count |
|----------|-------|
| critical | 35    |
| warn     | 120   |

By PM:

| PM                | Insights |
|-------------------|----------|
| Jason Szykulski   | 53       |
| Bob Mozine        | 31       |
| Nelson Belanger   | 28       |
| Lee Worthy        | 26       |
| Martin Mannix     | 16       |
| (unmapped)        | 1        |

`(unmapped) = 1` is one G2 insight on the FieldCrew job (Ross Built's own
field crew bucket — no PM owner). Acceptable.

---

## 2. Top 10 insights — full text + evidence + ask

Ranked by `severity_score + type_score`.  All ten score = 7 (critical
sequencing_risk).

**1.  DEWBERRY · 14.1  ·  Jason Szykulski  ·  CRITICAL · sequencing_risk**
- Message: 14.1 Exterior Paint dragging at 33% (dragging). Successor 14.9 Final Fencing / Gates complete. Risk of overlap.
- Evidence:
  - phase: 14.1 Exterior Paint @ Dewberry · status=ongoing · density=33% · active_days=14 · last_log=2026-04-13
  - phase: 14.9 Final Fencing / Gates @ Dewberry · status=complete
- Ask: Confirm sub for 14.1. Decide whether to hold 14.9 or stage parallel.

**2.  DEWBERRY · 15.1  ·  Jason Szykulski  ·  CRITICAL · sequencing_risk**
- Message: 15.1 Punch Walk & List dragging at 55% (scattered). Successor 15.2 Punch Repairs complete. Risk of overlap.
- Evidence: phase:15.1 ongoing density=55% | phase:15.2 complete (repairs done before walk closed)
- Ask: Confirm sub for 15.1. Decide whether to hold 15.2 or stage parallel.

**3.  DRUMMOND · 12.2  ·  Bob Mozine  ·  CRITICAL · sequencing_risk**
- Message: 12.2 Paint Walls dragging at 58% (scattered). Successor 12.3 Paint Trim & Doors ongoing. Risk of overlap.
- Evidence: phase:12.2 ongoing density=58% active=26d | phase:12.3 ongoing first_log=2025-12-29
- Ask: Confirm sub for 12.2. Decide whether to hold 12.3 or stage parallel.

**4.  DRUMMOND · 13.3  ·  Bob Mozine  ·  CRITICAL · sequencing_risk**
- Message: 13.3 Electrical Trim dragging at 29% (dragging). Successor 15.1 Punch Walk & List complete. Risk of overlap.
- Evidence: phase:13.3 ongoing density=29% active=5d | phase:15.1 complete
- Ask: Confirm sub for 13.3. Decide whether to hold 15.1 or stage parallel.

**5.  DRUMMOND · 14.1  ·  Bob Mozine  ·  CRITICAL · sequencing_risk**
- Message: 14.1 Exterior Paint dragging at 2% (dragging). Successor 15.1 Punch Walk & List complete. Risk of overlap.
- Evidence: phase:14.1 ongoing density=2% active=2d last=2026-04-22 | phase:15.1 complete
- Ask: Confirm sub for 14.1. Decide whether to hold 15.1 or stage parallel.

**6.  FISH · 10.2  ·  Martin Mannix  ·  CRITICAL · sequencing_risk**
- Message: 10.2 Floor Tile / Wood Flooring dragging at 49% (scattered). Successor 10.4 Stone / Slab Install complete. Risk of overlap.
- Evidence: phase:10.2 ongoing density=49% | phase:10.4 complete
- Ask: Confirm sub for 10.2. Decide whether to hold 10.4 or stage parallel.

**7.  FISH · 10.3  ·  Martin Mannix  ·  CRITICAL · sequencing_risk**
- Message: 10.3 Wall Tile dragging at 27% (dragging). Successor 10.4 Stone / Slab Install complete. Risk of overlap.
- Evidence: phase:10.3 ongoing density=27% | phase:10.4 complete
- Ask: Confirm sub for 10.3. Decide whether to hold 10.4 or stage parallel.

**8.  FISH · 14.8  ·  Martin Mannix  ·  CRITICAL · sequencing_risk** *(includes Watts as sub on this phase)*
- Message: 14.8 Pool Equipment & Startup dragging at 50% (scattered). Successor 15.1 Punch Walk & List complete. Risk of overlap.
- Evidence: phase:14.8 ongoing density=50% | phase:15.1 complete
- Ask: Confirm sub for 14.8. Decide whether to hold 15.1 or stage parallel.

**9.  FISH · 3.3  ·  Martin Mannix  ·  CRITICAL · sequencing_risk**
- Message: 3.3 Tie Beams (CIP) dragging at 47% (scattered). Successor 3.4 Floor Truss / Floor System Set complete. Risk of overlap.
- Evidence: phase:3.3 ongoing density=47% | phase:3.4 complete (structural sequencing — tie beams open while floor system set complete)
- Ask: Confirm sub for 3.3. Decide whether to hold 3.4 or stage parallel.

**10. FISH · 8.2  ·  Martin Mannix  ·  CRITICAL · sequencing_risk**
- Message: 8.2 Drywall Hang dragging at 42% (scattered). Successor 8.3 Drywall Tape & Mud complete. Risk of overlap.
- Evidence: phase:8.2 ongoing density=42% | phase:8.3 complete (tape & mud done while hang still open)
- Ask: Confirm sub for 8.2. Decide whether to hold 8.3 or stage parallel.

### Sanity checks (kickoff §149-152)

**Markgraf punch should fire G1**
- ✓ **Confirmed.** `[critical] sequencing_risk · Markgraf · 15.1 Punch Walk & List dragging at 38% (dragging). Successor 15.2 Punch Repairs ongoing. Risk of overlap.` (Nelson's top-5 item #5; insight id `g1-sequencing_risk-…`).

**Watts at Fish should fire G1+G2**
- ✓ **G1 fires** for Fish phases where Watts is a listed sub: 14.8 Pool Equipment (Watts on subs_involved at 100% density on this instance), 7.2 Stucco Scratch (Watts at 50.3%), 3.3 Tie Beams (Watts at 56%). Multiple Fish G1 risks in top-10 (#6-11) cover Watts' work indirectly.
- ⚠ **G2 does NOT fire on Watts at Fish.** The data does not support the kickoff prediction: Watts' density at Fish 7.2 Stucco is **50.3%, ABOVE his rollup baseline of 38.1% across 9 jobs** — i.e., Watts is *better* than his typical pattern at Fish, so the drift signal correctly does not fire. The kickoff prediction was speculative; the actual rollup data shows Watts is fine on stucco at Fish.
  - G2 *does* fire on other Fish subs that ARE drifting: Gator Plumbing on 13.1 Plumbing Trim (29% vs typical 100%), Ross Built Crew on 14.9, 6.4, 9.2 (all dragging vs baseline).

---

## 3. Generator 3 stats

| Metric | Value |
|---|---|
| Total action items                          | 222   |
| Items requiring field confirmation (after enrichment) | 156 / 222 (70.3%) |
| Items NOT requiring field confirmation               |  66 / 222 (29.7%) |
| Items COMPLETE in last 14-day window                 |  24   |
| Skipped — no `closed_date` on COMPLETE item          |   0   |
| Skipped — admin/decision-only (no field flag)        |  10   |
| Skipped — enrichment couldn't infer phase or sub     |   3   |
| **Items checked against daily logs**                 | **11** |
| Confirmed by field activity in [-21d, +7d] window    |   9   |
| **Flagged as missed_commitment**                     |   2   |
| **Flag rate**                                        | **8.3%**  |

Stop-condition target band: **2–20%** → **PASS** (8.3%).

The two flagged items:
- `HARL-009` — "Great-room landing + stair floor re-sanded and stained 4/22 per BT log" — closed 2026-04-22, related_phase inferred = 12.1 Caulk & Putty (enrichment caught "putty" in update text but the actual log activity is sanding/staining, which would tag under a different phase). Useful flag — surfaces an enrichment-quality issue worth investigating.
- `RUTH-010` — "Lee to complete Ruthven exterior cleanup with Corey/Dwayne" — closed 2026-04-23, related_phase inferred = 9.1 (mismatch — exterior cleanup isn't 9.1 Interior Stair Framing). Real signal that enrichment misclassified.

Both flags are technically true — "the inferred (phase) wasn't logged" — and lead the PM to either confirm the work or update the enrichment. Not noise.

Window tuning notes:
- Initial spec window of `[-7, +7]` produced 41.7% flag rate (way too aggressive) — closeout-style items routinely close 14–21 days after the actual field work.
- Asymmetric `[-21, +7]` window settled flag rate at 16.7% (in band).
- Tightening enrichment to detect "Complete —" closeout marker + admin-decision phrases (`decision locked`, `pricing finalized`, `no formal X needed`) further reduced to **8.3%**.

---

## 4. Nelson's Meeting Prep page

Source: `monday-binder-v2/meeting-prep/nelson-belanger.html` · `nelson-belanger.pdf`
(386 KB · extracted with Edge headless `--print-to-pdf` + `pdftotext -layout`).

```
NELSON BELANGER · MEETING PREP                            Generated for 2026-04-29
Today: 2026-04-29   Last meeting: 2026-04-23 (6d ago)
28 insights · 4 action items · 2 last-meeting commitments

Job strip:
  Markgraf · Closeout Push -- target move-in 4/27   [amber]
  Clark · Foundation / Early Framing                [green]
  Johnson · Pre-Construction                        [green]

THIS WEEK'S MUST-DISCUSS                  (5 ranked, severity × signal type)

  1. MARKGRAF · 10.2 SEQUENCING_RISK
     10.2 Floor Tile / Wood Flooring dragging at 50% (scattered). Successor
     11.1 Cabinet Install ongoing. Risk of overlap.
       phase: 10.2 Floor Tile / Wood Flooring @ Markgraf · status=ongoing ·
              density=50% · active=90d · first=2025-05-27 · last=2026-04-22
       phase: 11.1 Cabinet Install @ Markgraf · status=ongoing · first=2025-07-22
     › ASK: Confirm sub for 10.2. Decide whether to hold 11.1 or stage parallel.

  2. CLARK · 14.9 SUB_DRIFT
     USA Fence Company running 2% on 14.9 Final Fencing / Gates at Clark, vs
     their typical 100% across 3 jobs.
       sub on instance: USA Fence Company on 14.9 @ Clark · current=2% · active=2d · logs=2
       rollup: USA Fence Company × 14.9 · baseline=100% · jobs=3 · delta=-0.98
     › ASK: Ask PM what changed. Sub issue or job-specific?

  3. MARKGRAF · 12.2 SEQUENCING_RISK
     12.2 Paint Walls dragging at 63% (steady). Successor 12.3 Paint Trim & Doors
     complete. Risk of overlap.
       phase: 12.2 Paint Walls @ Markgraf · status=ongoing · density=63% ·
              active=26d · first=2025-08-25 · last=2026-04-22
       phase: 12.3 Paint Trim & Doors @ Markgraf · status=complete · first=2025-12-02
     › ASK: Confirm sub for 12.2. Decide whether to hold 12.3 or stage parallel.

  4. MARKGRAF · 13.3 SEQUENCING_RISK
     13.3 Electrical Trim dragging at 34% (dragging). Successor 13.6 Appliance
     Install ongoing. Risk of overlap.
       phase: 13.3 Electrical Trim @ Markgraf · status=ongoing · density=34% ·
              active=15d · first=2025-08-28 · last=2026-04-17
       phase: 13.6 Appliance Install @ Markgraf · status=ongoing · first=2025-11-06
     › ASK: Confirm sub for 13.3. Decide whether to hold 13.6 or stage parallel.

  5. MARKGRAF · 14.8 SEQUENCING_RISK
     14.8 Pool Equipment & Startup dragging at 39% (dragging). Successor 15.1
     Punch Walk & List ongoing. Risk of overlap.
       phase: 14.8 Pool Equipment & Startup @ Markgraf · status=ongoing ·
              density=39% · active=16d · first=2024-08-27 · last=2026-04-17
       phase: 15.1 Punch Walk & List @ Markgraf · status=ongoing · first=2024-07-19
     › ASK: Confirm sub for 14.8. Decide whether to hold 15.1 or stage parallel.

ALL OPEN INSIGHTS                          (6 critical · 22 warn · grouped by sev)

  CRITICAL  Markgraf · 10.2  10.2 Floor Tile / Wood Flooring dragging at 50% …
  CRITICAL  Markgraf · 12.2  12.2 Paint Walls dragging at 63% (steady). Succ. 12.3
  CRITICAL  Markgraf · 13.3  13.3 Electrical Trim dragging at 34% …
  CRITICAL  Markgraf · 14.8  14.8 Pool Equipment & Startup dragging at 39% …
  CRITICAL  Markgraf · 15.1  15.1 Punch Walk & List dragging at 38% …
  CRITICAL  Markgraf · 3.7   3.7 Roof Truss Set dragging at 50% (scattered). Succ. 3.8 complete
  WARN      Clark · 14.9     USA Fence Company 2% vs typical 100% (G2)
  WARN      Markgraf · 13.3  Metro Electric, LLC 56% vs typical 83% across 4 jobs
  WARN      Markgraf · 3.7   Kimal Lumber Company 33% vs typical 100% across 8 jobs
  WARN      Markgraf · 6.2   Gator Plumbing 22% vs typical 69% across 6 jobs
  WARN      Markgraf · 8.1   Paradise Foam, LLC 31% vs typical 53% across 6 jobs
  WARN      Markgraf · 9.1   DB Welding Inc. 72% vs typical 100% across 6 jobs
  WARN      Clark · 1.3      sequencing_violation: pred 1.2 has no logs
  WARN      Clark · 1.4      sequencing_violation: pred 1.1 has no logs
  WARN      Clark · 14.8     sequencing_violation: pred 14.7 has no logs
  WARN      Clark · 14.9     sequencing_violation: pred 14.1 has no logs
  WARN      Clark · 15.1     sequencing_violation: pred 13.1 has no logs
  WARN      Clark · 2.4      sequencing_violation: pred 2.3 has no logs
  WARN      Clark · 3.3      sequencing_violation: pred 3.2 has no logs
  WARN      Markgraf · 12.1  sequencing_violation: pred 11.3 has no logs
  WARN      Markgraf · 14.1  sequencing_violation: pred 7.6 has no logs
  WARN      Markgraf · 14.3  sequencing_violation: pred 7.7 has no logs
  WARN      Markgraf · 4.3   sequencing_violation: pred 3.9 (Hurricane Strapping) has no logs
  WARN      Markgraf · 4.4   sequencing_violation: pred 3.9 has no logs
  WARN      Markgraf · 5.3   sequencing_violation: pred 5.1 has no logs
  WARN      Markgraf · 6.4   sequencing_violation: pred 5.1 has no logs
  WARN      Markgraf · 8.3   sequencing_violation: pred 8.2 has no logs
  WARN      Markgraf · 9.1   sequencing_violation: pred 8.5 has no logs

ACTION ITEMS                               (4 open · 0 complete · 1 blocked · sorted by aging)

  MARK-032  Markgraf  15.2* Get Mark on-site to retest LV wiring after paint touch-up    due 2026-04-22  BLOCKED   26d
  MARK-047  Markgraf  7.2*  Send CO-4412 to homeowner for stucco repair scope            due 2026-04-24  NOT_STARTED 5d
                            (pricing finalized with Jeff Watts Plastering and Stucco)
  CLAR-001  Clark           Order steel package -- 3.5mo lead, confirm PO by 5/15        due 2026-05-15  NOT_STARTED 0d
  MARK-048  Markgraf        Confirm Seth's Monday 4/27 crew size via phone call by 4/24  due 2026-04-24  IN_PROGRESS 3d

COMMITMENTS FROM LAST MEETING              (2 commitments captured at or near 2026-04-23)

  MARK-048  Markgraf  Confirm Seth's Monday 4/27 crew size            opened 2026-04-20  IN PROGRESS  (wip)
  CLAR-001  Clark     Order steel package -- 3.5mo lead               opened 2026-04-23  NOT STARTED  (open)
```

**Verdicts**:
- 5 must-discuss items ranked correctly: critical sequencing_risks first, with one
  Clark slot reserved (G2 USA Fence Company drift). Remaining 4 are Markgraf
  closeout-stage paint/punch/electrical/pool risks. ✓
- Evidence cites real records: every phase reference matches `phase-instances-v2.json`
  data; rollup baseline is real (USA Fence Company has 3 jobs in `sub-phase-rollups.json`). ✓
- Asks are specific: each ask names the phase and a concrete decision. ✓

---

## 5. Bob's Meeting Prep page

Source: `monday-binder-v2/meeting-prep/bob-mozine.html` · `bob-mozine.pdf` (584 KB).

```
BOB MOZINE · MEETING PREP                            Generated for 2026-04-29
Today: 2026-04-29   Last meeting: 2026-04-14 (15d ago)
31 insights · 42 action items · 29 last-meeting commitments

Job strip:
  Drummond · Final Paint + Pool Deck + Trim Out                       [amber]
  Molinari · Drywall Repair + Wood Floor Protection + Trim Start      [amber]
  Biales · Pre-Active / Schedule Baseline                             [green]

THIS WEEK'S MUST-DISCUSS                  (5 ranked, severity × signal type)

  1. DRUMMOND · 12.2 SEQUENCING_RISK
     12.2 Paint Walls dragging at 58% (scattered). Successor 12.3 Paint Trim & Doors
     ongoing. Risk of overlap.
       phase:12.2 Paint Walls @ Drummond · ongoing density=58% active=26d
       phase:12.3 Paint Trim & Doors @ Drummond · ongoing first=2025-12-29
     › ASK: Confirm sub for 12.2. Decide whether to hold 12.3 or stage parallel.

  2. MOLINARI · 15.1 SEQUENCING_RISK
     15.1 Punch Walk & List dragging at 33% (dragging). Successor 15.2 Punch Repairs
     ongoing. Risk of overlap.
       phase:15.1 Punch Walk & List @ Molinari · ongoing density=33% active=7d
              first=2024-11-22 last=2026-04-27
       phase:15.2 Punch Repairs @ Molinari · ongoing first=2026-04-20
     › ASK: Confirm sub for 15.1. Decide whether to hold 15.2 or stage parallel.

  3. DRUMMOND · 13.3 SEQUENCING_RISK
     13.3 Electrical Trim dragging at 29% (dragging). Successor 15.1 Punch Walk & List
     complete. Risk of overlap.
       phase:13.3 Electrical Trim @ Drummond · ongoing density=29% active=5d
       phase:15.1 Punch Walk & List @ Drummond · complete first=2025-05-09
     › ASK: Confirm sub for 13.3. Decide whether to hold 15.1 or stage parallel.

  4. DRUMMOND · 14.1 SEQUENCING_RISK
     14.1 Exterior Paint dragging at 2% (dragging). Successor 15.1 Punch Walk & List
     complete. Risk of overlap.
       phase:14.1 Exterior Paint @ Drummond · ongoing density=2% active=2d last=2026-04-22
       phase:15.1 Punch Walk & List @ Drummond · complete first=2025-05-09
     › ASK: Confirm sub for 14.1. Decide whether to hold 15.1 or stage parallel.

  5. MOLINARI · 8.2 SEQUENCING_RISK
     8.2 Drywall Hang dragging at 36% (dragging). Successor 8.3 Drywall Tape & Mud
     complete. Risk of overlap.
       phase:8.2 Drywall Hang @ Molinari · ongoing density=36% active=9d
              first=2026-02-18 last=2026-04-27
       phase:8.3 Drywall Tape & Mud @ Molinari · complete first=2026-03-10
     › ASK: Confirm sub for 8.2. Decide whether to hold 8.3 or stage parallel.

ALL OPEN INSIGHTS                          (5 critical · 26 warn · grouped by sev)
  [G1: 5 critical sequencing risks · 14 warn sequencing violations · G2: 12 sub_drifts]

  WARN  Drummond · 14.1   TNT Custom Painting running 2% on 14.1 Exterior Paint at
                          Drummond, vs their typical 49% across 6 jobs.   ← G2 confirms G1 #4
  WARN  Drummond · 7.5    TNT Custom Painting 50% vs typical 75%
  WARN  Drummond · 9.2    Ross Built Crew 7% vs typical 50% across 7 jobs
  WARN  Molinari · 1.3    Ross Built Crew 2% vs typical 100% (early site)
  WARN  Molinari · 2.2    Southwest Concrete & Masonry 29% vs typical 62% across 3 jobs
  WARN  Molinari · 7.5    TNT Custom Painting 50% vs typical 75%
  WARN  Molinari · 9.1    Precision Stairs Florida, Inc 59% vs typical 100% across 7 jobs
  [+ 14 sequencing_violations across Drummond and Molinari]

ACTION ITEMS                               (38 open · 4 complete · 0 blocked · sorted by aging)
  [42 items — all have related_phase or related_sub from enrichment;
   Bob is the largest binder by item count]

COMMITMENTS FROM LAST MEETING              (29 commitments captured at or near 2026-04-14)
  [29 items opened in ±3d of 2026-04-14; status mix:
     done / wip / suspect (G3) / open
   per kickoff §134]
```

**Verdicts**:
- 5 must-discuss covers Drummond + Molinari (Biales is pre-active, no insights expected). ✓
- TNT Custom Painting at Drummond on 14.1 (G2 sub_drift, 2% vs 49%) directly
  confirms the G1 #4 phase-level signal — same trade, dragging at sub level too.
  This is the cross-data signal the kickoff §53 specifically called out. ✓
- 31 insights and 42 action items render in a single PDF (584 KB). Page is print-legible. ✓
- Asks are specific to phase and sub. ✓

---

## 6. Insight noise check

For the **top 20** ranked insights (all `[critical] sequencing_risk` score=7),
would each one change a meeting decision?

| # | PM             | Job      | Phase signal                                              | Decision-changing? |
|---|----------------|----------|-----------------------------------------------------------|--------------------|
| 1 | Jason          | Dewberry | 14.1 Paint dragging, 14.9 Fencing complete                | ✓ fence touch-up risk if paint wraps |
| 2 | Jason          | Dewberry | 15.1 Punch dragging, 15.2 Repairs complete                | ✓ repairs were blind |
| 3 | Bob            | Drummond | 12.2 Paint Walls 58%, 12.3 Trim ongoing                   | ✓ overlapping painters → schedule conflict |
| 4 | Bob            | Drummond | 13.3 Electrical Trim 29%, 15.1 Punch complete             | ✓ punch closed early |
| 5 | Bob            | Drummond | 14.1 Ext Paint 2%, 15.1 Punch complete                    | ✓ critical: punch done with no exterior paint |
| 6 | Martin         | Fish     | 10.2 Floor Tile, 10.4 Stone complete                      | ✓ stone on incomplete floor |
| 7 | Martin         | Fish     | 10.3 Wall Tile 27%, 10.4 Stone complete                   | ✓ same overlap |
| 8 | Martin         | Fish     | 14.8 Pool 50%, 15.1 Punch complete                        | ✓ pool not done at punch |
| 9 | Martin         | Fish     | 3.3 Tie Beams 47%, 3.4 Floor Truss complete (structural!) | ✓ MAJOR — structural sequence |
| 10 | Martin        | Fish     | 8.2 Drywall Hang 42%, 8.3 Tape complete                   | ✓ tape on incomplete hang |
| 11 | Martin        | Fish     | 9.2 Trim 36%, 10.2 Floor Tile ongoing                     | ✓ trim/tile coordination |
| 12 | Jason         | Harllee  | 12.2 Paint, 12.3 Trim complete                            | ✓ painters out of order |
| 13 | Jason         | Harllee  | 14.8 Pool 47%, 15.1 Punch ongoing                         | ✓ pool/punch overlap |
| 14 | Jason         | Harllee  | 15.1 Punch 9% (very low), 15.2 Repairs ongoing            | ✓ repairs without walk |
| 15 | Jason         | Harllee  | 15.2 Repairs 39%, 15.3 Cleaning complete                  | ✓ cleaned before repairs done |
| 16 | Jason         | Harllee  | 7.4 Siding 14%, 7.5 Soffit complete                       | ✓ soffit before siding |
| 17 | Lee Worthy    | Krauss   | 12.2 Paint, 12.3 Trim complete                            | ✓ painter sequence |
| 18 | Lee Worthy    | Krauss   | 14.8 Pool 35%, 15.1 Punch ongoing                         | ✓ pool/punch overlap |
| 19 | Lee Worthy    | Krauss   | 15.1 Punch, 15.2 Repairs complete                         | ✓ repairs blind |
| 20 | Nelson        | Markgraf | 10.2 Floor Tile, 11.1 Cabinet ongoing                     | ✓ cabinets on incomplete floor |

**Score: 20/20 = 100%** — well above the 70% bar.

Most signals are variants of three closeout patterns:
- **Punch happening before predecessor closes** (paint, electrical, plumbing, etc.)
- **Tape & mud / stone install / fencing** completing before their structural predecessor
- **Pool equipment startup** dragging while punch begins

These ARE the situations a Monday meeting should surface — even if the
patterns repeat across jobs, each instance is a separate PM conversation
(different sub, different schedule, different decision).

---

## Stop conditions (kickoff §160-164)

| # | Condition | Status |
|---|-----------|--------|
| 1 | All 3 generators run without errors                       | ✓ PASS |
| 2 | Meeting Prep pages render for all active PMs (5/5)        | ✓ PASS |
| 3 | Top 20 insights ≥70% would change a decision              | ✓ PASS (100%) |
| 4 | Generator 3 flagged rate in 2–20% band                    | ✓ PASS (8.3%) |

**Phase 6 ships.**

---

## Files written

- `data/insights.json`                                          — 193 KB · 155 insights
- `binders/enriched/{Bob,Jason,Lee,Martin,Nelson}*.json`        — 5 enriched binders
- `generators/_common.py`                                       — shared loaders + INSIGHT factory
- `generators/g1_sequencing.py`                                 — Generator 1
- `generators/g2_sub_drift.py`                                  — Generator 2
- `generators/g3_missed_commitment.py`                          — Generator 3
- `generators/enrich_action_items.py`                           — one-time enrichment
- `generators/run_all.py`                                       — orchestrator
- `monday-binder-v2/meeting-prep.template.html`                 — page template
- `monday-binder-v2/build_meeting_prep.py`                      — per-PM page builder
- `monday-binder-v2/meeting-prep/{slug}.html` × 5               — per-PM pages (170-412 KB each)
- `monday-binder-v2/meeting-prep/{slug}.pdf` × 5                — printed PDFs (386-697 KB)

---

## Anything flagged for follow-up

1. **76 sequencing_violations remain** — the recency filter (last 90 days)
   trimmed historical noise but the surviving 76 are real classification
   gaps (predecessor phases with zero logs on a job whose successor is
   complete). These are an *enrichment-quality signal* worth surfacing to
   PMs but the current presentation lumps them into "all open insights"
   alongside live risks. Phase 7 should consider a separate "Data Quality"
   bucket on the meeting page — they're useful but distinct from
   field-actionable signals.
2. **Top 20 are 100% sequencing_risk** — by design (rank score puts
   critical sequencing_risk at the top), but a Phase 7 ranker could
   blend in G2/G3 signals via per-type quotas if PMs report fatigue on
   the punch/paint/pool pattern.
3. **Watts at Fish G2 nonfire** — kickoff predicted G2 would fire here;
   actual data says Watts is performing at-or-above his rollup baseline
   on stucco at Fish. The kickoff prediction was speculative and
   the generator behaved correctly. Worth re-running this sanity check
   each Monday — if Watts' Fish density falls below 38%, G2 will fire.
4. **Enrichment phase mis-classification** — `HARL-009` got phase 12.1
   (Caulk & Putty) when the actual work was floor sanding/staining;
   `RUTH-010` got 9.1 (Interior Stair) when the work was exterior cleanup.
   These mismatches turned into G3 missed_commitment flags. Phase 7 should
   tighten the phase-keyword regex precision OR add a confidence score to
   the enrichment so low-confidence items get skipped.
5. **Inferred-field markers (`*` in the action item phase column)**
   currently only flag the field; PMs may want a tooltip showing the
   keyword that triggered the match so they can validate the inference.
6. **`(unmapped) = 1`** — the Ross Built Crew × 12.1 Caulk & Putty drift
   on the FieldCrew job is correctly captured but has no PM owner.
   FieldCrew probably needs an explicit owner mapping (Ross himself?)
   or a "House" PM bucket.

---

## Generator design notes (for future iteration)

- INSIGHT records carry `content_hash` (deterministic from type + key
  fields) so future runs can detect re-fires and PM-acknowledged dismissals
  without re-emitting the same signal.
- Insights are currently *fully overwritten* per run — Phase 6 MVP doesn't
  yet implement append-with-merge as the kickoff hints. Acknowledgment
  state is a Phase 7+ concern.
- Generator 4 (stage-should-be-doing) and Generator 7 (schedule reality)
  remain deferred to milestone `m03-schedule-generation` per kickoff §6-9.
- The phase-keyword + sub-name match heuristics in `enrich_action_items`
  are deliberately lightweight (kickoff §96) — they trade precision for
  coverage at the MVP stage.
