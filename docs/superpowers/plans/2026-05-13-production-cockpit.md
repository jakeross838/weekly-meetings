# Production Cockpit v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mobile production cockpit (Next.js 14) that mirrors `binders/*.json` action items into Supabase and lets Jake tap-to-complete from his phone. Existing pipeline untouched except for one additive sink in `process.py`.

**Architecture:** Two-write `process.py` (binders/*.json stays source of truth; Supabase is a mirror, failure-tolerant). Separate Next.js subfolder (`production-cockpit/`) deployed to Vercel later. Single shared Supabase project, no auth in v1.

**Tech Stack:** Python 3 + `supabase` + `python-dotenv` (sink). Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui + `@supabase/supabase-js` (cockpit). Supabase Postgres.

**Spec:** `docs/superpowers/specs/2026-05-13-production-cockpit-design.md`

---

## Environment notes (read before starting)

- **Git commits may fail** with "dubious ownership" because the repo is on a network share owned by Windows user `RBC/Jake` while the executing user is `RBC/Greg`. If a commit step fails with that error, skip it — the work continues, and Jake can commit later from his account or run `git config --global --add safe.directory '%(prefix)///RB2019/Company/Claude Projects/weekly-meetings'`.
- **Existing pipeline has zero test infrastructure.** No `tests/` folder, no pytest config. Rather than introduce one for a single sink function, the plan uses an executable smoke-test script under `scripts/` (matches existing pattern) and end-to-end verification.
- **Supabase MCP must be authenticated before Task 1.** If `mcp__plugin_supabase_supabase__list_organizations` is not in the deferred tools list, run `mcp__plugin_supabase_supabase__authenticate` first, give Jake the URL, and complete the flow with the callback URL.

---

## File structure

**Modified:**
- `process.py` — add `load_dotenv()` import block at top, add `_supabase_client()` lazy factory, add `_pm_slug()` helper, add `sink_to_supabase()` function, add one call site after `save_binder()`
- `requirements.txt` — add `supabase>=2.0`, `python-dotenv>=1.0`
- `.gitignore` — add `.env`, `production-cockpit/node_modules/`, `production-cockpit/.next/`, `production-cockpit/.env.local`, `production-cockpit/.env*.local`

**Created:**
- `.env` (root, gitignored) — `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
- `scripts/test_supabase_sink.py` — standalone end-to-end smoke test
- `production-cockpit/` — full Next.js 14 scaffold
  - `app/layout.tsx`, `app/page.tsx`, `app/globals.css`
  - `app/api/complete/route.ts`
  - `lib/supabase.ts` — server client factory
  - `lib/types.ts` — Todo + PM type definitions
  - `lib/week.ts` — ISO Monday helper
  - `components/header.tsx`
  - `components/stats-bar.tsx`
  - `components/filters.tsx`
  - `components/pm-section.tsx`
  - `components/todo-row.tsx`
  - shadcn-generated: `components/ui/{card,button,select,switch,collapsible}.tsx`
  - `package.json`, `tsconfig.json`, `next.config.js`, `tailwind.config.ts`, `postcss.config.js`, `components.json`
  - `.env.local` (gitignored)

---

## Task 1: Supabase project + schema + seed

**Files:** none on disk — all operations via Supabase MCP.

- [ ] **Step 1: List orgs to confirm auth + pick destination**

Run: `mcp__plugin_supabase_supabase__list_organizations`
Expected: returns at least one organization with an `id`. Note the ID — call it `<ORG_ID>` below.

- [ ] **Step 2: Create the project**

Run: `mcp__plugin_supabase_supabase__create_project` with:
```json
{
  "name": "ross-built-cockpit",
  "organization_id": "<ORG_ID>",
  "region": "us-east-1"
}
```
Expected: returns project `id`, `database` connection info, `service_role_key`, and `anon_key`. Note `id` (call it `<PROJECT_ID>`), the `SUPABASE_URL` (`https://<PROJECT_ID>.supabase.co`), and the `service_role_key` (call it `<SERVICE_KEY>`).

If the create call returns a "project provisioning" state, poll `mcp__plugin_supabase_supabase__get_project` with the project id until `status: "ACTIVE_HEALTHY"`.

- [ ] **Step 3: Apply schema**

Run: `mcp__plugin_supabase_supabase__apply_migration` with `project_id=<PROJECT_ID>`, `name="init_schema"`, and `query`:
```sql
create table pms (
  id text primary key,
  full_name text not null,
  active boolean default true
);

create table todos (
  id text primary key,
  pm_id text references pms(id),
  job text not null,
  title text not null,
  due_date date,
  priority text,
  status text default 'OPEN',
  type text,
  category text,
  created_at timestamptz default now(),
  completed_at timestamptz,
  source_transcript text,
  source_excerpt text
);
create index todos_pm_status_due_idx on todos (pm_id, status, due_date);
```
Expected: success response.

- [ ] **Step 4: Seed PMs**

Run: `mcp__plugin_supabase_supabase__execute_sql` with:
```sql
insert into pms (id, full_name, active) values
  ('martin', 'Martin Mannix', true),
  ('jason',  'Jason Szykulski', true),
  ('lee',    'Lee Worthy', true),
  ('bob',    'Bob Mozine', true),
  ('nelson', 'Nelson Belanger', true);
```
Expected: 5 rows inserted.

- [ ] **Step 5: Verify**

Run: `mcp__plugin_supabase_supabase__execute_sql` with:
```sql
select id, full_name from pms order by id;
select count(*) as todo_count from todos;
```
Expected: 5 PM rows; `todo_count = 0`.

- [ ] **Step 6: Capture credentials**

Note: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are needed for Tasks 2 + 5. Do **not** commit them. Hold them in working memory for the .env writes.

---

## Task 2: .env + .gitignore + Python deps

**Files:**
- Create: `.env` (root)
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Append to .gitignore**

Check the current `.gitignore`. Confirm `.env` is NOT already covered. If it isn't, append:
```
# Production Cockpit
.env
production-cockpit/node_modules/
production-cockpit/.next/
production-cockpit/.env.local
production-cockpit/.env*.local
```

Use the Edit tool with the existing `.gitignore`. If `.env` is already gitignored (it should be — check first), only add the production-cockpit lines.

- [ ] **Step 2: Write `.env`**

Path: `P:\Claude Projects\weekly-meetings\.env`

Content (substituting the values captured in Task 1 Step 6):
```
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<SERVICE_KEY>
```

- [ ] **Step 3: Update requirements.txt**

Use Edit tool. Add at end of `requirements.txt`:
```
supabase>=2.0
python-dotenv>=1.0
```

- [ ] **Step 4: Install deps**

Run: `pip install supabase python-dotenv`
Expected: both packages install. If pip is not on PATH, use `python -m pip install supabase python-dotenv`.

- [ ] **Step 5: Verify imports work**

Run: `python -c "import supabase, dotenv; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit** (skip if git ownership error)

Run:
```
git add requirements.txt .gitignore
git commit -m "deps: add supabase + python-dotenv for cockpit sink"
```

---

## Task 3: Add sink helpers to process.py

**Files:**
- Modify: `process.py` (top of file — imports; new functions near the binder utilities)

This task adds the helpers without wiring them into the run path yet. Wiring happens in Task 4. Splitting lets us run a smoke test on the helpers in isolation.

- [ ] **Step 1: Add load_dotenv + supabase import block**

Use Edit. At the top of `process.py`, after the existing `import hashlib` line (line 17), add:

Old:
```python
import hashlib
import io
import os
import sys
import json
import re
import time
from datetime import datetime, date
from pathlib import Path
```

New:
```python
import hashlib
import io
import os
import sys
import json
import re
import time
from datetime import datetime, date
from pathlib import Path

# Load environment from .env (Supabase credentials, etc.) before anything
# else reads os.environ. python-dotenv does NOT override existing env vars,
# so setx-set ANTHROPIC_API_KEY still wins — .env is a backstop.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env loading is optional; existing setx flow keeps working
```

- [ ] **Step 2: Add `_pm_slug` and `_supabase_client` helpers**

Use Edit. After the `binder_path()` function (around line 202), insert:

```python
def _pm_slug(pm_name: str) -> str:
    """First-name lowercase. 'Martin Mannix' -> 'martin'."""
    return pm_name.split()[0].lower() if pm_name else ""


_SUPABASE_CLIENT = None


def _supabase_client():
    """Lazy supabase client. Returns None when env is unset so the
    sink is a no-op in dev environments without Supabase configured."""
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    _SUPABASE_CLIENT = create_client(url, key)
    return _SUPABASE_CLIENT
```

- [ ] **Step 3: Add `_item_to_supabase_row` mapping helper**

Use Edit. Immediately after `_supabase_client()`, insert:

```python
def _item_to_supabase_row(item: dict, pm_name: str, transcript_filename: str) -> dict | None:
    """Map a binder item dict to a todos-table row. Returns None for items
    that should be skipped (DISMISSED)."""
    status = (item.get("status") or "").upper()
    if status == "DISMISSED":
        return None

    def _date_or_none(s):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
        except Exception:
            return None

    def _datetime_or_none(s):
        d = _date_or_none(s)
        return f"{d}T00:00:00Z" if d else None

    completed_at = None
    if status == "COMPLETE":
        completed_at = _datetime_or_none(item.get("close_date") or item.get("closed_date"))

    return {
        "id": item.get("id"),
        "pm_id": _pm_slug(pm_name),
        "job": item.get("job") or "",
        "title": item.get("action") or "",
        "due_date": _date_or_none(item.get("due")),
        "priority": item.get("priority"),
        "status": status,
        "type": item.get("type"),
        "category": item.get("category"),
        "created_at": _datetime_or_none(item.get("opened")),
        "completed_at": completed_at,
        "source_transcript": transcript_filename,
        "source_excerpt": item.get("update"),
    }
```

- [ ] **Step 4: Add the `sink_to_supabase` function**

Use Edit. Immediately after `_item_to_supabase_row`, insert:

```python
def sink_to_supabase(pm_name: str, binder: dict, transcript_filename: str, logger) -> int:
    """Upsert each binder item into Supabase todos. Failures log but never raise.
    Returns count of rows attempted (skipped DISMISSED items not counted)."""
    client = _supabase_client()
    if client is None:
        logger.info("Supabase: client unavailable (missing env or import). Skipping sink.")
        return 0
    rows = []
    for item in binder.get("items", []) or []:
        row = _item_to_supabase_row(item, pm_name, transcript_filename)
        if row is None:
            continue
        if not row.get("id"):
            continue  # never upsert without a primary key
        rows.append(row)
    if not rows:
        logger.info(f"Supabase: no rows to upsert for {pm_name}.")
        return 0
    try:
        client.table("todos").upsert(rows, on_conflict="id").execute()
        logger.info(f"Supabase: upserted {len(rows)} rows for {pm_name}.")
        return len(rows)
    except Exception as e:
        logger.error(f"Supabase upsert failed for {pm_name}: {type(e).__name__}: {e}")
        return 0
```

- [ ] **Step 5: Syntax check**

Run: `python -c "import ast; ast.parse(open(r'P:\Claude Projects\weekly-meetings\process.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit** (skip if git ownership error)

Run:
```
git add process.py
git commit -m "feat(process): add Supabase sink helpers (no wiring yet)"
```

---

## Task 4: Wire `sink_to_supabase` into `process_transcript`

**Files:**
- Modify: `process.py` (one call site inside `process_transcript`)

- [ ] **Step 1: Locate the call site**

The call should land **after** `save_binder(pm_name, new_binder, logger)` (line 825 in current file) and **before** `archive_transcript(transcript_file)` (line 827), so the original transcript filename is still available.

- [ ] **Step 2: Insert the call**

Use Edit. Find:
```python
    save_binder(pm_name, new_binder, logger)

    archived = archive_transcript(transcript_file)
    logger.info(f"Moved transcript → processed/{archived.name}")
```

Replace with:
```python
    save_binder(pm_name, new_binder, logger)

    # Additive Supabase sink — failure-tolerant, never breaks the run.
    # binder JSON above remains the source of truth.
    sink_to_supabase(pm_name, new_binder, transcript_file.name, logger)

    archived = archive_transcript(transcript_file)
    logger.info(f"Moved transcript → processed/{archived.name}")
```

- [ ] **Step 3: Syntax check**

Run: `python -c "import ast; ast.parse(open(r'P:\Claude Projects\weekly-meetings\process.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit** (skip if git ownership error)

Run:
```
git add process.py
git commit -m "feat(process): wire Supabase sink into process_transcript"
```

---

## Task 5: Smoke-test the sink end-to-end

**Files:**
- Create: `scripts/test_supabase_sink.py`

- [ ] **Step 1: Write the smoke test**

Path: `P:\Claude Projects\weekly-meetings\scripts\test_supabase_sink.py`

Content:
```python
"""End-to-end smoke test for the Supabase sink.

Loads Martin_Mannix.json, runs sink_to_supabase against the real Supabase
project, then queries back to verify rowcount matches non-DISMISSED items.

Run: python scripts/test_supabase_sink.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from process import sink_to_supabase, _supabase_client, _pm_slug


class _ConsoleLogger:
    def info(self, msg): print(f"[info] {msg}")
    def error(self, msg): print(f"[error] {msg}", file=sys.stderr)


def main():
    logger = _ConsoleLogger()
    pm_name = "Martin Mannix"
    binder_path = ROOT / "binders" / "Martin_Mannix.json"
    if not binder_path.exists():
        print(f"FAIL: missing {binder_path}")
        sys.exit(1)
    binder = json.loads(binder_path.read_text(encoding="utf-8"))
    items = binder.get("items", [])
    non_dismissed = [i for i in items if (i.get("status") or "").upper() != "DISMISSED"]
    print(f"Loaded {len(items)} items ({len(non_dismissed)} non-DISMISSED)")

    n = sink_to_supabase(pm_name, binder, "smoke-test.txt", logger)
    if n != len(non_dismissed):
        print(f"FAIL: sink returned {n}, expected {len(non_dismissed)}")
        sys.exit(1)

    client = _supabase_client()
    if client is None:
        print("FAIL: supabase client unavailable; check .env")
        sys.exit(1)
    resp = client.table("todos").select("id", count="exact").eq("pm_id", _pm_slug(pm_name)).execute()
    actual = resp.count if hasattr(resp, "count") else len(resp.data or [])
    if actual != len(non_dismissed):
        print(f"FAIL: queried {actual} rows, expected {len(non_dismissed)}")
        sys.exit(1)
    print(f"PASS: {actual} rows for {pm_name} in Supabase")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the smoke test**

Run: `python scripts/test_supabase_sink.py`
Expected: prints `PASS: N rows for Martin Mannix in Supabase` where N matches non-DISMISSED item count from the binder.

If FAIL: read the error, fix the underlying issue (likely env, field mapping, or row shape), and re-run.

- [ ] **Step 3: Verify via Supabase MCP**

Run: `mcp__plugin_supabase_supabase__execute_sql` with `project_id=<PROJECT_ID>` and:
```sql
select status, count(*) from todos where pm_id='martin' group by status order by status;
```
Expected: rows for each non-DISMISSED status (NOT_STARTED, IN_PROGRESS, BLOCKED, COMPLETE depending on Martin's current binder state).

- [ ] **Step 4: Verify pipeline still produces identical binders**

Run a no-op process.py invocation to confirm no regression:
```
python process.py
```
Expected: log says "No transcripts in inbox" — exits clean. (If transcripts are queued, this will process them and ALSO sink to Supabase. That's fine but means the test is not a pure no-op.)

- [ ] **Step 5: Commit** (skip if git ownership error)

Run:
```
git add scripts/test_supabase_sink.py
git commit -m "test: add Supabase sink smoke test"
```

---

## Task 6: Scaffold Next.js + Tailwind + shadcn

**Files:**
- Create: `production-cockpit/*` (full scaffold)

- [ ] **Step 1: Scaffold Next.js 14 with TS + Tailwind**

Run from project root:
```
npx --yes create-next-app@14 production-cockpit --typescript --tailwind --app --no-src-dir --import-alias "@/*" --eslint --use-npm
```
Expected: scaffold completes; `production-cockpit/package.json` exists.

- [ ] **Step 2: Install runtime deps**

Run:
```
cd production-cockpit && npm install @supabase/supabase-js lucide-react
```
Expected: installs succeed; `package.json` shows both.

- [ ] **Step 3: Init shadcn**

Run from `production-cockpit/`:
```
npx --yes shadcn@latest init -d
```
The `-d` (defaults) flag answers prompts non-interactively: New York style, Slate base color, CSS variables yes, default paths. Creates `components.json`, sets up `lib/utils.ts`, modifies `tailwind.config.ts` + `globals.css`.

Expected: prints "Success! Project initialization completed."

- [ ] **Step 4: Add required shadcn components**

Run from `production-cockpit/`:
```
npx --yes shadcn@latest add card button select switch collapsible
```
Expected: 5 component files appear under `components/ui/`.

- [ ] **Step 5: Verify scaffold renders**

Run:
```
cd production-cockpit && npm run dev
```
In a separate shell or browser, open `http://localhost:3000/`. Expected: default Next.js 14 home page renders.
Stop the dev server (Ctrl-C).

- [ ] **Step 6: Commit** (skip if git ownership error)

Run from project root:
```
git add production-cockpit/ -- ':!production-cockpit/node_modules' ':!production-cockpit/.next'
git commit -m "scaffold: Next.js 14 + Tailwind + shadcn under production-cockpit/"
```

---

## Task 7: Supabase client + types + week helper

**Files:**
- Create: `production-cockpit/lib/supabase.ts`
- Create: `production-cockpit/lib/types.ts`
- Create: `production-cockpit/lib/week.ts`
- Create: `production-cockpit/.env.local`

- [ ] **Step 1: Write `.env.local`**

Path: `P:\Claude Projects\weekly-meetings\production-cockpit\.env.local`

Content (same values as root `.env`):
```
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<SERVICE_KEY>
```

- [ ] **Step 2: Write `lib/supabase.ts`**

Path: `production-cockpit/lib/supabase.ts`

```ts
import { createClient } from "@supabase/supabase-js";

export function supabaseServer() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in env");
  }
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
```

- [ ] **Step 3: Write `lib/types.ts`**

```ts
export type Priority = "URGENT" | "HIGH" | "NORMAL";
export type Status = "NOT_STARTED" | "IN_PROGRESS" | "BLOCKED" | "COMPLETE";

export interface Todo {
  id: string;
  pm_id: string;
  job: string;
  title: string;
  due_date: string | null;
  priority: Priority | null;
  status: Status;
  type: string | null;
  category: string | null;
  created_at: string;
  completed_at: string | null;
  source_transcript: string | null;
  source_excerpt: string | null;
}

export interface PM {
  id: string;
  full_name: string;
  active: boolean;
}

export const OPEN_STATUSES: Status[] = ["NOT_STARTED", "IN_PROGRESS", "BLOCKED"];
```

- [ ] **Step 4: Write `lib/week.ts`**

```ts
/** Returns the Monday 00:00 UTC for the current ISO week as ISO string. */
export function isoMondayUtc(now: Date = new Date()): string {
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  // getUTCDay: Sun=0..Sat=6. We want Mon=0..Sun=6.
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day);
  return d.toISOString();
}
```

- [ ] **Step 5: Smoke-test the helper**

Run from `production-cockpit/`:
```
node -e "const {isoMondayUtc} = require('./lib/week.ts')"
```
This will fail because Node can't import TS directly — that's fine, we'll verify in the page render. Skip if it fails.

Alternative: open `npx tsx -e "..."` if tsx is available; otherwise rely on UI render to validate.

- [ ] **Step 6: Commit** (skip if git ownership error)

```
git add production-cockpit/lib/
git commit -m "feat(cockpit): supabase client, types, week helper"
```

---

## Task 8: Page components

**Files:**
- Create: `production-cockpit/components/header.tsx`
- Create: `production-cockpit/components/stats-bar.tsx`
- Create: `production-cockpit/components/filters.tsx`
- Create: `production-cockpit/components/pm-section.tsx`
- Create: `production-cockpit/components/todo-row.tsx`

- [ ] **Step 1: Header**

Path: `production-cockpit/components/header.tsx`

```tsx
import { Settings } from "lucide-react";

