# Job Intelligence & Weekly Review — build + handoff

Built from `CLAUDE-CODE-BRIEF.md` (the "Ross Built Cockpit — Job Intelligence & Weekly
Review" spec). Phase 0 was a discovery gate; the operator authorized building Phases 1–4
in one pass. This doc is the Phase 0 report **and** the record of what shipped, how it was
verified, and the one-time setup you still have to do yourself.

Date: 2026-07-01 · Supabase project `takewvlqgwpdbkvcwpvi` (shared by scraper + app).

---

## Phase 0 — what the repo actually is (confirmed against code + live DB)

1. **Stack.** `production-cockpit/` = Next.js **14.2.35**, App Router, React 18, Tailwind v4
   (+ shadcn/base-ui), `@supabase/supabase-js` (service-role, `no-store`), `@anthropic-ai/sdk`,
   `pg` (used for migrations), custom HMAC-cookie auth (not Supabase Auth), Resend for email.
   The root of the repo is a **Python transcript→Claude pipeline + generators**, not a scraper.
2. **The Buildertrend scraper is a *separate* sibling repo** (`C:\Users\Greg\buildertrend-scraper\`,
   `scrape_api.py`) — a JSON/API scraper (BT is a SPA now), **not** Playwright. The cockpit
   invokes it locally via `POST /api/bt/sync` which spawns the external script; that route
   **refuses to run on Vercel** (`process.env.VERCEL === "1"`), so scraping is local-only.
   Nothing long-lived stays up server-side — it's button-triggered + a 12h local schedule.
3. **Daily logs are real and working**, not stubbed: `daily_logs` = **306 rows** across 10
   jobs, keyed by a free-text `job_key` ("Krauss-427 South Blvd…"). Ingested by the BT sync
   route (upsert on `job_key+log_id`, manual-wins columns).
4. **POs are captured**: `purchase_orders` = **1288 rows** across 28 BT jobs (re-scraped
   2026-07-01). ⚠️ `po_line_items` = **0** — line-item ingestion is currently NOT running
   (STATE.md's 2,099 line items are gone); only PO headers are being pulled. Flag for the
   PO scraper owner.
5. **The old 503 / N+1 aggregation is not present** in the new surfaces — the Weekly hub and
   report use a handful of **batched** queries aggregated in memory (see below), never per-job
   loops. `job_summaries` already exists as a per-job rollup table.
6. **A job is a text slug** (`jobs.id` = "krauss"). The cross-system key that logs/POs carry is
   the free-text `job_key`; `lib/job-key.ts::jobKeyMatchesName` bridges them with a
   word-boundary match ("Clark" ≠ "Clarkson"). `jobs` had **no** email/BT-routing columns —
   added in migration 014 (below).
7. **Auth** is a custom HMAC-signed session cookie (`lib/auth.ts`, `middleware.ts`), plaintext
   seed passwords (internal MVP), PM scoping via `jobs.pm_id` + `canSeeJobByPm`. **No existing
   Microsoft/Graph integration** — Phase 1/4 Graph is net-new (the `email-intel/` service).

---

## What shipped

### DB — migration `scripts/migrations/014_job_intel_and_weekly_reports.sql` (APPLIED to prod)
- `jobs` += `pm_email`, `client_emails text[]`, `buildertrend_id`, `active`
  (backfilled: `pm_email` on 10 jobs from `user_overlay`, `buildertrend_id` on 11 from PO `bt_job_id`).
- `job_intel` — unified durable-intel store: `job_id` FK → `jobs.id`, `source` enum
  (`email|daily_log|po|manual`), `message_id` (unique-when-present, email dedupe), summary/detail/
  action_needed, manual-wins columns. **This is the spine Phase 1's email capture writes to.**
- `sync_state` — per-mailbox email watermark (recalculated absolutely).
- `weekly_reports` — the **draft→approved→sent** homeowner report, one per (job, week);
  `edited_body` (PM edits) wins over generated `body`.
- `report_feedback` — PM feedback per job, fed back into the next generation.
- `app_config` seeds — `WEEKLY_REPORT_MODEL`, `INTEL_EXTRACT_MODEL`, `INTEL_ANALYZE_MODEL`,
  `MEETING_CADENCE`, `REPORT_WEEK_START` (org-configurable, never hardcoded).

### App — the Weekly Review (Phases 1–3)
- **`/weekly`** — the hub. One row per job you can see (PM-scoped), showing this week's new
  signals, past-due work, and report status. Sorted attention-first. Batched queries only.
- **`/weekly/[job_id]`** — per job:
  - **Intel timeline** (Phase 1) — read-only, source-badged (email/daily_log/po/manual).
  - **Homeowner report** (Phase 3) — Generate a **DRAFT** (reuses the existing client-summary
    generation + captured intel + your stored feedback), **edit** any field, **Approve**
    (editing an approved report reverts it to draft), then **Copy for client** / **Mark as
    sent**. **Nothing is ever auto-sent.**
  - **Suggested to-dos** — proposes to-dos from open commitments + gaps + outstanding POs
    (with a `billing_ref` where the data allows). **Proposals only** — you accept each one into
    the live list (respecting "AI output is reviewed before it's real").
  - **Feedback** box — tunes the next draft.
- API routes under `app/v2/api/weekly/[job_id]/`: `generate`, `save`, `approve`, `mark-sent`,
  `feedback`, `generate-todos`. Nav: a **Weekly** link in the header.

### Email capture (Phases 1 & 4) — `email-intel/` (ready, runs locally, needs your Azure setup)
- Generalizes the prototype `capture.py`/`analyze.py`/`config.py`. Reads a PM's **sent** mail via
  Microsoft Graph, extracts durable intel with Claude, resolves a real `job_id`, writes `job_intel`.
- **Routing**: primary = match email participants against `jobs.client_emails`/`pm_email`
  (client address disambiguates the shared PM address); fallback = Claude-inferred name via the
  `job-key.ts` word-boundary rule; unresolved → stored with `job_id=null` for a human to re-route.
- **Two modes** (`AUTH_MODE`): `device` (Phase 1, your one mailbox, device-code login) and `app`
  (Phase 4, client-credentials over every PM mailbox, unattended). See `email-intel/SETUP.md`.

---

## One-time setup you must do (credential boundary — I can't do these)

1. **Populate the routing map.** Set `jobs.client_emails[]` (the homeowner addresses) and confirm
   `jobs.pm_email` for each active job. Without this, email routing falls back to name inference.
   (Do it in SQL or add an admin field — `pm_email` is already backfilled for 10 of 12 jobs;
   `fish` and `harllee` need a PM email, and every job needs client emails.)
2. **Azure app registration for Graph** (see `email-intel/SETUP.md` for exact clicks):
   - Phase 1: public client + **delegated** `Mail.Read` + admin consent → set `AZURE_CLIENT_ID`/
     `AZURE_TENANT_ID` → `python email-intel/capture.py` (browser login once) → your Fish emails
     land on the Fish page.
   - Phase 4: add **application** `Mail.Read` + admin consent + client secret → `AUTH_MODE=app`
     + `PM_MAILBOXES` → run unattended (Task Scheduler).
3. **Rotate the Supabase DB password** in root `.env` — it has been shared in chat before.

---

## Known gaps / follow-ups
- `po_line_items` ingestion is not currently running (headers only). Separate from this work.
- Email `job_intel` is empty until step 2 above; the timeline is currently seeded with 53
  `source='daily_log'` rows derived from real log notes so the feature is demonstrable now.
- Generated to-dos and reports are intentionally **not** auto-committed anywhere — human-gated.

## Verification (2026-07-01, local dev + live prod DB)
- `tsc --noEmit` clean; `npm test` 85/85 pass.
- Migration 014 applied + verified (all new tables/columns present).
- `/weekly` + `/weekly/krauss` render 200 with real data; PM gate denies cross-PM access
  (martin → krauss redirects, no data leak).
- Full generate → draft persisted (Krauss, week 2026-06-29; reasoned over 48% complete,
  7 logs, 6 intel items). `email-intel/routing.py` offline self-test passes.
