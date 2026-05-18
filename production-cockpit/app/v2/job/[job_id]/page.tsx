// /v2/job/[job_id] — PM home page.
//
// Three sections: Today, Soon, Open. Empty sections hidden.
// Merges two underlying sources into one list:
//   • v2 items table  (job_id = slug)
//   • v1 todos table  (job = display name)
// Each row knows which table it came from so the check-off button can
// hit the right endpoint.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { OPEN_STATUSES, Status } from "@/lib/types";
import { CheckOffButton } from "./check-off-button";

export const dynamic = "force-dynamic";

// Normalized row shape — both items and todos collapse into this.
interface RowData {
  id: string;
  source: "item" | "todo";
  title: string;
  sub_name: string | null;
  owner: string | null;
  target_date: string | null; // ISO yyyy-mm-dd
  carryover_count: number;
  created_at: string;
  completed_at: string | null;
  is_signal: boolean;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function inDaysIso(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
}

function dayLabel(iso: string, today: string): string {
  if (iso < today) {
    const days = Math.floor(
      (new Date(today).getTime() - new Date(iso).getTime()) / 86_400_000
    );
    return `-${days}d`;
  }
  if (iso === today) return "today";
  const days = Math.floor(
    (new Date(iso).getTime() - new Date(today).getTime()) / 86_400_000
  );
  if (days <= 7) {
    return new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
      weekday: "short",
      timeZone: "UTC",
    });
  }
  return `${days}d`;
}

