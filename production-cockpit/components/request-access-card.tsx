"use client";

// Empty-state card for a newly-signed-up user with no jobs assigned yet.
// One button → opens a tiny prompt for an optional note → POSTs to
// /api/auth/request-access → Jake gets an email and the row shows up on
// /admin/users.

import { useState } from "react";

export function RequestAccessCard() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/auth/request-access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
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

  return (
    <section className="mx-5 mt-6 border-2 border-accent bg-accent/5 p-5">
      <h2 className="font-head text-lg text-foreground">No jobs assigned yet</h2>
      <p className="mt-2 text-sm text-ink-2 leading-relaxed">
        Your account is set up, but Jake hasn&apos;t assigned any jobs to you
        yet. Click below to send him a quick heads-up — once he approves and
        assigns jobs, they&apos;ll show up here automatically.
      </p>

      {sent ? (
        <div className="mt-4 border border-success/40 bg-success/5 p-3 text-sm text-ink-2">
          ✓ Request sent. Jake will reach out shortly.
        </div>
      ) : !open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-4 bg-ink text-paper px-5 py-2.5 font-head text-sm transition hover:bg-accent"
        >
          Request access
        </button>
      ) : (
        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
              Short note for Jake (optional)
            </span>
            <textarea
              rows={3}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="e.g. I'm the new PM on the Tucker project, need access to that one"
              className="mt-1 w-full border border-rule bg-paper px-3 py-2 text-sm text-foreground placeholder:text-ink-3 focus:outline-none focus:border-accent"
            />
          </label>
          {error && (
            <p role="alert" className="border border-urgent/40 bg-urgent/5 px-3 py-2 text-xs text-urgent">
              {error}
            </p>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="bg-ink text-paper px-5 py-2 font-head text-sm transition hover:bg-accent disabled:opacity-60"
            >
              {busy ? "Sending…" : "Send request"}
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={busy}
              className="text-xs text-ink-3 hover:text-ink transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
