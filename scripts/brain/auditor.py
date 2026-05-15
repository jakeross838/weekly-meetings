"""Call 3 of the v2 brain: Auditor.

Reviews the Reconciler's output for one meeting and flags issues.
6 mechanical checks (SQL/structural) + 1 LLM-based sanity check.

Public function:
    audit_meeting(meeting_id, dry_run=False) -> dict

Severity rules:
- "clean"        — zero issues
- "needs_retry"  — issues the Reconciler can plausibly fix on retry
                   (wrong type, wrong priority, missing context)
- "needs_review" — issues that need a human (schema violations, hard
                   contradictions, repeat-after-retry)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


MODEL_OPUS = "claude-opus-4-7"
OPUS_PRICE_IN = 5.00 / 1_000_000
OPUS_PRICE_OUT = 25.00 / 1_000_000
OPUS_PRICE_CACHE_READ = 0.50 / 1_000_000
OPUS_PRICE_CACHE_CREATE = 6.25 / 1_000_000

VALID_ITEM_TYPES = {"action", "observation", "flag"}
VALID_CONFIDENCE = {"high", "medium", "low"}

# Decision 2 mapping (Extractor claim_type -> allowed item.type for Reconciler):
# claim_type -> set of acceptable items.type values
# (Decisions go to decisions table, questions go to open_questions; not in this map.)
TYPE_MAP_ALLOWED = {
    "commitment":         {"action"},
    "condition_observed": {"observation", "flag"},
    "status_update":      {"observation", "action"},
    "complaint":          {"flag", "observation"},
}


_SUPA = None
_ANTH = None


def _supabase():
    global _SUPA
    if _SUPA is not None:
        return _SUPA
    from supabase import create_client
    _SUPA = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    return _SUPA


def _anthropic():
    global _ANTH
    if _ANTH is not None:
        return _ANTH
    import anthropic
    _ANTH = anthropic.Anthropic()
    return _ANTH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- INPUT LOADING ----------

def _load_meeting(meeting_id: str) -> dict:
    r = _supabase().table("meetings").select("*").eq("id", meeting_id).execute()
    if not r.data:
        raise RuntimeError(f"meeting {meeting_id} not found")
    return r.data[0]


def _load_claims(meeting_id: str) -> list[dict]:
    r = _supabase().table("claims").select("*").eq("meeting_id", meeting_id).execute()
    return r.data or []


def _load_items(meeting_id: str) -> list[dict]:
    r = _supabase().table("items").select("*").eq("source_meeting_id", meeting_id).execute()
    return r.data or []


def _load_decisions(meeting_id: str) -> list[dict]:
    r = _supabase().table("decisions").select("*").eq("source_meeting_id", meeting_id).execute()
    return r.data or []


def _load_questions(meeting_id: str) -> list[dict]:
    r = _supabase().table("open_questions").select("*").eq("source_meeting_id", meeting_id).execute()
    return r.data or []


def _load_sub_ids() -> set[str]:
    r = _supabase().table("subs").select("id").execute()
    return {row["id"] for row in (r.data or [])}


def _load_line_items(job_ids: list[str]) -> dict[str, dict]:
    """Map line_item_id -> {id, job_id}."""
    if not job_ids:
        return {}
    r = _supabase().table("pay_app_line_items").select("id, job_id").in_("job_id", job_ids).execute()
    return {row["id"]: row for row in (r.data or [])}


# ---------- MECHANICAL CHECKS ----------

def _check_claims_accountability(claims, items, decisions, questions, meeting) -> list[dict]:
    """Heuristic count check — exact claim-by-claim tracking would require
    source_claim_id on items (not currently populated for the legacy run).
    For the Auditor's purpose, gross under-coverage gets flagged."""
    n_claims = len(claims)
    n_items = len(items)
    n_dec = len(decisions)
    n_q = len(questions)
    total_outputs = n_items + n_dec + n_q

    issues = []
    if n_claims == 0:
        return issues

    coverage_ratio = total_outputs / n_claims
    if coverage_ratio < 0.70:
        issues.append({
            "check": "claims_accountability",
            "severity": "needs_retry",
            "detail": (
                f"Output count ({total_outputs}: {n_items} items + {n_dec} decisions + {n_q} questions) "
                f"is only {coverage_ratio:.0%} of claims ({n_claims}) — possible under-coverage. "
                "Heuristic; exact tracking requires items.source_claim_id."
            ),
        })
    return issues


