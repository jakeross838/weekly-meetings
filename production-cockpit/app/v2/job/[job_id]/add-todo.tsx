"use client";

// "+ Add to-do" affordance for /v2/job/[job_id]. Opens a modal to hand-create a
// to-do on this job, POSTing to /api/todos/create (which scrubs relative dates
// and marks the row source="manual"). Visually mirrors EditRowModal so create
// and edit feel identical.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CATEGORIES } from "@/lib/categories";
import { ModalPortal } from "@/components/modal-portal";
import { SubOpt } from "./edit-row";

const PRIORITIES = ["NORMAL", "HIGH", "URGENT"] as const;

export function AddTodoButton({
  jobId,
  subs,
}: {
  jobId: string;
  subs: SubOpt[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [subId, setSubId] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState<string>("NORMAL");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function close() {
    setOpen(false);
    setTitle("");
    setDueDate("");
    setSubId("");
    setCategory("");
    setPriority("NORMAL");
    setErr(null);
  }

  // Esc to close (ignored while a save is in flight).
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) close();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy]);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/todos/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: jobId,
          title,
          due_date: dueDate || null,
          sub_id: subId || null,
          category: category || null,
          priority,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setErr(data.error || `HTTP ${res.status}`);
        setBusy(false);
        return;
      }
      router.refresh();
      close();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full border border-dashed border-rule px-4 py-2.5 text-sm font-medium text-ink-2 hover:border-ink hover:text-ink hover:bg-oceanside/20 transition-colors"
      >
        + Add to-do
      </button>

      {open && (
        <ModalPortal>
          <div
            className="fixed inset-0 z-50 bg-ink/40 flex items-end sm:items-center justify-center"
            onClick={() => {
              if (!busy) close();
            }}
          >
            <div
              className="bg-paper w-full sm:max-w-md sm:rounded sm:my-8 p-5 max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-baseline justify-between mb-4">
                <h2 className="font-head text-lg text-foreground">Add to-do</h2>
                <button
                  type="button"
                  onClick={close}
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
                    autoFocus
                    placeholder="What needs to happen?"
                    className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink resize-none"
                  />
                  <p className="mt-1 text-[10px] text-ink-3 leading-snug">
                    Use an exact date (e.g. 2026-06-30) or none — vague
                    timeframes (&ldquo;ASAP&rdquo;, &ldquo;next week&rdquo;) are
                    stripped automatically.
                  </p>
                </div>

                <div>
                  <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
                    Due
                  </label>
                  <input
                    type="date"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
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
                        {s.trade ? `${s.name} — ${s.trade}` : s.name}
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
                    <option value="">— ADMIN (default) —</option>
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
                    Priority
                  </label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                    className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p} value={p}>
                        {p}
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
                    {busy ? "Adding…" : "Add to-do"}
                  </button>
                  <button
                    type="button"
                    onClick={close}
                    className="px-4 py-2.5 text-sm text-ink-2 hover:text-ink"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </ModalPortal>
      )}
    </>
  );
}
