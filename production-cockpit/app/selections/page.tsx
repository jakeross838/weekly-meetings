import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Todo, OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";
import { shortDate, relativeOffset, daysFromToday } from "@/lib/date";

export const dynamic = "force-dynamic";

export default async function SelectionsPage() {
  const supabase = supabaseServer();
  const res = await supabase
    .from("todos")
    .select("*, sub:subs(id, name, trade, rating)")
    .eq("category", "SELECTION")
    .in("status", OPEN_STATUSES as Status[])
    .order("due_date", { ascending: true, nullsFirst: false });

  const todos = (res.data ?? []) as Todo[];

  // Group by job
  const byJob: Record<string, Todo[]> = {};
  for (const t of todos) {
    if (!byJob[t.job]) byJob[t.job] = [];
    byJob[t.job].push(t);
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
          Sheet · SEL-01
        </span>
      </div>

      <div className="px-5 pt-5 pb-4 border-b border-rule bg-paper">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Outstanding decisions · client / designer
        </p>
        <h1 className="mt-1 font-head text-3xl font-semibold leading-none text-ink">
          Selections
        </h1>
        <p className="mt-2 font-mono text-[11px] text-ink-3 tabular-nums">
          {todos.length} open across {Object.keys(byJob).length} jobs
        </p>
      </div>

      {Object.keys(byJob)
        .sort()
        .map((job) => (
          <section key={job} className="border-b border-rule">
            <header className="px-5 py-2 bg-muted/40 flex items-baseline justify-between">
              <h2 className="font-head text-sm font-semibold uppercase tracking-[0.14em] text-ink">
                {job}
              </h2>
              <span className="font-mono text-[10px] tabular-nums text-ink-3">
                {String(byJob[job].length).padStart(2, "0")}
              </span>
            </header>
            {byJob[job].map((t) => {
              const d = daysFromToday(t.due_date);
              const overdue = d != null && d < 0;
              return (
                <div
                  key={t.id}
                  className="flex items-stretch border-b border-rule-soft last:border-b-0"
                >
                  <span
                    className={`w-[3px] shrink-0 ${
                      t.priority === "URGENT"
                        ? "bg-urgent"
                        : t.priority === "HIGH"
                          ? "bg-high"
                          : "bg-rule"
                    }`}
                    aria-hidden
                  />
                  <div className="flex-1 min-w-0 px-4 py-3">
                    <p className="text-[14px] leading-snug text-ink line-clamp-3">
                      {t.edited_title ?? t.title}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2 font-mono text-[10px] text-ink-3 tabular-nums">
                      <span>{t.id}</span>
                      {t.due_date && (
                        <>
                          <span>·</span>
                          <span className={overdue ? "text-urgent" : ""}>
                            {shortDate(t.due_date)} · {relativeOffset(t.due_date)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </section>
        ))}
      {todos.length === 0 && (
        <div className="px-5 py-16 text-center font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          No selections outstanding
        </div>
      )}
    </main>
  );
}
