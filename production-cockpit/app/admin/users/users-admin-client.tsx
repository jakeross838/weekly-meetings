"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AdminUser } from "@/lib/user-store";

interface JobOpt {
  id: string;
  name: string;
  pm_id: string | null;
}
interface PmOpt {
  id: string;
  full_name: string;
}

interface SignupRequest {
  id: string;
  email: string;
  name: string;
  message: string | null;
  created_at: string;
}

export function UsersAdminClient({
  users,
  jobs,
  pms,
  selfEmail,
  pendingSignups,
}: {
  users: AdminUser[];
  jobs: JobOpt[];
  pms: PmOpt[];
  selfEmail: string;
  pendingSignups: SignupRequest[];
}) {
  const router = useRouter();
  const [busyEmail, setBusyEmail] = useState<string | null>(null);
  const [busySignup, setBusySignup] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reviewSignup(id: string, action: "approve" | "reject", pmId?: string) {
    setError(null);
    setBusySignup(id);
    try {
      const r = await fetch("/api/admin/signup-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, action, pmId: pmId || null }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) {
        setError(j.error ?? `HTTP ${r.status}`);
      } else {
        router.refresh();
      }
    } finally {
      setBusySignup(null);
    }
  }

  async function withBusy<T>(email: string, fn: () => Promise<T>) {
    setError(null);
    setBusyEmail(email);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setBusyEmail(null);
    }
  }

  async function postJson(method: string, url: string, body?: unknown) {
    const r = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const j = await r.json().catch(() => ({} as { ok?: boolean; error?: string }));
    if (!r.ok || (j as { ok?: boolean }).ok === false) {
      throw new Error((j as { error?: string }).error ?? `HTTP ${r.status}`);
    }
    return j;
  }

  // Clicking a job tile flips jobs.pm_id between this user's pmId and the
  // "owned by someone else" state — the API closes any stale assignment row
  // server-side so the change actually takes effect.
  async function toggleJob(userPmId: string | null, job: JobOpt) {
    if (!userPmId) {
      setError("This user has no pmId — can't assign jobs. Set a pmId first.");
      return;
    }
    const newPmId = job.pm_id === userPmId ? null : userPmId;
    await withBusy(userPmId, async () => {
      await postJson("PATCH", "/api/admin/jobs", { id: job.id, pm_id: newPmId });
      router.refresh();
    });
  }

  async function resetPassword(email: string) {
    const next = window.prompt(
      `New password for ${email}? (leave blank to cancel)`,
      ""
    );
    if (!next) return;
    await withBusy(email, async () => {
      await postJson("PATCH", "/api/admin/users", { email, password: next });
      router.refresh();
      alert(`Password for ${email} set to: ${next}\n\n(Share this securely.)`);
    });
  }

  async function toggleDisabled(email: string, currentlyDisabled: boolean) {
    const verb = currentlyDisabled ? "re-enable" : "disable";
    if (!window.confirm(`${verb[0].toUpperCase() + verb.slice(1)} ${email}?`)) return;
    await withBusy(email, async () => {
      await postJson("PATCH", "/api/admin/users", {
        email,
        disabled: !currentlyDisabled,
      });
      router.refresh();
    });
  }

  async function toggleRole(email: string, currentRole: "admin" | "pm") {
    const newRole = currentRole === "admin" ? "pm" : "admin";
    const msg =
      newRole === "admin"
        ? `Make ${email} an ADMIN? They'll see every job + this panel.`
        : `Revoke admin from ${email}? They'll go back to seeing only their own jobs.`;
    if (!window.confirm(msg)) return;
    await withBusy(email, async () => {
      await postJson("PATCH", "/api/admin/users", { email, role: newRole });
      router.refresh();
    });
  }

  async function removeUser(email: string) {
    if (
      !window.confirm(
        `Remove ${email}? This only removes their overlay row. Seed users revert to defaults; overlay-only users are gone for good.`
      )
    )
      return;
    await withBusy(email, async () => {
      await postJson(
        "DELETE",
        `/api/admin/users?email=${encodeURIComponent(email)}`
      );
      router.refresh();
    });
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

      {pendingSignups.length > 0 && (
        <section className="border-2 border-accent bg-accent/5 p-4">
          <header className="flex items-baseline justify-between gap-3">
            <h2 className="font-head text-[15px] text-foreground">
              Pending access requests · {pendingSignups.length}
            </h2>
          </header>
          <ul className="mt-3 space-y-2.5">
            {pendingSignups.map((s) => (
              <li key={s.id} className="border border-rule bg-paper p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-head text-sm text-foreground">
                      {s.name}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                      {s.email} · {new Date(s.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="shrink-0 flex gap-2">
                    <button
                      type="button"
                      onClick={() => reviewSignup(s.id, "approve")}
                      disabled={busySignup === s.id}
                      className="bg-ink text-paper px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] hover:bg-accent transition-colors disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => reviewSignup(s.id, "reject")}
                      disabled={busySignup === s.id}
                      className="border border-rule text-ink-3 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] hover:text-urgent hover:border-urgent transition-colors disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                </div>
                {s.message && (
                  <p className="mt-2 text-xs text-ink-2 leading-relaxed border-t border-rule pt-2">
                    {s.message}
                  </p>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-3 font-mono text-[10px] text-ink-3">
            Approve sends them a welcome email with a temporary password.
          </p>
        </section>
      )}

      <div className="flex items-baseline justify-between gap-3 pb-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          {users.length} {users.length === 1 ? "user" : "users"}
        </p>
        <a
          href="#add-pm"
          className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent hover:text-ink transition-colors"
        >
          + Add new PM →
        </a>
      </div>

      <ul className="space-y-3 stagger-children">
        {users.map((u) => {
          const isAdminRow = u.role === "admin";
          const isSelf = u.email.toLowerCase() === selfEmail.toLowerCase();
          const disabled = u._disabled;
          const busy = busyEmail === u.pmId || busyEmail === u.email;
          return (
            <li
              key={u.email}
              className={
                "border p-4 transition-all " +
                (disabled
                  ? "border-rule bg-sand/30 opacity-60"
                  : "border-rule bg-paper")
              }
            >
              <div className="flex items-baseline justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-head text-[15px] text-foreground">
                    {u.name}
                    {isSelf && (
                      <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
                        you
                      </span>
                    )}
                    {disabled && (
                      <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.14em] text-urgent">
                        disabled
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                    {u.email} · {u.role}
                    {u.pmId ? ` · pm:${u.pmId}` : ""}
                    {u._seedOnly ? " · seed" : " · overlay"}
                  </p>
                </div>
              </div>

              {/* Inline admin actions row */}
              <div className="mt-3 flex flex-wrap gap-3 text-[11px] font-mono uppercase tracking-[0.14em]">
                <button
                  type="button"
                  onClick={() => resetPassword(u.email)}
                  disabled={busy}
                  className="text-ink-3 hover:text-ink transition-colors disabled:opacity-50"
                >
                  Reset password
                </button>
                {!isSelf && (
                  <button
                    type="button"
                    onClick={() => toggleDisabled(u.email, disabled)}
                    disabled={busy}
                    className="text-ink-3 hover:text-urgent transition-colors disabled:opacity-50"
                  >
                    {disabled ? "Re-enable" : "Disable"}
                  </button>
                )}
                {!isSelf && (
                  <button
                    type="button"
                    onClick={() => toggleRole(u.email, isAdminRow ? "admin" : "pm")}
                    disabled={busy}
                    className="text-ink-3 hover:text-accent transition-colors disabled:opacity-50"
                  >
                    {isAdminRow ? "Revoke admin" : "Make admin"}
                  </button>
                )}
                {!isSelf && !u._seedOnly && (
                  <button
                    type="button"
                    onClick={() => removeUser(u.email)}
                    disabled={busy}
                    className="text-ink-3 hover:text-urgent transition-colors disabled:opacity-50"
                    title="Only deletes the overlay row (works on non-seed users)."
                  >
                    Remove
                  </button>
                )}
              </div>

              {isAdminRow ? (
                <p className="mt-4 text-xs text-ink-2">
                  Admin — sees every job.
                </p>
              ) : !u.pmId ? (
                <p className="mt-4 text-xs text-urgent">
                  No pmId set — can&apos;t assign jobs to this user.
                </p>
              ) : (
                <div className="mt-4">
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-2">
                    Jobs · click to assign / unassign
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {jobs.map((j) => {
                      const on = j.pm_id === u.pmId;
                      const otherPm =
                        j.pm_id && j.pm_id !== u.pmId ? j.pm_id : null;
                      return (
                        <button
                          key={j.id}
                          type="button"
                          disabled={busy || disabled}
                          onClick={() => toggleJob(u.pmId, j)}
                          title={
                            on
                              ? "Click to unassign"
                              : otherPm
                                ? `Currently assigned to ${otherPm} — click to reassign here`
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
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <div id="add-pm" />
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
  const [password, setPassword] = useState("");
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
          password: password || undefined,
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
      setPassword("");
      setPicked(new Set());
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="border border-rule p-4 mt-2">
      <h2 className="font-head text-[15px] text-foreground">Add a PM</h2>
      <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
        Password defaults to <span className="font-mono">password</span> if left blank.
        A new pmId also auto-creates the PM record so jobs can be assigned.
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
          pmId
        </span>
        <input
          type="text"
          value={pmId}
          onChange={(e) =>
            setPmId(e.target.value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, ""))
          }
          list="pms-list"
          placeholder="sarah  (pick existing or type a new one)"
          className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
        />
        <datalist id="pms-list">
          {pms.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
            </option>
          ))}
        </datalist>
        <span className="mt-1 block font-mono text-[10px] text-ink-3">
          Lowercase letters / digits / _ / - only. New pmIds also auto-create
          a row in the <span className="font-mono">pms</span> table.
        </span>
      </label>

      <label className="block mt-3">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Initial password (optional)
        </span>
        <input
          type="text"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="leave blank for default 'password'"
          className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
        />
      </label>

      <div className="mt-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-2">
          Jobs this PM owns (sets jobs.pm_id)
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
