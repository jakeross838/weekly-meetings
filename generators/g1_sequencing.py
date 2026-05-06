"""Generator 1 — Sequencing Risk + Sequencing Violation.

sequencing_risk:
  IF phase_X.status = "ongoing"
    AND phase_X.primary_density < 0.65
    AND ANY successor phase has logs (status in [ongoing, complete])
  THEN INSIGHT(severity = critical if successor already started, else warn).

sequencing_violation:
  IF phase_X.status = "complete"
    AND ANY predecessor phase has zero logs AND zero scheduled date
  THEN INSIGHT(severity = warn).

Reads phase_instances-v2.json, which already computes
predecessors_complete / predecessors_missing / successors_started.
"""
from __future__ import annotations

from datetime import timedelta

from generators._common import (
    insight_rank_score,
    job_pm_map,
    load_binders,
    load_excluded_jobs,
    load_phase3,
    make_insight,
    parse_iso,
)
from generators._phase_names import phase_label

DENSITY_RISK_THRESHOLD = 0.65
# sequencing_violation only fires for phases whose last log is recent —
# we don't want to surface 200+ historical classification artifacts on
# closeout-stage jobs. 90-day cap keeps the signal actionable.
VIOLATION_RECENCY_DAYS = 90


def _pct(d: float | None) -> str:
    if d is None:
        return "—"
    return f"{int(round(d * 100))}%"


def _instance_index(instances: list[dict]) -> dict[tuple[str, str], dict]:
    """{(job, phase_code): instance}"""
    out = {}
    for ins in instances:
        out[(ins["job"], ins["phase_code"])] = ins
    return out


