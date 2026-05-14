# Production Cockpit — Handoff Briefing

## What this is
Internal web app for **Ross Built** (a construction company) that serves as a daily "production cockpit" mirroring action items from the weekly Monday Binder pipeline. It's a mobile-first dashboard with desktop responsive layouts that surfaces todos, priorities, job traffic-lights, pace tracking, and a subcontractor catalog/profile system. Owner/operator: Jake (`jakeross838@gmail.com`).

## Architecture in one paragraph
A Python pipeline (`process.py` + `scripts/`) ingests meeting transcripts and Buildertrend daily logs, classifies them, and writes per-PM action items to local `binders/*.json` files. The same pipeline now also **mirrors** those items to **Supabase** as a second sink (binders JSON remains source of truth — Supabase is read-mostly for the cockpit). The cockpit is a **Next.js 14 App Router** app in `production-cockpit/` that reads from Supabase via server components and has a small write surface (complete/uncomplete/edit-todo). It deploys to **Vercel**.

## Tech stack (exact)
- **Next.js 14.2.35** (App Router, server components by default, `force-dynamic` on routes that read Supabase)
- **Tailwind v4** (`@tailwindcss/postcss`) — note: v4, not v3
- **@supabase/supabase-js 2.105.x** (server client only, service role key)
- **@base-ui/react** for primitives (NOT shadcn — most shadcn components were removed in Task 11)
- **lucide-react** icons, `class-variance-authority`, `clsx`, `tailwind-merge`
- React 18, TypeScript 5, Node (Vercel default)

## Repo layout
The repo is a **monorepo-ish** hybrid: Python pipeline at root, Next.js app in a subfolder.

```
weekly-meetings/                         # GitHub: jakeross838/weekly-meetings
├── process.py                           # main pipeline; calls sink_to_supabase
├── scripts/
│   ├── sync_subs.py                     # refresh subs catalog into Supabase
│   ├── backfill_sub_links.py            # regex-match canonical aliases
│   ├── ai_link_subs.py                  # Claude Haiku classifier fallback
│   └── test_supabase_sink.py            # smoke test all 5 PMs
├── binders/                             # GITIGNORED — per-PM JSON, source of truth
├── data/, transcripts/, etc.            # GITIGNORED — sensitive client data
├── docs/superpowers/
│   ├── specs/2026-05-13-production-cockpit-design.md
│   ├── plans/2026-05-13-production-cockpit.md       # v1 plan (shipped)
│   └── plans/2026-05-13-cockpit-v2.md               # v2 plan (Tasks 1-12)
└── production-cockpit/                  # ← Vercel Root Directory = this folder
    ├── app/
    │   ├── page.tsx                     # / — todos grouped by PM (Open/Done views)
    │   ├── pace/page.tsx                # /pace — 4-week per-PM trend
    │   ├── selections/page.tsx          # /selections — open SELECTION-category todos by job
    │   ├── sub/[id]/page.tsx            # /sub/<id> — sub profile (rating, avg days/job)
    │   ├── subs/page.tsx                # /subs — sub catalog
    │   ├── api/
    │   │   ├── complete/route.ts        # POST {id} → COMPLETE, captures previous_status
    │   │   ├── uncomplete/route.ts      # POST {id} → revert to previous_status
    │   │   └── edit-todo/route.ts       # POST {id,title} → edited_title + edited_at
    │   ├── layout.tsx, globals.css, favicon.ico
    ├── components/
    │   ├── header.tsx, logo.tsx (RossBuiltMark)
    │   ├── stats-bar.tsx, filters.tsx, trade-select.tsx
    │   ├── pm-section.tsx               # PM group with job traffic-lights
    │   ├── todo-row.tsx                 # row with sub chip, edit affordance
    │   ├── completed-section.tsx        # "Recently Completed" with Undo
    │   ├── priority-panel.tsx           # top-5 most-critical (server component)
    │   ├── edit-todo.tsx                # inline edit (client component)
    │   └── undo-button.tsx              # client component on Done rows
    ├── lib/
    │   ├── supabase.ts                  # supabaseServer() using service role key
    │   ├── types.ts                     # Todo, PM, Sub, SubEmbedded, Priority, Status
    │   ├── job-status.ts                # pure fn → GREEN/AMBER/RED per job
    │   ├── date.ts, week.ts, utils.ts
    ├── .env.local                       # GITIGNORED (SUPABASE_URL, SERVICE_ROLE_KEY)
    ├── .vercel/project.json             # links to Vercel project id
    └── next.config.mjs, tsconfig.json, package.json
```

## What's built (full feature list as of HEAD = `3b46746`)

**v1 (commit `7a9d245`):**
- Todos grouped by PM, Open/Done toggle
- Tap-to-complete via `/api/complete`
- Sub chip on each todo row → links to `/sub/[id]` profile
- Sub catalog at `/subs` with sort/filter by trade
- Sub rating algorithm (5.0 baseline minus deductions: PM-binder flags, return-burst rate, punch-burst rate, dragging-density)
- Recently Completed section at bottom of Open view
- Ross Built branding (slate/sand/stone palette, Space Grotesk/Inter/JetBrains Mono, architectural roofline logo)

