"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

interface UndoButtonProps {
  todoId: string;
  /** Hide after N hours since completion (default 24). 0 = never hide. */
  windowHours?: number;
  completedAt: string | null;
}

export function UndoButton({
  todoId,
  windowHours = 24,
  completedAt,
}: UndoButtonProps) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [done, setDone] = useState(false);

  if (windowHours > 0 && completedAt) {
    const elapsedHours =
      (Date.now() - new Date(completedAt).getTime()) / 36e5;
    if (elapsedHours > windowHours) return null;
  }
  if (done) return null;

  async function undo() {
    if (pending) return;
    try {
      const res = await fetch("/api/uncomplete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: todoId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDone(true);
      start(() => router.refresh());
    } catch (err) {
      alert(`Undo failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        undo();
      }}
      disabled={pending}
      className="font-mono text-[12px] tracking-[0.15em] uppercase text-ink-2 hover:text-ink disabled:opacity-50 px-2 py-1"
    >
      Undo
    </button>
  );
}
