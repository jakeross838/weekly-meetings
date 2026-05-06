#!/usr/bin/env python3
"""
Phase 3 — FOLLOW-UP

Three actions on top of Phase 3 first-run:
1. Apply library expansion (132 patterns across 7 target phases)
2. Add burst_role classification (primary / return / punch / pre_work)
3. Build sub × phase rollups with PM binder flag

Re-runs only affected logs / affected (sub × phase × job) burst combos.
Updates: bursts.json, phase-instances-v2.json, phase-medians.json,
         derived-phases-v2.json, sub-phase-rollups.json
"""

from __future__ import annotations

import json
import re
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
# Graduated from .planning to scripts/ on 2026-05-06 (wmp29). The only
# .planning reference was PHASE_DIR, used solely to write a debug state
# file alongside the script. State now writes next to this script in
# scripts/, preserving the side effect without keeping a stale path.
PHASE_DIR = Path(__file__).resolve().parent
DAILY_LOGS = Path(r"C:/Users/Jake/buildertrend-scraper/data/daily-logs.json")

DERIVED_V2 = DATA / "derived-phases-v2.json"
PHASE_KEYWORDS = CONFIG / "phase-keywords.yaml"
PHASE_TAXONOMY = CONFIG / "phase-taxonomy.yaml"
CROSS_TRADE = CONFIG / "cross-trade-rejections.yaml"

OUT_BURSTS = DATA / "bursts.json"
OUT_INSTANCES = DATA / "phase-instances-v2.json"
OUT_MEDIANS = DATA / "phase-medians.json"
OUT_ROLLUPS = DATA / "sub-phase-rollups.json"

TODAY = date(2026, 4, 29)
ONGOING_WINDOW_DAYS = 14
GAP_THRESHOLD_WORKING_DAYS = 6


# ---------------------------------------------------------------------------
# 132-record library expansion patterns (per keyword-gaps-proposals.md)
# ---------------------------------------------------------------------------

EXPANSION_PATTERNS = {
    "5.1": [
        r"OSB",
        r"plywood\s+wall",
        r"\bWRB\b",
        r"\btyvek\b",
        r"flashing\s+tape",
        r"column\s+wrap",
        r"beam\s+wrap",
        r"interior\s+sheathing",
    ],
    "7.1": [
        r"\blath",
        r"\bwire",
        r"\bpaper",
        r"\bnetting",
        r"\bmesh",
    ],
    "12.1": [
        r"\bcaulk",
        r"\bputty",
        r"\bnail\s+hole",
        r"\bfill\b.*\bhole",
        r"caulking\s+prep",
        r"punch\s+putty",
    ],
    "12.3": [
        r"\bspraying\s+(doors|trim|cabinets)",
        r"baseboard\s+paint",
        r"painting\s+(electrical|interior|hvac)\s+trim",
        r"painting\s+door",
        r"painting\s+door\s+hardware",
        r"paint\s+interior\s+door",
        r"paint\s+prep\s+trim",
    ],
    "13.1": [
        r"\btoilet\b.*\binstall",
        r"\bvanity\s+sink",
        r"\bbathroom\s+fixture",
        r"plumbing\s+trim\s+out",
        r"set\s+sink",
        r"trims?\s+and\s+faucets?",
        r"sink\s+faucet",
    ],
    "13.2": [
        r"gas\s+(line|hookup|stub|test)",
        r"propane\s+(connect|test)",
        r"plumbing/gas\s+trim",
        r"water\s+heater(?!\s+(electric|electrical))",
        r"gas\s+contractor\s+(was|is|were)\s+onsite",
    ],
    "13.3": [
        r"\boutlet",
        r"\bswitch",
        r"\bfixture",
        r"\breceptacle",
        r"electrical\s+trim\s+out",
        r"lighting\s+fixtures?",
        r"installing\s+(the\s+)?(last\s+of\s+(the\s+)?)?lighting",
        r"electricians?\s+(were|are|is|was)\s+onsite\s+installing",
    ],
}


# ---------------------------------------------------------------------------
# Helpers
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


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def working_days_between(d1: date, d2: date) -> int:
    if d2 <= d1:
        return 0
    days = 0
    cur = d1 + timedelta(days=1)
    while cur < d2:
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return days


def density_tier(density):
    if density is None:
        return None
    if density >= 0.80:
        return "continuous"
    if density >= 0.60:
        return "steady"
    if density >= 0.40:
        return "scattered"
    return "dragging"


def short_job(job: str) -> str:
    if not job:
        return job
    return job.split("-")[0].strip()


# ---------------------------------------------------------------------------
# STEP 1 — Library expansion
# ---------------------------------------------------------------------------

def append_expansion_patterns_to_yaml():
    """Append new patterns to config/phase-keywords.yaml.

    Read the file as text, find each target phase's keywords block, append
    new patterns under the existing list. Preserve all existing content.
    """
    text = PHASE_KEYWORDS.read_text(encoding="utf-8")

    for code, new_patterns in EXPANSION_PATTERNS.items():
        # Find the phase block: '  - code: "X.Y"' line
        # The next 'keywords:' inside this block belongs to this phase.
        # We append after the last keyword line in that block.
        # Pattern: from '- code: "code"' through to next phase or 'tag_hints:' / 'notes:'

        # Find the position
        m = re.search(r'^  - code: "' + re.escape(code) + r'"\s*$', text, flags=re.MULTILINE)
        if not m:
            print(f"  WARN: could not find code {code} block in YAML")
            continue

        block_start = m.start()
        # Find next phase block start after this one
        m2 = re.search(r'^  - code: "', text[block_start + len(m.group(0)):], flags=re.MULTILINE)
        if m2:
            block_end = block_start + len(m.group(0)) + m2.start()
        else:
            # End of phases section (might be followed by metadata)
            m3 = re.search(r'^# =+\n# STAGE', text[block_start + len(m.group(0)):], flags=re.MULTILINE)
            if m3:
                block_end = block_start + len(m.group(0)) + m3.start()
            else:
                m4 = re.search(r'^metadata:', text[block_start + len(m.group(0)):], flags=re.MULTILINE)
                block_end = block_start + len(m.group(0)) + m4.start() if m4 else len(text)

        block_text = text[block_start:block_end]

        # Find existing keywords list inside this block
        kw_m = re.search(r'^    keywords:\s*\n((?:\s+- .+\n)+)', block_text, flags=re.MULTILINE)
        if not kw_m:
            print(f"  WARN: no keywords block found for code {code}")
            continue

        existing_block = kw_m.group(1)
        # Get existing patterns (between leading spaces and end of line)
        existing_patterns = set()
        for line in existing_block.split("\n"):
            mm = re.match(r"\s+- '(.+)'$", line) or re.match(r'\s+- "(.+)"$', line)
            if mm:
                existing_patterns.add(mm.group(1))

        # Build addition lines (skip patterns already present)
        additions = []
        for p in new_patterns:
            if p not in existing_patterns:
                # Choose YAML quoting: single quotes unless the pattern contains a single quote
                if "'" in p:
                    additions.append(f'      - "{p}"')
                else:
                    additions.append(f"      - '{p}'")

        if not additions:
            print(f"  {code}: all proposed patterns already present, no additions")
            continue

        # Insert before the next non-keyword line (tag_hints/notes/etc.) inside the block
        # Splice at the end of the existing keywords list
        kw_end_in_block = kw_m.end()
        new_block_text = (
            block_text[:kw_end_in_block]
            + "\n".join(additions) + "\n"
            + block_text[kw_end_in_block:]
        )
        text = text[:block_start] + new_block_text + text[block_end:]
        print(f"  {code}: appended {len(additions)} patterns to YAML")

    PHASE_KEYWORDS.write_text(text, encoding="utf-8")
    print(f"  YAML updated at {PHASE_KEYWORDS}")


