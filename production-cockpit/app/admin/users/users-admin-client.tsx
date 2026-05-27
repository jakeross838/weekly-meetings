"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@/lib/auth-users";

interface JobOpt {
  id: string;
  name: string;
  pm_id: string | null;
}
interface PmOpt {
  id: string;
  full_name: string;
}

export function UsersAdminClient({
  users,
  jobs,
  pms,
}: {
  users: User[];
  jobs: JobOpt[];
  pms: PmOpt[];
}) {
  const router = useRouter();
  const [busyEmail, setBusyEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Toggle assigns / unassigns `jobs.pm_id` for that user's pmId. Clicking a
  // job that already belongs to this PM → unassign (pm_id=null). Clicking a
  // job belonging to a different PM → reassign to this one (the other PM
  // loses it). This is the single source of truth for "who sees what".
  async function toggleJob(userPmId: string | null, job: JobOpt) {
    if (!userPmId) {
      setError("This user has no pmId — can't assign jobs. Add a pmId via the user record first.");
      return;
    }
    setError(null);
    setBusyEmail(userPmId);
    const newPmId = job.pm_id === userPmId ? null : userPmId;
    try {
      const r = await fetch("/api/admin/jobs", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: job.id, pm_id: newPmId }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) {
        setError(j.error ?? `HTTP ${r.status}`);
      } else {
        router.refresh();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setBusyEmail(null);
    }
  }

  async function removeUser(email: string) {
    if (!confirm(`Remove ${email}?`)) return;
    setError(null);
    setBusyEmail(email);
    try {
      const r = await fetch(
        `/api/admin/users?email=${encodeURIComponent(email)}`,
        { method: "DELETE" }
      );
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) {
        setError(j.error ?? `HTTP ${r.status}`);
      } else {
        router.refresh();
      }
    } finally {
      setBusyEmail(null);
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
        {users.map((u) => {
          const isAdminRow = u.role === "admin";
          return (
            <li
              key={u.email}
              className="border border-rule p-4"
              data-busy={busyEmail === u.pmId}
            >
              <div className="flex items-baseline justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-head text-[15px] text-foreground">
                    {u.name}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                    {u.email} · {u.role}
                    {u.pmId ? ` · pm:${u.pmId}` : ""}
                  </p>
                </div>
                {!isAdminRow && (
                  <button
                    type="button"
                    onClick={() => removeUser(u.email)}
                    className="shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3 hover:text-urgent transition-colors"
                    disabled={busyEmail === u.pmId}
                    title="Removes the overlay row; seed users revert to their default access."
                  >
                    Remove
                  </button>
                )}
              </div>

              {isAdminRow ? (
                <p className="mt-3 text-xs text-ink-2">
                  Admin — sees every job.
                </p>
              ) : !u.pmId ? (
                <p className="mt-3 text-xs text-urgent">
                  No pmId set — can&apos;t assign jobs to this user.
                </p>
              ) : (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {jobs.map((j) => {
                    const on = j.pm_id === u.pmId;
                    const otherPm = j.pm_id && j.pm_id !== u.pmId ? j.pm_id : null;
                    return (
                      <button
                        key={j.id}
                        type="button"
                        disabled={busyEmail === u.pmId}
                        onClick={() => toggleJob(u.pmId, j)}
                        title={
                          on
                            ? "Click to unassign"
                            : otherPm
                              ? `Currently assigned to ${otherPm} — click to reassign`
                              : "Click to assign"
                        }
                        className={
                          "px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors border " +
                          (on
                            ? "border-accent bg-accent text-paper"
                            : otherPm
                              ? "border-rule text-ink-3 hover:border-ink-2"
                              : "border-rule text-ink-2 hover:border-ink-2")
                        }
                      >
                        {j.name}
                        {otherPm ? ` (${otherPm})` : ""}
                      </button>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <AddUserForm jobs={jobs} pms={pms} onAdded={() => router.refresh()} />
    </div>
  );
}

function AddUserForm({
  jobs,
  pms,
  onAdded,
}: {
  jobs: JobOpt[];
  pms: PmOpt[];
  onAdded: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [pmId, setPmId] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function togglePicked(id: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          name,
          pmId: pmId || null,
          allowedJobs: Array.from(picked),
        }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) {
        setError(j.error ?? `HTTP ${r.status}`);
        return;
      }
      setEmail("");
      setName("");
      setPmId("");
      setPicked(new Set());
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="border border-rule p-4 mt-2"
    >
      <h2 className="font-head text-[15px] text-foreground">Add a PM</h2>
      <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
        Password defaults to <span className="font-mono">password</span>
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Email
          </span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="newpm@rossbuilt.com"
            className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
          />
        </label>
        <label className="block">
          <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Name
          </span>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Pat Doe"
            className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
          />
        </label>
      </div>

      <label className="block mt-3">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Link to existing PM record (optional)
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

      <div className="mt-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-2">
          Jobs this PM can see
        </p>
        <div className="flex flex-wrap gap-1.5">
          {jobs.map((j) => {
            const on = picked.has(j.id);
            return (
              <button
                key={j.id}
                type="button"
                onClick={() => togglePicked(j.id)}
                className={
                  "px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors border " +
                  (on
                    ? "border-accent bg-accent text-paper"
                    : "border-rule text-ink-2 hover:border-ink-2")
                }
              >
                {j.name}
              </button>
            );
          })}
        </div>
      </div>

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
        {busy ? "Adding…" : "Add PM"}
      </button>
    </form>
  );
}
