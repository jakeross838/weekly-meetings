"use client";

// Clickable category pill that opens a small dropdown inline (no modal).
// Click target stops propagation so the surrounding row's full-edit modal
// does not also open.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CATEGORIES, styleFor } from "@/lib/categories";

interface Props {
  id: string;
  source: "item" | "todo";
  category: string | null;
}

export function CategoryPillEdit({ id, source, category }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const [value, setValue] = useState<string | null>(category);
  const ref = useRef<HTMLDivElement | null>(null);

  // Open upward when the pill sits low in the viewport, so the (up-to-280px)
  // menu never spills off the bottom of the screen.
  function toggle() {
    setOpen((o) => {
      if (!o && ref.current) {
        const rect = ref.current.getBoundingClientRect();
        setDropUp(window.innerHeight - rect.bottom < 300);
      }
      return !o;
    });
  }

  useEffect(() => setValue(category), [category]);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function pick(next: string | null) {
    if (next === value) {
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      const url =
        source === "item" ? `/v2/api/items/${id}/edit` : `/api/edit-todo`;
      const body =
        source === "item"
          ? { category: next }
          : { id, category: next };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setValue(next);
        router.refresh();
      }
    } finally {
      setBusy(false);
      setOpen(false);
    }
  }

  return (
    <div
      ref={ref}
      className="relative inline-block"
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          toggle();
        }}
        disabled={busy}
        className={`mt-1 inline-block font-mono text-[9px] tracking-[0.12em] px-1.5 py-0.5 hover:ring-1 hover:ring-ink/30 transition ${styleFor(value)} ${busy ? "opacity-50" : ""}`}
        aria-label="Change category"
      >
        {value ?? "+ category"}
      </button>
      {open && (
        <div
          className={`absolute z-10 left-0 bg-paper border border-rule shadow-lg min-w-[140px] max-h-[280px] overflow-y-auto ${
            dropUp ? "bottom-full mb-1" : "top-full mt-1"
          }`}
          role="menu"
        >
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              pick(null);
            }}
            className="block w-full text-left px-3 py-1.5 text-xs text-ink-3 hover:bg-sand-2"
          >
            — none —
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                pick(c);
              }}
              className={`block w-full text-left px-3 py-1.5 text-xs font-mono tracking-[0.12em] hover:bg-sand-2 ${
                value === c ? "bg-sand-2 text-ink" : "text-ink-2"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
