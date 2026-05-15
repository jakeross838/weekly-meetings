"use client";

import { useState } from "react";
import Link from "next/link";
import { Todo } from "@/lib/types";

interface PrereqHint {
  id: string;
  job: string;
  category: string | null;
  due_date: string | null;
  status: string;
  title: string;
  edited_title: string | null;
  priority: string | null;
}

interface ScheduleListProps {
  todos: Todo[];
  allOpen: PrereqHint[];
}

const PREREQ_CATEGORIES = new Set(["SELECTION", "PROCUREMENT"]);

function dayLabel(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  const todayIso = new Date().toISOString().slice(0, 10);
  const tomorrowIso = new Date(Date.now() + 86_400_000)
    .toISOString()
    .slice(0, 10);
  if (iso === todayIso) return "Today";
  if (iso === tomorrowIso) return "Tomorrow";
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${parseInt(m[2])}/${parseInt(m[3])}`;
}

export function ScheduleList({ todos, allOpen }: ScheduleListProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (todos.length === 0) {
    return (
      <div className="px-6 lg:px-10 py-20 text-center">
        <p className="font-head text-xl text-ink-3">
          Nothing due in this window
        </p>
      </div>
    );
  }

  // Group by due_date
  const byDate: Record<string, Todo[]> = {};
  for (const t of todos) {
    const d = t.due_date ?? "no-date";
    if (!byDate[d]) byDate[d] = [];
    byDate[d].push(t);
  }
  const dates = Object.keys(byDate).sort();

  return (
    <div className="pb-12">
      {dates.map((d) => (
        <section key={d} className="border-b border-rule">
          <header className="px-6 lg:px-10 py-3 bg-sand-2/50 flex items-baseline justify-between">
            <h2 className="font-head text-base font-semibold text-ink">
              {dayLabel(d)}
            </h2>
            <span className="font-mono text-[12px] text-ink-3 tabular-nums">
              {shortDate(d)} · {byDate[d].length} due
            </span>
          </header>
          <ul>
            {byDate[d].map((t) => {
              // Prerequisites: any OPEN selection/procurement on the same
              // job with due_date <= this todo's due_date.
              const prereqs = allOpen.filter(
                (p) =>
                  p.id !== t.id &&
                  p.job === t.job &&
                  PREREQ_CATEGORIES.has(p.category ?? "") &&
                  p.due_date &&
                  t.due_date &&
                  p.due_date <= t.due_date
              );
              const isOpen = !!expanded[t.id];
              const priority = (t.priority ?? "NORMAL").toUpperCase();
              const barColor =
                priority === "URGENT"
                  ? "bg-urgent"
                  : priority === "HIGH"
                    ? "bg-high"
                    : "bg-rule";
              return (
                <li
                  key={t.id}
                  className="border-b border-rule-soft last:border-b-0"
                >
                  <button
                    type="button"
                    onClick={() =>
                      setExpanded((s) => ({ ...s, [t.id]: !s[t.id] }))
                    }
                    className="w-full flex items-stretch text-left hover:bg-sand-2/30 transition-colors"
                  >
                    <span className={`w-1 shrink-0 ${barColor}`} aria-hidden />
                    <div className="flex-1 min-w-0 px-5 lg:px-8 py-3.5">
                      <div className="flex items-baseline justify-between gap-3">
                        <p className="text-[15px] font-medium text-ink">
                          {t.sub?.name ?? "No sub linked"}
                        </p>
                        <span className="font-mono text-[11px] text-ink-3 tabular-nums shrink-0">
                          {t.job}
                        </span>
                      </div>
                      <p className="mt-1 text-[14px] text-ink-2 line-clamp-2">
                        {t.edited_title ?? t.title}
                      </p>
                      <div className="mt-1.5 flex items-center gap-3 font-mono text-[11px] text-ink-3 tabular-nums">
                        {t.sub?.trade && (
                          <span className="uppercase tracking-wide">
                            {t.sub.trade}
                          </span>
                        )}
                        {prereqs.length > 0 && (
                          <span className="text-urgent uppercase tracking-wide">
                            {prereqs.length} prereq{prereqs.length === 1 ? "" : "s"}
                          </span>
                        )}
                        <span className="ml-auto">{isOpen ? "▴" : "▾"}</span>
                      </div>
                    </div>
                  </button>
                  {isOpen && (
                    <div className="px-5 lg:px-8 pl-6 lg:pl-9 pb-4 bg-paper border-t border-rule-soft">
                      {prereqs.length > 0 && (
                        <div className="mt-3">
                          <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-urgent mb-2">
                            Prerequisites · open
                          </p>
                          <ul className="space-y-1.5">
                            {prereqs.map((p) => (
                              <li
                                key={p.id}
                                className="text-[13px] text-ink-2 leading-snug"
                              >
                                <span className="font-mono text-[11px] text-ink-3 mr-2">
                                  {p.category}
                                </span>
                                {p.edited_title ?? p.title}
                                {p.due_date && (
                                  <span className="font-mono text-[11px] text-ink-3 ml-2">
                                    due {shortDate(p.due_date)}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <div className="mt-3 flex items-center gap-3">
                        {t.sub?.id && (
                          <Link
                            href={`/sub/${t.sub.id}`}
                            className="text-[12px] tracking-[0.15em] uppercase text-accent hover:text-ink"
                          >
                            Sub profile →
                          </Link>
                        )}
                        <Link
                          href={`/?pm=${t.pm_id}`}
                          className="text-[12px] tracking-[0.15em] uppercase text-ink-2 hover:text-ink"
                        >
                          Open in todos
                        </Link>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
