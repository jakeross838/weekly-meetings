"""Call 2 of the v2 brain: Reconciler.

Takes claims for one meeting (ingested by Gate 1D.6) and produces structured
items, decisions, and open_questions in Supabase, following the locked
design rules in docs/gate-1e-decisions.md.

Public function:
    reconcile_meeting(meeting_id: uuid, dry_run: bool = False) -> dict

Architecture (per the decisions doc):
- Python does deterministic work: load inputs, route each claim to a job
  (Decision 8), match sub via 3-stage cascade (Decision 6), match pay-app
  line item via 2-stage cascade (Decision 7), check urgency triggers
  (Decision 3), compute confidence (Decision 4).
- ONE Opus 4.7 call per meeting routes claims to items/decisions/questions
  per Decision 2, generates titles/details, extracts target_date
  (Decision 5), and decides create-vs-update for cross-meeting dedup
  (Decision 9).
- Haiku is used as a fallback classifier in sub-matching stage 3 and
  pay-app matching stage 2.
- Python applies clobber prevention (Decision 11) and generates
  human_readable_ids on insert (Decision 1).

NOT in this gate (per Decision 12): Auditor retry loop. Surfacing
"needs_review" but no second pass.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


MODEL_OPUS = "claude-opus-4-7"
MODEL_HAIKU = "claude-haiku-4-5"

OPUS_PRICE_IN = 5.00 / 1_000_000
OPUS_PRICE_OUT = 25.00 / 1_000_000
OPUS_PRICE_CACHE_READ = 0.50 / 1_000_000
OPUS_PRICE_CACHE_CREATE = 6.25 / 1_000_000
HAIKU_PRICE_IN = 1.00 / 1_000_000
HAIKU_PRICE_OUT = 5.00 / 1_000_000

URGENCY_TOKENS = [
    "urgent", "asap", "critical", "blocking",
    "now", "today", "tomorrow", "immediately",
]

JOB_PREFIXES: dict[str, str] = {
    "drummond": "DRUM",
    "molinari": "MOLI",
    "biales":   "BIAL",
    "pou":      "POU",
    "dewberry": "DEWB",
    "harllee":  "HARL",
    "krauss":   "KRAU",
    "ruthven":  "RUTH",
    "fish":     "FISH",
    "markgraf": "MARK",
    "clark":    "CLAR",
    "johnson":  "JOHN",
}

STOP_WORDS = set("""
the a an and or but in on at to from with for of is are was were be been being have has
had do does did this that these those it its their our we i you he she they them us
will would can could should may might must shall as by into onto over under up down out
about so if when where why how what which who whom whose not no yes here there
all any some many much more most less few one two three lot still just only also even ever
go went going get got gotten got make made making take took taken let told told tell
need needs needed want wants wanted know knows knew said say says saw see seen seeing
new old next last each other another like really maybe probably actually now soon
day days week weeks month months year years time times today tomorrow yesterday
yeah yep yup ok okay sure right good great fine cool huh wait done
""".split())

_SUPA = None
_ANTH = None


def _supabase():
    global _SUPA
    if _SUPA is not None:
        return _SUPA
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
    _SUPA = create_client(url, key)
    return _SUPA


def _anthropic():
    global _ANTH
    if _ANTH is not None:
        return _ANTH
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY must be set.")
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
    r = (
        _supabase()
        .table("claims")
        .select("*")
        .eq("meeting_id", meeting_id)
        .order("position_in_transcript", desc=False)
        .execute()
    )
    return r.data or []


def _load_open_items(job_ids: list[str]) -> list[dict]:
    if not job_ids:
        return []
    r = (
        _supabase()
        .table("items")
        .select("*")
        .in_("job_id", job_ids)
        .eq("status", "open")
        .execute()
    )
    return r.data or []


def _load_pay_app_lines(job_ids: list[str]) -> list[dict]:
    if not job_ids:
        return []
    r = (
        _supabase()
        .table("pay_app_line_items")
        .select("id, job_id, line_number, description, scheduled_value, pct_complete, division")
        .in_("job_id", job_ids)
        .execute()
    )
    return r.data or []


def _load_subs() -> list[dict]:
    r = _supabase().table("subs").select("id, name, trade, aliases").execute()
    return r.data or []


def _load_jobs() -> list[dict]:
    r = _supabase().table("jobs").select("id, name, address").execute()
    return r.data or []


# ---------- DECISION 8: PER-CLAIM JOB ROUTING ----------

def _route_claim_to_job(claim: dict, jobs: list[dict], default_job: str) -> str:
    """Per Decision 8: subject text wins over meeting.job_id. If multiple job
    names appear, pick the one closest to claim.position_in_transcript."""
    haystack_lo = " ".join([
        (claim.get("subject") or ""),
        (claim.get("statement") or ""),
        (claim.get("raw_quote") or ""),
    ]).lower()
    matches = [j["id"] for j in jobs if j["name"].lower() in haystack_lo]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Tie-break: position-proximity not available without raw transcript scan.
        # For now, fall through to default (heuristic: subject often comes first).
        return matches[0]
    return default_job


# ---------- DECISION 6: SUB MATCHING (3-STAGE CASCADE) ----------

def _haystack(claim: dict) -> str:
    return " ".join([
        (claim.get("subject") or ""),
        (claim.get("statement") or ""),
        (claim.get("raw_quote") or ""),
    ]).lower()


def _match_sub_stage1_alias(claim: dict, subs: list[dict]) -> list[str]:
    """Substring match against each sub's aliases."""
    hay = _haystack(claim)
    matches = []
    for s in subs:
        aliases = s.get("aliases") or []
        for a in aliases:
            if a and a.lower() in hay:
                matches.append(s["id"])
                break
    return list(dict.fromkeys(matches))  # dedup, preserve order


