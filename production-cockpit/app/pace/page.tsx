import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Todo, PM, OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";

export const dynamic = "force-dynamic";

interface WeekBucket {
  isoMonday: string;
  label: string;
  opened: number;
  closed: number;
}

interface PMSignals {
  agingSelections: number;       // SELECTION open > 14d
  urgentStale: number;           // URGENT open > 7d
  jobsWithoutClose: string[];    // jobs with no COMPLETE in 14d
  prereqAlerts: number;          // upcoming sub appearances with open prereqs
}

function isoMonday(d: Date): Date {
  const out = new Date(
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())
  );
  const day = (out.getUTCDay() + 6) % 7;
  out.setUTCDate(out.getUTCDate() - day);
  return out;
}

function fourWeekBuckets(): WeekBucket[] {
  const now = isoMonday(new Date());
  const out: WeekBucket[] = [];
  for (let w = 3; w >= 0; w--) {
    const d = new Date(now);
    d.setUTCDate(d.getUTCDate() - w * 7);
    out.push({
      isoMonday: d.toISOString(),
      label: `${d.getUTCMonth() + 1}/${d.getUTCDate()}`,
      opened: 0,
      closed: 0,
    });
  }
  return out;
}

export default async function PacePage() {
  const supabase = supabaseServer();
  const fourWeeksAgo = new Date(
    Date.now() - 28 * 86_400_000
  ).toISOString();
  const fourteenDaysAgo = new Date(
    Date.now() - 14 * 86_400_000
  ).toISOString();
  const sevenDaysAgo = new Date(
    Date.now() - 7 * 86_400_000
  ).toISOString();
  const todayIso = new Date().toISOString().slice(0, 10);
  const sevenDaysAhead = new Date(Date.now() + 7 * 86_400_000)
    .toISOString()
    .slice(0, 10);

  const [
    allTodosRes,
    pmsRes,
    openTodosRes,
    upcomingRes,
  ] = await Promise.all([
    supabase
      .from("todos")
      .select("id, pm_id, status, created_at, completed_at, job, category, priority")
      .gte("created_at", fourWeeksAgo),
    supabase
      .from("pms")
      .select("id, full_name, active")
      .eq("active", true)
      .order("full_name"),
    // All open todos (full state) for signal computation
    supabase
      .from("todos")
      .select("id, pm_id, status, category, priority, created_at, due_date, job, sub_id")
      .in("status", OPEN_STATUSES as Status[]),
    // Upcoming sub-appearances next 7 days
    supabase
      .from("todos")
      .select("id, pm_id, job, due_date, sub_id")
      .in("status", OPEN_STATUSES as Status[])
      .not("sub_id", "is", null)
      .gte("due_date", todayIso)
      .lte("due_date", sevenDaysAhead),
  ]);

  const pms = (pmsRes.data ?? []) as PM[];
  const todos = (allTodosRes.data ?? []) as Todo[];
  const openTodos = (openTodosRes.data ?? []) as Todo[];
  const upcoming = (upcomingRes.data ?? []) as Todo[];

  const byPm: Record<string, WeekBucket[]> = {};
  for (const pm of pms) byPm[pm.id] = fourWeekBuckets();
  for (const t of todos) {
    const pmBuckets = byPm[t.pm_id];
    if (!pmBuckets) continue;
    const openedDate = isoMonday(new Date(t.created_at));
    for (const b of pmBuckets) {
      if (new Date(b.isoMonday).getTime() === openedDate.getTime()) {
        b.opened++;
        break;
      }
    }
    if (t.completed_at) {
      const closedDate = isoMonday(new Date(t.completed_at));
      for (const b of pmBuckets) {
        if (new Date(b.isoMonday).getTime() === closedDate.getTime()) {
          b.closed++;
          break;
        }
      }
    }
  }

  // Open count per PM
  const openByPm: Record<string, number> = {};
  for (const t of openTodos) {
    openByPm[t.pm_id] = (openByPm[t.pm_id] ?? 0) + 1;
  }

  // Signals per PM
  const signalsByPm: Record<string, PMSignals> = {};
  for (const pm of pms) {
    signalsByPm[pm.id] = {
      agingSelections: 0,
      urgentStale: 0,
      jobsWithoutClose: [],
      prereqAlerts: 0,
    };
  }
  for (const t of openTodos) {
    const sig = signalsByPm[t.pm_id];
    if (!sig) continue;
    if (
      t.category === "SELECTION" &&
      t.created_at &&
      t.created_at < fourteenDaysAgo
    ) {
      sig.agingSelections++;
    }
    if (
      t.priority === "URGENT" &&
      t.created_at &&
      t.created_at < sevenDaysAgo
    ) {
      sig.urgentStale++;
    }
  }
  // Jobs without a close in 14d: any job with todos but zero completed_at in last 14d
  const jobsByPm: Record<string, Set<string>> = {};
  const closedJobsByPm: Record<string, Set<string>> = {};
  for (const t of todos) {
    if (!jobsByPm[t.pm_id]) jobsByPm[t.pm_id] = new Set();
    jobsByPm[t.pm_id].add(t.job);
    if (t.completed_at && t.completed_at > fourteenDaysAgo) {
      if (!closedJobsByPm[t.pm_id]) closedJobsByPm[t.pm_id] = new Set();
      closedJobsByPm[t.pm_id].add(t.job);
    }
  }
  for (const pmId in jobsByPm) {
    const sig = signalsByPm[pmId];
    if (!sig) continue;
    const closed = closedJobsByPm[pmId] ?? new Set();
    sig.jobsWithoutClose = Array.from(jobsByPm[pmId]).filter((j) => !closed.has(j));
  }
  // Prereq alerts: upcoming sub appearances where same-job SELECTION/PROCUREMENT is open
  const openPrereqByJob = new Map<string, number>();
  for (const t of openTodos) {
    if (t.category === "SELECTION" || t.category === "PROCUREMENT") {
      openPrereqByJob.set(t.job, (openPrereqByJob.get(t.job) ?? 0) + 1);
    }
  }
  for (const u of upcoming) {
    const sig = signalsByPm[u.pm_id];
    if (!sig) continue;
    const prereqCount = openPrereqByJob.get(u.job) ?? 0;
    if (prereqCount > 0) sig.prereqAlerts++;
  }

  return (
    <main className="max-w-[480px] lg:max-w-[1200px] mx-auto min-h-screen bg-background">
      <Header />

      <div className="px-6 lg:px-10 pt-6 pb-3 border-b border-rule">
        <p className="text-[12px] tracking-[0.18em] uppercase text-ink-3 font-medium">
          Last 4 weeks · opened vs closed per PM
        </p>
        <h1 className="mt-1 font-head text-4xl font-semibold leading-tight text-ink">
          Pace &amp; Insights
        </h1>
      </div>

      <div className="lg:grid lg:grid-cols-2 lg:divide-x lg:divide-rule">
        {pms.map((pm) => {
          const buckets = byPm[pm.id] ?? [];
          const totalOpened = buckets.reduce((a, b) => a + b.opened, 0);
          const totalClosed = buckets.reduce((a, b) => a + b.closed, 0);
          const verdict =
            totalClosed > totalOpened
              ? { label: "Ahead", color: "text-success" }
              : totalClosed === totalOpened
                ? { label: "On pace", color: "text-ink" }
                : { label: "Behind", color: "text-urgent" };
          const max = Math.max(
            1,
            ...buckets.flatMap((b) => [b.opened, b.closed])
          );
          const sig = signalsByPm[pm.id];

          return (
            <section key={pm.id} className="border-b border-rule">
              <header className="px-6 lg:px-10 py-3 bg-muted/40 flex items-baseline justify-between">
                <h2 className="font-head text-lg font-semibold text-ink">
                  {pm.full_name.split(" ")[0]}
                </h2>
                <span
                  className={`text-[12px] uppercase tracking-[0.18em] font-medium ${verdict.color}`}
                >
                  {verdict.label}
                </span>
              </header>
              <div className="px-6 lg:px-10 py-4 grid grid-cols-4 gap-2">
                {buckets.map((b) => (
                  <div key={b.isoMonday} className="flex flex-col items-center">
                    <div className="h-20 w-full flex items-end gap-1.5 justify-center">
                      <div
                        className="w-3 bg-ink"
                        style={{ height: `${(b.opened / max) * 100}%` }}
                        title={`Opened: ${b.opened}`}
                      />
                      <div
                        className="w-3 bg-success"
                        style={{ height: `${(b.closed / max) * 100}%` }}
                        title={`Closed: ${b.closed}`}
                      />
                    </div>
                    <span className="mt-1.5 font-mono text-[11px] text-ink-3 tabular-nums">
                      {b.label}
                    </span>
                    <span className="font-mono text-[11px] text-ink tabular-nums">
                      {b.opened}/{b.closed}
                    </span>
                  </div>
                ))}
              </div>
              <div className="px-6 lg:px-10 pb-3 flex items-center gap-4 text-[11px] tracking-[0.15em] uppercase text-ink-3 font-medium">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 bg-ink" aria-hidden /> Opened {totalOpened}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 bg-success" aria-hidden /> Closed {totalClosed}
                </span>
                <span className="ml-auto">
                  Open · {openByPm[pm.id] ?? 0}
                </span>
              </div>

              {/* Improvement signals — simple bullet list */}
              {sig && (
                <div className="px-6 lg:px-10 py-4 border-t border-rule-soft bg-paper">
                  <p className="text-[12px] tracking-[0.18em] uppercase text-ink-3 font-medium mb-3">
                    Signals
                  </p>
                  <ul className="space-y-2.5 text-[14px]">
                    <SignalRow
                      label="Selections aging >14d"
                      count={sig.agingSelections}
                      tone={sig.agingSelections > 0 ? "warn" : "ok"}
                      href={`/?pm=${pm.id}&view=selections`}
                    />
                    <SignalRow
                      label="Urgent open >7d"
                      count={sig.urgentStale}
                      tone={sig.urgentStale > 0 ? "urgent" : "ok"}
                      href={`/?pm=${pm.id}`}
                    />
                    <SignalRow
                      label="Jobs with no close in 14d"
                      count={sig.jobsWithoutClose.length}
                      tone={sig.jobsWithoutClose.length > 0 ? "warn" : "ok"}
                      hint={
                        sig.jobsWithoutClose.length
                          ? sig.jobsWithoutClose.slice(0, 3).join(" · ")
                          : undefined
                      }
                    />
                    <SignalRow
                      label="Upcoming subs with open prereqs"
                      count={sig.prereqAlerts}
                      tone={sig.prereqAlerts > 0 ? "urgent" : "ok"}
                      href={`/schedule?pm=${pm.id}`}
                    />
                  </ul>
                </div>
              )}
            </section>
          );
        })}
      </div>
    </main>
  );
}

function SignalRow({
  label,
  count,
  tone,
  hint,
  href,
}: {
  label: string;
  count: number;
  tone: "ok" | "warn" | "urgent";
  hint?: string;
  href?: string;
}) {
  const dotColor =
    tone === "urgent"
      ? "bg-urgent"
      : tone === "warn"
        ? "bg-high"
        : "bg-success";
  const countColor =
    tone === "urgent"
      ? "text-urgent"
      : tone === "warn"
        ? "text-high"
        : "text-ink-3";

  const inner = (
    <div className="flex items-start gap-3">
      <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${dotColor}`} aria-hidden />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-ink">{label}</span>
          <span className={`font-mono text-[14px] tabular-nums font-medium ${countColor}`}>
            {count}
          </span>
        </div>
        {hint && (
          <p className="mt-0.5 font-mono text-[11px] text-ink-3 tabular-nums">
            {hint}
          </p>
        )}
      </div>
    </div>
  );

  if (href && count > 0) {
    return (
      <li>
        <Link
          href={href}
          className="block hover:bg-sand-2/40 rounded transition-colors -mx-1 px-1 py-0.5"
        >
          {inner}
        </Link>
      </li>
    );
  }
  return <li>{inner}</li>;
}
