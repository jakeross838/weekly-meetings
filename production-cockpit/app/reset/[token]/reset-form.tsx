"use client";

import { useState } from "react";

export function ResetForm({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      const r = await fetch("/api/auth/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      const j = (await r.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
      };
      if (!r.ok || !j.ok) {
        setError(j.error ?? `Failed (${r.status})`);
        return;
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="mt-9 border border-success/40 bg-success/5 p-5 text-center">
        <p className="font-head text-base text-foreground">Password updated</p>
        <a
          href="/login"
          className="mt-4 inline-block bg-ink px-4 py-2.5 font-head text-sm text-paper transition hover:bg-accent"
        >
          Sign in
        </a>
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mt-9 space-y-3"
      style={{ animation: "fadeUp 460ms ease-out both", animationDelay: "120ms" }}
    >
      <label className="block">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          New password
        </span>
        <input
          type="password"
          required
          autoFocus
          minLength={6}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-accent"
        />
      </label>
      <label className="block">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Confirm
        </span>
        <input
          type="password"
          required
          minLength={6}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-accent"
        />
      </label>
      {error && (
        <p role="alert" className="border border-urgent/40 bg-urgent/5 px-3 py-2 text-xs text-urgent">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy}
        className="w-full bg-ink px-4 py-3 font-head text-sm text-paper transition hover:bg-accent disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {busy ? "Saving…" : "Set password"}
      </button>
    </form>
  );
}
