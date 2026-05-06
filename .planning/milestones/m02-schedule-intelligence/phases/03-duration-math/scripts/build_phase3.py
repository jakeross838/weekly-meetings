#!/usr/bin/env python3
"""
Phase 3 — Duration Math (Burst + Density)

Replaces span-based duration with burst-segmented active-day duration for every
(sub × phase × job) combination. Density becomes the headline metric.

Outputs:
  - data/bursts.json
  - data/phase-instances-v2.json
  - data/phase-medians.json
  - data/burst-retags.md
  - data/keyword-gaps-proposals.md
"""

from __future__ import annotations

import json
import re
import sys
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(r"C:/Users/Jake/weekly-meetings")
DATA = ROOT / "data"
CONFIG = ROOT / "config"
PHASE_DIR = ROOT / ".planning/milestones/m02-schedule-intelligence/phases/03-duration-math"
DAILY_LOGS = Path(r"C:/Users/Jake/buildertrend-scraper/data/daily-logs.json")

DERIVED_V2 = DATA / "derived-phases-v2.json"
PHASE_INSTANCES_V1 = DATA / "phase-instances.json"
PHASE_KEYWORDS = CONFIG / "phase-keywords.yaml"
PHASE_TAXONOMY = CONFIG / "phase-taxonomy.yaml"
CROSS_TRADE = CONFIG / "cross-trade-rejections.yaml"

OUT_BURSTS = DATA / "bursts.json"
OUT_INSTANCES = DATA / "phase-instances-v2.json"
OUT_MEDIANS = DATA / "phase-medians.json"
OUT_RETAGS = DATA / "burst-retags.md"
OUT_KEYWORDS = DATA / "keyword-gaps-proposals.md"
OUT_VERIFY = PHASE_DIR / "VERIFICATION.md"

TODAY = date(2026, 4, 29)
ONGOING_WINDOW_DAYS = 14


# ---------------------------------------------------------------------------
# Working-day arithmetic
# ---------------------------------------------------------------------------

def working_days_between(d1: date, d2: date) -> int:
    """Number of working days strictly between d1 and d2 (Mon=0..Sun=6).

    Counts weekdays in the open interval (d1, d2). E.g. Mon → next Mon is 4
    working days between (Tue/Wed/Thu/Fri). The kickoff says:
      Mon→Sat: 5 working days gap → does NOT end burst   (gap rule ≥6)
      Mon→Mon (next week): 5 working days gap → does NOT end
      Mon→Tue (week+): 6 working days gap → ends burst
    Validate that arithmetic.

    Mon(0) → Tue next-week(8 days later): the working days strictly between
    are Tue/Wed/Thu/Fri/Mon → 5. Mon → Tue+1week-ish:
    Let's interpret 'gap of ≥6 working days between consecutive logs' as the
    number of working days that fall *between* them exclusive of both endpoints,
    plus one — i.e. the standard count of intervening business days.
    """
    if d2 <= d1:
        return 0
    days = 0
    cur = d1 + timedelta(days=1)
    while cur < d2:
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return days


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(text)


# ---------------------------------------------------------------------------
# Density tier
# ---------------------------------------------------------------------------

def density_tier(density: float) -> str:
    if density >= 0.80:
        return "continuous"
    if density >= 0.60:
        return "steady"
    if density >= 0.40:
        return "scattered"
    return "dragging"


# ---------------------------------------------------------------------------
# Phase 1 keyword library — compile for retag matching
# ---------------------------------------------------------------------------

def compile_keyword_library(keywords_yaml: dict):
    """Compile a list of (code, name, regex, specificity) tuples.

    Specificity = pattern length (longer/more-token patterns win).
    """
    compiled = []
    for entry in keywords_yaml.get("phases", []):
        code = entry.get("code")
        name = entry.get("name")
        for kw in entry.get("keywords", []) or []:
            try:
                pat = re.compile(kw, flags=re.IGNORECASE)
            except re.error:
                continue
            compiled.append({
                "code": code,
                "name": name,
                "pattern_text": kw,
                "regex": pat,
                "specificity": len(kw),
            })
    return compiled


# ---------------------------------------------------------------------------
# Cross-trade allowlist helpers
# ---------------------------------------------------------------------------

def expand_phase_groups(cross_trade: dict) -> dict:
    return {k: [str(c) for c in v] for k, v in cross_trade.get("phase_groups", {}).items()}


def get_modal_trade(sub: str, derived_records, force_modal_map: dict) -> str | None:
    """Compute modal_trade for a sub. Use force_modal_trade override if present.

    Otherwise compute from highest-frequency category among `high` confidence
    records assigned to this sub.
    """
    if sub in force_modal_map:
        return force_modal_map[sub].get("modal")
    counts = Counter()
    for r in derived_records:
        if r.get("sub") == sub and r.get("classification_confidence") == "high":
            cat = r.get("primary_category")
            if cat:
                counts[cat] += 1
    if not counts:
        return None
    # Map primary_category to modal_trade keyword
    cat_to_modal = {
        "plumbing": "plumbing",
        "electrical": "electrical",
        "tile": "tile_floor",
        "concrete": "concrete",
        "stucco": "stucco_plaster",
        "pool": "pool_spa",
        "waterproofing": "waterproofing",
        "paint": "paint",
        "roofing": "roofing",
        "hvac": "hvac",
        "drywall": "drywall",
        "framing": "framing",
        "siding": "siding",
        "cabinetry": "cabinetry",
        "trim": "trim_finish",
        "stone": "stone_counters",
        "metal": "metal_fab",
    }
    top_cat, _ = counts.most_common(1)[0]
    return cat_to_modal.get(top_cat, top_cat)


