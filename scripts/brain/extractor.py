"""Call 1 of the v2 brain: Extractor.

Takes a raw construction meeting transcript and produces a list of structured
*claims* — paraphrased statements from each speaker, classified into one of
six claim types. NO reconciliation, NO cross-source logic, NO deduplication.
Claim accuracy and completeness are the only goals.

Public function:
    extract_claims(transcript_text, meeting_metadata) -> dict

Returns:
    {
      "claims":   [{...matching claims table columns...}],
      "metadata": {model, input_tokens, output_tokens, cache_*_tokens, elapsed_ms},
    }

Notes:
- Uses claude-opus-4-7 (matching the v1 pipeline in process.py).
- Adaptive thinking enabled — extraction is moderately complex.
- Structured outputs (json_schema) — guarantees parseable JSON.
- System prompt is cached (top-level cache_control) so the 5-transcript test
  pays the full-system-prompt cost once and reads from cache on calls 2-5.
- Streams the response with `messages.stream()` so large outputs don't hit
  SDK HTTP timeouts.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-7"

CLAIM_TYPES = [
    "commitment",
    "decision",
    "condition_observed",
    "status_update",
    "question",
    "complaint",
]


SYSTEM_PROMPT = """You are a structured information extractor for construction meeting transcripts at Ross Built, LLC (a residential construction company).

INPUT: A raw transcript from an automatic transcription tool (Plaud). These transcripts are messy — typically 50%+ noise, frequent crosstalk, mistranscribed names, technical jargon, and incomplete sentences. Speakers are construction project managers and field staff discussing active jobs.

YOUR JOB: Extract every distinct CLAIM as a structured statement. A claim is anything a speaker SAID — a commitment, a decision, an observation, a question, a complaint, or a status update.

# CRITICAL RULES

1. **Extract claims AS-SAID. Do NOT deduplicate.** If two speakers say the same thing, or one person contradicts themselves later, that is TWO claims, not one merged claim. The Reconciler downstream handles dedup — your job is to lose no information.

2. **Do NOT summarize across the meeting.** Do NOT collapse "Sanger said Tuesday" and "Sanger now says Friday" into "Sanger commitment shifted." Those are two separate commitment claims.

3. **Do NOT make judgments.** Do NOT decide which of two contradictory statements is correct. Record both.

4. **Be CONSERVATIVE about classification.** If you cannot confidently classify a statement into one of the six claim types below, LEAVE IT OUT rather than guess. Quality matters more than quantity.

5. **Preserve raw_quote verbatim from the transcript** (or the closest reasonable verbatim — the transcripts have errors). This lets reviewers audit your extraction.

6. **position_in_transcript** = approximate character offset (integer) where the source quote appears in the transcript. Estimate from the position of the quote text in the input. Used for debugging.

# CLAIM TYPES

- **commitment** — Someone said they or another party WILL do something. Future-tense action with an owner. Examples: "Sanger will pour Tuesday." "I'll call Tom tomorrow." "Lee said he'd send the schedule by Friday."

- **decision** — A choice was made between alternatives, or a direction was settled. Examples: "We're going with Progressive for the bug screens." "Owner approved the change order." "Decided to delay drywall until after framing punch is complete."

- **condition_observed** — A speaker reported a state of the world or site condition. Examples: "The slab is poured." "There's a leak in the basement." "Sub finished tile in master bath." NOT progress reporting on Ross Built's work — that's status_update.

- **status_update** — Progress reporting on Ross Built work that's in-flight. Examples: "Framing is about 60% done." "We're behind on tile by a week." "Permit application is still in review." Distinct from condition_observed in that it tracks WORK PROGRESS, not site state.

- **question** — A speaker asked a question. Often unanswered in the transcript. Examples: "Did Sanger ever show up Monday?" "When does drywall start?"

- **complaint** — A speaker expressed dissatisfaction, frustration, or escalation. Examples: "Sanger has missed three commitments in a row." "The client is unhappy with the appliance install."

If a statement is purely social ("hey how's it going"), purely filler ("uh yeah"), or off-topic chitchat, IGNORE it. Same for crosstalk where you can't tell who's speaking or what's being said.

# KNOWN SPEAKERS

