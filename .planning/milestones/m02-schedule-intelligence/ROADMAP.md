# m02 — Schedule Intelligence · Roadmap

## Vision
Fuse the four data silos (daily logs, meeting transcripts, action items, job data) into a single intelligence layer that builds accurate schedules, runs PM meetings predictively, and gets smarter every week. This is the unified intelligence layer — binders, meeting prep, and downstream schedule generation are all consumers, not the product itself.

## Source documents
- [SPEC.md](./SPEC.md) — full rebuild prompt (PARTS 1-11)
- [KICKOFF.md](./KICKOFF.md) — Jake's decisions, generator sequencing correction, standing rules

## Standing rules (also in [PROJECT.md](../../PROJECT.md))
- Output goes to `monday-binder-v2.html` alongside the running v1 system
- v1 stays live until Phase 10 cutover
- Recalculate, don't increment
- Org-configurable, not hardcoded
- Don't kill running processes (use a different port if needed)
- Backward-compatible action-item JSON schema (additive only)
- Print-legible status labels (text + icon, not icon-only)
- Every insight cites evidence

## Phase breakdown

| # | Phase | Review checkpoint | Deliverables |
|---|---|---|---|
| 0 | Visual mockups (30-min cap) | YES | `mockups/phase-card.html` (Plumbing Top-Out), `mockups/meeting-prep.html` (Nelson 4/29) |
| 1 | Sub reclassification | YES | Per-sub retag groupings (top-5 by volume, sample text), filter list, keyword library, `requires_manual_review` count |
| 2 | 15-stage build sequence + classifier | — | Phase taxonomy, two-pass classifier integrated, low_confidence + manual-review tables |
| 3 | Duration math (burst + density) | YES | Burst sanity check on Stucco/Drywall/Tile/Pool/Framing/Siding/Trim/Roofing — old span vs new active vs density vs burst count |
| 4 | Phase Library view | — | Plumbing Top-Out card + Stucco card live |
| 5 | Job page rebuild | YES | Markgraf full read-down, Active-phases-today strip |
| 6 | Generators 1/2/4 + MVP Meeting Prep | YES | 10 sample insights of varied types + Nelson MVP Meeting Prep |
| 7 | Schedule Builder | — | First 20 rows with predecessors verified |
| 8 | Meeting Prep refinement + generator tune | YES | Nelson's full page tuned against actual data; "noise %" measured |
| 9 | Generators 3/5/6/7 | — | Each generator wired into Meeting Prep one at a time |
| 10 | Cutover | — | `monday-binder-v2.html` live, v1 retired, smoke tests |

## Per-phase deliverable contract
Every phase ends with:
1. `PLAN.md` — what was built vs planned
2. `VERIFICATION.md` — QA outputs from spec
3. The actual artifact (HTML page, JSON file, CSV export)
4. A short summary in chat for review

Don't say "done." Paste verification artifacts into chat before moving on.

## Generator sequencing rationale (KICKOFF correction)
Original plan had Gens 1/2/4 ship before Meeting Prep. That was backwards — Meeting Prep is the *consumer* that judges whether insights are useful. Revised to ship them together (Phase 6), then refine in Phase 8, then add the rest in Phase 9 one at a time, each judged by "does this change a meeting decision."