export function Header() {
  return (
    <header className="flex items-center justify-between px-4 py-3 border-b">
      <h1 className="text-lg font-semibold">Production</h1>
      <button className="p-2 -mr-2 text-muted-foreground" aria-label="Settings">
        <Settings className="h-5 w-5" />
      </button>
    </header>
  );
}
```

- [ ] **Step 2: Stats bar**

Path: `production-cockpit/components/stats-bar.tsx`

```tsx
interface StatsBarProps {
  open: number;
  doneThisWeek: number;
  overdue: number;
}

export function StatsBar({ open, doneThisWeek, overdue }: StatsBarProps) {
  return (
    <div className="grid grid-cols-3 gap-px bg-border border-b">
      <Stat label="Open" value={open} />
      <Stat label="Done this week" value={doneThisWeek} />
      <Stat label="Overdue" value={overdue} tone={overdue > 0 ? "alert" : "default"} />
    </div>
  );
}

function Stat({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "alert" }) {
  return (
    <div className="flex flex-col items-center justify-center bg-background py-3">
      <span className={`text-2xl font-semibold ${tone === "alert" ? "text-red-600" : ""}`}>{value}</span>
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
    </div>
  );
}
```

- [ ] **Step 3: Filters**

Path: `production-cockpit/components/filters.tsx`

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useTransition } from "react";

interface FiltersProps {
  pms: { id: string; full_name: string }[];
  jobs: string[];
  selectedPm: string;
  selectedJob: string;
  view: "open" | "done";
}

export function Filters({ pms, jobs, selectedPm, selectedJob, view }: FiltersProps) {
  const router = useRouter();
  const params = useSearchParams();
  const [, startTransition] = useTransition();

  function update(key: string, value: string) {
    const p = new URLSearchParams(params.toString());
    if (!value || value === "all") p.delete(key);
    else p.set(key, value);
    if (key === "pm") p.delete("job"); // reset job when PM changes
    startTransition(() => router.push(`/?${p.toString()}`));
  }

  return (
    <div className="px-4 py-3 space-y-2 border-b">
      <div className="grid grid-cols-2 gap-2">
        <Select value={selectedPm || "all"} onValueChange={(v) => update("pm", v)}>
          <SelectTrigger><SelectValue placeholder="All PMs" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All PMs</SelectItem>
            {pms.map((p) => <SelectItem key={p.id} value={p.id}>{p.full_name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={selectedJob || "all"} onValueChange={(v) => update("job", v)}>
          <SelectTrigger><SelectValue placeholder="All jobs" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All jobs</SelectItem>
            {jobs.map((j) => <SelectItem key={j} value={j}>{j}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{view === "open" ? "Open" : "Done this week"}</span>
        <Switch
          checked={view === "done"}
          onCheckedChange={(c) => update("view", c ? "done" : "open")}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Todo row**

Path: `production-cockpit/components/todo-row.tsx`

```tsx
"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Todo } from "@/lib/types";

