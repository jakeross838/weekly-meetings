"use client";

import { useState } from "react";

type VerifyResult = {
  has_daily_logs: boolean;
  has_parent_group: boolean;
  has_items_category: boolean;
  has_sub_specialties: boolean;
  has_duration_override: boolean;
};

export function MigrateForm() {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<string[] | null>(null);

  async function run() {
    if (!password.trim()) {
      setErr("Paste the DB password first.");
      return;
    }
    setBusy(true);
    setErr(null);
    setResult(null);
    setAttempts(null);
    try {
      const r = await fetch("/api/admin/run-migrations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ db_password: password }),
      });
      const data = await r.json();
      if (!r.ok) {
        setErr(data.error || `HTTP ${r.status}`);
        if (data.attempts) setAttempts(data.attempts);
        setBusy(false);
        return;
      }
      setResult(data.verified);
      setPassword(""); // clear the password from the form once done
      setBusy(false);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  if (result) {
    const allGood =
      result.has_daily_logs &&
      result.has_parent_group &&
      result.has_items_category &&
      result.has_sub_specialties &&
      result.has_duration_override;
    return (
      <div className="border border-rule bg-paper p-5 space-y-4">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-success/80">
          Done · migrations applied
        </p>
        <ul className="text-sm space-y-1.5">
          <Row ok={result.has_daily_logs} label="daily_logs table" />
          <Row
            ok={result.has_parent_group}
            label="daily_logs.parent_group_activities column"
          />
          <Row ok={result.has_items_category} label="items.category column" />
          <Row ok={result.has_sub_specialties} label="sub_specialties table" />
          <Row
            ok={result.has_duration_override}
            label="sub_specialties.duration_days_manual_override column"
          />
        </ul>
        {allGood && (
          <div className="pt-3 border-t border-rule-soft space-y-2">
            <p className="text-sm text-ink-2">
              All schema in place. Next:
            </p>
            <a
              href="/subs"
              className="inline-block bg-accent text-paper px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Go to /subs → click &quot;Seed&quot;
            </a>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="border border-rule bg-paper p-5 space-y-4">
      <div>
        <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
          Supabase DB password
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="paste here"
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter") run();
          }}
          className="w-full bg-paper border border-rule px-3 py-2.5 text-sm font-mono text-ink focus:outline-none focus:border-ink"
        />
        <p className="mt-1 font-mono text-[9px] tracking-[0.12em] uppercase text-ink-3">
          stored in memory only · never persisted
        </p>
      </div>

      <button
        type="button"
        onClick={run}
        disabled={busy || !password.trim()}
        className="w-full bg-success text-paper px-5 py-3 text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm"
      >
        {busy ? "Running migrations…" : "Run migrations →"}
      </button>

      {err && (
        <div className="border border-urgent/50 bg-urgent/5 px-3 py-2">
          <p className="text-sm text-urgent break-words">{err}</p>
          {attempts && attempts.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-ink-3">
                Connection attempts
              </summary>
              <ul className="mt-1 space-y-1 font-mono text-[10px] text-ink-3 break-words">
                {attempts.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-baseline gap-2">
      <span
        className={
          "font-mono text-xs " + (ok ? "text-success" : "text-urgent")
        }
      >
        {ok ? "✓" : "✗"}
      </span>
      <span className="text-ink-2">{label}</span>
    </li>
  );
}
