"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface Job {
  id: string;
  name: string | null;
  address: string | null;
  pm_id: string | null;
  status: string | null;
}
interface PM {
  id: string;
  full_name: string;
}

export function JobsAdminClient({ jobs, pms }: { jobs: Job[]; pms: PM[] }) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function patch(id: string, patch: Partial<Job>) {
    setBusyId(id);
    setError(null);
    try {
      const r = await fetch("/api/admin/jobs", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...patch }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) {
        setError(j.error ?? `HTTP ${r.status}`);
      } else {
        router.refresh();
      }
    } finally {
      setBusyId(null);
    }
  }

  async function remove(id: string, name: string | null) {
    const ok = confirm(
      `Remove "${name ?? id}"?\n\n` +
        "This removes the job row. Existing purchase orders, daily logs, " +
        "todos, and pay-app rows for this job will stay in the DB but no " +
        "longer surface in the cockpit. This is hard to undo."
    );
    if (!ok) return;
    setBusyId(id);
    setError(null);
    try {
      const r = await fetch(`/api/admin/jobs?id=${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) {
        setError(j.error ?? `HTTP ${r.status}`);
      } else {
        router.refresh();
      }
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="px-5 pt-6 space-y-6">
      {error && (
        <p
          role="alert"
          className="border border-urgent/40 bg-urgent/5 px-3 py-2 text-xs text-urgent"
        >
          {error}
        </p>
      )}

      <ul className="space-y-3">
        {jobs.map((j) => (
          <JobRow
            key={j.id}
            job={j}
            pms={pms}
            busy={busyId === j.id}
            onPatch={(p) => patch(j.id, p)}
            onRemove={() => remove(j.id, j.name)}
          />
        ))}
      </ul>

      <AddJobForm pms={pms} onAdded={() => router.refresh()} />
    </div>
  );
}

function JobRow({
  job,
  pms,
  busy,
  onPatch,
  onRemove,
}: {
  job: Job;
  pms: PM[];
  busy: boolean;
  onPatch: (p: Partial<Job>) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(job.name ?? "");
  const [address, setAddress] = useState(job.address ?? "");
  const [pmId, setPmId] = useState(job.pm_id ?? "");

  function save() {
    onPatch({ name, address, pm_id: pmId || null });
    setEditing(false);
  }

  if (!editing) {
    return (
      <li className="border border-rule p-4">
        <div className="flex items-baseline justify-between gap-3">
          <div className="min-w-0">
            <p className="font-head text-[15px] text-foreground">
              {job.name ?? job.id}
            </p>
            <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
              {job.id}
              {job.pm_id ? ` · PM: ${job.pm_id}` : " · no PM"}
              {job.address ? ` · ${job.address}` : ""}
            </p>
          </div>
          <div className="shrink-0 flex items-center gap-3">
            <button
              type="button"
              onClick={() => setEditing(true)}
              disabled={busy}
              className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3 hover:text-ink transition-colors"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={onRemove}
              disabled={busy}
              className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3 hover:text-urgent transition-colors"
            >
              Remove
            </button>
          </div>
        </div>
      </li>
    );
  }

  return (
    <li className="border border-accent p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
        editing {job.id}
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Name
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
          />
        </label>
        <label className="block">
          <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Address
          </span>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
          />
        </label>
      </div>
      <label className="block mt-3">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          PM
        </span>
        <select
          value={pmId}
          onChange={(e) => setPmId(e.target.value)}
          className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
        >
          <option value="">— none —</option>
          {pms.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name} ({p.id})
            </option>
          ))}
        </select>
      </label>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={save}
          disabled={busy}
          className="bg-ink px-3 py-2 font-head text-sm text-paper transition hover:bg-accent disabled:opacity-60"
        >
          {busy ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          disabled={busy}
          className="border border-rule px-3 py-2 font-head text-sm text-ink-2 hover:bg-oceanside/30 transition-colors"
        >
          Cancel
        </button>
      </div>
    </li>
  );
}

function AddJobForm({ pms, onAdded }: { pms: PM[]; onAdded: () => void }) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [pmId, setPmId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/admin/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id,
          name,
          address: address || null,
          pm_id: pmId || null,
        }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) {
        setError(j.error ?? `HTTP ${r.status}`);
        return;
      }
      setId("");
      setName("");
      setAddress("");
      setPmId("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="border border-rule p-4 mt-2">
      <h2 className="font-head text-[15px] text-foreground">Add a job</h2>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Id (slug)
          </span>
          <input
            required
            value={id}
            onChange={(e) => setId(e.target.value.toLowerCase())}
            placeholder="newjob"
            pattern="[a-z0-9][a-z0-9_-]*"
            className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
          />
        </label>
        <label className="block">
          <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Display name
          </span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New Job"
            className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
          />
        </label>
      </div>

      <label className="block mt-3">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Address
        </span>
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="123 Some St"
          className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
        />
      </label>

      <label className="block mt-3">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          PM
        </span>
        <select
          value={pmId}
          onChange={(e) => setPmId(e.target.value)}
          className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
        >
          <option value="">— none —</option>
          {pms.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name} ({p.id})
            </option>
          ))}
        </select>
      </label>

      {error && (
        <p
          role="alert"
          className="mt-3 border border-urgent/40 bg-urgent/5 px-3 py-2 text-xs text-urgent"
        >
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy}
        className="mt-4 bg-ink px-4 py-2.5 font-head text-sm text-paper transition hover:bg-accent disabled:opacity-60"
      >
        {busy ? "Adding…" : "Add job"}
      </button>
    </form>
  );
}
