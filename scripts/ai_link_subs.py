"""Use Claude to link the remaining unlinked todos to subs.

For each todo with sub_id NULL, send the title + excerpt + sub catalog to
Claude Haiku 4.5 (cheap, fast classifier) and ask for the matching sub_id
or NONE.

Run: python scripts/ai_link_subs.py
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from process import _supabase_client


MODEL = "claude-haiku-4-5-20251001"
BATCH = 25


def main():
    sb = _supabase_client()
    if sb is None:
        print("FAIL: no supabase client")
        sys.exit(1)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("FAIL: ANTHROPIC_API_KEY missing from .env")
        sys.exit(1)
    ai = anthropic.Anthropic()

    # 1. Catalog
    subs = sb.table("subs").select("id, name, trade, aliases").execute().data
    valid_ids = {s["id"] for s in subs}
    catalog_lines = []
    for s in sorted(subs, key=lambda x: x["name"]):
        aliases = ", ".join(s.get("aliases") or [])
        trade = s.get("trade") or "?"
        catalog_lines.append(f"  {s['id']} — {s['name']} (trade: {trade}) [aliases: {aliases}]")
    catalog_str = "\n".join(catalog_lines)
    print(f"Catalog: {len(subs)} subs")

    # 2. Unlinked todos
    todos = sb.table("todos").select("id, title, source_excerpt").is_("sub_id", "null").execute().data
    print(f"Unlinked todos to classify: {len(todos)}")

    # 3. Batch through Claude
    updates: list[tuple[str, str]] = []
    none_count = 0
    for i in range(0, len(todos), BATCH):
        batch = todos[i:i + BATCH]
        # Build batch payload
        lines = []
        for t in batch:
            title = (t.get("title") or "")[:220]
            excerpt = (t.get("source_excerpt") or "")[:220]
            line = f"- {t['id']}: {title}"
            if excerpt:
                line += f" || ctx: {excerpt}"
            lines.append(line)
        todos_block = "\n".join(lines)

        prompt = f"""You are linking construction-project action items to subcontractors from a fixed catalog.

For each TODO below, identify which sub from the CATALOG is referenced — by company name, employee/owner first name, or unambiguous context. Return "NONE" when no catalog match is clearly referenced (e.g., the item is purely internal to Ross Built staff, or only mentions clients/designers, or references someone not in the catalog).

CATALOG (id — Name (trade) [aliases]):
{catalog_str}

TODOS:
{todos_block}

Return ONLY a JSON array — one entry per todo, in the same order:
[{{"id":"<todo-id>","sub_id":"<catalog-id-or-NONE>"}}, ...]

Be conservative. Prefer NONE over guessing. Only link when the text clearly implicates that specific sub."""

        try:
            resp = ai.messages.create(
                model=MODEL,
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            print(f"  Batch {i // BATCH + 1}: API error: {type(e).__name__}: {e}")
            continue

        text = "".join(block.text for block in resp.content if block.type == "text")
        # Find the JSON array
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            print(f"  Batch {i // BATCH + 1}: no JSON in response, skipping")
            continue
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            print(f"  Batch {i // BATCH + 1}: JSON parse failed: {e}")
            continue

        batch_links = 0
        for entry in parsed:
            tid = entry.get("id")
            sid = entry.get("sub_id")
            if not tid or not sid:
                continue
            if sid == "NONE":
                none_count += 1
                continue
            if sid not in valid_ids:
                # Hallucinated sub_id — skip
                continue
            updates.append((tid, sid))
            batch_links += 1
        print(f"  Batch {i // BATCH + 1}/{(len(todos) + BATCH - 1) // BATCH}: {batch_links} links / {len(batch)} todos")
        time.sleep(0.5)  # gentle rate-limit

    print(f"\nTotal new AI links: {len(updates)}  (NONE: {none_count})")

    # 4. Apply
    for j, (tid, sid) in enumerate(updates, 1):
        sb.table("todos").update({"sub_id": sid}).eq("id", tid).execute()
        if j % 25 == 0:
            print(f"  applied {j}/{len(updates)}")

    # 5. Final tally
    r = sb.table("todos").select("id", count="exact", head=True).not_.is_("sub_id", "null").execute()
    r2 = sb.table("todos").select("id", count="exact", head=True).execute()
    print(f"\nFinal state: {r.count}/{r2.count} todos linked ({100 * r.count / r2.count:.0f}%)")


if __name__ == "__main__":
    main()