export default async function V2JobPage({
  params,
}: {
  params: { job_id: string };
}) {
  const { job_id } = params;
  const supabase = supabaseServer();

  // First fetch the job so we know its display name (todos.job uses
  // display name like "Krauss" while jobs.id is the slug "krauss").
  const jobRes = await supabase
    .from("jobs")
    .select("id, name, address, pm_id")
    .eq("id", job_id)
    .maybeSingle();

  if (!jobRes.data) {
    return (
      <main className="max-w-[560px] mx-auto min-h-screen bg-background px-5 py-16">
        <h1 className="font-head text-2xl text-foreground">Job not found</h1>
        <p className="mt-2 text-ink-3 text-sm">
          No job with id <span className="font-mono">{job_id}</span>.
        </p>
      </main>
    );
  }

  const job = jobRes.data as {
    id: string;
    name: string;
    address: string | null;
    pm_id: string | null;
  };

  const [itemsRes, todosRes, completedItemsRes, completedTodosRes, pendingEventsRes] =
    await Promise.all([
      supabase
        .from("items")
        .select(
          "id, title, sub_id, owner, target_date, status, actionability, carryover_count, created_at, completed_at, sub:subs(id, name)"
        )
        .eq("job_id", job_id)
        .in("status", ["open", "in_progress", "blocked"]),
      supabase
        .from("todos")
        .select(
          "id, title, edited_title, due_date, status, sub_id, created_at, completed_at, sub:subs(id, name)"
        )
        .eq("job", job.name)
        .in("status", OPEN_STATUSES as Status[]),
      supabase
        .from("items")
        .select("id, title, completed_at")
        .eq("job_id", job_id)
        .eq("status", "complete")
        .gte("completed_at", new Date(Date.now() - 7 * 86_400_000).toISOString())
        .order("completed_at", { ascending: false })
        .limit(20),
      supabase
        .from("todos")
        .select("id, title, edited_title, completed_at")
        .eq("job", job.name)
        .eq("status", "COMPLETE")
        .gte("completed_at", new Date(Date.now() - 7 * 86_400_000).toISOString())
        .order("completed_at", { ascending: false })
        .limit(20),
      supabase
        .from("ingestion_events")
        .select("id, proposed_count")
        .eq("job_id", job_id)
        .in("review_state", ["pending", "in_review"]),
    ]);

  const pendingEvents = (pendingEventsRes.data ?? []) as {
    id: string;
    proposed_count: number;
  }[];

  type RawItem = {
    id: string;
    title: string;
    sub_id: string | null;
    owner: string | null;
    target_date: string | null;
    actionability: "actionable" | "signal" | null;
    carryover_count: number | null;
    created_at: string;
    completed_at: string | null;
    sub: { id: string; name: string } | null;
  };
  type RawTodo = {
    id: string;
    title: string;
    edited_title: string | null;
    due_date: string | null;
    sub_id: string | null;
    created_at: string;
    completed_at: string | null;
    sub: { id: string; name: string } | null;
  };

  const items = ((itemsRes.data ?? []) as unknown) as RawItem[];
  const todos = ((todosRes.data ?? []) as unknown) as RawTodo[];
  const completedItems = (completedItemsRes.data ?? []) as {
    id: string;
    title: string;
    completed_at: string;
  }[];
  const completedTodos = ((completedTodosRes.data ?? []) as unknown) as {
    id: string;
    title: string;
    edited_title: string | null;
    completed_at: string;
  }[];

  // Normalize both sources into RowData
  const itemRows: RowData[] = items.map((i) => ({
    id: i.id,
    source: "item",
    title: i.title,
    sub_name: i.sub?.name ?? null,
    owner: i.owner,
    target_date: i.target_date,
    carryover_count: i.carryover_count ?? 0,
    created_at: i.created_at,
    completed_at: i.completed_at,
    is_signal: i.actionability === "signal",
  }));
  const todoRows: RowData[] = todos.map((t) => ({
    id: t.id,
    source: "todo",
    title: t.edited_title ?? t.title,
    sub_name: t.sub?.name ?? null,
    owner: null,
    target_date: t.due_date,
    carryover_count: 0,
    created_at: t.created_at,
    completed_at: t.completed_at,
    is_signal: false,
  }));

  const actionable = [...itemRows, ...todoRows].filter((r) => !r.is_signal);

  const today = todayIso();
  const in7 = inDaysIso(7);
  const in60 = inDaysIso(60);

  // 1. Today — past-due, carryover ≥2, or due in next 7 days
  const todayRows = actionable.filter((r) => {
    if (r.target_date && r.target_date < today) return true;
    if (r.carryover_count >= 2) return true;
    if (r.target_date && r.target_date >= today && r.target_date <= in7) return true;
    return false;
  });
  todayRows.sort((a, b) =>
    (a.target_date ?? "9999").localeCompare(b.target_date ?? "9999")
  );

  const usedKeys = new Set(todayRows.map((r) => `${r.source}:${r.id}`));

  // 2. Soon — due 8..60 days out
  const soonRows = actionable.filter(
    (r) =>
      !usedKeys.has(`${r.source}:${r.id}`) &&
      r.target_date &&
      r.target_date > in7 &&
      r.target_date <= in60
  );
  soonRows.sort((a, b) =>
    (a.target_date ?? "").localeCompare(b.target_date ?? "")
  );
  soonRows.forEach((r) => usedKeys.add(`${r.source}:${r.id}`));

  // 3. Open — no date (or >60d)
  const openRows = actionable.filter(
    (r) => !usedKeys.has(`${r.source}:${r.id}`)
  );
  openRows.sort((a, b) => a.created_at.localeCompare(b.created_at));

  // Done — merge completed items + todos within last 7 days
  const completedRows = [
    ...completedItems.map((i) => ({
      id: i.id,
      source: "item" as const,
      title: i.title,
      completed_at: i.completed_at,
    })),
    ...completedTodos.map((t) => ({
      id: t.id,
      source: "todo" as const,
      title: t.edited_title ?? t.title,
      completed_at: t.completed_at,
    })),
  ];
  completedRows.sort((a, b) => b.completed_at.localeCompare(a.completed_at));

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <header className="px-5 pt-8 pb-6">
        <Link
          href="/"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Jobs
        </Link>
        <div className="mt-4 flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
              {job.name}
            </h1>
            {job.address && (
              <p className="mt-1.5 text-ink-3 text-sm">{job.address}</p>
            )}
          </div>
          {pendingEvents.length > 0 && (
            <Link
              href={`/v2/review`}
              className="shrink-0 text-[10px] font-mono uppercase tracking-[0.12em] text-urgent border border-urgent/60 px-2 py-1 hover:bg-urgent hover:text-paper transition-colors"
            >
              {pendingEvents.length} pending review
            </Link>
          )}
        </div>
      </header>

      {actionable.length === 0 && (
        <p className="px-5 pt-8 text-ink-3 text-sm">All clear.</p>
      )}

      <Section title="Today" rows={todayRows} today={today} highlight />
      <Section title="Soon" rows={soonRows} today={today} />
      <Section title="Open" rows={openRows} today={today} hideRightSlot />

      {completedRows.length > 0 && (
        <section className="px-5 pt-10">
          <details>
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-2">
              Done this week · {completedRows.length}
            </summary>
            <ul className="mt-2 space-y-1.5">
              {completedRows.map((r) => (
                <li
                  key={`${r.source}:${r.id}`}
                  className="flex gap-3 items-baseline py-1 min-h-[32px]"
                >
                  <CheckOffButton itemId={r.id} source={r.source} completed />
                  <span className="text-ink-3 text-sm line-through">
                    {r.title}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </main>
  );
}

function Section({
  title,
  rows,
  today,
  highlight,
  hideRightSlot,
}: {
  title: string;
  rows: RowData[];
  today: string;
  highlight?: boolean;
  hideRightSlot?: boolean;
}) {
  if (rows.length === 0) return null;
  return (
    <section className="px-5 pt-8">
      <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
        {title} · {rows.length}
      </h2>
      <ul className="space-y-2">
        {rows.map((r) => (
          <Row
            key={`${r.source}:${r.id}`}
            row={r}
            today={today}
            highlight={
              highlight && r.target_date != null && r.target_date < today
            }
            hideRightSlot={hideRightSlot}
          />
        ))}
      </ul>
    </section>
  );
}

function Row({
  row,
  today,
  highlight,
  hideRightSlot,
}: {
  row: RowData;
  today: string;
  highlight?: boolean;
  hideRightSlot?: boolean;
}) {
  const subLabel = row.sub_name ?? row.owner ?? null;
  return (
    <li
      className={`py-1.5 min-h-[40px] ${
        highlight ? "border-l-2 border-urgent pl-2 -ml-2" : ""
      }`}
    >
      <div className="flex gap-3 items-baseline">
        <CheckOffButton itemId={row.id} source={row.source} />
        <p className="flex-1 min-w-0 text-foreground text-sm leading-snug">
          {row.title}
          {subLabel && <span className="text-ink-3"> · {subLabel}</span>}
        </p>
        {!hideRightSlot && row.target_date && (
          <span
            className={`shrink-0 text-xs font-mono ${
              highlight ? "text-urgent" : "text-ink-3"
            }`}
          >
            {dayLabel(row.target_date, today)}
          </span>
        )}
      </div>
    </li>
  );
}
