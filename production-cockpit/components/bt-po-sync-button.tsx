"use client";

// One-click "Pull POs from Buildertrend" button + modal for /import. Submits
// to /api/bt/sync-po, which spawns scrape_po.py and chains into the PO upload.
//
// Default = fast grid-only pull (PO totals/status across all jobs; preserves
// line items). "Include line items" is slow (one request per PO) — pair it
// with a jobs filter or it'll time out.
//
// Credentials: username remembered in localStorage; password lives only in
// component state for a single submit and is cleared on success/close.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const USERNAME_KEY = "bt-sync-username";

interface PoSyncResult {
  ok: true;
  elapsedMs: number;
  includeLineItems: boolean;
  scrape: {
    exitCode: number;
    jobCount: number;
    poCount: number;
    lineItemCount: number;
    stdoutTail: string;
    stderrTail: string;
  };
  upload: {
    ok?: boolean;
    jobs?: number;
    upserted?: number;
    lineItems?: number;
    errors?: string[];
  };
}

interface PoSyncError {
  ok: false;
  error: string;
  scraperDir?: string;
  stdoutTail?: string;
  stderrTail?: string;
  elapsedMs?: number;
}

export function BtPoSyncButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [jobs, setJobs] = useState("");
  const [includeLineItems, setIncludeLineItems] = useState(false);
  const [headed, setHeaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PoSyncResult | null>(null);
  const [error, setError] = useState<PoSyncError | string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(USERNAME_KEY);
    if (saved) setUsername(saved);
  }, []);

  useEffect(() => {
    if (open && passwordRef.current) passwordRef.current.focus();
  }, [open]);

  function closeAndClear() {
    setOpen(false);
    setPassword("");
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(USERNAME_KEY, username);
    }
    try {
      const r = await fetch("/api/bt/sync-po", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          jobs: jobs.trim() || undefined,
          includeLineItems,
          headed,
        }),
      });
      const data = (await r.json()) as PoSyncResult | PoSyncError;
      if (!r.ok || data.ok === false) {
        setError(data as PoSyncError);
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
        className="bg-ink text-paper px-4 py-2.5 text-sm font-medium hover:bg-accent transition-colors"
      >
        💲 Pull POs from Buildertrend
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-ink/50 flex items-end sm:items-center justify-center px-3 py-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) closeAndClear();
          }}
        >
          <div className="w-full max-w-md bg-background border border-rule shadow-xl max-h-[90vh] overflow-y-auto">
            <header className="px-5 pt-5 pb-3 border-b border-rule">
              <h2 className="font-head text-lg font-semibold text-foreground">
                Pull purchase orders
              </h2>
              <p className="mt-1 text-xs text-ink-3 leading-snug">
                Runs locally — logs into BT and refreshes every job&apos;s POs
                (cost, paid, outstanding, status) into Supabase. Fast grid pull
                by default; line items are slower.
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

              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeLineItems}
                    onChange={(e) => setIncludeLineItems(e.target.checked)}
                    disabled={busy}
                    className="h-4 w-4 accent-accent"
                  />
                  Include line items (slow)
                </label>
                {includeLineItems && (
                  <p
                    className={
                      "font-mono text-[10px] leading-snug pl-6 " +
                      (jobs.trim() ? "text-ink-3" : "text-urgent")
                    }
                  >
                    {jobs.trim()
                      ? "One request per PO — pulls line items for the filtered job(s)."
                      : "⚠ Add a Jobs filter above to include line items — pulling them for every job times out (~30 min)."}
                  </p>
                )}
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
              </div>

              {busy && (
                <div className="border border-accent bg-accent/5 p-3">
                  <p className="font-mono text-[11px] text-accent leading-snug">
                    Pulling… grid-only is ~2-3 min; line items take longer.
                    Keep this tab open.
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
                        scraper stderr (last 3 KB)
                      </summary>
                      <pre className="mt-2 text-[10px] text-ink-2 bg-sand-2/40 p-2 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
                        {error.stderrTail}
                      </pre>
                    </details>
                  )}
                </div>
              )}

              {result && <PoResultSummary result={result} />}
            </div>

            <footer className="px-5 py-3 border-t border-rule flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={closeAndClear}
                disabled={busy}
                className="text-xs tracking-[0.18em] uppercase text-ink-3 hover:text-ink"
              >
                {result ? "Close" : "Cancel"}
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={
                  busy ||
                  !username.trim() ||
                  !password ||
                  (includeLineItems && !jobs.trim())
                }
                className="bg-ink text-paper px-5 py-2 text-sm font-medium disabled:opacity-50 hover:bg-accent transition-colors"
              >
                {busy ? "Pulling…" : result ? "Run again" : "Pull POs"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}

function PoResultSummary({ result }: { result: PoSyncResult }) {
  const secs = Math.round(result.elapsedMs / 1000);
  return (
    <div className="border border-success bg-success/5 p-3 space-y-2">
      <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-success">
        Success · {secs}s {result.includeLineItems ? "· with line items" : "· grid only"}
      </p>
      <ul className="text-sm text-ink-2 space-y-0.5">
        <li>
          Scrape: {result.scrape.poCount} PO
          {result.scrape.poCount === 1 ? "" : "s"} across {result.scrape.jobCount}{" "}
          job{result.scrape.jobCount === 1 ? "" : "s"}
          {result.includeLineItems && (
            <> · {result.scrape.lineItemCount} line items</>
          )}
        </li>
        <li>
          Supabase: {result.upload.upserted ?? 0} PO
          {result.upload.upserted === 1 ? "" : "s"} upserted
          {result.includeLineItems && (
            <> · {result.upload.lineItems ?? 0} line items</>
          )}
        </li>
        {(result.upload.errors ?? []).length > 0 && (
          <li className="text-urgent">
            {(result.upload.errors ?? []).length} upload error(s)
          </li>
        )}
      </ul>
      <details>
        <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          scraper log
        </summary>
        <pre className="mt-1 text-[10px] text-ink-2 bg-sand-2/40 p-2 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
          {result.scrape.stderrTail || result.scrape.stdoutTail || "(no output)"}
        </pre>
      </details>
    </div>
  );
}
