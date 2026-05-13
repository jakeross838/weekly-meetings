# Production Cockpit v1 — Design

**Date:** 2026-05-13
**Status:** Approved (Jake, 2026-05-13)
**Scope:** Add a single-user mobile cockpit on top of the existing weekly-meetings pipeline. Read-from + complete-into Supabase. Existing pipeline untouched except for one additive sink in `process.py`.

## Goals

- Jake (Production Director) can pull up a phone, see all open todos across the 5 PMs, filter, and tap-to-complete.
- Pipeline guarantees unchanged: Plaud → `process.py` → `binders/*.json` → `monday-binder/*.pdf` keeps working bit-for-bit identically.
- Supabase is a mirror of `binders/*.json`, refreshed every time `process.py` runs. v1 is one-way (binder → Supabase, plus the tap-to-complete API that writes only to Supabase).

## Non-goals (v1)

- No transcript ingestion via the cockpit.
- No phases / subs / insights / source drill-down.
- No write-back from Supabase → `binders/*.json`. Tap-to-complete updates Supabase only; the next Monday's binder will still show the item OPEN until the next transcript closes it.
- No auth. Vercel password protection deferred.
- No RLS. Service-role key used everywhere; cockpit is single-user.

## Architecture

```
Plaud .txt  ─►  process.py  ─►  binders/<PM>.json   ─►  monday-binder PDFs
                    │                                      (UNCHANGED)
                    │ (NEW, additive, lossy-safe sink)
                    ▼
                Supabase todos table  ◄────────  Next.js cockpit (production-cockpit/)
                                                    page.tsx (server component)
                                                    api/complete (POST)
```

## Data model

### Supabase tables

```sql
create table pms (
  id text primary key,                -- 'martin', 'jason', 'lee', 'bob', 'nelson'
  full_name text not null,
  active boolean default true
);

create table todos (
  id text primary key,                -- 'FISH-001' (binder id)
  pm_id text references pms(id),
  job text not null,                  -- 'Fish', 'Krauss', 'Markgraf', ...
  title text not null,                -- from item.action
  due_date date,
  priority text,                      -- URGENT | HIGH | NORMAL
  status text default 'OPEN',         -- NOT_STARTED|IN_PROGRESS|BLOCKED|COMPLETE
  type text,                          -- SELECTION|CONFIRMATION|...
  category text,                      -- SCHEDULE|PROCUREMENT|...
  created_at timestamptz default now(),
  completed_at timestamptz,
  source_transcript text,
  source_excerpt text                 -- item.update (Claude's note)
);
create index on todos (pm_id, status, due_date);
```

Note: column default for `status` is `'OPEN'` per the brief, but our writes always set an explicit value (one of NOT_STARTED/IN_PROGRESS/BLOCKED/COMPLETE) so the default is never observed. Kept as-is to match the brief.

### Seed (pms)

| id | full_name |
|---|---|
| martin | Martin Mannix |
| jason | Jason Szykulski |
| lee | Lee Worthy |
| bob | Bob Mozine |
| nelson | Nelson Belanger |

All `active=true`.

### Field mapping (binder item → todos row)

| `todos` column | source |
|---|---|
| `id` | `item.id` |
| `pm_id` | derived: `pm_name.split(" ")[0].lower()` |
| `job` | `item.job` |
| `title` | `item.action` |
| `due_date` | `item.due` (null if empty / unparseable) |
| `priority` | `item.priority` |
| `status` | `item.status` (verbatim; DISMISSED skipped — see below) |
| `type` | `item.type` |
| `category` | `item.category` |
| `created_at` | `item.opened` parsed → midnight UTC (overrides table default) |
| `completed_at` | `item.close_date` when status=COMPLETE; else NULL |
| `source_transcript` | original transcript filename captured before `archive_transcript` renames it |
| `source_excerpt` | `item.update` |

**DISMISSED items are skipped** at sink time (no upsert).

## Components

### 1. `process.py` addition

New function `sink_to_supabase(pm_name: str, binder: dict, transcript_filename: str, logger)` called immediately after `save_binder(...)` succeeds in `process_transcript`. Wrapped in try/except — any exception is logged and swallowed.

- Reads `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` from env (loaded from `.env` at startup via `python-dotenv`).
- Iterates `binder["items"]`, skips status==DISMISSED, builds row dicts, calls `client.table("todos").upsert(rows, on_conflict="id").execute()`.
- Returns count of rows upserted; logger logs `"Supabase: upserted N rows for {pm_name}"` or the error.

Sink failure does **not** affect the return value of `process_transcript`. binder JSON is the source of truth and remains so even if Supabase is unreachable.

