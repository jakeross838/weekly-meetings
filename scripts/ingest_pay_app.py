"""Pay app ingestor for the v2 rebuild.

Parses a single AIA G702/G703 workbook with parse_pay_app() and writes
the result into Supabase. Idempotent at the file level: a re-ingest of
the same file (matched by SHA-256 hash) is rejected.

supabase-py doesn't expose cross-table transactions, so a failed
line_items batch triggers a manual delete of the parent pay_apps row.
This keeps state consistent against client-side errors. Network partitions
between insert and rollback could still leave orphans; not handled.

No-op of v1's process.py code — this module replicates the minimal
connection helper rather than importing from a frozen pipeline.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "parsers"))

from pay_app_parser import parse_pay_app  # noqa: E402

load_dotenv()

_CLIENT = None


def _supabase():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "(loaded from .env or process environment)."
        )
    from supabase import create_client
    _CLIENT = create_client(url, key)
    return _CLIENT


def _iso_date(v: Any) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _pay_app_payload(pa: dict) -> dict:
    return {
        "job_id":                 pa["job_id"],
        "pay_app_number":         pa["pay_app_number"],
        "application_date":       _iso_date(pa.get("application_date")),
        "contract_amount":        pa.get("contract_amount"),
        "total_completed_stored": pa.get("total_completed_stored"),
        "retainage":              pa.get("retainage"),
        "current_payment_due":    pa.get("current_payment_due"),
        "source_file_name":       pa.get("source_file_name"),
        "source_file_hash":       pa.get("source_file_hash"),
        "raw_g702_json":          pa.get("raw_g702_json"),
    }


def _line_item_payload(li: dict, pay_app_id: str, job_id: str) -> dict:
    return {
        "pay_app_id":                 pay_app_id,
        "job_id":                     job_id,
        "line_number":                li["line_number"],
        "description":                li.get("description"),
        "division":                   li.get("division"),
        "scheduled_value":            li.get("scheduled_value"),
        "work_completed_previous":    li.get("work_completed_previous"),
        "work_completed_this_period": li.get("work_completed_this_period"),
        "materials_stored":           li.get("materials_stored"),
        "total_completed":            li.get("total_completed"),
        "pct_complete":               li.get("pct_complete"),
        "balance_to_finish":          li.get("balance_to_finish"),
        "retainage":                  li.get("retainage"),
        "raw_row_index":              li.get("raw_row_index"),
    }


def ingest_pay_app(file_path: Path | str, job_id: str, dry_run: bool = False) -> dict:
    """Parse and insert a single pay app file into Supabase.

    Idempotent on source_file_hash.

    Return shape:
        {"status": "ingested",  "pay_app_id": uuid, "line_items_inserted": int, "skipped_rows": int}
        {"status": "skipped",   "reason": "already ingested", "existing_pay_app_id": uuid}
        {"status": "dry_run",   "would_insert_pay_app": dict, "would_insert_line_items": int, "skipped_rows": int}
    Raises on parser exception, missing env, or DB error after rollback.
    """
    file_path = Path(file_path)

    parsed = parse_pay_app(file_path, job_id)
    pa = parsed["pay_app"]
    line_items = parsed["line_items"]
    skipped_rows = parsed.get("skipped_rows", [])

    if pa.get("pay_app_number") is None:
        raise RuntimeError(
            f"{file_path.name}: could not parse pay_app_number from G702 header; cannot ingest."
        )

    for li in line_items:
        sv = li.get("scheduled_value")
        if sv is not None and (sv < 0 or sv > 1e9):
            print(
                f"  WARN: {file_path.name} line {li['line_number']!r} has unusual scheduled_value={sv!r}",
                file=sys.stderr,
            )

    if dry_run:
        return {
            "status": "dry_run",
            "would_insert_pay_app": {k: v for k, v in pa.items() if k != "raw_g702_json"},
            "would_insert_line_items": len(line_items),
            "skipped_rows": len(skipped_rows),
        }

    client = _supabase()

    existing = (
        client.table("pay_apps")
        .select("id")
        .eq("source_file_hash", pa["source_file_hash"])
        .execute()
    )
    if existing.data:
        return {
            "status": "skipped",
            "reason": "already ingested",
            "existing_pay_app_id": existing.data[0]["id"],
        }

    pa_resp = client.table("pay_apps").insert(_pay_app_payload(pa)).execute()
    if not pa_resp.data:
        raise RuntimeError(f"pay_apps insert returned no rows: {pa_resp}")
    pay_app_id = pa_resp.data[0]["id"]

    try:
        inserted = 0
        if line_items:
            payloads = [_line_item_payload(li, pay_app_id, job_id) for li in line_items]
            # Chunk the insert to stay well under Supabase request size limits.
            for i in range(0, len(payloads), 500):
                batch = payloads[i : i + 500]
                resp = client.table("pay_app_line_items").insert(batch).execute()
                inserted += len(resp.data or batch)
    except Exception as e:
        try:
            client.table("pay_apps").delete().eq("id", pay_app_id).execute()
        except Exception as cleanup_err:
            print(
                f"  CRITICAL: rollback failed for pay_app_id={pay_app_id}: {cleanup_err!r}",
                file=sys.stderr,
            )
        raise RuntimeError(f"line_items insert failed for {file_path.name}: {e!r}") from e

    return {
        "status": "ingested",
        "pay_app_id": pay_app_id,
        "line_items_inserted": inserted,
        "skipped_rows": len(skipped_rows),
    }
