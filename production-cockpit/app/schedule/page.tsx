// /schedule — flat upcoming list grouped by date.
// One row per item; click a job → /v2/job/[id].

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Todo, OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";

export const dynamic = "force-dynamic";

interface SP {
  days?: string;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function inDaysIso(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
}

function dateBucket(due: string, today: string): string {
  if (due < today) return "Past due";
  if (due === today) return "Today";
  const tomorrow = inDaysIso(1);
  if (due === tomorrow) return "Tomorrow";
  const in7 = inDaysIso(7);
  if (due <= in7) return "This week";
  const in14 = inDaysIso(14);
  if (due <= in14) return "Next week";
  return "Later";
}

function fullLabel(iso: string): string {
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export default async function SchedulePage({
  searchParams,
}: {
  searchParams: SP;
}) {
  const supabase = supabaseServer();
  const horizonDays = searchParams.days === "30" ? 30 : 14;

  const today = todayIso();
  const horizon = inDaysIso(horizonDays);

  const [todosRes, jobsRes] = await Promise.all([
    supabase
      .from("todos")
      .select("*, sub:subs(id, name, trade, rating, reliability_pct, avg_days_per_job)")
      .in("status", OPEN_STATUSES as Status[])
      .not("due_date", "is", null)
      .lte("due_date", horizon)
      .order("due_date", { ascending: true }),
    supabase.from("jobs").select("id, name"),
  ]);

  const todos = (todosRes.data ?? []) as Todo[];
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const jobNameById = new Map(jobs.map((j) => [j.id, j.name]));

  // Group by bucket
  const buckets = new Map<string, Todo[]>();
  for (const t of todos) {
    if (!t.due_date) continue;
    const b = dateBucket(t.due_date, today);
    if (!buckets.has(b)) buckets.set(b, []);
    buckets.get(b)!.push(t);
  }

  const bucketOrder = [
    "Past due",
    "Today",
    "Tomorrow",
    "This week",
    "Next week",
    "Later",
  ];

  const pastDueCount = (buckets.get("Past due") ?? []).length;

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <header className="px-5 pt-8 pb-2">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Schedule
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          {todos.length} item{todos.length === 1 ? "" : "s"} in the next{" "}
          {horizonDays} days
          {pastDueCount > 0 && (
            <>
              {" · "}
              <span className="text-urgent">{pastDueCount} past due</span>
            </>
          )}
        </p>
      </header>

      {/* Horizon toggle — 14 / 30 */}
      <div className="px-5 pt-4">
        <div className="flex gap-1.5">
          <HorizonPill href="/schedule" active={horizonDays === 14} label="14 days" />
          <HorizonPill
            href="/schedule?days=30"
            active={horizonDays === 30}
            label="30 days"
          />
        </div>
      </div>

      {todos.length === 0 && (
        <p className="px-5 pt-10 text-ink-3 text-sm">
          Nothing scheduled in the next {horizonDays} days.
        </p>
      )}

      {bucketOrder.map((bucket) => {
        const items = buckets.get(bucket) ?? [];
        if (items.length === 0) return null;
        const cap = bucket === "Past due" ? 20 : items.length;
        const shown = items.slice(0, cap);
        const hidden = items.length - shown.length;
        return (
          <section key={bucket} className="px-5 pt-8">
            <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
              {bucket} · {items.length}
            </h2>
            <ul className="space-y-2">
              {shown.map((t) => (
                <ItemRow
                  key={t.id}
                  todo={t}
                  jobName={t.job ? jobNameById.get(t.job) ?? t.job : "—"}
                  highlight={bucket === "Past due"}
                />
              ))}
            </ul>
            {hidden > 0 && (
              <p className="mt-3 text-center font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
                + {hidden} more · open a job to see all
              </p>
            )}
          </section>
        );
      })}
    </main>
  );
}

function HorizonPill({
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

function ItemRow({
  todo,
  jobName,
  highlight,
}: {
  todo: Todo;
  jobName: string;
  highlight?: boolean;
}) {
  const subLabel = todo.sub?.name ?? null;
  return (
    <li
      className={`py-1.5 min-h-[40px] ${
        highlight ? "border-l-2 border-urgent pl-2 -ml-2" : ""
      }`}
    >
      <div className="flex gap-3 items-baseline">
        <Link
          href={todo.job ? `/v2/job/${todo.job}` : "#"}
          className="flex-1 min-w-0 text-foreground text-sm leading-snug hover:text-accent transition-colors"
        >
          {todo.edited_title ?? todo.title}
          <span className="text-ink-3">
            {" · "}
            {jobName}
            {subLabel && ` · ${subLabel}`}
          </span>
        </Link>
        {todo.due_date && (
          <span
            className={`shrink-0 text-xs font-mono ${
              highlight ? "text-urgent" : "text-ink-3"
            }`}
          >
            {fullLabel(todo.due_date)}
          </span>
        )}
      </div>
    </li>
  );
}
