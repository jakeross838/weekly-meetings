"use client";

// "Sync Buildertrend now" — triggers the cloud sync (GitHub Actions) from any
// device, no laptop. The 12h schedule keeps data fresh automatically; this is
// the on-demand backup. POSTs to /api/bt/trigger-sync.

import { useState } from "react";
import { useRouter } from "next/navigation";

export function BtCloudSyncButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function trigger() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch("/api/bt/trigger-sync", { method: "POST" });
      const d = (await r.json().catch(() => ({}))) as {
        ok?: boolean;
        message?: string;
        error?: string;
      };
      if (r.ok && d.ok) {
        setMsg({ ok: true, text: d.message || "Sync started." });
        // Give the run a moment to register, then refresh the history below.
        setTimeout(() => router.refresh(), 2000);
      } else {
        setMsg({ ok: false, text: d.error || `HTTP ${r.status}` });
      }
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={trigger}
        disabled={busy}
        className="bg-ink text-paper px-5 py-3 text-sm font-medium hover:bg-accent transition-colors disabled:opacity-50"
      >
        {busy ? "Starting…" : "⟳ Sync Buildertrend now"}
      </button>
      {msg && (
        <p className={`text-sm leading-snug ${msg.ok ? "text-success" : "text-urgent"}`}>
          {msg.text}
        </p>
      )}
      <p className="text-xs text-ink-3 leading-snug">
        Runs in the cloud — works from any device, no laptop needed. Buildertrend
        syncs <strong>automatically every 12h</strong>; use this only when you
        want a pull right now.
      </p>
    </div>
  );
}
