#!/usr/bin/env python3
"""Ross Built - Email Intel: ANALYZE.

Pulls the stored intelligence for ONE job and produces a master-PM review:
state of play, open commitments, risks/gaps, prioritized next actions.

Generalized to the real jobs spine: the argument can be a job SLUG (jobs.id,
e.g. "fish"), a job NAME, or a free-text project string. Resolution order:
  1. exact jobs.id slug match  -> query job_intel by job_id
  2. exact jobs.name match      -> query job_intel by that job_id
  3. otherwise                  -> fall back to the raw `project` ilike (audit /
     unrouted rows that were never resolved to a job_id).

Run:  python analyze.py "Fish"      (or a slug like "fish")
"""

import json
import sys

import requests

import config as cfg


def sb_headers():
    return {
        "apikey": cfg.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {cfg.SUPABASE_SERVICE_KEY}",
    }


def sb_app_config(key):
    """Read one app_config value (org-configurable model name). None if absent."""
    try:
        r = requests.get(
            f"{cfg.SUPABASE_URL}/rest/v1/app_config",
            headers=sb_headers(),
            params={"key": f"eq.{key}", "select": "value"},
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0]["value"] if rows else None
    except Exception:
        return None


def resolve_job(arg):
    """Return (job_id, label) for a slug/name arg, or (None, arg) if not a known job."""
    a = arg.strip()
    # slug (jobs.id) or name, case-insensitive
    r = requests.get(
        f"{cfg.SUPABASE_URL}/rest/v1/jobs",
        headers=sb_headers(),
        params={"select": "id,name", "or": f"(id.ilike.{a},name.ilike.{a})"},
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json()
    if rows:
        return rows[0]["id"], (rows[0].get("name") or rows[0]["id"])
    return None, a


def load_intel(arg):
    job_id, label = resolve_job(arg)
    params = {
        "select": "sent_at,intel_type,summary,detail,action_needed,recipients",
        "order": "sent_at.asc",
        "hidden": "eq.false",
    }
    if job_id is not None:
        params["job_id"] = f"eq.{job_id}"
    else:
        # Not a known job -> search the raw inferred project name (unrouted rows).
        params["project"] = f"ilike.*{arg}*"
    r = requests.get(
        f"{cfg.SUPABASE_URL}/rest/v1/job_intel",
        headers=sb_headers(),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return label, r.json()


ANALYZE_SYSTEM = """You are a master construction project manager reviewing ONE job at a luxury coastal custom-home builder (Ross Built), optimizing for maximum efficiency and zero dropped balls.
You are given the durable intelligence captured from the PM's sent emails on this job, in date order.

Produce a tight, standardized review. Be specific and useful - a good PM reading this should NOT think "no shit." Cite concrete items (dates, names, amounts). If the data is thin, say so plainly instead of padding. Do not invent facts the intel does not support.

Format exactly:

STATE OF PLAY
2-3 sentences: where this job appears to be, based only on the intel.

OPEN COMMITMENTS
Promises/answers made but not visibly closed. Bullet each: what, to whom, when made. If none evident, say so.

RISKS & GAPS
What's unresolved, slipping, or missing that a sharp PM would chase now. Be concrete.

NEXT ACTIONS (prioritized)
3-6 specific moves. Not "follow up with the sub" - say who owes what, since when, and the exact ask."""


def main():
    if len(sys.argv) < 2:
        sys.exit('Usage: python analyze.py "<job slug or name>"')
    arg = sys.argv[1]
    label, intel = load_intel(arg)
    if not intel:
        sys.exit(
            f'No stored intel yet for a job matching "{arg}". '
            f"Run capture.py first, or check the slug/name."
        )

    analyze_model = cfg.pick_model(
        sb_app_config("INTEL_ANALYZE_MODEL"), cfg.ANALYZE_MODEL_ENV, cfg.DEFAULT_ANALYZE_MODEL
    )
    user = (
        f"JOB: {label}\nCAPTURED INTELLIGENCE ({len(intel)} items):\n"
        + json.dumps(intel, indent=2)
    )
    payload = {
        "model": analyze_model,
        "max_tokens": 1500,
        "system": ANALYZE_SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": cfg.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    print("\n" + "".join(b.get("text", "") for b in r.json().get("content", [])) + "\n")


if __name__ == "__main__":
    main()
