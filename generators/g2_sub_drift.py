"""Generator 2 — Sub Performance Drift.

For each (sub × phase × job) where job-instance status is ongoing/complete
and the sub has performed this phase on >= 3 jobs:

  current  = sub_involved.density on this instance
  baseline = sub-phase rollup.primary_density (across all the sub's jobs)

  If current < baseline - 0.20 → INSIGHT(severity = warn).

This is the cross-data signal: "Watts is below his own baseline on this
job", distinct from G1 ("phase X dragging vs industry median").
"""
from __future__ import annotations

from generators._common import (
    insight_rank_score,
    job_pm_map,
    load_binders,
    load_excluded_jobs,
    load_phase3,
    make_insight,
)
from generators._phase_names import phase_label

DRIFT_THRESHOLD = 0.20
MIN_JOBS_FOR_BASELINE = 3


def _pct(d: float | None) -> str:
    if d is None:
        return "—"
    return f"{int(round(d * 100))}%"


def generate(phase3: dict, binders: list[dict], generated_at: str) -> list[dict]:
    rollups = phase3["rollups"]["rollups"]
    rollup_idx: dict[tuple[str, str], dict] = {
        (r["sub"], r["phase_code"]): r for r in rollups
    }
    pm_lookup = job_pm_map(binders)
    excluded = load_excluded_jobs()

    insights: list[dict] = []

    for ins in phase3["instances"]["instances"]:
        if ins.get("status") not in ("ongoing", "complete"):
            continue
        job = ins["job"]
        if job in excluded:
            continue
        phase_code = ins["phase_code"]
        phase_name = ins["phase_name"]
        pm = pm_lookup.get(job)
        for sub_entry in ins.get("subs_involved", []) or []:
            sub_name = sub_entry.get("sub")
            current = sub_entry.get("density")
            if not sub_name or current is None:
                continue
            rollup = rollup_idx.get((sub_name, phase_code))
            if not rollup:
                continue
            if (rollup.get("jobs_performed") or 0) < MIN_JOBS_FOR_BASELINE:
                continue
            baseline = rollup.get("primary_density")
            if baseline is None:
                continue
            delta = current - baseline
            if delta >= -DRIFT_THRESHOLD:
                continue  # not dragging enough below their baseline

            phase_str = phase_label(phase_code, phase_name)
            msg = (
                f"{sub_name} running {_pct(current)} on {phase_str} "
                f"at {job}, vs their typical {_pct(baseline)} "
                f"across {rollup.get('jobs_performed')} jobs."
            )
            summary = (
                f"{sub_name} {_pct(current)} on {phase_str} · "
                f"typical {_pct(baseline)} across {rollup.get('jobs_performed')} jobs"
            )
            ev = [
                {
                    "kind": "sub_on_instance",
                    "job": job,
                    "phase_code": phase_code,
                    "phase_name": phase_name,
                    "sub": sub_name,
                    "current_density": current,
                    "active_days": sub_entry.get("active_days"),
                    "log_count": sub_entry.get("log_count"),
                },
                {
                    "kind": "sub_phase_rollup",
                    "sub": sub_name,
                    "phase_code": phase_code,
                    "baseline_density": baseline,
                    "jobs_performed": rollup.get("jobs_performed"),
                    "primary_active_days_median": rollup.get("primary_active_days_median"),
                    "delta_below_baseline": round(delta, 4),
                },
            ]
            short_sub = sub_name.split(",")[0].split(" LLC")[0].split(" Inc")[0].strip()
            ask = f"What's different about {short_sub} on {job}? Sub issue or job-specific?"
            insights.append(
                make_insight(
                    generator="g2",
                    type_="sub_drift",
                    severity="warn",
                    message=msg,
                    summary_line=summary,
                    ask=ask,
                    evidence=ev,
                    related_job=job,
                    related_pm=pm,
                    related_phase=phase_code,
                    related_phase_name=phase_name,
                    related_sub=sub_name,
                    generated_at=generated_at,
                )
            )

    return insights


if __name__ == "__main__":
    from datetime import datetime, timezone

    phase3 = load_phase3()
    binders = load_binders()
    out = generate(phase3, binders, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    print(f"G2 produced {len(out)} insights.")
    for ins in sorted(out, key=insight_rank_score, reverse=True)[:5]:
        print(f"  [{ins['severity']:>8}] {ins['type']:<22} {ins['message'][:120]}")