def _match_sub_stage2_ilike(claim: dict, subs: list[dict]) -> list[str]:
    """Substring match against sub.name."""
    hay = _haystack(claim)
    matches = []
    for s in subs:
        n = (s.get("name") or "").lower()
        if n and n in hay:
            matches.append(s["id"])
    return list(dict.fromkeys(matches))


def _match_sub_stage3_haiku(claim: dict, subs: list[dict], cost_tracker: dict) -> str | None:
    """Send claim + sub catalog to Haiku for classification. Validates the
    returned sub_id is actually in the catalog — Haiku occasionally returns
    a name or invented id."""
    catalog = [
        {"id": s["id"], "name": s["name"], "trade": s.get("trade")}
        for s in subs
    ]
    valid_ids = {s["id"] for s in subs}
    system = (
        "You match a single construction meeting claim to the most likely "
        "subcontractor from a catalog. Return strict JSON: "
        '{"sub_id": "<id>" | null}. '
        "Return null if no sub is mentioned or the match is uncertain."
    )
    user = (
        f"CLAIM:\n"
        f"  subject: {claim.get('subject')!r}\n"
        f"  statement: {claim.get('statement')!r}\n"
        f"  raw_quote: {(claim.get('raw_quote') or '')[:300]!r}\n\n"
        f"SUBS CATALOG:\n{json.dumps(catalog, indent=2)}\n\n"
        "Return JSON: {\"sub_id\": \"<id>\" | null}"
    )
    schema = {
        "type": "object",
        "properties": {
            "sub_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": ["sub_id"],
        "additionalProperties": False,
    }
    client = _anthropic()
    started = time.monotonic()
    resp = client.messages.create(
        model=MODEL_HAIKU,
        max_tokens=200,
        system=system,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    )
    cost_tracker["haiku_in"] += getattr(resp.usage, "input_tokens", 0)
    cost_tracker["haiku_out"] += getattr(resp.usage, "output_tokens", 0)
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    sid = payload.get("sub_id")
    if sid and sid in valid_ids:
        return sid
    return None


def _match_sub(claim: dict, subs: list[dict], cost_tracker: dict) -> tuple[str | None, int]:
    """Run 3-stage cascade. Returns (sub_id_or_None, stage_used)."""
    stage1 = _match_sub_stage1_alias(claim, subs)
    if len(stage1) == 1:
        return stage1[0], 1
    stage2 = _match_sub_stage2_ilike(claim, subs)
    if len(stage2) == 1:
        return stage2[0], 2
    # Stage 3 only if any prior stage had ambiguity (>1) or the claim
    # plausibly references a sub (heuristic: contains a capitalized non-known word).
    candidate_signal = bool(stage1) or bool(stage2) or bool(re.search(r"\b[A-Z][a-z]+ (?:Welding|Construction|Electric|Plumbing|HVAC|Tile|Stucco|Concrete|Drywall|Painting|Pool|Service|Door|Glass)\b", (claim.get("statement") or "") + " " + (claim.get("raw_quote") or "")))
    if not candidate_signal:
        return None, 0
    sid = _match_sub_stage3_haiku(claim, subs, cost_tracker)
    return sid, 3


# ---------- DECISION 7: PAY-APP LINE-ITEM MATCHING (2-STAGE CASCADE) ----------

def _keywords(text: str) -> list[str]:
    toks = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    return [t for t in toks if t not in STOP_WORDS]


def _match_pay_app_stage1(claim: dict, lines: list[dict]) -> list[dict]:
    """Word-boundary substring match — significant nouns from the claim
    against pay-app descriptions. Longer keywords weighted higher so "railings"
    beats "all" when both appear."""
    text = (claim.get("subject") or "") + " " + (claim.get("statement") or "")
    kws = _keywords(text)
    kws = sorted(set(kws), key=lambda k: -len(k))[:8]
    if not kws:
        return []
    patterns = [(k, re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE)) for k in kws]
    candidates: list[tuple[dict, float]] = []  # (line, weighted_score)
    for line in lines:
        desc = (line.get("description") or "")
        if not desc:
            continue
        score = 0.0
        for k, pat in patterns:
            if pat.search(desc):
                score += len(k)  # longer keyword = stronger signal
        if score > 0:
            candidates.append((line, score))
    candidates.sort(key=lambda x: -x[1])
    return [c[0] for c in candidates[:5]]


