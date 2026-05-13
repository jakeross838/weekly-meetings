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

const STATUS_LABEL: Record<string, string> = {
  NOT_STARTED: "NEW",
  IN_PROGRESS: "WIP",
  BLOCKED: "BLK",
  COMPLETE: "DONE",
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
      {/* Priority bar — 3px, full row height */}
      <span className={`w-[3px] shrink-0 ${bar}`} aria-hidden />

      <div className="flex-1 min-w-0 px-4 py-3.5">
        {/* Meta row: ID · status · priority */}
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground">
            {todo.id}
          </span>
          <span className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground">
            ·
          </span>
          <span className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground">
            {STATUS_LABEL[todo.status] ?? todo.status}
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

        {/* Title — uses edited_title when present */}
        <p className="text-[15px] leading-snug text-foreground line-clamp-3">
          {displayTitle}
        </p>

        {/* Sub chip — tappable when the todo is linked to a known sub */}
        {todo.sub && (
          <Link
            href={`/sub/${todo.sub.id}`}
            onClick={(e) => e.stopPropagation()}
            className="mt-2 inline-flex items-center gap-1.5 px-1.5 py-0.5 bg-paper border border-rule text-[11px] hover:border-ink transition-colors"
          >
            <span className="font-medium text-ink truncate max-w-[180px]">
              {todo.sub.name}
            </span>
            {todo.sub.trade && (
              <>
                <span className="text-ink-3">·</span>
                <span className="font-mono text-[10px] text-ink-3 uppercase tracking-wide">
                  {todo.sub.trade}
                </span>
              </>
            )}
            {todo.sub.rating != null && (
              <span className="font-mono text-[10px] text-high tabular-nums ml-0.5">
                {todo.sub.rating.toFixed(1)}★
              </span>
            )}
          </Link>
        )}

        {/* Footer: job · due date · relative */}
        <div className="mt-2 flex items-center justify-between gap-3 font-mono text-[11px] text-muted-foreground tabular-nums">
          <span className="truncate">{todo.job}</span>
          {todo.due_date && (
            <span className={isOverdue ? "text-urgent" : ""}>
              {shortDate(todo.due_date)} · {relativeOffset(todo.due_date)}
            </span>
          )}
        </div>

        {/* Actions: Edit (always) + Undo (Done view only) + edited tag */}
        <div
          className="mt-2 flex items-center gap-3"
          onClick={(e) => e.stopPropagation()}
        >
          <EditTodo todoId={todo.id} initialTitle={displayTitle} />
          {!allowComplete && todo.status === "COMPLETE" && (
            <UndoButton todoId={todo.id} completedAt={todo.completed_at} />
          )}
          {todo.edited_at && (
            <span className="font-mono text-[10px] tracking-[0.12em] text-ink-3 ml-auto">
              edited
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