def is_phase_allowed_for_sub(
    sub: str,
    phase_code: str,
    modal_trade: str | None,
    cross_trade: dict,
    phase_groups: dict,
    log_text: str = "",
) -> tuple[bool, str]:
    """Return (allowed, reason). Mirrors classifier's logic."""
    allowlist = cross_trade.get("multi_trade_allowlist", {}).get(sub, {})
    # Internal crew never rejected
    if allowlist.get("allow_all"):
        return True, "allow_all"
    # Forbidden by modal
    if not modal_trade:
        return True, "no_modal_no_reject"
    rules = cross_trade.get("modal_trade_rejections", {}).get(modal_trade)
    if not rules:
        return True, "no_rule_for_modal"
    forbidden_codes = set()
    for entry in rules.get("forbidden", []):
        s = str(entry)
        if s.startswith("all_") and s in phase_groups:
            forbidden_codes.update(phase_groups[s])
        else:
            forbidden_codes.add(s)
    if phase_code not in forbidden_codes:
        return True, "not_forbidden_by_modal"
    # In forbidden — check allowlist
    allowed_codes = {str(c) for c in allowlist.get("allow", [])}
    if phase_code in allowed_codes:
        # Check conditional codes
        conditionals = allowlist.get("conditional_codes", []) or []
        for cond in conditionals:
            if str(cond.get("code")) == phase_code:
                # require_keyword check
                kws = cond.get("require_keyword", [])
                if not any(re.search(k, log_text, flags=re.IGNORECASE) for k in kws):
                    return False, f"conditional_keyword_missing for {phase_code}"
                else:
                    return True, "conditional_keyword_satisfied"
        return True, "allowlisted"
    return False, "modal_forbidden_no_allowlist_override"


# ---------------------------------------------------------------------------
# Job short-name canonicalization (Phase 2 strip address suffixes)
# ---------------------------------------------------------------------------

def short_job(job: str) -> str:
    if not job:
        return job
    # Phase 2 used the part before the first hyphen
    return job.split("-")[0].strip()


# ---------------------------------------------------------------------------
# Burst detection
# ---------------------------------------------------------------------------

GAP_THRESHOLD_WORKING_DAYS = 6


def detect_bursts(dates: list[date]):
    """Given a sorted list of distinct dates (active days), return list of
    bursts. Each burst is (first_date, last_date, list_of_active_dates).

    A burst ends when the working-day gap between two consecutive distinct
    log dates is ≥6.
    """
    if not dates:
        return []
    dates = sorted(set(dates))
    bursts = []
    cur_start = dates[0]
    cur_dates = [dates[0]]
    for prev, nxt in zip(dates, dates[1:]):
        gap = working_days_between(prev, nxt)
        if gap >= GAP_THRESHOLD_WORKING_DAYS:
            bursts.append((cur_start, prev, cur_dates[:]))
            cur_start = nxt
            cur_dates = [nxt]
        else:
            cur_dates.append(nxt)
    bursts.append((cur_start, cur_dates[-1], cur_dates))
    return bursts


def merge_short_bursts_if_total_lt_3(burst_list, total_active_days):
    """If a (sub × phase × job) combo has <3 total active days and the gap rule
    would split them, treat the whole thing as 1 burst.
    """
    if total_active_days < 3 and len(burst_list) > 1:
        all_dates = []
        for _, _, ds in burst_list:
            all_dates.extend(ds)
        all_dates = sorted(set(all_dates))
        return [(all_dates[0], all_dates[-1], all_dates)]
    return burst_list


# ---------------------------------------------------------------------------
# Build aggregate burst data
# ---------------------------------------------------------------------------

def build_bursts_for_records(records, taxonomy):
    """Walk records grouped by (sub, phase_code, job_short) and build bursts.

    Each record can have multiple derived_phase_codes — emit one row per code.
    """
    # group: (sub, phase_code, job) -> list of (date, log_id, record_ref)
    groups: dict[tuple[str, str, str], list[tuple[date, str, dict]]] = defaultdict(list)
    for rec in records:
        sub = rec.get("sub")
        if not sub:
            continue
        codes = rec.get("derived_phase_codes") or []
        if not codes:
            continue
        log_id = rec.get("logId")
        log_date = rec.get("log_date")
        if not log_date:
            continue
        try:
            d = parse_date(log_date)
        except Exception:
            continue
        job = short_job(rec.get("job_short") or rec.get("job") or "")
        if not job:
            continue
        for code in codes:
            groups[(sub, str(code), job)].append((d, log_id, rec))

    # Build phase code → name from taxonomy
    code_to_phase = {p["code"]: p for p in taxonomy.get("phases", [])}

    burst_records = []
    burst_id_counter = 1
    # Track all bursts indexed by (sub, code, job) so we can later assign retags
    bursts_by_combo: dict[tuple[str, str, str], list[dict]] = {}
    flagged_drops = []

    for combo, items in groups.items():
        sub, code, job = combo
        items.sort(key=lambda x: x[0])
        # Distinct active dates
        date_to_records = defaultdict(list)
        for d, lid, rec in items:
            date_to_records[d].append((lid, rec))
        active_dates = sorted(date_to_records.keys())

        burst_list = detect_bursts(active_dates)
        burst_list = merge_short_bursts_if_total_lt_3(burst_list, len(active_dates))

        local_bursts = []
        for i, (first_d, last_d, ds) in enumerate(burst_list, start=1):
            span_days = (last_d - first_d).days + 1
            active = len(ds)
            density = active / span_days if span_days > 0 else 1.0
            # collect log ids and texts
            log_ids = []
            log_records = []
            for d in ds:
                for lid, rec in date_to_records[d]:
                    log_ids.append(lid)
                    log_records.append(rec)
            tier = density_tier(density)
            phase_name = code_to_phase.get(code, {}).get("name") or ""
            stage = code_to_phase.get(code, {}).get("stage")
            stage_name = code_to_phase.get(code, {}).get("stage_name")

            burst = {
                "burst_id": burst_id_counter,
                "sub": sub,
                "phase_code": code,
                "phase_name": phase_name,
                "stage": stage,
                "stage_name": stage_name,
                "job_id": job,
                "burst_index": i,
                "first_log": first_d.isoformat(),
                "last_log": last_d.isoformat(),
                "active_days": active,
                "span_days": span_days,
                "density": round(density, 4),
                "density_tier": tier,
                "log_count": len(log_ids),
                "log_ids": log_ids,
                "_log_records": log_records,  # internal — stripped before write
            }
            burst_id_counter += 1
            local_bursts.append(burst)
            burst_records.append(burst)

        bursts_by_combo[combo] = local_bursts

    return burst_records, bursts_by_combo, flagged_drops