def _match_pay_app_stage2_haiku(claim: dict, candidates: list[dict], cost_tracker: dict) -> str | None:
    """Pick best candidate via Haiku. Validates the returned id is actually
    in the candidate set — Haiku has been observed returning the line_number
    string instead of the uuid id."""
    if not candidates:
        return None
    catalog = [
        {
            "id": c["id"],
            "line_number": c.get("line_number"),
            "description": c.get("description"),
        }
        for c in candidates
    ]
    valid_ids = {c["id"] for c in candidates}
    system = (
        "You match a construction meeting claim to the best pay-app G703 line item, "
        "if any. Return strict JSON: "
        '{"line_item_id": "<uuid>" | null}. '
        "Return null if no candidate is a good match — do not invent matches."
    )
    user = (
        f"CLAIM:\n"
        f"  subject: {claim.get('subject')!r}\n"
        f"  statement: {claim.get('statement')!r}\n\n"
        f"CANDIDATES (pick best or null):\n{json.dumps(catalog, indent=2)}\n\n"
        "Return JSON: {\"line_item_id\": \"<id>\" | null}"
    )
    schema = {
        "type": "object",
        "properties": {
            "line_item_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": ["line_item_id"],
        "additionalProperties": False,
    }
    client = _anthropic()
    resp = client.messages.create(
        model=MODEL_HAIKU,
        max_tokens=200,
        system=system,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    )
    cost_tracker["haiku_in"] += getattr(resp.usage, "input_tokens", 0)
    cost_tracker["haiku_out"] += getattr(resp.usage, "output_tokens", 0)
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    lid = payload.get("line_item_id")
    if lid and lid in valid_ids:
        return lid
    return None


def _match_pay_app_line(claim: dict, lines: list[dict], cost_tracker: dict) -> tuple[str | None, int]:
    """Run 2-stage cascade. Returns (line_id_or_None, stage_used).
    Skips action for question / complaint claim types — those rarely attach to a line."""
    if not lines:
        return None, 0
    if claim["claim_type"] in ("question",):
        return None, 0
    candidates = _match_pay_app_stage1(claim, lines)
    if len(candidates) == 0:
        return None, 0
    if len(candidates) == 1:
        return candidates[0]["id"], 1
    lid = _match_pay_app_stage2_haiku(claim, candidates[:3], cost_tracker)
    return lid, 2


# ---------- DECISION 3: URGENCY ----------

def _has_urgent_keyword(claim: dict) -> bool:
    text = (
        (claim.get("subject") or "")
        + " "
        + (claim.get("statement") or "")
        + " "
        + (claim.get("raw_quote") or "")
    ).lower()
    return any(re.search(rf"\b{re.escape(k)}\b", text) for k in URGENCY_TOKENS)


def _is_within_days(target: date | None, meeting_dt: date, days: int) -> bool:
    if target is None:
        return False
    delta = (target - meeting_dt).days
    return 0 <= delta <= days


def _pay_app_pct_complete(line_id: str | None, lines_by_id: dict) -> float | None:
    if not line_id:
        return None
    line = lines_by_id.get(line_id)
    if not line:
        return None
    v = line.get("pct_complete")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------- THE MAIN OPUS RECONCILER CALL ----------

RECONCILER_SYSTEM_PROMPT = """You are the Reconciler for Ross Built's v2 production-intelligence pipeline. You take structured *claims* extracted from a construction meeting transcript and turn them into structured *items* (actions, observations, flags), *decisions*, and *open questions* that will be stored in Supabase.

# CONTEXT

You are NOT the Extractor — you don't read the raw transcript. You read pre-extracted claims, each with a claim_type, subject, statement, raw_quote, speaker, position, and Python-pre-computed sub_id + pay_app_line_item_id + routed job_id. Your job is to interpret each claim and route it to the right output table with a useful title/detail.

# CLAIM_TYPE -> OUTPUT TABLE MAPPING (Decision 2 — locked)

| claim_type            | output                                       |
|-----------------------|----------------------------------------------|
| commitment            | items (type=action)                          |
| decision              | decisions table                              |
| condition_observed    | items (type=observation)                     |
| status_update         | items (type=observation) MOST OF THE TIME,   |
|                       | OR items (type=action) when the status       |
|                       | reveals a stalled item / new implicit        |
|                       | commitment                                   |
| complaint             | items (type=flag) when naming a sub/process  |
|                       | as a problem; items (type=observation) when  |
|                       | just venting                                 |
| question              | open_questions table                         |

Some claims may be DROPPED (truly trivial — pure repetition / no usable content). Use `dropped` for those. If a claim is real but you can't confidently classify it, put it in `needs_review` rather than guessing.

# TITLE / DETAIL GENERATION

- `title`: ONE LINE, max ~80 chars. Compress the claim's statement into a scannable headline.
  - Lead with the sub or scope when possible: "DB Welding: railings on house by Jul 4"
  - Avoid stop words ("the", "a", "we"). Telegraphic style.
- `detail`: 1-3 sentences. Preserve nuance the title couldn't. Include source meeting reference and (if matched) pay-app line item description. The raw_quote does NOT need to be repeated — it lives on the claim.
- For decisions.description: ONE sentence stating what was decided. No backstory unless essential.
- For open_questions.question: phrase as a real question with a question mark.

# TARGET_DATE EXTRACTION (Decision 5 — locked)

- If the claim text contains a parseable date (explicit date, weekday+context, "July 4th") -> emit `target_date` as YYYY-MM-DD. Use the meeting_date as the reference for relative dates.
- If the claim has a date-ish phrase you CAN'T resolve to a specific date ("next week", "by end of month", "before the slab pour", "ASAP") -> leave `target_date` NULL and put the original phrase in `target_date_text`.
- If no time signal at all -> both NULL.

# DEDUP (Decision 9 — locked)

You will receive an `existing_open_items` list. For each new claim, check if it matches an existing open item on (job_id + sub_id + pay_app_line_item_id). If yes:
- Set `decision: "update_existing"` and reference the existing item's id in `existing_item_id`.
- Your title/detail will REPLACE the existing values (Python applies clobber prevention on manually-edited fields).
- The new target_date overrides the old one (commitments shift).

If no match, set `decision: "create"`.

# NEEDS_REVIEW

Use needs_review for claims where:
- claim_type doesn't cleanly map (e.g. a status_update that's truly ambiguous between observation/action)
- the title would be misleading or you can't write a faithful one
- the speaker said something contradicting an existing item AND it's not clear which is current

# OUTPUT FORMAT

Strict JSON. One top-level object. Every claim must end up exactly once in items/decisions/open_questions/dropped/needs_review."""


RECONCILER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id":               {"type": "string"},
                    "decision":               {"type": "string", "enum": ["create", "update_existing"]},
                    "existing_item_id":       {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "type":                   {"type": "string", "enum": ["action", "observation", "flag"]},
                    "job_id":                 {"type": "string"},
                    "title":                  {"type": "string"},
                    "detail":                 {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "target_date":            {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "target_date_text":       {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "is_vague":               {"type": "boolean"},
                    "owner":                  {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": [
                    "claim_id", "decision", "existing_item_id", "type", "job_id",
                    "title", "detail", "target_date", "target_date_text", "is_vague", "owner",
                ],
                "additionalProperties": False,
            },
        },
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id":     {"type": "string"},
                    "job_id":       {"type": "string"},
                    "description":  {"type": "string"},
                    "decided_by":   {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "decision_date":{"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["claim_id", "job_id", "description", "decided_by", "decision_date"],
                "additionalProperties": False,
            },
        },
        "open_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id":    {"type": "string"},
                    "job_id":      {"type": "string"},
                    "question":    {"type": "string"},
                    "asked_by":    {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["claim_id", "job_id", "question", "asked_by"],
                "additionalProperties": False,
            },
        },
        "dropped": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "reason":   {"type": "string"},
                },
                "required": ["claim_id", "reason"],
                "additionalProperties": False,
            },
        },
        "needs_review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "reason":   {"type": "string"},
                },
                "required": ["claim_id", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items", "decisions", "open_questions", "dropped", "needs_review"],
    "additionalProperties": False,
}


