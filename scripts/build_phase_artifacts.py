"""Phase 2 build script — generates derived-phases-v2, phase-instances, job-stages,
sequencing-audit from the taxonomy YAML + Phase 1 classified records.

Reads:
  config/phase-taxonomy.yaml
  config/phase-keywords.yaml
  data/derived-phases.json

Writes:
  data/derived-phases-v2.json
  data/phase-instances.json
  data/job-stages.json
  data/sequencing-audit.md
  .planning/milestones/m02-schedule-intelligence/phases/02-build-sequence/VERIFICATION.md

All paths absolute. Today is 2026-04-29.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(r"C:\Users\Jake\weekly-meetings")
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
PHASE_DIR = ROOT / ".planning" / "milestones" / "m02-schedule-intelligence" / "phases" / "02-build-sequence"

TODAY = date(2026, 4, 29)

# 11 active jobs + Johnson if present (from system memory) + Field Crew, Biales (small).
ACTIVE_JOBS_SHORT = {"Fish", "Pou", "Dewberry", "Harllee", "Krauss", "Ruthven",
                     "Drummond", "Molinari", "Biales", "Markgraf", "Clark"}


def short_name_from_job(job_full: str) -> str:
    """Convert "Pou-109 Seagrape Ln" -> "Pou". """
    if "-" in job_full:
        return job_full.split("-", 1)[0].strip()
    if job_full.startswith("Field Crew"):
        return "FieldCrew"
    return job_full.strip()


def parse_log_date(s: str) -> date | None:
    """Parse the daily-log date string. Two formats observed:
        "Thu, Apr 23"          -> 2026 (current run)
        "Mon, Dec 29, 2025"    -> 2025
    Defaults to today's year (2026) when year is absent.
    """
    s = s.strip()
    # Try with year first
    m = re.match(r"^[A-Za-z]+,\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$", s)
    if m:
        month, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        try:
            return datetime.strptime(f"{month} {day} {year}", "%b %d %Y").date()
        except ValueError:
            return None
    # Try without year — assume current year
    m = re.match(r"^[A-Za-z]+,\s*([A-Za-z]+)\s+(\d{1,2})$", s)
    if m:
        month, day = m.group(1), int(m.group(2))
        for yr in (TODAY.year, TODAY.year - 1):
            try:
                d = datetime.strptime(f"{month} {day} {yr}", "%b %d %Y").date()
                # Date should be within reasonable bounds
                if (TODAY - d).days <= 60 and d <= TODAY + timedelta(days=14):
                    return d
            except ValueError:
                continue
        # Fall back to current year even if it's slightly future
        try:
            return datetime.strptime(f"{month} {day} {TODAY.year}", "%b %d %Y").date()
        except ValueError:
            return None
    return None


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def main() -> None:
    taxonomy_yaml = load_yaml(CONFIG_DIR / "phase-taxonomy.yaml")
    keywords_yaml = load_yaml(CONFIG_DIR / "phase-keywords.yaml")
    derived = load_json(DATA_DIR / "derived-phases.json")

    # Build taxonomy index
    taxonomy = {p["code"]: p for p in taxonomy_yaml["phases"]}

    # ─────────────────────────────────────────────────────────────────────
    # Step 2a — Canonicalize: ensure predecessor/successor symmetry.
    # We treat the union of forward + reverse declarations as the truth.
    # Each pred/succ list ends up sorted (string-sort by tuple of int parts).
    # ─────────────────────────────────────────────────────────────────────
    def code_sort_key(c: str):
        try:
            return tuple(int(p) for p in c.split("."))
        except ValueError:
            return (99,)

    # Collect all edges (direction-aware).
    forward_edges: set[tuple[str, str]] = set()
    for code, entry in taxonomy.items():
        for succ in (entry.get("successors") or []):
            if succ in taxonomy:
                forward_edges.add((code, succ))
        for pred in (entry.get("predecessors") or []):
            if pred in taxonomy:
                forward_edges.add((pred, code))

    # Rebuild successors and predecessors from this single source of truth.
    new_succ: dict[str, set[str]] = defaultdict(set)
    new_pred: dict[str, set[str]] = defaultdict(set)
    for u, v in forward_edges:
        new_succ[u].add(v)
        new_pred[v].add(u)
    for code, entry in taxonomy.items():
        entry["successors"] = sorted(new_succ.get(code, set()), key=code_sort_key)
        entry["predecessors"] = sorted(new_pred.get(code, set()), key=code_sort_key)

    # ─────────────────────────────────────────────────────────────────────
    # Step 2b — Validate dependency graph
    # ─────────────────────────────────────────────────────────────────────
    graph_violations = {"missing_predecessor": [],
                        "asymmetric_predecessor": [],
                        "asymmetric_successor": [],
                        "cycles": [],
                        "orphans": []}
    keyword_codes = {p["code"] for p in keywords_yaml["phases"]}
    taxonomy_codes = set(taxonomy.keys())
    for kc in keyword_codes:
        if kc not in taxonomy_codes:
            graph_violations["orphans"].append(kc)

    # Symmetry check
    for code, entry in taxonomy.items():
        for pred in entry.get("predecessors", []) or []:
            if pred not in taxonomy:
                graph_violations["missing_predecessor"].append((code, pred))
                continue
            pred_succ = taxonomy[pred].get("successors", []) or []
            if code not in pred_succ:
                graph_violations["asymmetric_predecessor"].append((code, pred))
        for succ in entry.get("successors", []) or []:
            if succ not in taxonomy:
                graph_violations["missing_predecessor"].append((code, succ))
                continue
            succ_pred = taxonomy[succ].get("predecessors", []) or []
            if code not in succ_pred:
                graph_violations["asymmetric_successor"].append((code, succ))

    # Cycle check via DFS
    def find_cycles():
        cycles = []
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {c: WHITE for c in taxonomy}
        path = []

        def dfs(u):
            color[u] = GRAY
            path.append(u)
            for v in (taxonomy[u].get("successors") or []):
                if v not in taxonomy:
                    continue
                if color[v] == GRAY:
                    cycles.append(path[path.index(v):] + [v])
                elif color[v] == WHITE:
                    dfs(v)
            path.pop()
            color[u] = BLACK

        for u in list(taxonomy.keys()):
            if color[u] == WHITE:
                dfs(u)
        return cycles

    graph_violations["cycles"] = find_cycles()

    # Roots / terminus
    roots = sorted([c for c, e in taxonomy.items() if not (e.get("predecessors") or [])])
    terminus = sorted([c for c, e in taxonomy.items() if not (e.get("successors") or [])])

    # ─────────────────────────────────────────────────────────────────────
    # Step 3 — Bind classified logs to taxonomy
    # ─────────────────────────────────────────────────────────────────────
    records = derived["records"]
    enriched = []
    unresolved = Counter()
    for r in records:
        codes = r.get("derived_phase_codes") or []
        binds = []
        for c in codes:
            entry = taxonomy.get(c)
            if entry:
                binds.append({
                    "code": c,
                    "name": entry["name"],
                    "stage": entry["stage"],
                    "stage_name": entry["stage_name"],
                    "category": entry["category"],
                })
            else:
                unresolved[c] += 1
        new_r = dict(r)
        # Job short-name
        new_r["job_short"] = short_name_from_job(r["job"])
        # Resolved log_date
        new_r["log_date"] = str(parse_log_date(r["date"]) or "")
        new_r["taxonomy_bindings"] = binds
        new_r["unresolved_codes"] = [c for c in codes if c not in taxonomy]
        # Convenience: flatten primary stage
        if binds:
            new_r["primary_stage"] = binds[0]["stage"]
            new_r["primary_stage_name"] = binds[0]["stage_name"]
            new_r["primary_category"] = binds[0]["category"]
        else:
            new_r["primary_stage"] = None
            new_r["primary_stage_name"] = None
            new_r["primary_category"] = None
        enriched.append(new_r)

    out_v2 = {
        "generated_at": str(TODAY),
        "source": "Phase 2 — taxonomy bind",
        "v1_source": str(DATA_DIR / "derived-phases.json"),
        "total_records": len(enriched),
        "unresolved_code_counts": dict(unresolved),
        "records": enriched,
    }
    save_json(DATA_DIR / "derived-phases-v2.json", out_v2)

    # ─────────────────────────────────────────────────────────────────────
    # Step 1 cont. — populate typical_subs from high + tag_disambiguated
    # ─────────────────────────────────────────────────────────────────────
    HIGH_CONF = {"high", "tag_disambiguated"}
    typical = defaultdict(Counter)
    for r in enriched:
        if r.get("classification_confidence") not in HIGH_CONF:
            continue
        sub = r.get("sub")
        if not sub:
            continue
        for code in r.get("derived_phase_codes") or []:
            typical[code][sub] += 1
    # Inject into taxonomy for write-back
    for code, counter in typical.items():
        if code in taxonomy:
            top = [{"sub": s, "log_count": n}
                   for s, n in counter.most_common() if n >= 3]
            taxonomy[code]["typical_subs"] = top[:8]
    # Reset codes with no qualifying subs
    for code, entry in taxonomy.items():
        if code not in typical or not entry.get("typical_subs"):
            entry["typical_subs"] = []
    # Re-write taxonomy YAML with populated subs + canonicalized graph
    out_yaml = {
        "phases": list(taxonomy.values()),
        "metadata": {
            "total_phases": len(taxonomy),
            "stage_count": len(set(p["stage"] for p in taxonomy.values())),
            "source_spec": ".planning/milestones/m02-schedule-intelligence/SPEC.md PART 3 (lines 121-241)",
            "source_keywords": "config/phase-keywords.yaml",
            "generated_at": str(TODAY),
            "notes": [
                "SPEC PART 3 enumerates 84 distinct phase codes across 15 stages (1.1–15.6, omitting 3.6 'Repeat 3.1-3.5' which is a directive not a phase).",
                "Every phase code in the keyword library resolves to one entry here. No orphans.",
                "typical_subs is populated at runtime from data/derived-phases.json by scripts/build_phase_artifacts.py — high + tag_disambiguated only, ≥3 logs.",
                "Roots: 1.1 + 1.2 (no predecessors). Terminus: 15.6 (no successors).",
                "Stage 3 cycles (3.1–3.5 per level) are flattened to a single linear graph; multi-level repetition is handled by the burst detector in Phase 4, not by graph cycles.",
                "Predecessor / successor lists are auto-symmetrized by the build script. Both directions of every edge are present.",
            ],
            "category_taxonomy": [
                "waterproofing", "plumbing", "electrical", "concrete", "framing",
                "stucco_plaster", "siding", "drywall", "tile_floor", "paint",
                "pool_spa", "landscape", "roofing", "cabinetry", "stone_counters",
                "metal_fab", "hvac", "audio_video", "interior_design", "cleaning",
                "inspection", "permit", "materials_supplier", "solar_energy",
                "elevator", "internal_crew", "other",
            ],
        },
    }
    with (CONFIG_DIR / "phase-taxonomy.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(out_yaml, f, sort_keys=False, default_flow_style=False, width=120, allow_unicode=True)

    # ─────────────────────────────────────────────────────────────────────
    # Step 4 — Build per-job phase instances
    # ─────────────────────────────────────────────────────────────────────
    # Group records by (job_short, code) — fan out one record per code
    inst_buckets: dict[tuple[str, str], list] = defaultdict(list)
    for r in enriched:
        if not r.get("log_date"):
            continue
        for code in r.get("derived_phase_codes") or []:
            if code not in taxonomy:
                continue
            inst_buckets[(r["job_short"], code)].append(r)

    instances = []
    for (job, code), rs in inst_buckets.items():
        dates = [datetime.strptime(r["log_date"], "%Y-%m-%d").date()
                 for r in rs if r.get("log_date")]
        if not dates:
            continue
        first, last = min(dates), max(dates)
        active_set = set(dates)
        active_days = len(active_set)
        span_days = (last - first).days + 1
        density = round(active_days / span_days, 3) if span_days > 0 else None
        days_since_last = (TODAY - last).days
        if days_since_last <= 14:
            status = "ongoing"
        else:
            status = "complete"
        # Confidence breakdown
        conf_counter = Counter(r.get("classification_confidence", "unknown") for r in rs)
        high_conf_count = conf_counter.get("high", 0) + conf_counter.get("tag_disambiguated", 0)
        # Confidence quality: high (≥50% high+tag) / mixed (≥25% high+tag) / low (else)
        if len(rs) > 0 and high_conf_count / len(rs) >= 0.5:
            evidence_quality = "high"
        elif len(rs) > 0 and high_conf_count / len(rs) >= 0.25:
            evidence_quality = "mixed"
        else:
            evidence_quality = "low"
        # Subs involved
        sub_counter = Counter()
        sub_dates: dict[str, set] = defaultdict(set)
        for r in rs:
            if r.get("sub"):
                sub_counter[r["sub"]] += 1
                if r.get("log_date"):
                    sub_dates[r["sub"]].add(r["log_date"])
        subs_involved = [{"sub": s, "log_count": n, "active_days": len(sub_dates[s])}
                         for s, n in sub_counter.most_common()]
        entry = taxonomy[code]
        instances.append({
            "job": job,
            "phase_code": code,
            "phase_name": entry["name"],
            "stage": entry["stage"],
            "stage_name": entry["stage_name"],
            "category": entry["category"],
            "status": status,
            "first_log_date": str(first),
            "last_log_date": str(last),
            "days_since_last": days_since_last,
            "active_days": active_days,
            "span_days": span_days,
            "density": density,
            "log_count": len(rs),
            "high_conf_count": high_conf_count,
            "evidence_quality": evidence_quality,
            "confidence_breakdown": dict(conf_counter),
            "subs_involved": subs_involved,
            "predecessors": entry.get("predecessors") or [],
            "successors": entry.get("successors") or [],
            "requires_inspection": entry.get("requires_inspection", False),
            "inspection_name": entry.get("inspection_name"),
        })

    # Compute predecessors_complete / successors_started
    inst_index: dict[tuple[str, str], dict] = {(i["job"], i["phase_code"]): i
                                               for i in instances}
    for inst in instances:
        preds = inst["predecessors"]
        if not preds:
            inst["predecessors_complete"] = True
            inst["predecessors_missing"] = []
        else:
            missing = []
            for p in preds:
                pi = inst_index.get((inst["job"], p))
                if not pi or pi["status"] not in ("complete",):
                    if not pi:
                        missing.append(p)
                    elif pi["status"] != "complete":
                        # Ongoing predecessor counts as not complete
                        missing.append(p)
            inst["predecessors_complete"] = len(missing) == 0
            inst["predecessors_missing"] = missing
        succs = inst["successors"]
        started = []
        for s in succs:
            si = inst_index.get((inst["job"], s))
            if si:
                started.append(s)
        inst["successors_started"] = started

    save_json(DATA_DIR / "phase-instances.json", {
        "generated_at": str(TODAY),
        "total_instances": len(instances),
        "instances": instances,
    })

    # ─────────────────────────────────────────────────────────────────────
    # Step 5 — Job stage detection
    # ─────────────────────────────────────────────────────────────────────
    job_stages = {}
    instances_by_job: dict[str, list] = defaultdict(list)
    for inst in instances:
        instances_by_job[inst["job"]].append(inst)

    for job, j_inst in instances_by_job.items():
        # current_stage = highest stage that has SUSTAINED + HIGH-EVIDENCE activity
        # AND is either ongoing or completed within 30 days. This guards against
        # classifier-noise false-positives in late stages (e.g., Pass-3-modal
        # "Ross Built Crew" hits creating phantom 15.1 Punch Walk records).
        # Tie-breaking rule: when multiple stages have evidence, take the highest
        # stage IF it has ≥30% of the leading stage's log volume; otherwise prefer
        # the leading-volume stage. This blocks classification noise (low log
        # count at a high stage) from incorrectly advancing the current_stage.
        recent_thresh = TODAY - timedelta(days=30)
        ongoing = [i for i in j_inst if i["status"] == "ongoing"]
        complete_recent = [i for i in j_inst
                           if i["status"] == "complete"
                           and datetime.strptime(i["last_log_date"], "%Y-%m-%d").date() >= recent_thresh]
        # Sustained: ≥3 logs OR ≥3 active days. Evidence: ≥3 high+tag logs OR
        # evidence_quality == 'high'.
        def is_sustained(inst):
            return inst.get("log_count", 0) >= 3 or inst.get("active_days", 0) >= 3
        def has_evidence(inst):
            return (inst.get("high_conf_count", 0) >= 3
                    or inst.get("evidence_quality") == "high")

        candidates = ongoing + complete_recent
        strong_candidates = [c for c in candidates
                             if is_sustained(c) and has_evidence(c)]

        def pick_stage(insts):
            """Pick stage by highest stage that has ≥30% of leading-stage log volume."""
            if not insts:
                return None
            # Sum log_count per stage
            stage_logs: dict[int, int] = defaultdict(int)
            for c in insts:
                stage_logs[c["stage"]] += c.get("log_count", 0)
            if not stage_logs:
                return None
            leader_logs = max(stage_logs.values())
            threshold = leader_logs * 0.3
            qualifying = [s for s, n in stage_logs.items() if n >= threshold]
            return max(qualifying) if qualifying else max(stage_logs.keys())

        if strong_candidates:
            current_stage = pick_stage(strong_candidates)
        elif candidates:
            current_stage = pick_stage(candidates)
        elif j_inst:
            current_stage = pick_stage(j_inst)
        else:
            current_stage = None
        # Stage name
        stage_phases_at_current = [t for t in taxonomy.values() if t["stage"] == current_stage]
        current_stage_name = stage_phases_at_current[0]["stage_name"] if stage_phases_at_current else None
        # Most recent completion
        completes = [i for i in j_inst if i["status"] == "complete"]
        if completes:
            mrc = max(completes, key=lambda x: x["last_log_date"])
            most_recent_completion = {
                "phase_code": mrc["phase_code"],
                "phase_name": mrc["phase_name"],
                "last_log_date": mrc["last_log_date"],
                "stage": mrc["stage"],
            }
        else:
            most_recent_completion = None
        ongoing_phases = [{"phase_code": i["phase_code"],
                          "phase_name": i["phase_name"],
                          "stage": i["stage"],
                          "first_log_date": i["first_log_date"],
                          "last_log_date": i["last_log_date"],
                          "active_days": i["active_days"],
                          "span_days": i["span_days"],
                          "density": i["density"]}
                         for i in sorted(ongoing, key=lambda x: x["stage"])]
        job_stages[job] = {
            "job_short": job,
            "current_stage": current_stage,
            "current_stage_name": current_stage_name,
            "ongoing_phases": ongoing_phases,
            "most_recent_completion": most_recent_completion,
            "co_target": None,    # Not in source
            "phase_instance_count": len(j_inst),
            "ongoing_count": len(ongoing),
            "complete_count": len([i for i in j_inst if i["status"] == "complete"]),
        }

    save_json(DATA_DIR / "job-stages.json", {
        "generated_at": str(TODAY),
        "today": str(TODAY),
        "jobs": job_stages,
    })

    # ─────────────────────────────────────────────────────────────────────
    # Step 6 — Sequencing audit
    # ─────────────────────────────────────────────────────────────────────
    audit_lines = []
    audit_lines.append(f"# Sequencing Audit — generated {TODAY}")
    audit_lines.append("")
    audit_lines.append(f"Today: {TODAY}. 'ongoing' = log within 14d. 'complete' = last log >14d ago.")
    audit_lines.append("")

    # We'll surface anomalies per active job.
    all_anomalies = []  # for global ranking
    severity_rank = {"critical": 3, "warn": 2, "info": 1}

    # Flat list of all active job names from data, intersected with intent set
    active_jobs_present = sorted(j for j in instances_by_job.keys() if j in ACTIVE_JOBS_SHORT)

    for job in active_jobs_present:
        j_inst = instances_by_job[job]
        ongoing = [i for i in j_inst if i["status"] == "ongoing"]
        # Walk each anomaly type
        anomalies = []

        # Out of order: phase X complete and successor Y also has logs but Y's first_log_date < X's last_log_date
        # Skip if either side is low-evidence (≤2 logs OR evidence_quality == low) — likely misclassification.
        # Skip Stage 1 entirely — site grading / fencing / surveying overlap is normal.
        def low_evidence(inst):
            return (inst.get("log_count", 0) <= 2
                    or inst.get("evidence_quality") == "low")
        for inst in j_inst:
            if inst["stage"] == 1:
                continue
            if low_evidence(inst):
                continue
            for s in inst["successors"]:
                si = inst_index.get((job, s))
                if not si:
                    continue
                if low_evidence(si):
                    continue
                pred_last = datetime.strptime(inst["last_log_date"], "%Y-%m-%d").date()
                succ_first = datetime.strptime(si["first_log_date"], "%Y-%m-%d").date()
                # Out of order means successor first_log is BEFORE predecessor's last_log
                # by enough gap (>30d) that the overlap wasn't normal staged work.
                if inst["status"] == "complete" and succ_first < pred_last - timedelta(days=30):
                    severity = "warn" if (pred_last - succ_first).days > 60 else "info"
                    anomalies.append({
                        "type": "out_of_order",
                        "severity": severity,
                        "phase": inst["phase_code"],
                        "successor": s,
                        "msg": f"{inst['phase_code']} {inst['phase_name']} complete but successor {s} {si['phase_name']} first logged {si['first_log_date']} (before {inst['phase_code']}'s last log {inst['last_log_date']})",
                    })

        # Predecessor not yet logged: ongoing phase X has predecessor Y with no logs at all
        for inst in ongoing:
            # Skip low-evidence ongoing phases — single-log classifier hits.
            if inst.get("log_count", 0) < 3:
                continue
            if inst.get("evidence_quality") == "low":
                continue
            for p in inst["predecessors"]:
                pi = inst_index.get((job, p))
                if not pi:
                    # Predecessor unstarted
                    pred_entry = taxonomy.get(p)
                    if not pred_entry:
                        continue
                    # Skip permits/inspections we don't track via logs reliably
                    if pred_entry["category"] in ("permit", "inspection"):
                        continue
                    anomalies.append({
                        "type": "predecessor_missing",
                        "severity": "warn",
                        "phase": inst["phase_code"],
                        "predecessor": p,
                        "msg": f"{inst['phase_code']} {inst['phase_name']} ongoing but predecessor {p} {pred_entry['name']} has no logs",
                    })

        # Density flag: ongoing phase with span_days >14, density < 0.4, AND ≥3 active days.
        # Density-based density flags only fire when there's enough data to trust them.
        for inst in ongoing:
            if (inst["span_days"] > 14
                and inst["active_days"] >= 3
                and inst["density"] is not None
                and inst["density"] < 0.4):
                sev = "warn" if inst["density"] < 0.3 else "info"
                anomalies.append({
                    "type": "low_density",
                    "severity": sev,
                    "phase": inst["phase_code"],
                    "msg": f"{inst['phase_code']} {inst['phase_name']} ongoing {inst['span_days']}d span, {inst['active_days']}d active, density {int(inst['density']*100)}%",
                })

        # Skipped phase: X complete, X has a single successor Y, Y has no logs but Y's successors do.
        # Require X to have ≥5 logs and at least one downstream phase to have ≥3 logs.
        for inst in j_inst:
            if inst["status"] != "complete":
                continue
            if inst.get("log_count", 0) < 5:
                continue
            if len(inst["successors"]) != 1:
                continue
            sole = inst["successors"][0]
            if (job, sole) in inst_index:
                continue
            sole_entry = taxonomy.get(sole)
            if not sole_entry:
                continue
            if sole_entry["category"] in ("permit", "inspection"):
                continue
            sole_succ = sole_entry.get("successors") or []
            grand_with_evidence = [ss for ss in sole_succ
                                   if (job, ss) in inst_index
                                   and inst_index[(job, ss)].get("log_count", 0) >= 3]
            if grand_with_evidence:
                anomalies.append({
                    "type": "skipped_phase",
                    "severity": "info",
                    "phase": inst["phase_code"],
                    "skipped": sole,
                    "msg": f"{inst['phase_code']} {inst['phase_name']} complete, sole successor {sole} {sole_entry['name']} has no logs (downstream {grand_with_evidence} have logs)",
                })

        # Emit section
        js = job_stages[job]
        audit_lines.append(f"## {job}")
        audit_lines.append("")
        audit_lines.append(f"- Current stage: {js['current_stage']} {js['current_stage_name']}")
        audit_lines.append(f"- Ongoing phases: {len(js['ongoing_phases'])}")
        if js["most_recent_completion"]:
            mrc = js["most_recent_completion"]
            audit_lines.append(f"- Most recent completion: {mrc['phase_code']} {mrc['phase_name']} @ {mrc['last_log_date']}")
        else:
            audit_lines.append(f"- Most recent completion: —")
        audit_lines.append("")
        if not anomalies:
            audit_lines.append("No sequencing anomalies surfaced.")
            audit_lines.append("")
            continue
        # Sort anomalies by severity desc
        anomalies.sort(key=lambda a: -severity_rank.get(a["severity"], 0))
        audit_lines.append(f"Anomalies ({len(anomalies)}):")
        audit_lines.append("")
        for a in anomalies:
            sev_icon = {"critical": "[CRIT]", "warn": "[WARN]", "info": "[INFO]"}[a["severity"]]
            audit_lines.append(f"- {sev_icon} {a['type']}: {a['msg']}")
            all_anomalies.append({**a, "job": job})
        audit_lines.append("")

    # Top-level rank for verification
    all_anomalies.sort(key=lambda a: (-severity_rank.get(a["severity"], 0), a["job"], a["phase"]))

    # Save audit
    (DATA_DIR / "sequencing-audit.md").write_text("\n".join(audit_lines), encoding="utf-8")

    # ─────────────────────────────────────────────────────────────────────
    # VERIFICATION.md
    # ─────────────────────────────────────────────────────────────────────
    ver = []
    ver.append(f"# Phase 2 — VERIFICATION")
    ver.append("")
    ver.append(f"Generated: {TODAY}.")
    ver.append("")

    # 1. Taxonomy completeness
    ver.append("## 1. Taxonomy completeness")
    ver.append("")
    ver.append(f"- Phase codes in keyword library: {len(keyword_codes)}")
    ver.append(f"- Phase codes in taxonomy: {len(taxonomy)}")
    ver.append(f"- Orphans (in keyword library but not taxonomy): {len(graph_violations['orphans'])}")
    if graph_violations["orphans"]:
        for o in sorted(graph_violations["orphans"]):
            ver.append(f"    - {o}")
    else:
        ver.append("    - (none)")
    extras = sorted(taxonomy_codes - keyword_codes)
    if extras:
        ver.append(f"- Codes in taxonomy but not in keyword library (will not produce matches): {len(extras)}")
        for e in extras:
            ver.append(f"    - {e} {taxonomy[e]['name']}")
    ver.append("")
    ver.append(f"- Unresolvable codes seen in derived-phases.json: {len(unresolved)}")
    if unresolved:
        for code, n in unresolved.most_common():
            ver.append(f"    - {code}: {n} records")
    ver.append("")

    # 2. Dependency graph validation
    ver.append("## 2. Dependency graph validation")
    ver.append("")
    ver.append(f"- Roots (no predecessors): {roots}")
    ver.append(f"- Terminus (no successors): {terminus}")
    ver.append(f"- Cycles: {len(graph_violations['cycles'])}")
    if graph_violations["cycles"]:
        for c in graph_violations["cycles"]:
            ver.append(f"    - {' -> '.join(c)}")
    else:
        ver.append("    - (none)")
    ver.append(f"- Asymmetric predecessor links: {len(graph_violations['asymmetric_predecessor'])}")
    for code, pred in graph_violations["asymmetric_predecessor"]:
        ver.append(f"    - {code} lists {pred} as predecessor, but {pred}.successors does not include {code}")
    ver.append(f"- Asymmetric successor links: {len(graph_violations['asymmetric_successor'])}")
    for code, succ in graph_violations["asymmetric_successor"]:
        ver.append(f"    - {code} lists {succ} as successor, but {succ}.predecessors does not include {code}")
    ver.append(f"- Missing references: {len(graph_violations['missing_predecessor'])}")
    for code, ref in graph_violations["missing_predecessor"]:
        ver.append(f"    - {code} references {ref} which is not in taxonomy")
    ver.append("")

    # 3. Phase instance counts
    ver.append("## 3. Phase instance counts")
    ver.append("")
    ver.append(f"- Total instances: {len(instances)}")
    by_status = Counter(i["status"] for i in instances)
    ver.append(f"- By status: ongoing={by_status['ongoing']}, complete={by_status['complete']}")
    ver.append("")
    ver.append("| Stage | Stage Name | Instances | Ongoing | Complete |")
    ver.append("|---|---|---|---|---|")
    by_stage = defaultdict(lambda: {"total": 0, "ongoing": 0, "complete": 0, "name": ""})
    for inst in instances:
        s = inst["stage"]
        by_stage[s]["total"] += 1
        by_stage[s]["name"] = inst["stage_name"]
        if inst["status"] == "ongoing":
            by_stage[s]["ongoing"] += 1
        elif inst["status"] == "complete":
            by_stage[s]["complete"] += 1
    for s in sorted(by_stage.keys()):
        d = by_stage[s]
        ver.append(f"| {s} | {d['name']} | {d['total']} | {d['ongoing']} | {d['complete']} |")
    ver.append("")
    ver.append("Per-job instance counts:")
    ver.append("")
    ver.append("| Job | Instances | Ongoing | Complete | Current Stage |")
    ver.append("|---|---|---|---|---|")
    for job in sorted(instances_by_job.keys()):
        js = job_stages[job]
        ver.append(f"| {job} | {js['phase_instance_count']} | {js['ongoing_count']} | {js['complete_count']} | {js['current_stage']} {js['current_stage_name']} |")
    ver.append("")

    # 4. Markgraf full read-down
    ver.append("## 4. Markgraf full read-down")
    ver.append("")
    if "Markgraf" in job_stages:
        mk = job_stages["Markgraf"]
        ver.append(f"- Job short: {mk['job_short']}")
        ver.append(f"- Current stage: {mk['current_stage']} {mk['current_stage_name']}")
        ver.append(f"- Phase instance count: {mk['phase_instance_count']}")
        ver.append(f"- Ongoing: {mk['ongoing_count']}")
        ver.append(f"- Complete: {mk['complete_count']}")
        if mk["most_recent_completion"]:
            ver.append(f"- Most recent completion: {mk['most_recent_completion']['phase_code']} {mk['most_recent_completion']['phase_name']} @ {mk['most_recent_completion']['last_log_date']}")
        ver.append("")
        ver.append("Phase instances in stage order:")
        ver.append("")
        ver.append("| Code | Name | Stage | Status | First | Last | Active | Span | Density | Subs |")
        ver.append("|---|---|---|---|---|---|---|---|---|---|")
        mk_instances = sorted(instances_by_job["Markgraf"], key=lambda x: (x["stage"], x["phase_code"]))
        for i in mk_instances:
            top_subs = ", ".join(s["sub"] for s in i["subs_involved"][:2])
            density_str = f"{int(i['density']*100)}%" if i["density"] is not None else "—"
            ver.append(f"| {i['phase_code']} | {i['phase_name']} | {i['stage']} | {i['status']} | {i['first_log_date']} | {i['last_log_date']} | {i['active_days']} | {i['span_days']} | {density_str} | {top_subs} |")
        ver.append("")
        # Spot-checks
        coatrite_2_4 = next((i for i in mk_instances if i["phase_code"] == "2.4"), None)
        coatrite_3_1 = next((i for i in mk_instances if i["phase_code"] == "3.1"), None)
        floor_3_4 = next((i for i in mk_instances if i["phase_code"] == "3.4"), None)
        floor_3_7 = next((i for i in mk_instances if i["phase_code"] == "3.7"), None)
        punch_15_2 = next((i for i in mk_instances if i["phase_code"] == "15.2"), None)
        ver.append("Spot-checks:")
        ver.append("")
        ver.append(f"- 2.4 Stem Wall Waterproofing (CoatRite): {'present' if coatrite_2_4 else 'ABSENT'}" + (f" — subs: {[s['sub'] for s in coatrite_2_4['subs_involved'][:3]]}" if coatrite_2_4 else ""))
        ver.append(f"- 3.1 Masonry Walls: {'present' if coatrite_3_1 else 'ABSENT'}" + (f" — subs: {[s['sub'] for s in coatrite_3_1['subs_involved'][:3]]}" if coatrite_3_1 else ""))
        ver.append(f"- 3.4 Floor Truss / Floor System Set: {'present' if floor_3_4 else 'ABSENT'}" + (f" — subs: {[s['sub'] for s in floor_3_4['subs_involved'][:3]]}" if floor_3_4 else ""))
        ver.append(f"- 3.7 Roof Truss Set: {'present' if floor_3_7 else 'ABSENT'}" + (f" — subs: {[s['sub'] for s in floor_3_7['subs_involved'][:3]]}" if floor_3_7 else ""))
        ver.append(f"- 15.2 Punch Repairs: {'present' if punch_15_2 else 'ABSENT'} — status={(punch_15_2 or {}).get('status','—')}")
    ver.append("")

    # 5. Clark sequencing
    ver.append("## 5. Clark sequencing")
    ver.append("")
    if "Clark" in job_stages:
        cj = job_stages["Clark"]
        ver.append(f"- Current stage: {cj['current_stage']} {cj['current_stage_name']}")
        ver.append(f"- Ongoing phases: {[(p['phase_code'], p['phase_name']) for p in cj['ongoing_phases']]}")
        ver.append("")
        ver.append("Clark phase instances:")
        ver.append("")
        ver.append("| Code | Name | Stage | Status | First | Last | Active | Span |")
        ver.append("|---|---|---|---|---|---|---|---|")
        for i in sorted(instances_by_job.get("Clark", []), key=lambda x: (x["stage"], x["phase_code"])):
            ver.append(f"| {i['phase_code']} | {i['phase_name']} | {i['stage']} | {i['status']} | {i['first_log_date']} | {i['last_log_date']} | {i['active_days']} | {i['span_days']} |")
        ver.append("")
        # Audit excerpt
        ver.append("Clark anomaly excerpt from sequencing-audit.md:")
        ver.append("")
        clark_anoms = [a for a in all_anomalies if a["job"] == "Clark"]
        if clark_anoms:
            for a in clark_anoms:
                ver.append(f"- [{a['severity']}] {a['type']}: {a['msg']}")
        else:
            ver.append("- (no anomalies surfaced)")
    ver.append("")

    # 6. Fish sequencing audit
    ver.append("## 6. Fish sequencing audit")
    ver.append("")
    if "Fish" in job_stages:
        fj = job_stages["Fish"]
        ver.append(f"- Current stage: {fj['current_stage']} {fj['current_stage_name']}")
        ongoing_disp = [(p['phase_code'], p['phase_name'], f"{p['active_days']}d / {p['span_days']}d") for p in fj['ongoing_phases']]
        ver.append(f"- Ongoing phases: {ongoing_disp}")
        ver.append("")
        fish_anoms = [a for a in all_anomalies if a["job"] == "Fish"]
        ver.append(f"Fish anomalies ({len(fish_anoms)}):")
        ver.append("")
        for a in fish_anoms:
            ver.append(f"- [{a['severity']}] {a['type']}: {a['msg']}")
        # Watts stucco specific
        ver.append("")
        ver.append("Watts stucco read-down (Fish):")
        ver.append("")
        ver.append("| Code | Name | Status | Active | Span | Density | Top Sub |")
        ver.append("|---|---|---|---|---|---|---|")
        for code in ["7.1", "7.2", "7.3", "7.6"]:
            inst = inst_index.get(("Fish", code))
            if inst:
                top = inst["subs_involved"][0]["sub"] if inst["subs_involved"] else "—"
                density_str = f"{int(inst['density']*100)}%" if inst["density"] is not None else "—"
                ver.append(f"| {inst['phase_code']} | {inst['phase_name']} | {inst['status']} | {inst['active_days']} | {inst['span_days']} | {density_str} | {top} |")
            else:
                tname = taxonomy[code]["name"]
                ver.append(f"| {code} | {tname} | not_started | — | — | — | — |")
    ver.append("")

    # 7. Top 10 sequencing anomalies across all jobs
    ver.append("## 7. Top 10 sequencing anomalies across all jobs")
    ver.append("")
    if not all_anomalies:
        ver.append("- (no anomalies surfaced)")
    else:
        for i, a in enumerate(all_anomalies[:10], start=1):
            ver.append(f"{i}. **{a['job']}** [{a['severity']}] {a['type']}: {a['msg']}")
    ver.append("")

    (PHASE_DIR / "VERIFICATION.md").write_text("\n".join(ver), encoding="utf-8")

    # ─────────────────────────────────────────────────────────────────────
    # Print summary
    # ─────────────────────────────────────────────────────────────────────
    print("=" * 70)
    print(f"PHASE 2 BUILD — {TODAY}")
    print("=" * 70)
    print(f"Taxonomy phases:      {len(taxonomy)}")
    print(f"Stages covered:       {len(set(p['stage'] for p in taxonomy.values()))}")
    print(f"Keyword orphans:      {len(graph_violations['orphans'])}")
    print(f"Cycles:               {len(graph_violations['cycles'])}")
    print(f"Asymmetric pred:      {len(graph_violations['asymmetric_predecessor'])}")
    print(f"Asymmetric succ:      {len(graph_violations['asymmetric_successor'])}")
    print(f"Missing refs:         {len(graph_violations['missing_predecessor'])}")
    print(f"Roots:                {roots}")
    print(f"Terminus:             {terminus}")
    print(f"Total instances:      {len(instances)}")
    print(f"  ongoing:            {by_status['ongoing']}")
    print(f"  complete:           {by_status['complete']}")
    print(f"Active jobs:          {sorted(instances_by_job.keys())}")
    print()
    print("MARKGRAF:")
    if "Markgraf" in job_stages:
        mk = job_stages["Markgraf"]
        print(f"  current stage:      {mk['current_stage']} {mk['current_stage_name']}")
        print(f"  ongoing:            {[(p['phase_code'], p['phase_name']) for p in mk['ongoing_phases']]}")
        mk_anoms = [a for a in all_anomalies if a["job"] == "Markgraf"]
        print(f"  anomalies:          {len(mk_anoms)}")
        for a in mk_anoms[:5]:
            print(f"    [{a['severity']}] {a['type']}: {a['msg']}")
    print()
    print("CLARK:")
    if "Clark" in job_stages:
        cj = job_stages["Clark"]
        print(f"  current stage:      {cj['current_stage']} {cj['current_stage_name']}")
        print(f"  ongoing:            {[(p['phase_code'], p['phase_name']) for p in cj['ongoing_phases']]}")
        ck_anoms = [a for a in all_anomalies if a["job"] == "Clark"]
        print(f"  anomalies:          {len(ck_anoms)}")
        for a in ck_anoms[:5]:
            print(f"    [{a['severity']}] {a['type']}: {a['msg']}")
    print()
    print("FISH:")
    if "Fish" in job_stages:
        fj = job_stages["Fish"]
        print(f"  current stage:      {fj['current_stage']} {fj['current_stage_name']}")
        print(f"  ongoing:            {[(p['phase_code'], p['phase_name']) for p in fj['ongoing_phases']]}")
        fh_anoms = [a for a in all_anomalies if a["job"] == "Fish"]
        print(f"  anomalies:          {len(fh_anoms)}")
        for a in fh_anoms[:6]:
            print(f"    [{a['severity']}] {a['type']}: {a['msg']}")
    print()
    print("TOP 10 ANOMALIES:")
    for i, a in enumerate(all_anomalies[:10], start=1):
        print(f"  {i}. {a['job']} [{a['severity']}] {a['type']}: {a['msg']}")
    print()
    print(f"FILES WRITTEN:")
    print(f"  {CONFIG_DIR / 'phase-taxonomy.yaml'}")
    print(f"  {DATA_DIR / 'derived-phases-v2.json'}")
    print(f"  {DATA_DIR / 'phase-instances.json'}")
    print(f"  {DATA_DIR / 'job-stages.json'}")
    print(f"  {DATA_DIR / 'sequencing-audit.md'}")
    print(f"  {PHASE_DIR / 'VERIFICATION.md'}")


if __name__ == "__main__":
    main()