# ---------------------------------------------------------------------------
# Cross-stage retag
# ---------------------------------------------------------------------------

def _sub_token_set(sub: str) -> set:
    """Tokens of the sub name useful for line matching. Drop generic words."""
    drop = {"llc", "inc", "the", "a", "of", "and", "co", "company", "corp",
            "services", "service", "construction", "constructors", "builders",
            "build", "industries", "group", "and"}
    toks = re.findall(r"[A-Za-z][A-Za-z']+", sub)
    return {t.lower() for t in toks if len(t) >= 4 and t.lower() not in drop}


def aggregate_burst_text(burst, daily_logs_index):
    """Aggregate text strictly relevant to this sub's burst.

    Prefer:
      1. matched_keywords from Phase 1 (already trade-specific text)
      2. parent_group_activities (tag-level signal)
      3. activity (single-day banner)
      4. lines from notes_full that explicitly mention the sub by name

    Fall back to notes_sample only if nothing else is available; that's
    noisy because for low_review records the full activity summary is dumped
    there and would pull in OTHER subs.
    """
    sub = burst.get("sub", "")
    sub_tokens = _sub_token_set(sub)
    parts = []
    has_strong_evidence = False
    for rec in burst.get("_log_records", []):
        # 1. Phase 1 high-confidence text matches — only count if the prefix
        #    is "text" (not pass3_modal / rule1_modal / tag_disambiguated).
        #    These matched_keywords look like "6.1::plumbing rough in".
        mks = rec.get("matched_keywords") or []
        ms = rec.get("match_source") or ""
        for mk in mks:
            if "::" in mk:
                prefix, _, txt = mk.partition("::")
                # Skip tag-based / modal-based entries — they pull activity
                # field text which contains other subs' work.
                if prefix in ("rule1_modal", "pass3_modal", "tag_modal", "tag_disambiguated"):
                    continue
                if ms == "text" and rec.get("classification_confidence") == "high":
                    parts.append(txt)
                    has_strong_evidence = True

        # 2. Sub-specific lines from notes_full — strongest signal
        lid = rec.get("logId")
        if not lid:
            continue
        log = daily_logs_index.get(str(lid))
        if not log:
            continue
        nf = log.get("notes_full") or ""
        if not nf or not sub_tokens:
            continue
        sub_lines = []
        for line in nf.split("\n"):
            ll = line.lower()
            # Skip "Daily Manpower Log" / "Number of Crews on site" header
            # lines that just enumerate crews — they pull in OTHER subs' names.
            if (re.search(r"daily\s+manpower\s+log", ll) or
                    re.search(r"number\s+of\s+crews", ll) or
                    re.search(r"absent\s*\(?", ll) or
                    re.search(r"^\s*total\s+work\s+force", ll) or
                    ll.strip().startswith("activity summary")):
                continue
            if any(tok in ll for tok in sub_tokens):
                sub_lines.append(line.strip())
        if sub_lines:
            parts.append(" ".join(sub_lines))
            has_strong_evidence = True

    return " ".join(parts), has_strong_evidence


def score_text_against_library(text: str, kw_lib):
    """For each phase code, count distinct keyword pattern matches × specificity.

    Returns dict[code] -> {score, name, hits}.
    """
    by_code: dict[str, dict] = {}
    if not text:
        return by_code
    for kw in kw_lib:
        if kw["regex"].search(text):
            slot = by_code.setdefault(kw["code"], {
                "code": kw["code"],
                "name": kw["name"],
                "score": 0.0,
                "hits": [],
            })
            slot["score"] += kw["specificity"]
            slot["hits"].append(kw["pattern_text"])
    return by_code


def has_high_conf_log_in_burst(burst):
    for rec in burst.get("_log_records", []):
        if rec.get("classification_confidence") == "high":
            return True
    return False


