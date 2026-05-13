"use client";

import { useState } from "react";
import { Todo } from "@/lib/types";
import { TodoRow } from "./todo-row";

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
          <span className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground truncate hidden sm:inline">
            {jobs.join(" · ")}
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
        <div className="bg-paper">
          {todos.map((t) => (
            <TodoRow key={t.id} todo={t} allowComplete={allowComplete} />
          ))}
        </div>
      )}
    </section>
  );
}
