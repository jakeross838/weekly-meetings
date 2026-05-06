"""One-time category audit + correction pass for binder action items.

The original backfill (`scripts/backfill_categories.py`) classified items
correctly for ~75% of cases but produced a noticeable miscategorization
rate on items where the existing v1 `type` field misled the rule-based
classifier:

  - SCHEDULE items mentioning "sample", "photo", "show" → likely SELECTION/CLIENT
  - PROCUREMENT items mentioning "seal", "protect", "monitor", "inspect" → QUALITY
  - QUALITY items mentioning "order", "PO", "delivery" → PROCUREMENT
  - BUDGET items without dollars/GP/cost references → suspicious
  - CLIENT items about subs → SUB-TRADE
  - Vague "follow up", "chase", "check-in" with unclear target → ambiguous

This script applies a stricter, action-text-only rule set with explicit
exemplars (per the kickoff). For high-confidence rule matches, the
category is auto-corrected. Anything that remains ambiguous gets
`_category_review: true` so templates can render a "?" indicator.

Run:
  python scripts/audit_categories.py            # apply
  python scripts/audit_categories.py --dry-run  # log only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINDERS = ROOT / "binders"
LOG_DIR = ROOT / "scripts"

VALID_CATEGORIES = {
    "SCHEDULE", "PROCUREMENT", "SUB-TRADE", "CLIENT",
    "QUALITY", "BUDGET", "ADMIN", "SELECTION",
}

# Known client/designer first-name patterns — used by the SELECTION rule
# to confirm "assemble [photo/sample] + client name" matches.
_CLIENT_NAMES_RE = re.compile(
    r"\b(Bishop|Bishops|Courtney|Fish(?:es)?|Krauss|Markgraf|Pou|Ruthven|"
    r"Molinari|Drummond|Dewberry|Clark|Biales|Johnson|Harllee|"
    r"Patrick|Cindy|Mara|Joe|Mark|Tom|Alex|Rob|Sego|Andrew|Lee|Jake|Jacob)\b",
)

# Each rule = (target_category, regex_pattern, description). Rules are
# tried in order; first match wins. Rules express HIGH-CONFIDENCE
# corrections only — patterns that strongly imply a category regardless
# of what the original backfill chose.
HIGH_CONFIDENCE_RULES = [
    # CLIENT — explicit "follow up / chase / push / force" + client name +
    # decision/sign-off/direction (wmp18 expanded rule)
    ("CLIENT", re.compile(
        r"\b(?:follow\s*up\s+with|chase|push|force|loop\s+back\s+with)\s+"
        r"(?:Bishop|Bishops|Courtney|Fish(?:es)?|Krauss|Markgraf|Pou|Ruthven|"
        r"Molinari|Drummond|Dewberry|Clark|Biales|Johnson|Harllee|"
        r"Patrick|Cindy|Mara|owner|homeowner|client)\s+"
        r"(?:on|for|about)\s+"
        r"(?:decision|sign[\s-]*off|direction|written|approval|response|feedback)",
        re.IGNORECASE,
    ), "follow-up/chase/push/force + client + decision/signoff/direction"),

    # SELECTION — "assemble photo/sample/combo/presentation" + client name
    # (wmp18 expanded rule)
    ("SELECTION", re.compile(
        r"\bassemble\s+(?:[\w\-/+]+\s+)*?(?:photo|sample|combo|presentation|"
        r"swatch|board|comparison|finish\s+sample)",
        re.IGNORECASE,
    ), "assemble [photo/sample/combo/presentation] for client decision"),

    # SUB-TRADE — "walk {sub} through" / "review with {sub}" (wmp18 rule)
    ("SUB-TRADE", re.compile(
        r"\b(?:walk\s+\w+\s+through|review\s+with\s+(?:TNT|Watts|Gator|"
        r"Smart\s*House|SmartShield|Tom\s+Sanger|Cucine\s+Ricci|First\s+Choice|"
        r"HBS\s+Drywall|Gilkey|Banko|D&D|Metro\s+Electric|Lonestar|"
        r"Volcano\s+Stone|Faust|Myers|Nemesio|Rangel|DB\s+Welding|"
        r"Sight\s+to\s+See|Precision\s+Stairs|CoatRite|Integrity\s+Floors|"
        r"Sarasota\s+Cab|Ross\s+Built\s+Crew|Field\s*Crew))\b",
        re.IGNORECASE,
    ), "walk-through / review-with sub by name"),

    # QUALITY — "monitor weekly|daily|through" + condition (wmp18 rule)
    ("QUALITY", re.compile(
        r"\bmonitor\s+(?:weekly|daily|through|for\s+\w+|until|while)",
        re.IGNORECASE,
    ), "monitor + frequency/duration condition"),
    # PROCUREMENT — material orders, deliveries, POs, BUYOUTS
    ("PROCUREMENT", re.compile(
        r"\b(to\s+(place\s+(an?\s+)?)?order(?!\s+(?:of\s+the\s+day|the\s+walk))|"
        r"to\s+order\s+|"
        r"deliver(y|ies)\s+(scheduled|date|expected|confirmed)|"
        r"po\s+(creat|issu|releas|cut)|"
        r"purchase\s*order|"
        r"buyout|"
        r"long[\s-]*lead|"
        r"submittal\s+(approval|review)|"
        r"steel\s+package\s+order)\b",
        re.IGNORECASE,
    ), "explicit ordering / PO / buyout / long-lead language"),

    # QUALITY — physical site work, sealing, monitoring, inspecting
    ("QUALITY", re.compile(
        r"\b(to\s+(seal|protect|monitor|inspect|rework|repair|"
        r"touch[\s-]*up|reinstall|reseat|fix\s+the|patch|caulk|sand|prime)|"
        r"to\s+install\s+(foam\s+protection|protection\s+|plastic\s+protection|"
        r"jamb[\s-]*protection|drop[\s-]*cloth|sound[\s-]*dampening|"
        r"acoustic\s+batt|french\s+drain)|"
        r"to\s+walk\s+(all|the|punch)|"
        r"to\s+pull\s+string[\s-]*line|"
        r"to\s+oversee\s+\w+\s+(repair|cut[\s-]*out|float|sand|patch)|"
        r"punch\s+(list|walk)|"
        r"hold\s+point|qc\s+sign[\s-]*off|"
        r"inspection\s+fail|fail(ed)?\s+inspection)\b",
        re.IGNORECASE,
    ), "physical/quality verb (seal/protect/monitor/inspect/rework/punch)"),

    # SELECTION — finishes, samples, design decisions, designer items
    ("SELECTION", re.compile(
        r"\b(to\s+(assemble|push|force|chase|follow\s+up\s+with)\s+\w+\s+"
        r"(?:on\s+)?(?:outstanding[\s-]*selections?|finish|color|design)|"
        r"to\s+lock\s+\w+\s+(?:floor\s+)?finish|"
        r"to\s+(get|push)\s+\w+\s+(?:on|for)\s+(?:Farrow|Mahogany|paint\s+color|"
        r"finish\s+schedule|hardware\s+finish)|"
        r"to\s+specify\s+\w+\s+(?:detail|finish|color)|"
        r"sample\s+(board|approval|photo|combo)|"
        r"swatch|"
        r"designer\s+(call|review|spec|item)|"
        r"selection(s)?\s+(email|sheet|chase|call|update)|"
        r"square[\s-]*pattern\s+tile|"
        r"AC\s+louver\s+(door|detail))\b",
        re.IGNORECASE,
    ), "selection / finish / designer language"),

    # BUDGET — explicit money, GP, CO, pay app
    ("BUDGET", re.compile(
        r"\b(co[-\s]?\d|change\s+order|pcco|"
        r"pay\s*app(lication)?|"
        r"gp\s*(?:vs|target|exposure|risk|fade)|gross\s*profit|"
        r"\$\d|over\s*budget|cost\s*report|markup|"
        r"credit\s*back|backcharge|deduct(ion)?)\b",
        re.IGNORECASE,
    ), "explicit money / CO / GP language"),

    # CLIENT — owner / homeowner / client decisions (NOT sub references)
    ("CLIENT", re.compile(
        r"\b(homeowner('s)?|owner['s]?\s+(walk|review|approval|signoff|sign[\s-]*off|"
        r"decision|approve|response|feedback)|"
        r"walkthrough|client\s+(call|email|update|approval|decision|response|"
        r"sign[\s-]*off|sentiment))\b",
        re.IGNORECASE,
    ), "owner/homeowner/client direct language"),

    # SUB-TRADE — performance / hire-fire / scope dispute
    ("SUB-TRADE", re.compile(
        r"\b(non[\s-]*responsive|sub\s+(performance|fire|replace|swap|drop|kick|"
        r"escalat\w+|withhold|backcharge|credit)|"
        r"chronic\s+(?:sub|issue)|"
        r"crew\s+(absent|missing|reduced)|"
        r"escalat\w+\s+to\s+(?:principal|partner|owner)|"
        r"scope\s+(dispute|disagree))\b",
        re.IGNORECASE,
    ), "sub-performance / hire-fire / scope-dispute language"),
]

# Lower-confidence patterns that flag the item for review but don't
# auto-correct.
SUSPECT_PATTERNS = [
    ("review", re.compile(r"^\s*\w+\s+to\s+(follow\s+up|chase|check[\s-]*in|"
                          r"loop\s+back)\s*$", re.IGNORECASE),
     "vague follow-up — target unclear"),
    ("review", re.compile(r"^\s*\w+\s+to\s+(?:discuss|review|look\s+into)",
                          re.IGNORECASE),
     "vague discuss/review verb"),
]


def _action_text(item: dict) -> str:
    return " ".join(filter(None, [item.get("action"), item.get("update")]))


def _budget_has_dollars(item: dict) -> bool:
    text = _action_text(item)
    return bool(re.search(r"\$\d|gp\b|gross\s+profit|change\s+order|pay\s*app|"
                          r"co[-\s]?\d|cost\s+report|over\s+budget",
                          text, re.IGNORECASE))


def _client_mentions_sub(item: dict) -> bool:
    text = _action_text(item)
    sub_indicators = re.search(
        r"\b(sub(contractor)?\b|crew\b|TNT\b|Watts\b|Gator\b|Smart\s*House|"
        r"SmartShield|Tom\s+Sanger|Cucine\s+Ricci|First\s+Choice|HBS\s+Drywall|"
        r"Gilkey|Banko|D&D|Metro\s+Electric|Lonestar|Volcano\s+Stone|"
        r"Faust|Myers|Nemesio|Rangel|DB\s+Welding|Sight\s+to\s+See|"
        r"Precision\s+Stairs|CoatRite|Integrity\s+Floors)\b",
        text, re.IGNORECASE)
    return bool(sub_indicators)


def classify_correction(item: dict) -> tuple[str | None, str, str]:
    """Returns (new_category | None, confidence, reason).

    confidence ∈ {"high", "review"}
    """
    text = _action_text(item)
    current_cat = (item.get("category") or "").upper()

    # First: high-confidence rule patterns
    for target_cat, pat, desc in HIGH_CONFIDENCE_RULES:
        if pat.search(text):
            if current_cat == target_cat:
                return None, "ok", f"already {target_cat} ({desc})"
            return target_cat, "high", f"matched: {desc}"

    # Second: BUDGET sanity check — if categorized BUDGET but no money mentions
    if current_cat == "BUDGET" and not _budget_has_dollars(item):
        # Try to suggest a better category
        if re.search(r"\b(schedule|confirm|start|date|sequence)\b", text, re.IGNORECASE):
            return "SCHEDULE", "high", "categorized BUDGET but no money refs; schedule language present"
        return None, "review", "categorized BUDGET but no money refs found"

    # Third: CLIENT sanity check — if categorized CLIENT but action mentions a sub
    if current_cat == "CLIENT" and _client_mentions_sub(item) and \
       not re.search(r"\b(homeowner|owner['s]?|walkthrough|client)\b", text, re.IGNORECASE):
        return "SUB-TRADE", "high", "categorized CLIENT but action targets a sub, not a client"

    # Fourth: vague follow-up / discuss patterns → review flag
    for _, pat, desc in SUSPECT_PATTERNS:
        if pat.search(item.get("action") or ""):
            return None, "review", desc

    return None, "ok", ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Category audit + correction pass.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    binder_files = sorted(BINDERS.glob("*.json"))
    if not binder_files:
        print(f"FATAL: no binders in {BINDERS}", file=sys.stderr)
        return 2

    log_lines: list[str] = []
    log_lines.append(f"# Category audit + correction — "
                     f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    log_lines.append(f"dry_run={args.dry_run}")
    log_lines.append("")

    total_audited = 0
    total_corrected = 0
    total_flagged = 0
    transitions: Counter = Counter()

    for bf in binder_files:
        binder = json.loads(bf.read_text(encoding="utf-8"))
        items = binder.get("items", [])
        per_binder_corrections = 0
        per_binder_flagged = 0

        log_lines.append(f"## {bf.name}")
        for item in items:
            # Skip items that are no longer open (COMPLETE, DISMISSED, DUPLICATE_MERGED)
            status = (item.get("status") or "").upper()
            if status in ("COMPLETE", "DISMISSED", "DUPLICATE_MERGED"):
                continue
            total_audited += 1

            new_cat, conf, reason = classify_correction(item)
            if new_cat and conf == "high":
                old_cat = item.get("category")
                if old_cat != new_cat:
                    log_lines.append(
                        f"  CORRECT  {item.get('id'):<10} "
                        f"{old_cat or '(none)':<11} -> {new_cat:<11}  ({reason})"
                    )
                    log_lines.append(
                        f"    action: {(item.get('action') or '')[:120]}"
                    )
                    item["category"] = new_cat
                    item["_category_corrected_from"] = old_cat
                    item.pop("_category_review", None)
                    per_binder_corrections += 1
                    total_corrected += 1
                    transitions[(old_cat, new_cat)] += 1
            elif conf == "review":
                if not item.get("_category_review"):
                    item["_category_review"] = True
                    log_lines.append(
                        f"  FLAG     {item.get('id'):<10} "
                        f"{item.get('category', '(none)'):<11}  ({reason})"
                    )
                    log_lines.append(
                        f"    action: {(item.get('action') or '')[:120]}"
                    )
                    per_binder_flagged += 1
                    total_flagged += 1
            elif conf == "ok":
                # Item is in the right category — clear any stale review flag
                if item.get("_category_review"):
                    item.pop("_category_review", None)

        if per_binder_corrections == 0 and per_binder_flagged == 0:
            log_lines.append("  (no changes)")
        else:
            log_lines.append(
                f"  ({per_binder_corrections} corrected, {per_binder_flagged} flagged for review)"
            )
        log_lines.append("")

        if not args.dry_run and (per_binder_corrections > 0 or per_binder_flagged > 0):
            bf.write_text(json.dumps(binder, indent=2, ensure_ascii=False), encoding="utf-8")

    log_lines.append("## Summary")
    log_lines.append(f"Total items audited (open only): {total_audited}")
    log_lines.append(f"Total auto-corrected:            {total_corrected}")
    log_lines.append(f"Total flagged for review:        {total_flagged}")
    log_lines.append("")
    if transitions:
        log_lines.append("Transitions:")
        for (old, new), n in sorted(transitions.items(), key=lambda kv: -kv[1]):
            log_lines.append(f"  {old or '(none)':<11} -> {new:<11}  {n}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"category-correction-log-{ts}.md"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print(f"\nCategory audit complete.")
    print(f"  Audited:    {total_audited}")
    print(f"  Corrected:  {total_corrected}")
    print(f"  Flagged:    {total_flagged}")
    print(f"  Log:        {log_path}")
    if transitions:
        print(f"\nTransitions:")
        for (old, new), n in sorted(transitions.items(), key=lambda kv: -kv[1]):
            print(f"  {old or '(none)':<11} -> {new:<11}  {n}")
    if args.dry_run:
        print("\n[dry-run] No files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