def perform_retag_pass(
    bursts_by_combo,
    daily_logs_index,
    kw_lib,
    cross_trade,
    phase_groups,
    derived_records,
    force_modal_map,
    require_text_signal,
):
    """For multi-burst phase instances where any two consecutive bursts are
    >60 days apart, run retag check on each burst.

    Returns list of retag log entries.
    """
    retag_log = []
    sub_modals: dict[str, str | None] = {}

    def get_modal(sub):
        if sub not in sub_modals:
            sub_modals[sub] = get_modal_trade(sub, derived_records, force_modal_map)
        return sub_modals[sub]

    for combo, bursts in bursts_by_combo.items():
        if len(bursts) < 2:
            continue
        # Check at least one >60 day gap between any two bursts (chronological)
        bursts_sorted = sorted(bursts, key=lambda b: b["first_log"])
        long_gap = False
        for a, b in zip(bursts_sorted, bursts_sorted[1:]):
            ga = (parse_date(b["first_log"]) - parse_date(a["last_log"])).days
            if ga > 60:
                long_gap = True
                break
        if not long_gap:
            continue

        for b in bursts_sorted:
            current_code = b["phase_code"]
            sub = b["sub"]
            # Block if any log in burst was high-confidence Phase 1
            if has_high_conf_log_in_burst(b):
                continue
            text, has_strong = aggregate_burst_text(b, daily_logs_index)
            if not has_strong:
                # No sub-specific text or matched_keywords from Phase 1 — skip
                # to avoid retagging based on cross-sub noise from a daily log.
                continue
            scores = score_text_against_library(text, kw_lib)
            if not scores:
                continue
            # Best other vs current
            current_score = scores.get(current_code, {}).get("score", 0.0)
            others = sorted(
                ((c, s) for c, s in scores.items() if c != current_code),
                key=lambda x: x[1]["score"],
                reverse=True,
            )
            if not others:
                continue
            best_code, best_slot = others[0]
            best_score = best_slot["score"]
            if current_score == 0:
                # Burst's current code has no keyword evidence at all in the
                # aggregated text — retag if best_other has meaningful
                # specificity (avoid 1-shot generic catches like 'east side').
                if best_score < 12:
                    continue
                ratio = float("inf")
            else:
                ratio = best_score / current_score
                if ratio < 0.80:
                    continue
                # Prevent retag from a more-specific to a less-specific code
                # when both fire — keep the original.
                if best_score < 12:
                    continue

            # Build sample text
            sample = (text[:280] + "…") if len(text) > 280 else text

            # Block: require_text_signal — new phase requires explicit text match
            if best_code in require_text_signal:
                # Must have explicit hit; the score loop already confirms a
                # keyword match in aggregated text — so the signal exists.
                pass

            # Strict gate: target phase must be in sub's allowlist if they have one,
            # else must be reachable per modal-trade rules. Cross-trade retags are
            # generally forbidden — a waterproofing sub being retagged to "windows"
            # is nonsense. Only retag within the sub's documented multi-trade scope.
            allowlist = cross_trade.get("multi_trade_allowlist", {}).get(sub, {})
            if not allowlist.get("allow_all", False):
                allowed_codes = {str(c) for c in allowlist.get("allow", [])}
                if allowed_codes and best_code not in allowed_codes:
                    retag_log.append({
                        "burst_id": b["burst_id"],
                        "sub": sub,
                        "job_id": b["job_id"],
                        "old_code": current_code,
                        "old_name": b["phase_name"],
                        "new_code": best_code,
                        "new_name": best_slot["name"],
                        "first": b["first_log"],
                        "last": b["last_log"],
                        "active_days": b["active_days"],
                        "current_score": current_score,
                        "new_score": best_score,
                        "ratio": ratio,
                        "status": "BLOCKED_outside_sub_scope",
                        "block_reason": f"{best_code} not in {sub} allowlist",
                        "sample_text": (text[:280] + "…") if len(text) > 280 else text,
                        "matched_keywords": best_slot["hits"][:5],
                    })
                    continue

            # Block: cross-trade allowlist via modal rules
            modal = get_modal(sub)
            allowed, reason = is_phase_allowed_for_sub(
                sub, best_code, modal, cross_trade, phase_groups, text
            )
            if not allowed:
                retag_log.append({
                    "burst_id": b["burst_id"],
                    "sub": sub,
                    "job_id": b["job_id"],
                    "old_code": current_code,
                    "old_name": b["phase_name"],
                    "new_code": best_code,
                    "new_name": best_slot["name"],
                    "first": b["first_log"],
                    "last": b["last_log"],
                    "active_days": b["active_days"],
                    "current_score": current_score,
                    "new_score": best_score,
                    "ratio": ratio,
                    "status": "BLOCKED_allowlist",
                    "block_reason": reason,
                    "sample_text": sample,
                    "matched_keywords": best_slot["hits"][:5],
                })
                continue

            # Apply retag
            old_code, old_name = current_code, b["phase_name"]
            b["_retag_from"] = old_code
            b["_retag_from_name"] = old_name
            b["phase_code"] = best_code
            b["phase_name"] = best_slot["name"]
            # update stage from taxonomy if available — but we can also just
            # leave; we'll re-assign on instance build.
            retag_log.append({
                "burst_id": b["burst_id"],
                "sub": sub,
                "job_id": b["job_id"],
                "old_code": old_code,
                "old_name": old_name,
                "new_code": best_code,
                "new_name": best_slot["name"],
                "first": b["first_log"],
                "last": b["last_log"],
                "active_days": b["active_days"],
                "current_score": current_score,
                "new_score": best_score,
                "ratio": ratio,
                "status": "APPLIED",
                "block_reason": None,
                "sample_text": sample,
                "matched_keywords": best_slot["hits"][:5],
            })

    return retag_log


# ---------------------------------------------------------------------------
# Instance aggregation
# ---------------------------------------------------------------------------

