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
    <div className="mt-2">
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="font-mono text-[10px] tracking-[0.18em] uppercase text-accent hover:underline disabled:opacity-50"
      >
        {busy ? "Seeding…" : "Seed default specialties"}
      </button>
      {msg && (
        <p className="mt-2 font-mono text-[10px] text-success/80">{msg}</p>
      )}
      {err && <p className="mt-2 text-xs text-urgent">{err}</p>}
    </div>
  );
}
