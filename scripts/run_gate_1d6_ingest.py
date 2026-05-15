"""Gate 1D.6 runner: ingest all 5 extractor JSON files into Supabase.

Mirrors the (json, transcript) pairs from scripts/test_extractor.py. Calls
ingest_meeting() for each and prints a summary table.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ingest_extractor_output import ingest_meeting  # noqa: E402


OUTPUT_DIR = Path("/tmp/extractor-out-v2")

PAIRS: list[tuple[str, str]] = [
    (
        "05-07_Krauss_Ruthven_Office_Production_Meeting-transcript.json",
        r"C:/Users/Jake/Downloads/05-07 Krauss_Ruthven Office Production Meeting-transcript.txt",
    ),
    (
        "2026-04-30_Krauss_Site_Production_Meeting-transcript.json",
        r"P:/Claude Projects/weekly-meetings/transcripts/processed/2026-04-30 Krauss Site Production Meeting-transcript.txt",
    ),
    (
        "2026-04-30_Dewberry_Site_Production_Meeting-transcript.json",
        r"P:/Claude Projects/weekly-meetings/transcripts/processed/2026-04-30 Dewberry Site Production Meeting-transcript.txt",
    ),
    (
        "04-30_Pou_Site_Production_Meeting-transcript.json",
        r"P:/Claude Projects/weekly-meetings/transcripts/processed/04-30 Pou Site Production Meeting-transcript.txt",
    ),
    (
        "2026-04-30_Ruthven_Site_Production_Meeting-transcript.json",
        r"P:/Claude Projects/weekly-meetings/transcripts/processed/2026-04-30 Ruthven Site Production Meeting-transcript.txt",
    ),
]


def main() -> int:
    rows: list[tuple] = []
    for json_name, transcript_path in PAIRS:
        json_path = OUTPUT_DIR / json_name
        if not json_path.exists():
            print(f"MISSING JSON: {json_path}", file=sys.stderr)
            rows.append((json_name, "?", "missing_json", "-", "-", "-"))
            continue
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            job = data["meeting_metadata"]["job_id"]
            print(f"[{job}] ingesting {json_name} ...")
            result = ingest_meeting(json_path, transcript_path=transcript_path)
            print(f"  -> {result}")
            mid = result.get("meeting_id") or "?"
            short = mid[:8] if isinstance(mid, str) else "?"
            rows.append(
                (
                    json_name,
                    job,
                    result["status"],
                    short,
                    result.get("claims_inserted", "-"),
                    result.get("claims_skipped_invalid_type", "-"),
                )
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            rows.append((json_name, "?", f"error", "-", "-", "-"))

    print()
    print("=" * 116)
    print(
        f"{'Meeting file':<58}  {'Job':<10} {'Status':<12} {'MtgID':>10}  {'Claims in':>10}  {'Skipped':>8}"
    )
    print("-" * 116)
    for jf, j, s, mid, ci, sk in rows:
        print(f"{jf:<58}  {j:<10} {s:<12} {str(mid):>10}  {str(ci):>10}  {str(sk):>8}")
    print("=" * 116)
    return 0


if __name__ == "__main__":
    sys.exit(main())
