// / — portfolio home (simplified).
// One row per job, sorted by past-due count. Click → /v2/job/[id].
// Single column, mobile-first, no decoration.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";

export const dynamic = "force-dynamic";

type JobRow = {
  id: string;
  name: string;
  address: string | null;
  pm_id: string | null;
};

export default async function Page({
  searchParams,
}: {
  searchParams: { pm?: string };
}) {
  const supabase = supabaseServer();
  const pmFilter = searchParams.pm ?? "";
  const todayIso = new Date().toISOString().slice(0, 10);

  const [jobsRes, openTodosRes, pmsRes, assignRes, pendingRes] = await Promise.all([
    supabase.from("jobs").select("id, name, address, pm_id").order("name"),
    supabase
      .from("todos")
      .select("job, due_date")
      .in("status", OPEN_STATUSES as Status[]),
    supabase.from("pms").select("id, full_name"),
    supabase
      .from("job_pm_assignments")
      .select("job_id, pm_id")
      .is("ended_at", null),
    supabase
      .from("ingestion_events")
      .select("job_id")
      .in("review_state", ["pending", "in_review"]),
  ]);

  const jobs = (jobsRes.data ?? []) as JobRow[];
  const todos = (openTodosRes.data ?? []) as {
    job: string | null;
    due_date: string | null;
  }[];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];
  const pending = (pendingRes.data ?? []) as { job_id: string | null }[];

  const pmNameById = new Map(pms.map((p) => [p.id, p.full_name]));
  const activePmByJob = new Map<string, string>();
  for (const a of assignments) activePmByJob.set(a.job_id, a.pm_id);

  // Index counts by job (todos.job is text, matching the job.id slug)
  const openByJob = new Map<string, { open: number; past_due: number }>();
  for (const t of todos) {
    if (!t.job) continue;
    const rec = openByJob.get(t.job) ?? { open: 0, past_due: 0 };
    rec.open += 1;
    if (t.due_date && t.due_date < todayIso) rec.past_due += 1;
    openByJob.set(t.job, rec);
  }

  const pendingByJob = new Map<string, number>();
  for (const e of pending) {
    if (!e.job_id) continue;
    pendingByJob.set(e.job_id, (pendingByJob.get(e.job_id) ?? 0) + 1);
  }

  // todos.job stores the display name ("Krauss"), jobs.id is the slug ("krauss").
  // Match by job.name.
  const countsFor = (j: JobRow) =>
    openByJob.get(j.name) ?? { open: 0, past_due: 0 };

  // Which PM "owns" a job: active assignment wins, else the legacy jobs.pm_id.
  const pmForJob = (j: JobRow) => activePmByJob.get(j.id) ?? j.pm_id ?? null;

  // PMs that actually have at least one job — drives the filter pills so we
  // never render a pill that would land on an empty list.
  const pmIdsWithJobs = new Set<string>();
  for (const j of jobs) {
    const pid = pmForJob(j);
    if (pid) pmIdsWithJobs.add(pid);
  }
  const pmPills = Array.from(pmIdsWithJobs)
    .map((id) => ({ id, name: pmNameById.get(id) ?? id }))
    .sort((a, b) => a.name.localeCompare(b.name));

  // Sort: past-due desc → open desc → name
  const sorted = [...jobs].sort((a, b) => {
    const ao = countsFor(a);
    const bo = countsFor(b);
    if (bo.past_due !== ao.past_due) return bo.past_due - ao.past_due;
    if (bo.open !== ao.open) return bo.open - ao.open;
    return a.name.localeCompare(b.name);
  });

  const rows = pmFilter
    ? sorted.filter((j) => pmForJob(j) === pmFilter)
    : sorted;

  // Header counts reflect the visible (filtered) jobs.
  let totalOpen = 0;
  let totalPastDue = 0;
  for (const j of rows) {
    const c = countsFor(j);
    totalOpen += c.open;
    totalPastDue += c.past_due;
  }

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <header className="px-5 pt-8 pb-2">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Jobs
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          {totalOpen} open
          {totalPastDue > 0 && (
            <>
              {" · "}
              <span className="text-urgent">{totalPastDue} past due</span>
            </>
          )}
        </p>
      </header>

      {pmPills.length > 0 && (
        <div className="px-5 pt-2 pb-1">
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-5 px-5">
            <FilterPill href="/" active={!pmFilter} label="All PMs" />
            {pmPills.map((p) => (
              <FilterPill
                key={p.id}
                href={`/?pm=${encodeURIComponent(p.id)}`}
                active={pmFilter === p.id}
                label={p.name}
              />
            ))}
          </div>
        </div>
      )}

      <ul className="mt-4">
        {rows.length === 0 ? (
          <li className="px-5 py-16 text-center text-ink-3 text-sm">
            {pmFilter ? "No jobs for this PM." : "No jobs."}
          </li>
        ) : (
          rows.map((j) => {
            const counts = countsFor(j);
            const activePm = activePmByJob.get(j.id) ?? j.pm_id;
            const pmName = activePm ? pmNameById.get(activePm) : null;
            const pendingCount = pendingByJob.get(j.id) ?? 0;
            return (
              <li key={j.id}>
                <Link
                  href={`/v2/job/${j.id}`}
                  className="flex items-baseline gap-3 px-5 py-3.5 border-b border-rule hover:bg-sand-2/40 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-foreground text-sm leading-snug truncate">
                      {j.name}
                    </p>
                    {(pmName || j.address) && (
                      <p className="mt-0.5 text-ink-3 text-xs truncate">
                        {pmName ?? ""}
                        {pmName && j.address ? " · " : ""}
                        {j.address ?? ""}
                      </p>
                    )}
                  </div>
                  <div className="shrink-0 flex items-baseline gap-2 font-mono text-xs">
                    {pendingCount > 0 && (
                      <span
                        className="text-accent"
                        title={`${pendingCount} plaud transcript${pendingCount === 1 ? "" : "s"} to approve`}
                      >
                        {pendingCount}△
                      </span>
                    )}
                    {counts.past_due > 0 && (
                      <span className="text-urgent">
                        {counts.past_due} late
                      </span>
                    )}
                    {counts.open > 0 ? (
                      <span className="text-ink-2">{counts.open} open</span>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </div>
                </Link>
              </li>
            );
          })
        )}
      </ul>
    </main>
  );
}

function FilterPill({
  href,
  active,
  label,
}: {
  href: string;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={
        "shrink-0 px-3 py-1.5 text-xs font-medium border transition-colors " +
        (active
          ? "bg-ink text-paper border-ink"
          : "bg-transparent text-ink-2 border-rule hover:border-ink hover:text-ink")
      }
    >
      {label}
    </Link>
  );
}
