"""Week-over-week meeting-commitment tracker.

Captures per-PM must-discuss snapshots into `data/meeting-commitments.json`
and computes resolution status of last week's commitments by matching
content_hash against the current insight set.

Schema (`data/meeting-commitments.json`):

```
{
  "version": 1,
  "weeks": [
    {
      "iso_week": "2026-W18",
      "today": "2026-04-29",
      "generated_at": "2026-04-30T...",
      "by_pm": {
        "Nelson Belanger": {
          "must_discuss": [
            { insight_id, content_hash, type, severity, title, summary_line, ask, related_job }
          ]
        }
      }
    }
  ]
}
```

The latest entry in `weeks[]` is "this week". The previous entry is
"last week". Resolution status is computed by:
  - last week content_hash exists in current insights → "carried"
  - last week content_hash absent from current insights → "resolved"
  - if same content_hash present in last 3 consecutive weeks → "stuck"

Same ISO week reruns UPDATE the entry rather than appending a new one,
so multiple Monday runs in a single week don't pollute the history.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
COMMITMENTS_FILE = DATA / "meeting-commitments.json"

STUCK_THRESHOLD_WEEKS = 3


def _iso_week(d: date) -> str:
    iy, iw, _ = d.isocalendar()
    return f"{iy}-W{iw:02d}"


def load_commitments() -> dict:
    if not COMMITMENTS_FILE.exists():
        return {"version": 1, "weeks": []}
    try:
        return json.loads(COMMITMENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "weeks": []}


def _snapshot_insight(ins: dict, title: str | None = None) -> dict:
    return {
        "insight_id": ins.get("id"),
        "content_hash": ins.get("content_hash"),
        "type": ins.get("type"),
        "severity": ins.get("severity"),
        "title": title or ins.get("message", "")[:80],
        "summary_line": ins.get("summary_line"),
        "ask": ins.get("ask"),
        "related_job": ins.get("related_job"),
        "related_phase": ins.get("related_phase"),
        "related_sub": ins.get("related_sub"),
    }


def update(
    today_iso: str,
    top_5_by_pm: dict[str, list[dict]],
    titles_by_id: dict[str, str] | None = None,
    persist: bool = True,
) -> dict:
    """Append (or update) this week's snapshot, return tracking info.

    persist=False computes tracking against last week's persisted snapshot
    without writing — used by live HTML render routes that must not mutate
    the weekly accountability ledger on every page view.

    Returns:
      {
        "this_week": "2026-W18",
        "by_pm": {
          "Nelson Belanger": {
             "this_week_count": 5,
             "last_week": [
               { ...commitment, current_status: "resolved|carried|stuck" }
             ],
             "resolved_count": 3,
             "carried_count": 2,
             "stuck_items": [ ... ],
           }
        }
      }
    """
    titles_by_id = titles_by_id or {}
    today_d = datetime.strptime(today_iso, "%Y-%m-%d").date()
    iso_week = _iso_week(today_d)
    state = load_commitments()
    weeks = state.setdefault("weeks", [])

    # Build current week entry (snapshot).
    current_entry = {
        "iso_week": iso_week,
        "today": today_iso,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by_pm": {},
    }
    for pm, ins_list in top_5_by_pm.items():
        current_entry["by_pm"][pm] = {
            "must_discuss": [
                _snapshot_insight(ins, titles_by_id.get(ins.get("id")))
                for ins in ins_list
            ]
        }

    # Update or append.
    if weeks and weeks[-1].get("iso_week") == iso_week:
        weeks[-1] = current_entry
    else:
        weeks.append(current_entry)

    # Compute current-week resolution info using prior weeks.
    history = weeks[:-1]  # everything before current
    last_week = history[-1] if history else None

    # Set of content_hashes present in this run, by PM
    current_hashes_by_pm: dict[str, set[str]] = {}
    for pm, ins_list in top_5_by_pm.items():
        current_hashes_by_pm[pm] = {
            ins.get("content_hash") for ins in ins_list if ins.get("content_hash")
        }

    tracking: dict = {
        "this_week": iso_week,
        "last_week": last_week.get("iso_week") if last_week else None,
        "by_pm": {},
    }

    # Populate per-PM accountability
    for pm in sorted(set(top_5_by_pm.keys()) | set(((last_week or {}).get("by_pm") or {}).keys())):
        last_md = (((last_week or {}).get("by_pm") or {}).get(pm) or {}).get("must_discuss") or []
        cur_hashes = current_hashes_by_pm.get(pm, set())

        # Compute count of consecutive weeks each hash has appeared.
        def consecutive_streak(content_hash: str) -> int:
            n = 0
            for w in reversed(weeks):  # includes this week as week 1 of streak
                w_md = ((w.get("by_pm") or {}).get(pm) or {}).get("must_discuss") or []
                hashes = {m.get("content_hash") for m in w_md}
                if content_hash in hashes:
                    n += 1
                else:
                    break
            return n

        last_with_status = []
        resolved = carried = stuck_count = 0
        stuck_items: list[dict] = []
        for it in last_md:
            ch = it.get("content_hash")
            if ch and ch in cur_hashes:
                streak = consecutive_streak(ch)
                if streak >= STUCK_THRESHOLD_WEEKS:
                    status = "stuck"
                    stuck_count += 1
                    stuck_items.append({**it, "current_status": "stuck", "streak_weeks": streak})
                else:
                    status = "carried"
                    carried += 1
            else:
                status = "resolved"
                resolved += 1
            last_with_status.append({**it, "current_status": status})

        tracking["by_pm"][pm] = {
            "this_week_count": len(top_5_by_pm.get(pm, [])),
            "last_week": last_with_status,
            "last_week_count": len(last_md),
            "resolved_count": resolved,
            "carried_count": carried,
            "stuck_count": stuck_count,
            "stuck_items": stuck_items,
        }

    # Persist.
    if persist:
        DATA.mkdir(parents=True, exist_ok=True)
        COMMITMENTS_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return tracking


def stuck_content_hashes(pm: str) -> set[str]:
    """Content hashes that have appeared in the last 3 consecutive weeks
    for this PM. Used to bump severity to critical."""
    state = load_commitments()
    weeks = state.get("weeks", [])
    if len(weeks) < STUCK_THRESHOLD_WEEKS:
        return set()
    out: set[str] = set()
    last_3 = weeks[-STUCK_THRESHOLD_WEEKS:]
    candidate_hashes: set[str] = None
    for w in last_3:
        md = ((w.get("by_pm") or {}).get(pm) or {}).get("must_discuss") or []
        hashes = {m.get("content_hash") for m in md if m.get("content_hash")}
        candidate_hashes = hashes if candidate_hashes is None else (candidate_hashes & hashes)
        if not candidate_hashes:
            break
    return candidate_hashes or set()
