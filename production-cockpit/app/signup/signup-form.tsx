"use client";

import { useState } from "react";

export function SignupForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const r = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      const j = (await r.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
      };
      if (!r.ok || !j.ok) {
        setError(j.error ?? `Failed (${r.status})`);
        return;
      }
      // Auto-login on success — go straight to /, which will show the
      // empty-state CTA pointing them at the Request-access button.
      window.location.assign("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
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
          Name
        </span>
        <input
          type="text"
          required
          autoFocus
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Pat Doe"
          className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground placeholder:text-ink-3 focus:outline-none focus:border-accent"
        />
      </label>
      <label className="block">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Email
        </span>
        <input
          type="email"
          required
          autoComplete="email"
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
          minLength={6}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-accent"
        />
      </label>
      <label className="block">
        <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Confirm password
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
        {busy ? "Creating…" : "Create account"}
      </button>
    </form>
  );
}
