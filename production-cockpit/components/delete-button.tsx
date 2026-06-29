"use client";

// Small ✕ that opens a centered "are you sure?" popup (ConfirmModal), then POSTs
// to `endpoint` (a delete route — soft or hard) and refreshes. If the route
// returns HTTP 409 with { requiresForce: true, error }, the popup swaps to a
// "delete anyway" step that re-POSTs with { force: true }. The standard delete
// affordance — every ✕ in the app routes through here, so a delete is always a
// deliberate two-step confirm, never a one-click accident.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmModal } from "@/components/confirm-modal";

export function DeleteButton({
  endpoint,
  label,
  confirmLabel,
  className,
}: {
  endpoint: string;
  label?: string; // what's being deleted, shown prominently + in the tooltip/aria
  confirmLabel?: string; // overrides the "Are you sure…" question body
  className?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<"confirm" | "warn">("confirm");
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
      // Deleted — close the popup and repaint.
      setOpen(false);
      setBusy(false);
      setStep("confirm");
      setWarnMsg(null);
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  function openModal() {
    setStep("confirm");
    setWarnMsg(null);
    setErr(null);
    setOpen(true);
  }
  function cancel() {
    if (busy) return;
    setOpen(false);
    setStep("confirm");
    setWarnMsg(null);
    setErr(null);
  }

  const isWarn = step === "warn";

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        title={label ? `Delete ${label}` : "Delete"}
        aria-label={label ? `Delete ${label}` : "Delete"}
        className={(className ?? "") + " shrink-0 text-ink-3 hover:text-urgent transition-colors"}
      >
        ✕
      </button>
      <ConfirmModal
        open={open}
        title={isWarn ? "Heads up" : "Confirm delete"}
        subject={label || "this item"}
        body={
          <div>
            <p>
              {isWarn
                ? warnMsg
                : confirmLabel ??
                  "Are you sure you want to delete this? This can’t be undone."}
            </p>
            {err && <p className="mt-2 text-urgent">{err}</p>}
          </div>
        }
        confirmLabel={isWarn ? "Delete anyway" : "Delete"}
        cancelLabel={isWarn ? "Keep" : "Cancel"}
        tone="urgent"
        busy={busy}
        onCancel={cancel}
        onConfirm={() => del(isWarn)}
      />
    </>
  );
}
