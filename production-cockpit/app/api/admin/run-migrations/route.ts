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

  const password = (body.db_password ?? "").trim();
  if (!password) {
    return NextResponse.json(
      { error: "db_password is required" },
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

  // Direct connection. If it fails (firewall / IPv6), we'll try the pooler.
  const direct = {
    host: `db.${projectRef}.supabase.co`,
    user: "postgres",
    password,
    database: "postgres",
    port: 5432,
    ssl: { rejectUnauthorized: false },
    connectionTimeoutMillis: 8000,
  };
  const poolerHosts = [
    `aws-0-us-east-1.pooler.supabase.com`,
    `aws-0-us-west-1.pooler.supabase.com`,
    `aws-0-us-east-2.pooler.supabase.com`,
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

  let client: Client | null = await tryConnect(direct);
  if (!client) {
    for (const host of poolerHosts) {
      client = await tryConnect({
        host,
        user: `postgres.${projectRef}`,
        password,
        database: "postgres",
        port: 6543,
        ssl: { rejectUnauthorized: false },
        connectionTimeoutMillis: 8000,
      });
      if (client) break;
    }
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

    // Verify the new objects exist
    const verifyRes = await client.query(`
      SELECT
        EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='daily_logs')        AS has_daily_logs,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='daily_logs' AND column_name='parent_group_activities') AS has_parent_group,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='items' AND column_name='category') AS has_items_category,
        EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='sub_specialties') AS has_sub_specialties,
        EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='sub_specialties' AND column_name='duration_days_manual_override') AS has_duration_override
    `);
    const verified = verifyRes.rows[0];
    return NextResponse.json({
      ok: true,
      message:
        "All migrations applied. Click 'Seed default specialties' on /subs next.",
      verified,
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
