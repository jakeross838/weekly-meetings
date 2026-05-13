"use client";

import { useState } from "react";
import { Todo } from "@/lib/types";
import { TodoRow } from "./todo-row";
import { computeJobStatus } from "@/lib/job-status";

interface PMSectionProps {
  pmFullName: string;
  todos: Todo[];
  allowComplete: boolean;
  index?: number;
}

export function PMSection({
  pmFullName,
  todos,
  allowComplete,
  index = 0,
}: PMSectionProps) {
  const [open, setOpen] = useState(true);
  if (todos.length === 0) return null;

  const jobs = Array.from(new Set(todos.map((t) => t.job))).sort();
  const urgentCount = todos.filter((t) => t.priority === "URGENT").length;

  return (
    <section
      className="rise"
      style={{ animationDelay: `${180 + index * 50}ms` }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-5 py-3 bg-muted/40 border-b border-rule"
      >
        <div className="flex items-baseline gap-3 min-w-0">
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-muted-foreground">
            {open ? "▾" : "▸"}
          </span>
          <span className="font-head text-sm font-semibold uppercase tracking-[0.14em] truncate text-ink">
            {pmFullName}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0 font-mono text-[11px] tabular-nums">
          {urgentCount > 0 && (
            <span className="text-urgent">{urgentCount} urg</span>
          )}
          <span className="text-muted-foreground">
            {String(todos.length).padStart(2, "0")}
          </span>
        </div>
      </button>
      {open && (
        <>
          {/* Per-job traffic-light row: a dot + job name + count */}
          {allowComplete && jobs.length > 0 && (
            <div className="border-b border-rule-soft bg-sand-2/30 px-5 py-2 flex flex-wrap items-center gap-x-3 gap-y-1">
              {jobs.map((j) => {
                const jobTodos = todos.filter((t) => t.job === j);
                const status = computeJobStatus(jobTodos);
                const dotClass =
                  status.status === "red"
                    ? "bg-urgent"
                    : status.status === "amber"
                      ? "bg-high"
                      : "bg-success";
                return (
                  <span
                    key={j}
                    className="inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-2 tabular-nums"
                    title={status.reasons.join(" · ")}
                  >
                    <span className={`h-2 w-2 ${dotClass}`} aria-hidden />
                    <span>{j}</span>
                    <span className="text-ink-3">{jobTodos.length}</span>
                  </span>
                );
              })}
            </div>
          )}
          <div className="bg-paper">
            {todos.map((t) => (
              <TodoRow key={t.id} todo={t} allowComplete={allowComplete} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
