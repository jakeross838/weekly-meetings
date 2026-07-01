#!/usr/bin/env python3
"""Ross Built - Email Intel: CAPTURE  (Phases 1 & 4)

Reads PMs' SENT mail from Outlook via Microsoft Graph, extracts durable JOB
INTELLIGENCE with Claude (skipping logistics noise), resolves each email to a
REAL job, and stores it in Supabase `job_intel` with source='email'.

Two auth modes (config-driven AUTH_MODE), sharing all fetch/store logic:

  AUTH_MODE=device  (Phase 1, DEFAULT)  ->  python capture.py
     Device-code browser login once; reads YOUR OWN mailbox
     (/me/mailFolders/sentitems). Delegated Mail.Read.

  AUTH_MODE=app     (Phase 4)           ->  AUTH_MODE=app python capture.py
     Client-credentials (no user); loops over a list of PM mailboxes and reads
     each one's sent items (/users/{mailbox}/...). Application Mail.Read +
     admin consent. Runs UNATTENDED (e.g. Windows Task Scheduler). The mailbox
     list comes from PM_MAILBOXES, or is derived from DISTINCT jobs.pm_email.

JOB ROUTING (routing.py): each email is attached to a real jobs.id via, in order,
  1. exact address match of sender+to+cc against client_emails/pm_email, else
  2. Claude's inferred `project` name matched to a job name by the app's
     word-boundary prefix rule (ported from lib/job-key.ts), else
  3. job_id = None (still stored with `project` set for a human to re-route).
The resolved job_id is written AND the raw inferred name is kept in `project`.

Durability guarantees (carried over from the prototype):
  * per-mailbox watermark in sync_state (recalculated absolutely, never incremented)
  * dedupe on message_id (partial-unique index) via PostgREST upsert
  * cost guards: MAX_EMAILS_PER_RUN cap per mailbox, cheap extract model, retry-on-429
  * tool-free JSON extraction with one retry

Run:  python capture.py
"""

import json
import sys
import time
import datetime as dt

import requests

