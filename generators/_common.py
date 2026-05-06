"""Shared helpers for Phase 6 generators (G1, G2, G3).

Loaders, date utilities, PM-jobs map, sub list, INSIGHT factory.
Pure-function module — no side effects on import.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CFG = ROOT / "config"
BINDERS = ROOT / "binders"
SCRAPER_LOGS = ROOT.parent / "buildertrend-scraper" / "data" / "daily-logs.json"

PM_BY_BINDER_FILE = {
    "Bob_Mozine.json": "Bob Mozine",
    "Jason_Szykulski.json": "Jason Szykulski",
    "Lee_Worthy.json": "Lee Worthy",
    "Martin_Mannix.json": "Martin Mannix",
    "Nelson_Belanger.json": "Nelson Belanger",
}

PM_SLUGS = {
    "Bob Mozine": "bob-mozine",
    "Jason Szykulski": "jason-szykulski",
    "Lee Worthy": "lee-worthy",
    "Martin Mannix": "martin-mannix",
    "Nelson Belanger": "nelson-belanger",
}

# Daily-logs uses 'JobShort-Address' keys.  Built lazily below.
JOB_LOG_KEY_OVERRIDES = {
    "FieldCrew": "Field Crew (Ross Built)",
}

# Boilerplate strings we strip out of crews_clean / crews fields.
CREWS_BOILERPLATE = {
    "on Site",
    "Read less",
    "Daily Workforce",
    "Absent Crew(s)",
    "NONE",
    "Parent Group Activity",
    "",
}


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_phase3() -> dict[str, Any]:
    return {
        "instances": load_json(DATA / "phase-instances-v2.json"),
        "medians": load_json(DATA / "phase-medians.json"),
        "rollups": load_json(DATA / "sub-phase-rollups.json"),
        "job_stages": load_json(DATA / "job-stages.json"),
        "bursts": load_json(DATA / "bursts.json"),
        "taxonomy": load_yaml(CFG / "phase-taxonomy.yaml"),
        "phase_keywords": load_yaml(CFG / "phase-keywords.yaml"),
    }


def load_excluded_jobs() -> set[str]:
    """Load job_short names that should be skipped by all generators.

    Returns an empty set if the config file is missing.
    """
    p = CFG / "excluded_jobs.yaml"
    if not p.exists():
        return set()
    cfg = load_yaml(p) or {}
    return {entry["job"] for entry in cfg.get("excluded", []) if entry.get("job")}


def load_binders() -> list[dict[str, Any]]:
    out = []
    for fn, _ in PM_BY_BINDER_FILE.items():
        path = BINDERS / fn
        if path.exists():
            out.append({"file": fn, "data": load_json(path)})
    return out


def load_daily_logs() -> dict[str, list[dict[str, Any]]]:
    """Returns { 'JobShort-Address': [log, log, ...], ... }."""
    if not SCRAPER_LOGS.exists():
        return {}
    return load_json(SCRAPER_LOGS).get("byJob", {})


def job_log_key(job_short: str, log_keys: list[str]) -> str | None:
    """Map a job short name to its 'Short-Address' key in daily-logs."""
    if job_short in JOB_LOG_KEY_OVERRIDES:
        target = JOB_LOG_KEY_OVERRIDES[job_short]
        for k in log_keys:
            if k == target or k.startswith(target):
                return k
    prefix = f"{job_short}-"
    for k in log_keys:
        if k.startswith(prefix):
            return k
    return None


def parse_log_date(date_str: str, today_year: int) -> date | None:
    """Parse 'Wed, Apr 22' or 'Fri, Dec 22, 2023' into a date object.

    Year-omitted strings use today_year if the resulting date is <= today,
    else today_year - 1 (to handle Jan/Feb logs that are still recent).
    """
    if not date_str:
        return None
    s = date_str.strip()
    parts = [p.strip() for p in s.split(",")]
    if len(parts) == 2:
        # 'Wed, Apr 22' — no year given
        try:
            md = datetime.strptime(parts[1], "%b %d").date()
        except ValueError:
            return None
        candidate = date(today_year, md.month, md.day)
        return candidate
    if len(parts) == 3:
        # 'Fri, Dec 22, 2023'
        try:
            return datetime.strptime(f"{parts[1]}, {parts[2]}", "%b %d, %Y").date()
        except ValueError:
            return None
    return None


def parse_iso(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")


# ----------------------------- INSIGHT factory ------------------------------

_INSIGHT_TYPE_TO_CATEGORY = {
    "sequencing_risk":      "SCHEDULE",
    "sequencing_violation": "SCHEDULE",
    "sub_drift":            "SUB-TRADE",
    "missed_commitment":    "SCHEDULE",
}


def make_insight(
    *,
    generator: str,
    type_: str,
    severity: str,
    message: str,
    ask: str,
    evidence: list[dict],
    related_job: str | None = None,
    related_pm: str | None = None,
    related_phase: str | None = None,
    related_phase_name: str | None = None,
    related_sub: str | None = None,
    related_action_id: str | None = None,
    generated_at: str | None = None,
    bucket: str = "field",
    summary_line: str | None = None,
    category: str | None = None,
    source: str = "system_predicted",
) -> dict:
    """Build a normalized INSIGHT record.

    `id` is unique per record (per-run). `content_hash` is deterministic
    from the (type, scope-key) tuple so future de-dup / acknowledgment
    tracking can match an insight across runs without over-indexing on
    the run timestamp.

    `bucket`:
      - "field"        — actionable signal, eligible for top-5 must-discuss
      - "data_quality" — classifier artifact, surfaced separately at the
                         bottom of the meeting page; never in the top-5

    `summary_line` is the single-line "evidence summary" used by the
    redesigned meeting-prep checklist (3-line cards). When omitted, the
    renderer falls back to a generic format derived from `evidence`.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if category is None:
        category = _INSIGHT_TYPE_TO_CATEGORY.get(type_, "ADMIN")
    scope_key = "|".join([
        type_,
        str(related_job or ""),
        str(related_phase or ""),
        str(related_sub or ""),
        str(related_action_id or ""),
    ])
    content_hash = hashlib.sha1(scope_key.encode("utf-8")).hexdigest()[:12]
    insight_id = f"{generator}-{type_}-{content_hash}-{generated_at.replace(':','').replace('-','')[:14]}"
    return {
        "id": insight_id,
        "content_hash": content_hash,
        "generator": generator,
        "type": type_,
        "category": category,
        "source": source,
        "severity": severity,
        "bucket": bucket,
        "message": message,
        "summary_line": summary_line,
        "ask": ask,
        "evidence": evidence,
        "related_job": related_job,
        "related_pm": related_pm,
        "related_phase": related_phase,
        "related_phase_name": related_phase_name,
        "related_sub": related_sub,
        "related_action_id": related_action_id,
        "generated_at": generated_at,
        "status": "open",
    }


