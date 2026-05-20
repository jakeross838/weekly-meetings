// POST /api/admin/run-migrations
// Body: { db_password: string }
//
// Connects directly to the Supabase Postgres pooler with the provided
// password and runs all four bundled migrations in one transaction.
// The password is never persisted — used only to build a single connection.
//
// This route exists because PostgREST blocks raw SQL execution and the
// Supabase MCP OAuth flow keeps timing out, leaving manual SQL paste as
// the only path. This wraps that paste in a button-click.

import { NextRequest, NextResponse } from "next/server";
import { Client } from "pg";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

const MIGRATIONS_SQL = `
CREATE TABLE IF NOT EXISTS public.daily_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_key text NOT NULL,
    log_id text,
    log_date date,
    crews_present jsonb NOT NULL DEFAULT '[]'::jsonb,
    absent_crews jsonb NOT NULL DEFAULT '[]'::jsonb,
    parent_group_activities jsonb NOT NULL DEFAULT '[]'::jsonb,
    daily_workforce int,
    weather_high int,
    weather_low int,
    activity text,
    notes text,
    enriched_at timestamptz,
    source text DEFAULT 'bt_scraper',
    inserted_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_key, log_id)
);

CREATE INDEX IF NOT EXISTS daily_logs_job_date_idx
    ON public.daily_logs (job_key, log_date);
CREATE INDEX IF NOT EXISTS daily_logs_absent_crews_idx
    ON public.daily_logs USING GIN (absent_crews);
CREATE INDEX IF NOT EXISTS daily_logs_crews_present_idx
    ON public.daily_logs USING GIN (crews_present);
CREATE INDEX IF NOT EXISTS daily_logs_parent_group_idx
    ON public.daily_logs USING GIN (parent_group_activities);

ALTER TABLE public.items ADD COLUMN IF NOT EXISTS category text;
CREATE INDEX IF NOT EXISTS items_category_idx
    ON public.items (category) WHERE category IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.sub_specialties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_id text NOT NULL REFERENCES public.subs(id) ON DELETE CASCADE,
    specialty text NOT NULL,
    source text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'auto')),
    duration_days_manual_override numeric,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sub_id, specialty)
);

CREATE INDEX IF NOT EXISTS sub_specialties_sub_idx
    ON public.sub_specialties (sub_id);
CREATE INDEX IF NOT EXISTS sub_specialties_specialty_idx
    ON public.sub_specialties (specialty);

-- F3,F6,F8: extend daily_logs to hold per-sub crew sizes, inspections,
-- and photo data + vision summaries. All jsonb so they tolerate scraper
-- shape evolution without further migrations.
ALTER TABLE public.daily_logs
    ADD COLUMN IF NOT EXISTS crew_counts      jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS inspections      jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS photo_urls       jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS photo_summary    jsonb,
    ADD COLUMN IF NOT EXISTS photo_summary_at timestamptz;

CREATE INDEX IF NOT EXISTS daily_logs_crew_counts_idx
    ON public.daily_logs USING GIN (crew_counts);
CREATE INDEX IF NOT EXISTS daily_logs_inspections_idx
    ON public.daily_logs USING GIN (inspections);

-- F5: Canonical schedule items so durations can be compared across subs
-- regardless of how Buildertrend's parent_group_activities tag spells it.
-- A small reference table; everything maps to it by name (lowercased).
CREATE TABLE IF NOT EXISTS public.schedule_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,         -- "Electrical Rough"
    trade text,                        -- "Electrical"
    sequence_order int,                -- rough sort order across a job
    typical_duration_days numeric,
    aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS schedule_items_trade_idx ON public.schedule_items (trade);

-- Optional link from sub_specialties to a canonical schedule_item. When set,
-- the sub profile renders the canonical name and rolls durations up under it.
ALTER TABLE public.sub_specialties
    ADD COLUMN IF NOT EXISTS schedule_item_id uuid REFERENCES public.schedule_items(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS sub_specialties_schedule_item_idx
    ON public.sub_specialties (schedule_item_id);

-- F7: Running checklist items per sub, two lenses (safety / schedule).
-- Free-text item, check-off state, optional note. Order via position int.
CREATE TABLE IF NOT EXISTS public.sub_checklist_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_id text NOT NULL REFERENCES public.subs(id) ON DELETE CASCADE,
    lens text NOT NULL CHECK (lens IN ('SAFETY', 'SCHEDULE')),
    item_text text NOT NULL,
    is_done boolean NOT NULL DEFAULT false,
    done_at timestamptz,
    done_by text,
    notes text,
    position int NOT NULL DEFAULT 0,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sub_checklist_items_sub_idx
    ON public.sub_checklist_items (sub_id);
CREATE INDEX IF NOT EXISTS sub_checklist_items_lens_idx
    ON public.sub_checklist_items (sub_id, lens, position);

-- Seed canonical schedule items if the table is empty. Idempotent: only
-- inserts rows whose name does not already exist. Captures the items Jake
-- specifically called out (T-pole, electrical rough) plus a starter sweep
-- across the trades referenced in v2-plan.md so the canonical layer is
-- useful on day one.
INSERT INTO public.schedule_items (name, trade, sequence_order, typical_duration_days)
SELECT * FROM (VALUES
    ('T-Pole'                  , 'Electrical' ,  5,  1.0),
    ('Underground Electrical'  , 'Electrical' , 15,  3.0),
    ('Electrical Rough'        , 'Electrical' , 50,  7.0),
    ('Electrical Trim'         , 'Electrical' , 90,  5.0),
    ('Electrical Punch'        , 'Electrical' ,100,  2.0),
    ('Underground Plumbing'    , 'Plumbing'   , 10,  3.0),
    ('Plumbing Rough'          , 'Plumbing'   , 48,  7.0),
    ('Plumbing Trim'           , 'Plumbing'   , 88,  4.0),
    ('Plumbing Punch'          , 'Plumbing'   ,100,  2.0),
    ('HVAC Rough'              , 'HVAC'       , 52, 10.0),
    ('HVAC Equipment Set'      , 'HVAC'       , 70,  3.0),
    ('HVAC Trim'               , 'HVAC'       , 92,  4.0),
    ('Excavation / Site Prep'  , 'Site Work'  ,  1,  5.0),
    ('Foundation'              , 'Concrete'   ,  8, 10.0),
    ('Slab'                    , 'Concrete'   , 25,  3.0),
    ('Wall Framing'            , 'Framing'    , 30, 14.0),
    ('Roof Framing'            , 'Framing'    , 38,  7.0),
    ('Sheathing / Dry-In'      , 'Framing'    , 42,  4.0),
    ('Roofing'                 , 'Roofing'    , 45,  5.0),
    ('Window Install'          , 'Windows'    , 47,  3.0),
    ('Stucco Wire/Lath'        , 'Stucco'     , 55,  3.0),
    ('Stucco Scratch'          , 'Stucco'     , 58,  3.0),
    ('Stucco Brown'            , 'Stucco'     , 62,  3.0),
    ('Stucco Finish'           , 'Stucco'     , 95,  4.0),
    ('Insulation'              , 'Insulation' , 60,  3.0),
    ('Drywall Hang'            , 'Drywall'    , 65,  4.0),
    ('Drywall Tape/Finish'     , 'Drywall'    , 68,  6.0),
    ('Drywall Texture'         , 'Drywall'    , 72,  2.0),
    ('Tile Set'                , 'Tile'       , 80,  5.0),
    ('Tile Grout'              , 'Tile'       , 83,  2.0),
    ('Cabinetry Install'       , 'Cabinetry'  , 85,  4.0),
    ('Wood Floor Install'      , 'Flooring'   , 87,  4.0),
    ('Paint Prime'             , 'Paint'      , 75,  3.0),
    ('Paint Body'              , 'Paint'      , 78,  4.0),
    ('Paint Trim'              , 'Paint'      , 89,  3.0),
    ('Interior Trim'           , 'Trim'       , 82,  6.0),
    ('Punch'                   , 'General'    , 99,  5.0)
) AS v(name, trade, sequence_order, typical_duration_days)
WHERE NOT EXISTS (
    SELECT 1 FROM public.schedule_items s WHERE s.name = v.name
);

-- Per-job summary documents — one row per refresh, latest wins. Powers
-- the big AI-generated summary panel on /v2/job/[id]. We keep history
-- (not just overwrite) so we can diff "what changed this week".
CREATE TABLE IF NOT EXISTS public.job_summaries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id text NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    generated_at timestamptz NOT NULL DEFAULT now(),
    summary jsonb NOT NULL,
    last_data_through date,       -- most recent daily_log.log_date considered
    log_count int NOT NULL DEFAULT 0,
    photo_count int NOT NULL DEFAULT 0,
    open_todo_count int NOT NULL DEFAULT 0,
    done_todo_count int NOT NULL DEFAULT 0,
    model text,                   -- e.g. claude-opus-4-7
    elapsed_ms int
);

CREATE INDEX IF NOT EXISTS job_summaries_job_recent_idx
    ON public.job_summaries (job_id, generated_at DESC);
`;

