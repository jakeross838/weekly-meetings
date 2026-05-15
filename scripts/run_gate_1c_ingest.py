"""Gate 1C runner: ingest pay apps for the 5 reachable jobs and print a summary."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ingest_pay_app import ingest_pay_app  # noqa: E402


FILES: list[tuple[str, str]] = [
    ("krauss",   r"C:/Users/Jake/Downloads/Krauss_pay_app_10_October_25.xlsx"),
    ("pou",      r"C:/Users/Jake/Downloads/Pou109_pay_app_11_November_2025.xlsx"),
    ("dewberry", r"C:/Users/Jake/nightwork-platform/test-invoices/Dewberry-681_KRD-Pay_App_10_March_26.xlsx"),
    ("fish",     r"C:/Users/Jake/nightwork-platform/test-invoices/Fish_Pay_App_21_March_26.xlsx"),
    ("drummond", r"C:/Users/Jake/Downloads/Drummond_Pay_App_2_20260415.xlsx"),
]


def main() -> int:
    rows = []
    for job_id, fpath in FILES:
        file_path = Path(fpath)
        if not file_path.exists():
            print(f"[{job_id}] MISSING FILE: {fpath}")
            rows.append((job_id, file_path.name, "missing_file", None, None))
            continue
        print(f"[{job_id}] ingesting {file_path.name} ...")
        try:
            result = ingest_pay_app(file_path, job_id)
            status = result["status"]
            li = result.get("line_items_inserted", "-")
            sk = result.get("skipped_rows", "-")
            print(f"  -> {result}")
            rows.append((job_id, file_path.name, status, li, sk))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            rows.append((job_id, file_path.name, f"error", None, None))

    print()
    print("=" * 112)
    print(f"{'Job':<10}  {'File':<55}  {'Status':<14}  {'Line items':>11}  {'Skipped':>8}")
    print("-" * 112)
    for j, f, s, li, sk in rows:
        li_s = "-" if li is None else str(li)
        sk_s = "-" if sk is None else str(sk)
        print(f"{j:<10}  {f:<55}  {s:<14}  {li_s:>11}  {sk_s:>8}")
    print("=" * 112)
    return 0


if __name__ == "__main__":
    sys.exit(main())