def _check_sub_resolves(items, sub_ids) -> list[dict]:
    issues = []
    for it in items:
        sid = it.get("sub_id")
        if sid is None:
            continue
        if sid not in sub_ids:
            issues.append({
                "check":    "sub_resolves",
                "severity": "needs_review",
                "item_id":  it["id"],
                "human_id": it.get("human_readable_id"),
                "detail":   f"sub_id {sid!r} not in subs table",
            })
    return issues


def _check_line_resolves(items, line_index: dict[str, dict]) -> list[dict]:
    issues = []
    for it in items:
        lid = it.get("pay_app_line_item_id")
        if lid is None:
            continue
        line = line_index.get(lid)
        if line is None:
            issues.append({
                "check":    "line_resolves",
                "severity": "needs_review",
                "item_id":  it["id"],
                "human_id": it.get("human_readable_id"),
                "detail":   f"pay_app_line_item_id {lid!r} not in pay_app_line_items",
            })
            continue
        if line["job_id"] != it["job_id"]:
            issues.append({
                "check":    "line_job_mismatch",
                "severity": "needs_review",
                "item_id":  it["id"],
                "human_id": it.get("human_readable_id"),
                "detail":   f"item.job_id={it['job_id']!r} but line.job_id={line['job_id']!r}",
            })
    return issues


def _check_item_types(items) -> list[dict]:
    issues = []
    for it in items:
        if it["type"] not in VALID_ITEM_TYPES:
            issues.append({
                "check":    "invalid_item_type",
                "severity": "needs_review",
                "item_id":  it["id"],
                "human_id": it.get("human_readable_id"),
                "detail":   f"type {it['type']!r} not in {sorted(VALID_ITEM_TYPES)}",
            })
    return issues


def _check_confidence(items) -> list[dict]:
    """Decision 4 cold-start: no item should be 'high' until cross-source
    data (daily_logs) exists. daily_logs table not yet built (Week 3)."""
    issues = []
    for it in items:
        if it["confidence"] not in VALID_CONFIDENCE:
            issues.append({
                "check":    "invalid_confidence",
                "severity": "needs_review",
                "item_id":  it["id"],
                "human_id": it.get("human_readable_id"),
                "detail":   f"confidence {it['confidence']!r} not in {sorted(VALID_CONFIDENCE)}",
            })
            continue
        if it["confidence"] == "high":
            issues.append({
                "check":    "premature_high_confidence",
                "severity": "needs_retry",
                "item_id":  it["id"],
                "human_id": it.get("human_readable_id"),
                "detail":   "Cold start (no daily_logs yet) — confidence=high requires 2+ sources per Decision 4",
            })
    return issues


def _check_intra_meeting_dups(items) -> list[dict]:
    """No two items within the meeting's output share
    (job_id, sub_id, pay_app_line_item_id) AND status='open'."""
    issues = []
    seen: dict[tuple, dict] = {}
    for it in items:
        if it["status"] != "open":
            continue
        sid = it.get("sub_id")
        lid = it.get("pay_app_line_item_id")
        # Skip the dedup check when both are null (too loose to be meaningful)
        if sid is None and lid is None:
            continue
        key = (it["job_id"], sid, lid)
        if key in seen:
            other = seen[key]
            issues.append({
                "check":    "intra_meeting_dup",
                "severity": "needs_retry",
                "item_ids": [other["id"], it["id"]],
                "human_ids":[other.get("human_readable_id"), it.get("human_readable_id")],
                "detail":   f"Duplicate on (job_id={key[0]!r}, sub_id={key[1]!r}, line_id={key[2]!r})",
            })
        else:
            seen[key] = it
    return issues


# ---------- LLM AUDIT (Check 7) ----------

