"use client";

// Edit popup for a single row on /v2/job. Click the row → modal opens.
// Save hits the right endpoint based on source ("item" | "todo").

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const CATEGORIES = [
  "SCHEDULE",
  "QUALITY",
  "PROCUREMENT",
  "SELECTION",
  "BUDGET",
  "CLIENT",
  "ADMIN",
  "SUB-TRADE",
];

export interface SubOpt {
  id: string;
  name: string;
}

export interface RowEditValues {
  title: string;
  target_date: string | null; // yyyy-mm-dd
  sub_id: string | null;
  category: string | null;
}

interface EditRowModalProps {
  open: boolean;
  onClose: () => void;
  source: "item" | "todo";
  id: string;
  initial: RowEditValues;
  subs: SubOpt[];
}

export function EditRowModal({
  open,
  onClose,
  source,
  id,
  initial,
  subs,
}: EditRowModalProps) {
  const router = useRouter();
  const [title, setTitle] = useState(initial.title);
  const [targetDate, setTargetDate] = useState(initial.target_date ?? "");
  const [subId, setSubId] = useState(initial.sub_id ?? "");
  const [category, setCategory] = useState(initial.category ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTitle(initial.title);
      setTargetDate(initial.target_date ?? "");
      setSubId(initial.sub_id ?? "");
      setCategory(initial.category ?? "");
      setErr(null);
    }
  }, [open, initial]);

  // Esc to close
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const url =
        source === "item"
          ? `/v2/api/items/${id}/edit`
          : `/api/edit-todo`;
      const body: Record<string, unknown> =
        source === "item"
          ? {
              title,
              target_date: targetDate || null,
              sub_id: subId || null,
              category: category || null,
            }
          : {
              id,
              title,
              due_date: targetDate || null,
              sub_id: subId || null,
              category: category || null,
            };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as {
          error?: string;
        };
        setErr(data.error || `HTTP ${res.status}`);
        setBusy(false);
        return;
      }
      router.refresh();
      onClose();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center"
      onClick={onClose}
    >
      <div
        className="bg-paper w-full sm:max-w-md sm:rounded sm:my-8 p-5 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="font-head text-lg text-foreground">Edit item</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-3 hover:text-ink text-sm"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
              Title
            </label>
            <textarea
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              rows={3}
              className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink resize-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
              Due
            </label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
            />
          </div>

          <div>
            <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
              Sub
            </label>
            <select
              value={subId}
              onChange={(e) => setSubId(e.target.value)}
              className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
            >
              <option value="">— none —</option>
              {subs.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
              Category
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
            >
              <option value="">— none —</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {err && <p className="text-xs text-urgent">{err}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={save}
              disabled={busy || !title.trim()}
              className="flex-1 bg-ink text-paper px-4 py-2.5 text-sm font-medium disabled:opacity-50 hover:bg-accent transition-colors"
            >
              {busy ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 text-sm text-ink-2 hover:text-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