def build_phase_instances(burst_records, code_to_phase, phase_instances_v1, derived_records):
    """Aggregate bursts to (job × phase_code) phase instances.

    Each instance has:
      bursts[], burst_count, total_active_days, total_span_days,
      weighted_density, primary_density, status, density_tier,
      subs_involved, predecessors/successors, predecessors_complete,
      successors_started.
    """
    # group bursts by (job, phase_code) AFTER any retags applied (b["phase_code"] reflects retag)
    job_phase_bursts: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for b in burst_records:
        key = (b["job_id"], b["phase_code"])
        job_phase_bursts[key].append(b)

    # Index existing v1 instance for keeping inspection_name etc.
    v1_index: dict[tuple[str, str], dict] = {}
    for inst in phase_instances_v1.get("instances", []):
        v1_index[(inst["job"], inst["phase_code"])] = inst

    # Index of all (job × phase) presence for predecessor/successor calc
    all_codes_by_job: dict[str, set] = defaultdict(set)
    for (job, code) in job_phase_bursts.keys():
        all_codes_by_job[job].add(code)

    # Index of (job × phase) → last_log_date for successor_started
    last_log_by_job_phase: dict[tuple[str, str], date] = {}
    first_log_by_job_phase: dict[tuple[str, str], date] = {}
    for key, bursts in job_phase_bursts.items():
        last_log_by_job_phase[key] = max(parse_date(b["last_log"]) for b in bursts)
        first_log_by_job_phase[key] = min(parse_date(b["first_log"]) for b in bursts)

    instances = []
    for (job, code), bursts in sorted(job_phase_bursts.items()):
        bursts_sorted = sorted(bursts, key=lambda b: b["first_log"])
        # Reindex burst_index per (job, code) after retag
        for i, b in enumerate(bursts_sorted, start=1):
            b["burst_index"] = i

        first_log = min(parse_date(b["first_log"]) for b in bursts_sorted)
        last_log = max(parse_date(b["last_log"]) for b in bursts_sorted)
        # total_active_days — distinct dates across all bursts
        active_set = set()
        for b in bursts_sorted:
            f = parse_date(b["first_log"])
            l = parse_date(b["last_log"])
            # distinct dates are not stored on burst; derive from log_records
            for rec in b.get("_log_records", []):
                ld = rec.get("log_date")
                if ld:
                    active_set.add(parse_date(ld))
        total_active_days = len(active_set)
        total_span_days = (last_log - first_log).days + 1

        sum_active = sum(b["active_days"] for b in bursts_sorted)
        sum_active_density = sum(b["active_days"] * b["density"] for b in bursts_sorted)
        weighted_density = sum_active_density / sum_active if sum_active > 0 else 0.0
        # primary_density = density of largest burst by active days
        primary_burst = max(bursts_sorted, key=lambda b: b["active_days"])
        primary_density = primary_burst["density"]

        # Status: ongoing if last log within 14d, else complete
        days_since_last = (TODAY - last_log).days
        status = "ongoing" if days_since_last <= ONGOING_WINDOW_DAYS else "complete"

        # Subs involved
        sub_active: dict[str, set] = defaultdict(set)
        sub_logs: dict[str, int] = defaultdict(int)
        sub_density_acc: dict[str, list] = defaultdict(list)
        for b in bursts_sorted:
            for rec in b.get("_log_records", []):
                ld = rec.get("log_date")
                if ld:
                    sub_active[b["sub"]].add(ld)
                sub_logs[b["sub"]] += 1
            # weighted average
            sub_density_acc[b["sub"]].append((b["active_days"], b["density"]))
        subs_involved = []
        for sub, dates in sub_active.items():
            tot = 0
            wsum = 0.0
            wsum_active = 0
            for ad, dd in sub_density_acc[sub]:
                tot += ad
                wsum += ad * dd
                wsum_active += ad
            sub_dens = wsum / wsum_active if wsum_active else 0.0
            subs_involved.append({
                "sub": sub,
                "active_days": len(dates),
                "log_count": sub_logs[sub],
                "density": round(sub_dens, 4),
                "density_tier": density_tier(sub_dens),
            })
        subs_involved.sort(key=lambda x: -x["active_days"])

        # Phase metadata
        phase_meta = code_to_phase.get(code, {})
        # Predecessors
        predecessors = phase_meta.get("predecessors", []) or []
        successors = phase_meta.get("successors", []) or []
        # Predecessors_complete: every predecessor has logs and last_log < first_log of this phase
        pred_complete = True
        pred_missing = []
        for p in predecessors:
            if p not in all_codes_by_job[job]:
                pred_missing.append(p)
                pred_complete = False
            else:
                p_last = last_log_by_job_phase.get((job, p))
                if p_last is None or p_last > first_log:
                    pred_complete = False
        successors_started = []
        for s in successors:
            if s in all_codes_by_job[job]:
                s_first = first_log_by_job_phase.get((job, s))
                if s_first is not None and s_first >= first_log:
                    successors_started.append(s)

        # Confidence breakdown across all logs in instance
        breakdown = Counter()
        for b in bursts_sorted:
            for rec in b.get("_log_records", []):
                cb = rec.get("classification_confidence") or "unknown"
                breakdown[cb] += 1

        # Build burst dicts for output
        out_bursts = []
        for b in bursts_sorted:
            ob = {
                "burst_id": b["burst_id"],
                "burst_index": b["burst_index"],
                "first": b["first_log"],
                "last": b["last_log"],
                "active": b["active_days"],
                "span": b["span_days"],
                "density": round(b["density"], 4),
                "density_tier": b["density_tier"],
                "log_count": b["log_count"],
                "sub": b["sub"],
            }
            if b.get("_retag_from"):
                ob["retagged_from"] = b["_retag_from"]
                ob["retagged_from_name"] = b.get("_retag_from_name")
            out_bursts.append(ob)

        v1 = v1_index.get((job, code), {})

        inst = {
            "job": job,
            "phase_code": code,
            "phase_name": phase_meta.get("name") or v1.get("phase_name") or "",
            "stage": phase_meta.get("stage") or v1.get("stage"),
            "stage_name": phase_meta.get("stage_name") or v1.get("stage_name"),
            "category": phase_meta.get("category") or v1.get("category"),
            "status": status,
            "first_log_date": first_log.isoformat(),
            "last_log_date": last_log.isoformat(),
            "days_since_last": days_since_last,
            "log_count": sum(b["log_count"] for b in bursts_sorted),

            "bursts": out_bursts,
            "burst_count": len(bursts_sorted),
            "total_active_days": total_active_days,
            "total_span_days": total_span_days,
            "weighted_density": round(weighted_density, 4),
            "weighted_density_tier": density_tier(weighted_density),
            "primary_density": round(primary_density, 4),
            "primary_density_tier": density_tier(primary_density),

            "subs_involved": subs_involved,
            "predecessors": predecessors,
            "successors": successors,
            "predecessors_complete": pred_complete,
            "predecessors_missing": pred_missing,
            "successors_started": successors_started,
            "requires_inspection": phase_meta.get("requires_inspection"),
            "inspection_name": phase_meta.get("inspection_name"),
            "confidence_breakdown": dict(breakdown),
        }
        instances.append(inst)
    return instances