**v2 (Tasks 1-11, commits `c0a6488` → `3b46746`):**
1. Schema migration: added `previous_status`, `edited_title`, `edited_at` columns to `todos`
2. `/api/complete` now captures `previous_status`; new `/api/uncomplete` route
3. Undo button on Done rows + Recently Completed section
4. `/api/edit-todo` + inline edit-todo UI
5. Top-5 Priority Panel on home (server component)
6. `/selections` dashboard — open SELECTION-category todos by job
7. Job traffic light (GREEN/AMBER/RED) per job, rendered in `PMSection`
8. `/pace` 4-week-trend dashboard per PM
9. Sub profile: replaced Reliability% with Avg days per job; per-todo elapsed days
10. Desktop responsive layout (container scales 480px mobile → 1200px desktop via `lg:`)
11. Simplification pass: dropped unused shadcn primitives (button, card, select, switch, collapsible) and leftover Geist fonts from scaffold

**Task 12 — Deploy + final verification:** in progress (see "Deployment status" below).

## Deployment status (as of 2026-05-14)
- **GitHub repo:** `https://github.com/jakeross838/weekly-meetings` (public branch: `main`)
- **Vercel project:** `production-cockpit` (org: `jakeross838's-projects`, project id `prj_q8LShfLv16TAowa8deF3Du3GzG9O`)
- **Live URL:** `https://production-cockpit.vercel.app`
- **Vercel Root Directory:** `production-cockpit` ✓ (set on 2026-05-14 — was empty before)
- **Git connection:** connected on 2026-05-14; the prior 9 deployments were CLI deploys, not git-triggered
- **Local branch state:** clean, `main` synced with `origin/main` at commit `3b46746`
- **Next git push:** will trigger first git-based production deploy
- **Production Branch:** `main` (master also exists in remote dropdown but main is canonical)

## Supabase setup
- **Project ID:** `takewvlqgwpdbkvcwpvi` (region: us-west-2)
- **Connection (admin/migrations):** psycopg2 to `aws-1-us-west-2.pooler.supabase.com:5432`, user `postgres.takewvlqgwpdbkvcwpvi`
- **Tables used:**
  - `todos` — columns include id, pm_id, job, title, due_date, priority, status, type, category, created_at, completed_at, source_transcript, source_excerpt, sub_id, **previous_status**, **edited_title**, **edited_at**
  - `pms` — id, full_name, active
  - `subs` — id, name, trade, rating, reliability_pct, avg_days_per_job, aliases, jobs_performed, flagged_for_pm_binder, flag_reasons, rating_basis, notes, updated_at
- **TypeScript types** live in `production-cockpit/lib/types.ts`
- **Status enum:** `NOT_STARTED | IN_PROGRESS | BLOCKED | COMPLETE`
- **Priority enum:** `URGENT | HIGH | NORMAL`
- **OPEN_STATUSES:** `["NOT_STARTED", "IN_PROGRESS", "BLOCKED"]`

## Environment variables (Vercel)
Already configured (the live site works). The cockpit only reads these two:
- `SUPABASE_URL` — the Supabase project REST URL
- `SUPABASE_SERVICE_ROLE_KEY` — service role (server-only; never expose to client)

The Python pipeline at the repo root uses additional vars in `.env`: `ANTHROPIC_API_KEY`, `SUPABASE_DB_PASSWORD` for psycopg2 migrations, plus Buildertrend scraper creds.

## What's NOT in the repo (intentionally)
- `binders/` — per-PM JSON action item state (source of truth)
- `data/`, `transcripts/`, `api-responses/`, `state/`, `logs/`, `tmp-pdfs/`, `exports/`, `print/` — sensitive client/sub/financial data
- `.env`, `production-cockpit/.env.local` — secrets
- A fresh `git clone` will NOT have working pipeline data; cockpit can still build/deploy because it only needs Supabase env vars.

## Working environment gotchas (Windows)
- **Git on this machine** requires `safe.directory` override per command (don't modify global config):
  ```
  git -c safe.directory='*' commit -m "..."
  ```
- **Dev server lock:** `npm run dev` holds a lock on `production-cockpit/.next/`. Kill node processes before clean builds:
  ```
  powershell -Command "Get-Process node | Stop-Process -Force"
  rm -rf production-cockpit/.next
  ```
- **PostgREST cache** invalidates ~30s after DDL — if a new column "doesn't exist" right after a migration, wait.

## Open items / what to do next
1. **First git-triggered deploy** — push any commit (or click "Redeploy" on the latest deployment in Vercel) to confirm the git pipeline works end-to-end with the new Root Directory setting.
2. **Task 12 verification** — the v2 plan's final task is end-to-end verification across all 11 features after deploy.
3. The v2 plan doc at `docs/superpowers/plans/2026-05-13-cockpit-v2.md` (1760 lines) has step-by-step detail for every task if you need to re-execute or audit anything.

## Key files to read first
1. `production-cockpit/app/page.tsx` — main entry, shows the data shape
2. `production-cockpit/lib/types.ts` — the data model in one screen
3. `production-cockpit/lib/supabase.ts` — server client pattern
4. `docs/superpowers/specs/2026-05-13-production-cockpit-design.md` — design rationale
5. `docs/superpowers/plans/2026-05-13-cockpit-v2.md` — what was built in the last day
