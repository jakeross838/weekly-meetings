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
}: PMSectionProps) {
  const [open, setOpen] = useState(true);
  if (todos.length === 0) return null;

  const jobs = Array.from(new Set(todos.map((t) => t.job))).sort();
  const urgentCount = todos.filter((t) => t.priority === "URGENT").length;

  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 bg-muted/40 border-b border-rule"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[12px] text-ink-3">
            {open ? "▾" : "▸"}
          </span>
          <span className="font-head text-lg font-semibold text-ink truncate">
            {pmFullName.split(" ")[0]}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0 font-mono text-[13px] tabular-nums">
          {urgentCount > 0 && (
            <span className="text-urgent">{urgentCount} urgent</span>
          )}
          <span className="text-ink-2">{todos.length} open</span>
        </div>
      </button>
      {open && (
        <>
          {/* Per-job status — simple bullet list */}
          {allowComplete && jobs.length > 0 && (
            <div className="border-b border-rule-soft bg-sand-2/40 px-5 py-3">
              <ul className="flex flex-wrap gap-x-5 gap-y-1.5">
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
                    <li
                      key={j}
                      className="flex items-center gap-2 text-[13px] text-ink-2"
                      title={status.reasons.join(" · ")}
                    >
                      <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} aria-hidden />
                      <span>{j}</span>
                      <span className="font-mono text-[11px] text-ink-3 tabular-nums">
                        {jobTodos.length}
                      </span>
                    </li>
                  );
                })}
              </ul>
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
