// /import — unified import surface.
// Two sections: Transcripts (Plaud .txt) + Daily logs (BT scraper .json).
// Each daily-log JSON contains a full week (or more) of entries, indexed by
// job. One drop = whole week.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { PM } from "@/lib/types";
import { Header } from "@/components/header";
import { ImportForm } from "@/components/import-form";
import { BtSyncButton } from "@/components/bt-sync-button";
import { BtPoSyncButton } from "@/components/bt-po-sync-button";
import { DailyLogUploadForm } from "../v2/daily-logs/upload/upload-form";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const supabase = supabaseServer();
  const [pmsRes, jobsRes, assignRes, subsRes] = await Promise.all([
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
  ]);
  const pms = (pmsRes.data ?? []) as PM[];
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];
  const subs = (subsRes.data ?? []) as { id: string; name: string }[];

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
        <ImportForm pms={pms} jobs={jobs} assignments={assignments} subs={subs} />
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
