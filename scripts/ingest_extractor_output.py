"""Ingest Extractor JSON output into Supabase meetings + claims.

Idempotent on meetings.source_file_hash (UNIQUE constraint). On re-ingestion
of a meeting, existing claims for that meeting_id are DELETEd before the
new claims are INSERTed — claims are disposable derived artifacts per the
Gate 1E decisions doc.

source_file_hash is computed from the TRANSCRIPT file bytes, not the JSON
output. Two different extractor runs against the same transcript produce
the same hash and re-ingest the meeting (refreshing claims + extracted_at).
A different transcript text would produce a new hash and a new meeting row.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VALID_CLAIM_TYPES = {
    "commitment",
    "decision",
    "condition_observed",
    "status_update",
    "complaint",
    "question",
}

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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest_meeting(
    json_path: Path | str,
    transcript_path: Path | str | None = None,
    dry_run: bool = False,
) -> dict:
    """Ingest one Extractor JSON file into meetings + claims.

    Args:
        json_path: path to the Extractor's JSON output (from test_extractor.py)
        transcript_path: path to the source transcript .txt file. Required —
            the JSON doesn't carry the original transcript path; the caller
            supplies it.
        dry_run: if True, no DB writes; returns what would happen.

    Returns:
        {"status": "ingested" | "re_ingested" | "dry_run",
         "meeting_id": uuid,
         "claims_inserted": int,
         "claims_deleted_first": int,
         "claims_skipped_invalid_type": int}

    Raises if transcript_path is None / missing, or if the meetings INSERT
    returns no data. Claims with invalid claim_type are logged and skipped,
    not raised.
    """
    json_path = Path(json_path)
    if transcript_path is None:
        raise RuntimeError(
            f"transcript_path is required (json={json_path.name}); "
            "the JSON does not embed the source path."
        )
    transcript_path = Path(transcript_path)
    if not transcript_path.exists():
        raise FileNotFoundError(f"transcript not found: {transcript_path}")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    meta = data["meeting_metadata"]
    claims_in = data.get("claims", [])

    source_file_hash = _sha256_file(transcript_path)
    raw_transcript_text = transcript_path.read_text(encoding="utf-8", errors="replace")

    # Validate claim_type against the CHECK constraint enum before any DB write.
    skipped_invalid: list[dict] = []
    valid_claims: list[dict] = []
    for c in claims_in:
        ct = c.get("claim_type")
        if ct not in VALID_CLAIM_TYPES:
            skipped_invalid.append({"claim": c, "reason": f"invalid claim_type {ct!r}"})
            print(
                f"  WARN: {json_path.name} skipping claim with invalid type {ct!r}: "
                f"{(c.get('statement') or '')[:80]!r}",
                file=sys.stderr,
            )
            continue
        valid_claims.append(c)

    if dry_run:
        return {
            "status": "dry_run",
            "source_file_hash": source_file_hash,
            "transcript_chars": len(raw_transcript_text),
            "would_insert_claims": len(valid_claims),
            "claims_skipped_invalid_type": len(skipped_invalid),
        }

    client = _supabase()

    existing = (
        client.table("meetings")
        .select("id")
        .eq("source_file_hash", source_file_hash)
        .execute()
    )

    claims_deleted = 0
    re_ingest = bool(existing.data)

    if re_ingest:
        meeting_id = existing.data[0]["id"]
        del_resp = (
            client.table("claims")
            .delete()
            .eq("meeting_id", meeting_id)
            .execute()
        )
        claims_deleted = len(del_resp.data or [])
    else:
        m_payload = {
            "job_id":               meta["job_id"],
            "pm_id":                meta.get("pm_id"),
            "meeting_date":         meta["meeting_date"],
            "meeting_type":         meta["meeting_type"],
            "attendees":            meta.get("attendees"),
            "transcript_file_path": str(transcript_path),
            "raw_transcript_text":  raw_transcript_text,
            "source_file_hash":     source_file_hash,
            "extracted_at":         _now_iso(),
        }
        m_resp = client.table("meetings").insert(m_payload).execute()
        if not m_resp.data:
            raise RuntimeError(f"meetings insert returned no rows: {m_resp}")
        meeting_id = m_resp.data[0]["id"]

    inserted = 0
    if valid_claims:
        rows = [
            {
                "meeting_id":             meeting_id,
                "speaker":                c.get("speaker"),
                "claim_type":             c["claim_type"],
                "subject":                c.get("subject"),
                "statement":              c["statement"],
                "raw_quote":              c.get("raw_quote"),
                "position_in_transcript": c.get("position_in_transcript"),
            }
            for c in valid_claims
        ]
        for i in range(0, len(rows), 500):
            batch = rows[i : i + 500]
            resp = client.table("claims").insert(batch).execute()
            inserted += len(resp.data or batch)

    client.table("meetings").update({"extracted_at": _now_iso()}).eq("id", meeting_id).execute()

    return {
        "status":                       "re_ingested" if re_ingest else "ingested",
        "meeting_id":                   meeting_id,
        "claims_inserted":              inserted,
        "claims_deleted_first":         claims_deleted,
        "claims_skipped_invalid_type":  len(skipped_invalid),
    }
