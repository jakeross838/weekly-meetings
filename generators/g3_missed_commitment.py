"""Generator 3 — Missed Commitment.

For each enriched action item where:
  - status == COMPLETE
  - closed_date within last 14 days
  - requires_field_confirmation == True
  - related_sub OR related_phase is set

Verify field activity in [closed_date - 7, closed_date + 7] daily-log window.

Match logic per log entry on the item's job:
  - Sub match: related_sub appears in crews_clean (canonical) or notes_full text
  - Phase match: any parent_group_activity OR phrase in notes_full matches
                 a phase keyword whose phase_code == related_phase

If zero matching log entries → fire INSIGHT(missed_commitment, warn).

If enrichment didn't produce sub/phase, the item is skipped (per kickoff).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from generators._common import (
    BINDERS,
    canonical_sub_universe,
    compile_phase_matchers,
    crews_clean_subs,
    insight_rank_score,
    job_log_key,
    job_pm_map,
    load_binders,
    load_daily_logs,
    load_excluded_jobs,
    load_phase3,
    make_insight,
    match_phase,
    match_sub,
    parse_iso,
    parse_log_date,
)

ENRICHED_DIR = BINDERS / "enriched"
LOOKBACK_DAYS = 14
# Asymmetric window — closeout-style items often close weeks after the
# actual field work. Look back further than forward.
WINDOW_BACK_DAYS = 21
WINDOW_FWD_DAYS = 7


def _load_enriched_binders() -> list[dict]:
    out = []
    for p in sorted(ENRICHED_DIR.glob("*.enriched.json")):
        out.append({"file": p.name, "data": json.loads(p.read_text(encoding="utf-8"))})
    return out


def _log_in_window(log_date, target_date, back_days: int, fwd_days: int) -> bool:
    if log_date is None or target_date is None:
        return False
    diff = (log_date - target_date).days  # negative = before target
    return -back_days <= diff <= fwd_days


def _activity_matches(
    log: dict,
    related_sub: str | None,
    related_phase: str | None,
    phase_matchers: list,
    sub_universe: list[str],
) -> dict:
    """Check whether this log entry confirms field activity for the item.

    Returns a dict with `sub_match`, `phase_match`, `notes_excerpt`.
    """
    notes = " ".join(filter(None, [log.get("notes_full"), log.get("notes"), log.get("activity")]))
    crews = crews_clean_subs(log)
    pgas = log.get("parent_group_activities") or []
    sub_match = False
    phase_match = False

    if related_sub:
        # Direct canonical match against crews_clean
        if related_sub in crews:
            sub_match = True
        else:
            # Loose name match against canonical universe in notes
            mentioned = match_sub(notes, sub_universe)
            if mentioned and mentioned[0] == related_sub:
                sub_match = True

    if related_phase:
        # Match parent_group_activities first (those are construction tags)
        for pga in pgas:
            m = match_phase(pga, phase_matchers)
            if m and m[0] == related_phase:
                phase_match = True
                break
        # Then match keyword regex in free-text notes
        if not phase_match and notes:
            m = match_phase(notes, phase_matchers)
            if m and m[0] == related_phase:
                phase_match = True

    return {"sub_match": sub_match, "phase_match": phase_match}


# (kept unchanged) match_sub returns (canonical, confidence) | None — we
# only care about the canonical name here, not the confidence, so unwrap
# below where this helper's return is used.


def generate(phase3: dict, binders: list[dict], generated_at: str, today: str | None = None) -> dict:
    """Returns {'insights': [...], 'stats': {...}}."""
    today_d = parse_iso(today or phase3["job_stages"]["today"])
    cutoff = today_d - timedelta(days=LOOKBACK_DAYS)

    sub_universe = sorted(canonical_sub_universe(phase3), key=len, reverse=True)
    phase_matchers = compile_phase_matchers(phase3["phase_keywords"])
    pm_lookup = job_pm_map(load_binders())  # use originals for PM mapping
    daily_by_job = load_daily_logs()
    log_keys = list(daily_by_job.keys())
    excluded = load_excluded_jobs()

    insights: list[dict] = []
    stats = {
        "items_total": 0,
        "items_complete_in_window": 0,
        "items_skipped_no_close_date": 0,
        "items_skipped_no_field_flag": 0,
        "items_skipped_no_phase_or_sub": 0,
        "items_checked": 0,
        "items_flagged": 0,
        "items_confirmed": 0,
        "by_pm": {},
    }

    for binder in binders:
        b = binder["data"]
        pm = b["meta"]["pm"]
        for item in b.get("items", []):
            stats["items_total"] += 1
            if item.get("status") != "COMPLETE":
                continue
            if item.get("job") in excluded:
                continue
            close_str = item.get("closed_date")
            close_d = parse_iso(close_str)
            if close_d is None:
                stats["items_skipped_no_close_date"] += 1
                continue
            if close_d < cutoff or close_d > today_d:
                continue
            stats["items_complete_in_window"] += 1
            if not item.get("requires_field_confirmation"):
                stats["items_skipped_no_field_flag"] += 1
                continue
            related_phase = item.get("related_phase")
            related_sub = item.get("related_sub")
            if not related_phase and not related_sub:
                stats["items_skipped_no_phase_or_sub"] += 1
                continue
            stats["items_checked"] += 1

            # Resolve job → log-key
            job = item.get("job")
            log_key = job_log_key(job, log_keys)
            logs = daily_by_job.get(log_key, []) if log_key else []
            window_logs = []
            for log in logs:
                ld = parse_log_date(log.get("date", ""), close_d.year)
                if ld is None:
                    continue
                if _log_in_window(ld, close_d, WINDOW_BACK_DAYS, WINDOW_FWD_DAYS):
                    window_logs.append((ld, log))

            sub_hits = 0
            phase_hits = 0
            sample_hit = None
            for ld, log in window_logs:
                m = _activity_matches(log, related_sub, related_phase, phase_matchers, sub_universe)
                if m["sub_match"]:
                    sub_hits += 1
                if m["phase_match"]:
                    phase_hits += 1
                if (m["sub_match"] or m["phase_match"]) and sample_hit is None:
                    sample_hit = (ld, log)

            confirmed = (sub_hits + phase_hits) > 0
            if confirmed:
                stats["items_confirmed"] += 1
                continue

            stats["items_flagged"] += 1
            stats["by_pm"][pm] = stats["by_pm"].get(pm, 0) + 1

            label_parts = []
            if related_sub:
                label_parts.append(related_sub)
            if related_phase:
                label_parts.append(related_phase)
            label = " / ".join(label_parts) or "(no anchor)"

            window_size = len(window_logs)
            window_lo = (close_d - timedelta(days=WINDOW_BACK_DAYS)).isoformat()
            window_hi = (close_d + timedelta(days=WINDOW_FWD_DAYS)).isoformat()

            msg = (
                f"Item {item['id']} marked DONE {close_str} but no field activity "
                f"confirms ({label}). {window_size} daily logs in {window_lo}…{window_hi}, "
                f"none mention {label}."
            )
            summary = (
                f"Item {item['id']} closed {close_str} · 0 {label} logs in window"
                f" ({window_size} logs in window total)"
            )
            ev = [
                {
                    "kind": "action_item",
                    "id": item["id"],
                    "job": job,
                    "action": item.get("action"),
                    "update": item.get("update"),
                    "closed_date": close_str,
                    "related_phase": related_phase,
                    "related_phase_inferred": item.get("related_phase_inferred", False),
                    "related_sub": related_sub,
                    "related_sub_inferred": item.get("related_sub_inferred", False),
                    "requires_field_confirmation_inferred": item.get(
                        "requires_field_confirmation_inferred", False
                    ),
                },
                {
                    "kind": "log_window",
                    "job": job,
                    "log_key": log_key,
                    "window_start": window_lo,
                    "window_end": window_hi,
                    "logs_in_window": window_size,
                    "sub_match_count": sub_hits,
                    "phase_match_count": phase_hits,
                },
            ]
            short_action = (item.get("action") or "").split("—")[0].split("--")[0].strip()
            short_action = short_action.replace("Complete -", "").replace("Complete:", "").strip()
            short_action = short_action[:60]
            if related_sub:
                ask = f"Was {related_sub.split(',')[0].split(' LLC')[0].strip()} actually here? Verify in field."
            else:
                ask = f"Was [{short_action}] actually done? Verify in field."
            insights.append(
                make_insight(
                    generator="g3",
                    type_="missed_commitment",
                    severity="warn",
                    message=msg,
                    summary_line=summary,
                    ask=ask,
                    evidence=ev,
                    related_job=job,
                    related_pm=pm,
                    related_phase=related_phase,
                    related_sub=related_sub,
                    related_action_id=item["id"],
                    generated_at=generated_at,
                )
            )

    if stats["items_complete_in_window"] > 0:
        stats["flagged_pct"] = round(
            100 * stats["items_flagged"] / stats["items_complete_in_window"], 1
        )
    else:
        stats["flagged_pct"] = 0.0

    return {"insights": insights, "stats": stats}


if __name__ == "__main__":
    from datetime import timezone

    phase3 = load_phase3()
    enriched = _load_enriched_binders()
    res = generate(
        phase3,
        enriched,
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    print(f"G3 produced {len(res['insights'])} insights.")
    print("Stats:")
    for k, v in res["stats"].items():
        print(f"  {k}: {v}")
    for ins in sorted(res["insights"], key=insight_rank_score, reverse=True)[:5]:
        print(f"  [{ins['severity']:>8}] {ins['type']:<22} {ins['message'][:140]}")
