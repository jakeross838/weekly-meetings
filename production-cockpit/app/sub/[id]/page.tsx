// /sub/[id] — simplified sub profile.
// Headline metrics: open, past-due, avg drift days.
// Body: open items (action) + recently done (collapsed).

import Link from "next/link";
import { notFound } from "next/navigation";
import { supabaseServer } from "@/lib/supabase";
import { Sub, Todo, OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";

export const dynamic = "force-dynamic";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  return Math.round(
    (new Date(b).getTime() - new Date(a).getTime()) / 86_400_000
  );
}

export default async function SubPage({
  params,
}: {
  params: { id: string };
}) {
  const supabase = supabaseServer();

  const [subRes, openRes, doneRes] = await Promise.all([
    supabase.from("subs").select("*").eq("id", params.id).maybeSingle(),
    supabase
      .from("todos")
      .select("*")
      .eq("sub_id", params.id)
      .in("status", OPEN_STATUSES as Status[])
      .order("due_date", { ascending: true, nullsFirst: false }),
    supabase
      .from("todos")
      .select("*")
      .eq("sub_id", params.id)
      .eq("status", "COMPLETE")
      .order("completed_at", { ascending: false })
      .limit(20),
  ]);

  const sub = subRes.data as Sub | null;
  if (!sub) notFound();

  // No-show count: rows in daily_logs.absent_crews that match this sub's
  // name or any of its aliases. Degrades to null if the daily_logs table
  // doesn't exist yet (migration 009 not applied) so the UI shows "—".
  const candidateNames = Array.from(
    new Set([sub.name, ...((sub.aliases ?? []) as string[])])
  ).filter(Boolean);
  let noShowCount: number | null = null;
  if (candidateNames.length > 0) {
    const { count, error } = await supabase
      .from("daily_logs")
      .select("id", { count: "exact", head: true })
      .overlaps("absent_crews", candidateNames);
    if (!error) {
      noShowCount = count ?? 0;
    } else if (!/PGRST205|does not exist/i.test(error.message)) {
      console.error("daily_logs no-show query failed:", error);
    }
  }

  // Phase C: activity timeline. Pull daily-log days where this sub appears
  // in crews_present + items scheduled for this sub. Tolerates the table /
  // columns not existing (returns empty array on PGRST205 / missing column).
  type LogRow = {
    log_date: string | null;
    job_key: string;
    parent_group_activities: string[] | null;
  };
  let presentDays: LogRow[] = [];
  if (candidateNames.length > 0) {
    const r = await supabase
      .from("daily_logs")
      .select("log_date, job_key, parent_group_activities")
      .overlaps("crews_present", candidateNames)
      .order("log_date", { ascending: false })
      .limit(120);
    if (!r.error) presentDays = (r.data ?? []) as LogRow[];
  }

  // Phase D: aggregate parent_group_activities across this sub's presence,
  // and compare against peers in the same trade.
  const activityCounts = new Map<string, { days: number; jobs: Set<string> }>();
  for (const row of presentDays) {
    const tags = Array.isArray(row.parent_group_activities)
      ? row.parent_group_activities
      : [];
    for (const tag of tags) {
      const rec = activityCounts.get(tag) ?? { days: 0, jobs: new Set() };
      rec.days += 1;
      if (row.job_key) rec.jobs.add(row.job_key);
      activityCounts.set(tag, rec);
    }
  }

  // Peer comparison: other subs in the same trade. We resolve their names
  // (+ aliases) and run one overlapping query per peer for now — the catalog
  // is ~54 entries so the worst-case fan-out is manageable. If perf bites,
  // collapse to a single GROUP BY query via an RPC later.
  type PeerStat = {
    id: string;
    name: string;
    byActivity: Map<string, number>;
  };
  let peers: PeerStat[] = [];
  if (sub.trade) {
    const peerRes = await supabase
      .from("subs")
      .select("id, name, aliases")
      .eq("trade", sub.trade)
      .neq("id", sub.id);
    const peerRows = (peerRes.data ?? []) as {
      id: string;
      name: string;
      aliases: string[] | null;
    }[];
    peers = await Promise.all(
      peerRows.map(async (p) => {
        const names = Array.from(
          new Set([p.name, ...((p.aliases ?? []) as string[])])
        ).filter(Boolean);
        if (names.length === 0)
          return { id: p.id, name: p.name, byActivity: new Map() };
        const r = await supabase
          .from("daily_logs")
          .select("parent_group_activities")
          .overlaps("crews_present", names)
          .limit(500);
        const byA = new Map<string, number>();
        if (!r.error) {
          for (const row of (r.data ?? []) as {
            parent_group_activities: string[] | null;
          }[]) {
            for (const tag of row.parent_group_activities ?? []) {
              byA.set(tag, (byA.get(tag) ?? 0) + 1);
            }
          }
        }
        return { id: p.id, name: p.name, byActivity: byA };
      })
    );
  }

  const openTodos = (openRes.data ?? []) as Todo[];
  const doneTodos = (doneRes.data ?? []) as Todo[];

  const today = todayIso();
  const pastDue = openTodos.filter(
    (t) => t.due_date != null && t.due_date < today
  );

  // Drift signal: of completed items that had a due_date, avg days late.
  // Negative = early, positive = late. Skip items missing either date.
  const driftSamples = doneTodos.filter(
    (t) => t.due_date != null && t.completed_at != null
  );
  const driftDays =
    driftSamples.length > 0
      ? driftSamples.reduce(
          (sum, t) =>
            sum +
            daysBetween(t.due_date as string, (t.completed_at as string).slice(0, 10)),
          0
        ) / driftSamples.length
      : null;

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      {/* Header */}
      <header className="px-5 pt-8 pb-6">
        <Link
          href="/subs"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Subs
        </Link>
        <h1 className="mt-4 font-head text-[28px] leading-none tracking-tight text-foreground">
          {sub.name}
        </h1>
        {sub.trade && (
          <p className="mt-1.5 text-ink-3 text-sm">{sub.trade}</p>
        )}
      </header>

      {/* Headline metrics — four numbers, no decoration */}
      <section className="px-5 pt-2">
        <div className="grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-4">
          <Metric label="Open" value={openTodos.length} />
          <Metric
            label="Past due"
            value={pastDue.length}
            accent={pastDue.length > 0 ? "urgent" : undefined}
          />
          <Metric
            label="No-shows"
            value={noShowCount == null ? "—" : noShowCount}
            accent={
              noShowCount != null && noShowCount > 0 ? "urgent" : undefined
            }
            sub={noShowCount == null ? "no log data" : "from daily logs"}
          />
          <Metric
            label="Avg drift"
            value={
              driftDays == null
                ? "—"
                : `${driftDays > 0 ? "+" : ""}${driftDays.toFixed(1)}d`
            }
            accent={driftDays != null && driftDays > 1 ? "urgent" : undefined}
            sub={
              driftSamples.length > 0
                ? `n=${driftSamples.length}`
                : "no data"
            }
          />
        </div>
      </section>

      {/* Open items */}
      <section className="px-5 pt-10">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
          Open · {openTodos.length}
        </h2>
        {openTodos.length === 0 ? (
          <p className="text-ink-3 text-sm">None open.</p>
        ) : (
          <ul className="space-y-2">
            {openTodos.map((t) => {
              const isPastDue =
                t.due_date != null && t.due_date < today;
              return (
                <li
                  key={t.id}
                  className={`py-1.5 min-h-[40px] ${
                    isPastDue ? "border-l-2 border-urgent pl-2 -ml-2" : ""
                  }`}
                >
                  <div className="flex gap-3 items-baseline">
                    <p className="flex-1 min-w-0 text-foreground text-sm leading-snug">
                      {t.edited_title ?? t.title}
                      <span className="text-ink-3"> · {t.job}</span>
                    </p>
                    {t.due_date && (
                      <span
                        className={`shrink-0 text-xs font-mono ${
                          isPastDue ? "text-urgent" : "text-ink-3"
                        }`}
                      >
                        {isPastDue
                          ? `-${daysBetween(t.due_date, today)}d`
                          : daysBetween(today, t.due_date) === 0
                            ? "today"
                            : `${daysBetween(today, t.due_date)}d`}
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Activity breakdown — what this sub does, by BT parent_group tag */}
      {activityCounts.size > 0 && (
        <section className="px-5 pt-10">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
            Does · {activityCounts.size} activit
            {activityCounts.size === 1 ? "y" : "ies"}
          </h2>
          <ul className="space-y-1.5">
            {Array.from(activityCounts.entries())
              .sort((a, b) => b[1].days - a[1].days)
              .map(([tag, rec]) => {
                // Compare against peers
                const peerCounts = peers
                  .map((p) => ({
                    name: p.name,
                    days: p.byActivity.get(tag) ?? 0,
                  }))
                  .filter((p) => p.days > 0)
                  .sort((a, b) => b.days - a.days)
                  .slice(0, 3);
                return (
                  <li
                    key={tag}
                    className="py-1.5 border-b border-rule-soft last:border-b-0"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-sm text-foreground">{tag}</span>
                      <span className="font-mono text-xs text-ink-2 tabular-nums">
                        {rec.days}d · {rec.jobs.size} job
                        {rec.jobs.size === 1 ? "" : "s"}
                      </span>
                    </div>
                    {peerCounts.length > 0 && (
                      <p className="mt-1 font-mono text-[10px] text-ink-3 tabular-nums">
                        peers:{" "}
                        {peerCounts
                          .map((p) => `${p.name.split(" ")[0]} ${p.days}d`)
                          .join(" · ")}
                      </p>
                    )}
                  </li>
                );
              })}
          </ul>
          <p className="mt-3 text-[10px] font-mono tracking-[0.18em] uppercase text-ink-3">
            from daily logs · last 120 entries
          </p>
        </section>
      )}

      {/* Activity timeline — chronological list of on-site days */}
      {presentDays.length > 0 && (
        <section className="px-5 pt-10">
          <details>
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-2">
              On-site timeline · {presentDays.length} day
              {presentDays.length === 1 ? "" : "s"}
            </summary>
            <ul className="mt-2 space-y-1">
              {presentDays.slice(0, 60).map((row, i) => (
                <li
                  key={i}
                  className="flex items-baseline justify-between gap-3 py-1"
                >
                  <span className="text-sm text-ink-2">
                    {row.log_date ?? "—"}
                  </span>
                  <span className="font-mono text-xs text-ink-3 tabular-nums truncate">
                    {row.job_key}
                  </span>
                </li>
              ))}
              {presentDays.length > 60 && (
                <li className="text-center font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 pt-2">
                  + {presentDays.length - 60} more
                </li>
              )}
            </ul>
          </details>
        </section>
      )}

      {/* Recently done — collapsed */}
      {doneTodos.length > 0 && (
        <section className="px-5 pt-10">
          <details>
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-2">
              Recently done · {doneTodos.length}
            </summary>
            <ul className="mt-2 space-y-1.5">
              {doneTodos.map((t) => (
                <li
                  key={t.id}
                  className="text-ink-3 text-sm line-through truncate"
                >
                  {t.edited_title ?? t.title}
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </main>
  );
}

function Metric({
  label,
  value,
  accent,
  sub,
}: {
  label: string;
  value: number | string;
  accent?: "urgent";
  sub?: string;
}) {
  return (
    <div className="flex flex-col items-start">
      <span
        className={
          "font-mono text-[28px] font-medium leading-none tabular-nums " +
          (accent === "urgent" ? "text-urgent" : "text-ink")
        }
      >
        {value}
      </span>
      <span className="mt-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
        {label}
      </span>
      {sub && (
        <span className="mt-0.5 font-mono text-[9px] tracking-[0.12em] uppercase text-ink-3 opacity-70">
          {sub}
        </span>
      )}
    </div>
  );
}
