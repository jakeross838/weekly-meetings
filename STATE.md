# Ross Built — Project State & Handoff

**Last updated:** 2026-05-29 (auth + admin + brand session)
**Read this first.** It's the single source of truth for where the project is and how to finish it.

---

## 1. The end goal (your vision, recapped)

One mobile-first, dead-simple **interactive document per job** that runs the Monday meetings. It ingests everything about a job — **meeting transcripts + Buildertrend daily logs + pay-app line items** — cross-checks claims, and shows one trustworthy, tappable list everyone (office screen / your iPad on site / PM's phone) works off of. Simplicity and mobile are the point. (Full vision: `v2-plan.md`.)

Two systems exist:
- **`production-cockpit/`** — Next.js + Supabase web app. **This is the future** and where all current work happens. Mobile-first, interactive.
- **`monday-binder/`** + `process.py` — the older Python→PDF system that still produces the Monday packets (shipped milestone m02). Untouched this session; keep it as the live fallback until the cockpit fully replaces it.

---

## 2. What works RIGHT NOW (verified live this session)

The DB schema is **applied to production Supabase** (us-west-2) and every cockpit feature was tested against real data + a browser.

| # | Feature | Status |
|---|---------|--------|
| 1 | Per-row **Job** dropdown on import (e.g. reassign to Dewberry) | ✅ persists to the todo |
| 2 | **No broad timeframes in todos** — exact dates only | ✅ 30 unit tests + live (`tomorrow`→date, `ASAP` stripped, `next week`→+7) |
| 3 | **Crew size** per task on sub profiles | ✅ rendered `~4.0 crew` from a daily log |
| 4 | A–F grading removed | ✅ |
| 5 | **How long each sub takes** per schedule item (T-Pole, Electrical Rough…) | ✅ durations + 37 seeded canonical items |
| 6 | **Inspections** per sub | ✅ rendered `Rough Drywall — PASS` |
| 7 | **Running checklist** (Safety + Schedule lenses) | ✅ add/toggle/remove |
| 8 | **Daily-log photo → AI context** | ⏳ code complete; needs real photos (blocked on BT login — see §4) |

Also verified: home/jobs, /subs, /sub/[id], /v2/job/[id] (with AI Summary panel), /import, /admin/migrate, /v2/review all render; complete/uncomplete, sub-specialties, daily-logs upload, extract-photos, and the AI job summary (F9) all work. **Production build passes (31 routes).**

**2026-05-22 — Purchase Orders + universal edit/delete (manual-wins).** Full BT pull live: **1,260 POs + 2,099 line items across 28 jobs** in Supabase, shown per-job on `/v2/job/[id]` (committed/paid/outstanding + expandable line items). Every PO field, every line item, the sub profile (name/trade/notes/aliases), and todo/item rows are now **click-to-edit + deletable**. Edits/deletes **survive re-scrape** via manual-wins columns (`manually_edited_fields`, `hidden`) on `purchase_orders`/`po_line_items`/`daily_logs` (+ `subs.hidden`) — uploads skip edited columns and never un-hide deletes. Proven by a reversible 22/22 stress test (edit→re-upload→survived; delete→re-upload→stayed gone) and a mobile+desktop UI pass. New: `components/editable-text.tsx`, `components/delete-button.tsx`, and 10 edit/delete API routes. See CHANGELOG 2026-05-22.

---

## 3. What changed this session (the fixes that made it real)

These were the reasons the features looked "built" but did nothing:

1. **Schema was never applied.** The migrate button pointed at the **wrong AWS region** (`us-east-1`); your project is `us-west-2`. Fixed `app/api/admin/run-migrations/route.ts` and applied the full F3–F9 schema (crew_counts, inspections, photo_urls/summary, `schedule_items` seeded, `sub_checklist_items`, `job_summaries`, `sub_specialties.schedule_item_id`).
2. **`.overlaps()` doesn't work on Supabase `jsonb`.** The sub profile used it for crews/inspections/timeline, so they silently returned nothing. Rewrote those queries to jsonb-safe containment (`app/sub/[id]/page.tsx`). See `[[reference-supabase-jsonb-no-overlaps]]` in memory.
3. **Date rule** built + wired at 3 write boundaries (`lib/scrub-relative-dates.ts`).
4. **Synced `RUN_THIS_IN_SUPABASE.sql`** to the full schema.
5. **Auto-commit hook** added (`.claude/settings.local.json`) — commits pending changes at the end of each turn (run `/hooks` once to activate; commit-only, never pushes).
6. **Cleaned** all mock/test data — production DB is clean and awaits real data.
7. **UI / Ross Built blue branding pass.** Confirmed the palette is correct stone-blue (matches rossbuilt.com). Made primary action buttons (`Push to to-do list`, `Run migrations`) use the brand stone-blue (`bg-ink`, hover → lighter `accent`) instead of off-brand green — green now means "done/success" only, matching their site's dark CTA style. Fixed a mobile layout bug on `/v2/job/[id]` where the "plaud transcript to approve" pill squeezed the address into an ugly 3-line wrap (now stacks below the title on phones).
8. **Freshness hardening** (`lib/supabase.ts`): server Supabase reads now use `cache: "no-store"` so Next's Data Cache can't serve stale data. (A stale job-summary I chased turned out to be leftover zombie `next dev` processes on Windows, not a prod bug — but no-store makes freshness explicit and safe.)

---

## 4. Buildertrend scrape — REBUILT & WORKING (2026-05-20)

This *was* the blocker. Root cause: **BT replaced its old HTML UI with a modern SPA + JSON API**, so the DOM-walking `scrape.py` logged in but scraped **0 logs**. Rebuilt against BT's real API → **`buildertrend-scraper/scrape_api.py`**, and pointed the one-click button at it.

How it works now (`scrape_api.py`):
1. `POST /api/jobpicker/GetJobPickerData {templatesOnly:false}` → active jobs (name→internal id; names match `jobs.py` JOB_NAME_MAP).
2. `GET /api/Filters/31?jobID=` → crew id→name map.
3. `POST /apix/v2/DailyLogs/grid` (paged) → full log rows: date, crews, absent crews, weather (max/min temp), daily workforce, notes, **photos (direct URLs, downloaded locally)**.

**Verified end-to-end 2026-05-20:** pulled **150 real logs across all 11 jobs** (74 distinct subs) → Supabase → sub profiles show real on-site timelines/crews. Photos confirmed downloading (Krauss: 20 photos).

**To run it:** just use the **"✨ Pull from Buildertrend"** button on `/import` (local cockpit) — type your BT email + password in the modal. It reuses the saved session when valid, re-logs in when not. (Terminal equivalent: `python auth.py set` once, then `python scrape_api.py --days 14`.) MFA: tick "Show browser window" the first time. **Don't paste the BT password in chat — only into the modal/terminal.**

---

## 5. How the daily-log → meeting pipeline works (the "button")

`/import` → **"✨ Pull from Buildertrend"** (`components/bt-sync-button.tsx` → `POST /api/bt/sync`, local-only):
1. You enter BT email+password in the modal (password never stored in the browser).
2. Server spawns the Python scraper (creds passed as env vars, never logged).
3. Scraper logs in, walks each job's Daily Logs, extracts crews + **crew_counts + activities + inspections**, downloads photos, writes `data/daily-logs.json`.
4. Route upserts into `daily_logs` (dedupe on `job_key+log_id`).
5. If "run vision" is on → Claude vision over new photos → `photo_summary`.
6. Modal reports: logs / jobs / photos / upserted / vision processed.

That data then surfaces on **sub profiles** (crew size, inspections, timeline, photo context) and feeds the **AI job summary** on `/v2/job/[id]` — which is the meeting document.

**Meeting flow (mobile):** open `/` (all jobs, sorted by past-due) → tap a job → read the AI Summary → work the Today/Soon/Open todos, tapping to check off → check sub profiles for accountability. Everyone on the same URL on their phone.

---

## 6. Deploy (LIVE — fully reconciled with origin/main)

As of 2026-05-29, `main` and `origin/main` are at the same commit (`a65fc72`) and Vercel
auto-deploys from `main` — so everything in this document is live on
production-cockpit.vercel.app. No held commits, no deploy gap. The May 22 "13 commits
held" warning is resolved.

If a future deploy needs a rollback, Vercel dashboard → Deployments → Promote a prior
build. Don't `git push --force` to main.

---

## 7. Remaining roadmap toward the full vision (prioritized)

Shipped 2026-05-20 (built, verified live, deployed to prod):

- ✅ **Pay-app backbone** — `/v2/job/[id]` shows a Contract Progress card
  (Σ total_completed / Σ scheduled_value) + collapsible cost breakdown by line
  description (biggest contract first). Data on 5 jobs (krauss/pou/dewberry/
  fish/drummond), one pay app each; renders nothing on jobs without one.
  Verified: Krauss 48% ($2.03M / $4.26M).
- ✅ **By-PM view** — home (`/`) has "All PMs" + per-PM filter pills
  (`/?pm=<id>`, from `job_pm_assignments` → `jobs.pm_id` fallback); the
  open/past-due header counts reflect the filtered PM.
- ✅ **Flags lane** — `/subs` has a "⚑ Flagged · N" filter pill + gold marker
  on flagged rows (reason inline in the lane); `/sub/[id]` shows a flag banner
  with all `flag_reasons`. Framed as an auto-derived signal ("confirm in
  person before acting"), not a verdict — honors manual-wins / human-review.
- ✅ **Sub health pill (RED/YELLOW/GREEN)** — factual triage, not a grade
  (A–F stays removed): RED = past-due open todos, YELLOW = flagged OR a todo
  due within 7d, GREEN = clear (the auto-flag tops out at yellow, never red).
  Tested helper `lib/sub-health.ts` (7 cases in `npm test`); a status dot leads
  every `/subs` row (beside the ⚑), labeled pill on `/sub/[id]`. Verified:
  30 red / 14 yellow / 62 green across 106 subs.
- ✅ **Meeting run-of-show** (`/meeting`, in Header nav) — guided job-by-job
  Monday-meeting agenda from live signals: per job Past due / This week (≤7d) /
  Subs to watch (health pill + flag reason, routed from subs working that job),
  + contract % + transcripts-to-approve. PM scope pills, urgency sort, sticky
  progress bar with a per-job "mark covered" walk-through (ephemeral client
  state). NO fabricated PPC%/predictions — only data the cockpit has. NOTE: it
  exposes a large real backlog (≈186 past-due todos) — accurate, not a bug;
  many are stale historical items worth a closeout pass.

Shipped 2026-05-22 (reliability hardening + full QA pass):

- ✅ **All 3 Claude calls hardened with tool-use** — the job-summary,
  transcript-extractor, and photo-vision routes asked Claude for free-text JSON
  then `JSON.parse`'d it, which 502'd on malformed output (the Generate-Summary
  button was failing exactly this way). All three now use tool-use with an
  `input_schema`, so output is structurally guaranteed — no regex, no
  `JSON.parse`. Files: `app/api/jobs/[id]/refresh-summary/route.ts`,
  `app/api/import-transcript/route.ts`,
  `app/v2/api/daily-logs/extract-photos/route.ts`. Each verified live.
- ✅ **Full button-by-button QA** — home PM pills; meeting covered-toggle /
  reset / scope pills; subs trade + flagged filters + RYG dots; sub editors
  (specialties + checklist add/toggle/edit/delete, test data reverted); job
  cost-breakdown, category pills, check-off (+re-open), generate-summary;
  import BT modal; review queue + detail. One real bug (summary 502) found +
  fixed; BT scraper re-verified end-to-end (full pull → Supabase → vision → live).

Shipped 2026-05-27 (real auth + admin hub + meeting UI polish):

- ✅ **Real login + PM-scoped views** — moved off the user-overlay JSON to Supabase
  (persists in prod). Visibility is driven by `jobs.pm_id` (not an overlay), with
  `revalidatePath` on edits so PM changes show up immediately.
- ✅ **/admin hub + /admin/jobs CRUD** — middleware verifies HMAC; an admin user
  panel manages access.
- ✅ **Meeting run-of-show redesign** — cards + color-coded buckets, roomier
  layout, category sub-grouping.
- ✅ **Import hardening** — cache-bust on PO/CO/log uploads, CO history visible,
  local-only banner for clarity.
- ✅ **BLUEPRINT.md** — comprehensive system extraction doc committed for handoff /
  onboarding context.

Shipped 2026-05-29 (auth go-live + admin reliability + brand v3):

- ✅ **Self-signup with password + post-login "request access" flow** — new users
  can register themselves; admin gates approval.
- ✅ **Forgot-password + public signup with admin approval (Resend)** — email is
  sent via Resend with a Supabase fallback if `RESEND_API_KEY` is missing.
- ✅ **2nd admin added** (`jakeross838@gmail.com`) so Resend's free-tier
  addressable-email rule doesn't block approval emails.
- ✅ **7 admin sync bugs closed** in users/jobs/migrate flows; create-PM now
  actually assigns the picked jobs; clearer `pmId` UI; real confirm modal +
  bigger color-coded action buttons; `/subs` gated; Migrations card hidden from
  the admin hub; "+ Add new" jump links above existing lists.
- ✅ **Brand palette v3** — warmer base, cooler/lighter "oceanside grey-blue"
  family; motion + blue brand band + staggered list reveals.
- ✅ **Crew-name import fix** — strips trailing `(N)` headcount from crew names
  so auto-sub creation matches canonical subs (no more duplicate "Acme (4)"
  vs "Acme" subs).
- ✅ **Manual sticky-note replaces auto density/burst-rate flag on subs** — the
  derived signal was noisy; a human-written note is more honest and matches the
  manual-wins philosophy.

Still open — larger, need your editorial calls (don't build blind):

1. **The 3-call brain in-app** — Extractor/Reconciler/Auditor still run offline
   in Python; `/v2/review` shows pending transcripts awaiting approval. Biggest
   remaining lever; touches the core pipeline — wants a scoped design pass.
2. **Meeting prediction / preflight** (Phase 13 in the spec) — the run-of-show
   renders today's state; it does NOT yet forecast (PPC% reliability, 2/4/8-wk
   look-ahead from a schedule/taxonomy, Office-vs-Site scope). Those need data
   not in the cockpit (commitment history, phase taxonomy, on-site-this-week).
3. **Whole-company view** polish on home (partial today).

Confirmed-skip:

- **Date-rule backfill** over existing todos — empirically re-verified
  2026-05-20: of 211 open todos, 12 would change and ALL misfire (double-dates
  like "2026-05-11 5/11"; wrong anchors — "Monday 4/27" → 2026-04-20 because
  the anchor is the import date, not the spoken date; rewrites *inside* quotes).
  The forward-only scrub at the write boundary is correct; do NOT rewrite
  history.

---

## 8. Gotchas / how to resume

- **Run cockpit locally:** `cd production-cockpit; npm run dev` → http://localhost:3000
- **Run tests:** `cd production-cockpit; npm test`
- **Re-seed a demo (no BT needed):** `cd C:\Users\Greg\buildertrend-scraper; python scrape.py --mock` then upload `data/daily-logs.json` via the import page's manual upload. (Purge after: delete `daily_logs` rows.)
- **DB password** is in `.env` as `SUPABASE_DB_PASSWORD` — **rotate it** (it was shared in chat). Migrations apply via `/admin/migrate` or `node` + `pg` against `aws-1-us-west-2.pooler.supabase.com:6543`.
- **jsonb columns** (`crews_present`, `absent_crews`): never use `.overlaps()` — use per-name `.filter(col,"cs",json)` containment.
- **Screenshots** (`verify-*.png`, `m-*.png`) are local-only proof shots — gitignored via `/*.png` (this repo is public; client data must never be committed). They render the features with real data but are not in git.
- **TWO Vercel projects** are wired to this repo: `production-cockpit` (the real app — GREEN, serves production-cockpit.vercel.app) and `weekly-meetings` (a duplicate whose root dir is the repo root, where there's no app — so it's RED on every commit). The red ✗ is **purely cosmetic** and does not affect the live site. **DANGER — do NOT add a `vercel.json` at the repo root to "fix" it:** BOTH projects read the repo root, so a root `vercel.json` overrides the REAL project's build and the live site serves a placeholder (learned the hard way 2026-05-22; caught + reverted in ~1 min). The duplicate can only be removed from the Vercel **account** (dashboard → `weekly-meetings` → Settings → Delete, or the Vercel MCP OAuth). The saved Vercel CLI tokens in `%APPDATA%/Roaming/com.vercel.cli/Data/auth.json` are **expired (403)**.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
