"use client";

// Small ✕ that asks for inline confirmation, then POSTs to `endpoint` (a delete
// route — soft or hard) and refreshes. If the route returns HTTP 409 with
// { requiresForce: true, error }, it surfaces that warning and a "delete anyway"
// step that re-POSTs with { force: true }. The standard delete affordance.

import { useState } from "react";
import { useRouter } from "next/navigation";

export function DeleteButton({
  endpoint,
  label,
  confirmLabel,
  className,
}: {
  endpoint: string;
  label?: string; // what's being deleted, for the tooltip/aria
  confirmLabel?: string; // overrides the "Delete?" prompt
  className?: string;
}) {
  const router = useRouter();
  const [step, setStep] = useState<"idle" | "confirm" | "warn">("idle");
  const [warnMsg, setWarnMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function del(force: boolean) {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(force ? { force: true } : {}),
      });
      if (r.status === 409) {
        const b = await r.json().catch(() => ({}));
        if (b.requiresForce) {
          setWarnMsg(b.error || "Delete anyway?");
          setStep("warn");
          setBusy(false);
          return;
        }
        setErr(b.error || "HTTP 409");
        setBusy(false);
        return;
      }
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        setErr(b.error || `HTTP ${r.status}`);
        setBusy(false);
        return;
      }
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  function cancel() {
    setStep("idle");
    setWarnMsg(null);
    setErr(null);
  }

  if (step === "confirm" || step === "warn") {
    const isWarn = step === "warn";
    return (
      <span className="inline-flex items-center gap-2 font-mono text-xs shrink-0">
        <span className={isWarn ? "text-urgent" : "text-ink-3"}>
          {isWarn ? warnMsg : confirmLabel ?? "Delete?"}
        </span>
        <button
          type="button"
          onClick={() => del(isWarn)}
          disabled={busy}
          className="px-2 py-1 text-urgent hover:underline disabled:opacity-50"
        >
          {isWarn ? "delete anyway" : "yes"}
        </button>
        <button
          type="button"
          onClick={cancel}
          disabled={busy}
          className="px-2 py-1 text-ink-3 hover:text-ink"
        >
          {isWarn ? "keep" : "no"}
        </button>
        {err && <span className="text-urgent">{err}</span>}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setStep("confirm")}
      title={label ? `Delete ${label}` : "Delete"}
      aria-label={label ? `Delete ${label}` : "Delete"}
      className={(className ?? "") + " shrink-0 text-ink-3 hover:text-urgent transition-colors"}
    >
      ✕
    </button>
  );
}
