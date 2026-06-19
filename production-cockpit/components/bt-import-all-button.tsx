"use client";

// One-click "Import all jobs from Buildertrend" — replaces the three separate
// pull buttons (daily logs / POs / COs). Opens a small modal:
//   - BT email (remembered in localStorage)
//   - BT password (component state only, wiped on close/success)
//   - Show-browser-window checkbox (first-time login / MFA)
//   - Big "Import all jobs" button
//
// Submits to /api/bt/sync-all, which streams NDJSON progress events. The modal
// renders a live 3-step progress UI (spinner → checkmark / red X per step) so
// you can see exactly which scrape is currently running.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ModalPortal } from "@/components/modal-portal";

const USERNAME_KEY = "bt-sync-username";

type StepName = "daily-logs" | "purchase-orders" | "change-orders";
type StepStatus = "idle" | "running" | "ok" | "fail";

interface StepState {
  status: StepStatus;
  label: string;
  detail: string;
  progress?: string; // most recent per-job activity line ("Krauss · 9 logs")
  jobsDone?: number;
  jobsTotal?: number;
  error?: string;
  stderrTail?: string;
}

const INITIAL_STEPS: Record<StepName, StepState> = {
  "daily-logs": { status: "idle", label: "Daily logs", detail: "Field activity + on-site photos" },
  "purchase-orders": { status: "idle", label: "Purchase orders", detail: "Cost, paid, outstanding · line items included" },
  "change-orders": { status: "idle", label: "Change orders", detail: "Approved + pending CO totals" },
};

const STEP_ORDER: StepName[] = ["daily-logs", "purchase-orders", "change-orders"];

interface StepStartEvent {
  kind: "step:start";
  step: StepName;
  label: string;
}
interface StepProgressEvent {
  kind: "step:progress";
  step: StepName;
  message: string;
  jobsDone?: number;
  jobsTotal?: number;
}
interface StepDoneEvent {
  kind: "step:done";
  step: StepName;
  ok: boolean;
  elapsedMs: number;
  scrape: {
    jobCount: number;
    logCount?: number;
    photoCount?: number;
    poCount?: number;
    lineItemCount?: number;
    coCount?: number;
  };
  upload: { upserted?: number; inserted?: number; lineItems?: number } & Record<string, unknown>;
  vision?: { considered?: number; processed?: number; failed?: number } | null;
  error?: string;
  stderrTail?: string;
}
interface DoneEvent {
  kind: "done";
  ok: boolean;
  elapsedMs: number;
}
interface ErrorEvent {
  kind: "error";
  error: string;
}
type Event = StepStartEvent | StepProgressEvent | StepDoneEvent | DoneEvent | ErrorEvent;

