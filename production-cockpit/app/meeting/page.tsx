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
import { businessToday, businessDateOffset } from "@/lib/today";
import { Header } from "@/components/header";
import { MeetingAgenda, MeetingJob, MeetingItem } from "./meeting-client";
import { currentUser, canSeeJobByPm } from "@/lib/auth";

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
  category: string | null;
};
type ItemRowDB = {
  id: string;
  title: string;
  target_date: string | null;
  sub_id: string | null;
  category: string | null;
  owner: string | null;
  job_id: string | null;
};
// One normalized commitment (todo OR v2 item) used to build the agenda.
type Entry = {
  id: string;
  source: "item" | "todo";
  title: string;
  date: string | null;
  sub_id: string | null;
  subName: string | null;
  category: string | null;
};
type SubRow = {
  id: string;
  name: string;
  flagged_for_pm_binder: boolean;
  flag_note: string | null;
};

export default async function MeetingPage({ searchParams }: { searchParams: SP }) {
  const supabase = supabaseServer();
  const pmFilter = searchParams.pm ?? "";
  const today = businessToday();
  const in7 = businessDateOffset(7);

  const [jobsRes, todosRes, itemsRes, subsRes, pmsRes, assignRes, pendingRes, payAppRes] =
    await Promise.all([
      supabase.from("jobs").select("id, name, address, pm_id").order("name"),
      supabase
        .from("todos")
        .select("id, title, edited_title, job, due_date, sub_id, category")
        .in("status", OPEN_STATUSES as Status[]),
      // v2 items belong on the agenda exactly like todos (the job page merges
      // them), so the Monday run-of-show and its counts stay complete.
      supabase
        .from("items")
        .select("id, title, target_date, sub_id, category, owner, job_id")
        .in("status", ["open", "in_progress", "blocked"]),
      supabase
        .from("subs")
        .select("id, name, flagged_for_pm_binder, flag_note")
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

  const user = await currentUser();
  const allJobs = (jobsRes.data ?? []) as JobRow[];
  const todos = (todosRes.data ?? []) as TodoRow[];
  const items = (itemsRes.data ?? []) as ItemRowDB[];
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

  // Visibility model: PMs see jobs where `jobs.pm_id` (or an active
  // job_pm_assignment) matches their pmId. Admin sees all.
  const jobs = allJobs.filter((j) => canSeeJobByPm(user, pmForJob(j)));

  const subById = new Map(subs.map((s) => [s.id, s]));

  // Global per-sub commitment tally (across every job) — drives the health
  // pill, so a sub flagged on one job still reads its true status here.
  const subTally = new Map<string, { pastDue: number; dueSoon: number }>();
  const tallySub = (subId: string | null, date: string | null) => {
    if (!subId) return;
    const rec = subTally.get(subId) ?? { pastDue: 0, dueSoon: 0 };
    if (date && date < today) rec.pastDue += 1;
    else if (date && date >= today && date <= in7) rec.dueSoon += 1;
    subTally.set(subId, rec);
  };
  for (const t of todos) tallySub(t.sub_id, t.due_date);
  for (const i of items) tallySub(i.sub_id, i.target_date);

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
  // items.job_id is the slug ("krauss"); jobs.id matches it.
  const itemsByJobId = new Map<string, ItemRowDB[]>();
  for (const i of items) {
    if (!i.job_id) continue;
    const arr = itemsByJobId.get(i.job_id) ?? [];
    arr.push(i);
    itemsByJobId.set(i.job_id, arr);
  }

  const daysBetween = (a: string, b: string) =>
    Math.floor((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);

  const meetingJobs: MeetingJob[] = [];
  for (const j of jobs) {
    if (pmFilter && pmForJob(j) !== pmFilter) continue;
    // Merge both commitment sources for this job into one normalized list.
    const entries: Entry[] = [
      ...(todosByJob.get(j.name) ?? []).map((t) => ({
        id: t.id,
        source: "todo" as const,
        title: t.edited_title ?? t.title,
        date: t.due_date,
        sub_id: t.sub_id,
        subName: t.sub_id ? subById.get(t.sub_id)?.name ?? null : null,
        category: t.category ?? null,
      })),
      ...(itemsByJobId.get(j.id) ?? []).map((i) => ({
        id: i.id,
        source: "item" as const,
        title: i.title,
        date: i.target_date,
        sub_id: i.sub_id,
        subName: i.sub_id
          ? subById.get(i.sub_id)?.name ?? null
          : i.owner ?? null,
        category: i.category ?? null,
      })),
    ];

    const lite = (e: Entry): MeetingItem => ({
      id: e.id,
      source: e.source,
      title: e.title,
      daysOver: e.date && e.date < today ? daysBetween(e.date, today) : null,
      daysTo: e.date && e.date >= today ? daysBetween(today, e.date) : null,
      subName: e.subName,
      category: e.category,
    });

    const pastDue = entries
      .filter((e) => e.date && e.date < today)
      .map(lite)
      .sort((a, b) => (b.daysOver ?? 0) - (a.daysOver ?? 0));
    const dueSoon = entries
      .filter((e) => e.date && e.date >= today && e.date <= in7)
      .map(lite)
      .sort((a, b) => (a.daysTo ?? 0) - (b.daysTo ?? 0));
    const laterCount = entries.length - pastDue.length - dueSoon.length;

    // Subs on this job that aren't GREEN — routed in as "watch" rows.
    const jobSubIds = Array.from(
      new Set(entries.map((e) => e.sub_id).filter(Boolean) as string[])
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
          reason: s?.flag_note ?? null,
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
