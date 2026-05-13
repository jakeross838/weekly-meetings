import Link from "next/link";
import { notFound } from "next/navigation";
import { supabaseServer } from "@/lib/supabase";
import { Sub, Todo, OPEN_STATUSES, Status } from "@/lib/types";
import { shortDate, relativeOffset } from "@/lib/date";
import { Header } from "@/components/header";

export const dynamic = "force-dynamic";

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

  const openTodos = (openRes.data ?? []) as Todo[];
  const doneTodos = (doneRes.data ?? []) as Todo[];

  const ratingDisplay =
    sub.rating != null ? sub.rating.toFixed(1) : "—";
  const reliability =
    sub.reliability_pct != null ? sub.reliability_pct : null;

  return (
    <main className="max-w-[480px] lg:max-w-[960px] mx-auto min-h-screen bg-background">
      <Header />

      {/* Back link */}
      <div className="px-5 py-2 border-b border-rule bg-sand-2/40 flex items-center justify-between">
        <Link
          href="/subs"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← All subs
        </Link>
        <Link
          href="/"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          Todos
        </Link>
      </div>

      {/* Sub header */}
      <div className="px-5 pt-5 pb-6 border-b border-rule bg-paper rise">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Sub · {sub.trade ?? "Trade unknown"}
        </p>
        <h1 className="mt-1 font-head text-2xl font-semibold leading-tight text-ink">
          {sub.name}
        </h1>

        {/* Rating + reliability */}
        <div className="mt-4 flex items-stretch gap-px bg-rule">
          <div className="flex-1 bg-paper px-4 py-3">
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
              Rating
            </p>
            <p className="mt-1 font-mono text-2xl font-medium tabular-nums text-ink">
              {ratingDisplay}
              {sub.rating != null && (
                <span className="text-high text-base ml-1">★</span>
              )}
            </p>
          </div>
          <div className="flex-1 bg-paper px-4 py-3">
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
              Days / job
            </p>
            <p className="mt-1 font-mono text-2xl font-medium tabular-nums text-ink">
              {sub.avg_days_per_job != null
                ? sub.avg_days_per_job.toFixed(1)
                : "—"}
            </p>
          </div>
          <div className="flex-1 bg-paper px-4 py-3">
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
              Open
            </p>
            <p className="mt-1 font-mono text-2xl font-medium tabular-nums text-ink">
              {String(openTodos.length).padStart(2, "0")}
            </p>
          </div>
        </div>

        {sub.rating == null && (
          <p className="mt-4 px-3 py-2 border border-rule bg-sand-2/60 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
            No BT data yet · rating populates after next weekly analytics sync
          </p>
        )}

        {/* Why this rating — the specific deductions that produced the score */}
        {sub.rating_basis && sub.rating_basis.length > 0 && (
          <div className="mt-4">
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
              Why this rating
            </p>
            <ul className="space-y-1">
              {sub.rating_basis.map((line, i) => (
                <li
                  key={i}
                  className="font-mono text-[11px] leading-snug text-ink-2"
                >
                  {line}
                </li>
              ))}
            </ul>
            <p className="mt-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
              Source · Buildertrend analytics rollups · {sub.jobs_performed ?? 0} jobs
            </p>
          </div>
        )}

        {/* Flag reasons (when flagged for PM binder) */}
        {sub.flagged_for_pm_binder && sub.flag_reasons && sub.flag_reasons.length > 0 && (
          <div className="mt-4 border-l-2 border-urgent pl-3">
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-urgent">
              Flagged in PM binder
            </p>
            <ul className="mt-1.5 space-y-1">
              {sub.flag_reasons.map((r, i) => (
                <li
                  key={i}
                  className="text-[12px] text-ink-2 leading-snug"
                >
                  · {r}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Open todos for this sub */}
      <section
        className="rise"
        style={{ animationDelay: "120ms" }}
      >
        <header className="px-5 py-3 bg-muted/40 border-b border-rule flex items-baseline justify-between">
          <h2 className="font-head text-sm font-semibold uppercase tracking-[0.14em] text-ink">
            Open · {sub.name.split(" ")[0]}
          </h2>
          <span className="font-mono text-[11px] text-ink-3 tabular-nums">
            {String(openTodos.length).padStart(2, "0")}
          </span>
        </header>
        {openTodos.length === 0 ? (
          <div className="px-5 py-10 text-center font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            None open
          </div>
        ) : (
          openTodos.map((t) => <SubTodoRow key={t.id} todo={t} />)
        )}
      </section>

      {/* Recently done */}
      {doneTodos.length > 0 && (
        <section
          className="rise"
          style={{ animationDelay: "200ms" }}
        >
          <header className="px-5 py-3 bg-sand-2/50 border-b border-rule flex items-baseline justify-between">
            <h2 className="font-head text-sm font-semibold uppercase tracking-[0.14em] text-ink-2">
              Recently Done
            </h2>
            <span className="font-mono text-[11px] text-ink-3 tabular-nums">
              {String(doneTodos.length).padStart(2, "0")}
            </span>
          </header>
          {doneTodos.map((t) => (
            <div
              key={t.id}
              className="flex items-start gap-3 px-5 py-2.5 border-b border-rule-soft bg-paper/30"
            >
              <span className="mt-1 inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center border border-success/60 text-success">
                <svg viewBox="0 0 12 12" fill="none" className="h-2.5 w-2.5">
                  <path
                    d="M2 6.5L4.5 9L10 3"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="square"
                  />
                </svg>
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] leading-snug text-ink-3 line-through line-clamp-2">
                  {t.edited_title ?? t.title}
                </p>
                <p className="mt-0.5 font-mono text-[10px] text-ink-3 tabular-nums">
                  {t.id} · {t.job}
                  {t.completed_at && (
                    <>
                      {" · took "}
                      {Math.round(
                        (new Date(t.completed_at).getTime() -
                          new Date(t.created_at).getTime()) /
                          86_400_000
                      )}
                      d
                    </>
                  )}
                </p>
              </div>
            </div>
          ))}
        </section>
      )}

      <footer className="mt-6 px-5 py-6 border-t border-rule bg-sand-2/40">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Ross Built · Sub Profile · {sub.id}
        </p>
      </footer>
    </main>
  );
}

function SubTodoRow({ todo }: { todo: Todo }) {
  const priority = (todo.priority ?? "NORMAL").toUpperCase();
  const bar =
    priority === "URGENT"
      ? "bg-urgent"
      : priority === "HIGH"
        ? "bg-high"
        : "bg-rule";
  return (
    <div className="flex items-stretch border-b border-rule">
      <span className={`w-[3px] shrink-0 ${bar}`} aria-hidden />
      <div className="flex-1 min-w-0 px-4 py-3.5">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-[10px] tracking-[0.12em] text-ink-3">
            {todo.id}
          </span>
          {priority === "URGENT" && (
            <span className="ml-auto font-mono text-[10px] tracking-[0.18em] uppercase text-urgent">
              Urgent
            </span>
          )}
          {priority === "HIGH" && (
            <span className="ml-auto font-mono text-[10px] tracking-[0.18em] uppercase text-high">
              High
            </span>
          )}
        </div>
        <p className="text-[15px] leading-snug text-foreground line-clamp-3">
          {todo.edited_title ?? todo.title}
        </p>
        <div className="mt-2 flex items-center justify-between gap-3 font-mono text-[11px] text-ink-3 tabular-nums">
          <span className="truncate">{todo.job}</span>
          <span className="text-ink-2">
            open{" "}
            {Math.round(
              (Date.now() - new Date(todo.created_at).getTime()) / 86_400_000
            )}
            d
          </span>
          {todo.due_date && (
            <span>
              {shortDate(todo.due_date)} · {relativeOffset(todo.due_date)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
