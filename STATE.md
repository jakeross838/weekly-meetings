# Ross Built — Project State & Handoff

**Last updated:** 2026-05-20 (autonomous session)
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

## 4. THE ONE BLOCKER — Buildertrend login (your single step)

Real daily logs + photos (item 8, and real data for 3/5/6) need a working BT scrape. The scraper at `C:\Users\Greg\buildertrend-scraper` has **no credentials on file** and its last login failed. I can't supply your BT password — that's the one boundary that's yours.

**To unblock:**
```powershell
cd C:\Users\Greg\buildertrend-scraper
.\.venv\Scripts\Activate.ps1
python auth.py set        # enter BT email + password (stored in Windows Credential Manager)
python scrape.py --headed --days 14   # --headed first time in case BT shows MFA
```
Then in the cockpit, the data flows automatically (or use the button — see §5).

**Two credential paths (this trips people up):**
- **Terminal** `python scrape.py` → reads Windows Credential Manager (`auth.py set`).
- **"Pull from Buildertrend" button** → uses the email+password you type **into the modal** (not the keyring).

If login still lands on the login page with a correct password, BT changed its Auth0 form and the selectors in `bt_session.py` need updating (re-run `--headed`, inspect, patch).

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

## 6. Deploy (HELD — your call; bigger than it looks)

**Local `main` is 13 commits ahead of `origin/main`.** Your live Vercel site is running **old** code — it does NOT have the per-job AI summary, the Pull-from-Buildertrend button, the sub crew-size/checklist/vision features, or any of this session's fixes. All of that is committed locally but never deployed.

I did **not** push, on purpose: an unsupervised production deploy of 13 commits of accumulated features to the tool your PMs use Monday morning is too high-stakes to do without you watching. It's **build-verified** (31 routes, 0 errors) and the prod Supabase schema is already applied, so it's ready — but you should be the one to pull the trigger:
```powershell
cd "P:\Claude Projects\weekly-meetings"
git log --oneline origin/main..HEAD   # review the 13 commits first
git push                              # triggers the Vercel production deploy
```
If anything looks off after deploy, Vercel's dashboard can instant-rollback to the current live build.

---

## 7. Remaining roadmap toward the full vision (prioritized)

Not done — these are larger and need your editorial calls (don't build blind):

1. **Pay-app backbone** — the v2-plan's load-bearing idea (`pay_app_line_items` as the master list everything attaches to). Schema exists; not surfaced in the cockpit UI. Biggest lever.
2. **Three views** — by-job (have it) + **by-PM** (missing) + whole-company (home, partial). A `/pm/[id]` view is squarely in the vision.
3. **The 3-call brain in-app** — currently the Extractor/Reconciler/Auditor run offline in Python; `/v2/review` shows 4 pending transcripts (208 proposals) awaiting your approval.
4. **RED/YELLOW/GREEN sub pills + real meeting structure** — fully specced in `.planning/.../12-integrated-redesign/PLAN.md` (Parts A/B/C), never built. Read that doc; it's the next big build.
5. **Flags lane** (slipped commitments, drift) on the job document.
6. **Date-rule backfill** over the 268 existing todos — deliberately skipped (many old titles pair a weekday with a real date, so a blind rewrite would corrupt them; needs a careful, reviewed pass).

---

## 8. Gotchas / how to resume

- **Run cockpit locally:** `cd production-cockpit; npm run dev` → http://localhost:3000
- **Run tests:** `cd production-cockpit; npm test`
- **Re-seed a demo (no BT needed):** `cd C:\Users\Greg\buildertrend-scraper; python scrape.py --mock` then upload `data/daily-logs.json` via the import page's manual upload. (Purge after: delete `daily_logs` rows.)
- **DB password** is in `.env` as `SUPABASE_DB_PASSWORD` — **rotate it** (it was shared in chat). Migrations apply via `/admin/migrate` or `node` + `pg` against `aws-1-us-west-2.pooler.supabase.com:6543`.
- **jsonb columns** (`crews_present`, `absent_crews`): never use `.overlaps()` — use per-name `.filter(col,"cs",json)` containment.
- **Screenshots** `verify-walter-drywall-*.png` are committed proof the features render with data.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