function projectRefFromUrl(url: string): string | null {
  // https://takewvlqgwpdbkvcwpvi.supabase.co → takewvlqgwpdbkvcwpvi
  const m = url.match(/^https?:\/\/([^.]+)\.supabase\.co/);
  return m ? m[1] : null;
}

export async function POST(req: NextRequest) {
  let body: { db_password?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const password = (body.db_password ?? process.env.SUPABASE_DB_PASSWORD ?? "").trim();
  if (!password) {
    return NextResponse.json(
      { error: "db_password is required (or set SUPABASE_DB_PASSWORD in the server env)" },
      { status: 400 }
    );
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  if (!supabaseUrl) {
    return NextResponse.json(
      { error: "SUPABASE_URL not set in env" },
      { status: 500 }
    );
  }
  const projectRef = projectRefFromUrl(supabaseUrl);
  if (!projectRef) {
    return NextResponse.json(
      { error: `could not parse project ref from ${supabaseUrl}` },
      { status: 500 }
    );
  }

  // Supabase Supavisor pooler. The region prefix MUST match the project's
  // region — takewvlqgwpdbkvcwpvi lives in us-west-2, so the working host is
  // aws-1-us-west-2.pooler.supabase.com (verified 2026-05-20; the old
  // us-east-1/us-west-1 guesses never connected, which is why this button
  // appeared to "succeed" but never applied anything). The legacy direct host
  // db.<ref>.supabase.co no longer resolves for newer projects, so it's only a
  // last-ditch fallback. Other regions kept in case the project ever moves.
  const poolerUser = `postgres.${projectRef}`;
  const candidates: Array<{ host: string; port: number; user: string }> = [
    { host: "aws-1-us-west-2.pooler.supabase.com", port: 5432, user: poolerUser },
    { host: "aws-1-us-west-2.pooler.supabase.com", port: 6543, user: poolerUser },
    { host: "aws-0-us-west-1.pooler.supabase.com", port: 6543, user: poolerUser },
    { host: "aws-0-us-east-1.pooler.supabase.com", port: 6543, user: poolerUser },
    { host: "aws-0-us-east-2.pooler.supabase.com", port: 6543, user: poolerUser },
    { host: `db.${projectRef}.supabase.co`, port: 5432, user: "postgres" },
  ];

  const errors: string[] = [];

  async function tryConnect(opts: Record<string, unknown>): Promise<Client | null> {
    const client = new Client(opts);
    try {
      await client.connect();
      return client;
    } catch (e) {
      errors.push(
        `${(opts.host as string) ?? "?"}:${opts.port}: ${(e as Error).message}`
      );
      try {
        await client.end();
      } catch {
        /* ignore */
      }
      return null;
    }
  }

  let client: Client | null = null;
  for (const c of candidates) {
    client = await tryConnect({
      host: c.host,
      user: c.user,
      password,
      database: "postgres",
      port: c.port,
      ssl: { rejectUnauthorized: false },
      connectionTimeoutMillis: 8000,
    });
    if (client) break;
  }

  if (!client) {
    return NextResponse.json(
      {
        error:
          "Could not connect to Postgres. Verify the DB password is correct (Supabase Studio → Settings → Database).",
        attempts: errors,
      },
      { status: 502 }
    );
  }

  try {
    await client.query("BEGIN");
    await client.query(MIGRATIONS_SQL);
    await client.query("COMMIT");

    // Verify the new objects exist. Extended after the 2026-05-18 round
    // so the response surfaces which piece is missing if a partial apply
    // ever happens.
    const verifyRes = await client.query(`
      SELECT
        EXISTS(SELECT 1 FROM information_schema.tables  WHERE table_schema='public' AND table_name ='daily_logs')                                                                AS has_daily_logs,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='daily_logs' AND column_name='parent_group_activities')                       AS has_parent_group,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='items'      AND column_name='category')                                      AS has_items_category,
        EXISTS(SELECT 1 FROM information_schema.tables  WHERE table_schema='public' AND table_name ='sub_specialties')                                                            AS has_sub_specialties,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='sub_specialties' AND column_name='duration_days_manual_override')             AS has_duration_override,
        -- F3 / F6 / F8 — new daily_logs columns
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='daily_logs' AND column_name='crew_counts')                                   AS has_crew_counts,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='daily_logs' AND column_name='inspections')                                   AS has_inspections,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='daily_logs' AND column_name='photo_urls')                                    AS has_photo_urls,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='daily_logs' AND column_name='photo_summary')                                 AS has_photo_summary,
        -- F5 — canonical schedule items
        EXISTS(SELECT 1 FROM information_schema.tables  WHERE table_schema='public' AND table_name ='schedule_items')                                                             AS has_schedule_items,
        (SELECT count(*) FROM public.schedule_items)                                                                                                                              AS schedule_items_rowcount,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name ='sub_specialties' AND column_name='schedule_item_id')                          AS has_sub_specialty_schedule_item,
        -- F7 — per-sub running checklist
        EXISTS(SELECT 1 FROM information_schema.tables  WHERE table_schema='public' AND table_name ='sub_checklist_items')                                                        AS has_sub_checklist,
        -- F9 — per-job AI summary
        EXISTS(SELECT 1 FROM information_schema.tables  WHERE table_schema='public' AND table_name ='job_summaries')                                                              AS has_job_summaries
    `);
    const verified = verifyRes.rows[0] as Record<string, unknown>;
    // Flag any boolean check that came back false so the operator sees
    // exactly what's still missing instead of having to diff manually.
    const missing = Object.entries(verified)
      .filter(([, v]) => v === false)
      .map(([k]) => k);
    return NextResponse.json({
      ok: missing.length === 0,
      message:
        missing.length === 0
          ? "All migrations applied. Click 'Seed default specialties' on /subs next."
          : `Migration ran but ${missing.length} object(s) missing — see 'missing' field.`,
      verified,
      missing,
    });
  } catch (e) {
    try {
      await client.query("ROLLBACK");
    } catch {
      /* ignore */
    }
    return NextResponse.json(
      { error: `migration failed: ${(e as Error).message}` },
      { status: 500 }
    );
  } finally {
    try {
      await client.end();
    } catch {
      /* ignore */
    }
  }
}
