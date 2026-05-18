"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function SeedSpecialtiesButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    if (
      !confirm(
        "Seed default specialties (e.g. tile → prep, lay, grout) for every sub based on their trade?\n\nIdempotent — re-running won't duplicate."
      )
    )
      return;
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      const r = await fetch("/api/sub-specialties/seed-defaults", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await r.json();
      if (!r.ok) {
        setErr(data.error || `HTTP ${r.status}`);
      } else {
        setMsg(
          `Seeded ${data.subs_touched} subs · ${data.inserted_or_kept} rows · ${data.subs_without_defaults} with no defaults`
        );
        router.refresh();
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 border border-rule bg-paper px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Seed sub specialties
          </p>
          <p className="mt-1 text-xs text-ink-2 leading-snug">
            Auto-populate every sub with sensible default work types based on
            their trade (Tile → Prep, Lay, Grout; Paint → Prep, Exterior,
            Interior; etc.)
          </p>
        </div>
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="shrink-0 bg-accent text-paper px-4 py-2 text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {busy ? "Seeding…" : "Seed"}
        </button>
      </div>
      {msg && (
        <p className="mt-2 font-mono text-[10px] text-success/80">{msg}</p>
      )}
      {err && (
        <p className="mt-2 text-xs text-urgent break-words">{err}</p>
      )}
    </div>
  );
}
