"""Post-hoc dedup pass for binder action items.

Process.py occasionally produces near-duplicate items because the LLM
extracts slightly different sentences for the same underlying task
(see FISH-028 vs FISH-049 — both were "Martin to call Tom at D&D /
Banko Overhead Doors directly by Thu 4/30").

This script groups open items by (job, owner) and finds duplicate pairs
where:
  1. The first 30 chars of `action` match >85% via difflib
  2. OR same target_phase/related_phase + same priority + due dates within 7 days

For each duplicate pair: keep the OLDER item (lower id sort), merge the
newer's update text into the older's update field, mark the newer with
status=DUPLICATE_MERGED and merged_into=<older_id>. Items are NEVER
deleted — they stay in the binder for audit.

Run:
  python scripts/dedup_binders.py            # apply
  python scripts/dedup_binders.py --dry-run  # log only
  python scripts/dedup_binders.py --threshold 0.80  # tweak similarity cutoff

Idempotent: re-running ignores items already marked DUPLICATE_MERGED.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINDERS = ROOT / "binders"
LOG_DIR = ROOT / "scripts"

OPEN_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "OPEN", "IN PROGRESS"}
MERGED_STATUS = "DUPLICATE_MERGED"


def _normalize_action_head(action: str | None) -> str:
    if not action:
        return ""
    # Lowercase, strip leading owner-phrase ("Martin to ", "Bob/Jason to ")
    s = action.lower().strip()
    s = re.sub(r"^[a-z/\.\s]+to\s+", "", s, count=1)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Cap to 30 chars for the head similarity check
    return s[:30]


def _id_sort_key(item: dict) -> tuple:
    """Sort by job-prefix then numeric tail so 'FISH-001' < 'FISH-049' < 'FISH-100'."""
    iid = item.get("id") or ""
    m = re.match(r"^([A-Z_]+)[-_](\d+)$", iid)
    if not m:
        return (iid, 0)
    return (m.group(1), int(m.group(2)))


def _parse_iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _due_within(a: dict, b: dict, days: int) -> bool:
    da, db = _parse_iso(a.get("due")), _parse_iso(b.get("due"))
    if not da or not db:
        return False
    return abs((da - db).days) <= days


def _is_open(item: dict) -> bool:
    s = (item.get("status") or "").upper()
    return s in OPEN_STATUSES


def _is_already_merged(item: dict) -> bool:
    return (item.get("status") or "").upper() == MERGED_STATUS


def find_duplicates(items: list[dict], threshold: float) -> list[tuple[dict, dict, str, float]]:
    """Return list of (older_item, newer_item, reason, score)."""
    pairs: list[tuple[dict, dict, str, float]] = []

    # Filter to open items, group by (job, owner)
    open_items = [it for it in items if _is_open(it) and not _is_already_merged(it)]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for it in open_items:
        groups[(it.get("job") or "", it.get("owner") or "")].append(it)

    seen_ids: set[str] = set()
    for (_job, _owner), grp in groups.items():
        # Sort by ID so older (smaller id) comes first
        sorted_grp = sorted(grp, key=_id_sort_key)
        for i in range(len(sorted_grp)):
            older = sorted_grp[i]
            if older.get("id") in seen_ids:
                continue
            for j in range(i + 1, len(sorted_grp)):
                newer = sorted_grp[j]
                if newer.get("id") in seen_ids:
                    continue

                # Rule 1: action-head similarity
                head_a = _normalize_action_head(older.get("action"))
                head_b = _normalize_action_head(newer.get("action"))
                if head_a and head_b:
                    score = SequenceMatcher(None, head_a, head_b).ratio()
                    if score >= threshold:
                        pairs.append((older, newer, f"action-head similarity {score:.2f}", score))
                        seen_ids.add(newer.get("id"))
                        continue

                # Rule 2: same phase + same priority + due within 7d
                ph_a = (older.get("related_phase") or older.get("target_phase") or "").strip()
                ph_b = (newer.get("related_phase") or newer.get("target_phase") or "").strip()
                pri_a = (older.get("priority") or "").upper()
                pri_b = (newer.get("priority") or "").upper()
                if ph_a and ph_b and ph_a == ph_b and pri_a == pri_b and _due_within(older, newer, 7):
                    # Also require some action overlap (avoid 2 different items on same phase)
                    full_a = (older.get("action") or "").lower()
                    full_b = (newer.get("action") or "").lower()
                    soft = SequenceMatcher(None, full_a, full_b).ratio()
                    if soft >= 0.55:
                        pairs.append((older, newer, f"same phase+priority+near-due (soft {soft:.2f})", soft))
                        seen_ids.add(newer.get("id"))
                        continue

    return pairs


def merge_pair(older: dict, newer: dict, reason: str) -> None:
    """Mutate `newer` to DUPLICATE_MERGED with merged_into=<older.id>.
    Append newer's update text into older's update field for context."""
    older_update = older.get("update") or ""
    newer_update = newer.get("update") or ""
    newer_action = newer.get("action") or ""

    note = f"[merged from {newer.get('id')}]"
    if newer_update and newer_update not in older_update:
        appendage = f" {note} {newer_update.strip()}"
        older["update"] = (older_update + appendage).strip()
    elif newer_action and not newer_update:
        # Carry the newer item's action snippet as context
        snippet = newer_action.strip()
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        if snippet not in (older.get("action") or ""):
            older["update"] = (older_update + f" {note} {snippet}").strip()

    newer["status"] = MERGED_STATUS
    newer["merged_into"] = older.get("id")
    newer["merged_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    newer["merge_reason"] = reason


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-hoc dedup of binder items.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.85,
                        help="Action-head similarity cutoff (0.85 default).")
    args = parser.parse_args()

    binder_files = sorted(BINDERS.glob("*.json"))
    if not binder_files:
        print(f"FATAL: no binders in {BINDERS}", file=sys.stderr)
        return 2

    log_lines: list[str] = []
    log_lines.append(f"# Dedup binders — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    log_lines.append(f"threshold={args.threshold}  dry_run={args.dry_run}")
    log_lines.append("")

    total_open_before = 0
    total_open_after = 0
    total_merged = 0
    pair_samples: list[tuple] = []

    for bf in binder_files:
        binder = json.loads(bf.read_text(encoding="utf-8"))
        items = binder.get("items", [])

        open_before = sum(1 for it in items if _is_open(it))
        total_open_before += open_before

        pairs = find_duplicates(items, args.threshold)

        log_lines.append(f"## {bf.name}  ({open_before} open before)")
        if not pairs:
            log_lines.append("  No duplicates found.")
            log_lines.append("")
            total_open_after += open_before
            continue

        # Apply merges
        for older, newer, reason, score in pairs:
            log_lines.append(f"  MERGE  {newer.get('id')}  ->  {older.get('id')}  ({reason})")
            log_lines.append(f"    older: {(older.get('action') or '')[:140]}")
            log_lines.append(f"    newer: {(newer.get('action') or '')[:140]}")
            log_lines.append("")
            merge_pair(older, newer, reason)
            total_merged += 1
            if len(pair_samples) < 5:
                pair_samples.append((bf.name, older, newer, reason))

        open_after = sum(1 for it in items if _is_open(it))
        total_open_after += open_after
        log_lines.append(f"  ({open_before} -> {open_after} open · {len(pairs)} merged)")
        log_lines.append("")

        if not args.dry_run and pairs:
            bf.write_text(json.dumps(binder, indent=2, ensure_ascii=False), encoding="utf-8")

    log_lines.append("## Summary")
    log_lines.append(f"Total open items before: {total_open_before}")
    log_lines.append(f"Total open items after:  {total_open_after}")
    log_lines.append(f"Total merged:            {total_merged}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"dedup-log-{ts}.md"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print(f"\nDedup complete.")
    print(f"  Open items before: {total_open_before}")
    print(f"  Open items after:  {total_open_after}")
    print(f"  Merged:            {total_merged}")
    print(f"  Log: {log_path}")
    if args.dry_run:
        print("\n[dry-run] No files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