export function BtImportAllButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [headed, setHeaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState<Record<StepName, StepState>>(INITIAL_STEPS);
  const [doneEvent, setDoneEvent] = useState<DoneEvent | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const passwordRef = useRef<HTMLInputElement>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(USERNAME_KEY);
    if (saved) setUsername(saved);
  }, []);

  useEffect(() => {
    if (open && passwordRef.current) passwordRef.current.focus();
  }, [open]);

  useEffect(() => {
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, []);

  function reset() {
    setSteps(INITIAL_STEPS);
    setDoneEvent(null);
    setFatalError(null);
    setElapsedMs(0);
  }

  function closeAndClear() {
    if (busy) return;
    setOpen(false);
    setPassword("");
    reset();
  }

  function applyEvent(ev: Event) {
    if (ev.kind === "step:start") {
      setSteps((prev) => ({
        ...prev,
        [ev.step]: { ...prev[ev.step], status: "running", detail: ev.label, progress: undefined, jobsDone: undefined, jobsTotal: undefined },
      }));
    } else if (ev.kind === "step:progress") {
      setSteps((prev) => ({
        ...prev,
        [ev.step]: {
          ...prev[ev.step],
          progress: ev.message,
          jobsDone: ev.jobsDone ?? prev[ev.step].jobsDone,
          jobsTotal: ev.jobsTotal ?? prev[ev.step].jobsTotal,
        },
      }));
    } else if (ev.kind === "step:done") {
      const status: StepStatus = ev.ok ? "ok" : "fail";
      const summary = summarize(ev);
      setSteps((prev) => ({
        ...prev,
        [ev.step]: {
          ...prev[ev.step],
          status,
          detail: summary,
          error: ev.error,
          stderrTail: ev.stderrTail,
        },
      }));
    } else if (ev.kind === "done") {
      setDoneEvent(ev);
    } else if (ev.kind === "error") {
      setFatalError(ev.error);
    }
  }

  async function submit() {
    setBusy(true);
    reset();
    if (typeof window !== "undefined") {
      window.localStorage.setItem(USERNAME_KEY, username);
    }
    const startedAt = Date.now();
    setElapsedMs(0);
    tickRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 250);

    try {
      const r = await fetch("/api/bt/sync-all", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, headed }),
      });
      const reader = r.body?.getReader();
      if (!reader) {
        setFatalError("No stream returned from server");
        return;
      }
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          try {
            const ev = JSON.parse(line) as Event;
            applyEvent(ev);
          } catch {
            // ignore malformed lines — best effort
          }
        }
      }
      if (buf.trim()) {
        try {
          applyEvent(JSON.parse(buf.trim()) as Event);
        } catch {
          // ignore
        }
      }
      setPassword("");
      // NOTE: deliberately not calling router.refresh() here. The user wants
      // explicit control: the green "Update Supabase & refresh history"
      // button below is what flips the "At a glance" dates above. Data
      // already landed in Supabase during the run — the refresh just
      // re-queries it so the page reflects reality.
    } catch (e) {
      setFatalError(e instanceof Error ? e.message : String(e));
    } finally {
      if (tickRef.current) {
        clearInterval(tickRef.current);
        tickRef.current = null;
      }
      setBusy(false);
    }
  }

  const canSubmit = !busy && username.trim().length > 0 && password.length > 0;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="bg-ink text-paper px-5 py-3 text-sm font-medium hover:bg-accent transition-colors"
      >
        ⬇ Import all jobs from Buildertrend
      </button>

      {open && (
        <ModalPortal>
        <div
          className="fixed inset-0 z-50 bg-ink/50 flex items-end sm:items-center justify-center px-3 py-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeAndClear();
          }}
        >
          <div className="w-full max-w-md bg-background border border-rule shadow-xl max-h-[90vh] overflow-y-auto">
            <header className="px-5 pt-5 pb-3 border-b border-rule">
              <h2 className="font-head text-lg font-semibold text-foreground">
                Import all jobs from Buildertrend
              </h2>
              <p className="mt-1 text-xs text-ink-3 leading-snug">
                Logs into BT once and pulls daily logs (+ photos), every PO with
                line items, and every change order for <em>every active job</em>.
                New jobs in BT are auto-detected — no setup needed.
              </p>
            </header>

            <div className="px-5 py-4 space-y-4">
              {/* Credentials */}
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
              <label className="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={headed}
                  onChange={(e) => setHeaded(e.target.checked)}
                  disabled={busy}
                  className="h-4 w-4 accent-accent"
                />
                Show browser window (first-time login / MFA)
              </label>

              {/* Live progress UI — appears as soon as a run starts */}
              {(busy || doneEvent || someStepRan(steps)) && (
                <div className="border border-rule bg-paper p-4 space-y-3">
                  <div className="flex items-baseline justify-between">
                    <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
                      {doneEvent
                        ? doneEvent.ok
                          ? "Done"
                          : "Finished with errors"
                        : busy
                          ? "Pulling…"
                          : "Idle"}
                    </p>
                    <p className="font-mono text-[10px] tabular-nums text-ink-3">
                      {formatElapsed(elapsedMs)}
                    </p>
                  </div>
                  <ol className="space-y-2.5">
                    {STEP_ORDER.map((name) => (
                      <StepRow key={name} step={steps[name]} />
                    ))}
                  </ol>
                </div>
              )}

              {/* Explicit "saved to Supabase" success panel — appears only after a
                  fully-successful run. Tells the user, in plain English, that
                  every record landed in the database and gives them the button
                  to commit the new "last sync" dates into the page they're
                  looking at. */}
              {doneEvent?.ok && (
                <div className="border border-success bg-success/5 p-4 space-y-2">
                  <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-success">
                    ✓ Saved to Supabase
                  </p>
                  <ul className="text-sm text-ink-2 space-y-0.5">
                    <li>
                      Daily logs · {steps["daily-logs"].detail || "uploaded"}
                    </li>
                    <li>
                      Purchase orders · {steps["purchase-orders"].detail || "uploaded"}
                    </li>
                    <li>
                      Change orders · {steps["change-orders"].detail || "uploaded"}
                    </li>
                  </ul>
                  <p className="text-xs text-ink-3 pt-1">
                    Hit <strong>Update Supabase &amp; refresh history</strong>{" "}
                    to flip the &ldquo;At a glance&rdquo; dates above to today.
                  </p>
                </div>
              )}

              {fatalError && (
                <div className="border border-urgent bg-urgent/5 p-3 text-sm text-urgent">
                  {fatalError}
                </div>
              )}
            </div>

            <footer className="px-5 py-3 border-t border-rule flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={closeAndClear}
                disabled={busy}
                className="text-xs tracking-[0.18em] uppercase text-ink-3 hover:text-ink disabled:opacity-40"
              >
                {doneEvent ? "Close" : "Cancel"}
              </button>
              {/* Primary post-completion CTA — explicit "save / refresh
                  history" button the user asked for. The save itself already
                  happened during the stream; this button forces a
                  router.refresh() so the page's "At a glance" panel
                  re-queries Supabase and shows the new last-sync dates. */}
              {doneEvent?.ok ? (
                <button
                  type="button"
                  onClick={() => {
                    router.refresh();
                    closeAndClear();
                  }}
                  className="bg-success text-paper px-5 py-2 text-sm font-medium hover:opacity-90 transition-opacity"
                >
                  ✓ Update Supabase &amp; refresh history
                </button>
              ) : (
                <button
                  type="button"
                  onClick={submit}
                  disabled={!canSubmit}
                  className="bg-ink text-paper px-5 py-2 text-sm font-medium disabled:opacity-50 hover:bg-accent transition-colors"
                >
                  {busy
                    ? "Pulling…"
                    : doneEvent
                      ? "Try again"
                      : "Import all jobs"}
                </button>
              )}
            </footer>
          </div>
        </div>
        </ModalPortal>
      )}
    </>
  );
}

