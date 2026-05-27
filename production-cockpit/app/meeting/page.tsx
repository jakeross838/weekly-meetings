// /meeting — Monday meeting run-of-show.
//
// A guided, job-by-job agenda built from the cockpit's LIVE signals only:
// open commitments split into Past due / This week, subs to watch (the same
// RED/YELLOW health pill), contract %, and transcripts awaiting approval.
// Scope by PM. Walk top-to-bottom (urgent jobs first), check each off.
//
// Deliberately NOT the old Python build_meeting_prep (PPC%, taxonomy
// look-ahead prediction): we surface what the cockpit has, no invented
// metrics. The fuller Office/Site + prediction vision lives in Phase 12
// PLAN.md Part B and needs data not yet wired into the cockpit.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { OPEN_STATUSES, Status } from "@/lib/types";
import { subHealth } from "@/lib/sub-health";
import { Header } from "@/components/header";
import { MeetingAgenda, MeetingJob, MeetingItem } from "./meeting-client";
import { currentUser, canSeeJob } from "@/lib/auth";

export const dynamic = "force-dynamic";

interface SP {
  pm?: string;
}

type JobRow = {
  id: string;
  name: string;
  address: string | null;
  pm_id: string | null;
};
type TodoRow = {
  id: string;
  title: string;
  edited_title: string | null;
  job: string | null;
  due_date: string | null;
  sub_id: string | null;
};
type SubRow = {
  id: string;
  name: string;
  flagged_for_pm_binder: boolean;
  flag_reasons: string[] | null;
};