# ----------------------------- PM ↔ Jobs map --------------------------------

def pm_job_map(binders: list[dict]) -> dict[str, list[str]]:
    """{'Nelson Belanger': ['Markgraf', 'Clark', 'Johnson'], ...}"""
    out: dict[str, list[str]] = {}
    for b in binders:
        pm = b["data"]["meta"]["pm"]
        out[pm] = [j["name"] for j in b["data"].get("jobs", [])]
    return out


def job_pm_map(binders: list[dict]) -> dict[str, str]:
    """{'Markgraf': 'Nelson Belanger', ...}"""
    out: dict[str, str] = {}
    for pm, jobs in pm_job_map(binders).items():
        for j in jobs:
            out[j] = pm
    return out


# ----------------------------- Sub canonicalization --------------------------

def canonical_sub_universe(phase3: dict) -> set[str]:
    """All sub names referenced anywhere in Phase 3 data + rollups."""
    subs: set[str] = set()
    for r in phase3["rollups"]["rollups"]:
        subs.add(r["sub"])
    for ins in phase3["instances"]["instances"]:
        for s in ins.get("subs_involved", []):
            if s.get("sub"):
                subs.add(s["sub"])
        for b in ins.get("bursts", []):
            if b.get("sub"):
                subs.add(b["sub"])
    return subs


def crews_clean_subs(log: dict) -> list[str]:
    """Pull canonical sub names out of a log's crews fields.

    crews_clean (preferred) is a list[str] of canonical sub names already
    stripped of boilerplate. crews (legacy) is a semicolon-separated
    string mixed with tokens like 'on Site' and 'Daily Workforce'.
    """
    cc = log.get("crews_clean")
    if isinstance(cc, list):
        return [s for s in cc if s and s not in CREWS_BOILERPLATE]
    raw = cc or log.get("crews") or ""
    if isinstance(raw, str) and raw:
        out: list[str] = []
        for tok in (s.strip() for s in raw.split(";")):
            if tok and tok not in CREWS_BOILERPLATE:
                out.append(tok)
        return out
    return []


# ----------------------------- Phase keyword matcher ------------------------

