"""Monday weekly batch: validate data + persist commitment-tracker snapshot.

Phase 11 cutover: meeting-prep pages are NO LONGER pre-rendered to HTML or
PDF. The dashboard at http://localhost:8765 serves /meeting-prep/* live —
each request reads fresh data and renders on demand. PDFs are produced
on-demand at click time via the same dashboard server.

Why this script still exists: run_weekly.bat invokes it on Monday morning
to (1) confirm all input data files load cleanly and (2) persist this
week's must-discuss snapshot via commitment_tracker.update(). That snapshot
is the basis for next week's accountability diff in validate_accountability.py.

This script never writes any HTML or PDF files. The dashboard does that
on click.
"""
from __future__ import annotations

import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parents[1]
_MONDAY_BINDER = _THIS.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_MONDAY_BINDER) not in sys.path:
    sys.path.insert(0, str(_MONDAY_BINDER))

from render_helpers import (
    compute_top_5_by_pm,
    compute_tracking,
    load_context,
)


def main() -> int:
    print("[build_meeting_prep] loading context...")
    ctx = load_context()
    print(f"[build_meeting_prep] today={ctx.today}  insights={len(ctx.all_insights)}  "
          f"PMs={len(ctx.pm_to_jobs)}")

    print("[build_meeting_prep] computing top-5 must-discuss per PM...")
    top_5 = compute_top_5_by_pm(ctx)

    print("[build_meeting_prep] persisting commitment-tracker snapshot...")
    tracking = compute_tracking(ctx, top_5, persist=True)

    print(f"[build_meeting_prep] this_week={tracking.get('this_week')}  "
          f"last_week={tracking.get('last_week')}")
    for pm, info in tracking.get("by_pm", {}).items():
        print(f"  {pm:<18} this_week={info['this_week_count']:>2} "
              f"last_week={info['last_week_count']:>2} "
              f"resolved={info['resolved_count']:>2} "
              f"carried={info['carried_count']:>2} "
              f"stuck={info['stuck_count']:>2}")

    print("[build_meeting_prep] OK -- snapshot persisted. "
          "Pages render live from /meeting-prep/* on the dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
