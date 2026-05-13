"""Backfill todos.sub_id by regex-matching each todo's title + excerpt
against the subs.aliases list.

Algorithm:
- Load all subs + their aliases from Supabase
- For each todo with sub_id IS NULL, scan title + source_excerpt
- Match each alias as a whole-word, case-insensitive regex
- When multiple subs match, pick the one with the LONGEST matched alias
  (so "Tom Sanger" wins over "Sanger" alone)
- Persist sub_id

Run: python scripts/backfill_sub_links.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from process import _supabase_client


def main():
    client = _supabase_client()
    if client is None:
        print("FAIL: no supabase client")
        sys.exit(1)

    # 1. Load subs + aliases
    subs_resp = client.table("subs").select("id, name, aliases").execute()
    subs = subs_resp.data or []
    print(f"Loaded {len(subs)} subs")

    # Pre-compile alias patterns. For each sub, build a list of
    # (compiled_regex, alias_string) pairs. Whole-word, case-insensitive.
    patterns: list[tuple[re.Pattern, str, str]] = []
    for s in subs:
        for alias in s.get("aliases") or []:
            # Escape the alias for regex, then wrap with word boundaries.
            # Use (?<!\w) and (?!\w) so punctuation also counts as a boundary
            # (e.g., "Tom Sanger." matches "Tom Sanger").
            pat = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
            patterns.append((pat, alias, s["id"]))

    # 2. Load all todos
    todos_resp = client.table("todos").select("id, title, source_excerpt, sub_id").execute()
    todos = todos_resp.data or []
    print(f"Scanning {len(todos)} todos…")

    updates: list[tuple[str, str]] = []
    already_linked = 0
    no_match = 0
    multi_match = 0
    matches_by_sub: dict[str, int] = {}

    for t in todos:
        if t.get("sub_id"):
            already_linked += 1
            continue
        text = (t.get("title") or "") + " " + (t.get("source_excerpt") or "")
        best: tuple[int, str] | None = None  # (alias_len, sub_id)
        seen_sub_ids: set[str] = set()
        for pat, alias, sub_id in patterns:
            if pat.search(text):
                seen_sub_ids.add(sub_id)
                if best is None or len(alias) > best[0]:
                    best = (len(alias), sub_id)
        if best is None:
            no_match += 1
            continue
        if len(seen_sub_ids) > 1:
            multi_match += 1
        sub_id = best[1]
        updates.append((t["id"], sub_id))
        matches_by_sub[sub_id] = matches_by_sub.get(sub_id, 0) + 1

    print(f"  already linked:    {already_linked}")
    print(f"  no alias matched:  {no_match}")
    print(f"  multi-match (longest-alias won): {multi_match}")
    print(f"  new links to apply: {len(updates)}")

    # 3. Apply updates — one row at a time to avoid upsert insert-collisions.
    # ~100 round-trips at ~150ms ≈ 15s total. Fine for a one-shot backfill.
    if updates:
        for i, (tid, sid) in enumerate(updates, 1):
            client.table("todos").update({"sub_id": sid}).eq("id", tid).execute()
            if i % 25 == 0:
                print(f"  {i}/{len(updates)}…")
        print(f"Applied {len(updates)} sub_id updates.")

    # Report top subs
    print()
    print("Top 10 subs by todo link count:")
    by_count = sorted(matches_by_sub.items(), key=lambda kv: -kv[1])[:10]
    for sid, n in by_count:
        sub = next((s for s in subs if s["id"] == sid), None)
        sub_name = sub["name"] if sub else sid
        print(f"  {n:>3}  {sub_name}")


if __name__ == "__main__":
    main()