def find_affected_records(records, expansion_patterns, cross_trade, phase_groups):
    """Find low_review/manual_review/tag_disambiguated records that match any new pattern.

    Apply cross-trade rejection: if the sub's modal trade forbids the candidate
    phase AND the sub isn't allowlisted for that phase, skip the promotion.

    Returns dict[code] -> list of record indices. Each record gets the FIRST matching
    code (we don't double-count across phases).
    """
    pattern_compiled = {
        code: [re.compile(p, flags=re.IGNORECASE) for p in patterns]
        for code, patterns in expansion_patterns.items()
    }

    eligible_confidences = {"low_review", "manual_review", "tag_disambiguated"}

    # Pre-compute force-modal map and allowlist
    force_modal_map = cross_trade.get("force_modal_trade", {}) or {}
    multi_trade_allowlist = cross_trade.get("multi_trade_allowlist", {}) or {}
    modal_rejections = cross_trade.get("modal_trade_rejections", {}) or {}

    affected = defaultdict(list)
    seen_record_ids = set()
    skipped_for_modal = 0

    for idx, rec in enumerate(records):
        conf = rec.get("classification_confidence")
        if conf not in eligible_confidences:
            continue
        text = " ".join([
            rec.get("notes_sample") or "",
            rec.get("activity") or "",
            " ".join(rec.get("parent_group_activities") or []),
        ])
        if not text.strip():
            continue

        best_code = None
        best_match_len = 0
        for code, regexes in pattern_compiled.items():
            for rgx in regexes:
                m = rgx.search(text)
                if m:
                    match_len = len(m.group(0))
                    if match_len > best_match_len:
                        best_match_len = match_len
                        best_code = code
                    break

        if best_code is None:
            continue

        # Cross-trade rejection check
        sub = rec.get("sub")
        modal = None
        if sub in force_modal_map:
            modal = force_modal_map[sub].get("modal")
        else:
            modal = rec.get("modal_trade")

        if modal:
            allowlist = multi_trade_allowlist.get(sub, {}) or {}
            if not allowlist.get("allow_all"):
                # Check forbidden list for the modal trade
                rules = modal_rejections.get(modal, {}) or {}
                forbidden_codes = set()
                for entry in rules.get("forbidden", []):
                    s = str(entry)
                    if s.startswith("all_") and s in phase_groups:
                        forbidden_codes.update(phase_groups[s])
                    else:
                        forbidden_codes.add(s)
                if best_code in forbidden_codes:
                    # Check if best_code is in the sub's allowlist
                    allowed_codes = {str(c) for c in (allowlist.get("allow") or [])}
                    if best_code not in allowed_codes:
                        skipped_for_modal += 1
                        continue

        if rec.get("logId") in seen_record_ids:
            continue
        seen_record_ids.add(rec.get("logId"))
        affected[best_code].append(idx)

    if skipped_for_modal:
        print(f"  Skipped {skipped_for_modal} records due to cross-trade modal rejection")
    return affected


def reclassify_affected_records(records, affected_by_code, code_to_phase):
    """For each affected record, set derived_phase_codes=[code], confidence=high,
    and rebuild taxonomy_bindings."""
    for code, indices in affected_by_code.items():
        for idx in indices:
            rec = records[idx]
            phase_meta = code_to_phase.get(code, {})

            old_codes = rec.get("derived_phase_codes") or []
            old_conf = rec.get("classification_confidence")

            rec["derived_phase_codes"] = [code]
            rec["classification_confidence"] = "high"
            rec["match_source"] = "text"
            rec["matched_keywords"] = [f"{code}::library_expansion"]
            rec["rejected_phases"] = []

            # Rebuild taxonomy_bindings
            rec["taxonomy_bindings"] = [
                {
                    "code": code,
                    "name": phase_meta.get("name"),
                    "stage": phase_meta.get("stage"),
                    "stage_name": phase_meta.get("stage_name"),
                    "category": phase_meta.get("category"),
                }
            ]
            rec["unresolved_codes"] = []
            rec["primary_stage"] = phase_meta.get("stage")
            rec["primary_stage_name"] = phase_meta.get("stage_name")
            rec["primary_category"] = phase_meta.get("category")

            # Mark for downstream rebuild
            rec["_library_expansion_promoted"] = {
                "from_codes": old_codes,
                "from_confidence": old_conf,
                "to_code": code,
            }


def affected_combos_from_promoted(records):
    """Collect (sub, phase, job_short) combos for any promoted records.
    Also include the OLD (sub, old_phase, job_short) combos because removing
    the record from a burst there potentially changes the burst structure.
    """
    combos = set()
    for rec in records:
        promo = rec.get("_library_expansion_promoted")
        if not promo:
            continue
        sub = rec.get("sub")
        job = short_job(rec.get("job_short") or rec.get("job") or "")
        if not sub or not job:
            continue
        # Add new combo
        combos.add((sub, promo["to_code"], job))
        # Add old combos
        for old_code in promo.get("from_codes", []):
            combos.add((sub, str(old_code), job))
    return combos


