"""Decision 12 — Auditor retry loop, capped at 1 retry.

Public function:
    audit_and_retry(meeting_id) -> dict

Flow:
1. Run audit_meeting()
2. If clean → done
3. If needs_retry → DELETE this meeting's outputs, re-run Reconciler with
   audit issues passed as `prior_attempt_issues`, then re-audit
4. If still not clean OR severity == "needs_review" from the start → stop,
   leave items marked with audit_state.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from auditor import audit_meeting  # noqa: E402
from reconciler import reconcile_meeting  # noqa: E402


def _supabase():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def _delete_meeting_outputs(client, meeting_id: str) -> dict:
    """Delete items, decisions, open_questions whose source_meeting_id matches."""
    n_items = len(client.table("items").delete().eq("source_meeting_id", meeting_id).execute().data or [])
    n_dec = len(client.table("decisions").delete().eq("source_meeting_id", meeting_id).execute().data or [])
    n_q = len(client.table("open_questions").delete().eq("source_meeting_id", meeting_id).execute().data or [])
    return {"items": n_items, "decisions": n_dec, "questions": n_q}


def audit_and_retry(meeting_id: str) -> dict:
    started = time.monotonic()
    client = _supabase()

    audit1 = audit_meeting(meeting_id, dry_run=False)
    total_cost = audit1["cost_usd"]

    if audit1["severity"] == "clean":
        return {
            "meeting_id":     meeting_id,
            "final_severity": "clean",
            "retried":        False,
            "audit_initial":  audit1,
            "audit_final":    audit1,
            "total_cost_usd": round(total_cost, 4),
            "elapsed_ms":     int((time.monotonic() - started) * 1000),
        }

    if audit1["severity"] == "needs_review":
        # Hard issues — don't retry
        return {
            "meeting_id":     meeting_id,
            "final_severity": "needs_review",
            "retried":        False,
            "audit_initial":  audit1,
            "audit_final":    audit1,
            "total_cost_usd": round(total_cost, 4),
            "elapsed_ms":     int((time.monotonic() - started) * 1000),
        }

    # severity == "needs_retry" — wipe outputs, re-run Reconciler with audit context
    deleted = _delete_meeting_outputs(client, meeting_id)

    all_issues = audit1["mechanical_issues"] + audit1["llm_issues"]
    reconcile2 = reconcile_meeting(meeting_id, dry_run=False, prior_attempt_issues=all_issues)
    total_cost += reconcile2.get("cost_usd", 0)

    audit2 = audit_meeting(meeting_id, dry_run=False)
    total_cost += audit2["cost_usd"]

    # If still not clean after retry, force severity = "needs_review"
    final_severity = audit2["severity"]
    if final_severity != "clean":
        final_severity = "needs_review"

    return {
        "meeting_id":          meeting_id,
        "final_severity":      final_severity,
        "retried":             True,
        "deleted_on_retry":    deleted,
        "audit_initial":       audit1,
        "reconcile_retry":     {k: v for k, v in reconcile2.items() if k not in ("needs_review", "claims_dropped")},
        "audit_final":         audit2,
        "total_cost_usd":      round(total_cost, 4),
        "elapsed_ms":          int((time.monotonic() - started) * 1000),
    }
