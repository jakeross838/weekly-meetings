import { Todo } from "@/lib/types";
import { daysFromToday, shortDate } from "@/lib/date";

interface PriorityPanelProps {
  todos: Todo[];
  pmNames: Record<string, string>;
}

const PRIORITY_RANK: Record<string, number> = { URGENT: 0, HIGH: 1, NORMAL: 2 };

/**
 * Top-5 "most important right now" panel.
 *
 * Score: lower = more urgent.
 *   priority_rank × 100 + (days_overdue when negative)
 *
 *   URGENT overdue → 0 + days_overdue  (most negative ⇒ first)
 *   URGENT future  → 0
 *   HIGH overdue   → 100 + days_overdue
 *   HIGH future    → 100
 *   NORMAL         → 200
 */
export function PriorityPanel({ todos, pmNames }: PriorityPanelProps) {
  if (todos.length === 0) return null;
  const scored = todos
    .map((t) => {
      const base = PRIORITY_RANK[t.priority ?? "NORMAL"] ?? 2;
      const d = daysFromToday(t.due_date);
      const overdueBoost = d != null && d < 0 ? d : 0;
      return { t, score: base * 100 + overdueBoost };
    })
    .sort((a, b) => a.score - b.score)
    .slice(0, 5);

  return (
    <section className="border-b border-rule bg-paper">
      <header className="px-5 py-3 border-b border-rule flex items-baseline justify-between">
        <h2 className="font-head text-sm font-semibold uppercase tracking-[0.14em] text-ink">
          Top Priorities
        </h2>
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Right now
        </span>
      </header>
      <ol>
        {scored.map(({ t }, i) => {
          const d = daysFromToday(t.due_date);
          const overdue = d != null && d < 0;
          const pmShort = pmNames[t.pm_id]?.split(" ")[0] ?? t.pm_id;
          const title = t.edited_title ?? t.title;
          return (
            <li
              key={t.id}
              className="flex items-stretch border-b border-rule-soft last:border-b-0"
            >
              <span className="w-8 flex items-center justify-center font-mono text-[12px] tabular-nums text-ink-3 border-r border-rule-soft">
                {i + 1}
              </span>
              <div className="flex-1 min-w-0 px-4 py-2.5">
                <p className="text-[14px] leading-snug text-ink line-clamp-2">
                  {title}
                </p>
                <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-ink-3 tabular-nums">
                  <span>{pmShort}</span>
                  <span>·</span>
                  <span>{t.job}</span>
                  {t.due_date && (
                    <>
                      <span>·</span>
                      <span className={overdue ? "text-urgent" : ""}>
                        due {shortDate(t.due_date)}
                      </span>
                    </>
                  )}
                  {t.priority === "URGENT" && (
                    <span className="ml-auto text-urgent">URGENT</span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