def _reconciler_call(
    meeting: dict,
    claims_enriched: list[dict],
    existing_items: list[dict],
    pay_app_lines_by_id: dict,
    subs_by_id: dict,
    cost_tracker: dict,
) -> dict:
    """One Opus call per meeting."""

    # Compact existing-items context: just the fields the LLM needs for dedup.
    existing_compact = [
        {
            "id": it["id"],
            "human_readable_id": it.get("human_readable_id"),
            "job_id": it["job_id"],
            "type": it["type"],
            "title": it["title"],
            "sub_id": it.get("sub_id"),
            "pay_app_line_item_id": it.get("pay_app_line_item_id"),
            "target_date": it.get("target_date"),
            "status": it["status"],
        }
        for it in existing_items
    ]

    # Compact claim payload — include the Python-computed matches so the LLM
    # doesn't redo them. Strip raw_quote down to first ~300 chars to save tokens.
    claims_compact = []
    for c in claims_enriched:
        line = pay_app_lines_by_id.get(c.get("pay_app_line_item_id") or "")
        sub = subs_by_id.get(c.get("sub_id") or "")
        claims_compact.append({
            "claim_id":               c["id"],
            "claim_type":             c["claim_type"],
            "speaker":                c.get("speaker"),
            "subject":                c.get("subject"),
            "statement":              c.get("statement"),
            "raw_quote":              (c.get("raw_quote") or "")[:300],
            "position":               c.get("position_in_transcript"),
            "routed_job_id":          c["_routed_job_id"],
            "matched_sub_id":         c.get("sub_id"),
            "matched_sub_name":       sub["name"] if sub else None,
            "matched_line_item_id":   c.get("pay_app_line_item_id"),
            "matched_line_item_desc": line["description"] if line else None,
        })

    user_msg = (
        f"MEETING:\n"
        f"  id: {meeting['id']}\n"
        f"  date: {meeting['meeting_date']}\n"
        f"  type: {meeting['meeting_type']}\n"
        f"  primary_job_id: {meeting['job_id']}\n\n"
        f"CLAIMS ({len(claims_compact)} total):\n"
        f"{json.dumps(claims_compact, indent=2, default=str)}\n\n"
        f"EXISTING OPEN ITEMS (for dedup, may be empty):\n"
        f"{json.dumps(existing_compact, indent=2, default=str)}\n\n"
        "Return strict JSON matching the schema. Every claim_id must appear exactly once across items + decisions + open_questions + dropped + needs_review."
    )

    client = _anthropic()
    started = time.monotonic()
    with client.messages.stream(
        model=MODEL_OPUS,
        max_tokens=48000,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": RECONCILER_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": RECONCILER_OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        final = stream.get_final_message()
    elapsed_ms = int((time.monotonic() - started) * 1000)

    text_block = next((b for b in final.content if b.type == "text"), None)
    if text_block is None:
        raise RuntimeError(f"Reconciler returned no text (stop_reason={final.stop_reason})")
    payload = json.loads(text_block.text)

    usage = final.usage
    cost_tracker["opus_in"] += getattr(usage, "input_tokens", 0)
    cost_tracker["opus_out"] += getattr(usage, "output_tokens", 0)
    cost_tracker["opus_cache_read"] += (getattr(usage, "cache_read_input_tokens", 0) or 0)
    cost_tracker["opus_cache_create"] += (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cost_tracker["opus_elapsed_ms"] += elapsed_ms

    return payload


# ---------- ID GENERATION ----------

def _next_human_id(job_id: str, kind: str) -> str:
    """Kind: 'item' | 'decision' | 'question'. Reads MAX existing per prefix
    and increments. NOT a transaction-safe sequence; fine for build phase."""
    prefix = JOB_PREFIXES.get(job_id, job_id.upper()[:4])
    if kind == "item":
        like = f"{prefix}-%"
        table = "items"
    elif kind == "decision":
        like = f"{prefix}-D-%"
        table = "decisions"
    elif kind == "question":
        like = f"{prefix}-Q-%"
        table = "open_questions"
    else:
        raise ValueError(kind)
    r = (
        _supabase()
        .table(table)
        .select("human_readable_id")
        .like("human_readable_id", like)
        .execute()
    )
    nums = []
    for row in r.data or []:
        m = re.search(r"(\d+)$", row["human_readable_id"])
        if m:
            nums.append(int(m.group(1)))
    nxt = (max(nums) + 1) if nums else 1
    if kind == "item":
        return f"{prefix}-{nxt:03d}"
    elif kind == "decision":
        return f"{prefix}-D-{nxt:03d}"
    else:
        return f"{prefix}-Q-{nxt:03d}"


# ---------- DECISION 11: CLOBBER PREVENTION ----------

def _apply_clobber_prevention(new_values: dict, existing: dict) -> dict:
    """Return the dict to UPDATE the existing row with, after applying clobber
    prevention. Rules per Decision 11:
    - If manually_edited_at IS NOT NULL: preserve each field listed in manually_edited_fields.
    - If status='complete' AND completed_at IS NOT NULL: force preserve status + completed_at.
    """
    merged = dict(new_values)

    if existing.get("manually_edited_at"):
        for f in existing.get("manually_edited_fields") or []:
            if f in merged:
                merged[f] = existing.get(f)

    if existing.get("status") == "complete" and existing.get("completed_at"):
        merged["status"] = "complete"
        merged["completed_at"] = existing["completed_at"]
        # Don't reset completion_basis
        if existing.get("completion_basis"):
            merged["completion_basis"] = existing["completion_basis"]

    return merged


# ---------- TARGET_DATE PARSE (safety net) ----------

def _parse_target_date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


# ---------- DECISION 4: CONFIDENCE (cold-start, transcript only) ----------

def _derive_confidence(is_vague: bool, has_sub: bool, has_line: bool) -> str:
    """Cold-start (no daily_logs yet, no prior cross-source) per Decision 4.
    - high: never at cold start (requires 2+ sources)
    - medium: clear claim (named sub + named scope OR explicit commitment)
    - low: vague claim
    """
    if is_vague:
        return "low"
    if has_sub or has_line:
        return "medium"
    return "low"


# ---------- DECISION 3: PRIORITY ----------

def _derive_priority(
    claim: dict,
    target_date_iso: str | None,
    meeting_dt: date,
    line_pct: float | None,
) -> str:
    """Decision 3 triggers (any => urgent):
    1. Explicit urgency tokens in claim text.
    2. target_date within 7 days of meeting_date.
    3. matched pay_app_line shows >90% complete.
    4. Sub has 2+ slipped commitments in last 30 days — DEFERRED (needs sub_events).
    """
    if _has_urgent_keyword(claim):
        return "urgent"
    if target_date_iso:
        try:
            td = datetime.fromisoformat(target_date_iso).date()
            if _is_within_days(td, meeting_dt, 7):
                return "urgent"
        except ValueError:
            pass
    if line_pct is not None and line_pct > 0.90:
        return "urgent"
    return "normal"


# ---------- DEDUP HELPERS (Decision 9) ----------

def _find_dedup_candidate(
    proposed: dict, claim: dict, existing_items: list[dict]
) -> dict | None:
    """Match on (job_id, sub_id, pay_app_line_item_id) — three-field tuple.
    Fallback: (job_id, sub_id, subject_keywords) if line_id is NULL on either."""
    job_id = proposed["job_id"]
    sub_id = claim.get("sub_id")
    line_id = claim.get("pay_app_line_item_id")

    if line_id is not None:
        for it in existing_items:
            if (it.get("job_id") == job_id
                    and it.get("sub_id") == sub_id
                    and it.get("pay_app_line_item_id") == line_id):
                return it
        return None

    # Fallback: same job + sub + subject keyword overlap >= 2
    kws_new = set(_keywords(proposed.get("title", "") + " " + (proposed.get("detail") or "")))
    for it in existing_items:
        if it.get("job_id") != job_id or it.get("sub_id") != sub_id:
            continue
        kws_old = set(_keywords(it.get("title", "") + " " + (it.get("detail") or "")))
        if len(kws_new & kws_old) >= 2:
            return it
    return None


# ---------- MAIN ENTRYPOINT ----------

def reconcile_meeting(meeting_id: str, dry_run: bool = False) -> dict:
    """Reconcile one meeting's claims into items + decisions + open_questions."""
    started = time.monotonic()
    cost_tracker = {
        "opus_in": 0, "opus_out": 0, "opus_cache_read": 0, "opus_cache_create": 0,
        "opus_elapsed_ms": 0,
        "haiku_in": 0, "haiku_out": 0,
    }

    meeting = _load_meeting(meeting_id)
    meeting_dt = datetime.fromisoformat(meeting["meeting_date"]).date() if isinstance(meeting["meeting_date"], str) else meeting["meeting_date"]
    claims = _load_claims(meeting_id)

    jobs = _load_jobs()
    subs = _load_subs()
    subs_by_id = {s["id"]: s for s in subs}

    # Per-claim routing first to know which jobs we need pay_app + existing_items for.
    routed_jobs: set[str] = set()
    for c in claims:
        c["_routed_job_id"] = _route_claim_to_job(c, jobs, meeting["job_id"])
        routed_jobs.add(c["_routed_job_id"])
    job_ids_for_meeting = list(routed_jobs)

    pay_app_lines = _load_pay_app_lines(job_ids_for_meeting)
    pay_lines_by_id = {l["id"]: l for l in pay_app_lines}
    pay_lines_by_job = {jid: [l for l in pay_app_lines if l["job_id"] == jid] for jid in job_ids_for_meeting}

    existing_items = _load_open_items(job_ids_for_meeting)

    # Per-claim sub + pay-app matching.
    sub_stage_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    pay_app_match_count = 0
    pay_app_unmatched_count = 0

    for c in claims:
        sid, stage = _match_sub(c, subs, cost_tracker)
        c["sub_id"] = sid
        sub_stage_counts[stage] = sub_stage_counts.get(stage, 0) + 1
        lid, _ = _match_pay_app_line(c, pay_lines_by_job.get(c["_routed_job_id"], []), cost_tracker)
        c["pay_app_line_item_id"] = lid
        if lid:
            pay_app_match_count += 1
        elif c["claim_type"] in ("commitment", "status_update", "condition_observed"):
            pay_app_unmatched_count += 1

    # The Opus reconciler call.
    llm_output = _reconciler_call(
        meeting, claims, existing_items, pay_lines_by_id, subs_by_id, cost_tracker,
    )

    # Build a claim-id-keyed map for quick lookup
    claim_by_id = {c["id"]: c for c in claims}

    # ---- Write outputs to DB ----
    items_created = 0
    items_updated = 0
    decisions_created = 0
    questions_created = 0
    needs_review: list[dict] = []

    if dry_run:
        return {
            "status": "dry_run",
            "meeting_id": meeting_id,
            "claims_processed": len(claims),
            "llm_output": llm_output,
        }

    client = _supabase()

    # ITEMS
    for it in llm_output.get("items", []):
        cid = it["claim_id"]
        c = claim_by_id.get(cid)
        if c is None:
            needs_review.append({"claim_id": cid, "reason": "LLM referenced unknown claim_id"})
            continue

        target_date_iso = _parse_target_date(it.get("target_date"))
        line_pct = _pay_app_pct_complete(c.get("pay_app_line_item_id"), pay_lines_by_id)
        priority = _derive_priority(c, target_date_iso, meeting_dt, line_pct)
        confidence = _derive_confidence(
            is_vague=bool(it.get("is_vague")),
            has_sub=c.get("sub_id") is not None,
            has_line=c.get("pay_app_line_item_id") is not None,
        )

        # Job + PM
        job_id = it["job_id"] if it["job_id"] else c["_routed_job_id"]

        if it["decision"] == "update_existing" and it.get("existing_item_id"):
            existing = next((e for e in existing_items if e["id"] == it["existing_item_id"]), None)
            if existing is None:
                needs_review.append({"claim_id": cid, "reason": f"LLM referenced unknown existing_item_id {it['existing_item_id']}"})
                continue
            update_values = {
                "title":               it["title"],
                "detail":              it.get("detail"),
                "target_date":         target_date_iso,
                "target_date_text":    it.get("target_date_text"),
                "priority":            priority,
                "confidence":          confidence,
                "owner":               it.get("owner"),
                "source_meeting_id":   meeting["id"],
                "updated_at":          _now_iso(),
                "carryover_count":     (existing.get("carryover_count") or 0) + 1,
                "type":                it["type"],
                "sub_id":              c.get("sub_id"),
                "pay_app_line_item_id":c.get("pay_app_line_item_id"),
            }
            merged = _apply_clobber_prevention(update_values, existing)
            client.table("items").update(merged).eq("id", existing["id"]).execute()
            items_updated += 1
            continue

        # CREATE
        hid = _next_human_id(job_id, "item")
        new_row = {
            "human_readable_id":     hid,
            "job_id":                job_id,
            "pm_id":                 meeting.get("pm_id"),
            "type":                  it["type"],
            "title":                 it["title"],
            "detail":                it.get("detail"),
            "sub_id":                c.get("sub_id"),
            "owner":                 it.get("owner"),
            "target_date":           target_date_iso,
            "target_date_text":      it.get("target_date_text"),
            "status":                "open",
            "priority":              priority,
            "confidence":            confidence,
            "source_meeting_id":     meeting["id"],
            "pay_app_line_item_id":  c.get("pay_app_line_item_id"),
            "carryover_count":       0,
        }
        client.table("items").insert(new_row).execute()
        items_created += 1

    # DECISIONS
    for d in llm_output.get("decisions", []):
        cid = d["claim_id"]
        c = claim_by_id.get(cid)
        if c is None:
            needs_review.append({"claim_id": cid, "reason": "LLM referenced unknown claim_id (decision)"})
            continue
        job_id = d["job_id"] if d["job_id"] else c["_routed_job_id"]
        hid = _next_human_id(job_id, "decision")
        client.table("decisions").insert({
            "human_readable_id":  hid,
            "job_id":             job_id,
            "source_meeting_id":  meeting["id"],
            "description":        d["description"],
            "decided_by":         d.get("decided_by"),
            "decision_date":      _parse_target_date(d.get("decision_date")) or meeting["meeting_date"],
            "source_claim_id":    cid,
        }).execute()
        decisions_created += 1

    # OPEN QUESTIONS
    for q in llm_output.get("open_questions", []):
        cid = q["claim_id"]
        c = claim_by_id.get(cid)
        if c is None:
            needs_review.append({"claim_id": cid, "reason": "LLM referenced unknown claim_id (question)"})
            continue
        job_id = q["job_id"] if q["job_id"] else c["_routed_job_id"]
        hid = _next_human_id(job_id, "question")
        client.table("open_questions").insert({
            "human_readable_id":  hid,
            "job_id":             job_id,
            "source_meeting_id":  meeting["id"],
            "question":           q["question"],
            "asked_by":           q.get("asked_by"),
            "source_claim_id":    cid,
        }).execute()
        questions_created += 1

    # Mark meeting as reconciled
    client.table("meetings").update({"reconciled_at": _now_iso(), "reconciler_version": "1.0"}).eq("id", meeting_id).execute()

    # Aggregate needs_review (from LLM output + any we added)
    for n in llm_output.get("needs_review", []):
        needs_review.append(n)

    dropped = llm_output.get("dropped", [])
    elapsed_ms = int((time.monotonic() - started) * 1000)

    cost_usd = (
        cost_tracker["opus_in"] * OPUS_PRICE_IN
        + cost_tracker["opus_out"] * OPUS_PRICE_OUT
        + cost_tracker["opus_cache_read"] * OPUS_PRICE_CACHE_READ
        + cost_tracker["opus_cache_create"] * OPUS_PRICE_CACHE_CREATE
        + cost_tracker["haiku_in"] * HAIKU_PRICE_IN
        + cost_tracker["haiku_out"] * HAIKU_PRICE_OUT
    )

    return {
        "meeting_id": meeting_id,
        "claims_processed": len(claims),
        "items_created": items_created,
        "items_updated": items_updated,
        "decisions_created": decisions_created,
        "open_questions_created": questions_created,
        "claims_dropped": dropped,
        "sub_matches": {"by_stage": sub_stage_counts},
        "pay_app_matches": {"matched": pay_app_match_count, "unmatched": pay_app_unmatched_count},
        "needs_review": needs_review,
        "elapsed_ms": elapsed_ms,
        "tokens": {
            "opus_in": cost_tracker["opus_in"],
            "opus_out": cost_tracker["opus_out"],
            "opus_cache_read": cost_tracker["opus_cache_read"],
            "opus_cache_create": cost_tracker["opus_cache_create"],
            "haiku_in": cost_tracker["haiku_in"],
            "haiku_out": cost_tracker["haiku_out"],
        },
        "cost_usd": round(cost_usd, 4),
    }
