"use client";

// One-click "Pull from Buildertrend" button + modal. Lives on /import
// next to the Daily logs upload form. Submits to /api/bt/sync which
// spawns the local Python scraper and chains into the Supabase upload
// + photo vision pass.
//
// Credential handling:
//  - username: remembered in localStorage (low-risk, convenience)
//  - password: NEVER stored client-side. Lives only in this component's
//    state during a single submit, cleared on success or modal close.
//  - On submit, password is POSTed once to /api/bt/sync; server passes
//    it to the child via env vars, never persists it.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const USERNAME_KEY = "bt-sync-username";

interface SyncResult {
  ok: true;
  elapsedMs: number;
  scrape: {
    exitCode: number;
    jobCount: number;
    logCount: number;
    photoCount: number;
    stdoutTail: string;
    stderrTail: string;
  };
  upload: {
    ok?: boolean;
    inserted?: number;
    skipped?: number;
    per_job?: Record<string, { total: number; inserted: number; skipped: number }>;
  };
  vision: {
    ok?: boolean;
    considered?: number;
    processed?: number;
    failed?: number;
  } | null;
  visionError: string | null;
}

interface SyncError {
  ok: false;
  error: string;
  scraperDir?: string;
  pythonExe?: string;
  scriptPath?: string;
  stdoutTail?: string;
  stderrTail?: string;
  uploadResult?: unknown;
  elapsedMs?: number;
}

export function BtSyncButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [days, setDays] = useState(14);
  const [jobs, setJobs] = useState("");
  const [skipPhotos, setSkipPhotos] = useState(false);
  const [extractVision, setExtractVision] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SyncResult | null>(null);
  const [error, setError] = useState<SyncError | string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  // Restore the remembered username on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(USERNAME_KEY);
    if (saved) setUsername(saved);
  }, []);

  // Focus the password field whenever the modal opens.
  useEffect(() => {
    if (open && passwordRef.current) {
      passwordRef.current.focus();
    }
  }, [open]);

  function closeAndClear() {
    setOpen(false);
    setPassword("");
    // Keep result visible until next open so user can re-read it.
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);

    // Persist only the username — never the password.
    if (typeof window !== "undefined") {
      window.localStorage.setItem(USERNAME_KEY, username);
    }

    try {
      const r = await fetch("/api/bt/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          days,
          jobs: jobs.trim() || undefined,
          skipPhotos,
          extractVision,
        }),
      });
      const data = (await r.json()) as SyncResult | SyncError;
      if (!r.ok || data.ok === false) {
        setError(data as SyncError);
        setBusy(false);
        return;
      }
      setResult(data);
      // Drop the password from component state immediately on success.
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
        className="bg-accent text-paper px-4 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity"
      >
        ✨ Pull from Buildertrend
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
                Pull from Buildertrend
              </h2>
              <p className="mt-1 text-xs text-ink-3 leading-snug">
                Runs locally on this machine — logs into BT, downloads
                daily logs + photos, writes to Supabase, and runs Claude
                vision over the photos.
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

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
                    Days back
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={90}
                    value={days}
                    onChange={(e) =>
                      setDays(Math.max(1, Number(e.target.value) || 14))
                    }
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
                    placeholder="Fish,Krauss"
                    disabled={busy}
                    className="w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!skipPhotos}
                    onChange={(e) => setSkipPhotos(!e.target.checked)}
                    disabled={busy}
                    className="h-4 w-4 accent-accent"
                  />
                  Download photos
                </label>
                <label
                  className={`flex items-center gap-2 text-sm cursor-pointer ${
                    skipPhotos ? "text-ink-3 opacity-50" : "text-ink-2"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={extractVision}
                    onChange={(e) => setExtractVision(e.target.checked)}
                    disabled={busy || skipPhotos}
                    className="h-4 w-4 accent-accent"
                  />
                  Run Claude vision on photos
                </label>
              </div>

              {busy && (
                <div className="border border-accent bg-accent/5 p-3">
                  <p className="font-mono text-[11px] text-accent leading-snug">
                    Running… this can take 1–5 minutes depending on how
                    many logs and photos. Keep this tab open.
                  </p>
                </div>
              )}

              {error && (
                <div className="border border-urgent bg-urgent/5 p-3 space-y-2">
                  <p className="text-sm text-urgent font-medium">
                    {typeof error === "string" ? error : error.error}
                  </p>
                  {typeof error !== "string" && error.scraperDir && (
                    <p className="font-mono text-[10px] text-ink-3 break-all">
                      tried: {error.scraperDir}
                    </p>
                  )}
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

              {result && <ResultSummary result={result} />}
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
                  busy || !username.trim() || !password
                }
                className="bg-ink text-paper px-5 py-2 text-sm font-medium disabled:opacity-50 hover:bg-accent transition-colors"
              >
                {busy ? "Pulling…" : result ? "Run again" : "Pull now"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}

function ResultSummary({ result }: { result: SyncResult }) {
  const secs = Math.round(result.elapsedMs / 1000);
  const visionLine = result.vision
    ? `Vision: ${result.vision.processed ?? 0} processed${
        (result.vision.failed ?? 0) > 0
          ? ` · ${result.vision.failed} failed`
          : ""
      }`
    : result.visionError
      ? `Vision failed: ${result.visionError}`
      : "Vision: skipped";

  return (
    <div className="border border-success bg-success/5 p-3 space-y-2">
      <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-success">
        Success · {secs}s
      </p>
      <ul className="text-sm text-ink-2 space-y-0.5">
        <li>
          Scrape: {result.scrape.logCount} log
          {result.scrape.logCount === 1 ? "" : "s"} across {result.scrape.jobCount}{" "}
          job{result.scrape.jobCount === 1 ? "" : "s"} · {result.scrape.photoCount}{" "}
          photo{result.scrape.photoCount === 1 ? "" : "s"}
        </li>
        <li>
          Supabase: {result.upload.inserted ?? 0} record
          {result.upload.inserted === 1 ? "" : "s"} upserted
          {(result.upload.skipped ?? 0) > 0 && (
            <span className="text-ink-3">
              {" "}
              · {result.upload.skipped} skipped (no logId)
            </span>
          )}
        </li>
        <li>{visionLine}</li>
      </ul>
      {result.upload.per_job && Object.keys(result.upload.per_job).length > 0 && (
        <details>
          <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            per-job breakdown
          </summary>
          <ul className="mt-1 text-[11px] font-mono text-ink-2 space-y-0.5">
            {Object.entries(result.upload.per_job).map(([job, c]) => (
              <li key={job}>
                {job}: {c.inserted}/{c.total}
                {c.skipped > 0 && (
                  <span className="text-ink-3"> · {c.skipped} skipped</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
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
