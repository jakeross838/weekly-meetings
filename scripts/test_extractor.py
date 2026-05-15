"""Gate 1D test runner: extract claims from 5 real transcripts.

NO Supabase writes. Saves per-file JSON to /tmp/extractor-out/ (Windows: that
maps to <current-drive>:\\tmp\\extractor-out\\). Prints per-transcript and
aggregate summaries, plus a sample of 5-6 claims.

Stops early if total estimated spend exceeds the $5 cap.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "brain"))

from extractor import extract_claims  # noqa: E402


OUTPUT_DIR = Path("/tmp/extractor-out-v2")
SPEND_CAP_USD = 5.00

# Opus 4.7 pricing per 1M tokens: $5 input, $25 output.
# Cache read ≈ 0.1× input = $0.50/MTok. Cache create ≈ 1.25× input = $6.25/MTok.
PRICE_INPUT = 5.00 / 1_000_000
PRICE_OUTPUT = 25.00 / 1_000_000
PRICE_CACHE_READ = 0.50 / 1_000_000
PRICE_CACHE_CREATE = 6.25 / 1_000_000


TRANSCRIPTS = [
    {
        "path": r"C:/Users/Jake/Downloads/05-07 Krauss_Ruthven Office Production Meeting-transcript.txt",
        "job_id": "krauss",
        "pm_id": "lee",
        "meeting_date": "2026-05-07",
        "meeting_type": "office",
        "notes": "Office meeting covering BOTH Krauss and Ruthven jobs. job_id is set to krauss but the transcript discusses both — important edge case for the Reconciler later.",
    },
    {
        "path": r"P:/Claude Projects/weekly-meetings/transcripts/processed/2026-04-30 Krauss Site Production Meeting-transcript.txt",
        "job_id": "krauss",
        "pm_id": "lee",
        "meeting_date": "2026-04-30",
        "meeting_type": "site",
    },
    {
        "path": r"P:/Claude Projects/weekly-meetings/transcripts/processed/2026-04-30 Dewberry Site Production Meeting-transcript.txt",
        "job_id": "dewberry",
        "pm_id": "jason",
        "meeting_date": "2026-04-30",
        "meeting_type": "site",
    },
    {
        "path": r"P:/Claude Projects/weekly-meetings/transcripts/processed/04-30 Pou Site Production Meeting-transcript.txt",
        "job_id": "pou",
        "pm_id": "jason",
        "meeting_date": "2026-04-30",
        "meeting_type": "site",
    },
    {
        "path": r"P:/Claude Projects/weekly-meetings/transcripts/processed/2026-04-30 Ruthven Site Production Meeting-transcript.txt",
        "job_id": "ruthven",
        "pm_id": "lee",
        "meeting_date": "2026-04-30",
        "meeting_type": "site",
    },
]


def _cost(m: dict) -> float:
    return (
        m["input_tokens"] * PRICE_INPUT
        + m["output_tokens"] * PRICE_OUTPUT
        + m["cache_read_input_tokens"] * PRICE_CACHE_READ
        + m["cache_creation_input_tokens"] * PRICE_CACHE_CREATE
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    overall: list[dict] = []
    running_cost = 0.0

    for spec in TRANSCRIPTS:
        path = Path(spec["path"])
        if not path.exists():
            print(f"MISSING: {path}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta = {k: v for k, v in spec.items() if k != "path"}

        print(f"[{spec['job_id']} {spec['meeting_date']} {spec['meeting_type']}]")
        print(f"  extracting from {path.name}  ({len(text):,} chars)")

        try:
            result = extract_claims(text, meta)
        except Exception as e:
            print(f"  ERROR: {e!r}", file=sys.stderr)
            continue

        claims = result["claims"]
        m = result["metadata"]
        per_type: dict[str, int] = {}
        for c in claims:
            t = c.get("claim_type", "?")
            per_type[t] = per_type.get(t, 0) + 1

        call_cost = _cost(m)
        running_cost += call_cost

        print(f"  -> {len(claims)} claims | by type: {per_type}")
        print(
            f"     tokens: in={m['input_tokens']:,} out={m['output_tokens']:,} "
            f"cache_read={m['cache_read_input_tokens']:,} cache_create={m['cache_creation_input_tokens']:,} "
            f"elapsed_ms={m['elapsed_ms']:,}"
        )
        print(f"     est cost this call: ${call_cost:.4f} | running total: ${running_cost:.4f}")

        outname = path.stem.replace(" ", "_") + ".json"
        outpath = OUTPUT_DIR / outname
        outpath.write_text(
            json.dumps({"meeting_metadata": meta, **result}, indent=2),
            encoding="utf-8",
        )
        print(f"     saved -> {outpath}")
        print()

        overall.append({"job_id": spec["job_id"], "claims": claims, "metadata": m})

        if running_cost > SPEND_CAP_USD:
            print(f"!! SPEND CAP HIT (${running_cost:.2f} > ${SPEND_CAP_USD:.2f}). Stopping early.", file=sys.stderr)
            return 2

    if not overall:
        print("No extractions completed.", file=sys.stderr)
        return 1

    total_claims = sum(len(o["claims"]) for o in overall)
    aggregate_per_type: dict[str, int] = {}
    for o in overall:
        for c in o["claims"]:
            t = c.get("claim_type", "?")
            aggregate_per_type[t] = aggregate_per_type.get(t, 0) + 1

    total_input = sum(o["metadata"]["input_tokens"] for o in overall)
    total_output = sum(o["metadata"]["output_tokens"] for o in overall)
    total_cache_read = sum(o["metadata"]["cache_read_input_tokens"] for o in overall)
    total_cache_create = sum(o["metadata"]["cache_creation_input_tokens"] for o in overall)

    print("=" * 80)
    print("AGGREGATE")
    print("=" * 80)
    print(f"Meetings processed: {len(overall)}")
    print(f"Total claims:       {total_claims}")
    print(f"Avg claims/meeting: {total_claims / len(overall):.1f}")
    print(f"By type:            {aggregate_per_type}")
    print()
    print(f"Tokens — input: {total_input:,}, output: {total_output:,}")
    print(f"       — cache read: {total_cache_read:,}, cache create: {total_cache_create:,}")
    print(f"Estimated total cost: ${running_cost:.4f} (cap: ${SPEND_CAP_USD:.2f})")

    print()
    print("=" * 80)
    print("SAMPLE CLAIMS")
    print("=" * 80)
    seen_types: set[str] = set()
    pool = [(o["job_id"], c) for o in overall for c in o["claims"]]
    random.seed(42)
    random.shuffle(pool)
    samples = []
    for job_id, c in pool:
        t = c.get("claim_type")
        if t not in seen_types:
            seen_types.add(t)
            samples.append((job_id, c))
        if len(seen_types) >= 6:
            break
    for job_id, c in samples:
        print(f"  [{job_id}] [{c.get('claim_type')}]  speaker={c.get('speaker')!r}  subject={c.get('subject')!r}")
        print(f"      statement: {c.get('statement')!r}")
        raw = (c.get("raw_quote") or "")
        if len(raw) > 140:
            raw = raw[:140] + "..."
        print(f"      raw_quote: {raw!r}")
        print(f"      pos: {c.get('position_in_transcript')!r}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
