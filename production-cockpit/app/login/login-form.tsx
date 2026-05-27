"use client";

import { useState } from "react";

export function LoginForm({ next }: { next: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const j = (await r.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
      };
      if (!r.ok || !j.ok) {
        setError(j.error ?? `Sign-in failed (${r.status})`);
        setBusy(false);
        return;
      }
      // Full-page nav so server components re-render with the new session.
      window.location.assign(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mt-9 space-y-3"
      style={{ animation: "fadeUp 460ms ease-out both", animationDelay: "120ms" }}
    >
      <label className="block">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Email
        </span>
        <input
          type="email"
          required
          autoComplete="username"
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@rossbuilt.com"
          className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground placeholder:text-ink-3 focus:outline-none focus:border-accent"
        />
      </label>

      <label className="block">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Password
        </span>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-accent"
        />
      </label>

      {error && (
        <p
          role="alert"
          className="border border-urgent/40 bg-urgent/5 px-3 py-2 text-xs text-urgent"
        >
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy}
        className="w-full bg-ink px-4 py-3 font-head text-sm text-paper transition hover:bg-accent disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
