# Ross Built Production Cockpit — BLUEPRINT

A complete extraction of every feature, data structure, integration, AI prompt,
and hard-won lesson in the Ross Built production cockpit. This document is the
operational truth for the system as of **2026-05-27**. If you've never seen
this codebase, you can read this end-to-end and have a fair shot at rebuilding
it cleanly — preserving the logic that took months of meeting cycles + real
data to get right.

**Audience:** a senior engineer (or a fresh AI on claude.ai) tasked with
either understanding, maintaining, or rewriting the cockpit. Each § is
self-contained enough to skim independently, with cross-references where
needed.

**Maintenance rule:** any PR adding a route, table, or external integration
**must** update the relevant § in the same commit. Otherwise this document
silently drifts and becomes lies.

---

## Table of Contents

1. **§1 PURPOSE** — what the system is, who uses it, non-goals
2. **§2 ARCHITECTURE** — stack, repo layout, env vars, runtime split
3. **§3 DATA MODEL** — every Supabase table with columns, rules, manual-wins
4. **§4 AUTH & VISIBILITY** — HMAC cookie, seed users, `jobs.pm_id` rule
5. **§5 PAGES** — every page route and its interactive elements
6. **§6 API ROUTES** — every endpoint with body, auth, writes, cache invalidation
7. **§7 AI CALLS** — the 4 Claude tool-use sites verbatim
8. **§8 PYTHON PIPELINE** — process.py + 3-call brain + generators
9. **§9 BUILDERTREND SCRAPER** — scrape_api/po/co, BT JSON API contract
10. **§10 END-TO-END FLOWS** — 8 critical user-action-to-DB-write narratives
11. **§11 GOTCHAS** — every learned-the-hard-way truth
12. **§12 FORWARD IDEAS** — placeholder for Jake's next requests

Footer: **How to use this doc** — guidance for a receiving AI session.

---

## §1 PURPOSE

**What this system is.** A mobile-first, single-page-per-job operating
document that runs Ross Built's weekly Monday meetings and the daily work
between them. It ingests every form of information about each active home:
meeting transcripts (Plaud voice recorder), Buildertrend daily logs and
photos, purchase orders, change orders, pay app G703 line items. It
cross-checks claims, surfaces who-owes-what-by-when, and shows one
trustworthy tappable list everyone (office screen, Jake's iPad, PM's phone)
works off of.

**Who uses it.**
- **Jake Ross** — Director of Construction. Admin role. Sees every job in the
  portfolio. Owns the cockpit, makes structural decisions, runs Monday
  meetings.
- **5 Project Managers** — Bob Mozine, Nelson Belanger, Lee Worthy, Martin
  Mannix, Jason Szykulski (each `pmId` is the lowercase first name). Each PM
  sees only the jobs where `jobs.pm_id` matches their `pmId`. No cross-PM
  visibility by default.
- **Office / admin staff** — currently no logins built for them; mentioned in
  the original /login wireframe as a future profile.

**What it does in one paragraph.** A construction PM job has hundreds of
moving parts. The cockpit is the single place where commitments made in
meetings are tracked, daily progress from the field is captured, financial
reality (POs, change orders, pay app billing) is reconciled, and AI
summarizes everything into a paragraph anyone can read on a phone. Every
piece of data has a single source of truth (BT scraper for daily logs and
financials; transcripts for commitments; Jake/PM manual edits override
anything when they touch a row). The Monday meeting consists of opening
`/meeting`, walking each job top-to-bottom, marking each one "covered" as you
discuss it.

**What it explicitly is NOT** (these are non-goals as of 2026-05-27):
- **Not a write-back to Buildertrend.** Read-only from BT. Always.
- **Not a schedule forecaster** — no PPC%, no Gantt, no 2/4/8-week look-ahead
  predictions. Surfaces today's state from the data we have; doesn't invent
  future numbers.
- **Not a client-facing portal.** Internal tool for the Ross Built team.
  Clients see the rendered weekly summary text Jake/PMs paste into email; no
  client logins.
- **Not SMS / email ingestion.** Phase 2 territory.
- **Not real-time multi-cursor collaboration.** Mobile-first read + a small
  set of write actions; not Figma.
- **Not the live Monday packet.** The old Python→PDF pipeline
  (`monday-binder/` + `process.py`) still produces the printed Monday packet
  as a fallback. The cockpit is replacing it, but the binder is the safety
  net until the cockpit covers 100% of meeting use.

**Vision quote.** From the user, repeatedly: *"One mobile-first, dead-simple
interactive document per job that runs the Monday meetings."* Simplicity and
mobile are the point — every UI decision optimizes for "PM with a phone in
the field, one thumb."

**Two parallel data models** during the v1→v2 transition:
- **v1 (live, in production)** — `todos` table. Surfaced on `/`, `/subs`,
  `/sub/[id]`, `/v2/job/[id]` (merged with items). Written by `/import` and
  the AI extractor.
- **v2 (the newer "brain")** — `items` table + `ingestion_events` +
  `proposed_changes` + `decisions` + `open_questions`. Routed through
  `/v2/upload` → `/v2/review/[id]` → `/v2/api/review/[id]/commit`. The
  3-call Python brain (Extractor / Reconciler / Auditor) runs offline and
  produces the structured claims that land here.

The cockpit reads from both. The cutover plan is to deprecate v1 once v2
fully covers it.

---


---

## §2 ARCHITECTURE

### Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14.2.35 App Router, React 18, TypeScript 5, Tailwind v4 (`@tailwindcss/postcss`), `@base-ui/react` primitives, lucide-react icons |
| Backend | Next.js server components + route handlers (Node runtime), Edge runtime for middleware only |
| Auth | HMAC-SHA256 cookie session (see §4). No third-party provider (Auth0/Clerk/Supabase Auth). |
| DB | Supabase Postgres (project `takewvlqgwpdbkvcwpvi`, region **us-west-2**) accessed via `@supabase/supabase-js` v2.105.x service-role server-side only |
| Migrations | Raw SQL applied via direct `pg` connection through Supavisor pooler (see below); also `/admin/migrate` UI runner |
| AI | Anthropic Claude — `claude-opus-4-7`, all 4 call sites use tool-use for structured JSON |
| Scrapers | Python 3.13 + Playwright + requests, lives in separate repo at `C:\Users\Greg\buildertrend-scraper\`, spawned by cockpit as child process |
| Hosting | Vercel (Node runtime, `force-dynamic` on data-loading routes) |
| Local dev | `cd production-cockpit && npm run dev` on http://localhost:3000 |

### Repo layout

```
weekly-meetings/                          # GitHub: jakeross838/weekly-meetings, public
├── production-cockpit/                   # ← Vercel Root Directory
│   ├── app/                              # Next.js App Router
│   ├── components/                       # Reusable client components
│   ├── lib/                              # auth.ts, supabase.ts, types.ts, …
│   ├── middleware.ts                     # Auth gate (Edge runtime)
│   ├── .env.local                        # GITIGNORED — SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, AUTH_SECRET, ANTHROPIC_API_KEY
│   ├── .vercel/project.json              # Links to Vercel project (NOT committed in current repo state)
│   └── package.json
├── process.py                            # Python pipeline entry
├── scripts/                              # Python ETL + 3-call brain + generators
│   ├── brain/{extractor,reconciler,auditor}.py
│   ├── parsers/pay_app_parser.py
│   ├── ingest_*.py
│   └── run_weekly_pipeline.py
├── generators/                           # g1/g2/g3 + commitment tracker
├── binders/                              # GITIGNORED — per-PM JSON action item state
├── data/, transcripts/, api-responses/   # GITIGNORED — sensitive client data
├── monday-binder/                        # The legacy Python→PDF system (still alive as fallback)
├── RUN_THIS_IN_SUPABASE.sql              # Canonical migrations (mirrors MIGRATIONS_SQL)
├── BLUEPRINT.md                          # THIS FILE
├── STATE.md, HANDOFF.md, HOW-IT-WORKS.md # Operational narrative
├── v2-plan.md                            # Original vision doc
├── v1-known-issues.md                    # Parked v1 bugs
└── .env                                  # GITIGNORED — SUPABASE_DB_PASSWORD, ANTHROPIC_API_KEY, BT creds (in keyring instead)
```

And separately, on Jake's Windows machine only (not in the repo):
```
C:\Users\Greg\buildertrend-scraper\       # Python + Playwright BT scraper
├── scrape_api.py, scrape_po.py, scrape_co.py
├── auth.py                               # Windows keyring credential storage
├── bt_session.py                         # Playwright session manager
├── jobs.py                               # JOB_NAME_MAP mirror of constants.py
└── .session/state.json                   # Cached Playwright auth state (gitignored — not in any repo)
```

### Environment variables

Per environment:

**`production-cockpit/.env.local` + Vercel project env (Production / Preview / Development):**
- `SUPABASE_URL` — `https://takewvlqgwpdbkvcwpvi.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY` — server-only, never expose to client
- `AUTH_SECRET` — HMAC key for session cookies. 64 char base64url recommended. Must be set in Vercel for all 3 environments; without it, dev fallback `"ross-built-dev-secret-please-change-me-now"` is used and a warning fires.
- `ANTHROPIC_API_KEY` — for the 4 Claude call sites
- `BT_SCRAPER_DIR` — optional override for where the Python scraper lives (default `C:\Users\Greg\buildertrend-scraper`, local-only)
- `SUPABASE_DB_PASSWORD` — optional, used by `/api/admin/run-migrations` if not passed in the request body

**Root `.env` (Python pipeline + migrations, gitignored):**
- `ANTHROPIC_API_KEY`
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_DB_PASSWORD` — for direct `pg` migrations
- Buildertrend credentials live in **Windows Credential Manager via Python `keyring`** under service name `buildertrend-scraper`, NOT in `.env`. Set with `python auth.py set` (the one step the user does themselves; never accept BT password through chat — see §11).

### Runtime split (important)

Two runtimes coexist in the cockpit, and the difference is load-bearing:

- **Node.js runtime** (default for pages + route handlers under `app/`). Has
  access to `node:crypto`, filesystem, `child_process.spawn`, full Supabase
  SDK. This is where 99% of cockpit code runs.
- **Edge runtime** (only middleware). No `node:crypto` — must use Web Crypto
  API (`crypto.subtle`). No filesystem. Limited package compatibility. This
  is why `lib/auth.ts` (Node-only) and `lib/auth-constants.ts` (Edge-safe
  shared) are split — middleware can only import from the constants file.
  See §4 for the BufferSource cast gotcha and §11.

### Database access patterns

- **From cockpit (page render / API routes)**: `supabaseServer()` factory in
  `lib/supabase.ts` returns a `@supabase/supabase-js` client created with the
  service-role key. Reads use `cache: "no-store"` to prevent Next's Data
  Cache from serving stale rows.
- **From migrations**: direct `pg` connection through Supavisor pooler.
  Connection host **must** match project region — for this project that's
  `aws-1-us-west-2.pooler.supabase.com`. Transaction mode (port `6543`)
  works; session mode (port `5432`) rejects the password for unclear
  reasons. User `postgres.takewvlqgwpdbkvcwpvi`. Password from
  `SUPABASE_DB_PASSWORD`.
- **From Python**: `psycopg2` direct connection using the same pooler + DB
  password.

The service-role REST API **cannot run DDL** — only CRUD. Schema changes
always go through the migrate runner or a pasted SQL block in Supabase
Studio.

### Deployment

- **GitHub repo**: `jakeross838/weekly-meetings`, branch `main`, public
- **Vercel project (the real one)**: `production-cockpit`, project id
  `prj_q8LShfLv16TAowa8deF3Du3GzG9O`, team
  `team_3Zx8Ov6Cq8cykl2B8qBUIorI`, root directory `production-cockpit`. URL:
  `https://production-cockpit.vercel.app`.
