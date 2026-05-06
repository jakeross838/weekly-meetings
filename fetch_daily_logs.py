"""
Fetch daily log data for a given PM from the Buildertrend scraper output.

Entry point: fetch_for_pm(pm_name, meeting_date, lookback_days)
Returns {"summary": {...per-job...}, "raw_entries": [...], "meta": {...}}.
Fails soft on missing file, parse errors, or missing job mappings.

CLI:
    python fetch_daily_logs.py "Martin Mannix" 2026-04-21
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from constants import DAILY_LOGS_PATH, JOB_NAME_MAP, PM_JOBS

STALE_HOURS = 48
DEFAULT_LOOKBACK_DAYS = 14
MAX_RAW_ENTRIES = 50  # truncate raw list if larger
# Jobs with no log data yet: Johnson, Brantman, Buhrman, Duncan, Gavin, Harllee 313, Moore

CREWS_LABELS_TO_STRIP = {
    "on Site", "Daily Workforce", "Absent Crew(s)", "NONE",
    "Parent Group Activity", "Inspections?", "Deliveries?", "Read more",
}


def parse_crews(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").split(";")]
    return [p for p in parts if p and p not in CREWS_LABELS_TO_STRIP]


def _is_enriched(rec: dict) -> bool:
    """A record counts as enriched if the scraper stamped it with enriched_at."""
    return bool(rec.get("enriched_at"))


def _effective_notes(rec: dict) -> str:
    """Prefer the full notes body; fall back to the legacy truncated notes."""
    return (rec.get("notes_full") or rec.get("notes") or "").strip()


def _effective_crews_clean(rec: dict) -> list[str]:
    """Prefer the structured crews_clean list; fall back to parsing the legacy crews string."""
    raw = rec.get("crews_clean")
    if isinstance(raw, list) and raw:
        return [c for c in raw if c]
    return parse_crews(rec.get("crews", ""))


def _is_meaningful(s) -> bool:
    """Whether a text field carries real content.

    BT's daily-log UI renders inspection/delivery/other-notable sections as free-form
    text; PMs often type "None", "N/A", or "-" when nothing applies. Treat those as
    absent so downstream event lists don't balloon with no-op entries.
    """
    if not s:
        return False
    t = s.strip().lower()
    return t not in ("", "none", "n/a", "na", "-", "—")


def _parse_log_date(date_str: str, context_date=None):
    """Parse a BT log date like 'Wed, Dec 31, 2025', 'Mon, 14 Jan 2026', or 'Fri, Apr 3' (no year).

    BT's list view drops the year for entries in the current year. If the input has no year,
    we fall back to context_date.year; if the resulting date lands in the future relative to
    context_date, we subtract one year (handles wrap-around for Dec dates parsed in early year).

    Returns datetime.date or None.
    """
    if not date_str:
        return None
    s = date_str.strip()
    for fmt in ("%a, %b %d, %Y", "%a, %d %b %Y", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Year-less formats (e.g. 'Fri, Apr 3', 'Apr 3') — need context year
    if context_date is None:
        return None
    for fmt in ("%a, %b %d", "%b %d", "%a, %d %b", "%d %b"):
        try:
            parsed = datetime.strptime(s, fmt).date().replace(year=context_date.year)
            # If we got a date after the context, BT's list is sliding backwards in time —
            # treat "future" dates as prior calendar year (e.g. 'Dec 28' seen in January).
            if parsed > context_date:
                parsed = parsed.replace(year=context_date.year - 1)
            return parsed
        except ValueError:
            continue
    return None


def _parse_iso_datetime(s: str):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _safe_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None


def _build_summary(records: list, lookback_days: int) -> dict:
    """Build per-job summary from filtered records. Each record carries _date (datetime.date).

    Handles both enriched (post-Phase 4) and legacy (pre-Phase 4) records: legacy records
    contribute to core counts + weather via their old fields, but cannot contribute to
    enrichment-derived metrics (workforce, absent crews, activity tags, inspection/delivery
    details, notable activities).
    """
    total = len(records)
    days = {r["_date"] for r in records if r.get("_date")}

    crew_day_counts: dict = {}  # crew -> set of dates
    activities = set()
    inspection_days = set()
    delivery_days = set()
    highs = []
    lows = []

    # Enrichment-only metrics
    workforce_values = []  # integers
    absent_crew_days: dict = {}  # crew -> set of dates
    activity_tag_days: dict = {}  # tag -> set of dates
    notable_entries = []  # {date, text}
    inspection_entries = []  # {date, details}
    delivery_entries = []  # {date, details}

    enriched_count = 0
    unenriched_count = 0

    for r in records:
        d = r.get("_date")
        if _is_enriched(r):
            enriched_count += 1
        else:
            unenriched_count += 1

        for crew in _effective_crews_clean(r):
            crew_day_counts.setdefault(crew, set()).add(d)
        if r.get("activity"):
            activities.add(r["activity"])
        if r.get("hasInspections") and d:
            inspection_days.add(d)
        if r.get("hasDeliveries") and d:
            delivery_days.add(d)
        hi = _safe_int(r.get("weatherHigh"))
        lo = _safe_int(r.get("weatherLow"))
        if hi is not None:
            highs.append(hi)
        if lo is not None:
            lows.append(lo)

        # Enrichment metrics — only for enriched records with real values
        wf = _safe_int(r.get("daily_workforce"))
        if wf is not None:
            workforce_values.append(wf)

        for crew in (r.get("absent_crews") or []):
            crew = (crew or "").strip()
            if crew:
                absent_crew_days.setdefault(crew, set()).add(d)

        for tag in (r.get("parent_group_activities") or []):
            tag = (tag or "").strip()
            if tag and d:
                activity_tag_days.setdefault(tag, set()).add(d)

        other = (r.get("other_notable_activities") or "").strip()
        if _is_meaningful(other):
            if len(other) > 400:
                other = other[:400].rstrip() + "..."
            notable_entries.append({"date": d.isoformat() if d else "", "text": other})

        insp = (r.get("inspection_details") or "").strip()
        if _is_meaningful(insp):
            inspection_entries.append({"date": d.isoformat() if d else "", "details": insp})

        deliv = (r.get("delivery_details") or "").strip()
        if _is_meaningful(deliv):
            delivery_entries.append({"date": d.isoformat() if d else "", "details": deliv})

    crew_counts_serializable = {
        k: len(v) for k, v in sorted(crew_day_counts.items(), key=lambda kv: -len(kv[1]))
    }

    sorted_recs = sorted(
        [r for r in records if r.get("_date")],
        key=lambda r: r["_date"],
        reverse=True,
    )
    latest_activities = [
        {
            "date": r["_date"].isoformat(),
            "activity": r.get("activity", ""),
            "author": r.get("author", ""),
        }
        for r in sorted_recs[:10]
    ]

    # workforce_stats
    if workforce_values:
        workforce_stats = {
            "avg": round(sum(workforce_values) / len(workforce_values), 1),
            "peak": max(workforce_values),
            "low": min(workforce_values),
            "total_person_days": sum(workforce_values),
        }
    else:
        workforce_stats = None

    # absent_crew_frequency: crew → days_absent_count, sorted desc
    absent_crew_frequency = {
        k: len(v) for k, v in sorted(absent_crew_days.items(), key=lambda kv: -len(kv[1]))
    }

    # activity_tag_frequency: tag → day_count, sorted desc
    activity_tag_frequency = {
        k: len(v) for k, v in sorted(activity_tag_days.items(), key=lambda kv: -len(kv[1]))
    }

    # Sort event lists newest first
    notable_entries.sort(key=lambda e: e["date"], reverse=True)
    inspection_entries.sort(key=lambda e: e["date"], reverse=True)
    delivery_entries.sort(key=lambda e: e["date"], reverse=True)

    summary = {
        "total_logs": total,
        "days_with_logs": len(days),
        "days_expected": lookback_days,
        "gap_days": max(0, lookback_days - len(days)),
        "unique_crews": sorted(crew_day_counts.keys()),
        "crew_day_counts": crew_counts_serializable,
        "activities_seen": sorted(activities),
        "inspection_days": len(inspection_days),
        "delivery_days": len(delivery_days),
        "latest_activities": latest_activities,
        "enriched_count": enriched_count,
        "unenriched_count": unenriched_count,
        "workforce_stats": workforce_stats,
        "absent_crew_frequency": absent_crew_frequency,
        "activity_tag_frequency": activity_tag_frequency,
        "notable_activities": notable_entries,
        "inspection_events": inspection_entries,
        "delivery_events": delivery_entries,
    }
    if highs or lows:
        weather = {}
        if highs:
            weather["high_max"] = max(highs)
        if lows:
            weather["low_min"] = min(lows)
        summary["weather_range"] = weather
    return summary


def fetch_for_pm(pm_name: str, meeting_date: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict:
    """Fetch per-PM daily log context from the Buildertrend scraper output.

    Returns { "summary": {...per-job...}, "raw_entries": [...], "meta": {...} }.
    On file missing: meta.error is set, summary and raw_entries are empty, meta.stale = True.
    On stale (>STALE_HOURS since lastRun): meta.stale = True, data still returned.
    """
    meta = {
        "pm": pm_name,
        "meeting_date": meeting_date,
        "lookback_days": lookback_days,
        "source_path": str(DAILY_LOGS_PATH),
        "stale": False,
        "jobs_without_data": [],
        "raw_truncated": False,
        "enriched_counts": {},    # per-job: { short_name: int }
        "unenriched_counts": {},  # per-job: { short_name: int }
    }

    if not DAILY_LOGS_PATH.exists():
        meta["error"] = f"Daily logs file not found at {DAILY_LOGS_PATH}"
        meta["stale"] = True
        return {"summary": {}, "raw_entries": [], "meta": meta}

    try:
        data = json.loads(DAILY_LOGS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        meta["error"] = f"Failed to parse daily-logs.json: {e}"
        return {"summary": {}, "raw_entries": [], "meta": meta}

    meta["last_run"] = data.get("lastRun")
    last_run_dt = _parse_iso_datetime(data.get("lastRun", ""))
    if last_run_dt is not None:
        age_hours = (datetime.now(timezone.utc) - last_run_dt).total_seconds() / 3600
        meta["age_hours"] = round(age_hours, 1)
        if age_hours > STALE_HOURS:
            meta["stale"] = True

    by_job = data.get("byJob", {}) or {}

    try:
        md = datetime.strptime(meeting_date, "%Y-%m-%d").date()
    except ValueError:
        meta["error"] = f"Invalid meeting_date: {meeting_date!r} (expected YYYY-MM-DD)"
        return {"summary": {}, "raw_entries": [], "meta": meta}

    window_start = md - timedelta(days=lookback_days)
    meta["window_start"] = window_start.isoformat()
    meta["window_end"] = md.isoformat()

    pm_jobs = PM_JOBS.get(pm_name)
    if pm_jobs is None:
        meta["error"] = f"Unknown PM: {pm_name!r}. Known PMs: {sorted(PM_JOBS.keys())}"
        return {"summary": {}, "raw_entries": [], "meta": meta}

    summary: dict = {}
    raw_entries: list = []

    for short_name in pm_jobs:
        job_key = JOB_NAME_MAP.get(short_name)
        if not job_key:
            meta["jobs_without_data"].append(short_name)
            summary[short_name] = {"total_logs": 0, "note": "no mapping in JOB_NAME_MAP"}
            continue
        job_records = by_job.get(job_key)
        if not job_records:
            meta["jobs_without_data"].append(short_name)
            summary[short_name] = {"total_logs": 0, "note": "job key not present in scraper output"}
            continue

        filtered = []
        for rec in job_records:
            d = _parse_log_date(rec.get("date", ""), context_date=md)
            if d is None:
                print(
                    f"[fetch_daily_logs] WARN: could not parse date "
                    f"{rec.get('date')!r} for logId {rec.get('logId')}",
                    file=sys.stderr,
                )
                continue
            if window_start <= d <= md:
                rec_copy = dict(rec)
                rec_copy["_date"] = d
                filtered.append(rec_copy)

        s = _build_summary(filtered, lookback_days)
        summary[short_name] = s
        meta["enriched_counts"][short_name] = s["enriched_count"]
        meta["unenriched_counts"][short_name] = s["unenriched_count"]

        for r in filtered:
            enriched = _is_enriched(r)
            notes_out = _effective_notes(r)
            if not enriched and len(notes_out) > 400:
                # Legacy notes are only the first 500 chars anyway; cap fallback at 400.
                notes_out = notes_out[:400]
            raw_entries.append({
                "date": r["_date"].isoformat(),
                "job": short_name,
                "activity": r.get("activity", ""),
                "author": r.get("author", ""),
                "crews_clean": _effective_crews_clean(r),
                "notes_full": notes_out,
                "daily_workforce": _safe_int(r.get("daily_workforce")),
                "absent_crews": list(r.get("absent_crews") or []),
                "parent_group_activities": list(r.get("parent_group_activities") or []),
                "other_notable_activities": (r.get("other_notable_activities") or None) if _is_meaningful(r.get("other_notable_activities")) else None,
                "inspection_details": (r.get("inspection_details") or None) if _is_meaningful(r.get("inspection_details")) else None,
                "delivery_details": (r.get("delivery_details") or None) if _is_meaningful(r.get("delivery_details")) else None,
                "weatherHigh": r.get("weatherHigh", ""),
                "weatherLow": r.get("weatherLow", ""),
                "hasInspections": bool(r.get("hasInspections")),
                "hasDeliveries": bool(r.get("hasDeliveries")),
                "enriched": enriched,
            })

    raw_entries.sort(key=lambda r: r["date"], reverse=True)
    total_before_truncate = len(raw_entries)
    if total_before_truncate > MAX_RAW_ENTRIES:
        raw_entries = raw_entries[:MAX_RAW_ENTRIES]
        meta["raw_truncated"] = True
        meta["raw_total_before_truncate"] = total_before_truncate

    return {"summary": summary, "raw_entries": raw_entries, "meta": meta}


if __name__ == "__main__":
    pm = sys.argv[1] if len(sys.argv) > 1 else "Martin Mannix"
    date = sys.argv[2] if len(sys.argv) > 2 else "2026-04-21"
    result = fetch_for_pm(pm, date)
    print(json.dumps(result, indent=2, default=str))
