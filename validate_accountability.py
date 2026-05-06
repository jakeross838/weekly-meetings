"""Phase 6.6 accountability-loop validator.

Runs after build_meeting_prep.py to diff this week's meeting-commitments
snapshot against last week's. Produces a per-PM report:

  - Closed (in last week, absent this week — content_hash gone)
  - Carried (content_hash present in both weeks)
  - New (this week only)
  - Stuck (3+ consecutive weeks)

Also flags near-misses: items in "closed" whose title is 80%+ similar to
items in "new" — likely the same commitment phrased differently after a
re-run, worth surfacing for manual review.

Writes the report to `data/accountability-week-{iso_week}.md` and emits a
single-line status banner that's useful in Task Scheduler logs.
"""
from __future__ import annotations

import json
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
COMMITMENTS = DATA / "meeting-commitments.json"

NEAR_MISS_THRESHOLD = 0.80
STUCK_WEEKS = 3


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def main() -> int:
    if not COMMITMENTS.exists():
        print(f"ERROR: {COMMITMENTS} not found. Run build_meeting_prep.py first.")
        return 2

    state = json.loads(COMMITMENTS.read_text(encoding="utf-8"))
    weeks = state.get("weeks", [])

    if len(weeks) == 0:
        print("ERROR: meeting-commitments.json has no week entries.")
        return 2

    this_week = weeks[-1]
    last_week = weeks[-2] if len(weeks) >= 2 else None

    iso_week = this_week.get("iso_week", "unknown")
    today = this_week.get("today", "")
    out_path = DATA / f"accountability-week-{iso_week}.md"

    lines: list[str] = []
    lines.append(f"# Accountability Validation — {iso_week}")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  ")
    lines.append(f"This week: **{iso_week}** (today {today}).  ")
    if last_week:
        lines.append(f"Comparing against: **{last_week.get('iso_week')}** (today {last_week.get('today')}).")
    else:
        lines.append("First run — no last-week data to diff against.")
    lines.append("")

    if last_week is None:
        # First run — just summarise this week's snapshot
        total_this = sum(len((info.get("must_discuss") or [])) for info in (this_week.get("by_pm") or {}).values())
        lines.append(f"**This week captured: {total_this} commitments across {len(this_week.get('by_pm') or {})} PMs.**")
        lines.append("")
        lines.append("Next week's run will compare against this snapshot.")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"FIRST_RUN iso_week={iso_week} commitments={total_this} wrote={out_path}")
        return 0

    # ---- Diff per-PM ----
    by_pm_this = this_week.get("by_pm") or {}
    by_pm_last = last_week.get("by_pm") or {}
    all_pms = sorted(set(by_pm_this.keys()) | set(by_pm_last.keys()))

    grand_last = grand_this = grand_closed = grand_carried = grand_new = grand_stuck = 0

    pm_blocks: list[tuple[str, dict]] = []
    near_miss_lines: list[str] = []

    for pm in all_pms:
        last_md = (by_pm_last.get(pm) or {}).get("must_discuss") or []
        this_md = (by_pm_this.get(pm) or {}).get("must_discuss") or []
        last_hashes = {it.get("content_hash"): it for it in last_md if it.get("content_hash")}
        this_hashes = {it.get("content_hash"): it for it in this_md if it.get("content_hash")}

        closed_hashes = set(last_hashes) - set(this_hashes)
        carried_hashes = set(last_hashes) & set(this_hashes)
        new_hashes = set(this_hashes) - set(last_hashes)

        # Stuck-3w+: items present in last STUCK_WEEKS consecutive weeks for this PM
        stuck_items: list[dict] = []
        if len(weeks) >= STUCK_WEEKS:
            recent = weeks[-STUCK_WEEKS:]
            persistent = None
            for w in recent:
                md = ((w.get("by_pm") or {}).get(pm) or {}).get("must_discuss") or []
                hashes = {it.get("content_hash") for it in md if it.get("content_hash")}
                persistent = hashes if persistent is None else (persistent & hashes)
                if not persistent:
                    break
            for h in (persistent or set()):
                if h in this_hashes:
                    stuck_items.append(this_hashes[h])

        # Near-miss detection: closed × new pairs with high text similarity
        for ch in closed_hashes:
            closed_it = last_hashes[ch]
            ctitle = (closed_it.get("title") or "") + " " + (closed_it.get("summary_line") or "")
            for nh in new_hashes:
                new_it = this_hashes[nh]
                ntitle = (new_it.get("title") or "") + " " + (new_it.get("summary_line") or "")
                ratio = text_similarity(ctitle, ntitle)
                if ratio >= NEAR_MISS_THRESHOLD:
                    near_miss_lines.append(
                        f"- **{pm}** · similarity={ratio:.2f}  \n"
                        f"  closed `{closed_it.get('content_hash')}` · {closed_it.get('title','')}  \n"
                        f"  new    `{new_it.get('content_hash')}` · {new_it.get('title','')}"
                    )

        grand_last += len(last_md)
        grand_this += len(this_md)
        grand_closed += len(closed_hashes)
        grand_carried += len(carried_hashes)
        grand_new += len(new_hashes)
        grand_stuck += len(stuck_items)

        pm_blocks.append(
            (pm, {
                "last_count": len(last_md),
                "this_count": len(this_md),
                "closed": [last_hashes[h] for h in closed_hashes],
                "carried": [this_hashes[h] for h in carried_hashes],
                "new": [this_hashes[h] for h in new_hashes],
                "stuck": stuck_items,
            }),
        )

    # ---- Summary ----
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Bucket  | Count |")
    lines.append(f"|---------|-------|")
    lines.append(f"| Last week ({last_week.get('iso_week')}) commitments captured | {grand_last} |")
    lines.append(f"| This week ({iso_week}) commitments captured                  | {grand_this} |")
    lines.append(f"| Closed (resolved — content_hash gone)                        | {grand_closed} |")
    lines.append(f"| Carried (still firing in current insights)                   | {grand_carried} |")
    lines.append(f"| New                                                           | {grand_new} |")
    lines.append(f"| Stuck-3w+                                                     | {grand_stuck} |")
    lines.append("")

    # ---- Per-PM ----
    lines.append("## Per-PM detail")
    lines.append("")
    for pm, blk in pm_blocks:
        lines.append(f"### {pm}")
        lines.append(f"- Last week: {blk['last_count']} · This week: {blk['this_count']}")
        lines.append(
            f"- Closed: {len(blk['closed'])} · Carried: {len(blk['carried'])} · "
            f"New: {len(blk['new'])} · Stuck: {len(blk['stuck'])}"
        )

        def render_items(label: str, items: list[dict]) -> None:
            if not items:
                return
            lines.append("")
            lines.append(f"**{label}:**")
            for it in items:
                title = it.get("title") or "(no title)"
                summary = it.get("summary_line") or ""
                ch = it.get("content_hash", "")
                lines.append(f"- `{ch}` · {title}")
                if summary:
                    lines.append(f"  - {summary}")

        render_items("Closed", blk["closed"])
        render_items("Carried", blk["carried"])
        render_items("New", blk["new"])
        render_items("Stuck-3w+", blk["stuck"])
        lines.append("")

    # ---- Near-misses ----
    lines.append("## Near-miss review (closed vs new ≥80% similar)")
    lines.append("")
    if near_miss_lines:
        lines.append(
            "These items don't match by content_hash but their text is highly similar — "
            "may be the same commitment with a small wording change after a re-run. "
            "Worth a manual eyeball:"
        )
        lines.append("")
        lines.extend(near_miss_lines)
    else:
        lines.append("No near-misses detected.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")

    # Single-line status banner for Task Scheduler logs
    print(
        f"OK iso_week={iso_week} last={grand_last} this={grand_this} "
        f"closed={grand_closed} carried={grand_carried} new={grand_new} stuck={grand_stuck} "
        f"near_miss={len(near_miss_lines)} -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(3)
