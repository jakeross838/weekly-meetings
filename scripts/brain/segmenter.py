"""Transcript-by-job segmenter.

Uses Claude Haiku (routing task, no deep reasoning required) to identify
clear job-transition points in a transcript and emit one segment per job
section. Most meetings are single-job and return one segment.

Public function:
    segment_transcript_by_job(transcript_text, available_jobs, primary_job_id) -> list
        Returns list of {start_pos, end_pos, inferred_job_id}, covering [0, len(transcript)).

    find_segment_for_position(segments, position) -> dict | None
"""

from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


MODEL_HAIKU = "claude-haiku-4-5"


SEGMENTER_SYSTEM_PROMPT = """You analyze meeting transcripts from a residential construction company (Ross Built, LLC) and identify which sections of the transcript discuss which job.

Most meetings cover ONE job, end-to-end. Some "office" meetings cover MULTIPLE jobs sequentially (e.g. "let's talk about Krauss... then move to Ruthven"). Your job is to identify clear job-transition points and emit one or more segments tagged with the job they discuss.

You will receive:
- The transcript text (raw, with Plaud transcription noise)
- The list of available job_ids (only these are valid targets)
- A primary_job_id from the meeting metadata (use as fallback / default)

Output: a JSON list of segments. Each segment has:
- start_pos: integer character offset in the transcript (inclusive)
- end_pos: integer character offset (exclusive)
- inferred_job_id: one of the available_jobs

Rules:
- Segments must cover the entire transcript from 0 to len(transcript), no gaps, no overlap.
- If the transcript is single-job, return ONE segment covering 0 to len(transcript).
- Job-transition cues: phrases like "ok let's move to X", "switching to X", "back to X", "X next", references to job names, address mentions, client name mentions.
- If you can't tell where a transition is precisely, err on the side of FEWER segments — treat ambiguous content as part of the primary job.
- inferred_job_id MUST be one of the available_jobs. Don't invent job_ids.

Return strict JSON matching the schema."""


_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_pos":       {"type": "integer"},
                    "end_pos":         {"type": "integer"},
                    "inferred_job_id": {"type": "string"},
                },
                "required": ["start_pos", "end_pos", "inferred_job_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["segments"],
    "additionalProperties": False,
}


def segment_transcript_by_job(
    transcript_text: str,
    available_jobs: list,
    primary_job_id: str,
) -> list:
    """Segment a transcript into job-sections. Returns a list of
    {start_pos, end_pos, inferred_job_id} covering the entire transcript.

    Falls back to a single segment with primary_job_id if Haiku output is
    malformed or the call fails. Single-segment is also returned when only
    one job is available."""
    n = len(transcript_text)
    fallback = [{"start_pos": 0, "end_pos": n, "inferred_job_id": primary_job_id}]

    if n == 0 or len(available_jobs) <= 1:
        return fallback

    import anthropic
    client = anthropic.Anthropic()

    jobs_compact = [{"id": j["id"], "name": j["name"]} for j in available_jobs]
    user_msg = (
        f"AVAILABLE_JOBS: {json.dumps(jobs_compact)}\n"
        f"PRIMARY_JOB_ID: {primary_job_id}\n"
        f"TRANSCRIPT_LENGTH: {n}\n\n"
        f"TRANSCRIPT:\n{transcript_text}\n\n"
        f"Return segments covering [0, {n})."
    )

    try:
        resp = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=4000,
            system=SEGMENTER_SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as e:
        print(f"  segmenter: Haiku call failed: {e!r}", flush=True)
        return fallback

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print(f"  segmenter: bad JSON from Haiku, falling back to single segment", flush=True)
        return fallback

    segments = payload.get("segments") or []
    valid_jobs = {j["id"] for j in available_jobs}
    clean: list[dict] = []
    for seg in segments:
        if seg.get("inferred_job_id") not in valid_jobs:
            continue
        sp = max(0, int(seg.get("start_pos", 0)))
        ep = min(n, int(seg.get("end_pos", n)))
        if sp >= ep:
            continue
        clean.append({"start_pos": sp, "end_pos": ep, "inferred_job_id": seg["inferred_job_id"]})

    if not clean:
        return fallback

    clean.sort(key=lambda s: s["start_pos"])
    # Pad any leading or trailing gap with the primary job
    if clean[0]["start_pos"] > 0:
        clean.insert(0, {"start_pos": 0, "end_pos": clean[0]["start_pos"], "inferred_job_id": primary_job_id})
    if clean[-1]["end_pos"] < n:
        clean.append({"start_pos": clean[-1]["end_pos"], "end_pos": n, "inferred_job_id": primary_job_id})

    # Patch any internal gaps by extending the previous segment
    patched: list[dict] = []
    for seg in clean:
        if patched and seg["start_pos"] > patched[-1]["end_pos"]:
            patched[-1]["end_pos"] = seg["start_pos"]
        patched.append(seg)

    return patched


def find_segment_for_position(segments: list, position: int | None) -> Optional[dict]:
    """Return the segment whose [start_pos, end_pos) contains position, or None."""
    if position is None:
        return None
    for seg in segments:
        if seg["start_pos"] <= position < seg["end_pos"]:
            return seg
    return None