AUDITOR_SYSTEM_PROMPT = """You audit the Reconciler's output for a single Ross Built production meeting. You compare the original *claims* (extracted from the transcript) against the *items, decisions, and open_questions* the Reconciler produced, and flag anything that looks wrong.

What to look for (in priority order):

1. **Wrong type assignment.** A commitment got routed to observation. A decision got routed to action. A status_update got marked as a flag when it wasn't a complaint. Use Decision 2's mapping as the rule.

2. **Inappropriate priority='urgent'.** Decision 3 says urgent fires if: explicit urgency keywords ("urgent", "ASAP", "today", "tomorrow", "blocking", "immediately"), OR target_date within 7 days, OR pay-app line >90% complete. PAST-TENSE status updates ("confirmed", "scheduled", "done") that have no urgency keywords should generally be 'normal'. Watch for keyword false positives where "today"/"now" appears casually (e.g. "we did that today").

3. **Inappropriate confidence.** Cold start (no daily_logs) means no item should be 'high'. 'Low' for clear claims with named subs is too pessimistic. 'Medium' for genuinely vague claims (no actor, no specifics) is too optimistic.

4. **Missing context** in the title or detail that a PM would need. E.g. title says "Coordinate vendor" without saying which vendor or which item.

5. **Contradictions across the same meeting.** Two items that contradict each other ("sub will start Monday" + "sub already finished") — should be one item with the latter taking precedence, or a needs_review flag.

6. **Wrong owner / sub linkage.** Item credits "DB Welding" the work but lists `sub_id` for a different sub.

For each issue, give:
- `item_id`: the item's uuid (or "decision:UUID" / "question:UUID" for those tables)
- `human_id`: the human_readable_id if available
- `issue_type`: short tag (one of: wrong_type, bad_priority, bad_confidence, missing_context, contradiction, wrong_sub, other)
- `severity`: "needs_retry" if a re-run of the Reconciler could plausibly fix it (e.g. wrong priority, wrong type); "needs_review" if it requires human judgment (contradictions, ambiguous claims, data inconsistencies that can't be resolved from the transcript alone)
- `detail`: 1-2 sentences explaining

If you see nothing wrong, return an empty issues list. **Be conservative — flag only real problems, not stylistic preferences.** A title you'd phrase slightly differently is NOT an issue.

Return strict JSON matching the schema."""


AUDITOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id":    {"type": "string"},
                    "human_id":   {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "issue_type": {"type": "string", "enum": [
                        "wrong_type", "bad_priority", "bad_confidence",
                        "missing_context", "contradiction", "wrong_sub", "other",
                    ]},
                    "severity":   {"type": "string", "enum": ["needs_retry", "needs_review"]},
                    "detail":     {"type": "string"},
                },
                "required": ["item_id", "human_id", "issue_type", "severity", "detail"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["issues"],
    "additionalProperties": False,
}