# ---------------------------------------------------------------------------
# STEP 1.5 — Re-run burst detection for affected combos
# ---------------------------------------------------------------------------

def detect_bursts_from_dates(active_dates):
    """Given a sorted list of distinct dates, return list of (first, last, dates)."""
    if not active_dates:
        return []
    dates = sorted(set(active_dates))
    bursts = []
    cur_dates = [dates[0]]
    for prev, nxt in zip(dates, dates[1:]):
        gap = working_days_between(prev, nxt)
        if gap >= GAP_THRESHOLD_WORKING_DAYS:
            bursts.append((cur_dates[0], cur_dates[-1], cur_dates[:]))
            cur_dates = [nxt]
        else:
            cur_dates.append(nxt)
    bursts.append((cur_dates[0], cur_dates[-1], cur_dates))
    # Merge if total active days <3
    total = sum(len(d) for d in [b[2] for b in bursts])
    if total < 3 and len(bursts) > 1:
        all_dates = sorted({d for _, _, ds in bursts for d in ds})
        return [(all_dates[0], all_dates[-1], all_dates)]
    return bursts


def rebuild_bursts_for_combos(records, affected_combos, existing_bursts, code_to_phase):
    """For each affected combo, drop existing bursts and rebuild from records.

    Also rebuild ALL combos to ensure consistency (since records may have been
    promoted ACROSS phase codes — e.g. a record at 6.3 → 13.3 — that affects
    BOTH the source 6.3 combo and the new 13.3 combo).

    Strategy:
    - Gather all (sub, code, job) -> [(date, log_id, rec)] from records
      (using current derived_phase_codes which already reflect promotions).
    - For each affected combo, replace bursts.
    - For unaffected combos, keep existing bursts as-is.
    """
    # Build new groups for affected combos only
    new_groups = defaultdict(list)
    for rec in records:
        sub = rec.get("sub")
        if not sub:
            continue
        codes = rec.get("derived_phase_codes") or []
        if not codes:
            continue
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
            combo = (sub, str(code), job)
            if combo in affected_combos:
                new_groups[combo].append((d, rec.get("logId"), rec))

    # Index existing bursts by combo (skipping affected combos which we'll rebuild)
    bursts_by_combo = defaultdict(list)
    for b in existing_bursts:
        combo = (b["sub"], b["phase_code"], b["job_id"])
        if combo not in affected_combos:
            bursts_by_combo[combo].append(b)

    # Renumber existing bursts that we keep
    max_burst_id = max((b["burst_id"] for b in existing_bursts), default=0)
    new_burst_id = max_burst_id + 1

    # Rebuild affected combos
    rebuilt_log_records = defaultdict(list)  # combo -> [list of records keyed by date]

    for combo, items in new_groups.items():
        sub, code, job = combo
        items.sort(key=lambda x: x[0])
        date_to_records = defaultdict(list)
        for d, lid, rec in items:
            date_to_records[d].append((lid, rec))
        active_dates = sorted(date_to_records.keys())

        burst_list = detect_bursts_from_dates(active_dates)

        local_bursts = []
        for i, (first_d, last_d, ds) in enumerate(burst_list, start=1):
            span_days = (last_d - first_d).days + 1
            active = len(ds)
            density = active / span_days if span_days > 0 else 1.0
            log_ids = []
            log_records = []
            for d in ds:
                for lid, rec in date_to_records[d]:
                    log_ids.append(lid)
                    log_records.append(rec)
            tier = density_tier(density)
            phase_meta = code_to_phase.get(code, {})

            burst = {
                "burst_id": new_burst_id,
                "sub": sub,
                "phase_code": code,
                "phase_name": phase_meta.get("name") or "",
                "stage": phase_meta.get("stage"),
                "stage_name": phase_meta.get("stage_name"),
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
            }
            new_burst_id += 1
            local_bursts.append(burst)
            rebuilt_log_records[burst["burst_id"]] = log_records

        bursts_by_combo[combo] = local_bursts

    return bursts_by_combo, rebuilt_log_records


# ---------------------------------------------------------------------------
# STEP 1.5b — For unaffected bursts, rebuild log_records from current records.
# We need this for downstream burst-role classification.
# ---------------------------------------------------------------------------

def rebuild_all_log_records(records, all_bursts):
    """For every burst, find the log records that belong to it.

    Match by (sub, phase_code, job_short) and date in [first_log, last_log].
    """
    burst_log_records = defaultdict(list)

    # Index records by (sub, code, job) -> [(date, rec)]
    rec_idx = defaultdict(list)
    for rec in records:
        sub = rec.get("sub")
        if not sub:
            continue
        codes = rec.get("derived_phase_codes") or []
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
            rec_idx[(sub, str(code), job)].append((d, rec))

    for burst in all_bursts:
        combo = (burst["sub"], burst["phase_code"], burst["job_id"])
        first_d = parse_date(burst["first_log"])
        last_d = parse_date(burst["last_log"])
        for d, rec in rec_idx.get(combo, []):
            if first_d <= d <= last_d:
                burst_log_records[burst["burst_id"]].append(rec)

    return burst_log_records


# ---------------------------------------------------------------------------
# STEP 2 — Burst role classification
# ---------------------------------------------------------------------------

# Phases that allow multiple primaries by trade convention
MULTI_PRIMARY_PHASES = {
    "7.2": 3,  # Stucco scratch (multi-trip is common)
    "7.3": 3,  # Stucco brown
    "7.6": 3,  # Stucco finish
    "12.2": 2,  # Paint walls (primer + finish)
    "14.1": 2,  # Exterior paint
    "14.5": 2,  # Pool shell
    "14.7": 2,  # Pool plaster
}


