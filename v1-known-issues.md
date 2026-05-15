# v1 Known Issues

Issues found in v1 (Python pipeline + production-cockpit) during v2 work.
Per the v1 freeze, items in this file are NOT fixed; they're parked for
later review.

## Pay app parser: unnumbered overflow items
- Some pay apps have late-added scope items in the G703 with no line
  number (e.g. Krauss row 218 "Well abandonment", row 219
  "Trellis-Pergola over garage").
- These are currently skipped during parse.
- To investigate later: should we (a) auto-assign synthetic line
  numbers, (b) parse the PCCO Change Order Log sheet to capture them,
  or (c) leave as-is?
- Found during Gate 1B (2026-05-15).

## Retry orchestrator improvement
- Auditor should pre-write specific corrections (e.g. "change KRAU-050
  priority to normal") rather than describing issues abstractly.
- Reconciler prompt should treat prior-issue hints as hard constraints
  rather than soft hints.
- When to address: after Gate 2A surface lands and we see how often
  retries fire in normal operation.
- Found during Gate 1F (2026-05-15).

## Subs catalog disambiguation needed
- "Terry" resolved to TNT Custom Painting when speaker meant Terry
  Sprague (a different mechanical sub).
- "Jeff Watts" matched to plastering scope on a Dewberry electrical
  item.
- These are real-world ambiguity that needs human-curated alias updates
  to the subs table.
- When to address: one-shot data-quality task, schedule after Gate 2C.
- Found during Gate 1F (2026-05-15).

## Mechanical audit refinement
- The claim-accountability heuristic (output count <70% of input claims)
  is too noisy.
- Replace with exact tracking via source_claim_id column on items.
- When to address: small follow-up migration, schedule between Gate 2
  and Gate 3.
- Found during Gate 1F (2026-05-15).
