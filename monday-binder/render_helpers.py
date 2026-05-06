"""Shared rendering helpers for meeting-prep pages.

Used by:
  - monday-binder/build_meeting_prep.py (Monday weekly batch — runs commitment
    tracker, prints status, exits; no longer pre-generates HTML or PDFs)
  - monday-binder/transcript-ui/server.py (live HTML routes + on-demand PDF
    download routes; reads everything fresh per request)

Pure data + template substitution. Templates live next to this file
(meeting-prep.template.html, master.template.html, executive.template.html,
preconstruction.template.html). Each template carries the placeholder
`__SI_DATA_BUNDLE__` which is JSON-replaced at render time.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Project root on sys.path so `generators` resolves regardless of
# whether this is imported as `monday-binder.render_helpers` or directly.
_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from generators import commitment_tracker
from generators._common import (
    canonical_sub_universe,
    job_log_key,
    load_daily_logs,
    parse_log_date,
)


# ---- Paths ---------------------------------------------------------------
ROOT = _PROJECT_ROOT
DATA = ROOT / "data"
BINDERS = ROOT / "binders"
ENRICHED = BINDERS / "enriched"
MONDAY_BINDER = ROOT / "monday-binder"
JOB_TEMPLATE = MONDAY_BINDER / "job-document.template.html"
PM_PACKET_TEMPLATE = MONDAY_BINDER / "pm-packet.template.html"
MASTER_TEMPLATE = MONDAY_BINDER / "master.template.html"
EXECUTIVE_TEMPLATE = MONDAY_BINDER / "executive.template.html"
PRECON_TEMPLATE = MONDAY_BINDER / "preconstruction.template.html"


# Phase 12 Part B — 8 action item categories
ITEM_CATEGORIES = (
    "SCHEDULE", "PROCUREMENT", "SUB-TRADE", "CLIENT",
    "QUALITY", "BUDGET", "ADMIN", "SELECTION",
)


# Walk-area mapping for the Site meeting §2. Each area buckets one or more
# phase-taxonomy stages so the Site walk reads as a real walk-the-job
# checklist (Exterior → Foundation → Framing → ...) rather than a phase code list.
WALK_AREAS = [
    ("Site & Exterior",   [1, 14]),                # 1=Pre-Con/Site, 14=Exterior Finish
    ("Foundation",        [2]),
    ("Shell & Framing",   [3]),
    ("Dry-In",            [4, 5]),                 # 4=Dry-In, 5=Exterior Rough
    ("MEP Rough",         [6]),
    ("Envelope",          [7]),                    # stucco, siding, soffit
    ("Drywall & Insul",   [8]),
    ("Interior Trim",     [9]),
    ("Tile & Stone",      [10]),
    ("Cabinets & Tops",   [11]),
    ("Paint",             [12]),
    ("MEP Trim",          [13]),
    ("Punch & Closeout",  [15]),
]


# ---- PM registry ---------------------------------------------------------
PM_NAMES = [
    "Nelson Belanger",
    "Bob Mozine",
    "Martin Mannix",
    "Jason Szykulski",
    "Lee Worthy",
]

PM_SLUGS = {pm: pm.lower().replace(" ", "-") for pm in PM_NAMES}
SLUG_TO_PM = {slug: pm for pm, slug in PM_SLUGS.items()}

PM_BINDER_FILES = {pm: f"{pm.replace(' ', '_')}.json" for pm in PM_NAMES}


# ---- Scoring -------------------------------------------------------------
SEVERITY_SCORE = {"critical": 3, "warn": 1}
TYPE_SCORE = {
    "missed_commitment": 5,
    "sequencing_risk": 4,
    "sub_drift": 3,
    "sequencing_violation": 2,
}
MAX_PER_TYPE_IN_TOP5 = 2

CONFIRM_VERBS = re.compile(
    r"\b(confirm|verify|nail\s*down|lock|finalize|schedule|coordinate)\w*",
    re.IGNORECASE,
)


def insight_score(ins: dict) -> int:
    return SEVERITY_SCORE.get(ins.get("severity", "warn"), 1) + TYPE_SCORE.get(ins.get("type", ""), 0)


def parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_json(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def shorten_action(a: str | None) -> str:
    if not a:
        return ""
    s = re.sub(r"^Complete\s*[-—:]\s*", "", a).strip()
    s = s.split("—")[0].split(" -- ")[0]
    return _word_truncate(s, 80)


def _word_truncate(text: str, max_chars: int, suffix: str = "…") -> str:
    """Truncate `text` to at most `max_chars`, cutting on the last
    word boundary that fits and appending `suffix`. Returns the
    original string unchanged if it already fits.

    Used by exec-summary slices where pre-existing char-count slicing
    chopped mid-word (e.g. "...AC return louver door style (5-panel
    matchi"). Cuts at the last whitespace before the limit and trims
    trailing punctuation.
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    space = cut.rfind(" ")
    if space > max_chars // 2:  # require at least half the budget before snapping back
        cut = cut[:space]
    return cut.rstrip(" ,;:-—.") + suffix


# ---- Render context ------------------------------------------------------
@dataclass
class RenderContext:
    all_insights: list
    today: str
    phase3: dict
    daily_by_job: dict
    pm_to_jobs: dict
    items_by_pm: dict
    thresholds: dict = field(default_factory=dict)


def _merge_category_from_source(enriched_items: list[dict], source_items: list[dict]) -> list[dict]:
    """Reconciles enriched binder against the source binder for fields
    that the enrichment pipeline doesn't currently propagate:
      - `category` and `source` (Phase 12 Part B backfill)
      - `status=DUPLICATE_MERGED` plus `merged_into`/`merge_reason`/`merged_at`
        (Phase 12 polish dedup) — these are authoritative on the source
        binder; enriched copies are stale until next enrichment run.
    """
    src_by_id = {it.get("id"): it for it in source_items if it.get("id")}
    out: list[dict] = []
    for it in enriched_items:
        merged = dict(it)
        src = src_by_id.get(it.get("id"))
        if src is not None:
            if not merged.get("category"):
                merged["category"] = src.get("category")
            if not merged.get("source"):
                merged["source"] = src.get("source")
            # Always pull dedup fields forward from source — source is
            # authoritative for status when DUPLICATE_MERGED.
            src_status = (src.get("status") or "").upper()
            if src_status == "DUPLICATE_MERGED":
                merged["status"] = src_status
                if src.get("merged_into"):
                    merged["merged_into"] = src["merged_into"]
                if src.get("merge_reason"):
                    merged["merge_reason"] = src["merge_reason"]
                if src.get("merged_at"):
                    merged["merged_at"] = src["merged_at"]
            # Pull close_date forward (Phase 12 polish)
            if src.get("close_date") and not merged.get("close_date"):
                merged["close_date"] = src["close_date"]
        out.append(merged)
    return out


def load_context() -> RenderContext:
    """Load all input data fresh from disk. No caching."""
    import yaml

    insights_data = load_json(DATA / "insights.json")
    all_insights = insights_data["insights"]
    today = insights_data["today"]

    phase3 = {
        "instances": load_json(DATA / "phase-instances-v2.json"),
        "medians": load_json(DATA / "phase-medians.json"),
        "rollups": load_json(DATA / "sub-phase-rollups.json"),
        "job_stages": load_json(DATA / "job-stages.json"),
        "bursts": load_json(DATA / "bursts.json"),
        "taxonomy": yaml.safe_load((ROOT / "config" / "phase-taxonomy.yaml").read_text(encoding="utf-8")),
    }

    # Bug 4 (wmp22) — org-configurable thresholds for stale-phase suppression.
    thresholds_path = ROOT / "config" / "thresholds.yaml"
    thresholds: dict = {}
    if thresholds_path.exists():
        thresholds = yaml.safe_load(thresholds_path.read_text(encoding="utf-8")) or {}
    thresholds.setdefault("phase_active_suppress_days", 90)

    daily_by_job = load_daily_logs()

    pm_to_jobs: dict[str, list[str]] = {}
    items_by_pm: dict[str, list[dict]] = {}
    for pm in PM_NAMES:
        bp = BINDERS / PM_BINDER_FILES[pm]
        if not bp.exists():
            pm_to_jobs[pm] = []
            items_by_pm[pm] = []
            continue
        binder_orig = load_json(bp)
        pm_to_jobs[pm] = [j["name"] for j in binder_orig.get("jobs", [])]
        source_items = binder_orig.get("items", [])
        enriched_path = ENRICHED / f"{Path(PM_BINDER_FILES[pm]).stem}.enriched.json"
        if enriched_path.exists():
            enriched_items = load_json(enriched_path).get("items", [])
            items_by_pm[pm] = _merge_category_from_source(enriched_items, source_items)
        else:
            items_by_pm[pm] = source_items

    return RenderContext(
        all_insights=all_insights,
        today=today,
        phase3=phase3,
        daily_by_job=daily_by_job,
        pm_to_jobs=pm_to_jobs,
        items_by_pm=items_by_pm,
        thresholds=thresholds,
    )


def select_top_5(pm_field_sorted: list[dict]) -> list[dict]:
    top_5: list[dict] = []
    seen_keys: set[tuple] = set()
    covered_jobs: set[str] = set()
    type_counts: dict[str, int] = {}

    def key(ins: dict) -> tuple:
        return (ins.get("related_job"), ins.get("related_phase"), ins.get("type"))

    def can_take(ins: dict) -> bool:
        return type_counts.get(ins.get("type", ""), 0) < MAX_PER_TYPE_IN_TOP5

    for ins in pm_field_sorted:
        job = ins.get("related_job")
        if job and job not in covered_jobs and key(ins) not in seen_keys and can_take(ins):
            top_5.append(ins)
            seen_keys.add(key(ins))
            type_counts[ins.get("type", "")] = type_counts.get(ins.get("type", ""), 0) + 1
            if job:
                covered_jobs.add(job)
            if len(top_5) >= 5:
                break

    if len(top_5) < 5:
        for ins in pm_field_sorted:
            if key(ins) in seen_keys:
                continue
            if not can_take(ins):
                continue
            top_5.append(ins)
            seen_keys.add(key(ins))
            type_counts[ins.get("type", "")] = type_counts.get(ins.get("type", ""), 0) + 1
            if len(top_5) >= 5:
                break

    return top_5


def compute_top_5_by_pm(ctx: RenderContext) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for pm in PM_NAMES:
        pm_field = [i for i in ctx.all_insights if i.get("related_pm") == pm and i.get("bucket", "field") == "field"]
        out[pm] = select_top_5(sorted(pm_field, key=insight_score, reverse=True))
    return out


def compute_tracking(ctx: RenderContext, top_5_by_pm: dict[str, list[dict]], persist: bool) -> dict:
    return commitment_tracker.update(ctx.today, top_5_by_pm, persist=persist)


# ---- Selection → phase keyword matcher (Fix 6) -----------------------
_SELECTION_PHASE_CACHE: list | None = None


def _selection_phase_mappings() -> list:
    """Lazy-load config/selection-to-phase.yaml mappings."""
    global _SELECTION_PHASE_CACHE
    if _SELECTION_PHASE_CACHE is not None:
        return _SELECTION_PHASE_CACHE
    import yaml
    path = ROOT / "config" / "selection-to-phase.yaml"
    if not path.exists():
        _SELECTION_PHASE_CACHE = []
        return _SELECTION_PHASE_CACHE
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _SELECTION_PHASE_CACHE = cfg.get("mappings") or []
    return _SELECTION_PHASE_CACHE


def _phase_for_item(item: dict) -> tuple[str | None, str | None]:
    """Returns (phase_code, phase_name) for the phase an item GATES,
    derived from action+update text using config/selection-to-phase.yaml.
    Falls back to item.related_phase if no keyword match."""
    text = " ".join(filter(None, [item.get("action"), item.get("update")])).lower()
    for entry in _selection_phase_mappings():
        for kw in entry.get("keywords", []):
            if kw.lower() in text:
                return entry["phase"], entry.get("phase_name")
    rp = item.get("related_phase") or item.get("target_phase")
    if rp:
        return rp, item.get("related_phase_name")
    return None, None


def _items_referencing_phase(items: list[dict], phase_code: str, phase_name: str | None,
                             job: str | None = None) -> list[dict]:
    """Returns items whose action/update text references this phase by code,
    name, or via the selection-phase mapping. Optionally filtered by job."""
    if not phase_code:
        return []
    out: list[dict] = []
    code_low = phase_code.lower()
    name_low = (phase_name or "").lower()
    for it in items:
        if job and it.get("job") != job:
            continue
        text = " ".join(filter(None, [it.get("action"), it.get("update")])).lower()
        # Direct phase code reference
        if code_low and code_low in text:
            out.append(it)
            continue
        # Phase name reference (only if name is distinctive — skip very short names)
        if name_low and len(name_low) >= 6 and name_low in text:
            out.append(it)
            continue
        # Selection-mapping match
        ip_code, _ = _phase_for_item(it)
        if ip_code == phase_code:
            out.append(it)
    # Dedup by id
    seen = set()
    deduped = []
    for it in out:
        if it.get("id") in seen:
            continue
        seen.add(it.get("id"))
        deduped.append(it)
    return deduped


# ---- Cross-PM aggregations for leadership templates ---------------------
def _aligned_master_data(ctx: RenderContext, tracking: dict) -> dict:
    """Cross-PM rollup aligned to the new section structure (Phase 12 Part B):
      - Section 1 — PPC% per PM and aggregate
      - Section 2 — 2-week execution red flags by job
      - Section 5 — open action item totals by category
      - Section 7 — financial exposure top-line
    """
    today_d = parse_iso(ctx.today)

    # PPC per PM
    ppc_per_pm = []
    pm_resolved = pm_committed = 0
    for pm in PM_NAMES:
        info = tracking.get("by_pm", {}).get(pm, {})
        last_w = info.get("last_week_count", 0)
        resolved = info.get("resolved_count", 0)
        ppc_per_pm.append({
            "pm": pm,
            "committed": last_w,
            "resolved": resolved,
            "carried": info.get("carried_count", 0),
            "stuck": info.get("stuck_count", 0),
            "ppc_pct": round(100 * resolved / last_w) if last_w else None,
        })
        pm_resolved += resolved
        pm_committed += last_w
    aggregate_ppc = round(100 * pm_resolved / pm_committed) if pm_committed else None

    # Execution 2wk red flags across all jobs (any column N)
    execution_red = []
    for pm in PM_NAMES:
        rows, _pred = _execution_2wk(ctx, pm, ctx.items_by_pm.get(pm, []))
        for jb in rows:
            for r in jb["rows"]:
                if r.get("any_red_flag"):
                    execution_red.append({
                        "pm": pm,
                        "job": jb["job"],
                        "phase_code": r["phase_code"],
                        "phase_name": r["phase_name"],
                        "sub": r["sub"],
                        "predecessor_complete": r["predecessor_complete"],
                        "blockers": r["blockers"],
                    })
    execution_red.sort(key=lambda x: (x["pm"], x["job"], x["phase_code"]))

    # Items totals by category across all PMs
    cat_totals = {c: 0 for c in ITEM_CATEGORIES}
    for pm in PM_NAMES:
        items = ctx.items_by_pm.get(pm, [])
        for it in items:
            if not _open_status(it.get("status")):
                continue
            cat = it.get("category") or "ADMIN"
            if cat in cat_totals:
                cat_totals[cat] += 1
            else:
                cat_totals["ADMIN"] += 1

    # Financial top-line: jobs with GP populated + open BUDGET item count
    fin_jobs = []
    open_budget = 0
    for pm in PM_NAMES:
        items = ctx.items_by_pm.get(pm, [])
        for it in items:
            if it.get("category") == "BUDGET" and _open_status(it.get("status")):
                open_budget += 1
        # Re-derive jobs from binder
        bp = BINDERS / PM_BINDER_FILES[pm]
        if bp.exists():
            for j in load_json(bp).get("jobs", []):
                gp = j.get("gp", "—")
                if gp and gp != "—":
                    fin_jobs.append({"pm": pm, "job": j.get("name"), "gp": gp,
                                     "targetCO": j.get("targetCO", "—"), "status": j.get("status")})

    return {
        "ppc_per_pm": ppc_per_pm,
        "ppc_aggregate": aggregate_ppc,
        "ppc_committed_total": pm_committed,
        "ppc_resolved_total": pm_resolved,
        "execution_red_flags": execution_red,
        "items_by_category_totals": cat_totals,
        "financial_jobs": fin_jobs,
        "open_budget_items": open_budget,
    }


def _aligned_executive_data(ctx: RenderContext, tracking: dict) -> dict:
    """Exception-only — what's on fire. Pulls from execution_red_flags,
    overdue selections (across PMs), and any flagged BUDGET items."""
    today_d = parse_iso(ctx.today)

    # Execution blockers — same as master but capped to top 8.
    # Bug 5 (wmp25) §2 cleanup: when a row's only red signal is "predecessor
    # missing" AND the job has moved past every missing predecessor's stage
    # AND the row's phase has been "active" longer than
    # phase_active_suppress_days, the missing predecessor is almost certainly
    # an old/unmatched log entry (same data-attribution issue Bug 4 cleaned up
    # on the Active phases line) — not a real blocker. Suppress those rows
    # while keeping legitimate predecessor-missing on actively-current jobs
    # (e.g. Clark · Slab Prep at stage 2 with missing 2.5/2.6).
    suppress_days = (ctx.thresholds or {}).get("phase_active_suppress_days", 90)

    def _stage_of(code: str) -> int | None:
        try:
            return int(str(code).split(".")[0])
        except (ValueError, AttributeError):
            return None

    execution_blockers = []
    for pm in PM_NAMES:
        rows, _pred = _execution_2wk(ctx, pm, ctx.items_by_pm.get(pm, []))
        for jb in rows:
            cur_stage = jb.get("current_stage")
            for r in jb["rows"]:
                if not r.get("any_red_flag"):
                    continue
                progress = r.get("progress") or {}
                pred_missing = r.get("predecessor_missing") or []
                only_pred_missing = (
                    r.get("predecessor_complete") == "N"
                    and not r.get("blockers")
                    and progress.get("flag") != "red"
                )
                days_active = progress.get("days_active") or 0
                # Case A: explicit "predecessor missing" with all missing
                # predecessors strictly upstream of current_stage and the row
                # has been "active" longer than suppress_days.
                if (only_pred_missing and pred_missing and cur_stage is not None):
                    pred_stages = [_stage_of(p) for p in pred_missing]
                    pred_stages = [s for s in pred_stages if s is not None]
                    if (pred_stages
                        and all(s < cur_stage for s in pred_stages)
                        and days_active > suppress_days):
                        continue
                # Case B: pre-data noise — row is upstream of current_stage,
                # no real blockers, no concrete missing predecessors listed
                # (gap_codes path renders an empty "predecessor missing:"
                # string), and days_active exceeds the threshold. Same
                # data-attribution concept.
                row_stage = r.get("stage")
                if (cur_stage is not None
                    and row_stage is not None
                    and row_stage < cur_stage
                    and not r.get("blockers")
                    and not pred_missing
                    and days_active > suppress_days):
                    continue
                # Case C: closeout-stage same-stage predecessor (wmp27).
                # Punch Repairs (15.2) appearing to start before Punch Walk
                # (15.1) on a job already classified as Closeout is a
                # logging-gap artifact, not a real sequencing issue. Tight
                # trigger: cur_stage == 15 AND row_stage == 15 AND every
                # listed missing predecessor is also at stage 15.
                if (cur_stage == 15
                    and row_stage == 15
                    and pred_missing
                    and all(_stage_of(p) == 15 for p in pred_missing)):
                    continue
                execution_blockers.append({
                    "pm": pm.split()[0], "job": jb["job"],
                    "phase": f"{r['phase_name']} ({r['phase_code']})",
                    "sub": r["sub"],
                    "blockers": r["blockers"] or
                                f"predecessor missing: {', '.join(pred_missing)}",
                })
    execution_blockers = execution_blockers[:8]

    # Overdue selections cross-PM. Bug 5 (wmp25) §6: rows ≥ stale_days
    # overdue get a `stale=True` flag so the template can render an
    # escalation marker. Sort order unchanged.
    stale_days = (ctx.thresholds or {}).get("overdue_selection_stale_days", 14)
    overdue_sel = []
    for pm in PM_NAMES:
        items = ctx.items_by_pm.get(pm, [])
        for it in items:
            if it.get("category") != "SELECTION" or not _open_status(it.get("status")):
                continue
            n = _normalize_item(it, today_d)
            if n.get("days_to_due") is not None and n["days_to_due"] < 0:
                n["pm"] = pm.split()[0]
                n["stale"] = (-n["days_to_due"]) >= stale_days
                overdue_sel.append(n)
    overdue_sel.sort(key=lambda x: x.get("days_to_due", 0))
    overdue_sel = overdue_sel[:8]

    # Financial flags: jobs with status=red, plus any open URGENT BUDGET items.
    # Bug 5 (wmp25) §7: gated behind financial_exposure_enabled config flag
    # until Phase 13 contract integration provides real GP / contract dollars.
    # While disabled, the flags are still computed (so the data path is
    # exercised) but the bundle reports them as suppressed and the template
    # renders a placeholder line; flipping the flag restores the existing
    # rendering with no further code change.
    fin_enabled = bool((ctx.thresholds or {}).get("financial_exposure_enabled", False))
    fin_flags = []
    for pm in PM_NAMES:
        bp = BINDERS / PM_BINDER_FILES[pm]
        if bp.exists():
            for j in load_json(bp).get("jobs", []):
                if (j.get("status") or "").lower() in ("red", "amber"):
                    fin_flags.append({
                        "pm": pm.split()[0], "job": j.get("name"),
                        "status": j.get("status"), "gp": j.get("gp", "—"),
                        "targetCO": j.get("targetCO", "—"),
                    })
        for it in ctx.items_by_pm.get(pm, []):
            if it.get("category") == "BUDGET" and _open_status(it.get("status")):
                if (it.get("priority") or "").upper() == "URGENT":
                    fin_flags.append({
                        "pm": pm.split()[0], "job": it.get("job"),
                        "status": "URGENT BUDGET ITEM", "gp": "—",
                        "action": _word_truncate(it.get("action") or "", 80),
                    })

    return {
        "execution_blockers": execution_blockers,
        "overdue_selections": overdue_sel,
        "financial_flags": fin_flags[:6] if fin_enabled else [],
        "financial_exposure_disabled": not fin_enabled,
    }


def _aligned_precon_data(ctx: RenderContext) -> dict:
    """Forward-looking — 4-week coordination + 8-week procurement/selection
    aggregated across all PMs."""
    today_d = parse_iso(ctx.today)

    coord = []
    for pm in PM_NAMES:
        rows = _coordination_4wk(ctx, pm)
        for jb in rows:
            for r in jb["rows"]:
                coord.append({
                    "pm": pm.split()[0], "job": jb["job"],
                    "phase": f"{r['phase_name']} ({r['phase_code']})",
                    "sub": r.get("sub") or "—",
                    "needs": r["needs_confirmation"],
                })
    coord = coord[:15]

    proc_items = []
    sel_items = []
    for pm in PM_NAMES:
        items = ctx.items_by_pm.get(pm, [])
        ps = _procurement_8wk(items, today_d)
        for i in ps["procurement_items"][:6]:
            i["pm"] = pm.split()[0]
            proc_items.append(i)
        for i in ps["selection_items"][:6]:
            i["pm"] = pm.split()[0]
            sel_items.append(i)

    return {
        "coordination": coord,
        "procurement": proc_items,
        "selections": sel_items,
    }


def build_master_bundle(ctx: RenderContext, tracking: dict) -> dict:
    field = sorted(
        [i for i in ctx.all_insights if i.get("bucket", "field") == "field"],
        key=insight_score,
        reverse=True,
    )
    top10: list[dict] = []
    type_caps: dict[str, int] = {}
    for ins in field:
        t = ins.get("type", "")
        if type_caps.get(t, 0) >= 4:
            continue
        top10.append(ins)
        type_caps[t] = type_caps.get(t, 0) + 1
        if len(top10) >= 10:
            break

    pm_summary = []
    must_discuss_total = 0
    open_actions_total = 0
    stale_total = 0
    for pm, jobs in ctx.pm_to_jobs.items():
        items = ctx.items_by_pm.get(pm, [])
        open_items = [i for i in items if i.get("status") not in ("COMPLETE", "DISMISSED")]
        stale = sum(1 for i in open_items if (i.get("days_open") or 0) > 14)
        md = tracking.get("by_pm", {}).get(pm, {}).get("this_week_count", 0)
        must_discuss_total += md
        open_actions_total += len(open_items)
        stale_total += stale
        pm_summary.append({
            "pm": pm,
            "jobs": jobs,
            "must_discuss": md,
            "open_actions": len(open_items),
            "stale": stale,
        })

    instances = ctx.phase3["instances"]["instances"]
    excluded = _load_excluded()
    active_jobs = set()
    ongoing_count = 0
    for ins in instances:
        if ins["job"] in excluded:
            continue
        if ins.get("status") in ("ongoing", "complete"):
            active_jobs.add(ins["job"])
        if ins.get("status") == "ongoing":
            ongoing_count += 1

    flagged_jobs = set()
    for ins in field:
        if ins.get("severity") == "critical":
            flagged_jobs.add(ins.get("related_job"))

    by_pm = tracking.get("by_pm", {})
    last_week_total = sum(info.get("last_week_count", 0) for info in by_pm.values())
    resolved_total = sum(info.get("resolved_count", 0) for info in by_pm.values())
    carried_total = sum(info.get("carried_count", 0) for info in by_pm.values())
    stuck_total = sum(info.get("stuck_count", 0) for info in by_pm.values())
    this_week_total = sum(info.get("this_week_count", 0) for info in by_pm.values())

    return {
        "today": ctx.today,
        "totals": {
            "active_jobs": len(active_jobs),
            "pms": len(ctx.pm_to_jobs),
            "ongoing_phases": ongoing_count,
            "flagged_jobs": len(flagged_jobs),
            "must_discuss_total": must_discuss_total,
            "open_actions_total": open_actions_total,
            "stale_total": stale_total,
        },
        "red_flags": top10,
        "accountability_rollup": {
            "this_week": tracking.get("this_week"),
            "last_week": tracking.get("last_week"),
            "last_week_total": last_week_total,
            "resolved_total": resolved_total,
            "carried_total": carried_total,
            "stuck_total": stuck_total,
            "this_week_total": this_week_total,
        },
        "pm_summary": pm_summary,
        "aligned": _aligned_master_data(ctx, tracking),  # Phase 12 Part B
    }


def build_executive_bundle(ctx: RenderContext, tracking: dict) -> dict:
    field_critical = sorted(
        [i for i in ctx.all_insights if i.get("bucket", "field") == "field" and i.get("severity") == "critical"],
        key=insight_score,
        reverse=True,
    )

    red_this_week = []
    seen_jobs: set[str] = set()
    for ins in field_critical:
        job = ins.get("related_job")
        if not job or job in seen_jobs:
            continue
        seen_jobs.add(job)
        if ins["type"] == "sequencing_risk":
            label = f"Sequencing risk · {ins.get('related_phase', '')}"
            detail = ins.get("summary_line", ins.get("message", ""))
        elif ins["type"] == "sub_drift":
            sub = (ins.get("related_sub") or "").split(",")[0].split(" LLC")[0].strip()
            label = f"Sub drift · {sub}"
            detail = ins.get("summary_line", ins.get("message", ""))
        else:
            label = ins["type"].replace("_", " ").title()
            detail = ins.get("summary_line", ins.get("message", ""))
        red_this_week.append({"job": job.upper(), "label": label, "detail": detail or ""})
        if len(red_this_week) >= 3:
            break

    job_critical: dict = {}
    for ins in ctx.all_insights:
        if ins.get("bucket", "field") != "field":
            continue
        job = ins.get("related_job")
        if not job:
            continue
        if ins.get("severity") == "critical":
            job_critical.setdefault(job, 0)
            job_critical[job] += 1

    # Trajectory denominator must match the master banner's "ACTIVE JOBS"
    # count (jobs with ongoing/complete phase instances, minus excluded).
    # Previously this also included PM-binder jobs without any phase
    # instances yet (e.g., a new job with open items but no field activity)
    # via the "unknown" bucket, which inflated the trajectory total to N+1
    # and made the executive's "Insufficient data: 1 of 12" disagree with
    # master's "11 ACTIVE JOBS". Master's definition is the source of truth.
    instances = ctx.phase3["instances"]["instances"]
    excluded = _load_excluded()
    active_set: set[str] = set()
    for ins in instances:
        if ins.get("job") in excluded:
            continue
        if ins.get("status") in ("ongoing", "complete"):
            active_set.add(ins["job"])

    flagged = sum(1 for j in active_set if job_critical.get(j, 0) > 0)
    on_track = max(0, len(active_set) - flagged)
    unknown = 0  # jobs without phase data are not "active" by master's definition

    trajectory = {"on_track": on_track, "flagged": flagged, "unknown": unknown}

    recovery = []
    last_week_red_jobs = set()
    state = commitment_tracker.load_commitments()
    weeks = state.get("weeks", [])
    if len(weeks) >= 2:
        prev = weeks[-2]
        for pm, info in (prev.get("by_pm") or {}).items():
            for it in (info.get("must_discuss") or []):
                if it.get("severity") == "critical" and it.get("related_job"):
                    last_week_red_jobs.add(it["related_job"])
        current_critical_jobs = {ins.get("related_job") for ins in field_critical if ins.get("related_job")}
        for job in last_week_red_jobs:
            if job not in current_critical_jobs:
                recovery.append({"job": job.upper(), "what": "Critical signal cleared", "verdict": "closed", "verdict_class": "closed"})
            else:
                cnt_then = sum(1 for it in (prev.get("by_pm") or {}).values()
                               for c in it.get("must_discuss") or []
                               if c.get("related_job") == job and c.get("severity") == "critical")
                cnt_now = sum(1 for ins in field_critical if ins.get("related_job") == job)
                if cnt_now < cnt_then:
                    recovery.append({"job": job.upper(), "what": "Improving", "verdict": "improved", "verdict_class": "improved"})
                elif cnt_now > cnt_then:
                    recovery.append({"job": job.upper(), "what": "Getting worse", "verdict": "worse", "verdict_class": "worse"})
                else:
                    recovery.append({"job": job.upper(), "what": "Same severity", "verdict": "same", "verdict_class": "same"})

    decisions = []
    stuck_items = []
    for pm, info in tracking.get("by_pm", {}).items():
        for it in info.get("stuck_items", []):
            stuck_items.append((pm, it))
    for pm, it in stuck_items[:2]:
        job = (it.get("related_job") or "").upper()
        decisions.append({
            "question": f"{job}: escalate stuck item to Andrew or hard close?",
            "context": f"{it.get('title', '')} · stuck {it.get('streak_weeks', 0)} weeks"
        })
    if len(decisions) < 2:
        for ins in field_critical:
            if ins["type"] == "sub_drift":
                sub = (ins.get("related_sub") or "").split(",")[0].split(" LLC")[0].strip()
                job = (ins.get("related_job") or "").upper()
                decisions.append({
                    "question": f"{job}: replace {sub} or stay course?",
                    "context": ins.get("summary_line", ins.get("message", ""))
                })
                if len(decisions) >= 2:
                    break
    # wmp27 — Option C+E: replace the prior sequencing_risk fallback (which
    # surfaced PM-level decisions to Lee) with a scored filter over Lee-owned
    # action items. Decision-shape signals (CO authorizations, exec
    # categories, decision verbs in the action text, urgency) earn points;
    # PM-execution prefixes (schedule/coordinate/confirm timing/follow up on)
    # are hard-excluded even if Lee is the listed owner. Weights and the
    # threshold live in config/thresholds.yaml.decisions_needed so they
    # stay tunable without code changes. Total decisions cap at 4.
    MAX_DECISIONS = 4
    if len(decisions) < MAX_DECISIONS:
        dn_cfg = (ctx.thresholds or {}).get("decisions_needed", {}) or {}
        threshold = dn_cfg.get("score_threshold", 3)
        w_co_invoice = dn_cfg.get("weight_co_invoice", 2)
        w_exec_cat = dn_cfg.get("weight_exec_category", 2)
        w_verb = dn_cfg.get("weight_decision_verb", 2)
        w_urgent = dn_cfg.get("weight_urgent", 1)
        EXEC_CATEGORIES = {"BUDGET", "CLIENT", "SUB-TRADE"}
        DECISION_VERB_RE = re.compile(
            r"\b(issue CO|CO to|fire |replace sub|escalate|one-tier-up|approve|present .*to.*homeowner|sign-off)\b",
            re.IGNORECASE,
        )
        HARD_EXCLUDE_RE = re.compile(
            r"^(schedule|coordinate|confirm timing|follow up on)\b",
            re.IGNORECASE,
        )
        scored: list[tuple[int, str, dict]] = []
        for pm in PM_NAMES:
            for it in ctx.items_by_pm.get(pm, []):
                if not _open_status(it.get("status")):
                    continue
                owner = (it.get("owner") or "").lower()
                if "lee" not in owner:
                    continue
                action = (it.get("action") or "").strip()
                if HARD_EXCLUDE_RE.match(action):
                    continue
                score = 0
                if it.get("type") == "CO_INVOICE":
                    score += w_co_invoice
                if it.get("category") in EXEC_CATEGORIES:
                    score += w_exec_cat
                if action and DECISION_VERB_RE.search(action):
                    score += w_verb
                if (it.get("priority") or "").upper() == "URGENT":
                    score += w_urgent
                if score >= threshold:
                    scored.append((score, pm, it))
        # Sort by score desc, then priority (URGENT > HIGH > NORMAL > others)
        _PRI_ORDER = {"URGENT": 0, "HIGH": 1, "NORMAL": 2}
        scored.sort(key=lambda t: (
            -t[0],
            _PRI_ORDER.get((t[2].get("priority") or "").upper(), 3),
        ))
        for score, pm, it in scored:
            if len(decisions) >= MAX_DECISIONS:
                break
            job = (it.get("job") or "").upper()
            action_text = (it.get("action") or "").strip()
            question_body = _word_truncate(action_text, 90) if action_text else "Action item"
            decisions.append({
                "question": f"{job}: {question_body}" if job else question_body,
                "context": f"{it.get('id', '')} · {it.get('priority', 'NORMAL')} · score {score}",
            })

    return {
        "today": ctx.today,
        "red_this_week": red_this_week,
        "trajectory": trajectory,
        "recovery": recovery,
        "decisions": decisions,
        "aligned": _aligned_executive_data(ctx, tracking),  # Phase 12 Part B
    }


def build_preconstruction_bundle(ctx: RenderContext) -> dict:
    job_stages = ctx.phase3["job_stages"]["jobs"]
    taxonomy = {p["code"]: p for p in (ctx.phase3["taxonomy"].get("phases") or [])}
    log_keys = list(ctx.daily_by_job.keys())
    excluded = _load_excluded()

    stage_names = {}
    for code, p in taxonomy.items():
        stage_names[p["stage"]] = p.get("stage_name", "")

    upcoming_jobs = []
    sub_gaps = []
    for short, js in job_stages.items():
        if short in excluded:
            continue
        cur_stage = js.get("current_stage")
        if cur_stage is None or cur_stage > 1:
            continue
        log_key = job_log_key(short, log_keys)
        logs = ctx.daily_by_job.get(log_key, []) if log_key else []
        ever_logged_subs: set[str] = set()
        for log in logs:
            cc = log.get("crews_clean")
            if isinstance(cc, list):
                for s in cc:
                    if s:
                        ever_logged_subs.add(s)

        subs_needed: set[str] = set()
        for code, p in taxonomy.items():
            if cur_stage <= p.get("stage", 99) <= cur_stage + 3:
                for ts in (p.get("typical_subs") or []):
                    if ts.get("sub"):
                        subs_needed.add(ts["sub"])

        upcoming_jobs.append({
            "name": short,
            "next_stage_name": stage_names.get((cur_stage or 0) + 1, "Site Work"),
            "address": "",
            "subs_locked": len(subs_needed & ever_logged_subs),
            "subs_total": len(subs_needed),
        })

        next_stage = (cur_stage or 0) + 1
        for code, p in taxonomy.items():
            if p.get("stage") != next_stage:
                continue
            needed = [ts["sub"] for ts in (p.get("typical_subs") or []) if ts.get("sub")]
            missing = [s for s in needed if s not in ever_logged_subs]
            if missing:
                sub_gaps.append({
                    "job": short,
                    "phase_code": code,
                    "phase_name": p.get("name", ""),
                    "needed_subs": [s for s in missing[:4]],
                    "stage": next_stage,
                })

    EST_VERBS = re.compile(
        r"\b(quote|propos|estimat|pricing|scope|takeoff|takeoff|"
        r"co[-\s]?\d|change\s+order|pcco|select\w*|spec\s*ed|spec\b|"
        r"contract|sub-?contract|bid|allowance|owner\s+co)\w*",
        re.IGNORECASE,
    )
    estimating_actions = []
    for pm, items in ctx.items_by_pm.items():
        for it in items:
            if it.get("status") in ("COMPLETE", "DISMISSED"):
                continue
            text = " ".join(filter(None, [it.get("action"), it.get("update")]))
            if not EST_VERBS.search(text):
                continue
            estimating_actions.append({
                "id": it["id"],
                "job": it.get("job", ""),
                "action_short": shorten_action(it.get("action")),
                "priority": it.get("priority", "NORMAL"),
                "days_open": it.get("days_open"),
            })

    PRI = {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "MEDIUM": 2, "LOW": 3}
    estimating_actions.sort(key=lambda x: (PRI.get(x.get("priority", "NORMAL"), 4), -(x.get("days_open") or 0)))

    return {
        "today": ctx.today,
        "upcoming_jobs": upcoming_jobs,
        "sub_gaps": sub_gaps,
        "estimating_actions": estimating_actions,
        "aligned": _aligned_precon_data(ctx),  # Phase 12 Part B
    }


def _load_excluded() -> set:
    excl_yaml = ROOT / "config" / "excluded_jobs.yaml"
    if not excl_yaml.exists():
        return set()
    import yaml
    cfg = yaml.safe_load(excl_yaml.read_text(encoding="utf-8")) or {}
    return {e["job"] for e in cfg.get("excluded", []) if e.get("job")}


# ---- Template substitution ----------------------------------------------
def render_template(template_path: Path, bundle: dict) -> str:
    tpl = template_path.read_text(encoding="utf-8")
    return tpl.replace("__SI_DATA_BUNDLE__", json.dumps(bundle, separators=(",", ":")))


# ---- Edge headless PDF ---------------------------------------------------
def find_edge() -> str | None:
    candidates = [
        os.environ.get("EDGE_BINARY"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _rewrite_asset_paths_for_file_url(html: str) -> str:
    """Templates reference `../assets/...` or `../../assets/...` (relative
    paths that work when served over HTTP from /meeting-prep/...). For PDF
    generation we write the HTML to a temp dir and Edge loads it via file://;
    relative paths there resolve outside the project tree and 404. Rewrite
    them to absolute file:// URLs to the real assets directory so Edge can
    load styles, fonts, and components.js."""
    assets_dir = MONDAY_BINDER / "assets"
    file_prefix = "file:///" + str(assets_dir.resolve()).replace("\\", "/")
    html = html.replace('"../../assets/', f'"{file_prefix}/')
    html = html.replace('"../assets/', f'"{file_prefix}/')
    html = html.replace("'../../assets/", f"'{file_prefix}/")
    html = html.replace("'../assets/", f"'{file_prefix}/")
    return html


def html_to_pdf_bytes(html: str, edge_path: str | None = None, timeout: int = 60) -> bytes:
    """Render HTML to PDF bytes via Edge headless. Writes a temp HTML file
    so Edge can load it via file://, prints to a temp PDF, reads bytes,
    cleans up. Raises on failure.

    --virtual-time-budget=4000 gives Edge 4 seconds of fast-forwarded
    virtual time to settle JS-driven rendering before printing. Without
    this, Edge prints the page within ~100ms and our templates (which
    render synchronously from a JSON bundle inside <script id='mp-data'>)
    sometimes get printed before the inline JS finishes drawing the DOM.
    The 4s budget is fast-forward, not wall-clock — Edge still exits
    quickly, just after the simulated time elapses inside the page.
    """
    edge = edge_path or find_edge()
    if not edge:
        raise RuntimeError("Edge not found at standard install paths. Set EDGE_BINARY env var.")

    rewritten = _rewrite_asset_paths_for_file_url(html)

    with tempfile.TemporaryDirectory(prefix="rb_pdf_") as tmpdir:
        tmp_html = Path(tmpdir) / "page.html"
        tmp_pdf = Path(tmpdir) / "page.pdf"
        tmp_html.write_text(rewritten, encoding="utf-8")
        src_url = "file:///" + str(tmp_html.resolve()).replace("\\", "/")

        res = subprocess.run(
            [
                edge,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                "--no-first-run",
                "--disable-extensions",
                "--virtual-time-budget=4000",
                f"--print-to-pdf={tmp_pdf}",
                src_url,
            ],
            capture_output=True,
            timeout=timeout,
        )
        if not tmp_pdf.exists() or tmp_pdf.stat().st_size == 0:
            raise RuntimeError(
                f"Edge --print-to-pdf produced no output (rc={res.returncode}). "
                f"stderr: {res.stderr[:500].decode('utf-8', errors='replace')}"
            )
        return tmp_pdf.read_bytes()


# ---- Top-level convenience: render a single page by name ----------------
PAGE_REGISTRY = {
    "master": (MASTER_TEMPLATE, "build_master_bundle"),
    "executive": (EXECUTIVE_TEMPLATE, "build_executive_bundle"),
    "preconstruction": (PRECON_TEMPLATE, "build_preconstruction_bundle"),
}


def render_master(ctx: RenderContext, tracking: dict) -> str:
    return render_template(MASTER_TEMPLATE, build_master_bundle(ctx, tracking))


def render_executive(ctx: RenderContext, tracking: dict) -> str:
    return render_template(EXECUTIVE_TEMPLATE, build_executive_bundle(ctx, tracking))


def render_preconstruction(ctx: RenderContext) -> str:
    return render_template(PRECON_TEMPLATE, build_preconstruction_bundle(ctx))


# ---- Phase 12 Part B — Production meeting bundles ----------------------
def _open_status(s: str | None) -> bool:
    return (s or "").upper() in ("NOT_STARTED", "IN_PROGRESS", "BLOCKED", "OPEN", "IN PROGRESS")


def _safe_due(item: dict) -> date | None:
    return parse_iso(item.get("due"))


def _days_open(item: dict, today: date | None) -> int:
    if not today:
        return item.get("days_open") or 0
    opened = parse_iso(item.get("opened"))
    if not opened:
        return item.get("days_open") or 0
    return max(0, (today - opened).days)


def _urgency_label(days_to_due: int | None, status: str | None) -> dict:
    """Returns {label, kind} where kind ∈ {overdue, today, future, none}.
    Open items past due render OVERDUE; closed items keep their final state."""
    s = (status or "").upper()
    if s in ("COMPLETE", "DUPLICATE_MERGED", "DISMISSED"):
        return {"label": "", "kind": "none"}
    if days_to_due is None:
        return {"label": "no date", "kind": "none"}
    if days_to_due < 0:
        return {"label": f"OVERDUE {-days_to_due}d", "kind": "overdue"}
    if days_to_due == 0:
        return {"label": "DUE TODAY", "kind": "today"}
    return {"label": f"{days_to_due}d", "kind": "future"}


def _canonical_section_for_item(item: dict, days_to_due: int | None) -> str:
    """Phase 13 polish (wmp21 Fix 1) — assign each item ONE canonical
    section so other appearances render as compact refs.

    Order of precedence:
      "escalations"      — URGENT priority + days_open > 14 (true escalations)
      "selections"       — category=SELECTION (the §6 list is primary)
      "active_this_week" — category=PROCUREMENT due in [-7, 7]d (§4a)
      "by_category"      — everything else (§5 by category bucket)
    """
    pri = (item.get("priority") or "").upper()
    cat = item.get("category")
    days_open = item.get("days_open") or 0
    if pri == "URGENT" and days_open > 14:
        return "escalations"
    if cat == "SELECTION":
        return "selections"
    if cat == "PROCUREMENT" and days_to_due is not None and -7 <= days_to_due <= 7:
        return "active_this_week"
    return "by_category"


def _normalize_item(item: dict, today: date | None) -> dict:
    """Compute display fields the templates need without mutating source data.

    `today` is used for `days_open` (item age relative to snapshot date so
    PPC/staleness stays consistent with the data layer). Urgency labels
    instead use `date.today()` so OVERDUE/DUE TODAY reflect the actual
    calendar — mid-week renders shouldn't show items as "due in 2 days"
    when they were already due last Friday."""
    out = dict(item)
    out["days_open"] = _days_open(item, today)
    due = _safe_due(item)
    cal_today = date.today()
    if due:
        out["days_to_due"] = (due - cal_today).days
    else:
        out["days_to_due"] = None
    out["category"] = item.get("category") or "ADMIN"
    out["source"] = item.get("source") or "transcript"
    out["category_review"] = bool(item.get("_category_review"))
    # Phase 12 brevity — pre-compute headline/detail/update_excerpt so
    # templates don't have to do string surgery in JS. Source action
    # never modified.
    concise = render_item_concise(item)
    out["headline"] = concise["headline"]
    out["detail"] = concise["detail"]
    out["update_excerpt"] = concise["update_excerpt"]
    # Phase 12 polish — urgency label feeds the right-aligned date column
    out["urgency"] = _urgency_label(out["days_to_due"], item.get("status"))
    # Fix 1 (wmp21) — canonical section so the template only renders the
    # full card at the canonical home and emits compact refs elsewhere.
    out["canonical_section"] = _canonical_section_for_item(out, out["days_to_due"])
    return out


# Phase 12 polish — concise headline + detail split for templates.
_OWNER_RE = re.compile(r"^([A-Za-z][A-Za-z/\.\s]*?)\s+to\s+(.+)$", re.IGNORECASE)
# Natural breaks: ";", " — ", " -- ", " for ", " with ", " per ", " on the ",
# " so that ". Note ";" doesn't require leading whitespace (real text writes
# "status; conduit", not "status ; conduit").
_NATURAL_BREAK_RE = re.compile(
    r"(?:\s*[—;]\s+|\s+--\s+|\s+(?:for|with|per|on\s+the|so\s+that)\s+)",
    re.IGNORECASE,
)
# "by Wed 4/29" / "by Fri 5/1" / "by 4/30" — stripped from verb phrase
# before headline extraction so the date column doesn't duplicate it.
_BY_DATE_RE = re.compile(
    r"\s+by\s+(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[A-Za-z]*\s+)?\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?",
    re.IGNORECASE,
)
_HEADLINE_MAX = 80   # was 60; raised per wmp17 to allow cleaner full-clause headlines
_HEADLINE_MIN_FLOOR = 30  # if natural break would cut shorter than this we
                          # fall back to showing the full action instead


def render_item_concise(item: dict) -> dict:
    """Split an item's `action` into:
      - headline: short owner-first summary (~80 chars, ends at a natural
        break point when possible). Never cut mid-clause.
      - detail: the remainder of the action sentence (Line 2 — full prose).
        Excludes any leading "by [date]" since due is rendered separately.
      - update_excerpt: the binder's update field (Line 3 — italicized).

    Falls back to showing the full action as the headline (with no detail)
    when no clean natural break fits inside _HEADLINE_MAX. The kickoff
    explicitly prefers a slightly-longer headline over an awkwardly
    truncated one.

    Pure rendering transform — never mutates the source action.
    """
    action = (item.get("action") or "").strip()
    update = (item.get("update") or "").strip()

    if not action:
        return {"headline": "", "detail": "", "update_excerpt": update}

    m = _OWNER_RE.match(action)
    if m:
        display_owner = m.group(1).strip()
        verb_phrase = m.group(2).strip()
    else:
        display_owner = (item.get("owner") or "").strip()
        verb_phrase = action

    # Strip "by [date]" patterns from the verb phrase BEFORE headline
    # extraction — the date column already shows the due date, so dropping
    # it here lets the headline carry meaningful content.
    headline_source = _BY_DATE_RE.sub("", verb_phrase).strip()
    headline_source = re.sub(r"\s{2,}", " ", headline_source)  # collapse double-spaces

    truncated = None
    cut_at = None

    # Look for the LAST natural break that still fits inside _HEADLINE_MAX —
    # this lets us land at the longest sensible clause boundary rather than
    # the first one (which often cuts a sentence too short).
    last_break = None
    for m_nb in _NATURAL_BREAK_RE.finditer(headline_source[: _HEADLINE_MAX + 5]):
        if m_nb.start() <= _HEADLINE_MAX:
            last_break = m_nb
        else:
            break
    if last_break and last_break.start() >= _HEADLINE_MIN_FLOOR:
        cut_at = last_break.start()
        truncated = headline_source[:cut_at].rstrip(" ,;-—.")

    # No good natural break: if the cleaned phrase is short enough to fit
    # anyway, use the whole thing. Otherwise fall back to the FULL cleaned
    # phrase (no ellipsis) — kickoff explicitly prefers a longer clean
    # headline over an awkwardly truncated one.
    if truncated is None:
        truncated = headline_source
        cut_at = len(headline_source)

    headline = f"{display_owner} · {truncated}" if display_owner else truncated

    # Line 2 — remainder of the verb phrase (after the cut point in the
    # CLEANED source, then re-checked against the original to surface
    # context that wasn't promoted to the headline).
    detail = ""
    if cut_at is not None and cut_at < len(headline_source):
        tail = headline_source[cut_at:].lstrip(" ,;-—")
        tail = _BY_DATE_RE.sub("", tail).strip()
        if tail and len(tail) > 4:
            detail = tail

    return {"headline": headline, "detail": detail, "update_excerpt": update}


def get_recently_completed(ctx: "RenderContext", pm: str, since_days: int = 7) -> dict:
    """Items where status=COMPLETE and the close date is within the last
    `since_days` days, grouped by category. Falls back to binder.meta.date
    when an item lacks an explicit close_date.

    Returns: dict[category] -> list[item], each item with `close_date` set.
    """
    today = parse_iso(ctx.today)
    if not today:
        return {}

    bp = BINDERS / PM_BINDER_FILES[pm]
    if not bp.exists():
        return {}
    binder = load_json(bp)
    meta_date = parse_iso(binder.get("meta", {}).get("date"))

    items = ctx.items_by_pm.get(pm, [])
    cutoff = today - timedelta(days=since_days)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        if (it.get("status") or "").upper() != "COMPLETE":
            continue
        close_d = parse_iso(it.get("close_date") or it.get("closed_date"))
        if not close_d:
            close_d = meta_date
        if not close_d or close_d < cutoff or close_d > today:
            continue
        n = _normalize_item(it, today)
        n["close_date"] = close_d.isoformat()
        grouped[n.get("category") or "ADMIN"].append(n)

    for cat in grouped:
        grouped[cat].sort(key=lambda x: x.get("close_date") or "", reverse=True)
    return dict(grouped)


def _ppc_for_pm(ctx: RenderContext, pm: str, tracking: dict, today: date | None) -> dict:
    """Compute Last Week PPC% — items committed last meeting vs. completed
    this week. Uses tracking['by_pm'][pm] for the resolved/carried/stuck
    breakdown plus the binder for the underlying item statuses."""
    info = tracking.get("by_pm", {}).get(pm, {})
    last_week_count = info.get("last_week_count", 0)
    resolved = info.get("resolved_count", 0)
    carried = info.get("carried_count", 0)
    stuck = info.get("stuck_count", 0)

    if last_week_count == 0:
        return {
            "first_run": True,
            "iso_week": tracking.get("this_week"),
            "committed_count": 0,
            "completed_count": 0,
            "ppc_pct": None,
            "miss_reasons": [],
            "summary": "Baseline week — no prior plan to compare.",
        }

    ppc_pct = round(100 * resolved / last_week_count) if last_week_count else None
    miss = []
    for c in info.get("last_week", []):
        if c.get("current_status") in ("carried", "stuck"):
            miss.append({
                "title": c.get("title") or c.get("type") or "(item)",
                "type": c.get("type"),
                "severity": c.get("severity"),
                "current_status": c.get("current_status"),
                "related_job": c.get("related_job"),
                "streak": c.get("streak_weeks"),
            })

    return {
        "first_run": False,
        "iso_week": tracking.get("last_week"),
        "committed_count": last_week_count,
        "completed_count": resolved,
        "carried_count": carried,
        "stuck_count": stuck,
        "ppc_pct": ppc_pct,
        "miss_reasons": miss,
        "summary": f"Last week: {resolved}/{last_week_count} committed items closed "
                   f"({ppc_pct}%). {carried} carried, {stuck} stuck.",
    }


def _phase_lookup(ctx: RenderContext) -> dict:
    return {p["code"]: p for p in (ctx.phase3["taxonomy"].get("phases") or [])}


_IN_HOUSE_PHASES_CACHE: dict | None = None


def _in_house_phases() -> dict:
    """Loads config/in-house-phases.yaml lazily. Maps phase_code → {sub, note}."""
    global _IN_HOUSE_PHASES_CACHE
    if _IN_HOUSE_PHASES_CACHE is not None:
        return _IN_HOUSE_PHASES_CACHE
    import yaml
    path = ROOT / "config" / "in-house-phases.yaml"
    if not path.exists():
        _IN_HOUSE_PHASES_CACHE = {}
        return _IN_HOUSE_PHASES_CACHE
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _IN_HOUSE_PHASES_CACHE = cfg.get("phases") or {}
    return _IN_HOUSE_PHASES_CACHE


def _typical_sub_for_phase(taxonomy_phase: dict | None, phase_code: str | None = None) -> str | None:
    """Returns the typical sub for a phase. For phases Ross Built handles
    in-house (config/in-house-phases.yaml), returns the in-house designation
    instead of requiring a taxonomy match."""
    if phase_code:
        in_house = _in_house_phases().get(phase_code)
        if in_house:
            return in_house.get("sub")
    if not taxonomy_phase:
        return None
    typical = taxonomy_phase.get("typical_subs") or []
    for ts in typical:
        if ts.get("sub"):
            return ts["sub"]
    return None


def _in_house_note(phase_code: str | None) -> str | None:
    """Returns the suggested 'needs confirmation' line for an in-house phase,
    or None if the phase isn't in the in-house config."""
    if not phase_code:
        return None
    entry = _in_house_phases().get(phase_code)
    return entry.get("note") if entry else None


def _confirmed_in_items(items: list[dict], phase_code: str, job: str) -> bool:
    """Items with text mentioning the phase code or sub for this job, where
    status is non-BLOCKED, treated as "confirmed". Loose heuristic — exists
    so the §2 confirmed column isn't always '?' on first run."""
    needle = phase_code.lower()
    for it in items:
        if it.get("job") != job:
            continue
        if it.get("status") in ("COMPLETE", "DISMISSED", "BLOCKED"):
            continue
        text = " ".join(filter(None, [it.get("action"), it.get("update")])).lower()
        if needle in text:
            return True
    return False


def _execution_2wk(ctx: RenderContext, pm: str, items: list[dict]) -> tuple[list[dict], list[dict]]:
    """2-week execution rows ANCHORED to current_stage from job-stages.json
    (not phase 1). For each PM job we surface:
      1. Ongoing phases at stage >= current_stage - 1 (current/recent work)
      2. Unstarted phases at stage in [current_stage, current_stage + 2]
         (next-up work that should kick off in 14 days)

    Logging-gap diagnostic: jobs whose current_stage is well past pre-data
    history (current_stage > 5) frequently have legacy 'ongoing' phases at
    stage 1-3 because logs from those phases were never captured. Those are
    flagged as `pre_data` and DO NOT generate PREDICTED items — they're
    visual notices only.

    PREDICTED items are capped at 3 per job and only fire on real ambiguity
    (predecessor explicitly missing, or BLOCKED status), never on pre-data.

    Returns (per_job_rows, predicted_items).
    """
    instances = ctx.phase3["instances"]["instances"]
    job_stages = ctx.phase3["job_stages"]["jobs"]
    taxonomy = _phase_lookup(ctx)
    pm_jobs = ctx.pm_to_jobs.get(pm, [])

    per_job: list[dict] = []
    predicted: list[dict] = []
    pred_seq = 1

    for job in pm_jobs:
        js = job_stages.get(job) or {}
        current_stage = js.get("current_stage")
        if current_stage is None:
            continue

        # ----- Build candidate phase code list -----
        candidate_codes: list[str] = []
        seen: set[str] = set()
        gap_codes: list[str] = []  # ongoing phases way below current_stage = pre-data

        # Bucket: ongoing phases bucketed by stage
        for op in (js.get("ongoing_phases") or []):
            code = op.get("phase_code")
            if not code:
                continue
            tax = taxonomy.get(code)
            if not tax:
                continue
            stage = tax.get("stage", 0) or 0
            if stage < current_stage - 3:
                gap_codes.append(code)
                # still surface gap rows so PM sees them, but tagged pre_data
                if code not in seen:
                    candidate_codes.append(code)
                    seen.add(code)
            elif stage >= current_stage - 1:
                if code not in seen:
                    candidate_codes.append(code)
                    seen.add(code)
            # phases at stage in [current_stage-2, current_stage-3]: skip
            # (likely complete or no longer relevant)

        # Plus next-up unstarted phases at stage [current_stage .. current_stage+2]
        instance_codes_for_job = {
            i.get("phase_code") for i in instances if i.get("job") == job
        }
        for code, tax in taxonomy.items():
            stage = tax.get("stage", 0) or 0
            if current_stage <= stage <= current_stage + 2:
                if code in instance_codes_for_job:
                    continue  # already started/complete
                if code in seen:
                    continue
                candidate_codes.append(code)
                seen.add(code)

        # ----- Build rows -----
        # Pre-load completed-phase set for predecessor checks
        complete_codes_for_job = {
            i.get("phase_code") for i in instances
            if i.get("job") == job and i.get("status") == "complete"
        }
        medians_by_code = {m.get("phase_code"): m for m in (ctx.phase3.get("medians", {}).get("medians") or [])}
        today_d = parse_iso(ctx.today)

        rows: list[dict] = []
        for code in candidate_codes:
            tax = taxonomy.get(code) or {}
            stage = tax.get("stage", 0) or 0
            phase_name = tax.get("name", "")
            sub = _typical_sub_for_phase(tax, code)

            inst = next(
                (i for i in instances if i.get("job") == job and i.get("phase_code") == code),
                None,
            )

            is_pre_data = code in gap_codes
            pred_missing: list[str] = []
            if is_pre_data:
                pred_complete = "(pre-data)"
            elif inst is not None and inst.get("predecessors_complete") is True:
                pred_complete = "Y"
            elif inst is not None and inst.get("predecessors_complete") is False:
                # Check if predecessors are completed via instances (Fix 1)
                preds = tax.get("predecessors") or []
                missing_real = [p for p in preds if p not in complete_codes_for_job]
                if not missing_real:
                    pred_complete = "Y"  # data layer was wrong; instances show predecessors complete
                else:
                    pred_complete = "N"
                    pred_missing = missing_real
            elif inst is None:
                # Phase not yet started — check predecessors via instances
                preds = tax.get("predecessors") or []
                if not preds:
                    pred_complete = "Y"
                else:
                    missing_real = [p for p in preds if p not in complete_codes_for_job]
                    if not missing_real:
                        pred_complete = "Y"
                    elif len(missing_real) == len(preds):
                        pred_complete = "?"  # we have no data on any predecessor
                    else:
                        pred_complete = "N"
                        pred_missing = missing_real
            else:
                pred_complete = "?"

            # Fix 1 — populate Materials from PROCUREMENT items referencing this phase
            related = _items_referencing_phase(items, code, phase_name, job=job)
            proc_items = [it for it in related if it.get("category") == "PROCUREMENT"]
            proc_pending = [it for it in proc_items if _open_status(it.get("status"))]
            if not proc_items:
                materials = "?"
                materials_detail = ""
            elif proc_pending:
                materials = f"PENDING ({len(proc_pending)})"
                materials_detail = ", ".join(it.get("id", "?") for it in proc_pending[:3])
            else:
                materials = "Y"
                materials_detail = ""

            # Fix 1 — populate Confirmed from SCHEDULE items mentioning the phase
            sched_items = [it for it in related
                           if it.get("category") == "SCHEDULE"
                           and _open_status(it.get("status"))]
            if sched_items:
                confirmed = "Y"
                confirmed_detail = sched_items[0].get("id", "")
            else:
                confirmed = "N" if related else "?"
                confirmed_detail = ""

            # Fix 1 — Blockers from BLOCKED items referencing this phase
            blockers = [it for it in related if it.get("status") == "BLOCKED"]
            blockers_text = "; ".join(b.get("id", "?") for b in blockers) if blockers else ""

            # Fix 8 — phase progression: days active vs median.
            # Fix 3 (wmp21) — phase-medians.json keys are 'median_active_days'
            # (not 'primary_active_days_median'). Look up correctly.
            # Fix 4 (wmp21) — when days_active > 365, surface as pre-data
            # (data attribution issue from older log entries).
            progress = None
            if inst is not None and inst.get("status") == "ongoing":
                first_log = parse_iso(inst.get("first_log_date"))
                if first_log and today_d:
                    days_active = max(0, (today_d - first_log).days)
                    median_data = medians_by_code.get(code) or {}
                    median_active = median_data.get("median_active_days")
                    if days_active > 365:
                        progress = {
                            "days_active": days_active,
                            "median_days": median_active,
                            "kind": "pre_data",
                            "flag": "pre_data",
                        }
                    else:
                        progress = {
                            "days_active": days_active,
                            "median_days": median_active,
                            "kind": "ongoing",
                        }
                        if median_active and days_active > median_active * 2:
                            progress["flag"] = "red"
                        elif median_active and days_active > median_active * 1.5:
                            progress["flag"] = "amber"
                        else:
                            progress["flag"] = "ok"
            elif inst is not None and inst.get("status") == "complete":
                progress = {"kind": "complete"}

            # Fix 6 — cross-references to related items (top 3)
            cross_ref_ids = [it.get("id") for it in related[:3] if it.get("id")]

            any_red = (pred_complete == "N") or bool(blockers) or (progress and progress.get("flag") == "red")

            rows.append({
                "phase_code": code,
                "phase_name": phase_name,
                "sub": sub,
                "materials_on_site": materials,
                "materials_detail": materials_detail,
                "predecessor_complete": pred_complete,
                "predecessor_missing": pred_missing,
                "confirmed": confirmed,
                "confirmed_detail": confirmed_detail,
                "blockers": blockers_text,
                "any_red_flag": bool(any_red),
                "pre_data": is_pre_data,
                "stage": stage,
                "progress": progress,
                "cross_ref_ids": cross_ref_ids,
            })

            # PREDICTED items — only for real ambiguity (NOT pre-data, NOT
            # missing instance data). Cap at 3 per job. Fix 15: clean
            # action text without "[PREDICTED]" prefix (template adds the
            # marker visually).
            job_predicted_count = sum(1 for p in predicted if p.get("job") == job)
            if job_predicted_count >= 3:
                continue
            if is_pre_data:
                continue
            if pred_complete == "N" and pred_missing:
                first_pred = pred_missing[0]
                predicted.append({
                    "id": f"PRED-{pred_seq:03d}",
                    "job": job,
                    "category": "SCHEDULE",
                    "source": "system_predicted",
                    "owner": pm.split()[0],
                    "action": (
                        f"{pm.split()[0]} to confirm or sequence "
                        f"{phase_name} ({code}) — predecessor {first_pred} "
                        f"not logged. Hold {code} or backfill predecessor."
                    ),
                    "due": None,
                    "priority": "HIGH",
                    "status": "NOT_STARTED",
                    "phase_code": code,
                    "predicted_kind": "predecessor",
                })
                pred_seq += 1
            elif blockers:
                predicted.append({
                    "id": f"PRED-{pred_seq:03d}",
                    "job": job,
                    "category": "SCHEDULE",
                    "source": "system_predicted",
                    "owner": pm.split()[0],
                    "action": (
                        f"{pm.split()[0]} to resolve blocker on "
                        f"{phase_name} ({code}) — items {blockers_text} blocked."
                    ),
                    "due": None,
                    "priority": "HIGH",
                    "status": "NOT_STARTED",
                    "phase_code": code,
                    "predicted_kind": "blocker",
                })
                pred_seq += 1
            elif materials == "?" and confirmed == "?":
                # Fix 1 — single confirm-the-gap predicted item per row
                # (cap-aware so we don't flood)
                predicted.append({
                    "id": f"PRED-{pred_seq:03d}",
                    "job": job,
                    "category": "SCHEDULE",
                    "source": "system_predicted",
                    "owner": pm.split()[0],
                    "action": (
                        f"{pm.split()[0]} to confirm sub + materials for "
                        f"{phase_name} ({code}) — no procurement or schedule "
                        f"items reference this phase yet."
                    ),
                    "due": None,
                    "priority": "NORMAL",
                    "status": "NOT_STARTED",
                    "phase_code": code,
                    "predicted_kind": "gap",
                })
                pred_seq += 1

        # Sort rows: real current-stage stuff first, pre-data last
        rows.sort(key=lambda r: (r["pre_data"], r["stage"], r["phase_code"]))

        if rows:
            # Detect "logging gap" — current_stage > 5 AND any pre_data rows
            # OR any rows below stage 5 when current_stage > 5
            has_gap = (
                current_stage > 5
                and any(r["pre_data"] or r["stage"] < 5 for r in rows)
            )
            gap_count = sum(1 for r in rows if r["pre_data"])
            per_job.append({
                "job": job,
                "current_stage": current_stage,
                "current_stage_name": js.get("current_stage_name", ""),
                "rows": rows,
                "logging_gap": has_gap,
                "logging_gap_count": gap_count,
            })

    return per_job, predicted


_CLOSEOUT_SEQUENCE_PHASES = ["15.1", "15.2", "15.3", "15.4", "15.5", "15.6"]


def _coordination_4wk(ctx: RenderContext, pm: str) -> list[dict]:
    """Sequencing dependencies for activities ~15-28d out, ANCHORED to
    current_stage. Walks unstarted phases at stage [current_stage+1,
    current_stage+2] (Fix 7 wmp21 — was current_stage+3) and surfaces
    those needing sub identification or sequencing confirmation. Capped
    at 6 phases per job (was 8). Skips phases that already have an
    instance (ongoing or complete).

    Fix 5 (wmp21) — when a job is at current_stage>=15 AND no candidate
    phases generate (everything's already complete or in-progress),
    force-render the closeout sequence as a single in-house line so the
    section isn't empty for late-stage jobs.
    """
    job_stages = ctx.phase3["job_stages"]["jobs"]
    instances = ctx.phase3["instances"]["instances"]
    taxonomy = _phase_lookup(ctx)
    pm_jobs = ctx.pm_to_jobs.get(pm, [])
    out: list[dict] = []

    for job in pm_jobs:
        js = job_stages.get(job) or {}
        current_stage = js.get("current_stage")
        if current_stage is None:
            continue

        instance_codes = {
            i.get("phase_code") for i in instances
            if i.get("job") == job and i.get("status") in ("ongoing", "complete")
        }

        rows: list[dict] = []
        # Fix 7 — narrower forward window (current_stage+1 .. current_stage+2)
        # to avoid pre-con jobs walking the entire foundation stage.
        for code, tax in taxonomy.items():
            stage = tax.get("stage", 0) or 0
            if not (current_stage + 1 <= stage <= current_stage + 2):
                continue
            if code in instance_codes:
                continue
            sub = _typical_sub_for_phase(tax, code)
            preds = tax.get("predecessors") or []
            preds_named = [
                f"{p} {(taxonomy.get(p) or {}).get('name','')}".strip()
                for p in preds[:3]
            ]
            in_house = _in_house_note(code)
            if in_house:
                needs = in_house
            elif sub:
                needs = "Confirm sub start + sequence"
            else:
                needs = f"Identify sub for {tax.get('name', '')}"
            rows.append({
                "phase_code": code,
                "phase_name": tax.get("name", ""),
                "stage": stage,
                "sub": sub,
                "predecessors": preds_named,
                "needs_confirmation": needs,
            })

        # Fix 5 — closeout fallback for stage-15 jobs with no candidates
        if not rows and current_stage >= 15:
            for code in _CLOSEOUT_SEQUENCE_PHASES:
                tax = taxonomy.get(code)
                if not tax:
                    continue
                if code in instance_codes:
                    continue
                rows.append({
                    "phase_code": code,
                    "phase_name": tax.get("name", ""),
                    "stage": tax.get("stage", 15),
                    "sub": _typical_sub_for_phase(tax, code) or "Ross Built Crew",
                    "predecessors": [],
                    "needs_confirmation": _in_house_note(code) or "Confirm timing",
                })

        if rows:
            rows.sort(key=lambda r: (r["stage"], r["phase_code"]))
            out.append({
                "job": job,
                "current_stage": current_stage,
                "rows": rows[:6],   # Fix 7 — cap 6 (was 8)
            })

    return out


def _procurement_8wk(items: list[dict], today: date | None) -> dict:
    """Open PROCUREMENT + SELECTION items split by horizon (Fix 2):

      §4a ACTIVE THIS WEEK — due_date in next 7d OR priority=URGENT
      §4b 8-WEEK GATE — long-lead items (everything else)

    SELECTION items always show in 8-WEEK GATE unless they're URGENT or
    due-this-week, since they're inherently gating decisions. Each item
    also gets `gates_phase_code`/`gates_phase_name` for the cross-reference
    line (Fix 6).
    """
    cal_today = date.today()

    active_this_week: list[dict] = []
    long_lead: list[dict] = []

    for it in items:
        if not _open_status(it.get("status")):
            continue
        cat = it.get("category")
        if cat not in ("PROCUREMENT", "SELECTION"):
            continue
        n = _normalize_item(it, today)

        # Annotate which phase this item gates (Fix 6)
        gp_code, gp_name = _phase_for_item(it)
        n["gates_phase_code"] = gp_code
        n["gates_phase_name"] = gp_name

        d = n.get("days_to_due")
        is_urgent = (it.get("priority") or "").upper() == "URGENT"
        active = is_urgent or (d is not None and -7 <= d <= 7)

        if active:
            active_this_week.append(n)
        else:
            long_lead.append(n)

    def _key(x):
        d = x.get("days_to_due")
        if d is None:
            return (1, 0)
        return (0, d)

    active_this_week.sort(key=_key)
    long_lead.sort(key=_key)

    # Bucket the 8-week gate by category for clearer rendering
    long_lead_proc = [n for n in long_lead if n.get("category") == "PROCUREMENT"]
    long_lead_sel = [n for n in long_lead if n.get("category") == "SELECTION"]

    return {
        # Backwards-compat keys (legacy template fields):
        "procurement_items": long_lead_proc,
        "selection_items": long_lead_sel,
        # New Fix-2 horizon split:
        "active_this_week": active_this_week,
        "long_lead_procurement": long_lead_proc,
        "long_lead_selections": long_lead_sel,
    }


_PRIORITY_WEIGHT = {"URGENT": 4, "HIGH": 3, "NORMAL": 2, "LOW": 1, "MEDIUM": 2}


def _items_by_category(items: list[dict], today: date | None,
                       pm_owner_first: str | None = None) -> dict:
    """Group open items by category. Sort within each category (Fix 11):
    priority DESC → days overdue DESC → opened_date DESC.
    Items owned by someone other than the PM are excluded (Fix 12 —
    they go to a separate 'waiting on others' subsection)."""
    out: dict[str, list[dict]] = {c: [] for c in ITEM_CATEGORIES}
    for it in items:
        if not _open_status(it.get("status")):
            continue
        # Fix 12 — exclude items owned by someone other than this PM
        if pm_owner_first:
            owner = (it.get("owner") or "").strip()
            owner_first = owner.split()[0].lower() if owner else ""
            if owner_first and owner_first != pm_owner_first.lower():
                continue
        n = _normalize_item(it, today)
        out[n["category"]].append(n)

    def _sort_key(item):
        pri = _PRIORITY_WEIGHT.get((item.get("priority") or "").upper(), 0)
        d = item.get("days_to_due")
        overdue = -d if (d is not None and d < 0) else 0
        opened = item.get("opened") or ""
        return (-pri, -overdue, opened)

    for cat in out:
        out[cat].sort(key=_sort_key)
    return {cat: lst for cat, lst in out.items() if lst}


def _slugify_sub(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return re.sub(r"-+", "-", s).strip("-")


def _sub_signals_for_pm(ctx: RenderContext, pm: str) -> dict:
    """Fix 7 — sub performance integration. For each sub currently active
    on a job in this PM's portfolio, surface name + density vs baseline +
    flag_score + drift signals. RED status (flag_score >= 4) is highlighted.

    Returns:
      {
        "active": [ {sub, density, vs_baseline, flag_score, drift, jobs_touching} ],
        "red_count": int,
      }
    """
    pm_jobs = ctx.pm_to_jobs.get(pm, [])
    instances = ctx.phase3.get("instances", {}).get("instances") or []
    rollups = ctx.phase3.get("rollups", {}).get("rollups") or []

    # Collect subs currently active on PM's jobs (from ongoing phase instances)
    sub_jobs: dict[str, set[str]] = defaultdict(set)
    for ins in instances:
        if ins.get("job") not in pm_jobs:
            continue
        if ins.get("status") != "ongoing":
            continue
        for s in (ins.get("subs_involved") or []):
            name = s.get("sub") if isinstance(s, dict) else s
            if name:
                sub_jobs[name].add(ins.get("job"))

    # For each active sub, find their worst rollup → that's the headline signal
    rollups_by_sub: dict[str, list[dict]] = defaultdict(list)
    for r in rollups:
        rollups_by_sub[r.get("sub")].append(r)

    active = []
    red_count = 0
    for sub, jobs_set in sub_jobs.items():
        rs = rollups_by_sub.get(sub, [])
        if rs:
            worst = min(rs, key=lambda r: r.get("vs_phase_median_density", 0) or 0)
            density = worst.get("primary_density")
            vs_baseline = worst.get("vs_phase_median_density")
            flag_score = worst.get("flag_score", 0) or 0
            drift = ""
            if flag_score >= 2:
                lbl = worst.get("density_label_absolute") or ""
                pc = worst.get("phase_code") or ""
                drift = f"{lbl} on {pc}" if lbl and pc else lbl or pc
        else:
            density = vs_baseline = None
            flag_score = 0
            drift = ""
        if flag_score >= 4:
            red_count += 1
        active.append({
            "sub": sub,
            "slug": _slugify_sub(sub),
            "density": density,
            "vs_baseline": vs_baseline,
            "flag_score": flag_score,
            "drift": drift,
            "jobs_touching": sorted(jobs_set),
            "status": ("RED" if flag_score >= 4
                       else "YELLOW" if flag_score >= 2
                       else "GREEN"),
        })
    # Sort: RED first, then YELLOW by worst vs_baseline, then GREEN
    active.sort(key=lambda x: (
        0 if x["status"] == "RED" else 1 if x["status"] == "YELLOW" else 2,
        x["vs_baseline"] if x["vs_baseline"] is not None else 0,
    ))
    return {"active": active, "red_count": red_count}


_NAME_AT_END_RE = re.compile(
    r"\b(?:with|for|from|to|by|push|chase|force)\s+"
    r"(Bishop|Bishops|Courtney|Fish(?:es)?|Krauss|Markgraf|Pou|Ruthven|"
    r"Molinari|Drummond|Dewberry|Clark|Biales|Johnson|Harllee|"
    r"Patrick|Cindy|Mara|owner|homeowner|client)\b",
    re.IGNORECASE,
)


def _client_decisions_pending(items: list[dict], today: date | None) -> dict:
    """Fix 10 — group CLIENT and SELECTION items by the named client/designer
    referenced in the action text. Empty groups omitted."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        if not _open_status(it.get("status")):
            continue
        cat = it.get("category")
        if cat not in ("CLIENT", "SELECTION"):
            continue
        text = " ".join(filter(None, [it.get("action"), it.get("update")]))
        m = _NAME_AT_END_RE.search(text)
        if not m:
            continue
        name = m.group(1).title()
        # Normalize plural Fishes → Fishes (already title)
        grouped[name].append(_normalize_item(it, today))

    # Sort each person's items by priority desc, due asc
    for k in grouped:
        grouped[k].sort(key=lambda x: (
            -_PRIORITY_WEIGHT.get((x.get("priority") or "").upper(), 0),
            x.get("days_to_due") if x.get("days_to_due") is not None else 999,
        ))

    return dict(grouped)


def _what_changed_since_last(items: list[dict], today: date | None,
                             pm_owner_first: str | None,
                             since_days: int = 7) -> dict:
    """Fix 9 — what changed since last office meeting (last 7 days).
    Counts new / closed / escalated / waiting-on-others items.
    Compact data shape — template renders a single line."""
    if not today:
        return {"new": 0, "new_by_cat": {}, "closed": 0, "escalated": 0, "waiting": 0}
    cutoff = today - timedelta(days=since_days)

    new_by_cat: dict[str, int] = defaultdict(int)
    new_count = closed_count = escalated_count = waiting_count = 0

    for it in items:
        opened = parse_iso(it.get("opened"))
        status = (it.get("status") or "").upper()
        cat = it.get("category") or "ADMIN"
        if opened and opened >= cutoff:
            if status not in ("DUPLICATE_MERGED",):
                new_count += 1
                new_by_cat[cat] += 1
        # Closed
        cd = parse_iso(it.get("close_date") or it.get("closed_date"))
        if cd and cd >= cutoff and status in ("COMPLETE", "DISMISSED"):
            closed_count += 1
        # Escalated proxy: priority is URGENT AND opened recently OR status BLOCKED
        if status == "BLOCKED" and opened and opened >= cutoff:
            escalated_count += 1
        elif (it.get("priority") or "").upper() == "URGENT" and opened and opened >= cutoff:
            escalated_count += 1
        # Waiting on others
        owner = (it.get("owner") or "").strip()
        owner_first = owner.split()[0].lower() if owner else ""
        if (pm_owner_first
                and owner_first
                and owner_first != pm_owner_first.lower()
                and _open_status(status)):
            waiting_count += 1

    return {
        "new": new_count,
        "new_by_cat": dict(new_by_cat),
        "closed": closed_count,
        "escalated": escalated_count,
        "waiting": waiting_count,
    }


def _job_header_context(ctx: RenderContext, job: str) -> dict:
    """Fix 13 — per-job context block: stage, days in stage, last sub on
    site, last log date, target CO, GP direction, item counts by category.

    Fix 4 (wmp21) — when days_in_stage > 365, surface honestly as a data
    attribution issue rather than the misleading day count.
    """
    job_stages = ctx.phase3.get("job_stages", {}).get("jobs", {})
    js = job_stages.get(job, {})
    instances = ctx.phase3.get("instances", {}).get("instances") or []

    # Find days in current stage = today - earliest first_log among ongoing
    today_d = parse_iso(ctx.today)
    cur_stage = js.get("current_stage")
    days_in_stage = None
    days_in_stage_attribution_flag = False
    if cur_stage is not None and today_d is not None:
        first_logs = []
        for ins in instances:
            if ins.get("job") != job:
                continue
            if ins.get("stage") != cur_stage:
                continue
            fl = parse_iso(ins.get("first_log_date"))
            if fl:
                first_logs.append(fl)
        if first_logs:
            days_in_stage = (today_d - min(first_logs)).days
            if days_in_stage > 365:
                days_in_stage_attribution_flag = True

    # Last sub on site + last log date
    log_keys = list(ctx.daily_by_job.keys())
    log_key = job_log_key(job, log_keys)
    logs = ctx.daily_by_job.get(log_key, []) if log_key else []
    last_sub = None
    last_log_date = None
    if logs:
        latest = logs[0]
        cc = latest.get("crews_clean") or []
        if cc:
            last_sub = cc[0]
        last_log_d = parse_log_date(latest.get("date") or "", today_d.year if today_d else 2026)
        if last_log_d:
            last_log_date = last_log_d.isoformat()

    return {
        "job": job,
        "current_stage": cur_stage,
        "current_stage_name": js.get("current_stage_name", ""),
        "days_in_stage": days_in_stage,
        "days_in_stage_attribution_flag": days_in_stage_attribution_flag,
        "last_sub_on_site": last_sub,
        "last_log_date": last_log_date,
        "target_co": js.get("co_target"),
    }


def _waiting_on_others(items: list[dict], today: date | None,
                       pm_owner_first: str) -> dict:
    """Items in this PM's binder where owner != PM's first name.
    Grouped by owner first-name (Fix 12)."""
    out: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        if not _open_status(it.get("status")):
            continue
        owner = (it.get("owner") or "").strip()
        if not owner:
            continue
        owner_first = owner.split()[0]
        if owner_first.lower() == pm_owner_first.lower():
            continue
        out[owner_first].append(_normalize_item(it, today))
    # Sort each group by priority desc, days_to_due asc (overdue first)
    for k in out:
        out[k].sort(key=lambda x: (
            -_PRIORITY_WEIGHT.get((x.get("priority") or "").upper(), 0),
            x.get("days_to_due") if x.get("days_to_due") is not None else 999,
        ))
    return dict(out)


def _outstanding_selections(items: list[dict], today: date | None) -> list[dict]:
    sel = [
        _normalize_item(it, today)
        for it in items
        if it.get("category") == "SELECTION" and _open_status(it.get("status"))
    ]
    sel.sort(key=lambda x: (x.get("days_to_due") if x.get("days_to_due") is not None else 999))
    return sel


def _issues_and_financial(items: list[dict], jobs: list[dict], today: date | None,
                          ctx: "RenderContext | None" = None,
                          pm_jobs: list[str] | None = None) -> dict:
    """Phase 12 wmp18 Fix 5 — §7 redesign.

    Three subsections:
      1. ESCALATIONS — items with priority=URGENT AND days_open > 14
         (true escalations, not routine items). Empty → "No active
         escalations" single line.
      2. BUDGET-CATEGORY ITEMS — open items where category=BUDGET, sorted
         by aging desc.
      3. FINANCIAL ROLLUP — GP/targetCO data when populated; otherwise
         render single empty-state line (Phase 13 placeholder).
      4. Sub performance summary — count of subs in RED status touching
         this PM's jobs (uses sub-phase-rollups flag_score >= 4).
    """
    # 1. Escalations
    escalations = []
    for it in items:
        if not _open_status(it.get("status")):
            continue
        if (it.get("priority") or "").upper() != "URGENT":
            continue
        if (it.get("days_open") or 0) <= 14:
            continue
        escalations.append(_normalize_item(it, today))
    escalations.sort(key=lambda x: -(x.get("days_open") or 0))

    # 2. BUDGET-category items
    budget_items = [
        _normalize_item(it, today) for it in items
        if it.get("category") == "BUDGET" and _open_status(it.get("status"))
    ]
    budget_items.sort(key=lambda x: -(x.get("days_open") or 0))

    # 3. Financial rollup — show jobs only when GP is populated
    financial_jobs = [
        {"name": j.get("name"), "gp": j.get("gp", "—"), "targetCO": j.get("targetCO", "—"),
         "status": j.get("status")}
        for j in jobs
    ]
    has_financial_data = any(
        (j.get("gp") and j.get("gp") not in ("—", "-", "", None))
        for j in financial_jobs
    )

    # 4. Sub performance — count of subs at flag_score >= 4 touching PM's jobs
    sub_red_count = 0
    sub_red_list = []
    if ctx and pm_jobs:
        rollups = ctx.phase3.get("rollups", {}).get("rollups") or []
        # Subs touching this PM's jobs (from phase-instances)
        instances = ctx.phase3.get("instances", {}).get("instances") or []
        subs_on_pm_jobs = set()
        for ins in instances:
            if ins.get("job") not in pm_jobs:
                continue
            for s in (ins.get("subs_involved") or []):
                name = s.get("sub") if isinstance(s, dict) else s
                if name:
                    subs_on_pm_jobs.add(name)
        # Now check rollups for RED status (worst flag_score per sub >= 4)
        sub_max_flag: dict[str, int] = {}
        for r in rollups:
            sub = r.get("sub")
            if sub not in subs_on_pm_jobs:
                continue
            sub_max_flag[sub] = max(sub_max_flag.get(sub, 0), r.get("flag_score", 0) or 0)
        for sub, max_flag in sub_max_flag.items():
            if max_flag >= 4:
                sub_red_count += 1
                sub_red_list.append({"sub": sub, "max_flag_score": max_flag})

    return {
        "escalations": escalations,
        "budget_items": budget_items,
        "financial": {
            "jobs": financial_jobs,
            "has_data": has_financial_data,
            "open_co_count": len(budget_items),
        },
        "sub_red_count": sub_red_count,
        "sub_red_list": sub_red_list,
    }


def build_office_meeting_bundle(ctx: RenderContext, pm: str, tracking: dict) -> dict:
    if pm not in PM_NAMES:
        raise KeyError(f"Unknown PM: {pm}")
    today_d = parse_iso(ctx.today)
    pm_first = pm.split()[0]

    binder_orig = load_json(BINDERS / PM_BINDER_FILES[pm])
    source_items = binder_orig.get("items", [])
    enriched_path = ENRICHED / f"{Path(PM_BINDER_FILES[pm]).stem}.enriched.json"
    if enriched_path.exists():
        items = _merge_category_from_source(
            load_json(enriched_path).get("items", []), source_items
        )
    else:
        items = source_items
    jobs = binder_orig.get("jobs", [])
    pm_jobs = ctx.pm_to_jobs.get(pm, [])

    open_items = [it for it in items if _open_status(it.get("status"))]
    stale_count = 0
    overdue_count = 0
    for it in open_items:
        n = _normalize_item(it, today_d)
        if (n.get("days_open") or 0) > 14:
            stale_count += 1
        d = n.get("days_to_due")
        if d is not None and d < 0:
            overdue_count += 1

    ppc = _ppc_for_pm(ctx, pm, tracking, today_d)
    exec_rows, predicted = _execution_2wk(ctx, pm, items)
    coord_rows = _coordination_4wk(ctx, pm)
    procurement_8wk = _procurement_8wk(items, today_d)
    # Fix 11 + Fix 12 — exclude items owned by others from §5 categories
    grouped = _items_by_category(items, today_d, pm_owner_first=pm_first)
    selections = _outstanding_selections(items, today_d)
    issues_fin = _issues_and_financial(items, jobs, today_d, ctx=ctx, pm_jobs=pm_jobs)
    # Phase 12 wmp18 — new sections
    sub_signals = _sub_signals_for_pm(ctx, pm)
    client_decisions = _client_decisions_pending(items, today_d)
    waiting = _waiting_on_others(items, today_d, pm_first)
    what_changed = _what_changed_since_last(items, today_d, pm_first, since_days=7)
    job_headers = [_job_header_context(ctx, j) for j in pm_jobs]

    # Fix 6 — annotate selection-section items with "gates phase" data so
    # templates can render the cross-reference inline.
    for s in selections:
        gp_code, gp_name = _phase_for_item(s)
        s["gates_phase_code"] = gp_code
        s["gates_phase_name"] = gp_name

    # Fix 14 — flag §3 as in-house-only when ALL rows have a sub starting
    # with "Ross Built Crew"
    for jb in coord_rows:
        in_house_only = all(
            (r.get("sub") or "").startswith("Ross Built Crew") for r in jb["rows"]
        )
        jb["in_house_only"] = in_house_only

    recently_completed = get_recently_completed(ctx, pm, since_days=7)

    return {
        "view_mode": "office",
        "pm": pm,
        "pm_slug": PM_SLUGS[pm],
        "today": ctx.today,
        "section_count": 7,
        "target_minutes": 75,
        "jobs": jobs,
        "job_headers": job_headers,
        "header_stats": {
            "open_actions": len(open_items),
            "stale_count": stale_count,
            "overdue_count": overdue_count,
            "selections_open": len(selections),
            "predicted_items": len(predicted),
            "waiting_on_others_count": sum(len(v) for v in waiting.values()),
            "recently_completed_count": sum(len(v) for v in recently_completed.values()),
            "sub_red_count": sub_signals.get("red_count", 0),
            "section_count": 7,
            "target_minutes": 75,
        },
        "what_changed": what_changed,
        "ppc": ppc,
        "execution_2wk": exec_rows,
        "execution_predicted": predicted,
        "sub_signals": sub_signals,
        "coordination_4wk": coord_rows,
        "procurement_8wk": procurement_8wk,
        "items_by_category": grouped,
        "waiting_on_others": waiting,
        "selections": selections,
        "client_decisions": client_decisions,
        "issues_financial": issues_fin,
        "recently_completed": recently_completed,
    }


# ---- Site meeting bundle -----------------------------------------------
def _rollover_items(items: list[dict], today: date | None) -> list[dict]:
    """Items still open or recently updated. Heuristic for the rollover
    section: any open item the PM was tracking, plus items closed in the
    last 7 days for context."""
    out: list[dict] = []
    for it in items:
        status = it.get("status")
        if _open_status(status):
            out.append(_normalize_item(it, today))
            continue
        if status == "COMPLETE":
            n = _normalize_item(it, today)
            if (n.get("days_open") or 0) <= 14:
                out.append(n)
    out.sort(key=lambda x: (x.get("status") == "COMPLETE",
                            -(x.get("days_open") or 0)))
    return out[:30]  # top 30 to keep the section tight


def _walk_areas(ctx: RenderContext, pm: str, items: list[dict], today: date | None) -> list[dict]:
    """Group ongoing phases on PM's jobs into walk areas. Each area lists
    active subs + recent QUALITY items for that area.

    Fix 2 (wmp21) — recency filter (14d) PLUS stage-floor for closeout
    jobs. The phase classifier mis-attributes recent logs to old phase
    buckets (e.g., Fish at stage 14 has "ongoing" instances at stages
    1-9 with recent log dates). For jobs at stage >= 14, restrict walk
    areas to stage >= current_stage - 4 (so stage 14 includes 10+, stage
    15 includes 11+). Surfacing honestly until classifier audit fixes
    the upstream data.
    """
    job_stages = ctx.phase3["job_stages"]["jobs"]
    instances = ctx.phase3["instances"]["instances"]
    taxonomy = _phase_lookup(ctx)
    pm_jobs = ctx.pm_to_jobs.get(pm, [])

    # Per-job stage floor: closeout jobs (stage >= 14) clip walks to
    # stage >= current_stage - 4 to suppress mis-attributed early-stage
    # phases. Pre-con/mid-build jobs use no floor.
    job_stage_floor: dict[str, int] = {}
    for j in pm_jobs:
        cs = (job_stages.get(j) or {}).get("current_stage")
        if cs is not None and cs >= 14:
            job_stage_floor[j] = max(0, cs - 4)
        else:
            job_stage_floor[j] = 0

    stage_to_area = {}
    for area_name, stages in WALK_AREAS:
        for s in stages:
            stage_to_area[s] = area_name

    by_area: dict[str, dict] = {a[0]: {"area": a[0], "stages": list(a[1]),
                                       "active_phases": [], "subs_active": set(),
                                       "items": [], "any_active": False}
                                for a in WALK_AREAS}

    # Active phases per area, restricted to PM's jobs.
    # Fix 2 (wmp21) — only include phases with RECENT log activity. The
    # phase classifier marks some pre-data phases as "ongoing" because
    # they have log entries in their bucket (e.g., Fish Site Grading 1.4
    # with log_count=1 from 18 months ago). Filter ongoing rows to those
    # whose last_log_date is within the last 14 days; otherwise the walk
    # surface fills with stale stages 1-9 for closeout-stage jobs.
    walk_recency_days = 14
    for ins in instances:
        job = ins.get("job")
        if job not in pm_jobs:
            continue
        # Stage-floor (closeout-job clamp) before per-instance recency
        stage = ins.get("stage", 0) or 0
        floor = job_stage_floor.get(job, 0)
        if stage < floor:
            continue
        status = ins.get("status")
        last_log = parse_iso(ins.get("last_log_date"))
        recent = (
            today is not None and last_log is not None
            and (today - last_log).days <= walk_recency_days
        )
        if status == "ongoing":
            if not recent:
                continue
        elif status == "complete":
            if not recent:
                continue
        else:
            continue
        area = stage_to_area.get(stage)
        if not area:
            continue
        b = by_area[area]
        b["active_phases"].append({
            "job": ins.get("job"),
            "phase_code": ins.get("phase_code"),
            "phase_name": ins.get("phase_name"),
            "primary_density": ins.get("primary_density"),
            "active_days": ins.get("primary_active_days"),
        })
        for s in (ins.get("subs_involved") or []):
            sub_name = s.get("sub") if isinstance(s, dict) else s
            if sub_name:
                b["subs_active"].add(sub_name)
        in_house_sub = _in_house_phases().get(ins.get("phase_code"), {}).get("sub")
        if in_house_sub:
            b["subs_active"].add(in_house_sub)
        b["any_active"] = True

    # QUALITY items per area: bucket by best-guess phase code → stage
    for it in items:
        if it.get("job") not in pm_jobs:
            continue
        if it.get("category") != "QUALITY" or not _open_status(it.get("status")):
            continue
        # Try to find a phase code referenced in the action
        text = " ".join(filter(None, [it.get("action"), it.get("update")])).lower()
        matched_area = None
        for code, p in taxonomy.items():
            if code.lower() in text and p.get("stage") in stage_to_area:
                matched_area = stage_to_area[p["stage"]]
                break
        if matched_area is None:
            # default punch-related items to closeout area
            matched_area = "Punch & Closeout"
        by_area[matched_area]["items"].append(_normalize_item(it, today))

    # Materialize: keep areas with any signal (active_phases OR items),
    # convert sub set to sorted list, sort phases by job/phase_code
    out: list[dict] = []
    for area_name, _stages in WALK_AREAS:
        b = by_area[area_name]
        if not b["any_active"] and not b["items"]:
            continue
        b["subs_active"] = sorted(b["subs_active"])
        b["active_phases"].sort(key=lambda x: (x.get("job") or "", x.get("phase_code") or ""))
        out.append(b)
    return out


def _subs_this_week(ctx: RenderContext, pm: str) -> list[dict]:
    """Per-job sub list with daily-log-derived activity in the last 7 days
    + sub-phase-rollups baseline check."""
    pm_jobs = ctx.pm_to_jobs.get(pm, [])
    rollups = ctx.phase3["rollups"]["rollups"]
    rollups_by_sub = defaultdict(list)
    for r in rollups:
        rollups_by_sub[r["sub"]].append(r)

    today_d = parse_iso(ctx.today)
    seven_ago = today_d - timedelta(days=7) if today_d else None
    log_keys = list(ctx.daily_by_job.keys())

    out: list[dict] = []
    for job in pm_jobs:
        log_key = job_log_key(job, log_keys)
        logs = ctx.daily_by_job.get(log_key, []) if log_key else []
        sub_days: dict[str, int] = defaultdict(int)
        for log in logs:
            log_d = parse_log_date(log.get("date") or "", today_d.year if today_d else 2026)
            if not log_d or not seven_ago:
                continue
            if log_d < seven_ago or log_d > today_d:
                continue
            for s in (log.get("crews_clean") or []):
                if s:
                    sub_days[s] += 1

        rows = []
        for sub, days in sorted(sub_days.items(), key=lambda kv: -kv[1]):
            sub_rollups = rollups_by_sub.get(sub, [])
            worst = min(sub_rollups, key=lambda r: r.get("vs_phase_median_density", 0)) if sub_rollups else None
            drift_signal = ""
            if worst and worst.get("flag_score", 0) >= 2:
                drift_signal = f"{worst.get('density_label_absolute','')} on {worst.get('phase_code','')}"
            rows.append({
                "sub": sub,
                "days_this_week": days,
                "vs_baseline": worst.get("vs_phase_median_density") if worst else None,
                "primary_density": worst.get("primary_density") if worst else None,
                "drift_signal": drift_signal,
                "flag_score": worst.get("flag_score", 0) if worst else 0,
            })
        if rows:
            out.append({"job": job, "subs": rows})
    return out


def _hold_points(ctx: RenderContext, pm: str, items: list[dict], today: date | None) -> list[dict]:
    """Hold points = phase taxonomy phases marked hold_point=true OR
    QUALITY-category items whose update or action mentions 'hold'."""
    pm_jobs = ctx.pm_to_jobs.get(pm, [])
    instances = ctx.phase3["instances"]["instances"]
    taxonomy = _phase_lookup(ctx)
    out: list[dict] = []

    # Phase-taxonomy hold points where phase is currently ongoing on PM's job
    for ins in instances:
        if ins.get("job") not in pm_jobs:
            continue
        if ins.get("status") not in ("ongoing", "complete"):
            continue
        tax_p = taxonomy.get(ins.get("phase_code"))
        if not tax_p:
            continue
        if tax_p.get("hold_point") is True or tax_p.get("requires_inspection"):
            out.append({
                "job": ins.get("job"),
                "phase_code": ins.get("phase_code"),
                "phase_name": ins.get("phase_name"),
                "status": ins.get("status"),
                "kind": "phase_taxonomy",
                "note": tax_p.get("inspection_name") or "Inspection / hold point",
            })

    # Item-level hold flags
    for it in items:
        if it.get("category") != "QUALITY" or not _open_status(it.get("status")):
            continue
        text = " ".join(filter(None, [it.get("action"), it.get("update")])).lower()
        if "hold" in text or "do not proceed" in text or "stop work" in text:
            out.append({
                "job": it.get("job"),
                "phase_code": None,
                "phase_name": None,
                "status": it.get("status"),
                "kind": "item",
                "note": (it.get("action") or "")[:120],
                "item_id": it.get("id"),
            })

    return out


def build_site_meeting_bundle(ctx: RenderContext, pm: str, tracking: dict) -> dict:
    if pm not in PM_NAMES:
        raise KeyError(f"Unknown PM: {pm}")
    today_d = parse_iso(ctx.today)

    binder_orig = load_json(BINDERS / PM_BINDER_FILES[pm])
    source_items = binder_orig.get("items", [])
    enriched_path = ENRICHED / f"{Path(PM_BINDER_FILES[pm]).stem}.enriched.json"
    if enriched_path.exists():
        items = _merge_category_from_source(
            load_json(enriched_path).get("items", []), source_items
        )
    else:
        items = source_items
    jobs = binder_orig.get("jobs", [])

    open_items = [it for it in items if _open_status(it.get("status"))]
    overdue_count = 0
    for it in open_items:
        n = _normalize_item(it, today_d)
        d = n.get("days_to_due")
        if d is not None and d < 0:
            overdue_count += 1
    recently_completed = get_recently_completed(ctx, pm, since_days=7)
    sub_signals = _sub_signals_for_pm(ctx, pm)
    pm_jobs = ctx.pm_to_jobs.get(pm, [])
    job_headers = [_job_header_context(ctx, j) for j in pm_jobs]

    return {
        "view_mode": "site",
        "pm": pm,
        "pm_slug": PM_SLUGS[pm],
        "today": ctx.today,
        "section_count": 6,
        "target_minutes": 60,
        "jobs": jobs,
        "job_headers": job_headers,
        "sub_signals": sub_signals,
        "header_stats": {
            "open_actions": len(open_items),
            "overdue_count": overdue_count,
            "recently_completed_count": sum(len(v) for v in recently_completed.values()),
            "section_count": 6,
            "target_minutes": 60,
        },
        "recently_completed": recently_completed,
        "rollover_items": _rollover_items(items, today_d),
        "walk_areas": _walk_areas(ctx, pm, items, today_d),
        "subs_this_week": _subs_this_week(ctx, pm),
        "hold_points": _hold_points(ctx, pm, items, today_d),
        "field_discovered_blank_rows": 8,
        "closeout_template_rows": 6,
    }


# ---- Phase 13 — job-centric architecture --------------------------------
# Note: build_office_meeting_bundle and build_site_meeting_bundle are
# retained internally — build_pm_packet_bundle/build_job_bundle filter
# their output down to per-job views. The legacy render_office_meeting /
# render_site_meeting / render_pm_packet(view_mode) wrappers are removed
# along with their templates (Phase 13 cleanup).
def _slugify_job(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return re.sub(r"-+", "-", s).strip("-")


_JOB_REGISTRY_CACHE: list | None = None


def get_job_registry(ctx: RenderContext) -> list[dict]:
    """Walk binders/*.json and dedupe to a flat list of all active jobs.
    Returns: [{slug, name, pm_name, pm_slug, current_stage, current_stage_name, status}].
    Cached per request via simple module-level cache (cleared by load_context).
    """
    global _JOB_REGISTRY_CACHE
    if _JOB_REGISTRY_CACHE is not None:
        return _JOB_REGISTRY_CACHE

    job_stages = ctx.phase3.get("job_stages", {}).get("jobs", {}) or {}
    seen: set[str] = set()
    registry: list[dict] = []

    for pm in PM_NAMES:
        bp = BINDERS / PM_BINDER_FILES[pm]
        if not bp.exists():
            continue
        binder = load_json(bp)
        for j in binder.get("jobs", []):
            name = j.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            js = job_stages.get(name, {}) or {}
            registry.append({
                "slug": _slugify_job(name),
                "name": name,
                "pm_name": pm,
                "pm_slug": PM_SLUGS[pm],
                "current_stage": js.get("current_stage"),
                "current_stage_name": js.get("current_stage_name", ""),
                "status": j.get("status", "—"),
                "address": j.get("address", ""),
                "target_co": j.get("targetCO") or js.get("co_target"),
                "gp": j.get("gp", "—"),
            })
    _JOB_REGISTRY_CACHE = registry
    return registry


def slug_to_job(ctx: RenderContext, job_slug: str) -> dict | None:
    for entry in get_job_registry(ctx):
        if entry["slug"] == job_slug:
            return entry
    return None


def _filter_items_by_job(items_or_groups, job_name):
    """Filter a list of items OR a dict-of-{key: [items]} to one job."""
    if isinstance(items_or_groups, list):
        return [i for i in items_or_groups if i.get("job") == job_name]
    if isinstance(items_or_groups, dict):
        out = {}
        for k, v in items_or_groups.items():
            if isinstance(v, list):
                filt = [i for i in v if i.get("job") == job_name]
                if filt:
                    out[k] = filt
        return out
    return items_or_groups


def build_job_bundle(ctx: RenderContext, job_name: str, tracking: dict,
                     office: dict | None = None, site: dict | None = None) -> dict:
    """Build the data bundle for a single job. Filters the PM-level
    office + site bundles down to one job. When called from
    `build_pm_packet_bundle`, the caller passes pre-built `office` and
    `site` so we don't re-compute per job.
    """
    # Find which PM owns this job
    pm_for_job = None
    for pm, jobs in ctx.pm_to_jobs.items():
        if job_name in jobs:
            pm_for_job = pm
            break
    if pm_for_job is None:
        raise KeyError(f"No PM owns job: {job_name}")
    pm_first = pm_for_job.split()[0]

    if office is None:
        office = build_office_meeting_bundle(ctx, pm_for_job, tracking)
    if site is None:
        site = build_site_meeting_bundle(ctx, pm_for_job, tracking)

    today_d = parse_iso(ctx.today)

    # Re-compute job-scoped what_changed against the job's items
    binder_orig = load_json(BINDERS / PM_BINDER_FILES[pm_for_job])
    source_items = binder_orig.get("items", [])
    enriched_path = ENRICHED / f"{Path(PM_BINDER_FILES[pm_for_job]).stem}.enriched.json"
    if enriched_path.exists():
        items = _merge_category_from_source(
            load_json(enriched_path).get("items", []), source_items
        )
    else:
        items = source_items
    job_items = [it for it in items if it.get("job") == job_name]
    what_changed = _what_changed_since_last(job_items, today_d, pm_first, since_days=7)

    # Filter PM-level data structures
    exec_rows = [jb for jb in office["execution_2wk"] if jb["job"] == job_name]
    coord_rows = [jb for jb in office["coordination_4wk"] if jb["job"] == job_name]
    predicted = [p for p in office["execution_predicted"] if p.get("job") == job_name]

    proc = office["procurement_8wk"]
    job_proc = {
        "active_this_week": [i for i in proc.get("active_this_week", []) if i.get("job") == job_name],
        "long_lead_procurement": [i for i in proc.get("long_lead_procurement", []) if i.get("job") == job_name],
        "long_lead_selections": [i for i in proc.get("long_lead_selections", []) if i.get("job") == job_name],
    }

    grouped = _filter_items_by_job(office["items_by_category"], job_name)
    selections = [s for s in office["selections"] if s.get("job") == job_name]
    waiting = _filter_items_by_job(office["waiting_on_others"], job_name)
    client_decisions = _filter_items_by_job(office["client_decisions"], job_name)
    recent = _filter_items_by_job(office["recently_completed"], job_name)

    # Issues + financial — escalations + budget filtered, financial passes through
    if_data = office["issues_financial"]
    issues_fin = {
        "escalations": [i for i in if_data.get("escalations", []) if i.get("job") == job_name],
        "budget_items": [i for i in if_data.get("budget_items", []) if i.get("job") == job_name],
        "financial": if_data.get("financial", {}),
        "sub_red_count": sum(
            1 for s in if_data.get("sub_red_list", [])
            if any(j == job_name for j in (s.get("jobs", []) or []))
        ),
        "sub_red_list": if_data.get("sub_red_list", []),
    }

    # Sub signals — only subs touching THIS job
    job_subs = [
        s for s in (office["sub_signals"].get("active") or [])
        if job_name in (s.get("jobs_touching") or [])
    ]
    sub_signals = {
        "active": job_subs,
        "red_count": sum(1 for s in job_subs if s.get("status") == "RED"),
    }

    # Walk areas + hold points (from site bundle, filtered)
    walk_areas: list[dict] = []
    for a in site.get("walk_areas", []):
        filtered_phases = [p for p in a.get("active_phases", []) if p.get("job") == job_name]
        filtered_items = [i for i in a.get("items", []) if i.get("job") == job_name]
        if filtered_phases or filtered_items:
            walk_areas.append({
                "area": a.get("area"),
                "stages": a.get("stages", []),
                "active_phases": filtered_phases,
                "items": filtered_items,
                "subs_active": sorted({
                    s for p in filtered_phases for s in (p.get("subs_active") or [])
                }) if any("subs_active" in p for p in filtered_phases) else a.get("subs_active", []),
            })
    hold_points = [h for h in site.get("hold_points", []) if h.get("job") == job_name]

    # Stats
    open_items = [it for it in job_items if _open_status(it.get("status"))]
    stale = 0
    overdue = 0
    for it in open_items:
        n = _normalize_item(it, today_d)
        if (n.get("days_open") or 0) > 14:
            stale += 1
        if (n.get("days_to_due") or 0) < 0:
            overdue += 1

    job_header = _job_header_context(ctx, job_name)

    # Look up registry entry for nice metadata (status pill etc.)
    reg = slug_to_job(ctx, _slugify_job(job_name)) or {}

    return {
        "kind": "job",
        "job": job_name,
        "job_slug": _slugify_job(job_name),
        "pm": pm_for_job,
        "pm_slug": PM_SLUGS.get(pm_for_job, ""),
        "pm_first": pm_first,
        "today": ctx.today,
        "job_header": job_header,
        "registry": reg,
        "stats": {
            "open": len(open_items),
            "overdue": overdue,
            "stale": stale,
            "selections_open": len(selections),
            "predicted": len(predicted),
            "waiting": sum(len(v) for v in waiting.values()),
            "recently_completed": sum(len(v) for v in recent.values()),
            "sub_red_count": sub_signals["red_count"],
        },
        "what_changed": what_changed,
        "execution_2wk": exec_rows,
        "execution_predicted": predicted,
        "sub_signals": sub_signals,
        "coordination_4wk": coord_rows,
        "procurement_8wk": job_proc,
        "items_by_category": grouped,
        "waiting_on_others": waiting,
        "selections": selections,
        "client_decisions": client_decisions,
        "issues_financial": issues_fin,
        "walk_areas": walk_areas,
        "hold_points": hold_points,
        "recently_completed": recent,
        "thresholds": dict(ctx.thresholds or {}),
    }


def build_pm_packet_bundle(ctx: RenderContext, pm: str, tracking: dict) -> dict:
    """PM aggregator. Builds office + site once, then constructs N job
    bundles + a PM-level summary. The render template iterates jobs[]
    and renders each as a job-document."""
    if pm not in PM_NAMES:
        raise KeyError(f"Unknown PM: {pm}")
    pm_jobs = ctx.pm_to_jobs.get(pm, [])
    pm_first = pm.split()[0]

    office = build_office_meeting_bundle(ctx, pm, tracking)
    site = build_site_meeting_bundle(ctx, pm, tracking)

    job_bundles: list[dict] = []
    for j in pm_jobs:
        job_bundles.append(build_job_bundle(ctx, j, tracking, office=office, site=site))

    # Aggregate PM stats from job bundles
    total_open = sum(jb["stats"]["open"] for jb in job_bundles)
    total_overdue = sum(jb["stats"]["overdue"] for jb in job_bundles)
    total_stale = sum(jb["stats"]["stale"] for jb in job_bundles)
    total_selections = sum(jb["stats"]["selections_open"] for jb in job_bundles)
    total_escalations = sum(len(jb["issues_financial"]["escalations"]) for jb in job_bundles)
    subs_red_pm = sum(1 for s in office["sub_signals"]["active"] if s.get("status") == "RED")

    # Aggregate what_changed across PM (sum the job-level diffs)
    pm_what_changed = {"new": 0, "new_by_cat": {}, "closed": 0, "escalated": 0, "waiting": 0}
    for jb in job_bundles:
        wc = jb["what_changed"]
        pm_what_changed["new"] += wc.get("new", 0)
        pm_what_changed["closed"] += wc.get("closed", 0)
        pm_what_changed["escalated"] += wc.get("escalated", 0)
        pm_what_changed["waiting"] += wc.get("waiting", 0)
        for cat, n in (wc.get("new_by_cat") or {}).items():
            pm_what_changed["new_by_cat"][cat] = pm_what_changed["new_by_cat"].get(cat, 0) + n

    return {
        "kind": "pm-packet",
        "pm": pm,
        "pm_slug": PM_SLUGS[pm],
        "today": ctx.today,
        "summary": {
            "total_jobs": len(pm_jobs),
            "total_open": total_open,
            "total_overdue": total_overdue,
            "total_stale": total_stale,
            "total_selections_open": total_selections,
            "total_escalations": total_escalations,
            "subs_red_pm": subs_red_pm,
            "what_changed": pm_what_changed,
        },
        "jobs": job_bundles,
        "thresholds": dict(ctx.thresholds or {}),
    }


def render_job_document(ctx: RenderContext, job_slug: str, tracking: dict) -> str:
    job_entry = slug_to_job(ctx, job_slug)
    if job_entry is None:
        raise KeyError(f"Unknown job slug: {job_slug}")
    bundle = build_job_bundle(ctx, job_entry["name"], tracking)
    return render_template(JOB_TEMPLATE, bundle)


def render_pm_packet(ctx: RenderContext, pm_slug: str, tracking: dict) -> str:
    """Phase 13 — single unified PM packet (no office/site mode)."""
    if pm_slug not in SLUG_TO_PM:
        raise KeyError(f"Unknown PM slug: {pm_slug}")
    pm = SLUG_TO_PM[pm_slug]
    bundle = build_pm_packet_bundle(ctx, pm, tracking)
    return render_template(PM_PACKET_TEMPLATE, bundle)