function StepRow({ step }: { step: StepState }) {
  const showProgress = step.status === "running" && (step.progress || step.jobsTotal);
  return (
    <li className="flex items-start gap-3">
      <StepIndicator status={step.status} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm text-foreground font-medium">{step.label}</p>
          {showProgress && step.jobsTotal ? (
            <p className="font-mono text-[10px] tabular-nums text-accent shrink-0">
              {step.jobsDone ?? 0} / {step.jobsTotal}
            </p>
          ) : null}
        </div>
        <p className="text-xs text-ink-3 leading-snug">{step.detail}</p>
        {showProgress && step.progress && (
          <p className="mt-0.5 font-mono text-[11px] text-accent leading-snug truncate">
            → {step.progress}
          </p>
        )}
        {step.error && (
          <p className="mt-1 text-xs text-urgent leading-snug">{step.error}</p>
        )}
        {step.stderrTail && step.status === "fail" && (
          <details className="mt-1">
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
              scraper stderr
            </summary>
            <pre className="mt-1 text-[10px] text-ink-2 bg-sand-2/40 p-2 overflow-x-auto whitespace-pre-wrap max-h-40 overflow-y-auto">
              {step.stderrTail}
            </pre>
          </details>
        )}
      </div>
    </li>
  );
}

function StepIndicator({ status }: { status: StepStatus }) {
  if (status === "running") {
    return (
      <span
        aria-label="Running"
        className="mt-0.5 inline-block h-4 w-4 shrink-0 rounded-full border-2 border-accent border-t-transparent animate-spin"
      />
    );
  }
  if (status === "ok") {
    return (
      <span
        aria-label="Done"
        className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-success text-paper text-[10px] leading-none"
      >
        ✓
      </span>
    );
  }
  if (status === "fail") {
    return (
      <span
        aria-label="Failed"
        className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-urgent text-paper text-[10px] leading-none"
      >
        ✕
      </span>
    );
  }
  return (
    <span
      aria-label="Pending"
      className="mt-0.5 inline-block h-4 w-4 shrink-0 rounded-full border-2 border-rule"
    />
  );
}

function summarize(ev: StepDoneEvent): string {
  if (!ev.ok) return ev.error ?? "Failed";
  if (ev.step === "daily-logs") {
    const u = (ev.upload as { inserted?: number; skipped?: number }) ?? {};
    const photos = ev.scrape.photoCount ?? 0;
    const vision = ev.vision
      ? ` · ${ev.vision.processed ?? 0} photos summarized`
      : "";
    return `${ev.scrape.logCount ?? 0} logs across ${ev.scrape.jobCount} jobs · ${
      u.inserted ?? 0
    } new${photos ? ` · ${photos} photos` : ""}${vision}`;
  }
  if (ev.step === "purchase-orders") {
    const u = ev.upload;
    return `${ev.scrape.poCount ?? 0} POs across ${ev.scrape.jobCount} jobs · ${
      u.upserted ?? 0
    } upserted · ${ev.scrape.lineItemCount ?? 0} line items`;
  }
  if (ev.step === "change-orders") {
    const u = ev.upload;
    return `${ev.scrape.coCount ?? 0} change orders across ${ev.scrape.jobCount} jobs · ${
      u.upserted ?? 0
    } upserted`;
  }
  return "Done";
}

function someStepRan(steps: Record<StepName, StepState>): boolean {
  return Object.values(steps).some((s) => s.status !== "idle");
}

function formatElapsed(ms: number): string {
  if (ms <= 0) return "0s";
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}
