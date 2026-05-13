"use client";

import { useState } from "react";
import { Todo } from "@/lib/types";
import { UndoButton } from "./undo-button";

interface CompletedSectionProps {
  todos: Todo[];
  pmNames: Record<string, string>;
}

export function CompletedSection({ todos, pmNames }: CompletedSectionProps) {
  const [open, setOpen] = useState(false);

  if (todos.length === 0) return null;

  return (
    <section
      className="border-t border-rule mt-6 rise"
      style={{ animationDelay: "260ms" }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-5 py-3 bg-sand-2/50 border-b border-rule"
      >
        <div className="flex items-baseline gap-3 min-w-0">
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            {open ? "▾" : "▸"}
          </span>
          <span className="font-head text-sm font-semibold uppercase tracking-[0.14em] text-ink-2 truncate">
            Recently Completed
          </span>
          <span className="font-mono text-[10px] tracking-[0.12em] text-ink-3 truncate hidden sm:inline">
            last 7 days
          </span>
        </div>
        <span className="font-mono text-[11px] tabular-nums text-ink-3">
          {String(todos.length).padStart(2, "0")}
        </span>
      </button>

      {open && (
        <ul>
          {todos.map((t) => {
            const completedShort = t.completed_at
              ? new Date(t.completed_at).toLocaleDateString("en-US", {
                  month: "numeric",
                  day: "numeric",
                })
              : "";
            const pmShort = pmNames[t.pm_id]?.split(" ")[0] ?? t.pm_id;
            return (
              <li
                key={t.id}
                className="flex items-start gap-3 px-5 py-2.5 border-b border-rule-soft bg-paper/30"
              >
                <span
                  className="mt-1 inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center border border-success/60 text-success"
                  aria-hidden
                >
                  <svg viewBox="0 0 12 12" fill="none" className="h-2.5 w-2.5">
                    <path
                      d="M2 6.5L4.5 9L10 3"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="square"
                      strokeLinejoin="miter"
                    />
                  </svg>
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] leading-snug text-ink-3 line-through line-clamp-2">
                    {t.edited_title ?? t.title}
                  </p>
                  <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-ink-3 tabular-nums">
                    <span>{t.id}</span>
                    <span>·</span>
                    <span>{pmShort}</span>
                    <span>·</span>
                    <span>{t.job}</span>
                    {completedShort && (
                      <>
                        <span>·</span>
                        <span className="text-success">done {completedShort}</span>
                      </>
                    )}
                    <span className="ml-auto">
                      <UndoButton todoId={t.id} completedAt={t.completed_at} />
                    </span>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