export default async function MeetingPage({ searchParams }: { searchParams: SP }) {
  const supabase = supabaseServer();
  const pmFilter = searchParams.pm ?? "";
  const today = new Date().toISOString().slice(0, 10);
  const in7 = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);

  const [jobsRes, todosRes, subsRes, pmsRes, assignRes, pendingRes, payAppRes] =
    await Promise.all([
      supabase.from("jobs").select("id, name, address, pm_id").order("name"),
      supabase
        .from("todos")
        .select("id, title, edited_title, job, due_date, sub_id")
        .in("status", OPEN_STATUSES as Status[]),
      supabase
        .from("subs")
        .select("id, name, flagged_for_pm_binder, flag_reasons")
        .eq("hidden", false),
      supabase.from("pms").select("id, full_name"),
      supabase
        .from("job_pm_assignments")
        .select("job_id, pm_id")
        .is("ended_at", null),
      supabase
        .from("ingestion_events")
        .select("job_id")
        .in("review_state", ["pending", "in_review"]),
      // Pay-app %; tolerates the table being absent.
      supabase
        .from("pay_app_line_items")
        .select("job_id, scheduled_value, total_completed"),
    ]);

  const user = currentUser();
  const allJobs = (jobsRes.data ?? []) as JobRow[];
  const jobs = allJobs.filter((j) => canSeeJob(user, j.id));
  const todos = (todosRes.data ?? []) as TodoRow[];
  const subs = (subsRes.data ?? []) as SubRow[];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];
  const pending = (pendingRes.data ?? []) as { job_id: string | null }[];
  const payApp =
    payAppRes && !payAppRes.error
      ? ((payAppRes.data ?? []) as {
          job_id: string;
          scheduled_value: number | null;
          total_completed: number | null;
        }[])
      : [];

  const pmNameById = new Map(pms.map((p) => [p.id, p.full_name]));
  const activePmByJob = new Map<string, string>();
  for (const a of assignments) activePmByJob.set(a.job_id, a.pm_id);
  const pmForJob = (j: JobRow) => activePmByJob.get(j.id) ?? j.pm_id ?? null;

  const subById = new Map(subs.map((s) => [s.id, s]));

  // Global per-sub commitment tally (across every job) — drives the health
  // pill, so a sub flagged on one job still reads its true status here.
  const subTally = new Map<string, { pastDue: number; dueSoon: number }>();
  for (const t of todos) {
    if (!t.sub_id) continue;
    const rec = subTally.get(t.sub_id) ?? { pastDue: 0, dueSoon: 0 };
    if (t.due_date && t.due_date < today) rec.pastDue += 1;
    else if (t.due_date && t.due_date >= today && t.due_date <= in7)
      rec.dueSoon += 1;
    subTally.set(t.sub_id, rec);
  }

  // Pay-app totals per job.
  const paySched = new Map<string, number>();
  const payComp = new Map<string, number>();
  for (const l of payApp) {
    paySched.set(
      l.job_id,
      (paySched.get(l.job_id) ?? 0) + (Number(l.scheduled_value) || 0)
    );
    payComp.set(
      l.job_id,
      (payComp.get(l.job_id) ?? 0) + (Number(l.total_completed) || 0)
    );
  }

  const pendingByJob = new Map<string, number>();
  for (const e of pending) {
    if (e.job_id)
      pendingByJob.set(e.job_id, (pendingByJob.get(e.job_id) ?? 0) + 1);
  }

  // todos.job stores the display name ("Krauss"); jobs.name matches it.
  const todosByJob = new Map<string, TodoRow[]>();
  for (const t of todos) {
    if (!t.job) continue;
    const arr = todosByJob.get(t.job) ?? [];
    arr.push(t);
    todosByJob.set(t.job, arr);
  }

  const daysBetween = (a: string, b: string) =>
    Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);

  const meetingJobs: MeetingJob[] = [];
  for (const j of jobs) {
    if (pmFilter && pmForJob(j) !== pmFilter) continue;
    const jobTodos = todosByJob.get(j.name) ?? [];

    const lite = (t: TodoRow): MeetingItem => ({
      id: t.id,
      title: t.edited_title ?? t.title,
      daysOver:
        t.due_date && t.due_date < today ? daysBetween(t.due_date, today) : null,
      daysTo:
        t.due_date && t.due_date >= today ? daysBetween(today, t.due_date) : null,
      subName: t.sub_id ? subById.get(t.sub_id)?.name ?? null : null,
    });

    const pastDue = jobTodos
      .filter((t) => t.due_date && t.due_date < today)
      .map(lite)
      .sort((a, b) => (b.daysOver ?? 0) - (a.daysOver ?? 0));
    const dueSoon = jobTodos
      .filter((t) => t.due_date && t.due_date >= today && t.due_date <= in7)
      .map(lite)
      .sort((a, b) => (a.daysTo ?? 0) - (b.daysTo ?? 0));
    const laterCount = jobTodos.length - pastDue.length - dueSoon.length;

    // Subs on this job that aren't GREEN — routed in as "watch" rows.
    const jobSubIds = Array.from(
      new Set(jobTodos.map((t) => t.sub_id).filter(Boolean) as string[])
    );
    const attentionSubs = jobSubIds
      .map((sid) => {
        const s = subById.get(sid);
        const tally = subTally.get(sid) ?? { pastDue: 0, dueSoon: 0 };
        const h = subHealth({
          pastDue: tally.pastDue,
          dueSoon: tally.dueSoon,
          flagged: s?.flagged_for_pm_binder ?? false,
        });
        return {
          id: sid,
          name: s?.name ?? sid,
          status: h.status,
          dotClass: h.dotClass,
          reason: s?.flag_reasons?.[0] ?? null,
        };
      })
      .filter((s) => s.status !== "green")
      .sort((a, b) => (a.status === "red" ? 0 : 1) - (b.status === "red" ? 0 : 1));

    const sched = paySched.get(j.id) ?? 0;
    const comp = payComp.get(j.id) ?? 0;
    const pid = pmForJob(j);
    meetingJobs.push({
      id: j.id,
      name: j.name,
      pmName: pid ? pmNameById.get(pid) ?? null : null,
      contractPct: sched > 0 ? Math.round((comp / sched) * 100) : null,
      pending: pendingByJob.get(j.id) ?? 0,
      pastDue,
      dueSoon,
      laterCount,
      attentionSubs,
    });
  }

  // Most past-due first → most due-soon → name. Clean jobs sink to the bottom.
  meetingJobs.sort(
    (a, b) =>
      b.pastDue.length - a.pastDue.length ||
      b.dueSoon.length - a.dueSoon.length ||
      a.name.localeCompare(b.name)
  );

  // PM scope pills (only PMs that own a job).
  const pmIds = new Set<string>();
  for (const j of jobs) {
    const pid = pmForJob(j);
    if (pid) pmIds.add(pid);
  }
  const pmPills = Array.from(pmIds)
    .map((id) => ({ id, name: pmNameById.get(id) ?? id }))
    .sort((a, b) => a.name.localeCompare(b.name));

  const totalPastDue = meetingJobs.reduce((s, j) => s + j.pastDue.length, 0);
  const totalDueSoon = meetingJobs.reduce((s, j) => s + j.dueSoon.length, 0);

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <header className="px-5 pt-8 pb-2">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Monday Meeting
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          {meetingJobs.length} job{meetingJobs.length === 1 ? "" : "s"}
          {totalPastDue > 0 && (
            <>
              {" · "}
              <span className="text-urgent">{totalPastDue} past due</span>
            </>
          )}
          {" · "}
          {totalDueSoon} due this week
        </p>
      </header>

      {/* PM filter pills only render for admins — PMs already see only their
          jobs, so a filter would be redundant and noisy. */}
      {user?.role === "admin" && pmPills.length > 0 && (
        <div className="px-5 pt-2 pb-1">
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-5 px-5">
            <ScopePill href="/meeting" active={!pmFilter} label="All PMs" />
            {pmPills.map((p) => (
              <ScopePill
                key={p.id}
                href={`/meeting?pm=${encodeURIComponent(p.id)}`}
                active={pmFilter === p.id}
                label={p.name}
              />
            ))}
          </div>
        </div>
      )}

      <MeetingAgenda jobs={meetingJobs} />
    </main>
  );
}

function ScopePill({
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
