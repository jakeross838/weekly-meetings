# Phase 0 — Visual mockups · VERIFICATION

## Deliverables produced
- [`mockups/phase-card.html`](./mockups/phase-card.html) — Plumbing Top-Out Phase Library card per [SPEC PART 6](../../SPEC.md)
- [`mockups/meeting-prep.html`](./mockups/meeting-prep.html) — Nelson Belanger Monday 2026-04-29 Meeting Prep page per [SPEC PART 9](../../SPEC.md)

## What was built

### `phase-card.html` — single tile
- Phase code + name header (`6.1` mono · "Plumbing Top-Out" display) with build-stage chip and historical job count
- 4-stat row: Typical Active · Typical Density · Typical Span · Active Now
- Density bar with tier breakpoints labeled (40 / 60 / 80) and colored fill
- Typical Subs table — Sub · Active · Density (dot + % + tier label) · Reliability · Jobs
- Sequence chips — Preceded By / Followed By with phase-code badges
- Insights block — warn-orange tinted card with bullet + mono evidence line
- Per-job detail teaser at bottom (collapsed)
- Standing-rule check: density indicators carry text labels ("Continuous"), not emoji-only ✓

### `meeting-prep.html` — full Nelson page
- Header: dark slate band with eyebrow / display name / meeting date / job list / last-meeting age
- 5 sections, each with a "Section NN" eyebrow:
  1. **This week's must-discuss** — 5 ranked items (3 warn / 2 info), each with severity chip · job tag · title · evidence (mono) · ask (italic with smart-quotes)
  2. **Open action items · Nelson** — 4 aging buckets (Abandoned · Stale · Aging · Fresh-collapsed), each row id · text · age · priority chip
  3. **Look-ahead · next 14 days** — 2 job cards with phase rows + risk card under affected phase
  4. **Commitments from last meeting · closure check** — done · suspect · wip with status chips and follow-up ask
  5. **Client signals** — owner sentiment + mention frequency
- Standing-rule check: every insight cites at least one log/transcript/phase reference ✓
- Standing-rule check: severity chips carry text labels ("Warn" / "Info"), not color-only ✓

## Sample data choices
All numbers, IDs, and dates are illustrative. Choices made:
- Phase card uses Plumbing Top-Out (6.1) with Gator + Loftin as the two-sub example per spec
- Meeting prep uses Nelson Belanger / 2026-04-29 / Markgraf + Clark as the two-job example
- Action item IDs (`CL-002`, `MK-014`, `MK-018`, `CL-008` …) — rough format only; real binder IDs vary
- All sub names are real (Gator, Loftin, TNT, Capstone, Smarthouse, DB Welding, CoatRite, ML Concrete) per the canonical list in `feedback_sub_names.md`

## What's deliberately NOT in the mockups
- No data wiring — these are pure HTML
- No interactivity beyond CSS hover affordances
- No PDF print stylesheet — we'll port v1's `@media print` rules in Phase 4
- No sidebar / nav / view-toggle — single page each, screen-only

## Open questions for review (also in the mockup notes)
1. **Density flag rendering** — color dot + numeric % + tier text label ("Continuous"). Does this read print-legible to you?
2. **Insight evidence treatment** — mono line with `phase:`, `transcript:`, `action:`, `log:` prefixes. Citable enough?
3. **Must-discuss density** — three blocks per item (Title · Evidence · Ask). Tight enough to scan in 60 sec?
4. **Severity treatment** — left border + chip. Different palette than v1's existing aging colors. Confirm direction.
5. **Look-ahead risk lines** — orange-tinted card under the affected phase, OR should risks live up in must-discuss instead? Currently they appear in both (must-discuss item #1 + look-ahead Markgraf risk line).
6. **Commitments "Suspect" treatment** — when binder says DONE but no log confirms, render as warn ⚠ with explicit "verify in field" ask. Confirm we want this discipline.

## Time spent
~25 minutes (under 30-min cap). No real logic crept in.

## Next step
Wait for Jake's review. Phase 1 begins once direction is confirmed (or redirected).
