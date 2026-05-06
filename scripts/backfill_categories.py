"""One-time backfill: assign `category` and `source` fields to all items in
binders/*.json.

Rule-based classifier:
  1. Type-field default mapping (covers ~70% confidently)
  2. Keyword-scan refinement on `action` + `update` text (catches the rest)
  3. Anything still ambiguous → ADMIN with a manual-review flag in the log

Existing items are all assumed source="transcript" — they came from prior
process.py runs.

Run from project root:
  python scripts/backfill_categories.py            # apply changes
  python scripts/backfill_categories.py --dry-run  # log only, no writes

Idempotent: re-running on already-classified items is a no-op (preserves
existing category unless --force-reclassify is set).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINDERS = ROOT / "binders"
LOG_DIR = ROOT / "scripts"

CATEGORIES = (
    "SCHEDULE",     # sub start dates, confirmations, duration, sequencing, schedule moves
    "PROCUREMENT",  # material orders, deliveries, lead times, PO creation, BUYOUTS
    "SUB-TRADE",    # sub performance, scheduling, credits, hire/fire, scope disputes
    "CLIENT",       # homeowner decisions, communication, walkthroughs, sentiment, CO approvals
    "QUALITY",      # field defects, rework, punch items, dust control, workmanship
    "BUDGET",       # cost estimates, budget variances, change orders to process, GP exposure
    "ADMIN",        # permits, inspections, insurance, internal process, company events
    "SELECTION",    # finish selections, design decisions, material choices, designer items
)

# Type-field default mapping. The existing 7-type axis maps softly to the
# new 8-category axis; keyword refinement pushes finer cases.
TYPE_DEFAULTS = {
    "SELECTION":    "SELECTION",
    "PRICING":      "BUDGET",
    "CO_INVOICE":   "BUDGET",
    "SCHEDULE":     "SCHEDULE",
    "CONFIRMATION": "SCHEDULE",
    "FIELD":        "QUALITY",
    "FOLLOWUP":     "ADMIN",   # weakest default — keyword scan usually rewrites
}

# Keyword patterns per category, ordered by specificity (most specific first).
# Each pattern wins if matched; later categories don't override an earlier hit
# unless the override is more specific (handled in classify()).
KEYWORD_PATTERNS = [
    # SELECTION — first because tile/finish/design language overlaps with QUALITY
    ("SELECTION", re.compile(
        r"\b(select(ion)?s?|pick|choose|finish(es)?\b|tile (color|pattern|spec)|"
        r"hardware finish|paint color|stain spec|fixture spec|cabinet spec|"
        r"countertop|backsplash|grout|grout color|designer (call|review|spec)|"
        r"swatch|sample (board|approval)|spec\s*(sheet|sample))\b",
        re.IGNORECASE,
    )),
    # PROCUREMENT — orders / lead time / buyouts (Jake said buyouts go here)
    ("PROCUREMENT", re.compile(
        r"\b(buyout|po\b|p\.o\.|purchase order|order(?:ing|ed)?|deliver(y|ies|ed)?|"
        r"lead\s*time|long[\s-]*lead|stock|backorder|ship(ment|ping)?|submittal|"
        r"material(s)?\s*(order|on\s*site|delivery|deliver)|"
        r"steel\s*(package|order)|cabinet\s*order|appliance\s*order)\b",
        re.IGNORECASE,
    )),
    # BUDGET — money / CO / pricing / GP
    ("BUDGET", re.compile(
        r"\b(co[-\s]?\d|change\s+order|pcco|owner\s+co|"
        r"pay\s*app(lication)?|invoice|allowance|credit\s*back|"
        r"gp\s*(?:vs|target|exposure|risk)|gross\s*profit|"
        r"budget\s*(variance|exposure|overrun|review|exceeded)|"
        r"quote|bid|estimat(e|ing)|pricing|markup|takeoff|"
        r"\$\d|over\s*budget|cost\s*report)\b",
        re.IGNORECASE,
    )),
    # CLIENT — owner/homeowner mentions
    ("CLIENT", re.compile(
        r"\b(client|homeowner|owner['s]?\s+(walk|review|call|response|approval|signoff|sign[\s-]*off)|"
        r"walkthrough|owner\s+walk|client\s+(call|email|update|approval|decision)|"
        r"co\s+approval|owner\s+approval)\b",
        re.IGNORECASE,
    )),
    # QUALITY — punch / rework / defects / dust / workmanship
    ("QUALITY", re.compile(
        r"\b(punch(\s*list|\s*walk)?|rework|defect|deficien(cy|cies)|"
        r"touch[\s-]*up|repair|dust|workmanship|hold\s*point|qc\s*sign[\s-]*off|"
        r"qa\s*(check|fail|pass)|inspection\s*fail|fail(ed)?\s*inspection|"
        r"crooked|damaged?|chipped?|scratched?|reseat|reinstall|"
        r"fix(ing)?\s+(the\s+)?(wall|floor|ceiling|trim|paint|grout))\b",
        re.IGNORECASE,
    )),
    # ADMIN — permits / inspections (passing) / insurance / internal
    ("ADMIN", re.compile(
        r"\b(permit|insurance|coi\b|certificate of insurance|"
        r"city of\s+\w+|building department|inspector(?!\s+fail)|"
        r"company\s*event|internal\s*(meeting|policy|process)|"
        r"holiday|vacation|out of office|ooo\b)\b",
        re.IGNORECASE,
    )),
    # SUB-TRADE — sub performance, hire/fire, dispute
    ("SUB-TRADE", re.compile(
        r"\b(sub(contractor)?\s+(performance|fire|replace|hire|swap|drop|kick)|"
        r"non[\s-]*responsive|chronic|escalat(e|ion)\s+(sub|crew)|"
        r"crew\s*(?:size|capacity|absent|missing)|missed\s*day|absent\s*day|"
        r"sub\s*(?:credit|deduction|backcharge|withhold)|"
        r"scope\s*dispute|scope\s*disagree)\b",
        re.IGNORECASE,
    )),
    # SCHEDULE — start dates / sequence / confirmations
    ("SCHEDULE", re.compile(
        r"\b(start\s*date|begin\s*date|confirm\s+(start|crew|sub|date|attendance)|"
        r"sequence|sequencing|preced(?:ing|or)|predecessor|successor|"
        r"hold\s+(start|drywall|tile|trim)|run\s+parallel|"
        r"reschedule|push\s+(?:back|out)|move\s+(?:up|forward|out)|"
        r"book\s+(?:date|crew|sub)|schedule\s+(?:walk|inspection|sub)|"
        r"target\s+(?:date|move[\s-]*in|completion)|"
        r"this\s+(?:mon|tue|wed|thu|fri|saturday|sunday)|by\s+(?:mon|tue|wed|thu|fri))\b",
        re.IGNORECASE,
    )),
]


def classify(item: dict) -> tuple[str, str, list[str]]:
    """Return (category, confidence, reasons).

    confidence ∈ {"high", "medium", "low"}
    reasons = list of trace strings explaining why this category won
    """
    type_ = (item.get("type") or "").upper()
    text = " ".join(filter(None, [item.get("action"), item.get("update")]))
    reasons: list[str] = []

    # Step 1: keyword hits (most specific signal)
    keyword_hits: list[str] = []
    for cat, pattern in KEYWORD_PATTERNS:
        if pattern.search(text):
            keyword_hits.append(cat)

    # Step 2: type-field default
    type_default = TYPE_DEFAULTS.get(type_, "ADMIN")

    # Decision logic:
    # - If keyword hits exist, the FIRST hit wins (KEYWORD_PATTERNS ordered by specificity)
    # - If first keyword agrees with type_default → high confidence
    # - If keyword exists but disagrees with type_default → medium (keyword wins)
    # - If no keyword and type_default is strong (SELECTION/SCHEDULE/etc.) → medium
    # - If no keyword and type_default is FOLLOWUP/ADMIN → low (likely ADMIN)
    if keyword_hits:
        chosen = keyword_hits[0]
        if chosen == type_default:
            reasons.append(f"keyword+type both → {chosen}")
            return chosen, "high", reasons
        else:
            reasons.append(f"keyword '{chosen}' overrides type-default '{type_default}'")
            if len(keyword_hits) > 1:
                reasons.append(f"other keyword hits: {keyword_hits[1:]}")
            return chosen, "medium", reasons

    # No keyword hit — fall back to type default
    if type_ in ("FOLLOWUP",):
        reasons.append(f"no keyword; type='{type_}' is ambiguous → ADMIN (review)")
        return "ADMIN", "low", reasons
    reasons.append(f"no keyword; type-default '{type_}' → {type_default}")
    return type_default, "medium", reasons


def backfill_binder(binder: dict, force: bool, log_lines: list[str], stats: Counter) -> int:
    """Mutates binder in place. Returns count of items modified."""
    modified = 0
    pm = binder.get("meta", {}).get("pm", "?")
    items = binder.get("items", [])
    for item in items:
        already = item.get("category") in CATEGORIES
        if already and not force:
            stats["skipped_already_classified"] += 1
            continue
        cat, conf, reasons = classify(item)
        prior = item.get("category", "—")
        item["category"] = cat
        if not item.get("source"):
            item["source"] = "transcript"
        modified += 1
        stats[f"category:{cat}"] += 1
        stats[f"confidence:{conf}"] += 1
        flag = " [REVIEW]" if conf == "low" else ""
        log_lines.append(
            f"  {item['id']:<10} {pm[:18]:<18} type={item.get('type','?'):<13} "
            f"→ {cat:<11} ({conf}){flag}\n"
            f"    action: {(item.get('action') or '')[:90]}\n"
            f"    why: {' | '.join(reasons)}"
        )
    return modified


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill category/source on binder items.")
    parser.add_argument("--dry-run", action="store_true", help="Compute and log, but don't write.")
    parser.add_argument("--force", action="store_true",
                        help="Reclassify items that already have a category set.")
    args = parser.parse_args()

    if not BINDERS.exists():
        print(f"FATAL: binders dir not found: {BINDERS}", file=sys.stderr)
        return 2

    binder_files = sorted(BINDERS.glob("*.json"))
    if not binder_files:
        print(f"FATAL: no binders found in {BINDERS}", file=sys.stderr)
        return 2

    stats: Counter = Counter()
    log_lines: list[str] = []
    log_lines.append(f"# Backfill categories — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    log_lines.append(f"force={args.force}  dry_run={args.dry_run}")
    log_lines.append("")

    total_modified = 0
    for bf in binder_files:
        binder = json.loads(bf.read_text(encoding="utf-8"))
        log_lines.append(f"## {bf.name}")
        n = backfill_binder(binder, args.force, log_lines, stats)
        log_lines.append(f"  ({n} items modified)")
        log_lines.append("")
        total_modified += n
        if not args.dry_run and n > 0:
            bf.write_text(json.dumps(binder, indent=2, ensure_ascii=False), encoding="utf-8")

    log_lines.append("## Summary")
    log_lines.append(f"Total items modified: {total_modified}")
    for cat in CATEGORIES:
        log_lines.append(f"  {cat:<12} {stats[f'category:{cat}']:>4}")
    for c in ("high", "medium", "low"):
        log_lines.append(f"  conf:{c:<7} {stats[f'confidence:{c}']:>4}")
    if stats["skipped_already_classified"]:
        log_lines.append(f"  already classified (skipped): {stats['skipped_already_classified']}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"backfill-log-{ts}.md"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"\nBackfill complete. Modified {total_modified} items across {len(binder_files)} binders.")
    print(f"Log: {log_path}")
    print("\nDistribution:")
    for cat in CATEGORIES:
        print(f"  {cat:<12} {stats[f'category:{cat}']:>4}")
    print("\nConfidence:")
    for c in ("high", "medium", "low"):
        print(f"  {c:<7} {stats[f'confidence:{c}']:>4}")
    if args.dry_run:
        print("\n[dry-run] No files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
