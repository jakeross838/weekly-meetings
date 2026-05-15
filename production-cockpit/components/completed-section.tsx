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
    <section className="border-t border-rule mt-4">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-5 py-3.5 bg-sand-2/50 border-b border-rule"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[12px] text-ink-3">
            {open ? "▾" : "▸"}
          </span>
          <span className="font-head text-base font-semibold text-ink-2">
            Recently Done
          </span>
        </div>
        <span className="font-mono text-[13px] tabular-nums text-ink-2">
          {todos.length}
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
                className="flex items-start gap-3 px-5 py-3 border-b border-rule-soft"
              >
                <span
                  className="mt-1 inline-flex h-4 w-4 shrink-0 items-center justify-center text-success"
                  aria-hidden
                >
                  <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3">
                    <path
                      d="M2 6.5L4.5 9L10 3"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-[14px] leading-snug text-ink-3 line-through">
                    {t.edited_title ?? t.title}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-3 tabular-nums">
                    {pmShort} · {t.job}
                    {completedShort && (
                      <span className="text-success">
                        {" "}
                        · done {completedShort}
                      </span>
                    )}
                  </p>
                </div>
                <UndoButton todoId={t.id} completedAt={t.completed_at} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
