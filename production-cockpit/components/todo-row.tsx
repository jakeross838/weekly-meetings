"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Todo } from "@/lib/types";
import { shortDate, relativeOffset, daysFromToday } from "@/lib/date";
import { EditTodo } from "./edit-todo";
import { UndoButton } from "./undo-button";

const ACCENT_BAR: Record<string, string> = {
  URGENT: "bg-urgent",
  HIGH: "bg-high",
  NORMAL: "bg-rule",
};

export function TodoRow({
  todo,
  allowComplete,
}: {
  todo: Todo;
  allowComplete: boolean;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [striking, setStriking] = useState(false);
  const [done, setDone] = useState(false);

  async function complete() {
    if (!allowComplete || pending || striking || done) return;
    setStriking(true);
    try {
      const res = await fetch("/api/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: todo.id }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTimeout(() => {
        setDone(true);
        start(() => router.refresh());
      }, 220);
    } catch (err) {
      setStriking(false);
      alert(
        `Failed to mark done: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }

  if (done) return null;

  const priority = (todo.priority ?? "NORMAL").toUpperCase();
  const bar = ACCENT_BAR[priority] ?? ACCENT_BAR.NORMAL;
  const daysOut = daysFromToday(todo.due_date);
  const isOverdue = allowComplete && daysOut !== null && daysOut < 0;
  const displayTitle = todo.edited_title ?? todo.title;

  return (
    <div
      onClick={complete}
      role={allowComplete ? "button" : undefined}
      tabIndex={allowComplete ? 0 : undefined}
      aria-disabled={!allowComplete || pending}
      className={
        "group w-full flex items-stretch text-left transition-colors border-b border-rule " +
        (allowComplete && !pending ? "cursor-pointer active:bg-muted/60" : "") +
        (striking ? " strike-out" : "") +
        (!allowComplete || pending ? " opacity-70" : "")
      }
    >
      {/* Priority bar — 4px, full row height */}
      <span className={`w-1 shrink-0 ${bar}`} aria-hidden />

      <div className="flex-1 min-w-0 px-5 py-4">
        {/* Title — large, readable */}
        <p className="text-[17px] leading-snug text-ink">
          {displayTitle}
        </p>

        {/* Sub chip — quiet, only if linked */}
        {todo.sub && (
          <Link
            href={`/sub/${todo.sub.id}`}
            onClick={(e) => e.stopPropagation()}
            className="mt-2 inline-flex items-center gap-2 px-2 py-1 bg-paper border border-rule text-[12px] hover:border-ink transition-colors"
          >
            <span className="font-medium text-ink truncate max-w-[200px]">
              {todo.sub.name}
            </span>
            {todo.sub.rating != null && (
              <span className="font-mono text-[11px] text-high tabular-nums">
                {todo.sub.rating.toFixed(1)}★
              </span>
            )}
          </Link>
        )}

        {/* Meta row: job · due · priority tag · actions */}
        <div className="mt-2.5 flex items-center flex-wrap gap-x-3 gap-y-1.5 font-mono text-[12px] text-ink-3 tabular-nums">
          <span className="text-ink-2">{todo.job}</span>
          {todo.due_date && (
            <span className={isOverdue ? "text-urgent" : ""}>
              due {shortDate(todo.due_date)} · {relativeOffset(todo.due_date)}
            </span>
          )}
          {priority === "URGENT" && (
            <span className="uppercase tracking-[0.15em] text-urgent">
              Urgent
            </span>
          )}
          {priority === "HIGH" && (
            <span className="uppercase tracking-[0.15em] text-high">
              High
            </span>
          )}
          {todo.edited_at && (
            <span className="text-ink-3 italic">edited</span>
          )}
          <span
            className="ml-auto flex items-center gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <EditTodo todoId={todo.id} initialTitle={displayTitle} />
            {!allowComplete && todo.status === "COMPLETE" && (
              <UndoButton todoId={todo.id} completedAt={todo.completed_at} />
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