def classify_burst_roles(bursts_by_combo, all_codes_by_job, last_log_by_job_phase, first_log_by_job_phase, code_to_phase):
    """Classify each burst with a role: primary / return / punch / pre_work.

    Apply per (sub × phase × job).
    """
    for combo, bursts in bursts_by_combo.items():
        sub, code, job = combo
        if not bursts:
            continue
        bursts_sorted = sorted(bursts, key=lambda b: b["first_log"])

        # --- Identify primary burst(s) ---
        max_active = max(b["active_days"] for b in bursts_sorted)

        # Multi-trip phase cap (3 for stucco, 2 for paint/pool); else default 2
        max_primaries_cap = MULTI_PRIMARY_PHASES.get(code, 2)

        # Sort candidates: longest first, tie-break by start date
        candidates = sorted(bursts_sorted, key=lambda b: (-b["active_days"], b["first_log"]))

        # Default: longest is always primary
        primaries_set = set()
        primaries_set.add(candidates[0]["burst_id"])

        succs = code_to_phase.get(code, {}).get("successors", [])
        first_succ_start = None
        for s in succs:
            s_first = first_log_by_job_phase.get((job, s))
            if s_first is not None:
                if first_succ_start is None or s_first < first_succ_start:
                    first_succ_start = s_first

        # Multi-trip phases (stucco/paint/pool): pick top-K bursts within 50% of max
        # and ≥3 active days. These are the natural multi-trip patterns.
        if code in MULTI_PRIMARY_PHASES:
            for cand in candidates[1:]:
                if len(primaries_set) >= max_primaries_cap:
                    break
                if cand["active_days"] >= 0.5 * max_active and cand["active_days"] >= 3:
                    primaries_set.add(cand["burst_id"])
        else:
            # Non-multi-trip: allow a 2nd primary if it's within 25% of the max
            # AND substantial (≥3 active days)
            # AND sequence-aligned (no successor started yet at its start)
            if len(candidates) > 1:
                second = candidates[1]
                if second["active_days"] >= 0.75 * max_active and second["active_days"] >= 3:
                    sec_start = parse_date(second["first_log"])
                    if first_succ_start is None or first_succ_start >= sec_start:
                        primaries_set.add(second["burst_id"])

        # --- Now classify all bursts ---
        primary_starts = sorted(parse_date(b["first_log"]) for b in bursts_sorted if b["burst_id"] in primaries_set)
        primary_ends = sorted(parse_date(b["last_log"]) for b in bursts_sorted if b["burst_id"] in primaries_set)

        if not primary_starts:
            # Defensive: if somehow no primaries, fall back to longest burst
            longest = max(bursts_sorted, key=lambda b: b["active_days"])
            primaries_set.add(longest["burst_id"])
            primary_starts = [parse_date(longest["first_log"])]
            primary_ends = [parse_date(longest["last_log"])]

        first_primary_start = min(primary_starts)
        last_primary_end = max(primary_ends)

        for b in bursts_sorted:
            b_start = parse_date(b["first_log"])
            b_end = parse_date(b["last_log"])

            if b["burst_id"] in primaries_set:
                b["burst_role"] = "primary"
                continue

            # Pre-work: starts before first primary's start
            if b_start < first_primary_start:
                b["burst_role"] = "pre_work"
                continue

            # Check if any successor started before this burst started
            succ_started_before = False
            for s in succs:
                s_first = first_log_by_job_phase.get((job, s))
                if s_first is not None and s_first < b_start:
                    succ_started_before = True
                    break

            # Punch: short burst after a successor started
            if succ_started_before and b["active_days"] <= 5:
                b["burst_role"] = "punch"
                continue

            # Punch: short burst >30 calendar days after last primary end
            days_after_last_primary = (b_start - last_primary_end).days
            if days_after_last_primary > 30 and b["active_days"] <= 3:
                b["burst_role"] = "punch"
                continue

            # Return: within 30 calendar days of any primary's start or end
            within_30 = False
            for ps in primary_starts:
                if abs((b_start - ps).days) <= 30 or abs((b_end - ps).days) <= 30:
                    within_30 = True
                    break
            for pe in primary_ends:
                if abs((b_start - pe).days) <= 30:
                    within_30 = True
                    break

            if within_30:
                b["burst_role"] = "return"
                continue

            # Default catch-all: bursts beyond 30d but not short enough to be punch
            # AND no successor started → probably a return-to-scope work session
            if not succ_started_before:
                b["burst_role"] = "return"
            else:
                # After successor started but >5 active days → return-to-scope
                b["burst_role"] = "return"


# ---------------------------------------------------------------------------
# STEP 3 — Phase instance density math (with new fields)
# ---------------------------------------------------------------------------

