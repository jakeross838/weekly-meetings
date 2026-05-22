"use client";

// One-click "Pull change orders from Buildertrend" button + modal for /import.
// Submits to /api/bt/sync-co (spawns scrape_co.py -> change_orders upload).
// Username remembered; password never stored client-side.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const USERNAME_KEY = "bt-sync-username";

interface CoSyncResult {
  ok: true;
  elapsedMs: number;
  scrape: { coCount: number; jobCount: number; stdoutTail: string; stderrTail: string };
  upload: { upserted?: number; jobs?: number; errors?: string[] };
}
interface CoSyncError {
  ok: false;
  error: string;
  stderrTail?: string;
}

export function BtCoSyncButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [jobs, setJobs] = useState("");
  const [headed, setHeaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CoSyncResult | null>(null);
  const [error, setError] = useState<CoSyncError | string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(USERNAME_KEY);
    if (saved) setUsername(saved);
  }, []);
  useEffect(() => {
    if (open && passwordRef.current) passwordRef.current.focus();
  }, [open]);

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    if (typeof window !== "undefined") window.localStorage.setItem(USERNAME_KEY, username);
    try {
      const r = await fetch("/api/bt/sync-co", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, jobs: jobs.trim() || undefined, headed }),
      });
      const data = (await r.json()) as CoSyncResult | CoSyncError;
      if (!r.ok || data.ok === false) {
        setError(data as CoSyncError);
        setBusy(false);
        return;
      }
      setResult(data);
      setPassword("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="border border-ink text-ink px-4 py-2.5 text-sm font-medium hover:bg-ink hover:text-paper transition-colors"
      >
        🧾 Pull change orders
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-ink/50 flex items-end sm:items-center justify-center px-3 py-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) setOpen(false);
          }}
        >
          <div className="w-full max-w-md bg-background border border-rule shadow-xl max-h-[90vh] overflow-y-auto">
            <header className="px-5 pt-5 pb-3 border-b border-rule">
              <h2 className="font-head text-lg font-semibold text-foreground">
                Pull change orders
              </h2>
              <p className="mt-1 text-xs text-ink-3 leading-snug">
                Runs locally — logs into BT and refreshes every job&apos;s change
                orders into Supabase. They show on each job page.
              </p>
            </header>
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
                  BT email
                </label>
                <input
                  type="email"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  disabled={busy}
                  className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
                />
              </div>
              <div>
                <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
                  BT password
                  <span className="ml-2 normal-case tracking-normal opacity-70">
                    (never stored in this browser)
                  </span>
                </label>
                <input
                  ref={passwordRef}
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={busy}
                  className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
                />
              </div>
              <div>
                <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
                  Jobs (optional)
                </label>
                <input
                  type="text"
                  value={jobs}
                  onChange={(e) => setJobs(e.target.value)}
                  placeholder="all jobs — or e.g. Fish,Krauss"
                  disabled={busy}
                  className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={headed}
                  onChange={(e) => setHeaded(e.target.checked)}
                  disabled={busy}
                  className="h-4 w-4 accent-accent"
                />
                Show browser window (debugging / MFA)
              </label>

              {busy && (
                <div className="border border-accent bg-accent/5 p-3">
                  <p className="font-mono text-[11px] text-accent leading-snug">
                    Pulling change orders… ~1-2 min. Keep this tab open.
                  </p>
                </div>
              )}
              {error && (
                <div className="border border-urgent bg-urgent/5 p-3 space-y-2">
                  <p className="text-sm text-urgent font-medium">
                    {typeof error === "string" ? error : error.error}
                  </p>
                  {typeof error !== "string" && error.stderrTail && (
                    <details>
                      <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
                        scraper stderr
                      </summary>
                      <pre className="mt-2 text-[10px] text-ink-2 bg-sand-2/40 p-2 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
                        {error.stderrTail}
                      </pre>
                    </details>
                  )}
                </div>
              )}
              {result && (
                <div className="border border-success bg-success/5 p-3">
                  <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-success">
                    Success · {Math.round(result.elapsedMs / 1000)}s
                  </p>
                  <p className="mt-1 text-sm text-ink-2">
                    {result.scrape.coCount} change orders across{" "}
                    {result.scrape.jobCount} jobs · {result.upload.upserted ?? 0} upserted
                  </p>
                </div>
              )}
            </div>
            <footer className="px-5 py-3 border-t border-rule flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                disabled={busy}
                className="text-xs tracking-[0.18em] uppercase text-ink-3 hover:text-ink"
              >
                {result ? "Close" : "Cancel"}
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={busy || !username.trim() || !password}
                className="bg-ink text-paper px-5 py-2 text-sm font-medium disabled:opacity-50 hover:bg-accent transition-colors"
              >
                {busy ? "Pulling…" : result ? "Run again" : "Pull change orders"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