def generate(phase3: dict, binders: list[dict], generated_at: str) -> list[dict]:
    instances = phase3["instances"]["instances"]
    medians = {m["phase_code"]: m for m in phase3["medians"]["medians"]}
    pm_lookup = job_pm_map(binders)
    idx = _instance_index(instances)
    today = parse_iso(phase3["instances"].get("today"))
    excluded = load_excluded_jobs()
    insights: list[dict] = []

    # Build a per-job set of phase_codes that have logs (ongoing OR complete).
    job_phases_with_logs: dict[str, set[str]] = {}
    for ins in instances:
        if ins.get("status") in ("ongoing", "complete"):
            job_phases_with_logs.setdefault(ins["job"], set()).add(ins["phase_code"])

    for ins in instances:
        job = ins["job"]
        if job in excluded:
            continue
        code = ins["phase_code"]
        name = ins["phase_name"]
        status = ins.get("status")
        density = ins.get("primary_density")
        pm = pm_lookup.get(job)

        # ---------- sequencing_risk ----------
        if status == "ongoing" and density is not None and density < DENSITY_RISK_THRESHOLD:
            successors = ins.get("successors", []) or []
            successors_started = ins.get("successors_started", []) or []
            # Any successor on this job that has logs?
            started_with_logs = [
                s for s in successors
                if s in job_phases_with_logs.get(job, set())
            ]
            if started_with_logs:
                first = started_with_logs[0]
                first_inst = idx.get((job, first))
                first_name = first_inst["phase_name"] if first_inst else ""
                successor_status = first_inst.get("status") if first_inst else "unknown"
                severity = "critical" if successor_status in ("ongoing", "complete") else "warn"
                density_label = ins.get("density_label_absolute") or "—"
                active_days = ins.get("primary_active_days")
                phase_str = phase_label(code, name)
                succ_str  = phase_label(first, first_name)
                msg = (
                    f"{phase_str} dragging at {_pct(density)} ({density_label}). "
                    f"Successor {succ_str} {successor_status}. "
                    f"Risk of overlap."
                )
                summary = (
                    f"{_pct(density)} density"
                    + (f" · {active_days}d active" if active_days else "")
                    + f" · successor {succ_str} {successor_status}"
                )
                ev = [
                    {
                        "kind": "phase_instance",
                        "job": job,
                        "phase_code": code,
                        "phase_name": name,
                        "status": status,
                        "primary_density": density,
                        "primary_active_days": ins.get("primary_active_days"),
                        "first_log_date": ins.get("first_log_date"),
                        "last_log_date": ins.get("last_log_date"),
                    },
                    {
                        "kind": "phase_instance",
                        "job": job,
                        "phase_code": first,
                        "phase_name": first_name,
                        "status": successor_status,
                        "first_log_date": first_inst.get("first_log_date") if first_inst else None,
                    },
                ]
                # Conversational ask in PM voice — no report-speak.
                if successor_status == "complete":
                    ask = (
                        f"Did we close {succ_str} early, or is {phase_str} "
                        "actually further along than the data shows?"
                    )
                else:
                    ask = (
                        f"Are we stuck on {phase_str}, or just slow? "
                        f"Hold {succ_str} or run parallel?"
                    )
                insights.append(
                    make_insight(
                        generator="g1",
                        type_="sequencing_risk",
                        severity=severity,
                        message=msg,
                        summary_line=summary,
                        ask=ask,
                        evidence=ev,
                        related_job=job,
                        related_pm=pm,
                        related_phase=code,
                        related_phase_name=name,
                        generated_at=generated_at,
                    )
                )

        # ---------- sequencing_violation ----------
        if status == "complete":
            # Recency filter — skip historical artifacts.
            last_log = parse_iso(ins.get("last_log_date"))
            if today and last_log and (today - last_log).days > VIOLATION_RECENCY_DAYS:
                continue
            missing = ins.get("predecessors_missing", []) or []
            if missing and not ins.get("predecessors_complete", True):
                # Re-check: a predecessor "violation" is when the predecessor
                # has zero log activity on this job (no instance OR instance
                # exists but has 0 bursts/0 logs).
                truly_missing = []
                for pred in missing:
                    pred_inst = idx.get((job, pred))
                    if pred_inst is None:
                        truly_missing.append(pred)
                    elif (pred_inst.get("log_count") or 0) == 0:
                        truly_missing.append(pred)
                if truly_missing:
                    pred = truly_missing[0]
                    # phase name lookup from medians or taxonomy
                    pred_name = ""
                    pred_med = medians.get(pred)
                    if pred_med:
                        pred_name = pred_med.get("phase_name", "")
                    phase_str = phase_label(code, name)
                    pred_str  = phase_label(pred, pred_name)
                    msg = (
                        f"{phase_str} complete on {job} but predecessor "
                        f"{pred_str} has no logs. "
                        f"Likely classification miss or skipped scope."
                    )
                    summary = f"complete · pred {pred_str} no logs"
                    ev = [
                        {
                            "kind": "phase_instance",
                            "job": job,
                            "phase_code": code,
                            "phase_name": name,
                            "status": status,
                            "first_log_date": ins.get("first_log_date"),
                            "last_log_date": ins.get("last_log_date"),
                        },
                        {
                            "kind": "predecessor_missing",
                            "job": job,
                            "phase_code": pred,
                            "phase_name": pred_name,
                            "log_count": 0,
                        },
                    ]
                    ask = f"Was {pred_str} done? Or did we skip it?"
                    insights.append(
                        make_insight(
                            generator="g1",
                            type_="sequencing_violation",
                            severity="warn",
                            message=msg,
                            summary_line=summary,
                            ask=ask,
                            evidence=ev,
                            related_job=job,
                            related_pm=pm,
                            related_phase=code,
                            related_phase_name=name,
                            generated_at=generated_at,
                            bucket="data_quality",
                        )
                    )

    return insights


if __name__ == "__main__":
    from datetime import datetime, timezone

    phase3 = load_phase3()
    binders = load_binders()
    out = generate(phase3, binders, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    print(f"G1 produced {len(out)} insights.")
    for ins in sorted(out, key=insight_rank_score, reverse=True)[:5]:
        print(f"  [{ins['severity']:>8}] {ins['type']:<22} {ins['message'][:120]}")
