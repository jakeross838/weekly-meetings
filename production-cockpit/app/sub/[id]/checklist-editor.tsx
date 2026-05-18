"use client";

// F7 — running checklist for a sub, split into two lenses (safety / schedule).
// Server passes items already split per lens. All mutations go through one
// POST endpoint (/api/sub-checklist) for simplicity; each mutation triggers
// a router.refresh() so the server-rendered counts re-derive.

import { useState } from "react";
import { useRouter } from "next/navigation";

export type ChecklistLens = "SAFETY" | "SCHEDULE";

export interface ChecklistItem {
  id: string;
  lens: ChecklistLens;
  item_text: string;
  is_done: boolean;
  done_at: string | null;
  done_by: string | null;
  notes: string | null;
  position: number;
}

const LENS_LABEL: Record<ChecklistLens, string> = {
  SAFETY: "Safety",
  SCHEDULE: "Schedule",
};

const LENS_HINT: Record<ChecklistLens, string> = {
  SAFETY: "PPE, insurance current, hot-work plan, fall protection…",
  SCHEDULE: "Start date confirmed, materials on site, sequencing OK…",
};

export function SubChecklistEditor({
  subId,
  safetyItems,
  scheduleItems,
}: {
  subId: string;
  safetyItems: ChecklistItem[];
  scheduleItems: ChecklistItem[];
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <ChecklistColumn subId={subId} lens="SAFETY" items={safetyItems} />
      <ChecklistColumn subId={subId} lens="SCHEDULE" items={scheduleItems} />
    </div>
  );
}

function ChecklistColumn({
  subId,
  lens,
  items,
}: {
  subId: string;
  lens: ChecklistLens;
  items: ChecklistItem[];
}) {
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [newText, setNewText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  async function call(body: Record<string, unknown>) {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/sub-checklist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sub_id: subId, ...body }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setErr(body.error || `HTTP ${r.status}`);
        return false;
      }
      router.refresh();
      return true;
    } catch (e) {
      setErr((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    const text = newText.trim();
    if (!text) return;
    const ok = await call({
      action: "add",
      lens,
      item_text: text,
    });
    if (ok) {
      setNewText("");
      setAdding(false);
    }
  }

  async function toggle(item: ChecklistItem) {
    await call({
      action: "toggle",
      item_id: item.id,
      is_done: !item.is_done,
    });
  }

  async function remove(item: ChecklistItem) {
    await call({ action: "remove", item_id: item.id });
  }

  async function saveEdit(item: ChecklistItem) {
    const t = editText.trim();
    if (!t || t === item.item_text) {
      setEditingId(null);
      return;
    }
    const ok = await call({
      action: "edit",
      item_id: item.id,
      item_text: t,
    });
    if (ok) setEditingId(null);
  }

  const doneCount = items.filter((i) => i.is_done).length;

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="font-head text-sm font-semibold text-foreground">
          {LENS_LABEL[lens]}
        </h3>
        <span className="font-mono text-[10px] tabular-nums text-ink-3">
          {doneCount}/{items.length}
        </span>
      </div>
      {items.length === 0 ? (
        <p className="text-ink-3 text-xs italic leading-relaxed">
          No items yet. Add one below — e.g. {LENS_HINT[lens]}
        </p>
      ) : (
        <ul className="space-y-1">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-start gap-2 py-1.5 border-b border-rule-soft last:border-b-0"
            >
              <input
                type="checkbox"
                checked={item.is_done}
                onChange={() => toggle(item)}
                disabled={busy}
                className="mt-0.5 h-4 w-4 accent-accent shrink-0"
                aria-label={`Mark ${item.item_text} ${
                  item.is_done ? "not done" : "done"
                }`}
              />
              <div className="flex-1 min-w-0">
                {editingId === item.id ? (
                  <input
                    type="text"
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onBlur={() => saveEdit(item)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        (e.target as HTMLInputElement).blur();
                      }
                      if (e.key === "Escape") {
                        setEditingId(null);
                      }
                    }}
                    autoFocus
                    className="w-full bg-paper border-b border-ink px-0 py-0 text-sm text-ink focus:outline-none"
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setEditingId(item.id);
                      setEditText(item.item_text);
                    }}
                    className={`text-left text-sm leading-snug ${
                      item.is_done
                        ? "text-ink-3 line-through"
                        : "text-foreground hover:text-accent"
                    }`}
                  >
                    {item.item_text}
                  </button>
                )}
                {item.is_done && item.done_at && (
                  <p className="font-mono text-[9px] tracking-[0.12em] uppercase text-ink-3 mt-0.5">
                    done {item.done_at.slice(0, 10)}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => remove(item)}
                disabled={busy}
                className="text-ink-3 hover:text-urgent text-xs shrink-0"
                aria-label={`Remove ${item.item_text}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 pt-2 border-t border-rule-soft">
        {!adding ? (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="text-xs text-accent hover:underline"
          >
            + Add {LENS_LABEL[lens].toLowerCase()} item
          </button>
        ) : (
          <div className="flex gap-2 items-center">
            <input
              type="text"
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              placeholder={LENS_HINT[lens]}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") add();
                if (e.key === "Escape") {
                  setAdding(false);
                  setNewText("");
                }
              }}
              className="flex-1 bg-paper border border-rule px-2 py-1 text-sm text-ink focus:outline-none focus:border-ink"
            />
            <button
              type="button"
              onClick={add}
              disabled={busy || !newText.trim()}
              className="bg-ink text-paper px-3 py-1 text-xs disabled:opacity-50"
            >
              Add
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setNewText("");
                setErr(null);
              }}
              className="text-xs text-ink-3 hover:text-ink"
            >
              Cancel
            </button>
          </div>
        )}
        {err && <p className="mt-2 text-xs text-urgent">{err}</p>}
      </div>
    </div>
  );
}
