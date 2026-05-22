"use client";

// Small ✕ that asks for inline confirmation, then POSTs to `endpoint` (a
// delete route — soft or hard) and refreshes. The standard delete affordance.

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
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function del() {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
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

  if (confirming) {
    return (
      <span className="inline-flex items-center gap-1.5 font-mono text-[10px] shrink-0">
        <span className="text-ink-3">{confirmLabel ?? "Delete?"}</span>
        <button
          type="button"
          onClick={del}
          disabled={busy}
          className="text-urgent hover:underline disabled:opacity-50"
        >
          yes
        </button>
        <button
          type="button"
          onClick={() => {
            setConfirming(false);
            setErr(null);
          }}
          className="text-ink-3 hover:text-ink"
        >
          no
        </button>
        {err && <span className="text-urgent">{err}</span>}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setConfirming(true)}
      title={label ? `Delete ${label}` : "Delete"}
      aria-label={label ? `Delete ${label}` : "Delete"}
      className={(className ?? "") + " shrink-0 text-ink-3 hover:text-urgent transition-colors"}
    >
      ✕
    </button>
  );
}
