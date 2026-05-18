"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

// Polymorphic toggle. `source="item"` hits the v2 items API; `source="todo"`
// hits the v1 todos API. Same UX, different backend.
export function CheckOffButton({
  itemId,
  completed = false,
  source = "item",
}: {
  itemId: string;
  completed?: boolean;
  source?: "item" | "todo";
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [optimistic, setOptimistic] = useState(completed);

  async function toggle() {
    if (busy) return;
    const next = !optimistic;
    setOptimistic(next);
    setBusy(true);
    try {
      let url: string;
      let body: string | undefined;
      if (source === "item") {
        const path = next ? "complete" : "uncomplete";
        url = `/v2/api/items/${itemId}/${path}`;
        body = next ? JSON.stringify({ completion_basis: "manual" }) : undefined;
      } else {
        const path = next ? "complete" : "uncomplete";
        url = `/api/${path}`;
        body = JSON.stringify({ id: itemId });
      }
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      if (!res.ok) {
        setOptimistic(!next);
      } else {
        router.refresh();
      }
    } catch {
      setOptimistic(!next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={busy}
      aria-label={optimistic ? "Mark not done" : "Mark done"}
      aria-pressed={optimistic}
      className={
        "mt-0.5 inline-flex items-center justify-center w-4 h-4 border shrink-0 transition-colors disabled:opacity-50 " +
        (optimistic
          ? "border-success bg-success/30 hover:bg-success/10"
          : "border-rule hover:border-ink hover:bg-success/20")
      }
    >
      {optimistic && (
        <svg
          viewBox="0 0 12 12"
          className="w-3 h-3 text-success"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="2.5 6.5 5 9 9.5 3.5" />
        </svg>
      )}
    </button>
  );
}