def compile_phase_matchers(phase_keywords_yaml: dict) -> list[dict]:
    """Returns [{code, name, keywords: [pat], hints: [pat]}, ...].

    Keywords (from `keywords:` in YAML) are specific phrases — strong signal.
    Hints (from `tag_hints:`) are loose substring matches — weak signal.
    """
    out = []
    for p in phase_keywords_yaml.get("phases", []):
        keywords: list[re.Pattern] = []
        hints: list[re.Pattern] = []
        for kw in p.get("keywords", []) or []:
            try:
                keywords.append(re.compile(kw, re.IGNORECASE))
            except re.error:
                keywords.append(re.compile(re.escape(kw), re.IGNORECASE))
        for hint in p.get("tag_hints", []) or []:
            hints.append(re.compile(re.escape(hint), re.IGNORECASE))
        if keywords or hints:
            out.append(
                {
                    "code": p["code"],
                    "name": p["name"],
                    "keywords": keywords,
                    "hints": hints,
                }
            )
    return out


def match_phase(text: str, matchers: list[dict]) -> tuple[str, str, float] | None:
    """Return (phase_code, phase_name, confidence) for the best match, else None.

    Confidence rubric (corroboration- and specificity-aware):
      - 0.95 — 2+ keyword matches (any breadth)
      - 0.85 — 1 multi-word keyword match (e.g., "interior stair", "drywall tape")
      - 0.65 — 1 single-word keyword match (e.g., "putty", "railing")
      - 0.55 — tag_hint match only
      - 0.0  — no match

    Penalizing single-word keyword matches catches cases like "putty"
    incidentally appearing in a sanding/staining item, or "railing" in
    "railing material gone".
    """
    if not text:
        return None
    best: tuple[str, str, float] | None = None
    for m in matchers:
        kw_matches = []
        for p in m["keywords"]:
            mh = p.search(text)
            if mh:
                kw_matches.append(mh.group(0))
        hint_hits = sum(1 for p in m["hints"] if p.search(text))
        if len(kw_matches) >= 2:
            score = 0.95
        elif len(kw_matches) == 1:
            matched = kw_matches[0].strip()
            score = 0.85 if (" " in matched or "\t" in matched) else 0.65
        elif hint_hits >= 1:
            score = 0.55
        else:
            continue
        if best is None or score > best[2]:
            best = (m["code"], m["name"], score)
    return best


def match_sub(text: str, sub_universe: list[str]) -> tuple[str, float] | None:
    """Find the canonical sub mentioned in `text` and score the match.

    Confidence rubric:
      - 0.95 — full canonical name (or close) appears verbatim
      - 0.85 — head + secondary distinctive token both present
      - 0.65 — single-token head match (still a real sub but weaker)
      - 0.0  — no match
    """
    if not text:
        return None
    txt = text.lower()
    ignore = {"inc", "llc", "co", "company", "corporation", "the", "of", "and", "services", "service"}
    generic_heads = {"all", "first", "best", "new", "south", "north", "east", "west", "us", "usa"}

    best: tuple[str, float] | None = None
    for sub in sub_universe:
        tokens = re.findall(r"[A-Za-z]+", sub)
        distinctive = [t for t in tokens if t.lower() not in ignore]
        if not distinctive:
            continue

        # 1) Full canonical name (case-insensitive) — strongest
        if sub.lower() in txt:
            score = 0.95
            if best is None or score > best[1]:
                best = (sub, score)
            continue

        head = distinctive[0]
        if head.lower() in generic_heads or len(head) < 3:
            continue
        head_pat = r"\b" + re.escape(head.lower()) + r"\b"
        if not re.search(head_pat, txt):
            continue

        # 2) Head + any secondary distinctive token both present
        secondary_hit = False
        for t in distinctive[1:]:
            if t.lower() in generic_heads or len(t) < 3:
                continue
            if re.search(r"\b" + re.escape(t.lower()) + r"\b", txt):
                secondary_hit = True
                break
        if secondary_hit:
            score = 0.85
        else:
            score = 0.65

        if best is None or score > best[1]:
            best = (sub, score)
    return best


# ----------------------------- Severity → score ------------------------------

SEVERITY_SCORE = {"critical": 3, "warn": 1}
TYPE_SCORE = {
    "missed_commitment": 5,
    "sequencing_risk": 4,
    "sub_drift": 3,
    "sequencing_violation": 2,
}


def insight_rank_score(ins: dict) -> int:
    """Higher = more important for top-5 ranking."""
    return SEVERITY_SCORE.get(ins.get("severity", "warn"), 1) + TYPE_SCORE.get(ins.get("type", ""), 0)
