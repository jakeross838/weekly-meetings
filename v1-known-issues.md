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