def _llm_audit(meeting, claims, items, decisions, questions, cost_tracker) -> list[dict]:
    """One Opus call. Returns the issues list and updates cost_tracker."""
    # Compact payload
    claims_compact = [
        {
            "claim_id":   c["id"],
            "claim_type": c["claim_type"],
            "speaker":    c.get("speaker"),
            "subject":    c.get("subject"),
            "statement":  c.get("statement"),
            "raw_quote":  (c.get("raw_quote") or "")[:200],
            "position":   c.get("position_in_transcript"),
        }
        for c in claims
    ]
    items_compact = [
        {
            "item_id":              it["id"],
            "human_id":             it.get("human_readable_id"),
            "type":                 it["type"],
            "title":                it["title"],
            "detail":               it.get("detail"),
            "sub_id":               it.get("sub_id"),
            "pay_app_line_item_id": it.get("pay_app_line_item_id"),
            "target_date":          str(it.get("target_date")) if it.get("target_date") else None,
            "target_date_text":     it.get("target_date_text"),
            "priority":             it["priority"],
            "confidence":           it["confidence"],
            "owner":                it.get("owner"),
        }
        for it in items
    ]
    decisions_compact = [
        {
            "decision_id":  d["id"],
            "human_id":     d.get("human_readable_id"),
            "description":  d["description"],
        }
        for d in decisions
    ]
    questions_compact = [
        {
            "question_id":  q["id"],
            "human_id":     q.get("human_readable_id"),
            "question":     q["question"],
        }
        for q in questions
    ]

    user_msg = (
        f"MEETING:\n"
        f"  id: {meeting['id']}\n"
        f"  date: {meeting['meeting_date']}\n"
        f"  type: {meeting['meeting_type']}\n"
        f"  primary_job_id: {meeting['job_id']}\n\n"
        f"CLAIMS ({len(claims_compact)} total):\n"
        f"{json.dumps(claims_compact, indent=2, default=str)}\n\n"
        f"ITEMS ({len(items_compact)} total):\n"
        f"{json.dumps(items_compact, indent=2, default=str)}\n\n"
        f"DECISIONS ({len(decisions_compact)} total):\n"
        f"{json.dumps(decisions_compact, indent=2, default=str)}\n\n"
        f"OPEN_QUESTIONS ({len(questions_compact)} total):\n"
        f"{json.dumps(questions_compact, indent=2, default=str)}\n\n"
        "Audit per the rules in the system prompt. Return strict JSON."
    )

    client = _anthropic()
    started = time.monotonic()
    with client.messages.stream(
        model=MODEL_OPUS,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": AUDITOR_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": AUDITOR_OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        final = stream.get_final_message()
    elapsed_ms = int((time.monotonic() - started) * 1000)

    text_block = next((b for b in final.content if b.type == "text"), None)
    if text_block is None:
        raise RuntimeError(f"Auditor returned no text (stop_reason={final.stop_reason})")
    payload = json.loads(text_block.text)
    issues = payload.get("issues", []) or []

    usage = final.usage
    cost_tracker["opus_in"] += getattr(usage, "input_tokens", 0)
    cost_tracker["opus_out"] += getattr(usage, "output_tokens", 0)
    cost_tracker["opus_cache_read"] += (getattr(usage, "cache_read_input_tokens", 0) or 0)
    cost_tracker["opus_cache_create"] += (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cost_tracker["opus_elapsed_ms"] += elapsed_ms

    return issues


# ---------- SEVERITY CLASSIFICATION ----------

def _classify_severity(mechanical_issues: list, llm_issues: list) -> str:
    if not mechanical_issues and not llm_issues:
        return "clean"
    all_issues = mechanical_issues + llm_issues
    if any(i.get("severity") == "needs_review" for i in all_issues):
        return "needs_review"
    return "needs_retry"


# ---------- PUBLIC ENTRYPOINT ----------

def audit_meeting(meeting_id: str, dry_run: bool = False) -> dict:
    """Run the 6 mechanical + 1 LLM audit checks for one meeting."""
    started = time.monotonic()
    cost_tracker = {
        "opus_in": 0, "opus_out": 0,
        "opus_cache_read": 0, "opus_cache_create": 0,
        "opus_elapsed_ms": 0,
    }

    meeting = _load_meeting(meeting_id)
    claims = _load_claims(meeting_id)
    items = _load_items(meeting_id)
    decisions = _load_decisions(meeting_id)
    questions = _load_questions(meeting_id)

    sub_ids = _load_sub_ids()
    job_ids_in_items = list({it["job_id"] for it in items})
    line_index = _load_line_items(job_ids_in_items)

    # Mechanical checks
    mechanical: list[dict] = []
    mechanical += _check_claims_accountability(claims, items, decisions, questions, meeting)
    mechanical += _check_sub_resolves(items, sub_ids)
    mechanical += _check_line_resolves(items, line_index)
    mechanical += _check_item_types(items)
    mechanical += _check_confidence(items)
    mechanical += _check_intra_meeting_dups(items)

    llm_issues: list[dict] = []
    if not dry_run:
        llm_issues = _llm_audit(meeting, claims, items, decisions, questions, cost_tracker)

    severity = _classify_severity(mechanical, llm_issues)

    cost_usd = (
        cost_tracker["opus_in"] * OPUS_PRICE_IN
        + cost_tracker["opus_out"] * OPUS_PRICE_OUT
        + cost_tracker["opus_cache_read"] * OPUS_PRICE_CACHE_READ
        + cost_tracker["opus_cache_create"] * OPUS_PRICE_CACHE_CREATE
    )

    # Persist audit_state on items if not dry_run
    if not dry_run:
        # Build a map item_id -> list of issues
        per_item_issues: dict[str, list[dict]] = {}
        for issue in llm_issues:
            iid = issue.get("item_id")
            if iid:
                per_item_issues.setdefault(iid, []).append(issue)
        for issue in mechanical:
            iid = issue.get("item_id")
            if iid:
                per_item_issues.setdefault(iid, []).append(issue)

        client = _supabase()
        for it in items:
            iid = it["id"]
            issues_for_item = per_item_issues.get(iid, [])
            if issues_for_item:
                # Audit state per item — take the most severe
                item_severity = "needs_review" if any(i.get("severity") == "needs_review" for i in issues_for_item) else "needs_retry"
            else:
                item_severity = "clean"
            client.table("items").update({
                "audit_state":  item_severity,
                "audit_issues": issues_for_item,
            }).eq("id", iid).execute()

    return {
        "meeting_id":         meeting_id,
        "audit_passed":       severity == "clean",
        "severity":           severity,
        "mechanical_issues":  mechanical,
        "llm_issues":         llm_issues,
        "elapsed_ms":         int((time.monotonic() - started) * 1000),
        "cost_usd":           round(cost_usd, 4),
        "counts": {
            "claims":    len(claims),
            "items":     len(items),
            "decisions": len(decisions),
            "questions": len(questions),
        },
    }
