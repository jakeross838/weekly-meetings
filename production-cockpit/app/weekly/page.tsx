// /weekly — the Weekly Review hub.
//
// One row per job the signed-in user can see. Each shows this week's new
// captured intel, past-due open work, and the homeowner-report status
// (none / draft / approved / sent). Sorted so the jobs that need attention
// (no report, or past-due work) rise to the top.
//
// All counts come from a handful of BATCHED queries aggregated in memory — no
// per-job round-trips (the old N+1 aggregation stays dead).

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Header } from "@/components/header";
import { currentUser, canSeeJobByPm } from "@/lib/auth";
import { businessToday } from "@/lib/today";
import { currentWeekStart } from "@/lib/weekly";

export const dynamic = "force-dynamic";

type JobRow = { id: string; name: string; address: string | null; pm_id: string | null; active: boolean | null };

const STATUS_STYLE: Record<string, string> = {
  none: "text-ink-3 border-rule",
  draft: "text-amber-700 border-amber-300 bg-amber-50",
  approved: "text-emerald-700 border-emerald-300 bg-emerald-50",
  sent: "text-sky-700 border-sky-300 bg-sky-50",
};

export default async function WeeklyHubPage() {
  const supabase = supabaseServer();
  const user = await currentUser();
  const weekStart = currentWeekStart();
  const weekStartTs = new Date(weekStart + "T00:00:00Z").toISOString();
  const todayIso = businessToday();

  const [jobsRes, intelRes, reportsRes, todosRes] = await Promise.all([
    supabase.from("jobs").select("id, name, address, pm_id, active").order("name"),
    supabase.from("job_intel").select("job_id").eq("hidden", false).gte("created_at", weekStartTs),
    supabase.from("weekly_reports").select("job_id, status").eq("week_start", weekStart),
    supabase
      .from("todos")
      .select("job, due_date, status")
      .in("status", ["NOT_STARTED", "IN_PROGRESS", "BLOCKED"]),
  ]);

  const allJobs = (jobsRes.data ?? []) as JobRow[];
  const jobs = allJobs.filter((j) => j.active !== false && canSeeJobByPm(user, j.pm_id));

  // Aggregate in memory.
  const intelByJob = new Map<string, number>();
  for (const r of (intelRes.data ?? []) as Array<{ job_id: string | null }>) {
    if (r.job_id) intelByJob.set(r.job_id, (intelByJob.get(r.job_id) ?? 0) + 1);
  }
  const reportByJob = new Map<string, string>();
  for (const r of (reportsRes.data ?? []) as Array<{ job_id: string; status: string }>) {
    reportByJob.set(r.job_id, r.status);
  }
  // todos key by job NAME; map name -> jobId.
  const nameToId = new Map(jobs.map((j) => [j.name, j.id]));
  const pastDueByJob = new Map<string, number>();
  for (const t of (todosRes.data ?? []) as Array<{ job: string; due_date: string | null }>) {
    if (!t.due_date || t.due_date >= todayIso) continue;
    const id = nameToId.get(t.job);
    if (id) pastDueByJob.set(id, (pastDueByJob.get(id) ?? 0) + 1);
  }

  const rows = jobs
    .map((j) => ({
      job: j,
      intel: intelByJob.get(j.id) ?? 0,
      pastDue: pastDueByJob.get(j.id) ?? 0,
      status: reportByJob.get(j.id) ?? "none",
    }))
    // Attention first: no report OR past-due work, then most new intel.
    .sort((a, b) => {
      const aNeeds = (a.status === "none" ? 1 : 0) + (a.pastDue > 0 ? 1 : 0);
      const bNeeds = (b.status === "none" ? 1 : 0) + (b.pastDue > 0 ? 1 : 0);
      if (aNeeds !== bNeeds) return bNeeds - aNeeds;
      return b.intel - a.intel;
    });

  const totalIntel = rows.reduce((n, r) => n + r.intel, 0);

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />
      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Weekly Review
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Week of {weekStart} · {rows.length} job{rows.length === 1 ? "" : "s"} ·{" "}
          {totalIntel} new signal{totalIntel === 1 ? "" : "s"} this week
        </p>
      </div>

      {rows.length === 0 ? (
        <div className="px-5 pt-12 text-center">
          <p className="text-ink-3 text-sm">No jobs to review.</p>
        </div>
      ) : (
        <ul className="px-5 pt-6 space-y-3">
          {rows.map(({ job, intel, pastDue, status }) => (
            <li key={job.id}>
              <Link
                href={`/weekly/${job.id}`}
                className="block p-4 lg:p-5 border border-rule hover:border-accent bg-paper transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-foreground text-base font-medium leading-tight">
                      {job.name}
                    </p>
                    {job.address && (
                      <p className="mt-0.5 text-ink-3 text-xs truncate">{job.address}</p>
                    )}
                    <p className="mt-2 text-ink-3 text-xs">
                      {intel} new signal{intel === 1 ? "" : "s"}
                      {pastDue > 0 && (
                        <span className="text-urgent"> · {pastDue} past due</span>
                      )}
                    </p>
                  </div>
                  <span
                    className={
                      "shrink-0 mt-1 px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.14em] border " +
                      (STATUS_STYLE[status] ?? STATUS_STYLE.none)
                    }
                  >
                    {status === "none" ? "no report" : status}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