import config as cfg
import routing
from graph_client import (
    fetch_sent_since,
    get_token_app,
    get_token_device,
    parse_iso,
    to_graph_z,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


# ---------------------------------------------------------------------------
# Supabase (raw PostgREST + service key -- no heavy client dep)
# ---------------------------------------------------------------------------
def sb_headers():
    return {
        "apikey": cfg.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {cfg.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def sb_app_config(key):
    """Read one app_config value (org-configurable model names). None if absent."""
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
    except Exception as e:
        print(f"  (warn) could not read app_config[{key}]: {e}")
        return None


def load_jobs():
    """Load the jobs spine once for routing. All jobs (not just active) so intel
    on a recently-closed job still routes."""
    r = requests.get(
        f"{cfg.SUPABASE_URL}/rest/v1/jobs",
        headers=sb_headers(),
        params={"select": "id,name,pm_email,client_emails,active"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def distinct_pm_emails(jobs):
    """Distinct, order-preserving list of non-empty jobs.pm_email addresses."""
    seen, lower = [], set()
    for j in jobs:
        e = (j.get("pm_email") or "").strip()
        if e and e.lower() not in lower:
            seen.append(e)
            lower.add(e.lower())
    return seen


def get_watermark(mailbox_key):
    """Read this mailbox's watermark, or first-run default (DAYS_BACK_ON_FIRST_RUN)."""
    r = requests.get(
        f"{cfg.SUPABASE_URL}/rest/v1/sync_state",
        headers=sb_headers(),
        params={"mailbox": f"eq.{mailbox_key}", "select": "last_processed_at"},
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json()
    if rows:
        return to_graph_z(parse_iso(rows[0]["last_processed_at"]))
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=cfg.DAYS_BACK_ON_FIRST_RUN)
    return to_graph_z(start)


def set_watermark(mailbox_key, ts_iso):
    """Upsert the watermark: recompute + set ABSOLUTELY (never increment)."""
    requests.post(
        f"{cfg.SUPABASE_URL}/rest/v1/sync_state",
        headers={**sb_headers(), "Prefer": "resolution=merge-duplicates"},
        json={"mailbox": mailbox_key, "last_processed_at": ts_iso},
        timeout=30,
    ).raise_for_status()


def store(record, msg, job_id, created_by):
    """Insert the intel row, deduped on message_id. Writes the resolved job_id AND
    keeps Claude's raw inferred name in `project` for audit / unrouted triage."""
    summary = (record.get("summary") or msg.get("subject") or "").strip()
    if not summary:
        # summary is NOT NULL; if we truly have nothing, don't write a broken row.
        print("  (skip) relevant email had no summary; not storing")
        return False
    row = {
        "job_id": job_id,                      # resolved real jobs.id (or None -> unrouted)
        "source": "email",
        "message_id": msg["id"],               # dedupe key (partial-unique)
        "sent_at": msg.get("sentDateTime"),
        "project": record.get("project"),      # raw inferred name (audit trail)
        "intel_type": record.get("intel_type"),
        "summary": summary,
        "detail": record.get("detail"),
        "action_needed": record.get("action_needed"),
        "recipients": record.get("recipients"),
        "created_by": created_by,
    }
    requests.post(
        f"{cfg.SUPABASE_URL}/rest/v1/job_intel",
        headers={**sb_headers(), "Prefer": "resolution=merge-duplicates"},
        params={"on_conflict": "message_id"},  # upsert against the message_id index
        json=row,
        timeout=30,
    ).raise_for_status()
    return True


# ---------------------------------------------------------------------------
# Extraction (tool-free JSON with one retry) -- prompt preserved from prototype
# ---------------------------------------------------------------------------
EXTRACT_SYSTEM = """You analyze an email SENT by a project manager at a luxury coastal custom-home builder (Ross Built).
Decide whether it contains DURABLE JOB INTELLIGENCE worth remembering, then extract it.

KEEP (relevant=true) if it contains any of:
- a commitment/promise made (to a client, subcontractor, vendor, or inspector)
- a decision made or direction given
- a client approval, selection, or answer
- a schedule change WITH a cause or consequence
- an unresolved issue, risk, or defect
- a scope change, change-order, or money/cost discussion

DISCARD (relevant=false):
- pure logistics ("running late", "on my way", "see attached" with no substance)
- simple acknowledgments / thanks / pleasantries
- scheduling pings with no decision
- automated or forwarded newsletters/notifications

Return ONLY a JSON object, no markdown, no prose:
{"relevant": true|false,
 "project": "<job name if inferable, else null>",
 "intel_type": "commitment|decision|client_approval|schedule_change|issue|scope_change|cost|other",
 "summary": "<one line a PM would want to recall>",
 "detail": "<1-3 sentences with specifics: amounts, dates, names>",
 "action_needed": "<open action if any, else null>"}"""


def extract(msg, model):
    """Ask Claude whether the email holds durable intel and extract it. Returns a
    dict; {"relevant": False} on non-relevant or any parse/format failure."""
    recipients = ", ".join(
        (r.get("emailAddress") or {}).get("address", "")
        for r in msg.get("toRecipients", [])
    )
    body = (msg.get("body") or {}).get("content") or msg.get("bodyPreview", "")
    user = (
        f"SUBJECT: {msg.get('subject', '')}\n"
        f"TO: {recipients}\n"
        f"SENT: {msg.get('sentDateTime', '')}\n\n"
        f"BODY:\n{body[:6000]}"
    )
    payload = {
        "model": model,
        "max_tokens": 400,
        "system": EXTRACT_SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }
    for attempt in range(2):
        r = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": cfg.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if r.status_code == 429 and attempt == 0:
            time.sleep(5)
            continue
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        text = (
            text.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        try:
            rec = json.loads(text)
        except json.JSONDecodeError:
            return {"relevant": False}
        rec["recipients"] = recipients
        return rec
    return {"relevant": False}


# ---------------------------------------------------------------------------
# Per-mailbox processing (shared by both auth modes)
# ---------------------------------------------------------------------------
def process_mailbox(token, graph_mailbox, watermark_key, jobs, extract_model):
    """Scan one mailbox's sent items after its watermark, extract + route + store,
    then advance that mailbox's watermark absolutely. `graph_mailbox` is "me" for
    device mode, or an address for app mode; `watermark_key` keys the sync_state row.
    """
    watermark = get_watermark(watermark_key)
    print(f"\n[{watermark_key}] scanning sent mail after {watermark} ...")
    msgs = fetch_sent_since(token, graph_mailbox, watermark, cfg.MAX_EMAILS_PER_RUN)
    print(f"[{watermark_key}] fetched {len(msgs)} message(s).")

    stored = skipped = unrouted = 0
    max_seen = parse_iso(watermark)
    for m in msgs:
        rec = extract(m, extract_model)
        if rec.get("relevant"):
            job_id, reason = routing.resolve_job_id(m, rec, jobs, log=lambda s: print("  " + s))
            if job_id is None:
                unrouted += 1
            if store(rec, m, job_id, created_by=watermark_key):
                stored += 1
                tag = job_id or "UNROUTED"
                print(f"  + [{rec.get('intel_type')}] {tag} ({reason}): {rec.get('summary')}")
        else:
            skipped += 1
        d = parse_iso(m["sentDateTime"])
        if d > max_seen:
            max_seen = d

    if msgs:
        set_watermark(watermark_key, to_graph_z(max_seen))
    print(
        f"[{watermark_key}] done. stored {stored} ({unrouted} unrouted), "
        f"skipped {skipped} (noise). watermark now {to_graph_z(max_seen)}."
    )
    return stored, skipped, unrouted


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------
def _require(pairs):
    missing = [name for name, val in pairs if not val]
    if missing:
        sys.exit(
            "Missing required config: "
            + ", ".join(missing)
            + "\nSet them in the repo-root .env or your environment (see config.example.py / SETUP.md)."
        )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    _require([
        ("SUPABASE_URL", cfg.SUPABASE_URL),
        ("SUPABASE_SERVICE_ROLE_KEY", cfg.SUPABASE_SERVICE_KEY),
        ("ANTHROPIC_API_KEY", cfg.ANTHROPIC_API_KEY),
        ("AZURE_CLIENT_ID", cfg.AZURE_CLIENT_ID),
        ("AZURE_TENANT_ID", cfg.AZURE_TENANT_ID),
    ])

    # Org-configurable model: Supabase app_config -> env -> prototype default.
    extract_model = cfg.pick_model(
        sb_app_config("INTEL_EXTRACT_MODEL"),
        cfg.EXTRACT_MODEL_ENV,
        cfg.DEFAULT_EXTRACT_MODEL,
    )

    jobs = load_jobs()
    print(f"AUTH_MODE={cfg.AUTH_MODE}  extract_model={extract_model}  jobs_loaded={len(jobs)}")
    if not any((j.get("client_emails") or j.get("pm_email")) for j in jobs):
        print("  (warn) no jobs have client_emails/pm_email set -- routing will rely on "
              "name inference only. Populate the routing map (see SETUP.md).")

    totals = [0, 0, 0]
    if cfg.AUTH_MODE == "app":
        # Phase 4: unattended, multi-mailbox, client-credentials.
        _require([("AZURE_CLIENT_SECRET", cfg.AZURE_CLIENT_SECRET)])
        mailboxes = cfg.PM_MAILBOXES or distinct_pm_emails(jobs)
        if not mailboxes:
            sys.exit("AUTH_MODE=app but no mailboxes: set PM_MAILBOXES or populate jobs.pm_email.")
        print(f"App mode over {len(mailboxes)} mailbox(es): {', '.join(mailboxes)}")
        token = get_token_app(cfg.AZURE_CLIENT_ID, cfg.AZURE_TENANT_ID, cfg.AZURE_CLIENT_SECRET)
        for mb in mailboxes:
            s, k, u = process_mailbox(token, mb, mb, jobs, extract_model)
            totals[0] += s; totals[1] += k; totals[2] += u
    else:
        # Phase 1: interactive device login, single (own) mailbox.
        token = get_token_device(cfg.AZURE_CLIENT_ID, cfg.AZURE_TENANT_ID)
        s, k, u = process_mailbox(token, "me", cfg.MAILBOX_LABEL, jobs, extract_model)
        totals = [s, k, u]

    print(f"\nAll done. Stored {totals[0]} ({totals[2]} unrouted), skipped {totals[1]} (noise).")


if __name__ == "__main__":
    main()