# ---------------------------------------------------------------------------
# Phase medians (Schedule Builder feed)
# ---------------------------------------------------------------------------

def build_phase_medians(instances, code_to_phase):
    by_code: dict[str, list] = defaultdict(list)
    for inst in instances:
        if inst["status"] != "complete":
            continue
        by_code[inst["phase_code"]].append(inst)

    def percentile(values, p):
        if not values:
            return None
        s = sorted(values)
        if len(s) == 1:
            return s[0]
        k = (len(s) - 1) * p
        f = int(k)
        c = min(f + 1, len(s) - 1)
        if f == c:
            return s[int(k)]
        return s[f] + (s[c] - s[f]) * (k - f)

    medians = []
    for code, insts in sorted(by_code.items()):
        # Per-job rollup: each job contributes once
        per_job: dict[str, dict] = {}
        for inst in insts:
            per_job[inst["job"]] = inst
        actives = [i["total_active_days"] for i in per_job.values()]
        spans = [i["total_span_days"] for i in per_job.values()]
        densities = [i["weighted_density"] for i in per_job.values()]
        burst_counts = [i["burst_count"] for i in per_job.values()]
        sample_size = len(per_job)
        if sample_size >= 5:
            confidence = "high"
        elif sample_size >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        # Subs
        sub_data: dict[str, dict] = defaultdict(lambda: {"active": [], "density": [], "jobs": set()})
        for inst in per_job.values():
            for s in inst["subs_involved"]:
                key = s["sub"]
                sub_data[key]["active"].append(s["active_days"])
                sub_data[key]["density"].append(s["density"])
                sub_data[key]["jobs"].add(inst["job"])
        subs = []
        for sub, d in sub_data.items():
            subs.append({
                "sub": sub,
                "median_active": round(statistics.median(d["active"]), 2) if d["active"] else None,
                "median_density": round(statistics.median(d["density"]), 4) if d["density"] else None,
                "jobs": len(d["jobs"]),
            })
        subs.sort(key=lambda x: -x["jobs"])
        subs = subs[:5]

        phase_meta = code_to_phase.get(code, {})
        med_density = round(statistics.median(densities), 4) if densities else 0.0
        rec = {
            "phase_code": code,
            "phase_name": phase_meta.get("name"),
            "stage": phase_meta.get("stage"),
            "stage_name": phase_meta.get("stage_name"),
            "median_active_days": round(statistics.median(actives), 2) if actives else None,
            "median_span_days": round(statistics.median(spans), 2) if spans else None,
            "median_density": med_density,
            "median_density_tier": density_tier(med_density),
            "median_burst_count": round(statistics.median(burst_counts), 2) if burst_counts else None,
            "active_range_p25_p75": [
                round(percentile(actives, 0.25), 2) if actives else None,
                round(percentile(actives, 0.75), 2) if actives else None,
            ],
            "sample_size": sample_size,
            "confidence": confidence,
            "subs": subs,
        }
        medians.append(rec)
    return medians


# ---------------------------------------------------------------------------
# Library expansion proposals
# ---------------------------------------------------------------------------

TARGET_PHASES_FOR_EXPANSION = {
    "5.1": {
        "name": "Exterior Wall Sheathing & Wrap",
        "anchors": [r"\bsheathing\b", r"\bwrap\b", r"\btyvek\b", r"weather barrier", r"WRB\b", r"zip\s*system"],
        "sample_terms": [r"OSB", r"plywood\s+wall", r"\bWRB\b", r"\btyvek\b", r"flashing\s+tape"],
    },
    "7.1": {
        "name": "Stucco Lath / Wire",
        "anchors": [r"\blath\b", r"\bwire\s+lath", r"paper\s+and\s+wire", r"stucco\s+wire"],
        "sample_terms": [r"\blath", r"\bwire", r"\bpaper", r"\bnetting", r"\bmesh"],
    },
    "12.1": {
        "name": "Caulk & Putty",
        "anchors": [r"\bcaulk", r"\bputty", r"\bnail\s+holes?\b", r"fill\s+voids?", r"sealant"],
        "sample_terms": [r"\bcaulk", r"\bputty", r"\bnail\s+hole", r"\bfill\b.*\bhole"],
    },
    "12.3": {
        "name": "Paint Trim & Doors",
        "anchors": [r"paint.{0,15}(trim|door|baseboard|casing)", r"trim\s+paint", r"door\s+paint"],
        "sample_terms": [r"\bspraying\s+(doors|trim|cabinets)", r"baseboard\s+paint"],
    },
    "13.1": {
        "name": "Plumbing Trim",
        "anchors": [r"set\s+(toilet|sink|tub|faucet|fixture)", r"plumb(ing)?\s+trim", r"\bfaucet"],
        "sample_terms": [r"\btoilet\b.*\binstall", r"\bvanity\s+sink", r"\bbathroom\s+fixture"],
    },
    "13.2": {
        "name": "Gas Trim",
        "anchors": [r"gas\s+trim", r"connect\s+gas", r"gas\s+test", r"hook\s+up\s+gas"],
        "sample_terms": [r"gas\s+(line|hookup|stub|test)", r"propane\s+(connect|test)"],
    },
    "13.3": {
        "name": "Electrical Trim",
        "anchors": [r"install\s+(outlet|switch|receptacle|fixture)", r"trim.{0,3}out\s+elec",
                    r"electrical\s+trim", r"set\s+(outlet|switch|panel)"],
        "sample_terms": [r"\boutlet", r"\bswitch", r"\bfixture", r"\breceptacle"],
    },
}


