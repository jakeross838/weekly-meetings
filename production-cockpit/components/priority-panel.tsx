import { Todo } from "@/lib/types";
import { daysFromToday, shortDate } from "@/lib/date";

interface PriorityPanelProps {
  todos: Todo[];
  pmNames: Record<string, string>;
}

const PRIORITY_RANK: Record<string, number> = { URGENT: 0, HIGH: 1, NORMAL: 2 };

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
      <h2 className="px-5 pt-5 pb-3 font-head text-xl font-semibold text-ink">
        Top Priorities
      </h2>
      <ol className="pb-3">
        {scored.map(({ t }, i) => {
          const d = daysFromToday(t.due_date);
          const overdue = d != null && d < 0;
          const pmShort = pmNames[t.pm_id]?.split(" ")[0] ?? t.pm_id;
          const title = t.edited_title ?? t.title;
          return (
            <li
              key={t.id}
              className="flex items-start gap-3 px-5 py-3 border-t border-rule-soft"
            >
              <span className="shrink-0 mt-0.5 inline-flex items-center justify-center w-6 h-6 font-mono text-[12px] tabular-nums text-ink-2 bg-sand-2 rounded-full">
                {i + 1}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-[16px] leading-snug text-ink">{title}</p>
                <p className="mt-1 font-mono text-[11px] text-ink-3 tabular-nums">
                  {pmShort} · {t.job}
                  {t.due_date && (
                    <span className={overdue ? " text-urgent" : ""}>
                      {" "}
                      · due {shortDate(t.due_date)}
                    </span>
                  )}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