Ross Built people who commonly appear in meetings:
- Jake (Jake Ross — owner/operator, frequently runs meetings)
- Lee Ross (co-owner)
- Andrew Ross (co-owner)
- Bob (Bob Mozine — PM for Drummond, Molinari, Biales)
- Jason (Jason Szykulski — PM for Pou, Dewberry, Harllee)
- Lee Worthy (PM for Krauss, Ruthven) — note: distinct from Lee Ross
- Martin (Martin Mannix — PM for Fish)
- Nelson (Nelson Belanger — PM for Markgraf, Clark, Johnson)

Also: clients (by last name like "Krauss", "Pou"), sub company names (Sanger, Progressive, etc.), site crew.

If you cannot identify a speaker from the transcript, set `speaker` to null. Do NOT guess.

# SUBJECT FIELD

`subject` = what the claim is ABOUT. Pick the most specific thing:
- For commitments: the sub/person/scope responsible (e.g. "Sanger", "drywall trim-out", "Owner")
- For decisions: the product/area/aspect decided (e.g. "Bug screens", "tile vendor", "completion date")
- For observations: the area/system/sub (e.g. "Master bath", "exterior framing", "Sanger")
- For status_updates: the work scope (e.g. "framing", "permit", "punch list")
- For questions: the topic
- For complaints: the target

If the subject is genuinely unclear, set it to null.

# OUTPUT FORMAT

Strict JSON matching the supplied schema. One claim per discrete statement. Order claims by their position in the transcript (earliest first).

When in doubt, leave it out."""


CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Identified speaker, or null if unknown.",
                    },
                    "claim_type": {
                        "type": "string",
                        "enum": CLAIM_TYPES,
                    },
                    "subject": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "What the claim is about (sub, person, scope, topic).",
                    },
                    "statement": {
                        "type": "string",
                        "description": "Paraphrased claim content (one sentence).",
                    },
                    "raw_quote": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Verbatim quote from the transcript.",
                    },
                    "position_in_transcript": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "Approximate character offset where the quote appears.",
                    },
                },
                "required": [
                    "speaker",
                    "claim_type",
                    "subject",
                    "statement",
                    "raw_quote",
                    "position_in_transcript",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims"],
    "additionalProperties": False,
}


def _build_user_message(transcript_text: str, meeting_metadata: dict) -> str:
    attendees = meeting_metadata.get("attendees")
    attendees_line = ", ".join(attendees) if attendees else "unknown"
    return (
        "MEETING METADATA:\n"
        f"- Job: {meeting_metadata.get('job_id')}\n"
        f"- PM: {meeting_metadata.get('pm_id')}\n"
        f"- Date: {meeting_metadata.get('meeting_date')}\n"
        f"- Type: {meeting_metadata.get('meeting_type')}\n"
        f"- Attendees: {attendees_line}\n"
        f"- Notes: {meeting_metadata.get('notes') or 'none'}\n\n"
        "TRANSCRIPT (raw, errors expected):\n"
        "```\n"
        f"{transcript_text}\n"
        "```\n\n"
        "Extract every distinct claim per the rules in the system prompt. "
        "Return strict JSON matching the schema. Order by position_in_transcript."
    )


def extract_claims(transcript_text: str, meeting_metadata: dict) -> dict:
    """Run the Extractor against one transcript. See module docstring."""
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY must be set (loaded from .env or environment)")

    client = anthropic.Anthropic()
    user_msg = _build_user_message(transcript_text, meeting_metadata)

    started = time.monotonic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        output_config={
            "format": {"type": "json_schema", "schema": CLAIMS_SCHEMA},
        },
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        final = stream.get_final_message()
    elapsed_ms = int((time.monotonic() - started) * 1000)

    text_block = next((b for b in final.content if b.type == "text"), None)
    if text_block is None:
        raise RuntimeError(
            f"No text block in response (stop_reason={final.stop_reason}). "
            f"Content types: {[b.type for b in final.content]}"
        )

    try:
        payload = json.loads(text_block.text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model returned invalid JSON: {e}\n\nText:\n{text_block.text[:500]}") from e

    claims = payload.get("claims", [])

    usage = final.usage
    return {
        "claims": claims,
        "metadata": {
            "model": MODEL,
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "elapsed_ms": elapsed_ms,
            "stop_reason": final.stop_reason,
        },
    }
