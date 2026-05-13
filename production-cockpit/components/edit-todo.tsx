"use client";

import { useState, useTransition, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";

interface EditTodoProps {
  todoId: string;
  initialTitle: string;
}

export function EditTodo({ todoId, initialTitle }: EditTodoProps) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(initialTitle);
  const [pending, start] = useTransition();
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing && taRef.current) {
      taRef.current.focus();
      taRef.current.select();
    }
  }, [editing]);

  async function save() {
    if (!draft.trim() || draft.trim() === initialTitle) {
      setEditing(false);
      return;
    }
    try {
      const res = await fetch("/api/edit-todo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: todoId, title: draft.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setEditing(false);
      start(() => router.refresh());
    } catch (err) {
      alert(
        `Edit failed: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setEditing(true);
        }}
        aria-label="Edit todo"
        className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 hover:text-ink"
      >
        Edit
      </button>
    );
  }

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      className="mt-1 border border-ink bg-paper"
    >
      <textarea
        ref={taRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={3}
        maxLength={600}
        className="w-full px-3 py-2 text-[15px] leading-snug bg-paper text-ink resize-none focus:outline-none"
      />
      <div className="flex items-center justify-end gap-3 px-3 py-1.5 border-t border-rule">
        <button
          type="button"
          onClick={() => {
            setDraft(initialTitle);
            setEditing(false);
          }}
          className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 hover:text-ink"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          disabled={pending}
          className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink hover:text-success disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </div>
  );
}
