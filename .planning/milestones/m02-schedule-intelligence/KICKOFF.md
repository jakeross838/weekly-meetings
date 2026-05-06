# Monday Binder Rebuild — Decisions & Kickoff

## My answers to your questions

**Q1 — Phase 1 first, but with a 30-min visual sketch upfront.**

Before you touch the data, render two static HTML mockups (no live data, just hard-coded sample content) so I can gut-check the visual direction:

1. One Phase Library card — use Plumbing Top-Out as the example with the structure from PART 6 of the spec
2. One Meeting Prep page — use a fictional "Nelson Belanger / Monday 2026-04-29" example with sample insights and asks

Save these as `mockups/phase-card.html` and `mockups/meeting-prep.html`. Do not wire them to data. They're sketches. I'll review the layout and either approve or redirect before you start Phase 1. **30 minutes of effort, hard cap.** If you find yourself building real logic, stop — that's not what this is.

After I approve the mockups, proceed to Phase 1.

**Q2 — Yes, bootstrap GSD planning.**

Run `/gsd-new-milestone` to create the milestone. Each of the 10 phases gets its own subdirectory with PLAN.md, RESEARCH.md, and VERIFICATION.md. Every QA artifact persists to disk. I want the reclassification diff and keyword library readable six months from now without digging through chat.

**Diff format for Phase 1:**

Group by sub, show top 5 retags per sub by log volume. CSV is too dense to spot a CoatRite-style error. I'd rather skim 50 readable groupings than scroll a 500-row spreadsheet.

Format per sub:

```
SUB: CoatRite LLC
  Logs total: 47   Old categories: Concrete (Masonry Walls 1L), Foundation
  Top retags (by volume):
    14 logs  →  2.4 Stem Wall Waterproofing
                Sample: "Waterproofed stem wall, applied membrane on Drummond..."
    11 logs  →  10.1 Wet Area Waterproofing
                Sample: "Hydroban applied master shower pan, second coat..."
     8 logs  →  2.4 Stem Wall Waterproofing
                Sample: "Below-grade waterproofing, foundation walls..."
     ... etc

  Logs unclassified after Pass 2: 3   (in requires_manual_review)
```

After the per-sub groupings, append a summary table: total logs, total retagged, % to manual review, top 10 phase tags by volume after reclassification.

## Generator sequencing — correction to the plan

Your phase order had Insight Engine Gens 1/2/4 (Phase 6) ship before Meeting Prep (Phase 8). That's backwards. Meeting Prep is the consumer that judges whether insights are useful. If generators ship in isolation, half of them produce noise no one would discuss in a meeting, and you tune them blind.

Revised order for Phases 6–9:

- **Phase 6** — Build Generators 1, 2, 4 PLUS a minimum-viable Meeting Prep page that consumes them. Both ship together.
- **Phase 7** — Schedule Builder (unchanged)
- **Phase 8** — Refine Meeting Prep against Nelson's actual data. Tune Generators 1/2/4 based on what changes a meeting decision and what doesn't. Same time budget as before.
- **Phase 9** — Add Generators 3, 5, 6, 7 one at a time, each wired into Meeting Prep as it's built. Judge each one by "does this change a meeting decision" before adding the next.

## Execution plan — the 10 phases

```
PHASE 0  Visual mockups (30 min cap)              ← new, do this first
PHASE 1  Sub reclassification                     ← review checkpoint
PHASE 2  15-stage build sequence + classifier
PHASE 3  Duration math (burst + density)          ← review checkpoint
PHASE 4  Phase Library view
PHASE 5  Job page rebuild                         ← review checkpoint
PHASE 6  Generators 1/2/4 + MVP Meeting Prep      ← review checkpoint
PHASE 7  Schedule Builder
PHASE 8  Meeting Prep refinement + generator tune ← review checkpoint
PHASE 9  Generators 3/5/6/7
PHASE 10 Cutover
```

Review checkpoints are where you stop and wait for me. Don't roll past them.

## Standing rules for the whole rebuild

- **Output goes to `monday-binder-v2.html`** alongside the current binder. Do not modify the running v1 system. v1 stays live until I greenlight cutover at Phase 10.
- **Recalculate, don't increment.** Every phase rebuild reads from source data and recomputes. No incremental state.
- **Org-configurable, not hardcoded.** Phase keywords, density thresholds, burst gap days, aging windows — all read from a config file, not baked in.
- **Do not kill running processes.** If a port is in use, use a different port.
- **Backward compatibility:** old action-item JSON binders must still load. Schema migrations are additive.
- **Print-legibility:** every status indicator has a text label, not emoji-only. Density flags read as `🟢 Continuous` not just `🟢`.
- **Cite evidence on every insight.** A talking-point with no underlying log/transcript/phase reference is unacceptable output.

## Per-phase deliverables (what I expect to see)

Every phase ends with:

1. PLAN.md updated with what was actually built vs what was planned
2. VERIFICATION.md with the QA outputs from the spec
3. The actual artifact (HTML page, JSON file, CSV export, whatever the phase produces)
4. A short summary in chat: what changed, what surprised you, what you flagged for review

Don't say "done." Paste the verification artifacts into chat for me to look at before moving to the next phase.

## Start here

1. Run `/gsd-new-milestone` and create the milestone structure for all 10 phases
2. Build the two Phase 0 mockups (Plumbing Top-Out card + Nelson Meeting Prep page) as static HTML
3. Stop. Paste both into chat. Wait for my green light before Phase 1.

Begin.