def mine_library_gaps(records, target_phases):
    """For each target phase, find low_review records whose text suggests the
    phase. Surface most-common 2-5 word phrases, propose patterns.
    """
    phrase_counter: dict[str, Counter] = {code: Counter() for code in target_phases}
    sample_lines: dict[str, list] = {code: [] for code in target_phases}
    affected_record_ids: dict[str, set] = {code: set() for code in target_phases}

    for rec in records:
        if rec.get("classification_confidence") not in ("low_review", "manual_review"):
            continue
        text = (rec.get("notes_sample") or "") + " " + (rec.get("activity") or "") + " " + " ".join(rec.get("parent_group_activities") or [])
        if not text.strip():
            continue
        text_l = text.lower()
        for code, meta in target_phases.items():
            anchors = meta.get("anchors", [])
            if any(re.search(a, text_l, flags=re.IGNORECASE) for a in anchors):
                affected_record_ids[code].add(rec.get("logId"))
                if len(sample_lines[code]) < 8:
                    sample_lines[code].append({
                        "logId": rec.get("logId"),
                        "sub": rec.get("sub"),
                        "job_short": rec.get("job_short"),
                        "log_date": rec.get("log_date"),
                        "notes_sample": (rec.get("notes_sample") or "")[:280],
                        "activity": rec.get("activity"),
                    })
                # Mine phrases — sliding window 2-3 words containing anchor token
                tokens = re.findall(r"[A-Za-z][A-Za-z'/-]+", text)
                lowered = [t.lower() for t in tokens]
                for n in (2, 3):
                    for i in range(len(lowered) - n + 1):
                        phrase = " ".join(lowered[i:i+n])
                        if any(re.search(a, phrase, flags=re.IGNORECASE) for a in anchors):
                            phrase_counter[code][phrase] += 1
    return phrase_counter, sample_lines, affected_record_ids


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def fmt_pct(d):
    if d is None:
        return "—"
    return f"{int(round(d * 100))}%"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("loading inputs…")
    derived = load_json(DERIVED_V2)
    records = derived["records"]
    phase_instances_v1 = load_json(PHASE_INSTANCES_V1)
    keywords_yaml = load_yaml(PHASE_KEYWORDS)
    taxonomy = load_yaml(PHASE_TAXONOMY)
    cross_trade = load_yaml(CROSS_TRADE)
    daily = load_json(DAILY_LOGS)

    # Build daily logs index by logId for retag text retrieval
    daily_logs_index: dict[str, dict] = {}
    for job_name, log_list in daily.get("byJob", {}).items():
        for log in log_list:
            lid = str(log.get("logId"))
            daily_logs_index[lid] = log

    code_to_phase = {p["code"]: p for p in taxonomy.get("phases", [])}
    kw_lib = compile_keyword_library(keywords_yaml)
    phase_groups = expand_phase_groups(cross_trade)
    force_modal_map = cross_trade.get("force_modal_trade", {}) or {}
    require_text_signal = {str(c) for c in cross_trade.get("require_text_signal", []) or []}

    print(f"  records: {len(records)}")
    print(f"  instances v1: {len(phase_instances_v1.get('instances', []))}")
    print(f"  keywords compiled: {len(kw_lib)}")
    print(f"  daily logs indexed: {len(daily_logs_index)}")

    print("step 1: detecting bursts…")
    burst_records, bursts_by_combo, dropped = build_bursts_for_records(records, taxonomy)
    print(f"  detected {len(burst_records)} bursts across {len(bursts_by_combo)} (sub × phase × job) combos")

    print("step 2: cross-stage retag…")
    retag_log = perform_retag_pass(
        bursts_by_combo,
        daily_logs_index,
        kw_lib,
        cross_trade,
        phase_groups,
        records,
        force_modal_map,
        require_text_signal,
    )
    applied = sum(1 for r in retag_log if r["status"] == "APPLIED")
    blocked = sum(1 for r in retag_log if r["status"].startswith("BLOCKED"))
    print(f"  retags: {applied} applied, {blocked} blocked")

    print("step 3: aggregating to instances…")
    instances = build_phase_instances(burst_records, code_to_phase, phase_instances_v1, records)
    print(f"  {len(instances)} instances")

    print("step 4: aggregating phase medians…")
    medians = build_phase_medians(instances, code_to_phase)
    print(f"  {len(medians)} phase median records")

    print("step 6: mining library gaps…")
    phrase_counter, sample_lines, affected_records = mine_library_gaps(
        records, TARGET_PHASES_FOR_EXPANSION
    )

    # ---------------- Write bursts.json (strip internal fields) -------------
    cleaned_bursts = []
    for b in burst_records:
        cb = {k: v for k, v in b.items() if not k.startswith("_")}
        cleaned_bursts.append(cb)
    write_json(OUT_BURSTS, {
        "generated_at": TODAY.isoformat(),
        "total_bursts": len(cleaned_bursts),
        "gap_threshold_working_days": GAP_THRESHOLD_WORKING_DAYS,
        "bursts": cleaned_bursts,
    })

    # ---------------- Write phase-instances-v2.json -------------------------
    write_json(OUT_INSTANCES, {
        "generated_at": TODAY.isoformat(),
        "total_instances": len(instances),
        "today": TODAY.isoformat(),
        "instances": instances,
    })

    # ---------------- Write phase-medians.json ------------------------------
    write_json(OUT_MEDIANS, {
        "generated_at": TODAY.isoformat(),
        "total_phases": len(medians),
        "medians": medians,
    })

    # ---------------- Write burst-retags.md ---------------------------------
    rt_lines = ["# Burst Retags — Cross-Stage Retag Log",
                "",
                f"Generated: {TODAY.isoformat()}",
                "",
                f"Total retag candidates evaluated: {len(retag_log)}",
                f"  Applied: {applied}",
                f"  Blocked: {blocked}",
                "",
                "Rules:",
                "- Retag candidate when burst is in a multi-burst phase with >60d gap between bursts.",
                "- Aggregate burst text → run through phase-keywords.yaml.",
                "- Retag if best other phase score / current phase score >= 0.80.",
                "- Block if any log in burst was Phase 1 high-confidence.",
                "- Block if new phase violates sub's allowlist in cross-trade-rejections.yaml.",
                "",
                "---",
                ""]
    for entry in sorted(retag_log, key=lambda r: (r["sub"], r["job_id"], r["first"])):
        rt_lines.append(f"## {entry['status']}: {entry['sub']} @ {entry['job_id']}")
        rt_lines.append("")
        rt_lines.append(f"- Burst: {entry['first']} → {entry['last']} ({entry['active_days']} active days)")
        rt_lines.append(f"- Old phase: {entry['old_code']} {entry['old_name']}")
        rt_lines.append(f"- New phase: {entry['new_code']} {entry['new_name']}")
        rt_lines.append(f"- Scores: current={entry['current_score']:.0f}, new={entry['new_score']:.0f}, ratio={entry['ratio']:.2f}")
        rt_lines.append(f"- Matched keywords: `{', '.join(entry['matched_keywords'])}`")
        if entry.get("block_reason"):
            rt_lines.append(f"- Block reason: {entry['block_reason']}")
        rt_lines.append("")
        rt_lines.append("Sample text:")
        rt_lines.append("> " + entry["sample_text"].replace("\n", " "))
        rt_lines.append("")
        rt_lines.append("---")
        rt_lines.append("")
    write_text(OUT_RETAGS, "\n".join(rt_lines))

    # ---------------- Write keyword-gaps-proposals.md -----------------------
    kg_lines = ["# Keyword Library Gap Proposals",
                "",
                f"Generated: {TODAY.isoformat()}",
                "",
                "Proposals only — DO NOT auto-apply. Awaits Jake's review.",
                "",
                "Each section: target phase, proposed regex pattern(s) + sample text from low_review/manual_review records that would graduate.",
                "",
                "---",
                ""]
    total_uplift = 0
    for code, meta in TARGET_PHASES_FOR_EXPANSION.items():
        kg_lines.append(f"## {code} {meta['name']}")
        kg_lines.append("")
        affected = affected_records[code]
        kg_lines.append(f"Estimated uplift if pattern adopted: {len(affected)} low_review/manual_review records would graduate.")
        kg_lines.append("")
        kg_lines.append("**Top phrases observed (by frequency):**")
        kg_lines.append("")
        top = phrase_counter[code].most_common(15)
        if not top:
            kg_lines.append("- (no phrases mined — anchor pattern matched 0 low_review records)")
        else:
            for phrase, cnt in top:
                kg_lines.append(f"- `{phrase}` × {cnt}")
        kg_lines.append("")
        kg_lines.append("**Proposed regex patterns:**")
        kg_lines.append("")
        for term in meta["sample_terms"]:
            kg_lines.append(f"- `{term}`")
        kg_lines.append("")
        kg_lines.append("**Sample low_review/manual_review log lines that would graduate:**")
        kg_lines.append("")
        for s in sample_lines[code]:
            kg_lines.append(f"- [{s['logId']}] {s['sub']} @ {s['job_short']} ({s['log_date']}) — {s['notes_sample']}")
        kg_lines.append("")
        kg_lines.append("---")
        kg_lines.append("")
        total_uplift += len(affected)
    kg_lines.append(f"\n**Total estimated uplift across 7 phases:** {total_uplift} records.")
    write_text(OUT_KEYWORDS, "\n".join(kg_lines))

    # ---------------- Save state for verification ---------------------------
    state = {
        "burst_records": cleaned_bursts,
        "instances": instances,
        "medians": medians,
        "retag_log": retag_log,
        "phrase_counter_keys": {k: dict(v.most_common(15)) for k, v in phrase_counter.items()},
        "affected_records": {k: list(v) for k, v in affected_records.items()},
        "total_keyword_uplift": total_uplift,
        "applied_retags": applied,
        "blocked_retags": blocked,
    }
    state_path = PHASE_DIR / "scripts" / "_phase3_state.json"
    write_json(state_path, state)
    print(f"  state saved to {state_path}")

    print("done.")


if __name__ == "__main__":
    main()