- **Vercel project (the cosmetic duplicate)**: `weekly-meetings`. Same
  GitHub repo, root directory at repo root (where there's no app). Always
  shows red ✗ on commits. **Purely cosmetic**. See §11 — do NOT add a
  repo-root `vercel.json` to "fix" the red ✗; it will override the real
  project's build and the live site will serve a placeholder.
- **Auto-deploy**: every push to `main` triggers a Vercel build. Failed
  builds keep the previous successful deploy live (so the site never goes
  down, but env-var-dependent fixes silently don't ship until a build
  succeeds). The CI keeps the alias on the last green build until a new
  green build comes in.
- **Auto-commit hook** (`.claude/settings.local.json`) auto-commits pending
  changes at end of each turn — commit-only, never pushes. Pushing is
  always manual.

### Manual-wins data model

Every scraped table follows the same pattern so user edits survive the next
scrape:

| Column | Purpose |
|---|---|
| `manually_edited_fields text[]` | Names of columns the user has overridden. The upserter skips these on next scrape. |
| `manually_edited_at timestamptz` | When the edit happened |
| `hidden boolean` | Soft delete; the upserter never un-hides |
| `hidden_at timestamptz` | When hidden |

Applies to: `purchase_orders`, `po_line_items`, `daily_logs`, `change_orders`.
Native (non-scraped) tables (`todos`, `items`) hard-delete instead. The
`subs` table is insert-only from the scraper so it gets `hidden` but no
`manually_edited_fields`. See §3 for column-level detail and §11 for the
"filter `hidden=false` everywhere" gotcha.

### How an AI rebuilding this should sequence work

1. Schema first (§3) — Supabase tables + manual-wins columns.
2. Auth (§4) — middleware + cookie + seed users + Supabase overlay.
3. Pages (§5) skeleton — server components with `force-dynamic`, no AI yet.
4. APIs (§6) for CRUD — admin/users, admin/jobs, complete/uncomplete, edit-todo.
5. BT scraper integration (§9) — the spawn-Python pattern.
6. AI calls (§7) last — they're nice-to-have, not load-bearing.
7. Python pipeline (§8) is largely independent and can be rebuilt or kept as-is.

---


---

## §3 DATA MODEL

The cockpit lives on a single Supabase Postgres project (`takewvlqgwpdbkvcwpvi`, region `us-west-2`). All tables sit in the `public` schema with RLS intentionally OFF — the Next.js server is the trust boundary, the `service_role` key is server-only, and per-job visibility is enforced at render time by `lib/auth.ts:canSeeJobByPm` (see §4). No FK exists between scraped tables (POs, daily logs) and `jobs.id` — they join by `job_key` (`Job-Address` prefix matching), which is messy but BT-driven.

Canonical DDL lives in two places that MUST stay in sync:
- `RUN_THIS_IN_SUPABASE.sql` — paste-in-the-Studio mirror, last synced 2026-05-20.
- `production-cockpit/app/api/admin/run-migrations/route.ts` (`MIGRATIONS_SQL` constant) — what the `/admin/migrate` button runs over a direct pg pooler connection.

Older one-shot DDL also lives in `scripts/migrations/00*.sql` (Gate 1A–2B, applied historically). The migrations route only covers the F-series additions (F3–F9, plus PO/CO scraping). Together they form the full schema.

TS shapes for the few tables the UI touches strongly are in `production-cockpit/lib/types.ts`. Most rows are read as `Record<string, unknown>` because the schema evolves faster than types.

> **Gotcha — jsonb arrays:** PostgREST's `.overlaps()` operator does NOT work on `jsonb` columns (only on Postgres array types like `text[]`). For `crews_present`, `absent_crews`, `parent_group_activities`, etc., use per-name containment filters: `.filter("crews_present", "cs", JSON.stringify([name]))`. See `feedback_supabase_jsonb_no_overlaps.md`.

---

### jobs

The job catalog. One row per active or pre-construction project. `id` is a lowercase slug (`pou`, `krauss`, `fish`) used as the cross-table join key. `pm_id` is the single source of truth for visibility (§4).

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | text | NO | — | Lowercase slug PK (`pou`, `krauss`, `fish`). Used as `job_id` everywhere. |
| name | text | YES | — | Display name (`Pou`, `Krauss`). Used as the `job` string on legacy `todos` rows + as the `job_key` prefix on scraped tables. |
| address | text | YES | — | Street address. Concatenated into `bt_long_key` for BT matching. |
| pm_id | text | YES | — | FK → `pms.id`. The visibility key — non-admins only see jobs where this equals their `pmId`. |
| phase | text | YES | — | Free-text phase (`pre-construction`, `framing`, etc.). |
| status | text | YES | — | Free-text status. |
| target_co_date | date | YES | — | Target certificate-of-occupancy date. |
| gp_pct | numeric | YES | — | Gross profit %. |
| contract_amount | numeric | YES | — | Contract dollar amount. |
| bt_long_key | text | YES | — | `<Name>-<Address>` — the prefix the BT scraper writes to `job_key` columns. |
| created_at | timestamptz | NO | now() | — |
| updated_at | timestamptz | NO | now() | — |

- **PK:** `id`
- **Writes:** seeded by `scripts/migrations/001_create_jobs_table.sql`; updated via `POST/PATCH/DELETE /api/admin/jobs/route.ts` (admin only).
- **Reads:** every page — `/` (home dashboard), `/meeting`, `/import`, `/admin/jobs`, `/admin/users`, `/v2/job/[job_id]`, `/v2/upload`, `/sub/[id]`, `/v2/review/[id]`.
- **Source-of-truth:** human-curated. Never overwritten by any scraper.

### todos

Live action-item table (v1). The cockpit still reads/writes this — `items` (§v2) was supposed to replace it but the v1 path is what the home, meeting, sub, and import pages actually drive. Inferred shape (not in migrations):

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| pm_id | text | YES | — | Which PM owns it. |
| job | text | YES | — | Job NAME (not id) — historical free text. |
| title | text | NO | — | Action item title. Forbidden from carrying relative dates (see `lib/scrub-relative-dates.ts`). |
| edited_title | text | YES | — | Human-edited title that supersedes `title`. UI prefers `edited_title ?? title`. |
| edited_at | timestamptz | YES | — | When `edited_title` was last set. |
| due_date | date | YES | — | Hard due date. |
| priority | text | YES | — | `URGENT \| HIGH \| NORMAL` |
| status | text | NO | NOT_STARTED | `NOT_STARTED \| IN_PROGRESS \| BLOCKED \| COMPLETE` (see `OPEN_STATUSES` in `types.ts`). |
| previous_status | text | YES | — | Snapshot taken before transitions so `uncomplete` can restore. |
| type | text | YES | — | `SELECTION \| CONFIRMATION \| PRICING \| SCHEDULE \| CO_INVOICE \| FIELD \| FOLLOWUP` |
| category | text | YES | — | `SELECTION \| SCHEDULE \| PROCUREMENT \| SUB-TRADE \| CLIENT \| QUALITY \| BUDGET \| ADMIN` |
| sub_id | text | YES | — | FK → `subs.id`. Resolved via `subs.aliases` matching during transcript import. |
| source_transcript | text | YES | — | Original transcript file id. |
| source_excerpt | text | YES | — | The ≤200-char verbatim transcript quote that grounds the item (§7 honesty gate). |
| created_at | timestamptz | NO | now() | — |
| completed_at | timestamptz | YES | — | When status flipped to COMPLETE. |

- **Writes:** `/api/save-extracted-todos`, `/api/complete`, `/api/uncomplete`, `/api/edit-todo`, `/api/subs/[id]/delete` (cascades), `/api/todos/[id]/delete`.
- **Reads:** `/`, `/meeting`, `/subs`, `/sub/[id]`, `/import`, `/v2/job/[job_id]` (alongside `items`), `/api/jobs/[id]/refresh-summary`, `/api/jobs/[id]/client-summary`.
- **Source-of-truth:** human + AI extraction. AI fills the row at import; humans then edit/complete it. `edited_title` is the protect-from-AI-rewrite mechanism.
- **Gotcha:** the `job` column carries `jobs.name`, not `jobs.id`. Queries join `.eq("job", job.name)`.

### items

v2 brain output — the unified action/observation/flag table behind `/v2/job/[job_id]` and the review queue. Replaces `todos` conceptually but BOTH still exist in prod (the F3–F9 migration applied 2026-05-20 — see `STATE.md`). Defined in `scripts/migrations/004_create_items_decisions_questions_tables.sql`, extended by 005, 006, 010.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| human_readable_id | text | NO unique | — | `KRAU-001` style — what humans cite. |
| job_id | text | NO | — | FK → `jobs.id`. |
| pm_id | text | YES | — | FK → `pms.id`. |
| pay_app_line_item_id | uuid | YES | — | FK → `pay_app_line_items.id` (for budget-tied items). |
| type | text | NO | — | `action \| observation \| flag` |
| title | text | NO | — | |
| detail | text | YES | — | Longer prose. |
| sub_id | text | YES | — | FK → `subs.id`. |
| owner | text | YES | — | Free text. |
| target_date | date | YES | — | |
| target_date_text | text | YES | — | Original (pre-resolution) phrase. |
| status | text | NO | open | `open \| in_progress \| complete \| blocked \| cancelled` |
| priority | text | YES | normal | `urgent \| normal` |
| confidence | text | YES | medium | `high \| medium \| low` |
| source_meeting_id | uuid | YES | — | FK → `meetings.id`. |
| carryover_count | int | YES | 0 | Times this item was rolled forward without resolution. |
| previous_status | text | YES | — | Snapshot for the unhide / uncomplete flows. |
| manually_edited_at | timestamptz | YES | — | Manual-wins timestamp. |
| manually_edited_fields | text[] | YES | — | Columns the AI must not clobber on next import. |
| audit_state | text | YES | — | `clean \| needs_retry \| needs_review` (Auditor verdict). |
| audit_issues | jsonb | YES | '[]' | Per-item issue records. |
| actionability | text | YES | — | `actionable \| signal` (Gate 2A.5 strict classifier). |
| category | text | YES | — | Matches the `todos.category` enum (Gate 1E addendum, migration 010). |
| completed_at | timestamptz | YES | — | |
| completed_by | text | YES | — | |
| completion_basis | text | YES | — | Why marked complete. |
| created_at | timestamptz | YES | now() | — |
| updated_at | timestamptz | YES | now() | — |

- **PK:** `id`. Unique: `human_readable_id`.
- **Writes:** `/v2/api/review/[ingestion_event_id]/commit` (the only entry point — items are CREATED by accepting `proposed_changes`), plus `/v2/api/items/[item_id]/{edit,complete,uncomplete,delete,convert-to-action}`.
- **Reads:** `/v2/job/[job_id]`, `/v2/review/*`.
- **Manual-wins:** `manually_edited_fields` lists columns that future Reconciler runs are forbidden to overwrite. `previous_status` lets unhide restore the prior state.

### daily_logs

Buildertrend daily-log entries. `job_key` is the BT-side `<Name>-<Address>` string (or just the job name — both prefixes exist), so reads use `.ilike("job_key", \`${job.name}%\`)`. Defined initially in migration 009, then extended for `parent_group_activities` (011), `crew_counts`/`inspections`/`photo_urls`/`photo_summary` (F3/F6/F8), and `manually_edited_fields`/`hidden` (manual-wins).

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| job_key | text | NO | — | `<Name>-<Address>` from BT. |
| log_id | text | YES | — | BT log id — UNIQUE per `(job_key, log_id)`. |
| log_date | date | YES | — | Parsed from the BT date string. |
| crews_present | jsonb | NO | '[]' | Array of crew name strings. Matched against `subs.name` + `subs.aliases`. |
| absent_crews | jsonb | NO | '[]' | Array of no-show crews. |
| parent_group_activities | jsonb | NO | '[]' | BT activity-bucket tags (`["Stucco Scratch", "Exterior Paint"]`). |
| daily_workforce | int | YES | — | Headcount. |
| weather_high | int | YES | — | |
| weather_low | int | YES | — | |
| activity | text | YES | — | One-line activity summary. |
| notes | text | YES | — | PM notes (full). |
| crew_counts | jsonb | NO | '{}' | `{ "Crew Name": int }` — F3. |
| inspections | jsonb | NO | '[]' | Array of inspection records — F6. |
| photo_urls | jsonb | NO | '[]' | Array of URLs OR absolute local paths (`C:\...`) the scraper saved. |
| photo_summary | jsonb | YES | — | AI vision output (see §7). |
| photo_summary_at | timestamptz | YES | — | When the vision call ran. |
| enriched_at | timestamptz | YES | — | When BT's enrichment finished. |
| source | text | YES | 'bt_scraper' | Where the row came from. |
| manually_edited_fields | text[] | NO | '{}' | Manual-wins. |
| manually_edited_at | timestamptz | YES | — | |
| hidden | boolean | NO | false | Soft-delete. UI filters `hidden=false`. |
| hidden_at | timestamptz | YES | — | |
| inserted_at | timestamptz | NO | now() | — |

- **PK:** `id`. UNIQUE `(job_key, log_id)` lets the BT upload upsert idempotently.
- **GIN indexes** on `absent_crews`, `crews_present`, `parent_group_activities`, `crew_counts`, `inspections` for fast jsonb containment.
- **Writes:** `/v2/api/daily-logs/upload` (BT scraper POSTs the `{ byJob }` payload); `/v2/api/daily-logs/[id]/{edit,delete}`; `/v2/api/daily-logs/extract-photos` (writes `photo_summary` + `photo_summary_at`).
- **Reads:** `/sub/[id]` (no-show + activity tally), `/v2/job/[job_id]` (recent activity), `/api/jobs/[id]/refresh-summary` (last 30 days), `/api/jobs/[id]/client-summary`.
- **Source-of-truth:** BT scraper. Manual edits protected via `manually_edited_fields`; deletes via `hidden=true` (the upload route NEVER un-hides — see `ensureSubsForCrews` pattern; uploads filter out hidden rows before upserting).
- **Gotcha:** `.overlaps()` does NOT work on `crews_present`/`absent_crews`/`parent_group_activities` (they're jsonb). Use `.filter("crews_present", "cs", JSON.stringify([name]))` for containment.

### job_summaries

Per-job AI summary documents — one row per refresh, history kept (so future diffs are possible). Powers the big "Generate Summary" panel on `/v2/job/[id]`.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| job_id | text | NO (FK→jobs.id, ON DELETE CASCADE) | — | |
| generated_at | timestamptz | NO | now() | |
| summary | jsonb | NO | — | The structured Claude output (see §7). |
| last_data_through | date | YES | — | Most recent `daily_logs.log_date` considered. |
| log_count | int | NO | 0 | |
| photo_count | int | NO | 0 | |
| open_todo_count | int | NO | 0 | |
| done_todo_count | int | NO | 0 | |
| model | text | YES | — | e.g. `claude-opus-4-7` |
| elapsed_ms | int | YES | — | |

- **Writes:** `POST /api/jobs/[id]/refresh-summary` only.
- **Reads:** `/v2/job/[job_id]` selects the latest row by `generated_at DESC limit 1`.
- **Index:** `job_summaries_job_recent_idx (job_id, generated_at DESC)`.
- **Source-of-truth:** AI output, manual-edit not supported (history kept; just refresh to overwrite the latest).

### purchase_orders

PO grid scraped from Buildertrend's `/api/PurchaseOrders`. Joins to jobs by `job_key` (BT-side `<Name>-<Address>`), not by `jobs.id`.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| bt_po_id | bigint | NO unique | — | BT's PO id — the upsert key. |
| job_key | text | NO | — | BT-side job string. |
| bt_job_id | bigint | YES | — | |
| po_number | text | YES | — | |
| title | text | YES | — | |
| vendor | text | YES | — | |
| bt_vendor_id | bigint | YES | — | |
| approval_status | text | YES | — | |
| work_status | text | YES | — | |
| paid_status | text | YES | — | |
| is_bill | boolean | NO | false | |
| cost | numeric | YES | — | |
| amount_paid | numeric | YES | — | |
| amount_remaining | numeric | YES | — | Committed-but-unpaid balance. |
| pct_paid | numeric | YES | — | |
| pct_remaining | numeric | YES | — | |
| pct_billed | numeric | YES | — | |
| cost_codes | jsonb | NO | '[]' | |
| date_added | date | YES | — | |
| manually_edited_fields | text[] | NO | '{}' | |
| manually_edited_at | timestamptz | YES | — | |
| hidden | boolean | NO | false | Soft-delete. |
| hidden_at | timestamptz | YES | — | |
| scraped_at | timestamptz | NO | now() | |

- **PK:** `id`. Unique `bt_po_id`. Index `purchase_orders_job_idx (job_key)`.
- **Writes:** `/v2/api/purchase-orders/upload` (BT scraper), `/v2/api/purchase-orders/[id]/edit`, `/v2/api/purchase-orders/[id]/delete`.
- **Reads:** `/v2/job/[job_id]`, `/api/jobs/[id]/client-summary` (commitment rollup), home dashboard.
- **Manual-wins:** edit any displayed column → it goes into `manually_edited_fields` and the scraper's `poRow()` skips that column on next upsert. Delete → `hidden=true`. The upload route does NOT include `hidden` or `manually_edited_*` in the upsert payload, so re-scraping never un-hides.

### po_line_items

PO line items — one row per BT lineItem under a PO. Cascades from `purchase_orders`.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| po_id | uuid | NO (FK→purchase_orders.id ON DELETE CASCADE) | — | |
| bt_line_item_id | bigint | YES | — | Part of upsert key. |
| cost_code | text | YES | — | |
| title | text | YES | — | |
| description | text | YES | — | |
| quantity | numeric | YES | — | |
| unit_cost | numeric | YES | — | |
| amount | numeric | YES | — | |
| amount_paid | numeric | YES | — | |
| amount_billed | numeric | YES | — | |
| position | int | NO | 0 | Display order. |
| manually_edited_fields | text[] | NO | '{}' | |
| manually_edited_at | timestamptz | YES | — | |
| hidden | boolean | NO | false | |
| hidden_at | timestamptz | YES | — | |

- **UNIQUE INDEX:** `po_line_items_po_btli_uidx (po_id, bt_line_item_id)` — added so re-scrapes UPSERT in place instead of delete+reinsert (which wiped edits/deletes).
- **Writes:** `/v2/api/purchase-orders/upload`, `/v2/api/po-line-items/[id]/{edit,delete}`.
- **Reads:** `/v2/job/[job_id]` (PO drawer).

### change_orders

CO grid scraped from BT's `/api/ChangeOrders`. Same manual-wins pattern as POs but no separate line-items table (BT exposes CO as a single header).

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| bt_co_id | bigint | NO unique | — | BT CO id, upsert key. |
| job_key | text | NO | — | |
| bt_job_id | bigint | YES | — | |
| co_number | text | YES | — | |
| title | text | YES | — | |
| status | text | YES | — | |
| approval_code | int | YES | — | |
| owner_price | numeric | YES | — | Client-facing CO amount. |
| builder_cost | numeric | YES | — | |
| total_with_tax | numeric | YES | — | |
| owner_name | text | YES | — | |
| date_approved | date | YES | — | |
| date_added | date | YES | — | |
| manually_edited_fields | text[] | NO | '{}' | |
| manually_edited_at | timestamptz | YES | — | |
| hidden | boolean | NO | false | |
| hidden_at | timestamptz | YES | — | |
| scraped_at | timestamptz | NO | now() | |

- **Writes:** `/v2/api/change-orders/upload`, `/v2/api/change-orders/[id]/{edit,delete}`.
- **Reads:** `/v2/job/[job_id]`.

### pay_app_line_items

G703 line items parsed from uploaded pay-app spreadsheets. Defined in migration 002. Header row lives in `pay_apps`.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| pay_app_id | uuid | NO (FK→pay_apps.id ON DELETE CASCADE) | — | |
| job_id | text | NO (FK→jobs.id) | — | |
| line_number | text | NO | — | |
| description | text | YES | — | |
| division | text | YES | — | |
| scheduled_value | numeric | YES | — | |
| work_completed_previous | numeric | YES | — | |
| work_completed_this_period | numeric | YES | — | |
| materials_stored | numeric | YES | — | |
| total_completed | numeric | YES | — | |
| pct_complete | numeric | YES | — | |
| balance_to_finish | numeric | YES | — | |
| retainage | numeric | YES | — | |
| raw_row_index | int | YES | — | |
| created_at | timestamptz | YES | now() | — |

- **Writes:** the pay-app xlsx ingestion (Python `process.py` / scripts, not currently a Next.js route — see §2/§5 of the parent doc).
- **Reads:** `/v2/job/[job_id]`, `/api/jobs/[id]/client-summary`, `/meeting`.
- **Indexes:** `idx_pay_app_line_items_job (job_id)`, `idx_pay_app_line_items_pay_app (pay_app_id)`.

### subs

Sub catalog. Hand-curated PRIMARY source plus an `auto`-source overlay populated by `ensureSubsForCrews` in `/v2/api/daily-logs/upload` — when the BT scraper logs a crew name that doesn't match any existing `subs.name` or `subs.aliases`, an `auto` row is inserted. Existing human-curated rows are NEVER overwritten. Shape inferred from `lib/types.ts:Sub` and the daily-log upload helper:

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | text | NO | — | Slug PK (slugified from `name`). |
| name | text | NO | — | Display name. Matched against `daily_logs.crews_present` (case-insensitive). |
| trade | text | YES | — | Free-text trade. |
| aliases | text[] | YES | — | Alternate spellings the import + crew-matcher use. |
| rating | numeric | YES | — | 1–5. |
| reliability_pct | numeric | YES | — | Computed metric. |
| avg_days_per_job | numeric | YES | — | |
| jobs_performed | int | YES | — | |
| flagged_for_pm_binder | boolean | NO | false | Surfaces in PM binder. |
| flag_reasons | text[] | YES | — | |
| rating_basis | text[] | YES | — | |
| notes | text | YES | — | |
| source | text | NO | 'manual' | `manual` (curated) vs `auto` (created from BT crew name). |
| hidden | boolean | NO | false | Soft-delete; re-scrape never un-hides (upload helper uses `ignoreDuplicates`). |
| hidden_at | timestamptz | YES | — | |
| updated_at | timestamptz | NO | now() | — |

- **Writes:** `/v2/api/daily-logs/upload` (`ensureSubsForCrews` — insert-only, `ignoreDuplicates:true`); `/api/subs/[id]/edit`; `/api/subs/[id]/delete` (deletes cascade to `todos` via the route's own cascade logic).
- **Reads:** `/subs`, `/sub/[id]`, `/import` (for the catalog Claude uses to canonicalize names — §7), `/v2/job/[job_id]`, `/api/import-transcript`, `/meeting`.
- **Source-of-truth:** human-curated for `manual` source rows; BT-derived for `auto` rows. The cockpit UI clearly badges the two.
- **Gotcha:** `subs.id` is a slug `text`, not uuid — many tables (`todos.sub_id`, `items.sub_id`, `sub_specialties.sub_id`, `sub_checklist_items.sub_id`) carry text FKs.

### sub_specialties

Per-sub specialty tags ("TNT does exterior painting"). Two sources: `manual` (Jake/PM declared) and `auto` (derived from `daily_logs.parent_group_activities` when this sub was on site). Migration 012 (and re-applied via the F-series).

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| sub_id | text | NO (FK→subs.id ON DELETE CASCADE) | — | |
| specialty | text | NO | — | |
| source | text | NO | 'manual' | CHECK (`manual`, `auto`). |
| duration_days_manual_override | numeric | YES | — | Override `schedule_items.typical_duration_days` for this sub × specialty. |
| schedule_item_id | uuid | YES (FK→schedule_items.id ON DELETE SET NULL) | — | When set, sub profile renders the canonical name and rolls durations up. |
| created_by | text | YES | — | |
| created_at | timestamptz | NO | now() | — |

- **UNIQUE:** `(sub_id, specialty)`.
- **Writes:** `/api/sub-specialties` (POST/DELETE).
- **Reads:** `/sub/[id]`.

### sub_checklist_items

Running per-sub checklist with two lenses (SAFETY / SCHEDULE). F7.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| sub_id | text | NO (FK→subs.id ON DELETE CASCADE) | — | |
| lens | text | NO | — | CHECK (`SAFETY`, `SCHEDULE`). |
| item_text | text | NO | — | |
| is_done | boolean | NO | false | |
| done_at | timestamptz | YES | — | |
| done_by | text | YES | — | |
| notes | text | YES | — | |
| position | int | NO | 0 | Display order within the lens. |
| created_by | text | YES | — | |
| created_at | timestamptz | NO | now() | — |
| updated_at | timestamptz | NO | now() | — |

- **Writes:** `/api/sub-checklist` (POST/PATCH/DELETE).
- **Reads:** `/sub/[id]`.

### pms

PM directory. Shape inferred from `types.ts:PM` and migration 007 (which adds `aliases` + `notes`).

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | text | NO | — | Slug PK (`bob`, `lee`, `nelson`, `martin`, `jason`). |
| full_name | text | NO | — | |
| active | bool | YES | true | |
| aliases | text[] | YES | '{}' | First names / shortenings the brain uses to canonicalize transcripts. |
| notes | text | YES | — | |

- **Seed:** migration 007 inserts the alias arrays per PM (`bob` → `['Bob']`, `lee` → `['Lee Worthy', 'Worthy']`, etc.).
- **Writes:** Supabase Studio / manual SQL only.
- **Reads:** every list/select widget that picks a PM — `/`, `/meeting`, `/import`, `/admin/users`, `/admin/jobs`, `/v2/upload`.
- **Source-of-truth:** human-curated. Note: `pmId` in `lib/auth-users.ts` (the seed user list) MUST match `pms.id` for visibility to work (§4).

### job_pm_assignments

Historical PM-to-job assignments — lets a job transition PMs without losing history. Migration 007.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| job_id | text | NO (FK→jobs.id) | — | |
| pm_id | text | NO (FK→pms.id) | — | |
| assigned_at | date | NO | — | |
| ended_at | date | YES | — | NULL = current assignment. |
| reason | text | YES | — | |
| created_at | timestamptz | YES | now() | — |

- **Partial index:** `idx_job_pm_assignments_current (job_id, ended_at) WHERE ended_at IS NULL` — fast "current PM of job X" lookups.
- **Reads:** `/`, `/meeting`, `/import`, `/v2/upload`. Treated as a secondary source — `jobs.pm_id` is the canonical visibility column; this table is for audit + future PM transitions.

### user_overlay

Per-user overrides that layer on top of the hardcoded `USERS` seed in `lib/auth-users.ts`. Lets the admin panel add users / change job access at runtime without a code change + redeploy (Vercel's filesystem is read-only).

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| email | text | NO | — | PK (case-insensitive index on `lower(email)`). |
| name | text | NO | — | |
| role | text | NO | 'pm' | `admin \| pm` |
| pm_id | text | YES | — | Matches `pms.id` for visibility. |
| allowed_jobs | text[] | NO | '{}' | DEPRECATED — visibility is now `jobs.pm_id`-driven (see §4). Kept on the row for legacy migration; not enforced. |
| password | text | YES | — | Plaintext (same trade-off as the seed list). Overrides seed if set. |
| created_at | timestamptz | NO | now() | — |
| updated_at | timestamptz | NO | now() | — |

- **Writes:** `lib/user-store.ts` (`upsertUserAccess`, `createUser`, `deleteUser`) — called from admin routes.
- **Reads:** `lib/user-store.ts:getAllUsers()` merges this onto `USERS` on every auth call.

### ingestion_events

Diff-review architecture (Gate 2B). Every transcript / daily-log / pay-app / manual ingestion creates one event; the Reconciler emits `proposed_changes` against it; `/v2/review/[id]` lets Jake accept/edit/reject. Migration 008.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| source_type | text | NO | — | CHECK (`transcript`, `daily_log`, `pay_app`, `manual`). |
| source_meeting_id | uuid | YES (FK→meetings.id) | — | |
| source_file_path | text | YES | — | |
| source_file_hash | text | YES | — | Dedupe across re-uploads. |
| ingested_at | timestamptz | YES | now() | |
| ingested_by | text | YES | 'jake' | |
| review_state | text | NO | 'pending' | CHECK (`pending`, `in_review`, `committed`, `rejected`, `partial`). |
| reviewed_at | timestamptz | YES | — | |
| reviewed_by | text | YES | — | |
| proposed_count | int | YES | 0 | |
| accepted_count | int | YES | 0 | |
| rejected_count | int | YES | 0 | |
| edited_count | int | YES | 0 | |
| job_id | text | YES (FK→jobs.id) | — | |
| notes | text | YES | — | |

- **Writes:** `/v2/api/upload`, `/v2/api/review/[id]/commit`, `/v2/api/items/[id]/convert-to-action`.
- **Reads:** `/v2/review`, `/v2/review/[ingestion_event_id]`, `/v2/job/[job_id]`, `/`.

### proposed_changes

The diff payload the Reconciler emits against an `ingestion_event`. Jake reviews each row in `/v2/review` and accepts/edits/rejects; on accept, the commit route writes into `items`/`decisions`/`open_questions` (canonical tables). Migration 008.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| ingestion_event_id | uuid | NO (FK→ingestion_events.id ON DELETE CASCADE) | — | |
| change_type | text | NO | — | CHECK (`add_item`, `update_item`, `resolve_item`, `merge_items`, `add_decision`, `add_open_question`, `add_signal`, `add_sub_event`). |
| proposed_item_data | jsonb | YES | — | For `add_item` / `add_signal`. |
| target_item_id | uuid | YES (FK→items.id) | — | For `update_item` / `resolve_item`. |
| field_changes | jsonb | YES | — | Field-level diff. |
| merge_target_id | uuid | YES (FK→items.id) | — | For `merge_items`. |
| merged_from_ids | uuid[] | YES | — | |
| proposed_decision_data | jsonb | YES | — | |
| proposed_question_data | jsonb | YES | — | |
| review_state | text | NO | 'pending' | CHECK (`pending`, `accepted`, `rejected`, `edited_and_accepted`). |
| reviewed_at | timestamptz | YES | — | |
| resulting_item_id | uuid | YES (FK→items.id) | — | Set on accept. |
| resulting_decision_id | uuid | YES (FK→decisions.id) | — | |
| resulting_question_id | uuid | YES (FK→open_questions.id) | — | |
| source_claim_ids | uuid[] | YES | — | Audit trail back to extractor claims. |
| confidence | text | YES | — | CHECK (`high`, `medium`, `low`). |
| job_id | text | YES (FK→jobs.id) | — | |
| sub_id | text | YES (FK→subs.id) | — | |
| notes | text | YES | — | |
| created_at | timestamptz | YES | now() | — |

- **Writes:** Python reconciler (writes proposed rows); `/v2/api/review/[id]/commit` (flips `review_state` + populates resulting_*_ids); `/v2/api/items/[id]/convert-to-action`.
- **Reads:** `/v2/review`, `/v2/review/[ingestion_event_id]`.

### decisions

Standalone decisions log ("we picked X") — kept separate from `items` so resolved decisions don't get nagged. Migration 004.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| human_readable_id | text | NO unique | — | |
| job_id | text | NO (FK→jobs.id) | — | |
| source_meeting_id | uuid | NO (FK→meetings.id) | — | |
| description | text | NO | — | |
| decided_by | text | YES | — | |
| decision_date | date | YES | — | |
| supersedes_decision_id | uuid | YES (FK→decisions.id) | — | Chain when a later decision overrules an earlier one. |
| source_claim_id | uuid | YES (FK→claims.id) | — | |
| created_at | timestamptz | YES | now() | — |

- **Writes:** `/v2/api/review/[id]/commit` (only via accept).
- **Reads:** `/v2/job/[job_id]` (not yet rendered in production — design exists).

### open_questions

Standalone unanswered-question log — same rationale (don't pollute `items` with non-actionable rows). Migration 004.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| human_readable_id | text | NO unique | — | |
| job_id | text | NO (FK→jobs.id) | — | |
| source_meeting_id | uuid | NO (FK→meetings.id) | — | |
| question | text | NO | — | |
| asked_by | text | YES | — | |
| status | text | YES | 'open' | CHECK (`open`, `answered`, `dropped`). |
| answer | text | YES | — | |
| answered_at | timestamptz | YES | — | |
| source_claim_id | uuid | YES (FK→claims.id) | — | |
| created_at | timestamptz | YES | now() | — |

- **Writes:** `/v2/api/review/[id]/commit`.
- **Reads:** `/v2/job/[job_id]`.

### meetings

One row per processed transcript. Three timestamp columns track the brain pipeline (Extractor → Reconciler → Auditor). Migration 003.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| job_id | text | NO (FK→jobs.id) | — | |
| pm_id | text | YES (FK→pms.id) | — | |
| meeting_date | date | NO | — | |
| meeting_type | text | YES | — | CHECK (`site`, `office`). |
| attendees | text[] | YES | — | |
| transcript_file_path | text | YES | — | |
| raw_transcript_text | text | YES | — | |
| source_file_hash | text | YES unique | — | Dedupe — re-uploading the same transcript is rejected. |
| extracted_at | timestamptz | YES | — | Call 1 done. |
| reconciled_at | timestamptz | YES | — | Call 2 done. |
| audited_at | timestamptz | YES | — | Call 3 done. |
| reconciler_version | text | YES | — | |
| created_at | timestamptz | YES | now() | — |

- **Writes:** `/v2/api/upload`.
- **Reads:** `/v2/review/*`.

### claims

Raw output of the Extractor (Call 1 of 3 brain). Kept verbatim so "what did the brain see + how did it classify it" stays auditable without re-running the LLM. Migration 003 (canonical-name columns added in 007).

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| meeting_id | uuid | NO (FK→meetings.id ON DELETE CASCADE) | — | |
| speaker | text | YES | — | Verbatim transcript speaker label. |
| speaker_canonical | text | YES | — | After alias resolution. |
| speaker_canonical_id | text | YES | — | `pms.id` / `internal_people.id`. |
| subject | text | YES | — | |
| subject_canonical | text | YES | — | |
| subject_canonical_id | text | YES | — | |
| claim_type | text | NO | — | CHECK (`commitment`, `decision`, `condition_observed`, `status_update`, `question`, `complaint`). |
| statement | text | NO | — | |
| raw_quote | text | YES | — | The verbatim line from the transcript. |
| position_in_transcript | int | YES | — | |
| extracted_at | timestamptz | YES | now() | — |

- **Writes:** Python extractor.
- **Reads:** `/v2/review/[ingestion_event_id]` (drilldown), Reconciler.

### corrections

Learning loop — every time Jake overrides a Reconciler suggestion, the override is recorded here so future runs can match similar contexts. Migration 007.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| item_id | uuid | YES (FK→items.id) | — | |
| field_changed | text | NO | — | |
| before_value | text | YES | — | |
| after_value | text | YES | — | |
| correction_reason | text | YES | — | |
| corrected_by | text | YES | 'jake' | |
| context | jsonb | YES | — | Surrounding state at correction time. |
| applied_count | int | YES | 0 | Times a future Reconciler run applied this correction. |
| created_at | timestamptz | YES | now() | — |

- **Indexes:** `idx_corrections_field`, `idx_corrections_recent (created_at DESC)`.
- **Writes:** the commit route / Reconciler when an edit is made during review.
- **Reads:** Python Reconciler (feeds prior corrections back into the prompt).

### texts

NOT actively used in the Next.js cockpit (no `.from("texts")` in any route or page). Referenced in the MEMORY note as a v0/v1 brain table that was superseded by `claims`. Treat as legacy / deprecated; do not write to it.

### schedule_items

Canonical schedule items (`Electrical Rough`, `Drywall Hang`, `T-Pole`, …) so durations can be compared across subs regardless of BT's spelling. F5.

| column | type | nullable | default | purpose |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| name | text | NO unique | — | `"Electrical Rough"` |
| trade | text | YES | — | `"Electrical"` |
| sequence_order | int | YES | — | Rough sort across a job. |
| typical_duration_days | numeric | YES | — | Default duration; can be overridden per `sub_specialties.duration_days_manual_override`. |
| aliases | jsonb | NO | '[]' | Alternative names. |
| notes | text | YES | — | |
| created_at | timestamptz | NO | now() | — |

- **Seed:** the migrations route seeds ~37 canonical items idempotently (`WHERE NOT EXISTS`).
- **Writes:** SQL/Studio only currently.
- **Reads:** `/sub/[id]` for rollups.

---

### Source-of-truth quick reference

| domain | source-of-truth table | notes |
|---|---|---|
| Job catalog | `jobs` | Edited via `/api/admin/jobs`. |
| PM-to-job visibility | `jobs.pm_id` | Single source. `user_overlay.allowed_jobs` and `job_pm_assignments` are NOT used by `canSeeJobByPm`. |
| PM directory | `pms` | Aliases used by transcript extractor. |
| Live action items (v1) | `todos` | What the home, meeting, and sub pages read/write. Edit via `edited_title`. |
| Action items (v2 brain) | `items` | Created only via the diff-review commit flow. |
| Decisions / open questions | `decisions` / `open_questions` | Same flow. |
| BT daily logs | `daily_logs` | Manual-wins via `manually_edited_fields`/`hidden`. |
| BT purchase orders | `purchase_orders` + `po_line_items` | Same manual-wins. |
| BT change orders | `change_orders` | Same. |
| Pay app G703 lines | `pay_app_line_items` | Python ingestion. |
| Sub catalog | `subs` | `manual` rows trump `auto` rows. Auto rows protect human-curated entries via `ensureSubsForCrews`'s alias check + `ignoreDuplicates`. |
| Sub specialties / checklist | `sub_specialties` / `sub_checklist_items` | Manual + auto union. |
| Job AI summary | `job_summaries` | One row per refresh, history kept. |
| Transcript ingestion audit | `meetings` + `claims` + `corrections` | Reconciler reads `corrections` to learn. |
| Review queue | `ingestion_events` + `proposed_changes` | Diff buffer between AI and canonical tables. |
| Users (overlay) | `user_overlay` | Layers on top of `USERS` seed in `lib/auth-users.ts` (by email, case-insensitive). |
| Canonical schedule items | `schedule_items` | Reference table. |
| Extra Ross Built people | `internal_people` | Non-PM aliases for Jake, Andrew, Lee Ross. |

---


---

## §4 AUTH & VISIBILITY

The cockpit's auth is intentionally a tiny in-house system — five hardcoded users, plaintext passwords, an HMAC-signed cookie, and one rule for visibility. Designed for an internal MVP; documented escape hatches below.

### Session model

A session is an HMAC-SHA256 signature over a base64url-encoded `{ email, exp }` payload.

```ts
// lib/auth.ts
interface SessionPayload {
  email: string;
  exp: number; // unix seconds
}

export function encodeSession(email: string): string {
  const payload: SessionPayload = {
    email,
    exp: Math.floor(Date.now() / 1000) + SESSION_TTL_SEC,
  };
  const body = b64url(JSON.stringify(payload));
  const sig = sign(body);  // HMAC-SHA256(body, AUTH_SECRET)
  return `${body}.${sig}`;
}
```

- **Secret:** `process.env.AUTH_SECRET` (must be ≥16 chars). Dev fallback `"ross-built-dev-secret-please-change-me-now"` so `npm run dev` boots without manual env setup; logs a one-time warning and is NOT secure.
- **TTL:** `SESSION_TTL_SEC = 7 * 24 * 60 * 60` (7 days).
- **Cookie name:** `rb_session` (constant `SESSION_COOKIE` in `lib/auth-constants.ts`).
- **Cookie flags (from `app/api/auth/login/route.ts`):** `httpOnly: true`, `sameSite: "lax"`, `secure: process.env.NODE_ENV === "production"`, `path: "/"`, `maxAge: SESSION_TTL_SEC`.
- **Verify path:** the body is HMACed again and the recomputed signature is compared with `crypto.timingSafeEqual` to avoid timing side-channels.

### Two-runtime split

Middleware runs in Edge runtime (no `node:crypto`), pages + route handlers run in Node. So:

- `lib/auth.ts` uses `node:crypto.createHmac("sha256", ...)` + `crypto.timingSafeEqual` — Node only.
- `middleware.ts` uses Web Crypto (`crypto.subtle.importKey` + `crypto.subtle.verify`) — Edge-compatible.
- Both paths compute the SAME HMAC over the SAME body bytes — they just call different APIs.

`lib/auth-constants.ts` is split out specifically so `middleware.ts` can import `SESSION_COOKIE` and `SESSION_TTL_SEC` without dragging `node:crypto` into the Edge bundle.

> **BufferSource cast gotcha:** Vercel's TS lib types `Uint8Array<ArrayBufferLike>` doesn't match `ArrayBufferView<ArrayBuffer>` expected by `crypto.subtle`. So middleware does `new TextEncoder().encode(getSecret()) as BufferSource` — runtime accepts plain Uint8Array fine. If you remove the cast you get TS errors at deploy time only.

### Seed users

`lib/auth-users.ts` exports the hardcoded `USERS` array:

| email | name | role | pmId | allowedJobs |
|---|---|---|---|---|
| jake@rossbuilt.com | Jake Ross | admin | null | `["*"]` |
| bob@rossbuilt.com | Bob Mozine | pm | bob | `["molinari", "pou"]` |
| nelson@rossbuilt.com | Nelson Belanger | pm | nelson | `["dewberry", "clark"]` |
| lee@rossbuilt.com | Lee Worthy | pm | lee | `["ruthven", "krauss"]` |
| martin@rossbuilt.com | Martin Mannix | pm | martin | `["fish"]` |

All passwords are the literal string `"password"`. `allowedJobs` is preserved on the type but NOT enforced anymore — see "Visibility rule" below.

> **Security trade-off:** internal MVP, behind login, ~5 users, all employees. Migration path: move passwords to bcrypt hashes in `user_overlay.password`, add a `password_hash` column, swap `checkPassword` to `bcrypt.compare`. Then either keep the same cookie model or swap to a real provider (Clerk, Auth0).

### Overlay model

`user_overlay` (Supabase) lets the admin panel add users / edit job access at runtime without redeploy. Why Supabase: Vercel's filesystem is read-only, so the previous JSON-file overlay couldn't be persisted.

`lib/user-store.ts:getAllUsers()` merges:
1. Read every row from `user_overlay`.
2. For each seed in `USERS`, if an overlay row exists for its email (case-insensitive), replace with `rowToUser({ ...overlayRow, email: seed.email })` to preserve original casing.
3. Append any overlay-only users not present in the seed.

`findUserByEmail` (used by login + cookie decode) calls `getAllUsers()` and finds by lowercased email.

### Visibility rule

The cockpit's ONE rule, on `lib/auth.ts`:

```ts
export function canSeeJobByPm(u: User | null, jobPmId: string | null): boolean {
  if (!u) return false;
  if (u.role === "admin") return true;
  return !!jobPmId && jobPmId === u.pmId;
}
```

- Admin sees everything.
- A PM sees a job iff `jobs.pm_id` (or, equivalently, the open row in `job_pm_assignments`) equals their `pmId`.
- A job with NO PM is invisible to all non-admins.

`user_overlay.allowed_jobs` is DEPRECATED — `jobs.pm_id` is the single source of truth. The column stays on the row for forward compatibility (e.g. if someone wants to re-add per-user exception lists later) but no code path enforces it. The previous `canSeeJob` helper that read `allowedJobs` was removed during the 2026-05 migration; the current shim is `canSeeJobByPm`.

### Middleware behavior

```ts
// middleware.ts
const PUBLIC_PREFIXES = ["/login", "/api", "/_next", "/favicon"];

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|ross-built-logo.svg|ross-built-mark.svg).*)",
  ],
};
```

- Matcher excludes static assets entirely (faster — Edge function never runs on them).
- For everything the matcher catches: if `pathname` starts with any `PUBLIC_PREFIXES` entry → `NextResponse.next()`.
- API routes are explicitly NOT gated by middleware. They're called by internal server-to-server fetches (e.g. the BT sync route POSTing `/v2/api/daily-logs/upload`) that don't carry the browser cookie. Page renders enforce per-job visibility instead.
- Otherwise: read `rb_session` cookie, run `verifyToken` (HMAC + exp check). On failure:
  - Build redirect to `/login?next=<original-pathname>`.
  - If a stale cookie was sent, also call `res.cookies.delete(SESSION_COOKIE)` so the browser stops re-sending it. This is the "stale-signature after `AUTH_SECRET` rotation" path — without the delete, the user would silently bounce-loop.

### `AUTH_SECRET` env var

- Set in Vercel project settings (Production + Preview).
- Length ≥16 chars enforced by both `lib/auth.ts:getSecret()` and `middleware.ts:getSecret()`. If missing, both fall back to the dev secret (insecure; warns once).
- **To rotate:** generate a new secret, set in Vercel, redeploy. ALL existing sessions become invalid — users get bounced to `/login` with the stale cookie auto-cleared. There's no current "graceful rotation" (no second key tried). If that becomes important, accept either of `AUTH_SECRET` / `AUTH_SECRET_PREV` in `verifyToken`.

---


---

## §5 PAGES

All pages live under `production-cockpit/app/`. Every page is a React Server Component (RSC) using the Next 14 App Router. Default cache directive is `export const dynamic = "force-dynamic"` — every page reads `cookies()` via `currentUser()` so static optimization is moot, and the cockpit values freshness over caching. Visibility everywhere routes through `canSeeJobByPm(user, jobPmId)` from `@/lib/auth` (admin sees everything; a PM sees jobs whose `jobs.pm_id` matches their own `pmId`). The shared mobile-first chrome is `@/components/header` (`<Header />`).

### `/` — Portfolio home

File: `production-cockpit/app/page.tsx`.

- **What it shows**: One row per job (visible to the signed-in user), sorted by past-due → open → name. Each row shows job name, PM name, address, and the right-side count slot (`N△` plaud-pending, `N late`, `N open`). Above the list, a "Director stat strip" of four tiles (Active jobs, Open items, Past due, To approve) + a portfolio-wide PO rollup card ("$X committed · $Y paid · $Z outstanding"). Admin gets PM filter pills (`?pm=<pmId>`).
- **Server loads** (one `Promise.all`): `jobs(id, name, address, pm_id)`, `todos(job, due_date)` filtered to `OPEN_STATUSES`, `pms(id, full_name)`, `job_pm_assignments(job_id, pm_id)` where `ended_at is null`, `ingestion_events(job_id)` where review_state in `('pending','in_review')`. Then paginates `purchase_orders` 1000 at a time (`cost, amount_paid, amount_remaining, job_key`, `hidden=false`) — Supabase default limit is 1000 — to compute the rollup. PO→job match is `job_key startsWith job.name`.
- **Visibility**: `currentUser()` → `canSeeJobByPm(user, activePmByJob.get(j.id) ?? j.pm_id)` filter on jobs before render. PM filter pills only render for admin.
- **Interactive elements**:
  - Link per job → `/v2/job/[id]`.
  - `FilterPill` admin-only → `GET /?pm=<pmId>`.
  - No buttons that mutate (read-only home).
- **Cache**: `dynamic = "force-dynamic"`.
- **Client components owned**: none — fully server-rendered.

### `/meeting` — Monday meeting agenda

Files: `production-cockpit/app/meeting/page.tsx` (server) + `meeting/meeting-client.tsx` (client).

- **What it shows**: Guided, job-by-job agenda for the Monday meeting. For each visible job (urgent first): an ordinal pill (`01`, `02`…), name, PM name, contract % billed, "N to approve" badge. Each card breaks into buckets — "Past due" (red), "This week" (blue), "Subs to watch" (chips with health dots). User can click "cover" to mark a job done in-meeting (ephemeral, resets on reload). Sticky progress bar at top.
- **Server loads**: `jobs`, `todos(id, title, edited_title, job, due_date, sub_id)` in `OPEN_STATUSES`, `subs(id, name, flagged_for_pm_binder, flag_reasons)` where `hidden=false`, `pms`, `job_pm_assignments`, `ingestion_events`, and `pay_app_line_items(job_id, scheduled_value, total_completed)` (tolerates missing table). Computes per-sub global tally (past-due / due-soon across all jobs) — drives the sub health dot via `subHealth()` from `@/lib/sub-health`. Computes contract pct per job from pay-app sums.
- **Visibility**: same `canSeeJobByPm` filter; admin gets PM scope pills (`?pm=`).
- **Interactive elements**:
  - Cover button (client, ephemeral — `useState<Set<string>>`).
  - Reset button on progress strip.
  - `DeleteButton` (`@/components/delete-button`) on each past-due item → `POST /api/todos/[id]/delete`.
  - SubChip → `/sub/[id]`.
  - Job card title → `/v2/job/[id]`.
  - ScopePill → `/meeting?pm=<id>`.
- **Cache**: `dynamic = "force-dynamic"`.
- **Client components**: `MeetingAgenda` (owns the covered-set state).

### `/import` — Unified import hub

File: `production-cockpit/app/import/page.tsx`.

- **What it shows**: Three section card panels — "Last pulls & imports" (recency for POs / daily logs / transcripts), "Transcript" (drop a Plaud `.txt`), "Daily logs" (one-click BT pull + manual JSON upload), "Purchase orders & change orders" (one-click PO/CO pull buttons).
- **Server loads**: `pms(active=true)`, `jobs`, `job_pm_assignments`, `subs(hidden=false)`, `todos.source_transcript distinct` to derive transcript-import history, `daily_logs` count + last enriched_at, `purchase_orders` count + last scraped_at.
- **Auth**: no explicit guard (middleware enforces session). Anyone signed in can hit it.
- **Interactive elements**:
  - `TranscriptImportModal` (`@/components/transcript-import-modal`) → fires `POST /api/import-transcript` then `POST /api/save-extracted-todos`.
  - `BtSyncButton` (`@/components/bt-sync-button`) → modal that POSTs `/api/bt/sync` with BT username + password (typed each time, never persisted).
  - `BtPoSyncButton` → `POST /api/bt/sync-po`.
  - `BtCoSyncButton` → `POST /api/bt/sync-co`.
  - `DailyLogUploadForm` (`../v2/daily-logs/upload/upload-form`) → reads a local JSON file, POSTs it to `/v2/api/daily-logs/upload`.
  - `<details>` history list of last 20 transcript imports.
- **Cache**: `dynamic = "force-dynamic"`. `app/import/loading.tsx` exists for the route's loading UI.
- **Notable**: `prettyImport()` and `prettyDate()` normalize filename → readable label (see commit `f8d4fe8`).

### `/v2/job/[job_id]` — PM job page

Files: `production-cockpit/app/v2/job/[job_id]/page.tsx` + sibling clients (`check-off-button.tsx`, `row-client.tsx`, `edit-row.tsx`, `category-pill-edit.tsx`, `job-summary-panel.tsx`).

- **What it shows**: The PM's daily working surface. Header with job name + address + a red "N plaud transcripts to approve" pill if ingestion_events are pending. Then in order:
  1. `JobSummaryPanel` — AI-generated narrative ("headline · phase · whats_happening · subs_recently_on_site · open_concerns · coming_up · inspections_recent · safety_flags").
  2. `PayAppProgress` — schedule-of-values contract %, breakdown of cost lines, "open on N POs" overlay.
  3. `ClientSummaryPanel` (`@/components/client-summary-panel`) — on-demand client-facing weekly/monthly update.
  4. `AccountingTable` (`@/components/accounting-table`) — purchase-order grid + line items.
  5. `ChangeOrdersSection` (`@/components/change-orders-section`) — change-order list.
  6. `CategoryFilterPills` — filter to a single category.
  7. Open items grouped by category via `CategorySection` → `RowClient`.
  8. "Done this week" collapsed `<details>`.
- **Server loads** (all in one `Promise.all`):
  - `jobs(id, name, address, pm_id)` by id (single).
  - `items(... + sub:subs(id,name))` where `job_id = job_id` and status in `('open','in_progress','blocked')`.
  - `todos(... + sub:subs)` where `job = job.name` (note: todos use display name, items use slug) and status in OPEN_STATUSES.
  - completed `items` + `todos` within last 7 days.
  - `ingestion_events` for the pending bar.
  - `subs(hidden=false)` for the edit-row sub picker.
  - `job_summaries` latest by `generated_at`.
  - `daily_logs(id, photo_urls, photo_summary)` `ilike job_key, '<job.name>%'` to compute total/pending photo counts.
  - `pay_app_line_items` for the contract progress card.
  - `purchase_orders` `ilike job_key`, `hidden=false`.
  - `change_orders` `ilike job_key`, `hidden=false`.
  - Then a follow-up `po_line_items` query keyed on the loaded PO ids (`hidden=false`).
- **Normalization**: items + todos are flattened into a single `RowData` shape so one rendering path handles both — the row remembers `source: "item" | "todo"` so the check-off / edit / delete buttons route to the right API.
- **Visibility**: `currentUser()` + `canSeeJobByPm(user, jobRes.data.pm_id)`. If false (or no job), renders a "Job not found" surface — same UI whether the job is missing or just hidden from this PM (no enumeration leak).
- **Interactive elements**:
  - `CheckOffButton` — polymorphic, item→`POST /v2/api/items/[id]/(un)complete`, todo→`POST /api/(un)complete` with `{id}`.
  - `RowClient` (the row wrapper) — click row title → `EditRowModal` → `POST /v2/api/items/[id]/edit` (for items) or `POST /api/edit-todo` (for todos).
  - `CategoryPillEdit` — inline change category. Wraps the same edit endpoints.
  - `DeleteButton` — for items `POST /v2/api/items/[id]/delete`, for todos `POST /api/todos/[id]/delete`.
  - `JobSummaryPanel` buttons:
    - "Process N pending photos" → `POST /api/jobs/[id]/process-pending`.
    - "Refresh / Generate summary" → `POST /api/jobs/[id]/refresh-summary` with `{window_days: 30}`.
  - `ClientSummaryPanel` → `POST /api/jobs/[id]/client-summary` with `{period}`.
  - `AccountingTable` rows → editable via `POST /v2/api/purchase-orders/[id]/edit` and `POST /v2/api/po-line-items/[id]/edit`; soft-delete via `/delete` siblings.
  - `ChangeOrdersSection` → `POST /v2/api/change-orders/[id]/(edit|delete)`.
  - `CategoryFilterPills` → `GET /v2/job/[id]?cat=<category>`.
- **Cache**: `dynamic = "force-dynamic"`. `app/v2/job/[job_id]/loading.tsx` exists.
- **Client components owned**: `RowClient`, `CheckOffButton`, `EditRowModal`, `CategoryPillEdit`, `JobSummaryPanel`.

### `/sub/[id]` — Sub profile

File: `production-cockpit/app/sub/[id]/page.tsx`.

- **What it shows**: Sub's name (editable), trade (editable), health dot, "Edit details" collapsible (notes / aliases / delete), four metric tiles (Open, Past due, No-shows). Then in order: Specialties editor (`SpecialtiesEditor` from `./specialties-editor`), Inspections list (last 20), Checklist (Safety + Schedule lenses via `SubChecklistEditor`), Photo summaries (from vision pass), Open items, On-site timeline (collapsed), Recently done (collapsed).
- **Server loads**: `subs(*)` by id, `todos(*)` for this sub split open + done, `sub_specialties` (manual), `jobs(id,name)`, `schedule_items` (canonical taxonomy, tolerant of missing table), `sub_checklist_items` for this sub. Plus `daily_logs` containment queries via helper `logsContainingAny()` which works around Supabase's lack of `&&` overlap on jsonb by issuing one `.filter(col, "cs", json)` per candidate name and de-duping by `id`. Names = sub name + aliases.
- **Visibility**: middleware-gated only — anyone signed-in can view any sub (subs are global, not job-scoped). Uses `notFound()` if the sub doesn't exist.
- **Interactive elements**:
  - `EditableText` (`@/components/editable-text`) on `name`, `trade`, `notes`, `aliases` → `POST /api/subs/[id]/edit`.
  - `DeleteButton` → `POST /api/subs/[id]/delete` (2-step: 409 + `requiresForce:true` if open todos still attached).
  - `SpecialtiesEditor` → `POST /api/sub-specialties` with `{action: 'add' | 'remove' | 'set_duration', specialty, duration_days?}`.
  - `SubChecklistEditor` → `POST /api/sub-checklist` with `{action: 'add' | 'remove' | 'toggle' | 'edit', lens, item_text, item_id, is_done}`.
  - `CategoryFilterPills` → `?cat=`.
- **Cache**: `dynamic = "force-dynamic"`.
- **Notable**: This page does the most aggressive workaround of the Supabase jsonb-overlap issue (see `lib/sub-health` for the dot color, and the memory note `reference_supabase_jsonb_no_overlaps.md`).

### `/subs` — Sub list

File: `production-cockpit/app/subs/page.tsx`.

- **What it shows**: One row per sub (filtered to `hidden=false`), sorted past-due → open → name. Health dot, flagged ⚑ glyph, name, trade or flag reason, right-side `N late · N open` counts. Filter pills: All / ⚑ Flagged / one per trade.
- **Server loads**: `subs(*)` where `hidden=false`, `todos(sub_id, due_date)` in OPEN_STATUSES with `sub_id not null`. Tallies per-sub `{open, past_due, due_soon}`.
- **Visibility**: middleware-gated only.
- **Interactive elements**:
  - Row link → `/sub/[id]`.
  - `DeleteButton` on each row → `POST /api/subs/[id]/delete`.
  - `FilterPill` → `?trade=` or `?flagged=1`.
- **Cache**: `dynamic = "force-dynamic"`.

### `/login` — Sign in

Files: `production-cockpit/app/login/page.tsx` (server) + `login-form.tsx` (client).

- **What it shows**: Centered Ross Built logo, "Production Cockpit · Sign in to continue", email + password form, error banner.
- **Server logic**: if `currentUser()` returns a user, `redirect(searchParams.next ?? "/")`. Otherwise renders `<LoginForm next={next} />`.
- **Interactive elements**: `LoginForm` POSTs `/api/auth/login` with `{email, password}` then does a full-page `window.location.assign(next)` so RSCs re-render with the new session.
- **Cache**: `dynamic = "force-dynamic"`. `metadata.title = "Sign in · Ross Built"`.

### `/admin` — Admin hub

File: `production-cockpit/app/admin/page.tsx`.

- **What it shows**: Three list rows linking to `/admin/users`, `/admin/jobs`, `/admin/migrate`.
- **Auth**: `if (!user) redirect("/login?next=/admin"); if (!isAdmin(user)) notFound();`. Non-admins see a 404, not a permission error (avoids enumeration).
- **Cache**: `dynamic = "force-dynamic"`.

### `/admin/users` — User access admin

Files: `production-cockpit/app/admin/users/page.tsx` + `users-admin-client.tsx`.

- **What it shows**: For each user (seed users from `lib/auth-users.ts` merged with overlay rows from Supabase `user_overlay`): name, email, role, pmId, and (for PMs) a row of toggle pills — one per job — showing which they have access to. Click a job pill to assign / unassign / steal from another PM. Bottom: "Add a PM" form with email, name, optional pmId, allowed jobs.
- **Server loads**: `jobs(id, name, pm_id)`, `pms(id, full_name)`, `getAllUsers()` (seed ∪ overlay).
- **Auth**: same admin guard pattern as `/admin`.
- **Interactive elements**:
  - Toggle job pill → `PATCH /api/admin/jobs` with `{id: jobId, pm_id: newPmId | null}`. This is the single source of truth for visibility — flipping `jobs.pm_id` is what makes the PM see (or lose) the job.
  - Remove user → `DELETE /api/admin/users?email=...` (seed users can only have their overlay row removed, not be hard-deleted).
  - Add PM → `POST /api/admin/users` with `{email, name, pmId, allowedJobs}`.
- **Cache**: `dynamic = "force-dynamic"`.

### `/admin/jobs` — Jobs CRUD

Files: `production-cockpit/app/admin/jobs/page.tsx` + `jobs-admin-client.tsx`.

- **What it shows**: One card per job — display name, slug id, PM, address. Per-row Edit / Remove buttons. Bottom: "Add a job" form (slug id, display name, address, PM).
- **Server loads**: `jobs(id, name, address, pm_id, status)`, `pms`.
- **Auth**: admin guard.
- **Interactive elements**:
  - Edit → PATCH `/api/admin/jobs` with `{id, name?, address?, pm_id?}`.
  - Remove → DELETE `/api/admin/jobs?id=<slug>` (warns about orphaned PO/log/todo data in the confirm; deletes the `jobs` row only, no FK cascades because the scraped tables don't have FKs onto jobs).
  - Add → POST `/api/admin/jobs`.
- **Cache**: `dynamic = "force-dynamic"`.

### `/admin/migrate` — One-click migrations

Files: `production-cockpit/app/admin/migrate/page.tsx` + `migrate-form.tsx`.

- **What it shows**: Instructions + DB password input + Run button. On success: a checklist of every schema object that's now present, plus a "Go to /subs" CTA.
- **Auth**: no explicit guard in the page (admin guard happens at `/admin`); the API route guard could be tighter but currently relies on the migrate page being unlinked.
- **Interactive elements**: Password input + Run button → `POST /api/admin/run-migrations` with `{db_password}`. Password held in `useState` only, cleared after success.
- **Cache**: `dynamic = "force-dynamic"`.

### `/v2/review` — Pending-review queue

File: `production-cockpit/app/v2/review/page.tsx`.

- **What it shows**: List of `ingestion_events` with `review_state in ('pending','in_review')`, sorted newest first. Each card: meeting label (e.g. "5/18 Krauss site"), proposal counts broken down by change_type (`N add · N update · N signal · N decision · N question`), age (`3d ago`), `stale` chip if > 7 days old. Click → `/v2/review/[id]`.
- **Server loads**: `ingestion_events(*)` filtered, `meetings(id, meeting_date, meeting_type, job_id)`, then `proposed_changes(ingestion_event_id, change_type)` for those event ids → per-event counts.
- **Cache**: `dynamic = "force-dynamic"`.

### `/v2/review/[ingestion_event_id]` — Diff detail

Files: `production-cockpit/app/v2/review/[ingestion_event_id]/page.tsx` + sibling `review-form.tsx` (client, not read here but referenced).

- **What it shows**: Header (meeting label + event metadata). Multi-job banner if `proposed_changes.job_id` spans >1 job. Then `<ReviewForm>` — one row per proposed_change, with per-row accept/edit/reject and a bulk commit at the bottom. Shows verbatim claim quotes alongside each row.
- **Server loads**: `ingestion_events(*)`, `proposed_changes(*)` for the event (ordered by change_type then created_at), `subs(hidden=false)`, `jobs`, and if `source_meeting_id` set: `meetings(id, meeting_date, meeting_type, job_id)` + `claims(id, speaker, statement, raw_quote)` for context (capped at 500).
- **Interactive elements** (in `ReviewForm`, client):
  - Per-row Accept / Edit-fields / Reject toggles.
  - Bulk "Commit decisions" → `POST /v2/api/review/[ingestion_event_id]/commit` with `{decisions: [{proposed_change_id, action, edited_data?}]}`.
- **Cache**: `dynamic = "force-dynamic"`.

### `/v2/upload` — Drop transcript (v2 pipeline)

Files: `production-cockpit/app/v2/upload/page.tsx` + sibling `upload-form.tsx` (client).

- **What it shows**: Drop-zone for a transcript .txt + form for job, PM, date, meeting type.
- **Server loads**: `jobs`, `pms(active=true)`, `job_pm_assignments`.
- **Interactive elements**: `UploadForm` reads the file and POSTs `/v2/api/upload` with `{filename, text, job_id, meeting_type, meeting_date, pm_id}`. The brain pipeline (Extractor + Reconciler) runs offline as a Python job; this route only saves the meeting + dedup hash.
- **Cache**: `dynamic = "force-dynamic"`.

### `/v2/daily-logs/upload` — Manual JSON drop

Files: `production-cockpit/app/v2/daily-logs/upload/page.tsx` + sibling `upload-form.tsx` (client, exported as `DailyLogUploadForm`).

- **What it shows**: File picker for a BT scraper `daily-logs.json` (shape `{ byJob: { jobKey: [...] } }`).
- **Interactive elements**: form POSTs the parsed JSON to `/v2/api/daily-logs/upload`.
- **Cache**: `dynamic = "force-dynamic"`.

---


---

## §6 API ROUTES

Every route file is a Next App Router route handler with `export const dynamic = "force-dynamic"`. Auth-guarded routes call `currentUser()` + `isAdmin()` from `@/lib/auth` and short-circuit with `{ok:false, error:"Admin only"}` 403 if the check fails. Most data routes do NOT enforce a session at the API layer — they assume the middleware has gated the originating page, and server-to-server internal `fetch()` (e.g. BT sync calling daily-log upload) must work without cookies. Tables noted as "writes" are the ones the route's update/insert/upsert/delete operates against.

### Auth

#### `POST /api/auth/login`

- File: `production-cockpit/app/api/auth/login/route.ts`.
- **Body**: `{email, password}` (JSON).
- **Auth guard**: none — this IS the auth.
- **Reads**: `getAllUsers()` → reads `user_overlay` from Supabase merged with `lib/auth-users.ts` seed.
- **Writes**: nothing in DB. Sets `SESSION_COOKIE` (HMAC-signed via `encodeSession()`) with `httpOnly`, `sameSite:"lax"`, `secure: NODE_ENV==="production"`, `maxAge: SESSION_TTL_SEC`.
- **Response**: `{ok, user: {email, name, role}}` on success; `{ok:false, error}` 401 on bad credentials, 400 on missing fields.

#### `POST /api/auth/logout`

- File: `production-cockpit/app/api/auth/logout/route.ts`.
- **Body**: none.
- **Writes**: clears the session cookie (`maxAge: 0`).
- **Response**: `{ok:true}`.

### Admin

#### `GET|POST|PATCH|DELETE /api/admin/jobs`

- File: `production-cockpit/app/api/admin/jobs/route.ts`.
- **Auth guard**: `adminGuard()` — `currentUser()` + `isAdmin()`, 403 otherwise.
- **GET**: returns `{ok, jobs:[...]}` (`id, name, address, pm_id, status, phase`).
- **POST body**: `{id, name, address?, pm_id?}`. `id` validated against `/^[a-z0-9][a-z0-9_-]*$/`. Inserts into `jobs`.
- **PATCH body**: `{id, name?, address?, pm_id?}`. Builds patch with `updated_at = now()`, updates `jobs` by id.
- **DELETE**: `?id=<slug>`. Deletes the `jobs` row (no cascade — orphaned POs/logs stay).
- **Cache invalidation**: `bustJobCaches(id)` calls `revalidatePath` on `/`, `/meeting`, `/admin/jobs`, `/admin/users`, `/admin`, `/subs`, and `/v2/job/[id]` if id present.
- **Response**: `{ok, job?}` or `{ok:false, error}`.

#### `GET|POST|PATCH|DELETE /api/admin/users`

- File: `production-cockpit/app/api/admin/users/route.ts`.
- **Auth guard**: admin.
- **GET**: returns merged `getAllUsers()`.
- **POST body**: `{email, name, pmId, allowedJobs[]}` → `createUser()` inserts a row in `user_overlay`.
- **PATCH body**: `{email, allowedJobs[]}` → `upsertUserAccess()` updates `user_overlay.allowed_jobs` (creates row from seed if absent).
- **DELETE**: `?email=...` → removes the overlay row only (seed users can't be hard-deleted).
- **Cache invalidation**: `bustUserCaches()` → `/admin/users`, `/admin`, `/`, `/meeting`.
- **Response**: `{ok, user?}` or `{ok:false, error}`.

#### `POST /api/admin/run-migrations`

- File: `production-cockpit/app/api/admin/run-migrations/route.ts`.
- **Body**: `{db_password}` (or env `SUPABASE_DB_PASSWORD`).
- **Auth guard**: none at API layer (relies on un-linkability of `/admin/migrate`). `maxDuration = 60`.
- **External calls**: opens a `pg.Client` connection to the Supabase Supavisor pooler. Walks a candidate list — `aws-1-us-west-2.pooler.supabase.com:5432`, then `:6543`, then us-east fallbacks, then the legacy `db.<ref>.supabase.co:5432`.
- **Writes**: executes `MIGRATIONS_SQL` (a single multi-statement string) inside `BEGIN/COMMIT`. Creates `daily_logs`, `sub_specialties`, `schedule_items`, `sub_checklist_items`, `job_summaries`, `purchase_orders`, `po_line_items`, `change_orders`, `user_overlay`; adds manual-wins columns (`manually_edited_fields`, `manually_edited_at`, `hidden`, `hidden_at`) on scraped tables; seeds the canonical schedule_items rows.
- **Response**: `{ok, message, verified:{...}, missing:[]}` listing which objects exist. 502 on connection failure with `attempts` array.

### Buildertrend integration (local-only)

All three BT sync routes refuse when `process.env.VERCEL === "1"` because they spawn local Python + Playwright. The user's BT credentials are typed each request, passed via child-process env vars (`BT_USERNAME`, `BT_PASSWORD`), redacted from any error tail before being returned, and never logged or persisted. See memory `project_bt_credential_boundary.md`.

#### `POST /api/bt/sync`

- File: `production-cockpit/app/api/bt/sync/route.ts`.
- **Body**: `{username, password, days?, jobs?, skipPhotos?, maxPhotosPerLog?, extractVision?, headed?}` (defaults: `days=14`, `maxPhotosPerLog=6`, `extractVision=true`).
- **External**: `spawn(pythonExe, [scriptPath, '--days', ...])` against `$BT_SCRAPER_DIR/scrape_api.py` (default `C:\Users\Greg\buildertrend-scraper`). `CHILD_TIMEOUT_SEC = 290`. On exit-0, reads `data/daily-logs.json`, then fetches its own `/v2/api/daily-logs/upload` to upsert, then optionally fetches `/v2/api/daily-logs/extract-photos` (`limit:30`) for vision.
- **Reads/writes**: indirectly — the downstream calls do the writes (`daily_logs` upsert + `subs` auto-create + `daily_logs.photo_summary` updates).
- **Failure logging**: on non-zero exit writes `$BT_SCRAPER_DIR/.session/last-failure.log` (passwords redacted).
- **Response**: `{ok, elapsedMs, scrape:{exitCode, jobCount, logCount, photoCount, stdoutTail, stderrTail}, upload, vision, visionError}`.

#### `POST /api/bt/sync-po`

- File: `production-cockpit/app/api/bt/sync-po/route.ts`.
- **Body**: `{username, password, jobs?, includeLineItems?, headed?}`. Refuses if `includeLineItems && !jobs` (line-items-for-all-jobs would time out — ~30 min).
- **External**: spawns `scrape_po.py`. `CHILD_TIMEOUT_SEC = 900`. Default is grid-only (`--skip-line-items`).
- **Writes**: indirectly via `POST /v2/api/purchase-orders/upload` with `{payload, skipLineItems: !includeLineItems}`.
- **Failure log**: `.session/last-po-failure.log`.
- **Response**: `{ok, elapsedMs, includeLineItems, scrape, upload}`.

#### `POST /api/bt/sync-co`

- File: `production-cockpit/app/api/bt/sync-co/route.ts`.
- **Body**: `{username, password, jobs?, headed?}`. `CHILD_TIMEOUT_SEC = 600`.
- **External**: spawns `scrape_co.py` → reads `data/change-orders.json` → POSTs `/v2/api/change-orders/upload`.
- **Response**: `{ok, elapsedMs, scrape, upload}`.

#### `GET /api/bt/last-failure`

- File: `production-cockpit/app/api/bt/last-failure/route.ts`.
- **Auth guard**: none.
- **Reads**: filesystem — `$BT_SCRAPER_DIR/.session/last-failure.log`.
- **Response**: `{ok, path, writtenAt, contents}` or 404 `{ok:false, error:"no last-failure log"}`.

### Daily logs

#### `POST /v2/api/daily-logs/upload`

- File: `production-cockpit/app/v2/api/daily-logs/upload/route.ts`.
- **Body**: `{source?, payload: {byJob: {[jobKey]: BTRecord[]}}}`. Each `BTRecord` is the BT scraper's row shape — `{logId, date, crews_clean, crews, absent_crews, parent_group_activities, daily_workforce, weatherHigh/Low, activity, notes_full/notes, enriched_at, crew_counts/crews_with_count, inspections/inspections_text, photo_urls/photos}`.
- **Auth guard**: none.
- **Writes**: `daily_logs` upsert `onConflict: "job_key,log_id"`. Columns set: `job_key, log_id, log_date, crews_present, absent_crews, parent_group_activities, daily_workforce, weather_high, weather_low, activity, notes, enriched_at, source, crew_counts, inspections, photo_urls`. Rows without `log_id` are skipped. Also inserts into `subs` (auto-create) via `ensureSubsForCrews()` — insert-only with `ignoreDuplicates: true`, so human-curated subs are never overwritten.
- **Manual-wins**: pre-reads `daily_logs.manually_edited_fields, hidden` for affected `(job_key, log_id)` pairs. Hidden rows are skipped. Rows with edited fields have those columns deleted from the upsert payload.
- **Cache invalidation**: `revalidatePath('/subs')`, `revalidatePath('/sub/[id]', 'page')`.
- **Response**: `{ok, inserted, skipped, auto_subs_created, per_job:{jobKey:{total, inserted, skipped}}}`.

#### `POST /v2/api/daily-logs/extract-photos`

- File: `production-cockpit/app/v2/api/daily-logs/extract-photos/route.ts`.
- **Body**: `{log_ids?, limit?}` (default limit 10, max 50). `maxDuration = 120`.
- **Auth guard**: none.
- **External**: Anthropic SDK (`claude-opus-4-7`). Uses tool-use (`emit_photo_summary`) for structurally-guaranteed JSON. Up to `MAX_PHOTOS_PER_LOG = 6` photos per log; local file paths base64-encoded, URLs sent as `{type:"image",source:{type:"url"}}`.
- **Reads**: `daily_logs(id, job_key, log_date, photo_urls, notes, parent_group_activities, crews_present, photo_summary)` with `photo_urls not null`; if `log_ids` empty, also `photo_summary is null` ordered by `log_date desc`.
- **Writes**: `daily_logs.photo_summary` (jsonb) + `photo_summary_at` per row.
- **Cache invalidation**: `revalidatePath('/sub/[id]', 'page')`, `revalidatePath('/subs')`.
- **Response**: `{ok, considered, processed, failed, results:[{log_id, job_key, log_date, ok, photoCount, summary?, error?}]}`.

#### `POST /v2/api/daily-logs/[id]/edit`

- File: `production-cockpit/app/v2/api/daily-logs/[id]/edit/route.ts`.
- **Body**: any of `{notes, activity, daily_workforce, weather_high, weather_low, crews_present, absent_crews, parent_group_activities}`.
- **Writes**: `daily_logs` row by id; appends edited keys to `manually_edited_fields`, stamps `manually_edited_at`.
- **Cache invalidation**: `/sub/[id]`, `/v2/job/[job_id]`.

#### `POST /v2/api/daily-logs/[id]/delete`

- File: `production-cockpit/app/v2/api/daily-logs/[id]/delete/route.ts`.
- **Writes**: soft delete — `hidden=true, hidden_at=now()` (the upload route never resurrects).
- **Cache invalidation**: `/sub/[id]`, `/v2/job/[job_id]`.

### Purchase orders

#### `POST /v2/api/purchase-orders/upload`

- File: `production-cockpit/app/v2/api/purchase-orders/upload/route.ts`. `maxDuration = 60`.
- **Body**: `{payload:{byJob}, skipLineItems?}` (or bare `{byJob}`).
- **Writes**: `purchase_orders` upsert `onConflict: "bt_po_id"`; `po_line_items` upsert `onConflict: "po_id,bt_line_item_id"`. Sets `scraped_at` on every PO.
- **Manual-wins**: For POs, pre-reads `manually_edited_fields, hidden` keyed by `bt_po_id`. Hidden POs entirely skipped; edited POs have those columns dropped from the upsert payload. For line items, same per `(po_id, bt_line_item_id)`. On a full pull (`!skipLineItems`), also DELETEs only CLEAN lines BT no longer returns — never deletes hidden or edited lines (so a manual deletion or edit survives).
- **Response**: `{ok, jobs, upserted, lineItems, errors[]}`.

#### `POST /v2/api/purchase-orders/[id]/edit`

- File: `production-cockpit/app/v2/api/purchase-orders/[id]/edit/route.ts`.
- **Body**: any of `{po_number, title, vendor, approval_status, work_status, paid_status, cost, amount_paid, amount_remaining, date_added}`.
- **Writes**: `purchase_orders` row; appends edited keys to `manually_edited_fields`.
- **Cache invalidation**: `/v2/job/[job_id]`.

#### `POST /v2/api/purchase-orders/[id]/delete`

- File: `production-cockpit/app/v2/api/purchase-orders/[id]/delete/route.ts`.
- **Writes**: soft delete (`hidden=true`).
- **Cache invalidation**: `/v2/job/[job_id]`.

#### `POST /v2/api/po-line-items/[id]/edit`

- File: `production-cockpit/app/v2/api/po-line-items/[id]/edit/route.ts`.
- **Body**: any of `{cost_code, title, description, quantity, unit_cost, amount, amount_paid, amount_billed}`.
- **Writes**: `po_line_items` row; appends edits to `manually_edited_fields`.

#### `POST /v2/api/po-line-items/[id]/delete`

- File: `production-cockpit/app/v2/api/po-line-items/[id]/delete/route.ts`.
- **Writes**: soft delete (`hidden=true`).

### Change orders

#### `POST /v2/api/change-orders/upload`

- File: `production-cockpit/app/v2/api/change-orders/upload/route.ts`. `maxDuration = 60`.
- **Body**: `{payload:{byJob}}` (or bare `{byJob}`).
- **Writes**: `change_orders` upsert `onConflict: "bt_co_id"`. Same manual-wins pattern as POs (hidden skipped, edited-fields dropped from the upsert).
- **Response**: `{ok, jobs, upserted, errors[]}`.

#### `POST /v2/api/change-orders/[id]/edit`

- File: `production-cockpit/app/v2/api/change-orders/[id]/edit/route.ts`.
- **Body**: any of `{co_number, title, status, owner_price, builder_cost, total_with_tax, date_approved}`.
- **Writes**: `change_orders` + manually_edited_fields bookkeeping.

#### `POST /v2/api/change-orders/[id]/delete`

- File: `production-cockpit/app/v2/api/change-orders/[id]/delete/route.ts`.
- **Writes**: soft delete (`hidden=true`).

### v1 todos (legacy live table)

#### `POST /api/complete`

- File: `production-cockpit/app/api/complete/route.ts`.
- **Body**: `{id}`.
- **Writes**: `todos` row → `status='COMPLETE', completed_at=now(), previous_status=<prior>`. Skips if already complete.
- **Cache invalidation**: `/`, `/subs`, `/sub/[prior.sub_id]`.

#### `POST /api/uncomplete`

- File: `production-cockpit/app/api/uncomplete/route.ts`.
- **Body**: `{id}`.
- **Writes**: `todos` → `status = previous_status || 'NOT_STARTED', completed_at=null, previous_status=null`.

#### `POST /api/edit-todo`

- File: `production-cockpit/app/api/edit-todo/route.ts`.
- **Body**: `{id, title?, due_date?, category?, sub_id?, priority?}`.
- **Writes**: `todos`. Title changes go into `edited_title` + stamp `edited_at` (original LLM-extracted title preserved). Runs `scrubRelativeDates(title, todayIso)` so manual edits can never reintroduce relative phrases like "by Friday" (enforced by `lib/scrub-relative-dates.ts`; covered by `lib/scrub-relative-dates.test.ts`).
- **Cache invalidation**: `/`, `/subs`, `/sub/[id]` for both prior and new sub_id.

#### `POST /api/todos/[id]/delete`

- File: `production-cockpit/app/api/todos/[id]/delete/route.ts`.
- **Writes**: hard delete from `todos` (todos are user/transcript data — re-approving the source transcript will recreate, which is intended).
- **Cache invalidation**: `/`, `/subs`, `/meeting`, `/v2/job/[job_id]`, `/sub/[prior.sub_id]`.

### v2 items (brain table)

#### `POST /v2/api/items/[item_id]/complete`

- File: `production-cockpit/app/v2/api/items/[item_id]/complete/route.ts`.
- **Body**: `{completion_basis?}` (default `"manual"`).
- **Writes**: `items` → `status='complete', completed_at, previous_status, completed_by, completion_basis, manually_edited_fields += 'status'`.
- **Cache invalidation**: `/`, `/v2/job/[job_id]`.

#### `POST /v2/api/items/[item_id]/uncomplete`

- File: `production-cockpit/app/v2/api/items/[item_id]/uncomplete/route.ts`.
- **Writes**: `items` → reverts `status` to `previous_status`, clears completion fields, strips `'status'` from `manually_edited_fields`.

#### `POST /v2/api/items/[item_id]/edit`

- File: `production-cockpit/app/v2/api/items/[item_id]/edit/route.ts`.
- **Body**: any of `{title, detail, target_date, target_date_text, sub_id, category}`.
- **Writes**: `items` + appends edited keys to `manually_edited_fields` (Decision 11 clobber protection — future Reconciler runs skip those columns).

#### `POST /v2/api/items/[item_id]/delete`

- File: `production-cockpit/app/v2/api/items/[item_id]/delete/route.ts`.
- **Writes**: hard delete.

#### `POST /v2/api/items/[item_id]/convert-to-action`

- File: `production-cockpit/app/v2/api/items/[item_id]/convert-to-action/route.ts`.
- **Body**: `{proposed_target_date?, proposed_target_date_text?, proposed_sub_id?}`.
- **Writes**: creates an `ingestion_events` row (`source_type:'manual'`, `review_state:'pending'`) + a `proposed_changes` row (`change_type:'update_item'`, `target_item_id`, `field_changes:{actionability:{before,after:'actionable'}, ...}`) so Jake can review the conversion at `/v2/review`.

### Upload + review

#### `POST /v2/api/upload`

- File: `production-cockpit/app/v2/api/upload/route.ts`.
- **Body**: `{filename, text, job_id, meeting_type, meeting_date, pm_id}`.
- **Writes**: `meetings` insert with SHA-256 hash of `text` in `source_file_hash` for dedup. If hash already exists, returns `{ok, duplicate_of, ingestion_event_id}` without inserting again. The Python Extractor + Reconciler pipeline runs offline; no `ingestion_event` is created here.
- **Response**: `{ok, meeting_id, ingestion_event_id: null, note}`.

#### `POST /v2/api/review/[ingestion_event_id]/commit`

- File: `production-cockpit/app/v2/api/review/[ingestion_event_id]/commit/route.ts`.
- **Body**: `{decisions: [{proposed_change_id, action:'accept'|'reject'|'edit', edited_data?}]}`.
- **Reads**: `ingestion_events(id, review_state, job_id)`, `proposed_changes(*)` for the decisions.
- **Writes**:
  - For `add_item` / `add_signal`: insert into `items` with a generated `human_readable_id` (job-prefixed via `nextHumanId()` walking `items.human_readable_id like 'PREFIX-%'`).
  - For `update_item`: applies `field_changes` to the target row, respecting Decision 11 — fields listed in `items.manually_edited_fields` are skipped (clobber protection). Manual completion (`status='complete'`) is always preserved. Increments `carryover_count`.
  - For `add_decision`: inserts into `decisions`.
  - For `add_open_question`: inserts into `open_questions`.
  - On edited accepts: also inserts a `corrections` row capturing the proposed → edited diff with `corrected_by = actor`.
  - Updates `proposed_changes.review_state` to `accepted` / `edited_and_accepted` / `rejected` + `resulting_*_id`.
  - Updates `ingestion_events.review_state` to `committed` / `partial` / `rejected` plus counts.
- **Cache invalidation**: `/`, `/subs`, `/v2/review`, `/v2/job/[event.job_id]`.
- **Response**: `{ingestion_event_id, final_state, accepted, rejected, edited, results}`.

### Subs

#### `POST /api/subs/[id]/edit`

- File: `production-cockpit/app/api/subs/[id]/edit/route.ts`.
- **Body**: any of `{name, trade, notes, flagged_for_pm_binder, aliases}`. `aliases` accepts an array or comma string.
- **Writes**: `subs`. No manually_edited_fields needed — subs are insert-only from the scraper.
- **Cache invalidation**: `/subs`, `/sub/[id]`.

#### `POST /api/subs/[id]/delete`

- File: `production-cockpit/app/api/subs/[id]/delete/route.ts`.
- **Body**: `{force?: boolean}`.
- **Writes**: soft delete (`hidden=true`). Two-step UX: without `force`, returns 409 `{requiresForce:true, openTodos}` if any open todos are still attached to this sub.
- **Cache invalidation**: `/subs`, `/sub/[id]`.

#### `POST /api/sub-specialties`

- File: `production-cockpit/app/api/sub-specialties/route.ts`.
- **Body**: `{sub_id, specialty, action:'add'|'remove'|'set_duration', duration_days?}`.
- **Writes**: `sub_specialties` — upsert with `source:'manual'` (add/set_duration) or delete with `source='manual'` (remove). The duration override always wins over the auto streak-based estimate when present.
- **Cache invalidation**: `/sub/[sub_id]`.

#### `POST /api/sub-checklist`

- File: `production-cockpit/app/api/sub-checklist/route.ts`.
- **Body**: `{sub_id, action:'add'|'remove'|'toggle'|'edit', item_id?, lens?, item_text?, is_done?, done_by?, notes?}`.
- **Writes**: `sub_checklist_items` — insert (computes `position = max+1` per lens), delete, update is_done/done_at/done_by, or update item_text.
- **Cache invalidation**: `/sub/[sub_id]`.

### Job AI surfaces

#### `POST /api/jobs/[id]/refresh-summary`

- File: `production-cockpit/app/api/jobs/[id]/refresh-summary/route.ts`. `maxDuration = 60`.
- **Body**: `{window_days?}` (default 30).
- **Reads**: `jobs(id, name, address)`, `daily_logs(... + photo_summary)` for last `windowDays`, open `todos` (top 60), recently-completed `todos` (top 40).
- **External**: Anthropic `claude-opus-4-7` with tool-use (`emit_job_summary`) for structured output (`headline, phase, whats_happening, subs_recently_on_site, open_concerns, coming_up, inspections_recent, safety_flags, confidence`).
- **Writes**: `job_summaries` insert (keeps history; latest wins on read). Tolerates missing table — returns the summary with `persisted:false, persist_hint:"apply migrations..."` if insert fails.
- **Cache invalidation**: `/v2/job/[id]` on success.
- **Response**: `{ok, summary, meta:{generated_at, log_count, photo_count, open_todo_count, done_todo_count, last_data_through, model, elapsed_ms}, persisted, persist_error}`.

#### `POST /api/jobs/[id]/process-pending`

- File: `production-cockpit/app/api/jobs/[id]/process-pending/route.ts`. `maxDuration = 120`.
- **Body**: none.
- **Reads**: `jobs(id, name)`; `daily_logs(id, photo_urls, photo_summary)` `ilike job_key, '<job.name>%'`, `photo_summary is null`, limit 200; filters in code to ones with non-empty photo_urls.
- **External**: same-origin `fetch` to `/v2/api/daily-logs/extract-photos` with `{log_ids, limit:log_ids.length}` to reuse the vision pipeline.
- **Response**: passthrough of the extract-photos response.

#### `POST /api/jobs/[id]/client-summary`

- File: `production-cockpit/app/api/jobs/[id]/client-summary/route.ts`. `maxDuration = 60`.
- **Body**: `{period?: 'weekly'|'monthly'}`.
- **Reads**: `jobs`, `pay_app_line_items(scheduled_value, total_completed)`, `purchase_orders(cost, amount_remaining)`, recent `daily_logs`, open `todos` (`category='SELECTION'` filtered separately).
- **External**: Anthropic `claude-opus-4-7` tool-use (`emit_client_summary`) → `{greeting, budget, schedule, upcoming_selections[], whats_next[], closing}`. Warm homeowner-facing tone.
- **Writes**: nothing — generated on demand, returned to the panel for a copy button.
- **Response**: `{ok, period, summary, meta:{percent_complete, log_count, upcoming_count, selection_count, elapsed_ms}}`.

### Legacy transcript import

#### `POST /api/import-transcript`

- File: `production-cockpit/app/api/import-transcript/route.ts`. `maxDuration = 60`.
- **Body**: `{transcript, pm_id, pm_name, meeting_date, meeting_type:'SITE'|'OFFICE'|'OTHER'}`.
- **Reads**: `subs(id, name, aliases)` for the catalog Claude canonicalizes against.
- **External**: Anthropic `claude-opus-4-7` tool-use (`emit_action_items`) → `{summary, jobs_mentioned[], items[]}`. Each item has `{title, sub_name, job, priority, due_date, suggested_due_date, suggested_due_date_reason, category, type, source_excerpt}`.
- **Post-processing**: every title goes through `scrubRelativeDates(item.title, meeting_date)` — defence-in-depth against relative-time phrases (matches the project rule that titles carry exact YYYY-MM-DD or no timeframe).
- **Writes**: nothing — this is the preview pass. The user accepts in the modal, then `/api/save-extracted-todos` persists.
- **Response**: `{ok, summary, jobs_mentioned, grouped:[{sub_id, sub_name, items[]}], totalItems}`.

#### `POST /api/save-extracted-todos`

- File: `production-cockpit/app/api/save-extracted-todos/route.ts`.
- **Body**: `{pm_id, meeting_date, source_label?, items:[{title, sub_id, job, priority, due_date, category, type}]}`.
- **Dedup gate**: if `source_label` already appears in `todos.source_transcript`, returns 409 `{duplicate:true, error}` — hard guarantee that re-uploading a transcript can't create duplicates.
- **Writes**: `todos` upsert `onConflict:"id"`. IDs are `<JOB_PREFIX>-C<base36-ts>` (collision-free with binder-derived `<JOB_PREFIX>-<###>` ids). Every title passes through `scrubRelativeDates(title, meeting_date)` again at the save boundary.
- **Cache invalidation**: `/`, `/subs`, `/sub/[sub_id]` per unique sub, `/v2/job/<slug>` for every distinct job name (slug = `job.toLowerCase().replace(/[^a-z0-9]+/g,'')`).
- **Response**: `{ok, saved}`.

---


---

## §7 AI CALLS

Four Claude call sites, all using the Anthropic SDK directly and ALL using tool-use to guarantee structured output. The "why tool-use" story is the same across all four — see the boxed note below.

> **Why tool-use everywhere:** the v1 implementations parsed `JSON.parse(claude.text)` and occasionally 502'd when Claude returned malformed free-text JSON (unescaped chars in long extractions, code fences, prose preambles). Switching to tool-use makes the SDK return a typed `tool_use.input` object that the schema validator on Anthropic's side guarantees is well-formed. No regex, no `JSON.parse`, no 502s from malformed JSON. Adopted across the four call sites between 2026-04-08 and 2026-05-12; the call site comments specifically reference the "Generate Summary 502" backstory.

All four call `claude-opus-4-7`. None of them stream; they all read the response synchronously, find the `tool_use` block, and treat `toolUse.input` as the typed payload.

---

### 7.1 Job summary — `POST /api/jobs/[id]/refresh-summary`

- **Trigger:** "Generate Summary" / "Refresh Summary" button on `/v2/job/[job_id]`.
- **Input:** assembled from Supabase in parallel:
  - `jobs` row (`id, name, address`).
  - Last 30 days of `daily_logs` for the job (max 60), selecting `log_date, job_key, crews_present, parent_group_activities, daily_workforce, crew_counts, inspections, notes, photo_summary, photo_urls`, ordered `log_date DESC`. Joined by `job_key ILIKE \`${name}%\``.
  - Open `todos` (`status IN NOT_STARTED|IN_PROGRESS|BLOCKED`), max 60, joined on `job = jobs.name`, includes `sub:subs(name)`.
  - Recently-completed `todos` (status=COMPLETE, `completed_at` within window), max 40.
  - Counts derived locally: `photoCount = sum(log.photo_urls.length)`, `lastDataThrough = logs[0].log_date`.
- **Early return:** if `logs.length === 0 && openTodos.length === 0` → 400 "Nothing to summarize". If `ANTHROPIC_API_KEY` missing → 500.
- **Model:** `claude-opus-4-7`. **Max tokens:** 4000.
- **Tool name:** `emit_job_summary`. **`tool_choice`:** `{ type: "tool", name: "emit_job_summary" }`.
- **`input_schema`** (verbatim):
  ```ts
  {
    type: "object",
    properties: {
      headline: { type: "string" },
      phase: { type: ["string", "null"] },
      whats_happening: { type: "array", items: { type: "string" } },
      subs_recently_on_site: {
        type: "array",
        items: {
          type: "object",
          properties: {
            name: { type: "string" },
            days: { type: "integer" },
            primary_activity: { type: ["string", "null"] },
          },
          required: ["name", "days"],
        },
      },
      open_concerns: {
        type: "array",
        items: {
          type: "object",
          properties: {
            text: { type: "string" },
            priority: { type: "string", enum: ["URGENT", "HIGH", "NORMAL"] },
            owner: { type: ["string", "null"] },
          },
          required: ["text", "priority"],
        },
      },
      coming_up: { type: "array", items: { type: "string" } },
      inspections_recent: { type: "array", items: { type: "string" } },
      safety_flags: { type: "array", items: { type: "string" } },
      confidence: { type: "string", enum: ["high", "medium", "low"] },
    },
    required: [
      "headline",
      "whats_happening",
      "subs_recently_on_site",
      "open_concerns",
      "coming_up",
      "inspections_recent",
      "safety_flags",
      "confidence",
    ],
  }
  ```
- **Prompt** (verbatim; built by `buildPrompt(job, windowDays, logs, openTodos, doneTodos)`):
  ```
  You are summarizing a Ross Built custom-home job for the Monday meeting binder.

  JOB:
  - name: ${job.name}
  - address: ${job.address ?? "(unknown)"}
  - as of: ${todayIso}
  - window: last ${windowDays} days of daily logs + open todos + recently completed todos

  DAILY LOGS (${logs.length} entries; newest first):
  ${JSON.stringify(logs, null, 2)}

  OPEN TODOS (${openTodos.length}):
  ${JSON.stringify(openTodos, null, 2)}

  RECENTLY COMPLETED TODOS (${doneTodos.length}):
  ${JSON.stringify(doneTodos, null, 2)}

  Return ONE JSON object with this exact shape:

  {
    "headline": "<≤120 chars one-sentence current state of the job>",
    "phase": "<one of: site prep, foundation, framing, dry-in, rough-in, drywall, finishes, exterior, punch, closeout, or null if ambiguous>",
    "whats_happening": ["<3-7 concrete observations from the last 2 weeks>"],
    "subs_recently_on_site": [
      {"name": "<sub name>", "days": <int days on site in window>, "primary_activity": "<what they were doing, or null>"}
    ],
    "open_concerns": [
      {"text": "<≤200 chars>", "priority": "URGENT|HIGH|NORMAL", "owner": "<who owns it, or null>"}
    ],
    "coming_up": ["<2-5 items committed for the next 1-2 weeks>"],
    "inspections_recent": ["<inspection name + result + date, one per line>"],
    "safety_flags": ["<any safety hazard surfaced in photo_summary or notes; EMPTY if none>"],
    "confidence": "high|medium|low"
  }

  Rules:
  - "whats_happening" comes from a synthesis of daily log notes + photo_summaries. Use the actual sub names and activities present in the data.
  - "subs_recently_on_site" counts unique log dates where the sub appears in crews_present in the window. Order by days desc.
  - "open_concerns" prioritizes URGENT todos, past-due items, and items mentioned in safety_flags or hazards.
  - "coming_up" pulls due dates in the next 14 days from open todos + any "next week" mentions in recent notes — written with explicit dates, not "next week".
  - Lower confidence to "medium" if photo_summary is null on most recent logs, "low" if there are fewer than 3 logs in the window.
  - Return ONLY the JSON. No prose, no fences.
  ```
- **Output handling:**
  ```ts
  const toolUse = resp.content.find((b) => b.type === "tool_use");
  if (!toolUse || toolUse.type !== "tool_use") return 502;
  parsed = toolUse.input as JobSummary;
  ```
  No `JSON.parse`, no regex — `toolUse.input` is already the typed object.
- **Where it lands:** inserted as a new row in `job_summaries` with `job_id, summary, last_data_through, log_count, photo_count, open_todo_count, done_todo_count, model, elapsed_ms`. If the insert fails (typically: table missing because migrations haven't been applied), the route still returns the summary to the UI with `persisted: false` + a hint to apply migrations — Claude work doesn't get wasted.
- **Cache-bust:** `revalidatePath(\`/v2/job/${job.id}\`)` on successful persist.
- **Hard limits:**
  - `maxDuration = 60` (function ceiling).
  - `max_tokens: 4000`.
  - `windowDays` default 30, configurable via body.
  - `daily_logs.limit(60)`, open todos `.limit(60)`, done todos `.limit(40)`.

### 7.2 Client-facing summary — `POST /api/jobs/[id]/client-summary`

- **Trigger:** "Generate Client Update" button on `/v2/job/[id]`. UI exposes a copy button for sharing.
- **Body:** `{ period?: "weekly" | "monthly" }` (default `"weekly"`). Maps to `lookbackDays` (10/35) and `lookaheadDays` (14/35).
- **Input:** parallel Supabase reads:
  - `jobs` row.
  - `pay_app_line_items` for the job: `scheduled_value, total_completed` → rolled up into `sched`, `comp`, `pct`.
  - `purchase_orders` not hidden: `cost, amount_remaining` → `committed`, `outstanding`.
  - `daily_logs` in window (max 40), ordered desc.
  - Open `todos` (max 100). Filtered locally into `upcoming` (due in `[today, today+lookahead]`) and `selections` (category=`SELECTION`).
  - Computed `data` object passed verbatim into the prompt: `contract_value, billed_to_date, percent_complete, committed_to_vendors, open_commitments, recent_activity, upcoming_tasks, pending_selections`.
- **Early return:** if `logs.length===0 && openTodos.length===0 && sched===0` → 400.
- **Model:** `claude-opus-4-7`. **Max tokens:** 2000.
- **Tool name:** `emit_client_summary`.
- **`input_schema`** (verbatim):
  ```ts
  {
    type: "object",
    properties: {
      greeting: { type: "string" },
      budget: { type: "string" },
      schedule: { type: "string" },
      upcoming_selections: { type: "array", items: { type: "string" } },
      whats_next: { type: "array", items: { type: "string" } },
      closing: { type: "string" },
    },
    required: ["greeting", "budget", "schedule", "upcoming_selections", "whats_next", "closing"],
  }
  ```
- **Prompt** (verbatim, with `${period}`, `${job.name}`, `${todayIso}`, `${JSON.stringify(data, null, 2)}` interpolated at call time):
  ```
  You are writing a ${period} construction update FOR THE HOMEOWNER CLIENT of a Ross Built custom home. Warm, clear, confident, and honest — no internal jargon, no sub names unless helpful, no to-do IDs. Speak to the client about THEIR home.

  JOB: ${job.name}${job.address ? ` — ${job.address}` : ""}
  AS OF: ${todayIso}  (period: ${period})

  DATA (already computed; budget figures are exact dollars):
  ${JSON.stringify(data, null, 2)}

  Write a ${period} update with:
  - greeting: one warm sentence naming their home/project and the period.
  - budget: 2-3 sentences on where the budget stands — contract value, how much is complete/billed, percent complete, and what's committed/outstanding — framed reassuringly but truthfully. If a figure is "unknown", omit it gracefully rather than saying "unknown".
  - schedule: 2-4 sentences on what's been accomplished recently (synthesize recent_activity) and whether things are progressing well.
  - upcoming_selections: a list of decisions/selections the client should make soon (from pending_selections + any selection-type upcoming_tasks), each with rough timing if known. EMPTY list if none.
  - whats_next: 2-4 short bullets of what happens next on site (from upcoming_tasks), in plain client language with dates where known.
  - closing: one friendly closing line inviting questions.

  Return ONLY via the tool.
  ```
- **Output handling:** same `resp.content.find(b => b.type === "tool_use")` pattern; `toolUse.input as ClientSummary`.
- **Where it lands:** NOT persisted. Returned to the UI in the response body:
  ```ts
  { ok: true, period, summary, meta: { percent_complete, log_count, upcoming_count, selection_count, elapsed_ms } }
  ```
  The client-facing copy is treated as a draft — Jake reads it before sharing.
- **Hard limits:**
  - `maxDuration = 60`.
  - `max_tokens: 2000`.
  - `daily_logs.limit(40)`, `todos.limit(100)`.
  - `purchase_orders` filtered to `hidden=false`.

### 7.3 Transcript action-item extractor — `POST /api/import-transcript`

- **Trigger:** `/import` page submit. UI also caps transcript length ≥100 chars.
- **Body:** `{ transcript, pm_id, pm_name, meeting_date, meeting_type?: "SITE"|"OFFICE"|"OTHER" }` (default `SITE`).
- **Input pre-load:** the full `subs` catalog (`id, name, aliases`) so the prompt can ask Claude to canonicalize references to the EXACT names — see the `KNOWN SUBS` block in the prompt below.
- **Early return:** transcript shorter than 100 chars, missing required fields, or missing `ANTHROPIC_API_KEY`.
- **Model:** `claude-opus-4-7`. **Max tokens:** 8000.
- **Tool name:** `emit_action_items`.
- **`input_schema`** (verbatim):
  ```ts
  {
    type: "object",
    properties: {
      summary: { type: "string" },
      jobs_mentioned: { type: "array", items: { type: "string" } },
      items: {
        type: "array",
        items: {
          type: "object",
          properties: {
            title: { type: "string" },
            sub_name: { type: ["string", "null"] },
            job: { type: "string" },
            priority: {
              type: "string",
              enum: ["URGENT", "HIGH", "NORMAL"],
            },
            due_date: { type: ["string", "null"] },
            suggested_due_date: { type: ["string", "null"] },
            suggested_due_date_reason: { type: ["string", "null"] },
            category: {
              type: "string",
              enum: [
                "SELECTION",
                "SCHEDULE",
                "PROCUREMENT",
                "SUB-TRADE",
                "CLIENT",
                "QUALITY",
                "BUDGET",
                "ADMIN",
              ],
            },
            type: {
              type: "string",
              enum: [
                "SELECTION",
                "CONFIRMATION",
                "PRICING",
                "SCHEDULE",
                "CO_INVOICE",
                "FIELD",
                "FOLLOWUP",
              ],
            },
            source_excerpt: { type: ["string", "null"] },
          },
          required: ["title", "job", "priority", "category", "type"],
        },
      },
    },
    required: ["summary", "jobs_mentioned", "items"],
  }
  ```
- **Prompt** (verbatim, abbreviated header — the long `buildPrompt(transcript, pmName, meetingDate, meetingType, subCatalog)` body):
  ```
  You are extracting action items from a Ross Built construction meeting transcript.

  META: PM=${pmName} | Date=${meetingDate} | Type=${meetingType}

  KNOWN SUBS (canonicalize references to these exact "name" strings — match aliases first, then partial/last-name matches; only leave sub_name null if no sub is plausibly referenced):
  ${catalog}

  Read the transcript. Return a JSON object with this exact shape:

  {
    "summary": "<1-2 sentence overview of the meeting>",
    "jobs_mentioned": ["<job-name>", ...],
    "items": [
      {
        "title": "<owner + verb + specific deliverable + hard due date>",
        "sub_name": "<exact name from catalog above, or null>",
        "job": "<job name — Fish, Krauss, Markgraf, Pou, Dewberry, Drummond, Molinari, Ruthven, Biales, Harllee, Clark, Johnson, etc.>",
        "priority": "URGENT" | "HIGH" | "NORMAL",
        "due_date": "<YYYY-MM-DD or null>",
        "suggested_due_date": "<YYYY-MM-DD — your best-guess fallback even when due_date is null>",
        "suggested_due_date_reason": "<≤80 chars explaining why this date>",
        "category": "SELECTION|SCHEDULE|PROCUREMENT|SUB-TRADE|CLIENT|QUALITY|BUDGET|ADMIN",
        "type": "SELECTION|CONFIRMATION|PRICING|SCHEDULE|CO_INVOICE|FIELD|FOLLOWUP",
        "source_excerpt": "<≤200 chars verbatim transcript snippet that grounds this item>"
      }
    ]
  }

  AUTO-MATCH RULES (do these before emitting any item):

  1. SUB MATCHING — work hard to fill sub_name. If the speaker says "Terry", check the aliases in the catalog above. If they say "Walter", match "Walter Drywall". If they say "Watts", match "Jeff Watts Plastering and Stucco". Only return null when the action is genuinely PM-internal (Lee to send X, Jake to draft Y) AND no sub is named.

  2. DATE INFERENCE from the meeting date ${meetingDate}:
     - "today" → ${meetingDate}
     - "tomorrow" → meeting_date + 1 day
     - "by Friday" / "this Friday" → next Friday on or after meeting_date
     - "by next week" / "early next week" → meeting_date + 7 days
     - "by end of month" → last day of meeting_date's month
     - "by [Month] [Day]" → resolve to YYYY-MM-DD using meeting_date's year (or next year if the date already passed)
     Return YYYY-MM-DD in due_date. Leave due_date null only if the transcript is genuinely open-ended.

     TITLE-DATE RULE — STRICT:
     The "title" field must NEVER contain a relative-time phrase. Forbidden
     substrings (case-insensitive): "today", "tomorrow", "yesterday", "tonight",
     "this week", "next week", "this month", "next month", "by Friday",
     "by Monday", "by [any weekday]", "this Friday", "next Friday",
     "this [weekday]", "end of week", "end of month", "soon", "ASAP",
     "in a few days", "shortly".

     If the action has a date, write the resolved YYYY-MM-DD into the title
     instead, e.g. "Walter to confirm drywall start 2026-05-22" — not
     "Walter to confirm drywall start tomorrow". If the action is
     genuinely open-ended, leave the date out of the title entirely
     (the due_date and suggested_due_date fields carry timing — the title
     should not duplicate or paraphrase relative time).

     If you find yourself writing one of the forbidden phrases, STOP, look up
     the resolved YYYY-MM-DD via the rules above, and substitute it.

     SUGGESTED FALLBACK (suggested_due_date) — ALWAYS populate this, even when
     due_date is set. When due_date has a value, suggested_due_date should
     equal it. When due_date is null, infer a sensible fallback from priority
     + category (each builds off meeting_date ${meetingDate}):
       • URGENT → meeting_date + 3 days
       • HIGH → meeting_date + 7 days
       • NORMAL + SELECTION/CLIENT → meeting_date + 14 days
       • NORMAL + SCHEDULE/PROCUREMENT/SUB-TRADE/QUALITY → meeting_date + 10 days
       • NORMAL + BUDGET/ADMIN → meeting_date + 21 days
     Write a short suggested_due_date_reason (≤80 chars) explaining the pick,
     e.g. "urgent — 3-day buffer" or "no explicit date, NORMAL procurement default".

  3. CATEGORY INFERENCE — pick the most specific:
     - SELECTION = waiting on client/designer choice (colors, fixtures, finishes, hardware, paint specs)
     - SCHEDULE = sub start/end dates, sequencing, moves
     - PROCUREMENT = orders, deliveries, vendor buyouts, lead times
     - SUB-TRADE = sub performance concerns / quality / back-charges (NOT routine scheduling)
     - CLIENT = client communication, status updates, written approvals
     - QUALITY = quality assurance, rework, callbacks, hinge replacements, paint touch-ups
     - BUDGET = pricing, change orders, cost coding, back-charges with $ amounts
     - ADMIN = permits, policies, internal documents, company-wide rules

  4. JOBS_MENTIONED — list every job name that appears in the transcript, even ones with no action items. The operator may need to check those job pages too. Dedupe but keep them.

  5. SOURCE_EXCERPT — for each item, copy 1-3 sentences verbatim from the transcript that contain the trigger phrase. Cap at 200 characters with an ellipsis if you have to. DO NOT paraphrase. If you cannot find a quotable line, DROP THE ITEM — do not include it.

  6. Every item must pass the Monday Morning Test: specific person + specific verb + specific deliverable + hard date.

  7. Priority: URGENT if due ≤3 days or blocks critical path or has financial exposure; HIGH if due ≤7 days or involves sub coordination; NORMAL otherwise.

  NEVER fabricate. If the transcript is vague, drop the item. The source_excerpt check is your honesty gate.

  Return ONLY the JSON. No prose, no fences.
  ```
  The transcript itself is appended below the prompt:
  ```ts
  content: `${prompt}\n\n---\n\nTRANSCRIPT:\n${transcript}`
  ```
- **Output handling:**
  ```ts
  const toolUse = resp.content.find((b) => b.type === "tool_use");
  parsed = toolUse.input as ExtractionResult;
  ```
  Then a post-pass scrub: every `item.title = scrubRelativeDates(item.title, meetingDate)` (`lib/scrub-relative-dates.ts`). Defence-in-depth — Claude occasionally still slips a relative phrase past the prompt; the scrub resolves every supported phrase to YYYY-MM-DD against the meeting date and strips genuinely vague spans (`ASAP`, `soon`, `this week`). Same util runs at the save boundary so manual edits can't reintroduce one.
  Then sub canonicalization: `sub_name` → `sub_id` lookup against the `subByName` map (lowercased). Items grouped per sub for the preview screen.
- **Where it lands:** the preview screen sends to `/api/save-extracted-todos` which writes rows into `todos`. So:
  - This route returns the structured `grouped` payload to the UI.
  - The UI lets the operator edit/drop items before save.
  - The save route writes `todos` rows.
- **Hard limits:**
  - `maxDuration = 60`.
  - `max_tokens: 8000` (transcripts can produce many items).
  - Transcript ≥100 chars enforced.

### 7.4 Photo vision — `POST /v2/api/daily-logs/extract-photos`

- **Trigger:** "Extract photo summaries" button on `/v2/upload` (or background fill). UI cap of 50 logs per click; default 10.
- **Body:** `{ log_ids?: string[], limit?: number }` (default `{ limit: 10 }`).
- **Input selection:** `daily_logs` rows where `photo_urls IS NOT NULL` AND (if `log_ids` not provided) `photo_summary IS NULL`, ordered `log_date DESC`, limited to `limit`.
- **Photo handling per row:** up to 6 photos (`MAX_PHOTOS_PER_LOG = 6`). Each URL is classified:
  - HTTP(S) URL → `{ type: "image", source: { type: "url", url: src } }`.
  - Local Windows/POSIX path (e.g. `C:\Users\Greg\buildertrend-scraper\photos\...`) → `fs.readFile` + base64-encode + `{ type: "image", source: { type: "base64", media_type, data } }`. Media type sniffed by extension (`.png` / `.webp` / `.gif` / default jpeg).
  - Unreadable file → counted as `skipped`, log not failed unless ALL photos are unreadable (in which case the per-log result returns `ok:false` with an error message).
- **Model:** `claude-opus-4-7`. **Max tokens:** 1200 per log.
- **Tool name:** `emit_photo_summary`.
- **`input_schema`** (verbatim):
  ```ts
  {
    type: "object",
    properties: {
      headline: { type: "string" },
      work_stage: { type: ["string", "null"] },
      subs_visible: { type: "array", items: { type: "string" } },
      work_observed: { type: "array", items: { type: "string" } },
      hazards: { type: "array", items: { type: "string" } },
      weather_notes: { type: ["string", "null"] },
      confidence: { type: "string", enum: ["high", "medium", "low"] },
    },
    required: [
      "headline",
      "subs_visible",
      "work_observed",
      "hazards",
      "confidence",
    ],
  }
  ```
- **Prompt** (verbatim; the `ctxBlock` is conditionally prepended when the row has metadata):
  ```
  Date: ${row.log_date}
  Job: ${row.job_key}
  Crews on site (per BT): ${row.crews_present.join(", ")}
  Activities tagged: ${row.parent_group_activities.join(", ")}
  PM notes: ${row.notes.slice(0, 600)}

  You are summarizing the photos from a single Buildertrend daily log on a Ross Built custom-home job. Look at every photo and return ONE JSON object with this exact shape:

  {
    "headline": "<≤80 chars — one-sentence what's happening overall>",
    "work_stage": "<one of: site prep, foundation, framing, dry-in, rough-in, drywall, finish, exterior, punch, or null if mixed/unclear>",
    "subs_visible": ["<branded trade names visible on shirts/vehicles, else trade nouns like 'electrician', 'framer'>"],
    "work_observed": ["<concrete observation 1>", "<observation 2>", "..."],
    "hazards": ["<safety concern — open trenches, missing fall protection, exposed wire, etc. EMPTY array if none>"],
    "weather_notes": "<conditions visible in photos (sun, rain, mud, standing water) or null>",
    "confidence": "high|medium|low"
  }

  Rules:
  - If the photos do not actually show construction (e.g. blank office photos, screenshots), return confidence "low" and put a note in headline.
  - Do NOT invent subs or work that isn't visible.
  - The "work_observed" array is the main payload — 3-7 specific items is ideal.
  - Return ONLY the JSON, no prose, no fences.
  ```
  Message structure: `messages: [{ role: "user", content: [...imageBlocks, { type: "text", text: buildPrompt(row) }] }]` — images first, then the text prompt.
- **Output handling:** `toolUse.input as ExtractedSummary`. One Claude call per log so a single failure doesn't poison the batch — errors are accumulated in the per-log result object.
- **Where it lands:**
  ```ts
  await supabase.from("daily_logs")
    .update({ photo_summary: parsed, photo_summary_at: new Date().toISOString() })
    .eq("id", row.id);
  ```
  `photo_summary` is jsonb so the object is stored directly.
- **Cache-bust:** `revalidatePath("/sub/[id]", "page")` and `revalidatePath("/subs")` once at the end (sub profiles render photo_summary blurbs).
- **Hard limits:**
  - `maxDuration = 120` (vision is slower).
  - `max_tokens: 1200` per log.
  - 6 photos max per log (`MAX_PHOTOS_PER_LOG`).
  - 10 logs per batch by default, capped at 50 (`Math.min(50, body.limit ?? 10)`).
  - Local file paths supported alongside URLs so the scraper-driven flow works without a public host.

---

### Add a new AI call — 6-step recipe

When wiring a fifth Claude call (e.g. "generate weekly subcontractor performance brief"), follow the exact pattern above:

1. **Define the schema first.** Write the `input_schema` JSON Schema BEFORE the prompt. Decide every field, type, enum, and `required` array. The schema IS the contract.
2. **Wire the tool-use call.** `new Anthropic({ apiKey })`, `client.messages.create({ model: "claude-opus-4-7", max_tokens, tools: [tool], tool_choice: { type: "tool", name: "<tool_name>" }, messages: [...] })`. Always force the tool with `tool_choice` — never leave it optional.
3. **Store the result.** Pick a column or new table. If it's a jsonb column, write the object verbatim. If it's a new table, mirror the `job_summaries` pattern (history kept, meta counts, model + elapsed_ms recorded).
4. **Render it.** A server component reads the latest row; a button POSTs to the API route to refresh.
5. **Cache-bust on persist.** `revalidatePath(\`/v2/job/${jobId}\`)` (or whatever route renders the data) immediately after the insert succeeds. Without this the UI shows stale data for ISR / static-rendered pages.
6. **NO `JSON.parse`.** Use `resp.content.find(b => b.type === "tool_use")` and cast `toolUse.input` to your typed interface. Tool-use guarantees structure; parsing free-text JSON is the failure mode the schema migration was designed to eliminate.

Additional rules that come up:
- Always check for `ANTHROPIC_API_KEY` at the top of the route and return a clean 500 if missing.
- Always set `export const dynamic = "force-dynamic"` and an appropriate `maxDuration` (60s for text, 120s for vision).
- If you read jsonb columns to assemble context, JSON.stringify them with `null, 2` for the prompt — model reads structured nicely.
- If the model occasionally drifts in a column the schema can't constrain (e.g. relative-date phrases in free-text titles), add a post-pass scrub like `scrubRelativeDates` and run it at BOTH the API boundary AND the save boundary.

---

## §8 PYTHON PIPELINE

This is the "offline brain" of the Ross Built system. Python code lives in the `weekly-meetings/` repo and runs as a sequence of scripts (no long-running daemon). It reads transcripts off disk, calls Claude (Opus 4.7 for reasoning, Haiku 4.5 for cheap classification), writes binder JSONs and Supabase rows, and produces the analytics that feed the Monday Binder + cockpit dashboards.

There are two layers of brain in this repo, and they coexist:

- **v1 brain** = `process.py` at the repo root. One Opus call per transcript, takes the prior PM binder + new transcript and produces a merged binder. This is what runs on Monday and feeds `binders/<PM>.json` + the live `todos` table.
- **v2 brain** = `scripts/brain/` (Extractor → Reconciler → Auditor). Three separable Opus calls per meeting, claim-grained traceability, writes to the v2 schema (`meetings`, `claims`, `items`, `decisions`, `open_questions`, `proposed_changes`). Built out under Gates 1B–1F, not yet wired into the Monday flow; runs against the same transcripts as a parallel pipeline.

### `process.py` — v1 transcript processor (THE Monday job)

`P:/Claude Projects/weekly-meetings/process.py`

One-line role: walk `transcripts/inbox/`, for each `.txt`, call Opus 4.7 with the prior binder + transcript + 14-day BT daily-log context, validate the returned JSON, atomic-write `binders/<PM>.json`, mirror to Supabase `todos`, move the transcript to `processed/`.

- **Inputs**:
  - `transcripts/inbox/*.txt` — Plaud transcripts. Filename parsing accepts ISO `YYYY-MM-DD`, `MM-DD`, `M_D_YY`, `M-D-YY`, `M/D/YY` and either first-name (`Martin`) or job-name (`Krauss`) tokens; meeting type derived from `site`/`office` substring.
  - `binders/<PM>.json` — prior binder; v1 source of truth.
  - `weekly-prompt.md` — the giant Opus prompt template.
  - Buildertrend daily-log JSON via `fetch_daily_logs.fetch_for_pm(...)` (14-day window).
  - `state/processing-ledger.jsonl` — SHA-256 dedupe ledger.
- **Outputs**:
  - `binders/<PM>.json` — atomic write (sibling `.tmp` + `os.replace`).
  - Supabase `todos` upsert via `sink_to_supabase(...)` with SELECT-then-merge clobber prevention.
  - `api-responses/<PM>_<ts>_raw.txt` — raw model output for audit.
  - `api-responses/<PM>_backup_<ts>.json` — pre-write binder snapshot.
  - `transcripts/processed/<filename>` (success), `transcripts/skipped/<filename>` (unparseable/short).
  - `logs/<YYYY-MM-DD>.log`, `state/processing-ledger.jsonl` append.
- **Key functions**:
  - `main()` — entrypoint.
  - `process_transcript(transcript_file, ledger_index, logger)` — handles one file end-to-end; returns `success | duplicate | previously_failed | failure`.
  - `parse_filename(name)` — date+PM+type extractor; uses `PM_KEYWORDS` built from `constants.PM_JOBS`.
  - `call_claude(...)` — streams Opus 4.7 with `max_tokens=32000`, extracts the JSON code block, saves raw response.
  - `migrate_binder_items(...)` — legacy-status migration (OPEN→NOT_STARTED, KILLED→COMPLETE w/ kill reason preserved).
  - `compute_item_aging(...)` — stamps `days_open`, `days_overdue`, `aging_flag` (fresh/aging/stale/abandoned), `escalation_level`.
  - `validate_binder(...)` — soft validation; defaults priority/status/category rather than rejecting.
  - `sink_to_supabase(...)` — upserts `todos`. **SELECT-then-merge** rule: if Supabase shows `COMPLETE` with non-null `completed_at`, force-preserve it; if `edited_title` exists, preserve it + `edited_at`. Everything else (title, priority, due_date, etc.) LLM wins. Aborts the upsert if the pre-merge SELECT fails — never clobber blindly.
  - `_extract_sub_id(...)` — alias-index regex match against `subs` table to tag each todo with its `sub_id`.
  - `append_ledger_record(...)` — O_APPEND-atomic JSONL writes (sub-PIPE_BUF payloads).
- **Dependencies**: `fetch_daily_logs`, `constants`. No other in-repo modules; runs standalone.
- **Anthropic calls**: 1 per transcript. Model `claude-opus-4-7`, `max_tokens=32000`, streaming required because Opus + 32K tokens routinely exceeds the 10-min single-shot timeout. Prompt = `weekly-prompt.md` + prior binder JSON + transcript + daily-log context.

### `fetch_daily_logs.py` — BT daily-log loader for the Monday prompt

`P:/Claude Projects/weekly-meetings/fetch_daily_logs.py`

One-line role: given a PM + meeting date, read the scraper output and return a 14-day summary + raw entries scoped to that PM's jobs.

- **Inputs**: `DAILY_LOGS_PATH` from `constants.py` — resolves env `BT_DAILY_LOGS_PATH` → `C:/Users/Greg/buildertrend-scraper/data/daily-logs.json` → `C:/Users/Jake/buildertrend-scraper/data/daily-logs.json`.
- **Outputs** (return value): `{summary: {short_name: {...}}, raw_entries: [...], meta: {...}}`. `meta.stale=true` if `lastRun > 48h`; `meta.error` set on missing/invalid file.
- **Key functions**: `fetch_for_pm(pm_name, meeting_date, lookback_days=14)`, `_build_summary(...)`.
- **Dependencies**: `constants` (PM_JOBS, JOB_NAME_MAP, DAILY_LOGS_PATH). Pure-Python, no API calls.
- Handles enriched vs legacy log records (the BT scraper migration left both shapes in flight); enriched records contribute to `workforce_stats`, `absent_crew_frequency`, `activity_tag_frequency`, `notable_activities`, `inspection_events`, `delivery_events`. Truncates `raw_entries` to 50.

### `validate_accountability.py` — week-over-week commitment diff

`P:/Claude Projects/weekly-meetings/validate_accountability.py`

One-line role: diff this week's `meeting-commitments.json` snapshot vs last week's; produce closed / carried / new / stuck-3w+ buckets + 80%+ text-similarity near-miss detection.

- **Inputs**: `data/meeting-commitments.json` (built upstream by `monday-binder/build_meeting_prep.py`).
- **Outputs**: `data/accountability-week-<iso_week>.md`; single-line status banner to stdout for Task Scheduler logs.
- **Key functions**: `main()`, `text_similarity(a,b)` (`difflib.SequenceMatcher`).
- **Anthropic calls**: none. Pure-Python diff.

### `constants.py` — single source of truth for PM/job/status taxonomy

`P:/Claude Projects/weekly-meetings/constants.py`

This file is mirrored across the system. Touching it without also touching the cockpit's `production-cockpit/buildertrend-scraper/jobs.py` and the scraper repo's `C:/Users/Greg/buildertrend-scraper/jobs.py` will produce silent drift.

- **`PM_JOBS`** — PM canonical name → list of job short names:
  ```
  "Martin Mannix":   ["Fish"]
  "Jason Szykulski": ["Pou", "Dewberry", "Harllee"]
  "Lee Worthy":      ["Krauss", "Ruthven"]
  "Bob Mozine":      ["Drummond", "Molinari", "Biales"]
  "Nelson Belanger": ["Markgraf", "Clark", "Johnson"]
  ```
- **`JOB_NAME_MAP`** — short → full BT key (e.g. `"Krauss"` → `"Krauss-427 South Blvd of the Presidents"`). The full key is the long form BT uses internally for daily-log titles and `byJob` keys in scraper output. **`jobs.py` in the scraper repo and `production-cockpit/buildertrend-scraper/jobs.py` mirror this exactly.**
- **`JOB_TO_PM`** — derived reverse map, so the two can't drift.
- **`PM_ORDER`** — alphabetical-by-last-name render order for the Monday binder.
- **`OLD_TO_NEW_STATUS`** — migration map for pre-taxonomy binders: `OPEN→NOT_STARTED`, `IN PROGRESS→IN_PROGRESS`, `DONE→COMPLETE`, `KILLED→COMPLETE` (with reason preserved), `BLOCKED→BLOCKED`, `DISMISSED→DISMISSED`.
- **`CLOSED_STATUSES`** = `{"COMPLETE", "DISMISSED"}` — used everywhere "is this active?" is asked.
- **`DAILY_LOGS_PATH`** — resolved lazily via `_resolve_daily_logs_path()`: env `BT_DAILY_LOGS_PATH` first, then candidates list (Greg's box first, then Jake's), then fall back to the historical default so error messages stay recognizable.

---

### `scripts/run_weekly_pipeline.py` — THE Monday orchestrator

`P:/Claude Projects/weekly-meetings/scripts/run_weekly_pipeline.py`

One-line role: end-to-end Monday pipeline. Pre-flight checks → 7 steps → dashboard server restart → URL verification → final READY-FOR-MONDAY / NEEDS-ATTENTION report.

- **Inputs**: `config/thresholds.yaml` (`weekly_pipeline.*` keys), the entire repo state.
- **Outputs**: stdout status report; child-process logs at `logs/dashboard-server.log`; touches data files via the steps it spawns.
- **Pre-flight checks** (any aborts halt the run):
  1. `daily-logs.json` freshness — soft warn at `daily_logs_recency_hours`, hard abort at `daily_logs_max_age_hours`.
  2. `transcripts/inbox/` non-empty implies `ANTHROPIC_API_KEY` must be set.
  3. Newest processed transcript age (warn only).
  4. `binders/<PM>.json` present for every required PM.
  5. `classifier.py` exists at the `.planning/` path.
  6. Edge browser binary present (`render_helpers.find_edge()`).
- **Steps** (each step uses the pipeline's Python via `sys.executable`; `PYTHONIOENCODING=utf-8` forced in every child to dodge Windows cp1252):
  1. `process.py` — v1 transcript extraction (no-op if inbox is empty).
  2. `.planning/.../classifier.py` → `data/derived-phases.json`.
  3. `scripts/build_phase_artifacts.py` → derived-phases-v2 + phase-instances + job-stages.
  4. `scripts/build_sub_phase_rollups.py` → bursts + phase-instances-v2 + medians + rollups.
  5. `python -m generators.run_all` → `data/insights.json` + `binders/enriched/`.
  6. `monday-binder/build_meeting_prep.py` → `data/meeting-commitments.json`.
  7. `validate_accountability.py` → `data/accountability-week-<iso>.md`.
- **Server restart**: stop existing dashboard server on `:8765` via PowerShell `Stop-Process`, spawn new `monday-binder/transcript-ui/server.py` detached, poll until responsive.
- **URL verification**: fetch `/meeting-prep/executive.pdf?_orchestrator=<epoch>`, assert `200`, `%PDF-` magic, `>50KB`, and CreationDate within 10 min of now. Anything else → NEEDS ATTENTION.
- **Dependencies**: spawns everything else as child processes. The orchestrator itself has no Anthropic calls.

### `scripts/ingest_extractor_output.py` — Extractor JSON → Supabase

`P:/Claude Projects/weekly-meetings/scripts/ingest_extractor_output.py`

One-line role: take the JSON the v2 Extractor writes for one transcript and persist it as one `meetings` row + N `claims` rows in Supabase.

- **Inputs**: Extractor JSON path + the original transcript `.txt` path (used to compute `source_file_hash` from the transcript bytes, not the JSON — same transcript re-extracted produces the same hash and re-ingests).
- **Outputs**: Supabase `meetings` row + `claims` rows. Idempotent on `meetings.source_file_hash` (UNIQUE); on re-ingest, existing claims for that meeting_id are DELETEd before INSERTs (claims are disposable per the Gate 1E decisions doc).
- **Key functions**: `ingest_meeting(json_path, transcript_path=None, dry_run=False)`.
- **Anthropic calls**: none.

### `scripts/ingest_pay_app.py` — pay app XLSX → Supabase

`P:/Claude Projects/weekly-meetings/scripts/ingest_pay_app.py`

One-line role: parse an AIA G702/G703 pay-app workbook with `pay_app_parser.parse_pay_app(...)` and insert one `pay_apps` row + N `pay_app_line_items` rows.

- **Inputs**: XLSX file path + `job_id`.
- **Outputs**: Supabase `pay_apps` + `pay_app_line_items`. Idempotent on `source_file_hash`; re-ingest of same file is rejected. supabase-py has no cross-table transaction, so a failed line-items batch triggers a manual rollback of the parent row.
- **Key functions**: `ingest_pay_app(file_path, job_id, dry_run=False)`.
- **Anthropic calls**: none.

### `scripts/sync_subs.py`, `ai_link_subs.py`, `backfill_sub_links.py` — sub catalog management

- `scripts/sync_subs.py` — upserts the canonical sub catalog (~50 subs) into the Supabase `subs` table. Catalog is the hardcoded `CATALOG` list at the top of the file: name + trade + aliases. The aliases drive every downstream sub-matching path (regex backfill, runtime extraction in `process.py`, Reconciler stage-1 matching). To add a sub: add it to `CATALOG` and re-run.
- `scripts/backfill_sub_links.py` — for every todo with `sub_id IS NULL`, regex-match title + `source_excerpt` against each sub's aliases. On multi-match, longest-matched-alias wins (so "Tom Sanger" beats "Sanger"). Pure-Python, no API calls.
- `scripts/ai_link_subs.py` — remaining unlinked todos go to **Haiku 4.5** (`claude-haiku-4-5-20251001`) in batches of 25 with the full sub catalog as context. Returns `sub_id` or `"NONE"`. Cheap fallback classifier for cases where the regex misses (e.g. "drywall guy" → HBS Drywall).

### `scripts/dedup_binders.py`, `audit_categories.py`, `backfill_categories.py` — binder cleanup

- `scripts/dedup_binders.py` — post-hoc dedup pass on `binders/*.json`. Groups open items by `(job, owner)`, finds pairs where the first 30 chars of `action` match >85% via `difflib.SequenceMatcher` OR same target_phase + priority + due within 7 days. Keeps the older item, marks newer as `status=DUPLICATE_MERGED` with `merged_into=<older_id>`. Items are never deleted — audit-preserving. CLI: `--dry-run`, `--threshold 0.80`.
- `scripts/backfill_categories.py` — one-time rule-based category classifier. Assigns one of `{SCHEDULE, PROCUREMENT, SUB-TRADE, CLIENT, QUALITY, BUDGET, ADMIN, SELECTION}` to every binder item via type-field defaults + keyword scan. Idempotent unless `--force-reclassify`.
- `scripts/audit_categories.py` — stricter second-pass classifier that fixes systematic miscategorizations from the original backfill (e.g. "QUALITY items mentioning order/PO → PROCUREMENT"). Anything ambiguous gets `_category_review: true` for "?" rendering in templates.

### `scripts/build_phase_artifacts.py`, `build_sub_phase_rollups.py` — schedule-intelligence builders

- `scripts/build_phase_artifacts.py` — Phase 2 of the schedule-intelligence milestone. Reads `config/phase-taxonomy.yaml` + `config/phase-keywords.yaml` + `data/derived-phases.json` (output of the `.planning/.../classifier.py`). Writes `data/derived-phases-v2.json`, `data/phase-instances.json`, `data/job-stages.json`, `data/sequencing-audit.md`. **`TODAY = date(2026, 4, 29)` is hardcoded** — the weekly orchestrator surfaces this as a standing note.
- `scripts/build_sub_phase_rollups.py` — Phase 3 follow-up. Applies a 132-pattern library expansion across 7 target phases, classifies bursts (primary/return/punch/pre_work), produces sub×phase rollups with the PM-binder flag. Outputs `data/bursts.json`, `data/phase-instances-v2.json`, `data/phase-medians.json`, `data/sub-phase-rollups.json`. Same `TODAY = date(2026, 4, 29)` hardcode. Re-writes `derived-phases-v2.json` (the orchestrator notes this dual-write).

### `scripts/run_gate_1c_ingest.py` / `1d6` / `1e_reconcile.py` / `1f_audit.py` — v2 brain quality gates

These are runner scripts for the v2 brain's gated rollout (Gates 1B–1F per the planning doc). They drive the brain modules end-to-end against a fixed test set so each gate's output is auditable in isolation.

- `scripts/run_gate_1c_ingest.py` — ingest 5 known pay-app XLSX files for Krauss/Pou/Dewberry/Fish/Drummond via `ingest_pay_app(...)`. Prints a results table.
- `scripts/run_gate_1d6_ingest.py` — ingest 5 known Extractor JSON outputs via `ingest_meeting(...)`. Reads pre-generated JSONs out of `/tmp/extractor-out-v2/` paired with the source transcripts.
- `scripts/run_gate_1e_reconcile.py` — pulls every meeting from Supabase in date order and runs `reconciler.reconcile_meeting(...)` on each. 4/30 site meetings run first (cold start), 5/07 office meeting last (tests cross-meeting dedup).
- `scripts/run_gate_1f_audit.py` — for every meeting, runs `retry_orchestrator.audit_and_retry(...)` (audit, retry once if `needs_retry`, stop if `needs_review`).

### `scripts/test_*.py` — smoke tests

- `scripts/test_extractor.py` — Gate 1D test: extract claims from 5 real transcripts, save JSON to `/tmp/extractor-out-v2/`, print spend (capped at $5).
- `scripts/test_pay_app_parser.py` — Gate 1B parser smoke test on the Krauss October 2025 pay app. No DB writes.
- `scripts/test_supabase_sink.py` — load every PM binder, run `sink_to_supabase`, query back to verify row count = non-DISMISSED items.
- `scripts/test_clobber_patch.py` — synthetic test: insert a `COMPLETE`-with-`completed_at` todo, run `sink_to_supabase` with an LLM-style `IN_PROGRESS` row, assert post-merge the row remains `COMPLETE`. Locks the clobber-prevention rule in place.

---

### The brain — `scripts/brain/`

The v2 brain is **three separable Opus calls** behind one Python orchestrator. Each call has a different system prompt and a different responsibility. The pipeline rule is "one job per call, each call auditable on its own". A single mega-call that did all three jobs would still produce items at the end — but you couldn't tell which step screwed up when something was wrong.

The brain currently runs against the v2 Supabase schema (`meetings`, `claims`, `items`, `decisions`, `open_questions`, `proposed_changes`, `ingestion_events`). It does **not** touch the v1 `todos` table; v1's `process.py` continues to feed `todos` independently.

#### `scripts/brain/extractor.py` — Call 1

`P:/Claude Projects/weekly-meetings/scripts/brain/extractor.py`

One-line role: turn one raw transcript into a list of structured *claims*. No reconciliation. No dedup. No cross-meeting logic.

- **Public function**: `extract_claims(transcript_text, meeting_metadata) -> {"claims": [...], "metadata": {...}}`.
- **Inputs**: raw transcript string + meeting metadata dict (`job_id`, `pm_id`, `meeting_date`, `meeting_type`, `attendees`, `notes`).
- **Outputs**: per-claim records with `speaker`, `claim_type` (one of 6 — see below), `subject`, `statement`, `raw_quote`, `position_in_transcript`. After the model call, `_normalize_claims(...)` adds `speaker_canonical`, `speaker_canonical_id`, `subject_canonical`, `subject_canonical_id` via `normalize.py`.
- **Claim taxonomy** (6 types, strict rules in the system prompt):
  - **commitment** — actor + action + (ideally) timeframe.
  - **decision** — alternatives were on the table and one was chosen. "Derek is our garage door guy" is NOT a decision (no alternatives) — it's a status_update.
  - **condition_observed** — factual observation; no judgment.
  - **status_update** — the catch-all. When in doubt between two types, prefer this.
  - **question** — genuinely unresolved; rhetorical statements aren't questions.
  - **complaint** — emotional/evaluative dissatisfaction; "Sanger missed Tuesday" is `condition_observed`, "Sanger keeps missing dates, this is ridiculous" is `complaint`.
- **Anthropic call**: `claude-opus-4-7`, `max_tokens=16000`, `thinking={"type": "adaptive"}`, **`output_config.format.type="json_schema"`** with `CLAIMS_SCHEMA` (guaranteed parseable JSON), **streaming via `messages.stream()`** (extraction can produce large outputs), **system prompt cached** via `cache_control: ephemeral` (so when this is called 5× in a row across a test batch, calls 2–5 read the prompt from cache).
- **Rules the prompt locks in**: extract claims AS-SAID, don't deduplicate, don't summarize across the meeting, don't pick a winner between contradictions, preserve `raw_quote` verbatim.

#### `scripts/brain/segmenter.py` — multi-job transcript splitter

`P:/Claude Projects/weekly-meetings/scripts/brain/segmenter.py`

One-line role: identify clear job-transition points in a transcript and emit one segment per job section.

- **Public functions**: `segment_transcript_by_job(text, available_jobs, primary_job_id) -> list[segment]`, `find_segment_for_position(segments, position)`.
- Returns `[{start_pos, end_pos, inferred_job_id}]` covering `[0, len(transcript))` with no gaps and no overlaps.
- Most meetings are single-job → returns one segment.
- Office meetings can cover multiple jobs sequentially ("ok let's move to Krauss, then Ruthven") → multiple segments.
- **Anthropic call**: `claude-haiku-4-5` — routing task, no deep reasoning. `max_tokens=4000`, `output_config.format=json_schema`. Single call, not streamed. Falls back to a single-segment with `primary_job_id` on any failure (malformed JSON, API error, transcript too short).
- Used by `reconciler.py` to tag each claim's `position_in_transcript` with the right job, overriding the subject-substring routing fallback.

#### `scripts/brain/normalize.py` — DB-driven entity normalizer

`P:/Claude Projects/weekly-meetings/scripts/brain/normalize.py`

One-line role: case-insensitive alias resolution against `internal_people` + `pms` + `subs` Supabase tables.

- **Public functions**: `load_entity_index(force_refresh=False)`, `normalize_entity(text, context='', entity_index=None) -> {canonical, ambiguous, matched_via, canonical_id}`.
- **Priority on alias collision**: person > pm > sub (first-write-wins).
- **Bare-name ambiguity**: `_BARE_AMBIGUOUS = {"lee", "terry"}` — "Lee" alone is ambiguous (Lee Ross owner vs Lee Worthy PM); "Terry" hits multiple TNT/sub aliases. Returns `"{name}?"` with `ambiguous=True` rather than auto-resolving; downstream Reconciler decides from context.
- **Lookup order**: bare-ambiguous → exact match on full name or alias → word-boundary substring (longest alias wins) → no match returns original text.
- **No hardcoded names** — all aliases come from the DB so adding a new sub via `sync_subs.py` automatically propagates. Cache invalidates on `force_refresh=True` or fresh process boot.
- **Anthropic calls**: none. Pure DB + regex.

#### `scripts/brain/reconciler.py` — Call 2

`P:/Claude Projects/weekly-meetings/scripts/brain/reconciler.py`

One-line role: take claims for one meeting → produce structured `items`, `decisions`, `open_questions` as `proposed_changes` (Gate 2B review queue).

- **Public function**: `reconcile_meeting(meeting_id, dry_run=False, prior_attempt_issues=None) -> dict`.
- **Inputs from Supabase**: the `meetings` row, all `claims` for that meeting, all open `items` for the routed jobs (for dedup), all `pay_app_line_items` for routed jobs (for line-item matching), all `subs`, all `jobs`, and the most recent 20 entries from `corrections` (Jake's feedback loop).
- **Outputs to Supabase**: one `ingestion_events` row + N `proposed_changes` rows. The Reconciler does NOT directly write to `items`/`decisions`/`open_questions` — Gate 2B routes everything through the review queue and Jake (or auto-approval) promotes them.

The architectural split is **deterministic-Python + one-LLM-call**:

- **Python (deterministic, per-claim, no LLM)**:
  - **Decision 8 — Per-claim job routing**: prefer segmenter output; fall back to subject-substring scan against `jobs.name`; final fallback `meeting.job_id`.
  - **Decision 6 — 3-stage sub-matching cascade**:
    1. Substring match against each sub's aliases.
    2. Substring match against `sub.name`.
    3. Haiku 4.5 classifier — only fires when stages 1/2 were ambiguous AND the claim text contains a sub-shaped capitalized phrase (heuristic regex for trades). Validates Haiku's returned `sub_id` is actually in the catalog (Haiku has been observed returning a name or inventing UUIDs).
  - **Decision 7 — 2-stage pay-app line-item matching cascade**:
    1. Word-boundary keyword match (length-weighted, top 5 candidates).
    2. Haiku 4.5 picks best from top 3 candidates. Validates the returned id is actually in the candidate set (observed: Haiku returning `line_number` instead of UUID).
    - Skipped entirely for `question` claim types.
  - **Decision 3 — Urgency** (any trigger → `priority=urgent`):
    1. Explicit urgency tokens (`URGENCY_TOKENS = ["urgent", "asap", "critical", "blocking", "now", "today", "tomorrow", "immediately"]`).
    2. `target_date` within 7 days of meeting date.
    3. Matched pay-app line shows `>90%` complete.
    4. Sub has 2+ slipped commitments in last 30 days — DEFERRED (needs `sub_events`).
  - **Decision 4 — Confidence (cold-start)**:
    - `high`: never at cold start (requires 2+ sources — not yet implemented).
    - `medium`: clear claim with named sub OR matched line item.
    - `low`: vague claim.
  - **Decision 11 — Clobber prevention**: on update, preserve each field in `existing.manually_edited_fields` when `manually_edited_at` is non-null; force-preserve `status='complete'` + `completed_at` when both are set.

- **The one Opus call** (`_reconciler_call(...)`): `claude-opus-4-7`, `max_tokens=48000`, `thinking={"type": "adaptive"}`, json_schema-constrained output, streaming, system prompt cached. The model receives the pre-computed `routed_job_id`, `matched_sub_id`, `matched_line_item_id` per claim so it doesn't redo Python's deterministic work. The prompt routes each claim per **Decision 2**:

  | claim_type            | output                                                                |
  |-----------------------|-----------------------------------------------------------------------|
  | commitment            | items (type=action)                                                   |
  | decision              | decisions                                                             |
  | condition_observed    | items (type=observation)                                              |
  | status_update         | items (observation, OR action when status reveals a stalled item)     |
  | complaint             | items (type=flag) when naming a sub; (observation) when just venting  |
  | question              | open_questions                                                        |

  The model also assigns **Decision 5 — `target_date`** (parsed → `YYYY-MM-DD`; unparseable phrase → `target_date_text`; nothing → both null), **Decision 9 — create vs update_existing** for cross-meeting dedup, and **Gate 2A.5 — `actionability`** = `actionable | signal` (3-prong test: specific actor + specific deliverable + specific/inferable timing; when in doubt, signal).
- **Corrections feedback loop (Gate 2A.6)**: the 20 most recent rows from the `corrections` table are injected into the prompt as "authoritative overrides of default judgment". On successful run, `_increment_correction_counts(...)` bumps each correction's `applied_count`.
- **Retry path**: if called with `prior_attempt_issues`, those audit findings are injected into the prompt under "PREVIOUS ATTEMPT HAD THESE AUDIT ISSUES — fix them this time".
- **Cost tracking**: every call updates `cost_tracker` with input/output/cache-read/cache-create tokens for both Opus and Haiku; final `cost_usd` is computed against the pricing constants at the top of the file (Opus: $5/$25 per MTok in/out, cache-read $0.50, cache-create $6.25; Haiku: $1/$5).

#### `scripts/brain/auditor.py` — Call 3

`P:/Claude Projects/weekly-meetings/scripts/brain/auditor.py`

One-line role: review the Reconciler's output for one meeting and flag issues. **6 mechanical checks + 1 LLM-based sanity check.**

- **Public function**: `audit_meeting(meeting_id, dry_run=False) -> dict`.
- **6 mechanical checks** (SQL/structural, no LLM):
  1. `claims_accountability` — total outputs (items + decisions + questions) ≥ 70% of claim count. Heuristic; exact tracking would need `items.source_claim_id`.
  2. `sub_resolves` — every `items.sub_id` exists in the `subs` table.
  3. `line_resolves` — every `items.pay_app_line_item_id` exists AND matches the item's `job_id`.
  4. `item_types` — every `items.type` is in `{action, observation, flag}`.
  5. `confidence` — valid value AND no `high` at cold start (Decision 4).
  6. `intra_meeting_dups` — no two open items share `(job_id, sub_id, pay_app_line_item_id)`.
- **1 LLM check** (`_llm_audit(...)`): `claude-opus-4-7`, `max_tokens=32000`, `thinking={"type": "adaptive"}`, json_schema output. Looks for: wrong type assignment (commitment → observation), inappropriate `priority=urgent` (past-tense status updates with casual "today"), inappropriate confidence, missing context (title says "Coordinate vendor" without saying which), intra-meeting contradictions, wrong sub linkage.
- **Severity rules**:
  - `clean` — zero issues.
  - `needs_retry` — issues the Reconciler can plausibly fix (wrong priority, wrong type).
  - `needs_review` — issues that need a human (schema violations, hard contradictions, repeat-after-retry).
- **Output**: `audit_state` + `audit_issues` are persisted PER ITEM on the `items` table.

#### `scripts/brain/retry_orchestrator.py` — Decision 12 retry loop

`P:/Claude Projects/weekly-meetings/scripts/brain/retry_orchestrator.py`

One-line role: glue Auditor → Reconciler retry → Auditor.

- **Public function**: `audit_and_retry(meeting_id) -> dict`.
- **Flow**:
  1. Run `audit_meeting()`.
  2. If `clean` → done.
  3. If `needs_review` → stop; don't retry (hard issues need human).
  4. If `needs_retry` → DELETE this meeting's `items`/`decisions`/`open_questions` rows, re-run `reconcile_meeting(meeting_id, prior_attempt_issues=all_issues)`, re-audit.
  5. If still not clean after retry → force `final_severity = "needs_review"` (no second retry).
- **Max 2 iterations rule**: Reconciler runs at most twice per meeting. After that, escalate to human review.

### Parsers — `scripts/parsers/`

#### `scripts/parsers/pay_app_parser.py`

`P:/Claude Projects/weekly-meetings/scripts/parsers/pay_app_parser.py`

One-line role: parse a Ross Built AIA G702/G703 pay-app XLSX into a structured `{pay_app, line_items, skipped_rows}` dict.

- **Public entrypoint**: `parse_pay_app(file_path, job_id) -> dict`.
- Prefers exact sheet names `"Project Summary (G702)"` and `"Line Item Estimate (G703)"`; falls back to substring match on `"G702"`/`"G703"`.
- G703 column mapping is done by **header text** (the two-row header block above data rows is combined and matched against known label patterns) — robust to column-letter drift across jobs.
- Handles Excel error sentinels (`#DIV/0!`, `#REF!`, etc.) → `None`.
- No Supabase I/O. Callers (e.g. `ingest_pay_app.py`) handle ingestion.

---

### Generators — `generators/` (Phase 6 insights)

The generators take the schedule-intelligence artifacts (`phase-instances-v2`, `sub-phase-rollups`, `bursts`) plus the per-PM binders and produce `data/insights.json` — the structured insight set that the Monday meeting-prep doc and the cockpit dashboards both render.

#### `generators/run_all.py`

`P:/Claude Projects/weekly-meetings/generators/run_all.py`

One-line role: orchestrator for the Phase 6 generator pipeline.

- **Pipeline**:
  1. `enrich_action_items.enrich_all()` — writes `binders/enriched/*.enriched.json`.
  2. `g1_sequencing.generate(phase3, originals, generated_at)`.
  3. `g2_sub_drift.generate(phase3, originals, generated_at)`.
  4. `g3_missed_commitment.generate(phase3, enriched, generated_at)`.
  5. Write `data/insights.json` with totals, by-type / by-severity / by-PM breakdowns.
- **Stats printed**: G3 flag rate target band 2–20%.

#### `generators/g1_sequencing.py`

`P:/Claude Projects/weekly-meetings/generators/g1_sequencing.py`

One-line role: fire `sequencing_risk` + `sequencing_violation` insights.

- **`sequencing_risk`**: phase X is ongoing AND primary density < 0.65 AND any successor has logs → INSIGHT (severity=`critical` if successor already started, else `warn`).
- **`sequencing_violation`**: phase X complete AND any predecessor has zero logs + no scheduled date → INSIGHT(`warn`). Capped to phases whose last log is within `VIOLATION_RECENCY_DAYS=90` to avoid 200+ historical artifacts on closeout-stage jobs.
- Reads `data/phase-instances-v2.json` (already computes `predecessors_complete`/`predecessors_missing`/`successors_started`).

#### `generators/g2_sub_drift.py`

`P:/Claude Projects/weekly-meetings/generators/g2_sub_drift.py`

One-line role: detect sub × phase × job drift vs sub's own baseline.

- For each `(sub × phase × job)` where job-instance status is ongoing/complete AND the sub has performed this phase on ≥ `MIN_JOBS_FOR_BASELINE=3` jobs:
  - `current = sub_involved.density on this instance`
  - `baseline = sub-phase rollup.primary_density across all the sub's jobs`
  - If `current < baseline - DRIFT_THRESHOLD (0.20)` → INSIGHT(`warn`).
- Cross-data signal: "Watts is below his own baseline on this job", distinct from G1.

#### `generators/g3_missed_commitment.py`

`P:/Claude Projects/weekly-meetings/generators/g3_missed_commitment.py`

One-line role: cross-check completed binder items against BT daily logs for field activity.

- For each enriched action item where `status == COMPLETE`, `closed_date within last 14 days`, `requires_field_confirmation == True`, and `related_sub OR related_phase` is set:
  - Search daily logs in `[closed_date - 7, closed_date + 7]` on the item's job.
  - Sub match: `related_sub` appears in `crews_clean` OR `notes_full`.
  - Phase match: `parent_group_activities` or `notes_full` contains a phrase whose phase keyword maps to `related_phase`.
- Zero matching log entries → INSIGHT(`missed_commitment`, `warn`).
- Reads daily logs via `_common.SCRAPER_LOGS` (which points at the same scraper output `fetch_daily_logs.py` reads — see §9).

#### `generators/commitment_tracker.py`

`P:/Claude Projects/weekly-meetings/generators/commitment_tracker.py`

One-line role: week-over-week meeting-commitment snapshot + resolution status.

- Captures per-PM must-discuss commitments into `data/meeting-commitments.json` with `content_hash` per entry.
- Diffs against previous week: `carried` (hash present in current insights), `resolved` (hash absent), `stuck` (present in last 3 consecutive weeks).
- Same-ISO-week re-runs UPDATE the entry in place rather than appending.
- Consumed by `validate_accountability.py` (which is invoked from `run_weekly_pipeline.py` step 7).

#### `generators/enrich_action_items.py`

`P:/Claude Projects/weekly-meetings/generators/enrich_action_items.py`

One-line role: infer `related_phase`, `related_sub`, `requires_field_confirmation` on each binder item.

- Pattern-matches `action` + `update` against `phase-keywords` config and canonical sub universe from Phase 3 data.
- `FIELD_VERBS` regex (`install|reinstall|verify|punch|complet|deliver|...`) determines `requires_field_confirmation`.
- Writes to `binders/enriched/<file>.enriched.json` — never overwrites originals.
- Inferred fields carry `inferred: true` markers so PMs can see what was guessed.

#### `generators/_common.py`

`P:/Claude Projects/weekly-meetings/generators/_common.py`

Shared helpers for generators: loaders for binders / phase data / daily logs, PM-jobs map (`PM_BY_BINDER_FILE`, `PM_SLUGS`), sub canonical universe, phase-keyword regex compilers, `make_insight(...)` factory, `insight_rank_score(...)`. Pure-function module, no side effects on import.

Notably: `SCRAPER_LOGS = ROOT.parent / "buildertrend-scraper" / "data" / "daily-logs.json"` — same output `fetch_daily_logs.py` reads. The generators and the v1 Monday prompt share the scraper output (see §9 cross-reference).

#### `generators/_phase_names.py`

Phase code → human name lookup against `config/phase-taxonomy.yaml`. Two helpers: `phase_name(code)` for bare name, `phase_label(code)` for `"Name (code)"`.

---

### The 3-call brain — why this shape?

The v2 brain (Extractor → Reconciler → Auditor) is structured as three Opus calls instead of one mega-call for three locked-in reasons:

1. **Each call is auditable on its own.** A single-call agent ("here's the transcript and the schema, produce items") hides which step failed when something looks wrong. With three calls, you can inspect the claims output and verify "yes, extraction got this right; the failure was in reconciliation." That's the foundation of the corrections loop (Gate 2A.6) — Jake's feedback can target a specific call's failure mode.
2. **Different responsibilities, different prompts, different settings.** Extraction needs to lose no information ("two contradictory statements = two claims, don't pick a winner"). Reconciliation needs to apply business rules and dedup. Auditing needs to be conservative ("flag only real problems, not stylistic preferences"). Asking one prompt to do all three reliably is harder than asking three prompts to each do one thing.
3. **Selective retry.** The retry orchestrator deletes only the Reconciler's outputs and re-runs Reconciler with audit context. Re-running extraction on the same transcript is wasted work — claims are deterministic-ish (Opus is consistent on extraction given the same prompt cache). The 3-call shape makes the "rewind to step 2 only" pattern possible.

**Max 2 iterations rule**: per `retry_orchestrator.audit_and_retry(...)`, Reconciler runs at most twice per meeting. After the second audit, if still not clean, `final_severity = "needs_review"` no matter what the Auditor said — Jake's eyes are the next step.

**The "needs Jake's review" escape hatch** runs at three levels:

- **Reconciler emits `needs_review[]`** for claims it can't confidently classify (rather than guessing).
- **Auditor's `needs_review` severity** for schema violations, hard contradictions, or post-retry persistence.
- **Items individually carry `audit_state = clean | needs_retry | needs_review`** so the cockpit can render a "?" indicator and route them into the human review queue.

This is the system-wide principle: **AI output is never the final word until a human review step.** Same logic as the `proposed_changes` queue and `manually_edited_fields` clobber prevention in §process.py.

---


---

## §9 BUILDERTREND SCRAPER

The Buildertrend scraper lives at `C:/Users/Greg/buildertrend-scraper/` (separate repo from `weekly-meetings/`). It pulls daily logs, purchase orders, and change orders out of Buildertrend via Playwright + the BT JSON API and writes JSON files that the Python pipeline (§8) and the cockpit consume.

It's invoked two ways:
- **Manually** from a terminal (`python scrape_api.py --days 14 -v`).
- **As a child process from the cockpit** (`/api/bt/sync` spawns the scraper with credentials passed via env vars — see §9.4).

### §9.1 — The BT API contract

Buildertrend used to be server-rendered with a walkable DOM. In early 2026 they shipped a SPA + JSON API, and the DOM-walking `scrape.py` (§9.3 below) started silently scraping 0 logs because the new DOM is empty until the SPA mounts. `scrape_api.py`, `scrape_po.py`, and `scrape_co.py` were reverse-engineered against the JSON API by capturing the live web app's XHR traffic (the `probe_co.py`/`probe_co2.py` exploration scripts).

Reverse-engineered endpoints (from `scrape_api.py`, `scrape_po.py`, `scrape_co.py`):

```sh
# Active jobs: name -> internal jobId
POST https://buildertrend.net/api/jobpicker/GetJobPickerData
Content-Type: application/json
{
  "filters": "{\"1\":\"\",\"0\":\"1\",\"2\":\"\"}",
  "displayMode": 15, "jobSortChoice": 1, "isExpanded": true,
  "templatesOnly": false, "selectMode": 2, "useJobInSession": false,
  "allowGlobalJob": false, "includeGeneralJob": false,
  "builderId": "90761", "includeCounts": false
}
# Returns a nested blob; scrape_api.get_active_jobs() walks it and yields
# { "Krauss-427 South Blvd of the Presidents": 12345, ... }.

# Crew custom-field id -> name map, per job
GET https://buildertrend.net/api/Filters/31?jobID={jid}&useSession=false
# Used to resolve crew ids from custom-field 425977 ("Crews on Site") and
# 425983 ("Absent Crew(s)") into human names.

# Daily-log rows (paged, newest first)
POST https://buildertrend.net/apix/v2/DailyLogs/grid
{
  "jobIds": [jid],
  "filters": { "8": "{\"SelectedValue\":2147483647,\"StartDate\":null,\"EndDate\":null}" },
  "gridRequest": { "hideMultiJobsColumns": false, "emptyStateEntity": 18 },
  "pagingData": { "pageNumber": 1, "pageSize": 100, ... }
}
# Each row has: dailyLogId, logDate, logTitle (activity), logNotes (full),
# customFields (incl. crews/workforce/absent ids), weatherInformation
# (maxTemp/minTemp), tags (parent group activities),
# images (with isPhoto + downloadDocPath/docPath for direct URLs).

# Purchase Orders grid
POST https://buildertrend.net/api/PurchaseOrders/Grid
# Same pagingData/jobIds shape. selectedColumns=
#   ["4","13","1","9","10","6","29","12","16","18","30","31","34","5"]
# (job, PO#, title, status, workStatus, performedBy, date, cost, paid,
# remaining, %paid, %remaining, %billed, costCodes).

# Purchase Order detail (line items)
GET https://buildertrend.net/api/PurchaseOrders/{id}
# data.lineItems.value -> [{ lineItemId, costCodeTitle, title, description,
# quantity, unitCost, calculatedAmount, amountPaid, amountBilled }, ...]

# Change Orders grid
POST https://buildertrend.net/api/ChangeOrders/Grid
# selectedColumns = ["13","2","0","31","27","14","3","15","5","1","6","8","19"]
# (co#, title, status, ownerPrice, builderCost, totalWithTax, dates, ownerName).
```

The `DATE_ALL` filter constant `{"SelectedValue":2147483647,"StartDate":null,"EndDate":null}` is BT's sentinel for "no date filter" — we apply it to every grid request and do date filtering client-side after the response.

### §9.2 — Session + auth

`C:/Users/Greg/buildertrend-scraper/bt_session.py`

Auth flow:
- **Playwright headless via `BTSession(headed=False)`**. Persistent storage state at `.session/state.json` (cookies + localStorage). First run logs in headed; subsequent runs reuse the saved state silently.
- **Session expiration detection**: BT (now Auth0 Universal Login) redirects unauthenticated requests through `login.buildertrend.com`. `_on_login_page()` treats any URL host containing `"login"` as "needs auth" — works both before BT redirects and during the Auth0 round-trip.
- **MFA**: BT's Auth0 sometimes prompts for a code. If detected in headless mode → raise `LoginFailed` with a clear "re-run with `--headed` to complete the prompt". In headed mode, waits up to 5 minutes for the user to clear it, then the resulting state.json is reused on future headless runs.
- **Login selectors** are listed at the top of `bt_session.py` (`LOGIN_SELECTORS`) with multiple fallbacks for username/password/submit — verified against the Auth0 form on 2026-05-18. When BT changes the DOM, update those selectors.

`C:/Users/Greg/buildertrend-scraper/auth.py`

Credentials:
- **`get_credentials()` resolution order**:
  1. `BT_USERNAME` + `BT_PASSWORD` env vars (one-shot use; set by cockpit `/api/bt/sync` before spawning the scraper; never persisted on disk).
  2. Windows Credential Manager via the `keyring` library — DPAPI-encrypted to the current Windows user account.
  3. Raise `MissingCredentialsError`.
- **CLI**: `python auth.py {set|status|clear}`. `set` prompts interactively (`getpass` hides the password), stores under service name `buildertrend-scraper` with a fixed `__bt_username__` pointer key.

**The credential boundary** (a load-bearing rule for this system):

- `python auth.py set` is the **one step Jake has to do himself**. It's never automated.
- The cockpit's BT-sync modal collects credentials in the browser, POSTs them to `/api/bt/sync`, which sets `BT_USERNAME` + `BT_PASSWORD` in the spawned child's environment ONLY. They live in the child process's env vars and die with the process. Never written to disk, never logged.
- **NEVER accept the BT password through the AI chat interface.** The user's MEMORY.md captures this as a hard rule. If the user pastes a password into the conversation, that's a prompt to remind them to use `auth.py set` instead.

### §9.3 — Each scraper file in detail

#### `scrape_api.py` — THE daily-log scraper (replaced `scrape.py`)

`C:/Users/Greg/buildertrend-scraper/scrape_api.py`

CLI:
```
python scrape_api.py [--days N] [--jobs A,B] [--skip-photos]
                     [--max-photos-per-log N] [--headed] [-v]
```

Step-by-step:
1. `bt_session.BTSession(headed=args.headed)` → `bt.ensure_logged_in()`.
2. Navigate to `/app/DailyLogs` once to warm the SPA session (cosmetic for headed/debug runs; the actual scrape is JSON API).
3. `get_active_jobs(ctx)` — POST `/api/jobpicker/GetJobPickerData {templatesOnly:false}`. Walks the response, builds `{jobName: jobId}`.
4. **Targets**:
   - With `--jobs Krauss,Pou` → only those short names (must exist in `JOB_NAME_MAP`).
   - Default → **every real active job** (not just the 11 in `JOB_NAME_MAP`), skipping templates/non-job entries via `is_real_job()` (filter on `NON_JOB_MARKERS = ("template", "master schedule", "strapping", "field crew")`).
5. Per job: `get_crew_map(ctx, jid)` → GET `/api/Filters/31?jobID={jid}` and walk for id→name pairs.
6. `fetch_log_rows(ctx, jid, since_iso)` — paged POST `/apix/v2/DailyLogs/grid` (page size 100, max 30 pages). Stops once a page's oldest row is before `since_iso`.
7. `map_record(row, crew_map)` converts each BT row to the cockpit's `BTRecord` shape. Pulls custom fields by id: `CF_CREWS=425977`, `CF_WORKFORCE=425978`, `CF_ABSENT=425983`.
8. `download_photos(ctx, images, ...)` — for each `image` with `isPhoto`, fetch the direct URL from `downloadDocPath`/`docPath`, save to `photos/<job_short>/<log_id>/photo_NNN.<ext>` (capped at `--max-photos-per-log`, default 6). Skipped when `--skip-photos`.
9. Write `data/daily-logs.json`.

Output JSON shape:
```json
{
  "byJob": {
    "Krauss-427 South Blvd of the Presidents": [
      {
        "logId": "12345",
        "date": "2026-05-20",
        "crews_clean": ["DB Welding", "Faust Renovations"],
        "crews": "DB Welding; Faust Renovations",
        "absent_crews": [],
        "parent_group_activities": ["Trim", "Punch"],
        "daily_workforce": 7,
        "weatherHigh": 88.0, "weatherLow": 71.0,
        "notes_full": "Crew installed crown molding in master ...",
        "notes": "Crew installed crown molding in master ...",
        "activity": "Trim — Master suite",
        "enriched_at": "2026-05-20T22:01:33+00:00",
        "photo_urls": ["C:/Users/Greg/buildertrend-scraper/photos/Krauss/12345/photo_001.jpg", ...]
      }
    ]
  }
}
```

This file is what `fetch_daily_logs.py` (§8) reads. It's also what `g3_missed_commitment.py` cross-checks against. **Verified 2026-05-20 with 150 real logs across 11 jobs.**

#### `scrape_po.py` — Purchase Order scraper

`C:/Users/Greg/buildertrend-scraper/scrape_po.py`

CLI:
```
python scrape_po.py [--jobs A,B] [--skip-line-items]
                    [--max-pos-per-job N] [--headed] [-v]
```

Step-by-step: same session/job-targeting flow as `scrape_api.py` (in fact `scrape_po.py` imports `get_active_jobs` and `is_real_job` directly from `scrape_api`). Then per job: POST `/api/PurchaseOrders/Grid` paged (page size 300, max 20 pages). Per PO (unless `--skip-line-items`): GET `/api/PurchaseOrders/{bt_po_id}` for `data.lineItems.value`.

`map_po(row)` shape: `bt_po_id`, `job_key`, `bt_job_id`, `po_number`, `is_bill`, `title`, `vendor`, `bt_vendor_id`, `approval_status`, `work_status`, `paid_status`, `cost`, `amount_paid`, **`amount_remaining` (outstanding/committed-but-unpaid)**, `pct_paid`, `pct_remaining`, `pct_billed`, `cost_codes`, `date_added`, `line_items`. Money fields go through `_v()` which extracts `.value` from BT's `{value, scale}` dicts.

Output: `data/purchase-orders.json` in the same `{byJob: {job_key: [po_records]}}` shape.

#### `scrape_co.py` — Change Order scraper (most recent)

`C:/Users/Greg/buildertrend-scraper/scrape_co.py`

CLI:
```
python scrape_co.py [--jobs A,B] [--headed] [-v]
```

Same shape as `scrape_po.py`. POST `/api/ChangeOrders/Grid` paged (page size 200, max 20 pages). No detail GET — the grid response carries everything (`co_number`, `title`, `status`, `approval_code`, `owner_price`, `builder_cost`, `total_with_tax`, `owner_name`, `date_approved`, `date_added`).

Output: `data/change-orders.json` in the same `{byJob: {job_key: [co_records]}}` shape.

#### Exploration scripts

- `probe_co.py` — captured BT's Change Orders endpoints by attaching a Playwright response listener (`page.on("response")`) and navigating to the CO page; dumped every JSON XHR matching `changeorder` to `.session/co-probe.json`. This is how the CO scraper was built without docs.
- `probe_co2.py` — followup, hits `ChangeOrders/Grid` per active job to find one with COs and dump a row's full shape.
- `inspect_url.py` — quick BT page inspector. Uses the saved session, navigates to a URL, dumps rendered HTML to `.session/inspect-<slug>.html`. Used for offline selector hunting when BT updates DOM.

#### `scrape.py` — LEGACY DOM-walking scraper (now broken)

`C:/Users/Greg/buildertrend-scraper/scrape.py`

Historical reference. This file walked BT's old project list page, navigated each job's Daily Logs page, extracted fields via Playwright DOM selectors, and produced the same `byJob` shape as `scrape_api.py`. Selectors were tagged `# TUNE` for the locations where BT-specific DOM assumptions live.

It still logs in successfully (the auth flow didn't change) but scrapes 0 logs because BT's modern SPA doesn't render the data into the DOM until the JSON API has been called. Kept in the repo as a reference for the selector-tuning workflow in case BT ever reverts.

### §9.4 — Cockpit integration

The cockpit (Next.js app at `production-cockpit/`) ships an `/api/bt/sync` route that drives BT scrapes from the UI. Pattern:

1. Browser opens the BT-sync modal, user enters BT credentials.
2. Cockpit POSTs creds + a job filter to `/api/bt/sync`.
3. The route spawns `python scrape_api.py [--jobs ...]` (or `scrape_po.py` / `scrape_co.py`) as a child process. **Credentials are passed via `BT_USERNAME` + `BT_PASSWORD` env vars on the child only.** Never written to disk, never logged. (See §9.2 — this is the credential boundary.)
4. Scraper writes `data/daily-logs.json` (or PO / CO equivalent) to the scraper repo.
5. Cockpit reads the resulting JSON and POSTs it to `/v2/api/daily-logs/upload` (or `/v2/api/pos/upload`, `/v2/api/cos/upload`) which upserts into Supabase.

The cockpit looks up the scraper's path via the `BT_SCRAPER_DIR` env var (or a sensible default). This lets the scraper live on a different drive than the cockpit — Greg's setup has the scraper on `C:` while the cockpit is on `P:`. The Python pipeline (§8) also reads the same `data/daily-logs.json` via `constants.DAILY_LOGS_PATH` (also `BT_SCRAPER_DIR`-aware via `BT_DAILY_LOGS_PATH`).

### §9.5 — Why `scrape_api.py` (the SPA + JSON rebuild)

Historical context:

- **Before early 2026**: Buildertrend was a traditional server-rendered web app. `scrape.py` walked the project list, navigated each job's Daily Logs tab, parsed the rendered table via Playwright DOM selectors. Worked fine.
- **Early 2026**: BT shipped a SPA. The old URLs still resolve, the old login flow still works, but the DOM is empty on first paint — data lives in JSON XHRs that the SPA fetches and renders client-side.
- **The silent failure**: `scrape.py` continued to authenticate successfully and navigate to each job's logs page. But every selector `# TUNE`-tagged for the old DOM returned zero matches. The scraper finished cleanly with `0 logs scraped` and the cockpit/pipeline kept consuming yesterday's `daily-logs.json` until someone noticed the dates weren't advancing.
- **The rebuild**: rather than reverse-engineer BT's React state, we attached a Playwright response listener and watched the live UI's network tab. Every grid view turned out to be a single POST to a `/api/.../Grid` endpoint with a uniform `pagingData`/`filters`/`jobIds` shape. The rebuild took the BT JSON exactly as it arrives, mapped it into the same `BTRecord` shape the cockpit + pipeline already consumed, and we never had to walk a DOM again. **`scrape_api.py` is faster, more robust, and produces strictly more data** (custom fields like absent crews and daily workforce that the old DOM scraper couldn't reach).
- **Verified 2026-05-20**: 150 real logs across 11 jobs in a single `--days 14` run. `scrape_po.py` followed the same pattern (1260 POs ingested 2026-05-22 per the cockpit handoff note). `scrape_co.py` is the most recent addition (built via `probe_co.py`/`probe_co2.py`).

Cross-reference: §8's `fetch_daily_logs.py` and `generators/_common.py` both read the file `scrape_api.py` writes. §8's `process.py` invokes `fetch_daily_logs.fetch_for_pm(...)` to inject 14-day BT context into the Monday Opus prompt. The cockpit invokes the scrapers as child processes (§9.4) and ingests their JSON into Supabase. Everything downstream of BT flows through these three files.

---

## §10 END-TO-END FLOWS

### Flow 1 — BT daily-log sync

User clicks "Pull from Buildertrend" on `/import`.

1. `BtSyncButton` (`@/components/bt-sync-button`) opens a modal prompting BT username + password (typed each time, never persisted — see memory `project_bt_credential_boundary.md`).
2. Modal POSTs to `/api/bt/sync` with `{username, password, days?, jobs?, skipPhotos?, maxPhotosPerLog?, extractVision?}`.
3. `production-cockpit/app/api/bt/sync/route.ts` refuses on Vercel (`process.env.VERCEL === "1"`). On local dev, it `spawn()`s `$BT_SCRAPER_DIR/.venv/Scripts/python.exe` against `scrape_api.py` with `BT_USERNAME`/`BT_PASSWORD` in the child env (no shell, args verbatim). Timeout: 290s.
4. On exit-0, reads `$BT_SCRAPER_DIR/data/daily-logs.json` (shape `{byJob: {jobKey: BTRecord[]}}`).
5. Same-origin `fetch()` to `/v2/api/daily-logs/upload` with `{source:'cockpit-bt-sync', payload}`. That route (`production-cockpit/app/v2/api/daily-logs/upload/route.ts`) upserts `daily_logs` on `(job_key, log_id)`, parses jsonb crew_counts/inspections/photo_urls, honors `manually_edited_fields` and `hidden`, and auto-creates new `subs` rows via `ensureSubsForCrews()` (insert-only, ignoreDuplicates, source='auto').
6. If `extractVision !== false && !skipPhotos`: same-origin `fetch()` to `/v2/api/daily-logs/extract-photos` with `{limit:30}`. That route (`production-cockpit/app/v2/api/daily-logs/extract-photos/route.ts`) selects `daily_logs` with photo_urls but null photo_summary, calls Claude (`claude-opus-4-7`) tool-use (`emit_photo_summary`) per log (max 6 photos each), writes `photo_summary` jsonb + `photo_summary_at`.
7. Both routes call `revalidatePath('/subs')`, `revalidatePath('/sub/[id]','page')`. The daily-log upload also implicitly affects `/` and `/v2/job/[id]` via the `daily_logs` join used to compute photo counts.
8. Response bubbles back to the modal: `{ok, scrape:{logCount, photoCount}, upload, vision}`.
9. User sees the result on home (the per-job rows; daily logs feed the photo-count badge indirectly) and on `/v2/job/[id]` (JobSummaryPanel "Process N pending photos" button drops to 0; "all N photos analyzed" chip).

### Flow 2 — Transcript import

User drops a `.txt` Plaud transcript on `/import`.

1. `TranscriptImportModal` (`@/components/transcript-import-modal`) reads the file, auto-fills PM/job/date/meeting type from the filename (`MM-DD <Job> <Site|Office|Other> Production Meeting-transcript.txt`), warns if the same filename already appears in `priorImports`.
2. POSTs `/api/import-transcript` with `{transcript, pm_id, pm_name, meeting_date, meeting_type}`.
3. `production-cockpit/app/api/import-transcript/route.ts` loads the `subs` catalog (id, name, aliases), builds a structured prompt, calls Claude `claude-opus-4-7` with tool-use `emit_action_items` (enforces the JSON schema; no regex parsing). Returns `{summary, jobs_mentioned, grouped:[...]}` to the modal — no DB writes at this step.
4. Every item title goes through `scrubRelativeDates(title, meeting_date)` (`lib/scrub-relative-dates.ts`) — resolves "tomorrow"/"by Friday"/"next week"/etc. to YYYY-MM-DD against the meeting date. Defence-in-depth: the same scrub runs again at the save boundary.
5. The modal renders the proposals (grouped by sub) with editable titles, dates, sub assignments, "use suggested date" hints.
6. User clicks "Save N to-dos". Modal POSTs `/api/save-extracted-todos` with `{pm_id, meeting_date, source_label:<filename>, items:[...]}`.
7. `production-cockpit/app/api/save-extracted-todos/route.ts` checks for duplicate `source_label` in `todos.source_transcript` (returns 409 if already imported). Otherwise upserts `todos` `onConflict:"id"` with collision-free ids `<JOB_PREFIX>-C<base36-ts>`. Runs `scrubRelativeDates()` once more on every title.
8. `revalidatePath('/')`, `/subs`, `/sub/<sub_id>` per unique sub, `/v2/job/<slug>` per unique job name (slug from `job.toLowerCase().replace(/[^a-z0-9]+/g,'')`).
9. The cockpit's home + each affected job page now show the new to-dos.

(The v2 brain pipeline is a separate path: `/v2/upload` saves a `meetings` row hashed for dedup; the Python Extractor + Reconciler runs offline; results land in `ingestion_events` + `proposed_changes`; user reviews at `/v2/review` and commits via `/v2/api/review/[id]/commit`.)

### Flow 3 — PO sync (grid-only fast path)

User clicks "Pull POs" on `/import`.

1. `BtPoSyncButton` (`@/components/bt-po-sync-button`) opens its modal — BT username + password + optional jobs filter + "Include line items" checkbox.
2. POSTs `/api/bt/sync-po`. Default: `includeLineItems=false` → grid-only (~30s across all jobs). If `includeLineItems && !jobs` → 400 with a helpful message (line items for all jobs would take ~30 min).
3. Route spawns `scrape_po.py` with `--skip-line-items` (or without, if includeLineItems). Timeout 900s.
4. On exit-0, reads `$BT_SCRAPER_DIR/data/purchase-orders.json` (shape `{byJob: {jobKey: PORecord[]}}`).
5. Same-origin POST to `/v2/api/purchase-orders/upload` with `{payload, skipLineItems: !includeLineItems}`.
6. `production-cockpit/app/v2/api/purchase-orders/upload/route.ts` upserts `purchase_orders` on `bt_po_id`, sets `scraped_at`. Pre-reads `manually_edited_fields, hidden` per `bt_po_id` — hidden POs are entirely skipped; edited POs have those columns deleted from the upsert payload (so a manual price edit survives the next scrape).
7. On a full pull (`!skipLineItems`), reconciles `po_line_items` — DELETEs only CLEAN lines BT no longer returns (never deletes hidden or edited lines), upserts incoming lines on `(po_id, bt_line_item_id)` with the same manual-wins skip.
8. Response: `{ok, jobs, upserted, lineItems, errors}`.
9. User sees fresh PO totals on `/` (portfolio rollup card) and per-job on `/v2/job/[id]` (AccountingTable).

### Flow 4 — CO sync

1. User clicks `BtCoSyncButton`. POSTs `/api/bt/sync-co` with `{username, password, jobs?, headed?}`.
2. Route spawns `scrape_co.py`. Timeout 600s.
3. Reads `data/change-orders.json`.
4. Same-origin POST to `/v2/api/change-orders/upload` with `{payload}`.
5. `production-cockpit/app/v2/api/change-orders/upload/route.ts` upserts `change_orders` on `bt_co_id` with the same manual-wins pattern (hidden skipped; edited fields dropped from upsert).
6. User sees the result in the ChangeOrdersSection on `/v2/job/[id]`.

### Flow 5 — Admin creates a job → PM sees it

1. Admin opens `/admin/jobs`, clicks "Add a job", fills `{id, name, address, pm_id}`.
2. `JobsAdminClient` POSTs `/api/admin/jobs` with the body.
3. Route runs `adminGuard()`, validates the slug regex, inserts into `jobs`.
4. `bustJobCaches(id)` calls `revalidatePath` on `/`, `/meeting`, `/admin/jobs`, `/admin/users`, `/admin`, `/subs`, `/v2/job/[id]`.
5. The next request from the PM whose `pmId === pm_id` re-renders the home page: `Page` (`app/page.tsx`) queries `jobs`, applies `canSeeJobByPm(user, jobs.pm_id ?? assignment.pm_id)` filter; the new job appears because the PM matches. Admin sees the job unconditionally.
6. Single source of truth for visibility is `jobs.pm_id` (active `job_pm_assignments` row also counts via `_pmForJob()`). The legacy `allowedJobs` overlay column is NOT consulted on the home/meeting/job pages.

### Flow 6 — Manual edit survives a re-scrape

1. On `/v2/job/[id]` user clicks an `EditableText` value in the AccountingTable (say, a PO's `vendor`), types a corrected name, blurs/presses Enter.
2. POSTs `/v2/api/purchase-orders/[id]/edit` with `{vendor: "Corrected Vendor LLC"}`.
3. Route updates `purchase_orders.vendor` and appends `"vendor"` to `manually_edited_fields`, stamps `manually_edited_at = now()`.
4. Later, BT sync runs: scraper pulls fresh PO data and POSTs to `/v2/api/purchase-orders/upload`.
5. Upload route pre-reads existing `manually_edited_fields` for every `bt_po_id` it's about to touch. For this PO, `"vendor"` is in the list — the upsert payload for this row has the `vendor` key DELETEd before upsert, so the user's value survives.
6. Same pattern applies to `daily_logs`, `po_line_items`, `change_orders` — every scraped table tracks `manually_edited_fields` columns and the upload route skips those columns on re-scrape (see memory `project_manual_wins_and_edit_delete.md`).
7. Soft-deletes (`hidden=true`) follow the same rule: the upload route never resurrects a hidden row; the UI filters `hidden=false` everywhere.

### Flow 7 — Job summary generation

1. On `/v2/job/[id]` the user clicks "Generate summary" (or "Refresh summary") in the `JobSummaryPanel`.
2. Client POSTs `/api/jobs/[id]/refresh-summary` with `{window_days: 30}`.
3. Route pulls in parallel: `jobs(id, name, address)`, `daily_logs` for last `window_days` ordered desc (limit 60) with `photo_summary, photo_urls, crews_present, parent_group_activities, daily_workforce, crew_counts, inspections, notes` — `ilike job_key, '<job.name>%'`; open `todos` (top 60); recently-completed `todos` (top 40, within window).
4. Builds prompt with all three result sets serialized as JSON; calls Claude `claude-opus-4-7` with tool-use `emit_job_summary` (schema-guaranteed `{headline, phase, whats_happening, subs_recently_on_site, open_concerns, coming_up, inspections_recent, safety_flags, confidence}`).
5. Inserts a new `job_summaries` row keeping history (latest wins on read; we keep history so we can diff "what changed this week"). Tolerates the table being missing — returns `persisted:false, persist_hint:"apply migrations via /admin/run-migrations..."` with the summary still in the response.
6. `revalidatePath('/v2/job/[id]')` on success.
7. `JobSummaryPanel` updates its local `summary` + `meta` state, calls `router.refresh()` so server-side counts (photo counts, todo counts) stay synced.
8. The narrative panel renders the headline, phase, what's happening, subs on site, open concerns (priority-tinted), coming up, inspections, safety flags.

### Flow 8 — Auth login + visibility

1. User hits any non-public page (e.g. `/`). Middleware (`production-cockpit/middleware.ts`) runs in the Edge runtime, reads the `SESSION_COOKIE`, verifies the HMAC-SHA256 signature against `process.env.AUTH_SECRET` using Web Crypto (`crypto.subtle.importKey` + `verify`). Checks `payload.exp > now`.
2. If absent / invalid / expired: 302 redirect to `/login?next=<original>`. Stale cookies are explicitly deleted.
3. `/login` renders the form. `LoginForm` (client) POSTs `/api/auth/login` with `{email, password}`.
4. `production-cockpit/app/api/auth/login/route.ts` calls `checkPassword(email, password)` → `findUserByEmail()` → `getAllUsers()` (`lib/user-store.ts`) which merges seed users from `lib/auth-users.ts` with overlay rows from Supabase `user_overlay` (overlay wins by case-insensitive email).
5. Plaintext password comparison (internal MVP — see file header). On success: `encodeSession(email)` builds `<base64url(payload)>.<base64url(hmacSha256(payload))>`, route sets `SESSION_COOKIE` (`httpOnly`, `sameSite:lax`, `secure: NODE_ENV==='production'`, `path:'/'`, `maxAge: SESSION_TTL_SEC`).
6. Client does `window.location.assign(next)` — full-page nav so all RSCs re-render with the new cookie.
7. Middleware verifies on every subsequent request. Server pages call `await currentUser()` (`lib/auth.ts`) which decodes the cookie via `decodeSession()` (Node `crypto.timingSafeEqual` here, not Web Crypto — the page runtime is Node).
8. Visibility: pages call `canSeeJobByPm(user, jobPmId)` — admin sees all; PMs see jobs whose `jobs.pm_id` matches their `pmId`. Admin can grant access by editing `jobs.pm_id` at `/admin/jobs` (or via the toggle pills at `/admin/users` which PATCH the same endpoint). The legacy per-user `allowedJobs` overlay column is no longer consulted on the main visibility surfaces.

---

Cross-refs: see §3 (Auth + middleware) for the cookie/secret model; §7 (Supabase tables) for the full column lists; §8 (manual-wins protocol) for the universal edit/delete pattern; §9 (Claude tool-use prompts) for the three structured-output prompts (`emit_action_items`, `emit_photo_summary`, `emit_job_summary`, `emit_client_summary`).

---

## §11 GOTCHAS — the hard-won truths

Every entry here represents a real incident or hours of debugging. **Read
this section before assuming anything works the way you'd expect.**

### Database / Supabase

- **Supabase project lives in `us-west-2`.** The cockpit's migrate button used
  to default to `us-east-1` and "succeeded" without actually applying
  anything (the pg client error was swallowed). Fixed 2026-05-20. Pooler
  host: `aws-1-us-west-2.pooler.supabase.com`, port `6543` (transaction
  mode). Port `5432` rejects the password — don't waste time on it.
- **`.overlaps()` doesn't work on jsonb columns.** The sub profile used it
  for `crews_present` / `absent_crews` / `parent_group_activities` and
  silently returned nothing for months. Use per-name containment instead:
  ```ts
  query.filter(col, "cs", JSON.stringify([name]))
  ```
  See `production-cockpit/app/sub/[id]/page.tsx` for the working pattern.
- **PostgREST cache invalidates ~30s after DDL.** If a fresh column reads
  "does not exist" right after a migration, just wait 30s.
- **The service-role key cannot run DDL.** Only PostgREST CRUD. Schema
  changes go through the migrate runner (direct `pg` connection with DB
  password) or pasted into Supabase Studio.

### Vercel

- **TWO Vercel projects** are wired to this GitHub repo: `production-cockpit`
  (the real one, green, serves the live site) and `weekly-meetings` (the
  cosmetic duplicate, red on every commit because its root dir is repo root
  where there's no app). **DANGER — do NOT add a `vercel.json` at the repo
  root to "fix" the red ✗** in the duplicate. Both projects read the repo
  root, so a root `vercel.json` overrides the REAL project's build and the
  live site serves a placeholder. Learned the hard way 2026-05-22; caught +
  reverted in ~1 min. The duplicate can only be removed from the Vercel
  **account dashboard** → `weekly-meetings` → Settings → Delete.
- **Saved Vercel CLI tokens are expired (403).** Don't try to use them;
  re-auth or use the Vercel MCP.
- **Setting an env var doesn't auto-redeploy.** After adding `AUTH_SECRET`
  you must trigger a redeploy from the dashboard or push a new commit.
- **Build cache restoration uses the LAST SUCCESSFUL deploy's cache.** This
  is fine, but it means a failing build that fixes a TS error in a previously
  cached file may still need a fresh cache miss to actually retest. Usually
  not a problem; mentioning for completeness.

### Middleware / Edge runtime

- **Middleware runs in the Edge runtime by default.** It cannot import
  `node:crypto` or `next/headers`. The cookie name + TTL live in
  `lib/auth-constants.ts` (Edge-safe leaf), and `lib/auth.ts` (Node) imports
  from the constants file. Middleware imports ONLY from `auth-constants.ts`.
- **Web Crypto types on Vercel's TS lib are strict.** `Uint8Array` is NOT
  assignable to `BufferSource` directly — must cast `as BufferSource` when
  passing into `crypto.subtle.verify()`. Locally it works without the cast.
  See `middleware.ts:verifyToken`.
- **The `matcher` config must whitelist public assets in `public/`.** Add
  every static file by name (currently `ross-built-logo.svg`,
  `ross-built-mark.svg`) or paths to login redirect to themselves recursively.
- **Cookie verification matters at the middleware layer, not just the page.**
  Middleware used to only check cookie *presence*; after `AUTH_SECRET`
  rotation, browsers still sent the old cookie, middleware let them
  through, then pages got `null` from `currentUser()` and rendered empty.
  Fix: middleware now verifies the HMAC signature via Web Crypto and clears
  invalid cookies on redirect.

### TypeScript / Build

- **Vercel's TS build target rejects `for…of map.values()`** without
  `downlevelIteration`. Use `Array.from(map.values()).forEach(...)` instead.
- **`@typescript-eslint/no-unused-vars` doesn't honor the underscore-prefix
  convention** in the project's ESLint config. An unused `_foo` parameter
  still fails the build. Just delete the param or the function.

### Auth

- **Passwords are plaintext literals in `lib/auth-users.ts`.** Internal MVP
  trade-off; rotating a password means a code edit + redeploy. Move to a
  real provider before opening to anyone outside Ross Built.
- **The `user_overlay.allowed_jobs` column is deprecated.** Visibility =
  `jobs.pm_id` matches `user.pmId`. Admin sees all. The `allowed_jobs`
  column still exists in the table but nothing reads it. Don't add new
  logic that depends on it.
- **Stale cookies after secret rotation** appear as "blank page on /". The
  fix above (signature verification in middleware) handles it.

### Buildertrend integration

- **BT replaced its DOM with a SPA + JSON API in early 2026.** The old
  `scrape.py` (DOM walker) logs in successfully but scrapes 0 logs because
  the DOM is now empty. Use `scrape_api.py` against BT's JSON endpoints.
  See §9.5 for the rebuild story and §9.1 for the endpoint contract.
- **Credential boundary: `python auth.py set` is the one step the user does
  themselves.** The cockpit modal accepts the password and passes it to the
  spawned child as env vars (never logged). Never accept the BT password
  through chat — it ends up in transcripts.
- **MFA flow needs `--headed` the first time.** Subsequent runs reuse the
  Playwright `.session/state.json`.
- **Full-jobs PO + line-items pull takes ~30 min** because it's one request
  per PO. The child timeout is 900s (15 min); the modal requires a jobs
  filter when "Include line items" is on. Grid-only (just totals across all
  jobs) is the fast default (~30s for 1,260 POs).

### Data quality

- **The date scrubber is forward-only.** `lib/scrub-relative-dates.ts`
  catches relative phrases ("tomorrow", "next week", "ASAP") at the write
  boundary and converts them to absolute YYYY-MM-DD or strips the timeframe.
  **Do NOT retroactively rewrite history** — empirically verified 2026-05-20
  that of 211 open todos, the 12 that would change ALL misfire (double dates
  like "2026-05-11 5/11"; "Monday 4/27" → 2026-04-20 anchored on import
  date, not the spoken date; rewrites *inside* quoted source).
- **"Terry" and "Jeff Watts" disambiguation problems exist.** "Terry"
  resolves to TNT Custom Painting when the speaker meant Terry Sprague (a
  mechanical sub). "Jeff Watts" matches plastering scope on a Dewberry
  electrical item. Human-curated alias updates needed; see
  `v1-known-issues.md`.
- **Pay app G703 overflow items are skipped.** Late-added scope rows with
  no line number (e.g. Krauss row 218 "Well abandonment") aren't parsed.
  See `v1-known-issues.md`.
- **`subs.hidden = false` filter is required everywhere subs appear.**
  Subs show up in ~6 places (`/subs`, `/meeting`, sub peers list, `/import`
  pickers, `/v2/review`, job-page sub chips). Miss one filter and deleted
  subs reappear in that surface.

### Operational

- **Auto-commit hook commits but never pushes.** `.claude/settings.local.json`
  defines a hook that runs at end of each turn and commits any pending
  changes with a generic "auto-save" message. Pushing is always manual.
- **The cockpit dev server holds a lock on `production-cockpit/.next/`.**
  Kill node processes before clean builds. Don't kill them while the user
  is working (rule from memory `feedback_project_working_rules.md`).
- **Cleanup zombie `next dev` processes on Windows when "stale data" appears.**
  Server-side cache is `cache: "no-store"`, but a lingering dev process can
  still serve from an in-memory React cache. `Get-Process node | Stop-Process
  -Force` then restart.

### Manual-wins / human edits

- **Human edits always win over re-scrape.** Pattern: `manually_edited_fields
  text[]` + `manually_edited_at` + `hidden` + `hidden_at` columns on every
  scraped table. The upserter fetches existing edit state, skips any column
  listed in `manually_edited_fields`, and never un-hides a `hidden=true`
  row. See §3 for which tables follow this pattern.
- **Soft delete on scraped tables, hard delete on native tables.** `todos`
  and `items` hard-delete because there's no scrape to survive.
- **PO line items upsert on `unique (po_id, bt_line_item_id)`** — not
  delete-and-reinsert. Otherwise edits to line items would be wiped on next
  pull.

### Where things live (cheat sheet)

| Question | Answer |
|---|---|
| Where do I add a new user? | `lib/auth-users.ts` for permanent seed, or via `/admin/users` UI which writes to `user_overlay` |
| Where do I change a PM's jobs? | `/admin/jobs` (sets `jobs.pm_id`) or click-toggle in `/admin/users` (also writes to `jobs.pm_id`) |
| Where's the BT API contract documented? | §9.1 + `reference_bt_scraper_api.md` in user memory |
| Where do I add a new Supabase table? | `RUN_THIS_IN_SUPABASE.sql` AND `MIGRATIONS_SQL` in `app/api/admin/run-migrations/route.ts` (keep both in sync) |
| Where do I add a new AI call? | New route under `app/api/.../route.ts`, use tool-use pattern — see §7 recipe |
| Where do I add a button to the meeting page? | `app/meeting/meeting-client.tsx`, then add the API route under `app/api/.../route.ts` and `revalidatePath('/meeting')` |
| Where's the screenshot proof? | Local `verify-*.png` and `m-*.png` files at repo root, gitignored (client data) |

---

## §12 FORWARD IDEAS

> **Placeholder.** Jake to fill in — or generate via the question-batch session
> with Claude. The orchestrator will ask 10–15 short questions covering: what's
> missing, what UI annoyances need fixing, who else needs to log in, which
> numbers don't you trust, what feature lives in your head but not the code.
> Each answer becomes a § subsection.

### How to add to this section
- One subsection per idea: `### IDEA-N: short title`
- For each: **What** (1–2 sentences), **Why** (the problem it solves), **Where
  it touches** (which § of this blueprint changes), **Risks** (anything that
  could break), **Rough effort** (S / M / L).
- Order by Jake's priority. Move shipped ideas into §1–§11 in the relevant
  section and delete the IDEA entry — keep §12 a living TODO list.

---

## How to use this doc

You're a Claude session (or other AI agent) being asked to work on or rebuild
the Ross Built production cockpit. Here's how to use this blueprint
efficiently:

### If you're rebuilding from scratch

1. **Read §1, §2 first.** Get the intent + stack before touching any code.
2. **Scaffold the schema (§3) before anything else.** The whole system pivots
   on the manual-wins columns and `jobs.pm_id` as visibility source.
3. **Wire auth (§4) before pages.** Middleware + cookie + seed users + the
   `user_overlay` Supabase table. Get `AUTH_SECRET` into env.
4. **Pages (§5) as server components first, no AI yet.** Skeleton render with
   real Supabase queries. Use `dynamic = "force-dynamic"` on data-loading
   pages.
5. **API routes (§6) for CRUD.** Admin panel works → migrate data → home
   shows correct jobs per user.
6. **BT scraper integration (§9) before AI calls.** The pipeline is
   spawn-Python → upsert-Supabase → revalidate. AI is layered on top.
7. **AI calls (§7) last.** They're nice-to-have, not load-bearing. Each one
   follows the same 6-step tool-use recipe at the end of §7.
8. **Python pipeline (§8)** can be ported, rewritten, or kept as-is —
   largely independent of the cockpit. The 3-call brain
   (Extractor/Reconciler/Auditor) is the highest-IQ component and worth
   preserving verbatim.

### If you're maintaining / extending

- **Got a UI change?** Start at §5 (find the page) and §6 (find the API it
  hits). Add `revalidatePath()` for any write that affects another page.
- **Need a new table?** §3 + update both `RUN_THIS_IN_SUPABASE.sql` AND
  `MIGRATIONS_SQL` in `app/api/admin/run-migrations/route.ts`. They must stay
  in sync. Apply via the migrate runner.
- **Adding a new AI call?** Follow the 6-step recipe at the end of §7. Always
  use tool-use; never `JSON.parse` free-text output (that's how the original
  502 happened — see §11).
- **Changing how PMs see jobs?** §4. `jobs.pm_id` is the single source of
  truth — anything that bypasses `canSeeJobByPm` is a bug.
- **Adding a BT data source?** §9. Reverse-engineer the JSON endpoint (BT is
  a SPA → JSON now), add a new scraper script following the existing
  pattern, add `/api/bt/sync-X` that spawns it, add `/v2/api/X/upload` that
  upserts with manual-wins protection.

### If you're debugging

- **First stop**: §11 GOTCHAS. Whatever's going wrong, it's probably already
  documented there.
- **Build errors on Vercel but works locally?** §11 has the TS strict-types
  cheat sheet (Uint8Array → BufferSource, Map iterator → Array.from, etc.).
- **Blank page?** Probably stale cookie after `AUTH_SECRET` rotation. §4 has
  the middleware HMAC verification path that clears bad cookies.
- **Numbers don't match?** Check the source-of-truth quick reference at the
  end of §3.

### Files to read in order if you skim

If you only have 20 minutes:
1. §1 PURPOSE (5 min)
2. §2 ARCHITECTURE (5 min)
3. §3 source-of-truth quick reference (2 min)
4. §11 GOTCHAS (10 min) — these are the things you can't infer from the code

The rest can be referenced as needed.

### Calibration

This document was assembled 2026-05-27 in a single working session by a
multi-agent extraction from the live codebase + STATE.md + HANDOFF.md +
HOW-IT-WORKS.md + user memory + recent git log. Verified against current code.
Cross-reference STATE.md for the most recent operational state; this blueprint
captures the system, STATE.md captures the moment.

— *End of BLUEPRINT.md*
