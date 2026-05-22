// /import — unified import surface.
// Two sections: Transcripts (Plaud .txt) + Daily logs (BT scraper .json).
// Each daily-log JSON contains a full week (or more) of entries, indexed by
// job. One drop = whole week.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { PM } from "@/lib/types";
import { Header } from "@/components/header";
import { TranscriptImportModal } from "@/components/transcript-import-modal";
import { BtSyncButton } from "@/components/bt-sync-button";
import { BtPoSyncButton } from "@/components/bt-po-sync-button";
import { DailyLogUploadForm } from "../v2/daily-logs/upload/upload-form";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const supabase = supabaseServer();
  const [pmsRes, jobsRes, assignRes, subsRes, txRes, dlRes, poRes] = await Promise.all([
    supabase
      .from("pms")
      .select("id, full_name, active")
      .eq("active", true)
      .order("full_name"),
    supabase.from("jobs").select("id, name").order("name"),
    supabase
      .from("job_pm_assignments")
      .select("job_id, pm_id")
      .is("ended_at", null),
    supabase.from("subs").select("id, name").eq("hidden", false).order("name"),
    // Transcript import history (derived from todos.source_transcript).
    supabase
      .from("todos")
      .select("source_transcript, created_at")
      .not("source_transcript", "is", null)
      .order("created_at", { ascending: false })
      .limit(1000),
    // Daily-log recency + total — enriched_at ≈ when last pulled/imported.
    supabase
      .from("daily_logs")
      .select("enriched_at", { count: "exact" })
      .order("enriched_at", { ascending: false, nullsFirst: false })
      .limit(1),
    // Purchase-order pull recency + total — scraped_at is set on every upload.
    supabase
      .from("purchase_orders")
      .select("scraped_at", { count: "exact" })
      .order("scraped_at", { ascending: false, nullsFirst: false })
      .limit(1),
  ]);
  const pms = (pmsRes.data ?? []) as PM[];
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];
  const subs = (subsRes.data ?? []) as { id: string; name: string }[];

  // Group todos by source file into a transcript-import history; the same set
  // (name + date) is handed to the form so it can flag a re-upload.
  const txTodos = (txRes.data ?? []) as {
    source_transcript: string | null;
    created_at: string;
  }[];
  const importMap = new Map<string, { name: string; date: string; count: number }>();
  for (const t of txTodos) {
    const name = t.source_transcript;
    if (!name || name === "cockpit-import") continue;
    const date = (t.created_at ?? "").slice(0, 10);
    const ex = importMap.get(name);
    if (ex) ex.count += 1;
    else importMap.set(name, { name, date, count: 1 });
  }
  const transcriptImports = Array.from(importMap.values()).sort((a, b) =>
    b.date.localeCompare(a.date)
  );
  const priorImports = transcriptImports.map((i) => ({ name: i.name, date: i.date }));
  const dlRows = (dlRes.data ?? []) as { enriched_at: string | null }[];
  const dailyCount = dlRes.count ?? null;
  const lastDailyImport = dlRows[0]?.enriched_at
    ? dlRows[0].enriched_at.slice(0, 10)
    : null;
  const poRows = (poRes.data ?? []) as { scraped_at: string | null }[];
  const poCount = poRes.count ?? null;
  const lastPoPull = poRows[0]?.scraped_at ? poRows[0].scraped_at.slice(0, 10) : null;

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Import
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Drop a Plaud meeting transcript or a Buildertrend daily-log JSON.
        </p>
      </div>

      {/* LAST PULLS & IMPORTS — recency at a glance */}
      <section className="px-5 pt-6">
        <div className="border border-rule p-4">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
            Last pulls &amp; imports
          </h2>
          <div className="space-y-2 text-sm">
            <HistoryRow label="Purchase orders" when={lastPoPull} count={poCount} unit="POs" />
            <HistoryRow label="Daily logs" when={lastDailyImport} count={dailyCount} unit="logs" />
            <HistoryRow
              label="Transcripts"
              when={transcriptImports[0]?.date ?? null}
              count={transcriptImports.length || null}
              unit="files"
            />
          </div>
        </div>
      </section>

      {/* TRANSCRIPT SECTION */}
      <section className="px-5 pt-10">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
          Transcript
        </h2>
        <p className="text-xs text-ink-3 mb-4">
          Plaud .txt — Claude extracts action items and writes them to the
          to-do table. PM, job, date, and meeting type auto-fill from the
          filename.{" "}
          <Link href="/v2/upload" className="text-accent hover:underline">
            v2 review pipeline →
          </Link>
        </p>
        <TranscriptImportModal
          pms={pms}
          jobs={jobs}
          assignments={assignments}
          subs={subs}
          priorImports={priorImports}
        />

        <p className="mt-4 font-mono text-[10px] tracking-[0.14em] uppercase text-ink-3">
          Naming · MM-DD &lt;Job&gt; &lt;Site|Office|Other&gt; Production
          Meeting-transcript.txt
        </p>
        {transcriptImports.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink py-2">
              Import history · {transcriptImports.length}
            </summary>
            <ul className="mt-1">
              {transcriptImports.slice(0, 20).map((imp) => (
                <li
                  key={imp.name}
                  className="flex items-baseline justify-between gap-3 border-b border-rule-soft py-1.5 last:border-b-0"
                >
                  <span className="min-w-0 flex-1 truncate text-ink-2 text-xs">
                    {imp.name}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] tabular-nums text-ink-3">
                    {imp.date} · {imp.count} item{imp.count === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {/* DAILY LOG SECTION */}
      <section className="px-5 pt-16">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
          Daily logs
        </h2>
        <p className="text-xs text-ink-3 mb-4">
          One-click button below logs into Buildertrend, downloads daily
          logs + photos, writes to Supabase, and runs Claude vision over
          the photos. Or drop a scraper JSON manually further down.
        </p>
        <div className="mb-6">
          <BtSyncButton />
        </div>
        <details className="mb-6">
          <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink py-2">
            Manual upload (advanced)
          </summary>
          <div className="mt-3">
            <p className="text-xs text-ink-3 mb-4">
              Drop a Buildertrend scraper JSON — full week for every job.
              Powers the no-show metric on{" "}
              <Link href="/subs" className="text-accent hover:underline">
                /subs
              </Link>
              .
            </p>
            <DailyLogUploadForm />
          </div>
        </details>
      </section>

      {/* PURCHASE ORDERS SECTION */}
      <section className="px-5 pt-16 pb-10">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
          Purchase orders
        </h2>
        <p className="text-xs text-ink-3 mb-4">
          One-click button logs into Buildertrend and refreshes every
          job&apos;s purchase orders (cost, paid, outstanding, status) into
          Supabase — they show on each job page. Fast grid pull by default;
          tick &ldquo;include line items&rdquo; (slower) for the full
          line-item breakdown.
        </p>
        <div className="mb-6">
          <BtPoSyncButton />
        </div>
      </section>
    </main>
  );
}

function HistoryRow({
  label,
  when,
  count,
  unit,
}: {
  label: string;
  when: string | null;
  count: number | null;
  unit: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-ink-2">{label}</span>
      <span className="font-mono text-xs tabular-nums text-ink-3">
        {when ? `last ${when}` : "never"}
        {count != null ? ` · ${count} ${unit}` : ""}
      </span>
    </div>
  );
}
