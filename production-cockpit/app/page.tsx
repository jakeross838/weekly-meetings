// / — portfolio home (simplified).
// One row per job, sorted by past-due count. Click → /v2/job/[id].
// Single column, mobile-first, no decoration.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";
import { RequestAccessCard } from "@/components/request-access-card";
import { currentUser, canSeeJobByPm } from "@/lib/auth";
import { jobKeyMatchesName } from "@/lib/job-key";

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

  const [jobsRes, openTodosRes, openItemsRes, pmsRes, assignRes, pendingRes] =
    await Promise.all([
      supabase.from("jobs").select("id, name, address, pm_id").order("name"),
      supabase
        .from("todos")
        .select("job, due_date")
        .in("status", OPEN_STATUSES as Status[]),
      // v2 items count toward the portfolio totals exactly like they do on the
      // job page (which merges items + todos). Counting todos only here made the
      // dashboard under-report by every open item.
      supabase
        .from("items")
        .select("job_id, target_date")
        .in("status", ["open", "in_progress", "blocked"]),
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

  const user = await currentUser();
  const allJobs = (jobsRes.data ?? []) as JobRow[];
  const todos = (openTodosRes.data ?? []) as {
    job: string | null;
    due_date: string | null;
  }[];
  const items = (openItemsRes.data ?? []) as {
    job_id: string | null;
    target_date: string | null;
  }[];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];
  const pending = (pendingRes.data ?? []) as { job_id: string | null }[];

  // Visibility model: a PM sees jobs where the active assignment (or the
  // legacy jobs.pm_id) matches their own pmId. Admin sees everything. The
  // user_overlay.allowed_jobs column is no longer consulted — single source
  // of truth is `jobs.pm_id` so editing the assignment in /admin/jobs
  // immediately changes what that PM sees.
  const _activePmByJob = new Map<string, string>();
  for (const a of assignments) _activePmByJob.set(a.job_id, a.pm_id);
  const _pmForJob = (j: JobRow) => _activePmByJob.get(j.id) ?? j.pm_id ?? null;
  const jobs = allJobs.filter((j) => canSeeJobByPm(user, _pmForJob(j)));

  // Portfolio PO rollup — totals + averages across every job the user can
  // see. POs match jobs by job_key prefix (e.g. job.name = "Krauss" matches
  // job_key "Krauss-427 South Blvd of the Presidents"). Paginate past
  // Supabase's 1000-row cap so all POs are counted.
  // Build the allowed prefix set from the *visible* jobs so non-admins get a
  // rollup scoped to their portfolio, not the whole company.
  const allowedJobNames = jobs.map((j) => j.name);
  const isPoVisible = (jobKey: string | null): boolean => {
    if (!jobKey) return false;
    return allowedJobNames.some((n) => jobKeyMatchesName(jobKey, n));
  };
  let poCommitted = 0;
  let poPaid = 0;
  let poOutstanding = 0;
  let poCount = 0;
  const poJobKeys = new Set<string>();
  for (let from = 0; ; from += 1000) {
    const { data } = await supabase
      .from("purchase_orders")
      .select("cost, amount_paid, amount_remaining, job_key")
      .eq("hidden", false)
      .range(from, from + 999);
    const poRows = (data ?? []) as {
      cost: number | null;
      amount_paid: number | null;
      amount_remaining: number | null;
      job_key: string | null;
    }[];
    for (const r of poRows) {
      if (!isPoVisible(r.job_key)) continue;
      poCommitted += Number(r.cost) || 0;
      poPaid += Number(r.amount_paid) || 0;
      poOutstanding += Number(r.amount_remaining) || 0;
      if (r.job_key) poJobKeys.add(r.job_key);
      poCount += 1;
    }
    if (poRows.length < 1000) break;
  }
  const poJobCount = poJobKeys.size;
  const fmtM = (n: number) =>
    n >= 1_000_000
      ? `$${(n / 1_000_000).toFixed(1)}M`
      : n >= 1_000
        ? `$${Math.round(n / 1_000)}K`
        : `$${Math.round(n)}`;

  const pmNameById = new Map(pms.map((p) => [p.id, p.full_name]));
  const activePmByJob = new Map<string, string>();
  for (const a of assignments) activePmByJob.set(a.job_id, a.pm_id);

  // Index counts by job. todos.job is the display name ("Krauss"); items.job_id
  // is the slug ("krauss"). Keep two maps and combine them in countsFor so the
  // portfolio totals equal what each job page shows (items + todos).
  const openByJob = new Map<string, { open: number; past_due: number }>();
  for (const t of todos) {
    if (!t.job) continue;
    const rec = openByJob.get(t.job) ?? { open: 0, past_due: 0 };
    rec.open += 1;
    if (t.due_date && t.due_date < todayIso) rec.past_due += 1;
    openByJob.set(t.job, rec);
  }
  const openByJobId = new Map<string, { open: number; past_due: number }>();
  for (const i of items) {
    if (!i.job_id) continue;
    const rec = openByJobId.get(i.job_id) ?? { open: 0, past_due: 0 };
    rec.open += 1;
    if (i.target_date && i.target_date < todayIso) rec.past_due += 1;
    openByJobId.set(i.job_id, rec);
  }

  const pendingByJob = new Map<string, number>();
  for (const e of pending) {
    if (!e.job_id) continue;
    pendingByJob.set(e.job_id, (pendingByJob.get(e.job_id) ?? 0) + 1);
  }

  // Combine todo counts (keyed by display name) with item counts (keyed by
  // slug) for each job.
  const countsFor = (j: JobRow) => {
    const t = openByJob.get(j.name) ?? { open: 0, past_due: 0 };
    const i = openByJobId.get(j.id) ?? { open: 0, past_due: 0 };
    return { open: t.open + i.open, past_due: t.past_due + i.past_due };
  };

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
  let totalPending = 0;
  for (const j of rows) {
    const c = countsFor(j);
    totalOpen += c.open;
    totalPastDue += c.past_due;
    totalPending += pendingByJob.get(j.id) ?? 0;
  }
  const avgOpen = rows.length ? (totalOpen / rows.length).toFixed(1) : "0";
  const avgPastDue = rows.length ? (totalPastDue / rows.length).toFixed(1) : "0";

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <header className="px-5 pt-8 pb-2">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Jobs
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          {pmFilter
            ? `${pmNameById.get(pmFilter) ?? "Portfolio"} · ${rows.length} ${rows.length === 1 ? "job" : "jobs"}`
            : "Across the portfolio"}
        </p>
      </header>

      {/* Director stat strip — portfolio health at a glance (no extra queries;
          all derived from data already loaded for the list). */}
      <section className="px-5 pt-4">
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <StatTile label="Active jobs" value={rows.length} />
          <StatTile label="Open items" value={totalOpen} />
          <StatTile
            label="Past due"
            value={totalPastDue}
            tone={totalPastDue > 0 ? "urgent" : undefined}
          />
          <StatTile
            label="To approve"
            value={totalPending}
            tone={totalPending > 0 ? "accent" : undefined}
          />
        </div>
        <p className="mt-2 font-mono text-[10px] tracking-[0.14em] uppercase text-ink-3">
          avg {avgOpen} open · {avgPastDue} past due / job
        </p>
      </section>

      {poCount > 0 && (
        <section className="px-5 pt-2">
          <div className="border border-rule p-4">
            <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-2">
              Portfolio · purchase orders
            </h2>
            <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-sm tabular-nums">
              <span className="text-foreground">{fmtM(poCommitted)} committed</span>
              <span className="text-ink-2">{fmtM(poPaid)} paid</span>
              <span className="text-urgent">{fmtM(poOutstanding)} outstanding</span>
            </div>
            <p className="mt-2 font-mono text-[10px] tracking-[0.14em] uppercase text-ink-3">
              {poCount} POs · {poJobCount} jobs · avg{" "}
              {fmtM(poJobCount > 0 ? poOutstanding / poJobCount : 0)} outstanding/job
            </p>
          </div>
        </section>
      )}

      {/* PM filter pills only render for admins — PMs already see only their
          jobs, so a filter would be redundant and noisy. */}
      {user?.role === "admin" && pmPills.length > 0 && (
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

      {/* Empty-state CTA: newly-signed-up users who haven't been granted any
          jobs yet land here. Don't show for admin (they always see jobs) or
          when filtering. */}
      {rows.length === 0 && user && user.role !== "admin" && !pmFilter && (
        <RequestAccessCard />
      )}

      <ul className="mt-4 stagger-children">
        {rows.length === 0 ? (
          <li className="px-5 py-16 text-center text-ink-3 text-sm">
            {pmFilter ? "No jobs for this PM." : "No jobs yet."}
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
                  className="flex items-baseline gap-3 px-5 py-3.5 border-b border-rule hover:bg-oceanside/30 transition-colors"
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

function StatTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: "urgent" | "accent";
}) {
  const color =
    tone === "urgent"
      ? "text-urgent"
      : tone === "accent"
        ? "text-accent"
        : "text-foreground";
  return (
    <div className="border border-rule bg-paper p-3 transition hover:-translate-y-0.5 hover:border-accent hover:shadow-sm">
      <div className={"font-head text-2xl leading-none tabular-nums " + color}>
        {value}
      </div>
      <div className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-3">
        {label}
      </div>
    </div>
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
