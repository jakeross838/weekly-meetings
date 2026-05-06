"""One-time action-item enrichment pass.

Infers `related_phase`, `related_sub`, and `requires_field_confirmation`
on each item by pattern-matching `action` + `update` text against the
phase-keywords config and the canonical sub universe from Phase 3 data.

Saves enriched binders to `binders/enriched/{file}.enriched.json` —
never overwrites originals. Inferred fields carry `inferred: true`
markers so PMs can see what was guessed.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from generators._common import (
    BINDERS,
    PM_BY_BINDER_FILE,
    canonical_sub_universe,
    compile_phase_matchers,
    load_binders,
    load_phase3,
    match_phase,
    match_sub,
)

ENRICHED_DIR = BINDERS / "enriched"

# Action verbs that imply physical field work (→ requires_field_confirmation).
FIELD_VERBS = re.compile(
    r"\b(install|reinstall|verify|punch|complet|deliver|rough|finish|trim|"
    r"frame|demo|remove|set|replace|fix|patch|repair|prime|paint|tile|"
    r"grout|caulk|seal|pour|frame|hang|drill|cut|excavat|backfill|"
    r"inspect|walk|on\s*site|scope|field|crew|build|construct|wire|"
    r"plumb|hvac|trench|run|rod|core)\w*",
    re.IGNORECASE,
)

# Action verbs that imply administrative/document-only work (NOT field).
ADMIN_VERBS = re.compile(
    r"\b(send|email|draft|review|sign|approve|submit|submitt|filed|filing|"
    r"applic|quote|price|estimat|"
    r"call|callback|voicemail|phone|text|schedule\s+(?:call|meeting|review)|"
    r"co-?\d|pcco|change\s+order|contract|homeowner|owner|permit\s+app|"
    r"\bdep\b|deposit|invoice|payment|paid|tracking\s+entry|"
    r"decision\s+locked|locked|close\s*out\s+tracking)\w*",
    re.IGNORECASE,
)

# Negation/decision-not-action patterns — strong admin signal.
ADMIN_DECISION = re.compile(
    r"\b(no\s+formal|not\s+needed|de[-\s]coupled|de[-\s]coupling|"
    r"deferred?|cancell?ed|withdrawn|tabled|won['’]t\s+do|"
    r"pricing\s+finalized|already\s+(?:paid|on\s+draw|signed|posted)|"
    r"decision\s+locked|policy\s+level|sandbags?\s+schedule)",
    re.IGNORECASE,
)

# Leading closeout marker — "Complete —", "Complete - ", "COMPLETE:" etc.
# Strip before field-flag classification so the closeout literal doesn't
# get misread as the field verb "complete".
LEADING_CLOSEOUT = re.compile(
    r"^\s*complet[ed]?\s*[—\-:]\s*", re.IGNORECASE
)


def infer_field_flag(text: str) -> bool:
    """Heuristic: does this item's text imply physical field activity?"""
    if not text:
        return False
    # Strip leading "Complete —" closeout marker so it's not read as a verb.
    cleaned = LEADING_CLOSEOUT.sub("", text)
    has_field = bool(FIELD_VERBS.search(cleaned))
    has_admin = bool(ADMIN_VERBS.search(cleaned))
    has_decision = bool(ADMIN_DECISION.search(cleaned))
    # Decision/negation phrases override field verbs — these are
    # closeout/admin entries even when they sound like field work.
    if has_decision:
        return False
    if has_field and not has_admin:
        return True
    if has_admin and not has_field:
        return False
    if has_field and has_admin:
        # Mixed — bias to field only if a strong physical verb is present
        # in the cleaned text (after closeout-marker strip).
        if re.search(r"\b(install|punch|deliver|inspect|sand|stain|grout|caulk|tile)\w*", cleaned, re.IGNORECASE):
            return True
        return False
    return False


CONFIDENCE_THRESHOLD = 0.7


def enrich_item(item: dict, phase_matchers: list, sub_universe: list[str]) -> dict:
    text = " ".join(filter(None, [item.get("action"), item.get("update")]))
    out = copy.deepcopy(item)

    if not item.get("related_phase"):
        m = match_phase(text, phase_matchers)
        if m and m[2] >= CONFIDENCE_THRESHOLD:
            out["related_phase"] = m[0]
            out["related_phase_name"] = m[1]
            out["related_phase_inferred"] = True
            out["related_phase_confidence"] = round(m[2], 2)

    if not item.get("related_sub"):
        sub = match_sub(text, sub_universe)
        if sub and sub[1] >= CONFIDENCE_THRESHOLD:
            out["related_sub"] = sub[0]
            out["related_sub_inferred"] = True
            out["related_sub_confidence"] = round(sub[1], 2)

    if "requires_field_confirmation" not in item:
        out["requires_field_confirmation"] = infer_field_flag(text)
        out["requires_field_confirmation_inferred"] = True

    return out


def enrich_all() -> dict[str, dict]:
    phase3 = load_phase3()
    sub_universe = sorted(canonical_sub_universe(phase3), key=len, reverse=True)
    phase_matchers = compile_phase_matchers(phase3["phase_keywords"])

    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    stats = {
        "files": 0,
        "items": 0,
        "with_phase": 0,
        "with_sub": 0,
        "phase_skipped_low_confidence": 0,
        "sub_skipped_low_confidence": 0,
        "with_field_confirmation_true": 0,
        "with_field_confirmation_false": 0,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }
    written = {}

    binders = load_binders()
    for b in binders:
        fn = b["file"]
        binder = copy.deepcopy(b["data"])
        new_items = []
        for it in binder.get("items", []):
            text = " ".join(filter(None, [it.get("action"), it.get("update")]))
            # Tally low-confidence skips before the actual enrichment writes
            if not it.get("related_phase"):
                m = match_phase(text, phase_matchers)
                if m and m[2] < CONFIDENCE_THRESHOLD:
                    stats["phase_skipped_low_confidence"] += 1
            if not it.get("related_sub"):
                s = match_sub(text, sub_universe)
                if s and s[1] < CONFIDENCE_THRESHOLD:
                    stats["sub_skipped_low_confidence"] += 1

            enriched = enrich_item(it, phase_matchers, sub_universe)
            stats["items"] += 1
            if enriched.get("related_phase"):
                stats["with_phase"] += 1
            if enriched.get("related_sub"):
                stats["with_sub"] += 1
            if enriched.get("requires_field_confirmation"):
                stats["with_field_confirmation_true"] += 1
            else:
                stats["with_field_confirmation_false"] += 1
            new_items.append(enriched)
        binder["items"] = new_items
        out_path = ENRICHED_DIR / f"{Path(fn).stem}.enriched.json"
        out_path.write_text(json.dumps(binder, indent=2), encoding="utf-8")
        stats["files"] += 1
        written[fn] = str(out_path)
    return {"stats": stats, "files": written}


if __name__ == "__main__":
    res = enrich_all()
    print("Enrichment stats:")
    for k, v in res["stats"].items():
        print(f"  {k}: {v}")
    print("\nFiles written:")
    for src, dst in res["files"].items():
        print(f"  {src} -> {dst}")
