"use client";

import { useState } from "react";

export function ForgotForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/auth/forgot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const j = (await r.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
      };
      if (!r.ok || !j.ok) {
        setError(j.error ?? `Failed (${r.status})`);
        return;
      }
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="mt-9 border border-rule bg-paper p-5 text-center">
        <p className="font-head text-base text-foreground">Check your inbox</p>
        <p className="mt-2 text-sm text-ink-2 leading-relaxed">
          If that email matches an account, a reset link is on its way. The
          link is good for 1 hour.
        </p>
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
          Email
        </span>
        <input
          type="email"
          required
          autoComplete="email"
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@rossbuilt.com"
          className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground placeholder:text-ink-3 focus:outline-none focus:border-accent"
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
        {busy ? "Sending…" : "Send reset link"}
      </button>
    </form>
  );
}
