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

  const [allTodos, pmsRes] = await Promise.all([
    supabase
      .from("todos")
      .select("id, pm_id, status, created_at, completed_at")
      .gte("created_at", fourWeeksAgo),
    supabase
      .from("pms")
      .select("id, full_name, active")
      .eq("active", true)
      .order("full_name"),
  ]);

  const pms = (pmsRes.data ?? []) as PM[];
  const todos = (allTodos.data ?? []) as Todo[];

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

  const openByPm: Record<string, number> = {};
  for (const t of todos) {
    if ((OPEN_STATUSES as Status[]).includes(t.status)) {
      openByPm[t.pm_id] = (openByPm[t.pm_id] ?? 0) + 1;
    }
  }

  return (
    <main className="max-w-[480px] lg:max-w-[1200px] mx-auto min-h-screen bg-background">
      <Header />
      <div className="px-5 py-2 border-b border-rule bg-sand-2/40 flex items-center justify-between">
        <Link
          href="/"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Todos
        </Link>
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Sheet · PACE-01
        </span>
      </div>
      <div className="px-5 pt-5 pb-4 border-b border-rule bg-paper">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Last 4 weeks · opened vs closed per PM
        </p>
        <h1 className="mt-1 font-head text-3xl font-semibold leading-none text-ink">
          Pace
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
          return (
            <section key={pm.id} className="border-b border-rule">
              <header className="px-5 py-3 bg-muted/40 flex items-baseline justify-between">
                <h2 className="font-head text-sm font-semibold uppercase tracking-[0.14em] text-ink">
                  {pm.full_name}
                </h2>
                <span
                  className={`font-mono text-[11px] uppercase tracking-[0.18em] ${verdict.color}`}
                >
                  {verdict.label}
                </span>
              </header>
              <div className="px-5 py-3 grid grid-cols-4 gap-2">
                {buckets.map((b) => (
                  <div key={b.isoMonday} className="flex flex-col items-center">
                    <div className="h-16 w-full flex items-end gap-1 justify-center">
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
                    <span className="mt-1 font-mono text-[10px] text-ink-3 tabular-nums">
                      {b.label}
                    </span>
                    <span className="font-mono text-[10px] text-ink tabular-nums">
                      {b.opened}/{b.closed}
                    </span>
                  </div>
                ))}
              </div>
              <div className="px-5 pb-3 flex items-center gap-4 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 bg-ink" aria-hidden /> Opened {totalOpened}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 bg-success" aria-hidden /> Closed {totalClosed}
                </span>
                <span className="ml-auto">
                  Open now · {openByPm[pm.id] ?? 0}
                </span>
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}
