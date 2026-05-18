// /v2/job/[job_id] — PM home page (simplified).
//
// Three sections only: Today, Soon, Open. Empty sections are hidden.
// One-line rows. No signals, no confidence dots, no decoration.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { CheckOffButton } from "./check-off-button";

export const dynamic = "force-dynamic";

type ItemStatus = "open" | "in_progress" | "complete" | "blocked" | "cancelled";

interface ItemRow {
  id: string;
  human_readable_id: string;
  job_id: string;
  title: string;
  sub_id: string | null;
  owner: string | null;
  target_date: string | null;
  status: ItemStatus;
  actionability: "actionable" | "signal" | null;
  carryover_count: number | null;
  created_at: string;
  completed_at: string | null;
  sub: { id: string; name: string } | null;
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

  const [jobRes, itemsRes, completedRes, pendingEventsRes] = await Promise.all([
    supabase
      .from("jobs")
      .select("id, name, address, pm_id")
      .eq("id", job_id)
      .maybeSingle(),
    supabase
      .from("items")
      .select(
        "id, human_readable_id, job_id, title, sub_id, owner, target_date, status, actionability, carryover_count, created_at, completed_at, sub:subs(id, name)"
      )
      .eq("job_id", job_id)
      .in("status", ["open", "in_progress", "blocked"]),
    supabase
      .from("items")
      .select("id, title, completed_at")
      .eq("job_id", job_id)
      .eq("status", "complete")
      .gte("completed_at", new Date(Date.now() - 7 * 86_400_000).toISOString())
      .order("completed_at", { ascending: false })
      .limit(20),
    supabase
      .from("ingestion_events")
      .select("id, proposed_count")
      .eq("job_id", job_id)
      .in("review_state", ["pending", "in_review"]),
  ]);

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
  const items = ((itemsRes.data ?? []) as unknown) as ItemRow[];
  const completed = (completedRes.data ?? []) as {
    id: string;
    title: string;
    completed_at: string;
  }[];
  const pendingEvents = (pendingEventsRes.data ?? []) as {
    id: string;
    proposed_count: number;
  }[];

  const today = todayIso();
  const in7 = inDaysIso(7);
  const in60 = inDaysIso(60);

  // Actionable only — drop signals from the PM view entirely.
  const actionable = items.filter((i) => i.actionability !== "signal");

  // 1. Today — past-due, carryover ≥2, or due in next 7 days
  const todayItems = actionable.filter((i) => {
    if (i.target_date && i.target_date < today) return true;
    if ((i.carryover_count ?? 0) >= 2) return true;
    if (i.target_date && i.target_date >= today && i.target_date <= in7)
      return true;
    return false;
  });
  todayItems.sort((a, b) =>
    (a.target_date ?? "9999").localeCompare(b.target_date ?? "9999")
  );

  const todaySet = new Set(todayItems.map((i) => i.id));

  // 2. Soon — due 8..60 days out
  const soon = actionable.filter(
    (i) =>
      !todaySet.has(i.id) &&
      i.target_date &&
      i.target_date > in7 &&
      i.target_date <= in60
  );
  soon.sort((a, b) =>
    (a.target_date ?? "").localeCompare(b.target_date ?? "")
  );

  const soonSet = new Set<string>([...Array.from(todaySet), ...soon.map((i) => i.id)]);

  // 3. Open — no date (or >60d)
  const open = actionable.filter((i) => !soonSet.has(i.id));
  open.sort((a, b) => a.created_at.localeCompare(b.created_at));

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      {/* HEADER — just job name and address. Pending-review badge if anything's queued. */}
      <header className="px-5 pt-10 pb-6">
        <div className="flex items-start justify-between gap-3">
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

      <Section title="Today" items={todayItems} today={today} highlight />
      <Section title="Soon" items={soon} today={today} />
      <Section title="Open" items={open} today={today} hideRightSlot />

      {completed.length > 0 && (
        <section className="px-5 pt-10">
          <details>
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-2">
              Done this week · {completed.length}
            </summary>
            <ul className="mt-2 space-y-1.5">
              {completed.map((i) => (
                <li key={i.id} className="text-ink-3 text-sm line-through">
                  {i.title}
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
  items,
  today,
  highlight,
  hideRightSlot,
}: {
  title: string;
  items: ItemRow[];
  today: string;
  highlight?: boolean;
  hideRightSlot?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <section className="px-5 pt-8">
      <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
        {title} · {items.length}
      </h2>
      <ul className="space-y-2">
        {items.map((i) => (
          <Row
            key={i.id}
            item={i}
            today={today}
            highlight={
              highlight && i.target_date != null && i.target_date < today
            }
            hideRightSlot={hideRightSlot}
          />
        ))}
      </ul>
    </section>
  );
}

function Row({
  item,
  today,
  highlight,
  hideRightSlot,
}: {
  item: ItemRow;
  today: string;
  highlight?: boolean;
  hideRightSlot?: boolean;
}) {
  const subLabel = item.sub?.name ?? item.owner ?? null;
  return (
    <li
      className={`py-1.5 min-h-[40px] ${
        highlight ? "border-l-2 border-urgent pl-2 -ml-2" : ""
      }`}
    >
      <div className="flex gap-3 items-baseline">
        <CheckOffButton itemId={item.id} />
        <p className="flex-1 min-w-0 text-foreground text-sm leading-snug">
          {item.title}
          {subLabel && <span className="text-ink-3"> · {subLabel}</span>}
        </p>
        {!hideRightSlot && item.target_date && (
          <span
            className={`shrink-0 text-xs font-mono ${
              highlight ? "text-urgent" : "text-ink-3"
            }`}
          >
            {dayLabel(item.target_date, today)}
          </span>
        )}
      </div>
    </li>
  );
}
