import { createClient } from "@supabase/supabase-js";

export function supabaseServer() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in env");
  }
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: {
      // Next.js patches global fetch and caches GET responses in its on-disk
      // Data Cache by DEFAULT — even on `force-dynamic` routes (force-dynamic
      // controls route rendering, not individual fetch caching). That made the
      // cockpit serve stale Supabase reads: e.g. a job summary kept rendering
      // after its row was deleted, surviving even a dev-server restart because
      // the cache lives in .next/cache/fetch-cache. Forcing `no-store` makes
      // every server-side read hit the database, which is what a live meeting
      // tool needs. Applies to all pages + API routes via supabaseServer().
      fetch: (input: RequestInfo | URL, init?: RequestInit) =>
        fetch(input, { ...init, cache: "no-store" }),
    },
  });
}
