"use client";

// Manual-specialty editor for a sub. Client-only because it triggers
// add/remove/duration-override API calls + router.refresh.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmModal } from "@/components/confirm-modal";

export interface SpecialtyRow {
  name: string;
  source: "auto" | "manual";
  days: number;
  jobs: number;
  // Simple average: total on-site days summed across jobs, divided by job
  // count. Easier to explain than the streak-mean we used previously.
  avgDurationDays: number | null;
  // Operator-entered duration; takes precedence over avgDurationDays when set.
  manualDurationDays: number | null;
  peers: { name: string; days: number }[];
  // Per-job breakdown that powers the citation line under each row.
  jobBreakdown: { jobKey: string; jobName: string; days: number }[];
  // F3 — avg crew size when this sub was on site on logs tagged with this
  // activity. Null = no per-crew headcount available (pre-migration data).
  avgCrewSize: number | null;
  // F5 — canonical schedule_items.name when this activity tag maps to one.
  // Renders alongside the raw tag so the operator sees both the BT label
  // and the comparable cross-sub label.
  canonicalName: string | null;
}

export function SpecialtiesEditor({
  subId,
  rows,
}: {
  subId: string;
  rows: SpecialtyRow[];
}) {
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Per-row duration draft (kept in client state until blur/Enter to commit)
  const [durationDrafts, setDurationDrafts] = useState<Record<string, string>>(
    {}
  );
  const [editingDuration, setEditingDuration] = useState<string | null>(null);
  const [pendingRemove, setPendingRemove] = useState<string | null>(null);

  async function add() {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/sub-specialties", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sub_id: subId,
          specialty: name,
          action: "add",
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setErr(body.error || `HTTP ${r.status}`);
        setBusy(false);
        return;
      }
      setNewName("");
      setAdding(false);
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(name: string): Promise<boolean> {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/sub-specialties", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sub_id: subId,
          specialty: name,
          action: "remove",
        }),
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

  async function saveDuration(name: string, raw: string) {
    setErr(null);
    const trimmed = raw.trim();
    // Empty string = clear the override
    let value: number | null = null;
    if (trimmed !== "") {
      const n = Number(trimmed);
      if (isNaN(n) || n < 0) {
        setErr(`"${trimmed}" isn't a valid duration`);
        return;
      }
      value = n;
    }
    setBusy(true);
    try {
      const r = await fetch("/api/sub-specialties", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sub_id: subId,
          specialty: name,
          action: "set_duration",
          duration_days: value,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setErr(body.error || `HTTP ${r.status}`);
      } else {
        setEditingDuration(null);
        router.refresh();
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function renderDuration(r: SpecialtyRow) {
    const display = r.manualDurationDays ?? r.avgDurationDays;
    const isManual = r.manualDurationDays != null;
    const draft = durationDrafts[r.name] ?? "";
    const isEditing = editingDuration === r.name;

    if (isEditing) {
      return (
        <input
          type="number"
          step="0.1"
          min="0"
          value={draft}
          onChange={(e) =>
            setDurationDrafts((s) => ({ ...s, [r.name]: e.target.value }))
          }
          onBlur={() => saveDuration(r.name, draft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              (e.target as HTMLInputElement).blur();
            }
            if (e.key === "Escape") {
              setEditingDuration(null);
            }
          }}
          autoFocus
          className="w-16 bg-paper border border-ink px-1 py-0.5 text-xs text-ink focus:outline-none tabular-nums"
          aria-label="Avg duration days"
        />
      );
    }
    return (
      <button
        type="button"
        onClick={() => {
          setDurationDrafts((s) => ({
            ...s,
            [r.name]: display != null ? display.toString() : "",
          }));
          setEditingDuration(r.name);
        }}
        className={
          "text-left text-xs font-mono tabular-nums hover:bg-sand-2 px-1 -mx-1 transition-colors " +
          (display == null
            ? "text-ink-3 hover:text-ink"
            : isManual
              ? "text-foreground"
              : "text-ink-3")
        }
        title={
          isManual
            ? "Manual override · click to edit"
            : display != null
              ? "Auto from daily logs · click to override"
              : "Click to set manually"
        }
      >
        {display == null
          ? "no data"
          : `${display.toFixed(1)}d/job`}
        {isManual && "*"}
      </button>
    );
  }

  return (
    <div>
      {rows.length === 0 ? (
        <p className="text-ink-3 text-sm py-2">
          No specialties tracked yet. Specialties auto-populate from daily
          logs (Buildertrend), or add one manually below.
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li
              key={r.name}
              className="py-2 border-b border-rule-soft last:border-b-0"
            >
              <div className="flex items-baseline justify-between gap-3">
                <div className="flex items-baseline gap-2 min-w-0 flex-1">
                  <span className="text-sm text-foreground truncate">
                    {r.name}
                  </span>
                  {r.canonicalName && r.canonicalName !== r.name && (
                    <span
                      className="font-mono text-[9px] tracking-[0.12em] uppercase text-accent"
                      title={`Canonical schedule item: ${r.canonicalName}`}
                    >
                      ≈ {r.canonicalName}
                    </span>
                  )}
                  {r.source === "manual" && r.days === 0 && (
                    <span className="font-mono text-[9px] tracking-[0.12em] uppercase text-ink-3">
                      declared
                    </span>
                  )}
                </div>
                <div className="shrink-0 flex items-baseline gap-3 font-mono text-xs tabular-nums text-ink-2">
                  {r.days > 0 && (
                    <span>
                      {r.days}d · {r.jobs} job{r.jobs === 1 ? "" : "s"}
                    </span>
                  )}
                  {r.avgCrewSize != null && (
                    <span
                      className="text-ink-3"
                      title="Avg crew size per BT daily log on this activity"
                    >
                      ~{r.avgCrewSize.toFixed(1)} crew
                    </span>
                  )}
                  {renderDuration(r)}
                  {r.source === "manual" && (
                    <button
                      type="button"
                      onClick={() => setPendingRemove(r.name)}
                      disabled={busy}
                      className="text-ink-3 hover:text-urgent text-xs"
                      aria-label={`Remove ${r.name}`}
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>
              {r.jobBreakdown.length > 0 && (
                <p className="mt-1 font-mono text-[10px] text-ink-3 tabular-nums">
                  sources:{" "}
                  {r.jobBreakdown
                    .map((j) => `${j.jobName} ${j.days}d`)
                    .join(" · ")}
                </p>
              )}
              {r.peers.length > 0 && (
                <p className="mt-0.5 font-mono text-[10px] text-ink-3 tabular-nums opacity-70">
                  peers:{" "}
                  {r.peers
                    .map((p) => `${p.name.split(" ")[0]} ${p.days}d`)
                    .join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 pt-3 border-t border-rule-soft">
        {!adding ? (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="text-xs text-accent hover:underline"
          >
            + Add specialty
          </button>
        ) : (
          <div className="flex gap-2 items-center">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. Exterior Paint"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") add();
                if (e.key === "Escape") {
                  setAdding(false);
                  setNewName("");
                }
              }}
              className="flex-1 bg-paper border border-rule px-2 py-1 text-sm text-ink focus:outline-none focus:border-ink"
            />
            <button
              type="button"
              onClick={add}
              disabled={busy || !newName.trim()}
              className="bg-ink text-paper px-3 py-1 text-xs disabled:opacity-50"
            >
              Add
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setNewName("");
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
      <ConfirmModal
        open={pendingRemove !== null}
        title="Confirm delete"
        subject={pendingRemove || "this specialty"}
        body={
          <div>
            <p>Remove this manual specialty? This can’t be undone.</p>
            {err && <p className="mt-2 text-urgent">{err}</p>}
          </div>
        }
        confirmLabel="Delete"
        tone="urgent"
        busy={busy}
        onCancel={() => setPendingRemove(null)}
        onConfirm={async () => {
          if (!pendingRemove) return;
          const ok = await remove(pendingRemove);
          if (ok) setPendingRemove(null);
        }}
      />
    </div>
  );
}