const PRIORITY_DOT: Record<string, string> = {
  URGENT: "bg-red-500",
  HIGH: "bg-amber-400",
  NORMAL: "bg-zinc-300",
};

export function TodoRow({ todo, allowComplete }: { todo: Todo; allowComplete: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [hidden, setHidden] = useState(false);

  async function complete() {
    if (!allowComplete || pending || hidden) return;
    setHidden(true); // optimistic
    try {
      const res = await fetch("/api/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: todo.id }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      start(() => router.refresh());
    } catch (err) {
      setHidden(false); // rollback
      alert(`Failed to mark done: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  if (hidden) return null;

  const dot = PRIORITY_DOT[todo.priority ?? "NORMAL"] ?? PRIORITY_DOT.NORMAL;
  return (
    <button
      onClick={complete}
      disabled={!allowComplete || pending}
      className="w-full flex items-start gap-3 px-4 py-3 text-left active:bg-muted transition-colors border-b last:border-b-0 disabled:opacity-60"
    >
      <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${dot}`} aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="text-sm leading-snug">{todo.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {todo.job}{todo.due_date ? ` · due ${todo.due_date}` : ""}
        </p>
      </div>
    </button>
  );
}
```

- [ ] **Step 5: PM section**

Path: `production-cockpit/components/pm-section.tsx`

```tsx
"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Todo } from "@/lib/types";
import { TodoRow } from "./todo-row";

interface PMSectionProps {
  pmFullName: string;
  todos: Todo[];
  allowComplete: boolean;
}

export function PMSection({ pmFullName, todos, allowComplete }: PMSectionProps) {
  const [open, setOpen] = useState(true);
  if (todos.length === 0) return null;
  const jobs = Array.from(new Set(todos.map((t) => t.job))).sort();
  const subtitle = jobs.length === 1 ? jobs[0] : `${jobs.length} jobs`;
  return (
    <section className="border-b">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-2 bg-muted/40 text-sm font-medium"
      >
        <span>{pmFullName} · {subtitle} · {todos.length} {allowComplete ? "open" : "done"}</span>
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? "" : "-rotate-90"}`} />
      </button>
      {open && (
        <div>
          {todos.map((t) => <TodoRow key={t.id} todo={t} allowComplete={allowComplete} />)}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 6: Commit** (skip if git ownership error)

```
git add production-cockpit/components/
git commit -m "feat(cockpit): page components — header, stats, filters, sections, rows"
```

---

## Task 9: Page + API route

**Files:**
- Modify: `production-cockpit/app/page.tsx`
- Modify: `production-cockpit/app/layout.tsx`
- Modify: `production-cockpit/app/globals.css`
- Create: `production-cockpit/app/api/complete/route.ts`

- [ ] **Step 1: Replace `app/page.tsx`**

Path: `production-cockpit/app/page.tsx`

```tsx
import { supabaseServer } from "@/lib/supabase";
import { Todo, PM, OPEN_STATUSES, Status } from "@/lib/types";
import { isoMondayUtc } from "@/lib/week";
import { Header } from "@/components/header";
import { StatsBar } from "@/components/stats-bar";
import { Filters } from "@/components/filters";
import { PMSection } from "@/components/pm-section";

interface SP { pm?: string; job?: string; view?: string }

const PRIORITY_RANK: Record<string, number> = { URGENT: 0, HIGH: 1, NORMAL: 2 };

export const dynamic = "force-dynamic";

export default async function Page({ searchParams }: { searchParams: SP }) {
  const supabase = supabaseServer();
  const selectedPm = searchParams.pm ?? "";
  const selectedJob = searchParams.job ?? "";
  const view = (searchParams.view === "done" ? "done" : "open") as "open" | "done";

  const monday = isoMondayUtc();
  const todayIso = new Date().toISOString().slice(0, 10);

  // Stats — always portfolio-wide (not PM-filtered) so Jake sees totals.
  const [openCountRes, doneCountRes, overdueCountRes, pmsRes, todosRes] = await Promise.all([
    supabase.from("todos").select("id", { count: "exact", head: true }).in("status", OPEN_STATUSES as Status[]),
    supabase.from("todos").select("id", { count: "exact", head: true }).eq("status", "COMPLETE").gte("completed_at", monday),
    supabase.from("todos").select("id", { count: "exact", head: true }).in("status", OPEN_STATUSES as Status[]).lt("due_date", todayIso),
    supabase.from("pms").select("id, full_name, active").eq("active", true).order("full_name"),
    buildTodoQuery(supabase, view, selectedPm, selectedJob),
  ]);

  const pms = (pmsRes.data ?? []) as PM[];
  const todos = (todosRes.data ?? []) as Todo[];

  // Job dropdown options for the currently selected PM (or all if no PM selected)
  const jobsForFilter = Array.from(new Set(
    (selectedPm
      ? todos.filter((t) => t.pm_id === selectedPm)
      : todos
    ).map((t) => t.job)
  )).sort();

  // Group by pm, sort URGENT-first then due ascending
  const byPm = new Map<string, Todo[]>();
  for (const t of todos) {
    if (!byPm.has(t.pm_id)) byPm.set(t.pm_id, []);
    byPm.get(t.pm_id)!.push(t);
  }
  for (const [, arr] of byPm) {
    arr.sort((a, b) => {
      const pr = (PRIORITY_RANK[a.priority ?? "NORMAL"] ?? 3) - (PRIORITY_RANK[b.priority ?? "NORMAL"] ?? 3);
      if (pr !== 0) return pr;
      const ad = a.due_date ?? "9999-12-31";
      const bd = b.due_date ?? "9999-12-31";
      return ad.localeCompare(bd);
    });
  }

  return (
    <main className="max-w-[480px] mx-auto min-h-screen bg-background">
      <Header />
      <StatsBar open={openCountRes.count ?? 0} doneThisWeek={doneCountRes.count ?? 0} overdue={overdueCountRes.count ?? 0} />
      <Filters pms={pms} jobs={jobsForFilter} selectedPm={selectedPm} selectedJob={selectedJob} view={view} />
      <div>
        {pms.map((pm) => {
          const items = byPm.get(pm.id) ?? [];
          return <PMSection key={pm.id} pmFullName={pm.full_name} todos={items} allowComplete={view === "open"} />;
        })}
        {todos.length === 0 && (
          <div className="px-4 py-12 text-center text-sm text-muted-foreground">
            Nothing here.
          </div>
        )}
      </div>
    </main>
  );
}

function buildTodoQuery(
  supabase: ReturnType<typeof supabaseServer>,
  view: "open" | "done",
  pm: string,
  job: string,
) {
  let q = supabase.from("todos").select("*");
  if (view === "open") {
    q = q.in("status", OPEN_STATUSES as Status[]);
  } else {
    q = q.eq("status", "COMPLETE").gte("completed_at", isoMondayUtc());
  }
  if (pm) q = q.eq("pm_id", pm);
  if (job) q = q.eq("job", job);
  return q.order("due_date", { ascending: true, nullsFirst: false });
}
```

- [ ] **Step 2: Update `app/layout.tsx`**

Open the file. Find the existing `<html lang="en">` and `<body>` block. Update the metadata + viewport for mobile:

```tsx
import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Production · Ross Built",
  description: "Production Director cockpit",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased bg-background text-foreground">{children}</body>
    </html>
  );
}
```

Replace whatever the scaffold generated. Keep the `globals.css` import.

- [ ] **Step 3: Write the API route**

Path: `production-cockpit/app/api/complete/route.ts`

```ts
import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  let body: { id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const id = body.id?.trim();
  if (!id) return NextResponse.json({ ok: false, error: "Missing id" }, { status: 400 });

  const supabase = supabaseServer();
  const { error } = await supabase
    .from("todos")
    .update({ status: "COMPLETE", completed_at: new Date().toISOString() })
    .eq("id", id);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 4: Smoke-test the build**

Run from `production-cockpit/`:
```
npm run build
```
Expected: build completes with no type errors. If a type error shows up, fix it inline (likely a Supabase generic type or a casing issue).

- [ ] **Step 5: Run dev server and click through**

Run: `cd production-cockpit && npm run dev`
Open `http://localhost:3000/` (use browser dev tools to switch to mobile viewport 375x667 or similar).

Verify:
- Header shows "Production"
- Stats bar shows 3 numbers (totals across all PMs)
- PM dropdown lists all 5 PMs; selecting one filters
- Job dropdown populates from todos visible
- Switch flips between Open/Done view
- PM sections render with todos sorted URGENT-first
- Each row shows priority dot, title, job, due date
- Tapping a row makes it disappear; refresh → it stays gone, appears in Done view

Stop dev server.

- [ ] **Step 6: Commit** (skip if git ownership error)

```
git add production-cockpit/app/
git commit -m "feat(cockpit): page + layout + complete API route"
```

---

## Task 10: Final verification

**Files:** none — verification only.

- [ ] **Step 1: Confirm `binders/*.json` is byte-identical when no new transcripts run**

Capture a pre-state hash:
```
python -c "import hashlib; print(hashlib.sha256(open(r'P:\Claude Projects\weekly-meetings\binders\Martin_Mannix.json','rb').read()).hexdigest())"
```

Run process.py with empty inbox:
```
python process.py
```
Expected: "No transcripts in inbox" — no binder changes.

Capture post-state hash, compare.

Expected: hashes equal.

- [ ] **Step 2: Confirm Supabase row counts match binders**

Run via Supabase MCP:
```sql
select pm_id, count(*) from todos group by pm_id order by pm_id;
```

In Python locally:
```python
import json, glob
for p in sorted(glob.glob(r"P:\Claude Projects\weekly-meetings\binders\*.json")):
    b = json.load(open(p, encoding="utf-8"))
    pm = b["meta"]["pm"]
    items = b.get("items", [])
    nd = [i for i in items if (i.get("status") or "").upper() != "DISMISSED"]
    print(f"{pm}: {len(items)} total, {len(nd)} non-DISMISSED")
```

Expected: each PM's Supabase rowcount equals their non-DISMISSED item count (after the Task 5 smoke test has populated Martin; other PMs will populate the next time a transcript runs for them, OR you can run the smoke test once per PM manually).

- [ ] **Step 3: Sync remaining PMs (optional, one-shot)**

To pre-populate Supabase with all 5 PMs' current binders without waiting for new transcripts, run a small one-off script. Add at the bottom of `scripts/test_supabase_sink.py`:

Skip if you'd rather wait for organic syncs.

- [ ] **Step 4: Final report**

Summarize:
- Schema applied? ✓ (Task 1 Step 5)
- process.py edit minimal? Helpers + one call site after `save_binder`. Existing behavior preserved.
- Mobile screen working? Open/Done filter, PM filter, Job filter, tap-to-complete all verified in Task 9 Step 5.
- Trade-offs (flag back to Jake): list from `docs/superpowers/specs/2026-05-13-production-cockpit-design.md` § Open trade-offs.

---

## Self-review checklist (run before handoff)

1. **Spec coverage** — every section in the design doc maps to a task:
   - Schema → Task 1
   - process.py sink → Tasks 3-5
   - Next.js scaffold → Task 6
   - Supabase client/types → Task 7
   - UI components → Task 8
   - Page + API → Task 9
   - Verification → Task 10
2. **Placeholder scan** — no TBD/TODO in steps; every code block is complete.
3. **Type consistency** — `Todo.status` type matches `OPEN_STATUSES` array elements; `PRIORITY_RANK` keys match `Priority` union.
4. **Commands exact** — npx, npm, python, mcp invocations all have explicit args.
