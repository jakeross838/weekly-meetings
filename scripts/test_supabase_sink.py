"""End-to-end smoke test for the Supabase sink.

Loads every PM's binder, runs sink_to_supabase against the real Supabase
project, then queries back to verify rowcount matches non-DISMISSED items.

Run: python scripts/test_supabase_sink.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# process.py loads .env at import time
from process import sink_to_supabase, _supabase_client, _pm_slug


class _ConsoleLogger:
    def info(self, msg): print(f"[info]  {msg}")
    def error(self, msg): print(f"[error] {msg}", file=sys.stderr)


PMS = [
    "Martin Mannix",
    "Jason Szykulski",
    "Lee Worthy",
    "Bob Mozine",
    "Nelson Belanger",
]


def main():
    logger = _ConsoleLogger()
    client = _supabase_client()
    if client is None:
        print("FAIL: supabase client unavailable; check .env")
        sys.exit(1)

    all_pass = True
    for pm_name in PMS:
        binder_path = ROOT / "binders" / f"{pm_name.replace(' ', '_')}.json"
        if not binder_path.exists():
            print(f"SKIP: no binder for {pm_name}")
            continue
        binder = json.loads(binder_path.read_text(encoding="utf-8"))
        items = binder.get("items", [])
        non_dismissed = [i for i in items if (i.get("status") or "").upper() != "DISMISSED"]
        print(f"\n--- {pm_name}: {len(items)} items, {len(non_dismissed)} non-DISMISSED ---")
        n = sink_to_supabase(pm_name, binder, "smoke-test.txt", logger)
        if n != len(non_dismissed):
            print(f"FAIL: sink returned {n}, expected {len(non_dismissed)}")
            all_pass = False
            continue
        resp = client.table("todos").select("id", count="exact").eq("pm_id", _pm_slug(pm_name)).execute()
        actual = resp.count if hasattr(resp, "count") else len(resp.data or [])
        if actual < len(non_dismissed):
            print(f"FAIL: queried {actual} rows, expected at least {len(non_dismissed)}")
            all_pass = False
            continue
        print(f"PASS: {actual} rows in Supabase for {pm_name}")

    if not all_pass:
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