### 2. `production-cockpit/`

Fresh Next.js 14 (App Router, TS, Tailwind) project.

- `app/page.tsx` — async server component. Reads `searchParams` for `pm`, `job`, `view` (open|done). Fetches via supabase-js server client. Renders header, stats bar, filters (Select + Switch), PM-grouped sections (Collapsible) with todo rows.
- `app/api/complete/route.ts` — POST handler. Reads `{ id }` from body. `update().eq("id", id)` setting `status='COMPLETE'`, `completed_at=now()`. Returns `{ ok: true }`.
- `lib/supabase.ts` — server-side client factory using `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` from `process.env`.
- Components from shadcn: Card, Button, Select, Switch, Collapsible.
- Layout: max-width 480px, centered, mobile-first.

### 3. .env files (both gitignored)

Project root `.env`:
```
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

`production-cockpit/.env.local`:
```
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Same values, two files (Python and Next.js each load their own).

## Error handling

- **Supabase down during process.py**: log + continue. binders/*.json still written. Next process.py run will re-upsert and converge.
- **Supabase down during cockpit load**: server component throws → user sees error UI. Page is read-only on the server; no SWR/retry needed in v1.
- **Tap-to-complete failure**: optimistic UI marks done immediately. If POST fails, surface a toast and roll back. Fallback: refresh page → row reappears.
- **Network from process.py**: 10s timeout, no retry. Stale data converges next run.

## Idempotency

- `process.py` upserts by `id`. Re-running on the same transcript (via SHA dedupe it won't re-run; but if forced) produces identical Supabase state.
- `created_at` always set to `item.opened` so re-runs don't drift.
- `completed_at` set to `item.close_date` for COMPLETE items; if a previously-tapped-done item gets re-upserted from a binder that hasn't yet been updated to COMPLETE, the upsert will overwrite `status` and `completed_at` from binder values. **This is a known v1 limitation** — tap-to-complete is transient until the next Monday transcript closes the underlying item.

## Testing / verification

After build:
1. **Pipeline unchanged**: Run `process.py` with no transcripts. Diff `binders/Martin_Mannix.json` before/after — must be byte-identical. Diff a representative `monday-binder/meeting-prep/*.pdf` — must be unchanged.
2. **Sink works**: Re-run on an existing transcript SHA (force) and confirm Supabase rowcount matches `len(binder.items) - count(status==DISMISSED)` per PM.
3. **Cockpit reads**: `npm run dev` in `production-cockpit/`, open `localhost:3000`, confirm rows display, PM filter works, Job filter populates by PM, Open/Done switch flips counts.
4. **Tap-to-complete**: Tap a row, confirm it animates out, check Supabase: `status='COMPLETE'`, `completed_at` set. Refresh page; row gone from Open view, present in Done view.

## Open trade-offs (flagged for Jake)

1. **`source_excerpt` semantics**: stores Claude's `update` note, not a verbatim transcript quote. The transcript text isn't preserved in the binder data model; extracting verbatim would require touching `weekly-prompt.md` which is out of scope.
2. **Tap-to-complete is Supabase-only**: doesn't write back to `binders/*.json`. Next Monday's PDFs will still show tapped-done items as IN_PROGRESS until the next transcript closes them. v2 candidate.
3. **DISMISSED hidden everywhere**: items dismissed in the binder don't appear in Supabase at all. Debugging requires checking `binders/*.json`.
4. **No retry on sink failure**: if Supabase is down when `process.py` runs, that PM's items won't sync until the next run. SHA dedupe means we can't force a re-run without manually editing the ledger.
5. **Service-role key in Next.js env**: bypasses RLS by design (single-user app). Vercel password protection is the auth boundary. Don't ship the URL publicly without that.

## File changes summary

**New files:**
- `production-cockpit/` (full Next.js scaffold + shadcn components)
- `.env` (root, gitignored)
- `production-cockpit/.env.local` (gitignored)
- `docs/superpowers/specs/2026-05-13-production-cockpit-design.md` (this doc)

**Modified files:**
- `process.py` — add `load_dotenv()` at top, add `sink_to_supabase()` function, one call site after `save_binder()`
- `requirements.txt` — add `supabase`, `python-dotenv`
- `.gitignore` — add `.env`, `production-cockpit/.env.local`, `production-cockpit/node_modules/`, `production-cockpit/.next/`

**Untouched (confirmed):**
- `weekly-prompt.md`, `generators/`, `monday-binder/`, dashboard (`localhost:8765` Flask app), `config/`, all other `binders/`-adjacent code paths.
