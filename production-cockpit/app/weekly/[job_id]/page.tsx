// /weekly/[job_id] — per-job Weekly Review.
//
// Read-only INTEL TIMELINE (Phase 1: captured emails/logs/POs for the job) plus
// the interactive review surface (Phase 3): generate a DRAFT homeowner report,
// edit it, approve it, propose to-dos, and leave feedback. Visibility is
// enforced here on render (API routes are trusted-internal, per the app's model).

import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { supabaseServer } from "@/lib/supabase";
import { Header } from "@/components/header";
import { currentUser, canSeeJobByPm } from "@/lib/auth";
import { currentWeekStart, normalizeBody, type JobIntel, type WeeklyReport } from "@/lib/weekly";
import { WeeklyReviewClient } from "./weekly-client";

export const dynamic = "force-dynamic";

const SOURCE_STYLE: Record<string, string> = {
  email: "text-indigo-700 bg-indigo-50 border-indigo-200",
  daily_log: "text-sky-700 bg-sky-50 border-sky-200",
  po: "text-purple-700 bg-purple-50 border-purple-200",
  manual: "text-stone-700 bg-stone-100 border-stone-200",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getUTCMonth() + 1}/${String(d.getUTCDate()).padStart(2, "0")}/${d.getUTCFullYear()}`;
}

export default async function WeeklyJobPage({ params }: { params: { job_id: string } }) {
  const jobId = params.job_id;
  const supabase = supabaseServer();

  const jobRes = await supabase
    .from("jobs")
    .select("id, name, address, pm_id")
    .eq("id", jobId)
    .maybeSingle();
  const job = jobRes.data as { id: string; name: string; address: string | null; pm_id: string | null } | null;
  if (!job) notFound();

  const user = await currentUser();
  if (!canSeeJobByPm(user, job.pm_id)) redirect("/weekly");

  const weekStart = currentWeekStart();
  const weekStartTs = new Date(weekStart + "T00:00:00Z").toISOString();

  const [intelRes, reportRes, feedbackRes] = await Promise.all([
    supabase
      .from("job_intel")
      .select("*")
      .eq("job_id", jobId)
      .eq("hidden", false)
      .order("sent_at", { ascending: false, nullsFirst: false })
      .order("created_at", { ascending: false })
      .limit(60),
    supabase
      .from("weekly_reports")
      .select("*")
      .eq("job_id", jobId)
      .eq("week_start", weekStart)
      .maybeSingle(),
    supabase
      .from("report_feedback")
      .select("id, feedback, created_by, created_at")
      .eq("job_id", jobId)
      .order("created_at", { ascending: false })
      .limit(12),
  ]);

  const intel = ((intelRes.data ?? []) as JobIntel[]).map((r) => r);
  const rawReport = reportRes.data as (WeeklyReport & { body: unknown; edited_body: unknown }) | null;
  const report: WeeklyReport | null = rawReport
    ? {
        ...rawReport,
        body: normalizeBody(rawReport.body),
        edited_body: rawReport.edited_body ? normalizeBody(rawReport.edited_body) : null,
      }
    : null;
  const feedback = (feedbackRes.data ?? []) as Array<{
    id: string;
    feedback: string;
    created_by: string | null;
    created_at: string;
  }>;

  const newThisWeek = intel.filter((i) => i.created_at >= weekStartTs).length;

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />
      <div className="px-5 pt-8">
        <Link href="/weekly" className="text-ink-3 text-xs hover:text-ink transition-colors">
          ← Weekly Review
        </Link>
        <h1 className="mt-2 font-head text-[28px] leading-none tracking-tight text-foreground">
          {job.name}
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          {job.address ? job.address + " · " : ""}week of {weekStart} ·{" "}
          {newThisWeek} new signal{newThisWeek === 1 ? "" : "s"}
        </p>
        <p className="mt-1">
          <Link href={`/v2/job/${job.id}`} className="text-accent text-xs hover:underline">
            open full job cockpit →
          </Link>
        </p>
      </div>

      {/* Interactive review: draft homeowner report + to-dos + feedback */}
      <WeeklyReviewClient
        jobId={job.id}
        jobName={job.name}
        weekStart={weekStart}
        initialReport={report}
        initialFeedback={feedback}
      />

      {/* Read-only intel timeline (Phase 1) */}
      <section className="px-5 pt-10">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Intel timeline
        </h2>
        {intel.length === 0 ? (
          <p className="mt-3 text-sm text-ink-3">
            No captured intel yet. Emails land here once the capture service runs;
            logs and POs appear as they&apos;re ingested.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {intel.map((i) => (
              <li key={i.id} className="border border-rule bg-paper p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={
                      "px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-[0.12em] border " +
                      (SOURCE_STYLE[i.source] ?? SOURCE_STYLE.manual)
                    }
                  >
                    {i.source}
                  </span>
                  {i.intel_type && (
                    <span className="text-[10px] font-mono uppercase tracking-[0.12em] text-ink-3">
                      {i.intel_type}
                    </span>
                  )}
                  <span className="ml-auto text-[10px] font-mono text-ink-3">
                    {fmtDate(i.sent_at ?? i.created_at)}
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-foreground leading-snug">{i.summary}</p>
                {i.detail && <p className="mt-1 text-xs text-ink-2 leading-snug">{i.detail}</p>}
                {i.action_needed && (
                  <p className="mt-1.5 text-xs text-urgent leading-snug">
                    ▸ {i.action_needed}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
