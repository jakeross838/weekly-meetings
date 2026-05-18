// /admin/migrate — one-click migration runner.
// Used because PostgREST can't run raw SQL and the Supabase MCP OAuth
// keeps timing out. You paste the DB password ONCE, click Run, and the
// API route applies every pending migration in a transaction.
//
// The password is never persisted — it lives in form state, is sent to
// the API route over local HTTPS, and is dropped from memory once the
// route returns. Don't bookmark with the password in the URL.

import { Header } from "@/components/header";
import { MigrateForm } from "./migrate-form";

export const dynamic = "force-dynamic";

export default function MigratePage() {
  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Apply migrations
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          One-time setup. Pastes your Supabase DB password into a Postgres
          connection, runs all pending migrations in a transaction. Idempotent.
        </p>
        <p className="mt-3 text-xs text-ink-3">
          <strong className="text-ink-2">Where to find the password:</strong>{" "}
          Supabase Studio →{" "}
          <a
            href="https://supabase.com/dashboard/project/takewvlqgwpdbkvcwpvi/settings/database"
            target="_blank"
            rel="noreferrer"
            className="text-accent underline"
          >
            Project Settings → Database → Connection string
          </a>
          . The password is the part after{" "}
          <span className="font-mono">postgres:</span> and before{" "}
          <span className="font-mono">@</span>. If you don&apos;t have it, click
          &quot;Reset database password&quot; on that page (won&apos;t affect
          your service-role key).
        </p>
      </div>

      <div className="px-5 pt-6">
        <MigrateForm />
      </div>
    </main>
  );
}
