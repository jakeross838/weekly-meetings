"""Gate 1B smoke test: parse the Krauss October 2025 pay app and report.

Does NOT write to Supabase. Just exercises parse_pay_app() and prints
enough output to verify the parser is correct.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "parsers"))

from pay_app_parser import parse_pay_app  # noqa: E402


KRAUSS_FILE = Path(r"C:/Users/Jake/Downloads/Krauss_pay_app_10_October_25.xlsx")


def _fmt(d) -> str:
    return json.dumps(d, indent=2, default=str, sort_keys=True)


def main() -> int:
    if not KRAUSS_FILE.exists():
        print(f"FATAL: {KRAUSS_FILE} not found", file=sys.stderr)
        return 1

    result = parse_pay_app(KRAUSS_FILE, job_id="krauss")
    pay_app = result["pay_app"]
    line_items = result["line_items"]
    skipped = result.get("skipped_rows", [])

    pay_app_view = {k: v for k, v in pay_app.items() if k != "raw_g702_json"}
    pay_app_view["raw_g702_json_cell_count"] = len(pay_app.get("raw_g702_json") or {})

    print("=" * 72)
    print("PAY APP HEADER")
    print("=" * 72)
    print(_fmt(pay_app_view))

    print()
    print("=" * 72)
    print(f"LINE ITEMS -- {len(line_items)} returned (target: ~220)")
    print("=" * 72)

    print()
    print("First 3 line items:")
    print(_fmt(line_items[:3]))

    print()
    print("Last 3 line items:")
    print(_fmt(line_items[-3:]))

    print()
    print("=" * 72)
    print(f"SKIPPED ROWS -- {len(skipped)} total")
    print("=" * 72)
    for s in skipped:
        print(
            f"  row {s['row']:>4}  reason={s.get('reason')!r}  "
            f"line={s.get('line_number')!r}  desc={s.get('description')!r}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