def build_phase_instances(bursts_by_combo, burst_log_records, code_to_phase):
    """Aggregate bursts to (job × phase_code) instances with primary/return/punch metrics."""
    job_phase_bursts = defaultdict(list)
    for combo, bursts in bursts_by_combo.items():
        for b in bursts:
            key = (b["job_id"], b["phase_code"])
            job_phase_bursts[key].append(b)

    # Indexes for predecessor/successor calc
    all_codes_by_job = defaultdict(set)
    for (job, code) in job_phase_bursts.keys():
        all_codes_by_job[job].add(code)

    last_log_by_job_phase = {}
    first_log_by_job_phase = {}
    for key, bursts in job_phase_bursts.items():
        last_log_by_job_phase[key] = max(parse_date(b["last_log"]) for b in bursts)
        first_log_by_job_phase[key] = min(parse_date(b["first_log"]) for b in bursts)

    instances = []
    for (job, code), bursts in sorted(job_phase_bursts.items()):
        bursts_sorted = sorted(bursts, key=lambda b: b["first_log"])
        for i, b in enumerate(bursts_sorted, start=1):
            b["burst_index"] = i

        first_log = min(parse_date(b["first_log"]) for b in bursts_sorted)
        last_log = max(parse_date(b["last_log"]) for b in bursts_sorted)

        # Active days (distinct dates)
        active_set = set()
        for b in bursts_sorted:
            for rec in burst_log_records.get(b["burst_id"], []):
                ld = rec.get("log_date")
                if ld:
                    active_set.add(parse_date(ld))
        total_active_days = len(active_set)
        total_span_days = (last_log - first_log).days + 1

        sum_active = sum(b["active_days"] for b in bursts_sorted)
        sum_active_density = sum(b["active_days"] * b["density"] for b in bursts_sorted)
        weighted_density = sum_active_density / sum_active if sum_active > 0 else 0.0

        # --- New: split by burst role ---
        primaries = [b for b in bursts_sorted if b.get("burst_role") == "primary"]
        returns = [b for b in bursts_sorted if b.get("burst_role") == "return"]
        punches = [b for b in bursts_sorted if b.get("burst_role") == "punch"]
        prework = [b for b in bursts_sorted if b.get("burst_role") == "pre_work"]

        if primaries:
            p_active_set = set()
            for b in primaries:
                for rec in burst_log_records.get(b["burst_id"], []):
                    ld = rec.get("log_date")
                    if ld:
                        p_active_set.add(parse_date(ld))
            primary_active_days = sum(b["active_days"] for b in primaries)
            # Spec: primary_span_days = last_log of last primary minus first_log of first primary + 1
            # (kept for transparency/reporting)
            p_first = min(parse_date(b["first_log"]) for b in primaries)
            p_last = max(parse_date(b["last_log"]) for b in primaries)
            primary_span_days = (p_last - p_first).days + 1
            # primary_density = active days / sum of per-primary span days (sums each
            # primary burst's own span, NOT the union span across all primaries).
            # This matches "weighted_density restricted to primaries": short focused
            # primaries score high; scattered primaries score low. Excludes gaps
            # BETWEEN primary trips (which the spec captures separately as multi-trip
            # cadence, not as density).
            sum_primary_span = sum(b["span_days"] for b in primaries)
            primary_density = primary_active_days / sum_primary_span if sum_primary_span > 0 else 1.0
        else:
            primary_active_days = 0
            primary_span_days = 0
            primary_density = None

        if returns:
            return_active = sum(b["active_days"] for b in returns)
            r_sum_density = sum(b["active_days"] * b["density"] for b in returns)
            return_density = r_sum_density / return_active if return_active > 0 else 0.0
        else:
            return_density = None

        # Status
        days_since_last = (TODAY - last_log).days
        status = "ongoing" if days_since_last <= ONGOING_WINDOW_DAYS else "complete"

        # Subs involved
        sub_active = defaultdict(set)
        sub_logs = defaultdict(int)
        sub_density_acc = defaultdict(list)
        for b in bursts_sorted:
            sub = b.get("sub")
            for rec in burst_log_records.get(b["burst_id"], []):
                ld = rec.get("log_date")
                if ld:
                    sub_active[sub].add(ld)
                sub_logs[sub] += 1
            sub_density_acc[sub].append((b["active_days"], b["density"]))
        subs_involved = []
        for sub, dates in sub_active.items():
            wsum = 0.0
            wsum_active = 0
            for ad, dd in sub_density_acc[sub]:
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
        predecessors = phase_meta.get("predecessors", []) or []
        successors = phase_meta.get("successors", []) or []

        # Predecessors_complete
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

        # Confidence breakdown
        breakdown = Counter()
        for b in bursts_sorted:
            for rec in burst_log_records.get(b["burst_id"], []):
                cb = rec.get("classification_confidence") or "unknown"
                breakdown[cb] += 1

        # Output bursts
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
                "burst_role": b.get("burst_role"),
            }
            out_bursts.append(ob)

        inst = {
            "job": job,
            "phase_code": code,
            "phase_name": phase_meta.get("name") or "",
            "stage": phase_meta.get("stage"),
            "stage_name": phase_meta.get("stage_name"),
            "category": phase_meta.get("category"),
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

            # NEW: primary metrics
            "primary_density": round(primary_density, 4) if primary_density is not None else None,
            "primary_density_tier": density_tier(primary_density),
            "primary_active_days": primary_active_days,
            "primary_span_days": primary_span_days,

            # NEW: return / punch / pre_work counts
            "return_density": round(return_density, 4) if return_density is not None else None,
            "return_burst_count": len(returns),
            "punch_burst_count": len(punches),
            "pre_work_burst_count": len(prework),

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
# STEP 4 — Phase medians (now using primary_density as default)
# ---------------------------------------------------------------------------

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


def build_phase_medians(instances, code_to_phase):
    by_code = defaultdict(list)
    for inst in instances:
        if inst["status"] != "complete":
            continue
        by_code[inst["phase_code"]].append(inst)

    medians = []
    for code, insts in sorted(by_code.items()):
        per_job = {}
        for inst in insts:
            per_job[inst["job"]] = inst

        # Use primary metrics as default
        primary_actives = [i["primary_active_days"] for i in per_job.values() if i.get("primary_active_days")]
        primary_spans = [i["primary_span_days"] for i in per_job.values() if i.get("primary_span_days")]
        primary_dens_vals = [i["primary_density"] for i in per_job.values() if i.get("primary_density") is not None]

        return_burst_counts = [i["return_burst_count"] for i in per_job.values()]
        punch_burst_counts = [i["punch_burst_count"] for i in per_job.values()]
        burst_counts = [i["burst_count"] for i in per_job.values()]

        # Backward-compat: weighted total
        actives = [i["total_active_days"] for i in per_job.values()]
        spans = [i["total_span_days"] for i in per_job.values()]
        densities = [i["weighted_density"] for i in per_job.values()]

        sample_size = len(per_job)
        if sample_size >= 5:
            confidence = "high"
        elif sample_size >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        # Subs
        sub_data = defaultdict(lambda: {"active": [], "density": [], "jobs": set()})
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

        # Return / punch rates: % of instances with ≥1
        return_rate = sum(1 for c in return_burst_counts if c >= 1) / sample_size if sample_size > 0 else 0.0
        punch_rate = sum(1 for c in punch_burst_counts if c >= 1) / sample_size if sample_size > 0 else 0.0

        phase_meta = code_to_phase.get(code, {})

        # Default median uses primary_density (per spec); fallback to weighted if no primary
        if primary_dens_vals:
            med_density = round(statistics.median(primary_dens_vals), 4)
        else:
            med_density = round(statistics.median(densities), 4) if densities else 0.0

        med_active = round(statistics.median(primary_actives), 2) if primary_actives else (
            round(statistics.median(actives), 2) if actives else None
        )
        med_span = round(statistics.median(primary_spans), 2) if primary_spans else (
            round(statistics.median(spans), 2) if spans else None
        )

        rec = {
            "phase_code": code,
            "phase_name": phase_meta.get("name"),
            "stage": phase_meta.get("stage"),
            "stage_name": phase_meta.get("stage_name"),

            # Default = primary
            "median_active_days": med_active,
            "median_span_days": med_span,
            "median_density": med_density,
            "median_density_tier": density_tier(med_density),
            "median_burst_count": round(statistics.median(burst_counts), 2) if burst_counts else None,

            # NEW
            "median_return_burst_count": round(statistics.median(return_burst_counts), 2) if return_burst_counts else 0,
            "median_punch_burst_count": round(statistics.median(punch_burst_counts), 2) if punch_burst_counts else 0,
            "return_burst_rate": round(return_rate, 4),
            "punch_burst_rate": round(punch_rate, 4),

            # Backward compat
            "weighted_median_density": round(statistics.median(densities), 4) if densities else 0.0,

            "active_range_p25_p75": [
                round(percentile(primary_actives or actives, 0.25), 2) if (primary_actives or actives) else None,
                round(percentile(primary_actives or actives, 0.75), 2) if (primary_actives or actives) else None,
            ],
            "sample_size": sample_size,
            "confidence": confidence,
            "subs": subs,
        }
        medians.append(rec)
    return medians


# ---------------------------------------------------------------------------
# STEP 5 — Sub-phase rollups
# ---------------------------------------------------------------------------

def build_sub_phase_rollups(instances, medians, code_to_phase):
    """For every (sub × phase) where sub has performed phase ≥3 jobs,
    build rollup with PM binder flag."""

    # Index medians
    median_by_code = {m["phase_code"]: m for m in medians}

    # Group instances by (sub, phase). One sub may appear across multiple
    # bursts in an instance; we count distinct (sub, job, phase) triples.
    sub_phase_data = defaultdict(lambda: {
        "jobs": set(),
        "instances": [],  # the parent phase_instance records
        "primary_active_per_job": defaultdict(int),
        "primary_density_per_job": {},
        "burst_count_per_job": defaultdict(int),
        "return_burst_count_per_job": defaultdict(int),
        "punch_burst_count_per_job": defaultdict(int),
    })

    for inst in instances:
        job = inst["job"]
        code = inst["phase_code"]
        # For each sub in the instance, record their burst contributions
        # (We need per-burst data — instances expose `bursts` list with sub field.)
        sub_to_bursts = defaultdict(list)
        for b in inst["bursts"]:
            sub_to_bursts[b["sub"]].append(b)

        for sub, bursts in sub_to_bursts.items():
            key = (sub, code)
            slot = sub_phase_data[key]
            slot["jobs"].add(job)

            primaries = [b for b in bursts if b.get("burst_role") == "primary"]
            returns = [b for b in bursts if b.get("burst_role") == "return"]
            punches = [b for b in bursts if b.get("burst_role") == "punch"]

            if primaries:
                p_active = sum(b["active"] for b in primaries)
                # primary span: last - first + 1
                p_first = min(parse_date(b["first"]) for b in primaries)
                p_last = max(parse_date(b["last"]) for b in primaries)
                p_span = (p_last - p_first).days + 1
                p_density = p_active / p_span if p_span > 0 else 1.0
                slot["primary_active_per_job"][job] = p_active
                slot["primary_density_per_job"][job] = p_density
            else:
                slot["primary_active_per_job"][job] = 0
                slot["primary_density_per_job"][job] = None

            slot["burst_count_per_job"][job] = len(bursts)
            slot["return_burst_count_per_job"][job] = len(returns)
            slot["punch_burst_count_per_job"][job] = len(punches)

    rollups = []
    for (sub, code), data in sub_phase_data.items():
        jobs_performed = len(data["jobs"])
        if jobs_performed < 3:
            continue  # not enough volume for statistical basis

        # Compute medians/p25/p75 across jobs
        primary_active_list = [v for v in data["primary_active_per_job"].values() if v]
        primary_density_list = [v for v in data["primary_density_per_job"].values() if v is not None]
        burst_count_list = list(data["burst_count_per_job"].values())
        return_count_list = list(data["return_burst_count_per_job"].values())
        punch_count_list = list(data["punch_burst_count_per_job"].values())

        if primary_density_list:
            primary_density = round(statistics.median(primary_density_list), 4)
        else:
            primary_density = None

        if primary_active_list:
            primary_active_median = round(statistics.median(primary_active_list), 2)
            p25 = round(percentile(primary_active_list, 0.25), 2)
            p75 = round(percentile(primary_active_list, 0.75), 2)
        else:
            primary_active_median = None
            p25 = None
            p75 = None

        return_burst_rate = sum(1 for c in return_count_list if c >= 1) / jobs_performed
        punch_burst_rate = sum(1 for c in punch_count_list if c >= 1) / jobs_performed
        avg_burst_count = sum(burst_count_list) / len(burst_count_list) if burst_count_list else 0.0

        # Phase median for comparison
        phase_med = median_by_code.get(code, {})
        phase_median_density = phase_med.get("median_density")

        if phase_median_density is not None and primary_density is not None:
            vs_phase_median = round(primary_density - phase_median_density, 4)
        else:
            vs_phase_median = None

        # Flag logic
        flag_reasons = []
        if primary_density is not None and primary_density < 0.65:
            flag_reasons.append(f"primary density {primary_density:.2f} below 0.65 threshold")
        if return_burst_rate > 0.5:
            flag_reasons.append(f"return burst rate {return_burst_rate:.2f} above 0.50 threshold")
        if punch_burst_rate > 0.3:
            flag_reasons.append(f"punch burst rate {punch_burst_rate:.2f} above 0.30 threshold")
        if vs_phase_median is not None and vs_phase_median < -0.15:
            flag_reasons.append(f"vs phase median {vs_phase_median:+.2f} below -0.15 threshold")

        flag_for_pm_binder = bool(flag_reasons)

        phase_meta = code_to_phase.get(code, {})
        phase_name = phase_meta.get("name", "")

        rec = {
            "sub": sub,
            "phase_code": code,
            "phase_name": phase_name,
            "jobs_performed": jobs_performed,

            "primary_density": primary_density,
            "primary_density_label": density_tier(primary_density),
            "primary_active_days_median": primary_active_median,
            "primary_active_days_p25_p75": [p25, p75],

            "return_burst_rate": round(return_burst_rate, 4),
            "punch_burst_rate": round(punch_burst_rate, 4),
            "avg_burst_count_per_job": round(avg_burst_count, 2),

            "phase_median_density": phase_median_density,
            "vs_phase_median_density": vs_phase_median,

            "flag_for_pm_binder": flag_for_pm_binder,
            "flag_reasons": flag_reasons,
        }
        rollups.append(rec)

    # Sort: flagged first by severity (count of reasons), then by vs_median
    rollups.sort(key=lambda r: (
        not r["flag_for_pm_binder"],
        -len(r["flag_reasons"]),
        r["vs_phase_median_density"] if r["vs_phase_median_density"] is not None else 0,
    ))

    return rollups


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("loading inputs…")
    derived = load_json(DERIVED_V2)
    records = derived["records"]
    keywords_yaml = load_yaml(PHASE_KEYWORDS)
    taxonomy = load_yaml(PHASE_TAXONOMY)
    cross_trade = load_yaml(CROSS_TRADE)

    code_to_phase = {p["code"]: p for p in taxonomy.get("phases", [])}
    phase_groups = {k: [str(c) for c in v] for k, v in cross_trade.get("phase_groups", {}).items()}
    print(f"  records: {len(records)}")
    print(f"  taxonomy phases: {len(code_to_phase)}")

    # ─── STEP 1 ──────────────────────────────────────────────────────────
    print("\nSTEP 1: applying library expansion…")

    # Pre-count: high confidence by phase code for the 7 target phases
    pre_high_counts = Counter()
    for rec in records:
        if rec.get("classification_confidence") == "high":
            for c in rec.get("derived_phase_codes") or []:
                if str(c) in EXPANSION_PATTERNS:
                    pre_high_counts[str(c)] += 1

    # Append patterns to YAML
    print("  Updating phase-keywords.yaml…")
    append_expansion_patterns_to_yaml()

    # Find affected records
    print("  Finding affected records…")
    affected_by_code = find_affected_records(records, EXPANSION_PATTERNS, cross_trade, phase_groups)

    # Reclassify
    print("  Reclassifying affected records…")
    reclassify_affected_records(records, affected_by_code, code_to_phase)

    # Write derived-phases-v2.json (cleaning the _library_expansion_promoted helper key)
    affected_combos = affected_combos_from_promoted(records)

    # Strip helper keys before writing
    clean_records = []
    for rec in records:
        cr = {k: v for k, v in rec.items() if not k.startswith("_")}
        clean_records.append(cr)

    derived_out = {
        **{k: v for k, v in derived.items() if k != "records"},
        "records": clean_records,
    }
    write_json(DERIVED_V2, derived_out)

    # Post-count
    post_high_counts = Counter()
    for rec in records:
        if rec.get("classification_confidence") == "high":
            for c in rec.get("derived_phase_codes") or []:
                if str(c) in EXPANSION_PATTERNS:
                    post_high_counts[str(c)] += 1

    total_uplift = 0
    print(f"  {'Code':<6} {'Pre':>6} {'Post':>6} {'Delta':>6}")
    for code in sorted(EXPANSION_PATTERNS.keys()):
        pre = pre_high_counts.get(code, 0)
        post = post_high_counts.get(code, 0)
        delta = post - pre
        total_uplift += delta
        print(f"  {code:<6} {pre:>6} {post:>6} {delta:>+6}")
    print(f"  TOTAL UPLIFT: {total_uplift}")
    print(f"  Affected (sub × phase × job) combos to rebuild: {len(affected_combos)}")

    # ─── STEP 1.5 — Re-run burst detection for affected combos ──────────
    print("\nSTEP 1.5: rebuilding bursts for affected combos…")
    existing_bursts_data = load_json(OUT_BURSTS)
    existing_bursts = existing_bursts_data["bursts"]

    bursts_by_combo, rebuilt_log_records = rebuild_bursts_for_combos(
        records, affected_combos, existing_bursts, code_to_phase
    )

    # Flatten
    all_bursts = []
    for combo, bursts in bursts_by_combo.items():
        all_bursts.extend(bursts)

    print(f"  total bursts after rebuild: {len(all_bursts)}")
    print(f"  total combos: {len(bursts_by_combo)}")

    # Build log-records map for ALL bursts (we need this for instance density math)
    all_burst_log_records = rebuild_all_log_records(records, all_bursts)

    # ─── STEP 2 — Burst role classification ──────────────────────────────
    print("\nSTEP 2: classifying burst roles…")

    # Need first/last log indexes per (job, phase) for sequence checks
    last_log_by_job_phase = {}
    first_log_by_job_phase = {}
    for combo, bursts in bursts_by_combo.items():
        sub, code, job = combo
        key = (job, code)
        for b in bursts:
            f = parse_date(b["first_log"])
            l = parse_date(b["last_log"])
            if key not in first_log_by_job_phase or f < first_log_by_job_phase[key]:
                first_log_by_job_phase[key] = f
            if key not in last_log_by_job_phase or l > last_log_by_job_phase[key]:
                last_log_by_job_phase[key] = l

    all_codes_by_job = defaultdict(set)
    for (sub, code, job) in bursts_by_combo.keys():
        all_codes_by_job[job].add(code)

    classify_burst_roles(
        bursts_by_combo,
        all_codes_by_job,
        last_log_by_job_phase,
        first_log_by_job_phase,
        code_to_phase,
    )

    # Role distribution sanity check
    role_counts = Counter()
    for combo, bursts in bursts_by_combo.items():
        for b in bursts:
            role_counts[b.get("burst_role", "unknown")] += 1
    total_bursts = sum(role_counts.values())
    print(f"  Role distribution across {total_bursts} bursts:")
    for role, ct in role_counts.most_common():
        print(f"    {role:<10} {ct:>5} ({ct/total_bursts*100:.1f}%)")

    primary_pct = role_counts.get("primary", 0) / total_bursts
    if primary_pct >= 1.0:
        print("  STOP-FLAG: 100% primaries — role classifier not triggering!")
    if role_counts.get("punch", 0) / total_bursts > 0.5:
        print("  STOP-FLAG: 50%+ punches — over-classifying!")
    if primary_pct < 0.6:
        print(f"  WARN: primary share is {primary_pct*100:.1f}% (below 60% target)")

    # ─── STEP 3 — Build phase instances ──────────────────────────────────
    print("\nSTEP 3: building phase instances…")
    instances = build_phase_instances(bursts_by_combo, all_burst_log_records, code_to_phase)
    print(f"  {len(instances)} phase instances")

    # ─── STEP 4 — Build phase medians ────────────────────────────────────
    print("\nSTEP 4: computing phase medians…")
    medians = build_phase_medians(instances, code_to_phase)
    print(f"  {len(medians)} phase median records")

    # ─── STEP 5 — Build sub-phase rollups ────────────────────────────────
    print("\nSTEP 5: building sub-phase rollups…")
    rollups = build_sub_phase_rollups(instances, medians, code_to_phase)
    flagged = sum(1 for r in rollups if r["flag_for_pm_binder"])

    # Coverage stats: total pairs vs eligible vs flagged
    # Total pairs = all (sub, phase) combos seen, regardless of jobs
    all_sub_phase_pairs = set()
    for inst in instances:
        for b in inst["bursts"]:
            all_sub_phase_pairs.add((b["sub"], inst["phase_code"]))

    eligible = len(rollups)
    print(f"  total (sub × phase) pairs seen: {len(all_sub_phase_pairs)}")
    print(f"  eligible (≥3 jobs): {eligible}")
    print(f"  flagged for PM binder: {flagged} ({flagged/eligible*100:.1f}% of eligible)")

    # ─── Write outputs ───────────────────────────────────────────────────
    print("\nWriting output files…")

    # bursts.json
    cleaned_bursts = []
    for combo, bursts in bursts_by_combo.items():
        for b in bursts:
            cb = {k: v for k, v in b.items() if not k.startswith("_")}
            cleaned_bursts.append(cb)
    cleaned_bursts.sort(key=lambda b: b["burst_id"])

    write_json(OUT_BURSTS, {
        "generated_at": TODAY.isoformat(),
        "total_bursts": len(cleaned_bursts),
        "gap_threshold_working_days": GAP_THRESHOLD_WORKING_DAYS,
        "bursts": cleaned_bursts,
    })
    print(f"  bursts.json: {len(cleaned_bursts)} bursts")

    # phase-instances-v2.json
    write_json(OUT_INSTANCES, {
        "generated_at": TODAY.isoformat(),
        "total_instances": len(instances),
        "today": TODAY.isoformat(),
        "instances": instances,
    })
    print(f"  phase-instances-v2.json: {len(instances)} instances")

    # phase-medians.json
    write_json(OUT_MEDIANS, {
        "generated_at": TODAY.isoformat(),
        "total_phases": len(medians),
        "medians": medians,
    })
    print(f"  phase-medians.json: {len(medians)} phases")

    # sub-phase-rollups.json
    write_json(OUT_ROLLUPS, {
        "generated_at": TODAY.isoformat(),
        "total_rollups": len(rollups),
        "flagged_for_pm_binder": flagged,
        "rollups": rollups,
    })
    print(f"  sub-phase-rollups.json: {len(rollups)} rollups, {flagged} flagged")

    # Save state for verification
    state = {
        "library_expansion": {
            "pre_high_counts": dict(pre_high_counts),
            "post_high_counts": dict(post_high_counts),
            "total_uplift": total_uplift,
            "affected_records_per_phase": {k: len(v) for k, v in affected_by_code.items()},
            "affected_combos_count": len(affected_combos),
        },
        "burst_role_distribution": dict(role_counts),
        "phase_instances": len(instances),
        "phase_medians": len(medians),
        "rollups": {
            "total": len(rollups),
            "flagged": flagged,
            "all_pairs_seen": len(all_sub_phase_pairs),
        },
    }
    state_path = PHASE_DIR / "_phase3_followup_state.json"
    write_json(state_path, state)
    print(f"\n  state saved to {state_path}")

    # Watts at Fish breakdown — for verification
    print("\n=== Watts at Fish 7.2 breakdown ===")
    watts_fish = []
    for b in cleaned_bursts:
        if b["sub"] == "Jeff Watts Plastering and Stucco" and b["job_id"] == "Fish" and b["phase_code"] == "7.2":
            watts_fish.append(b)
    watts_fish.sort(key=lambda b: b["first_log"])
    for b in watts_fish:
        print(f"  #{b['burst_index']}: {b['first_log']} → {b['last_log']}  active={b['active_days']:>2} span={b['span_days']:>3} density={b['density']:.2f}  role={b.get('burst_role')}")

    # 8-phase comparison
    print("\n=== 8-phase primary-vs-weighted density ===")
    sanity_codes = ["7.2", "8.2", "10.2", "14.5", "3.4", "7.4", "9.2", "4.2"]
    print(f"  {'Code':<6} {'Phase':<35} {'Weighted':>9} {'Primary':>9}")
    for code in sanity_codes:
        med = next((m for m in medians if m["phase_code"] == code), None)
        if med:
            wd = med.get("weighted_median_density", 0.0)
            pd = med.get("median_density", 0.0)
            print(f"  {code:<6} {med['phase_name'][:35]:<35} {wd:>9.4f} {pd:>9.4f}")

    # Top 20 PM binder flags
    print("\n=== Top 20 PM-binder-flagged sub-phase pairs ===")
    flagged_rollups = [r for r in rollups if r["flag_for_pm_binder"]][:20]
    for i, r in enumerate(flagged_rollups, 1):
        reason = r["flag_reasons"][0] if r["flag_reasons"] else "?"
        print(f"  {i:>2}. {r['sub'][:40]:<40} {r['phase_code']:<5} jobs={r['jobs_performed']:>2}  reason: {reason}")

    # Markgraf 2.4
    print("\n=== Markgraf full read-down ===")
    for inst in instances:
        if inst["job"] == "Markgraf":
            phase_meta_name = inst["phase_name"]
            pd = inst.get("primary_density")
            wd = inst.get("weighted_density")
            bc = inst.get("burst_count")
            rc = inst.get("return_burst_count", 0)
            pc = inst.get("punch_burst_count", 0)
            pwc = inst.get("pre_work_burst_count", 0)
            print(f"  {inst['phase_code']:<6} {phase_meta_name[:30]:<30} primary={pd}  weighted={wd}  bursts={bc}  R={rc} Punch={pc} PW={pwc}")

    print("\nDONE.")


if __name__ == "__main__":
    main()
