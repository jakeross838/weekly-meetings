"use client";

// Per-job client-facing update generator. Weekly / Monthly buttons call the
// client-summary route (Claude) and render a warm, share-ready update covering
// budget, schedule, and upcoming selections — with a one-tap copy for emailing
// the homeowner.

import { useState } from "react";
import { fetchJson } from "@/lib/fetch-json";

interface ClientSummary {
  greeting: string;
  budget: string;
  schedule: string;
  upcoming_selections: string[];
  whats_next: string[];
  closing: string;
}

export function ClientSummaryPanel({ jobId }: { jobId: string }) {
  const [period, setPeriod] = useState<"weekly" | "monthly" | null>(null);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function gen(p: "weekly" | "monthly") {
    setBusy(true);
    setErr(null);
    setSummary(null);
    setPeriod(p);
    setCopied(false);
    try {
      const j = await fetchJson(`/api/jobs/${jobId}/client-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ period: p }),
      });
      setSummary(j.summary as ClientSummary);
      setBusy(false);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  function asText(s: ClientSummary): string {
    const parts = [s.greeting, "", `BUDGET\n${s.budget}`, "", `SCHEDULE\n${s.schedule}`];
    if (s.upcoming_selections.length)
      parts.push("", "UPCOMING SELECTIONS", ...s.upcoming_selections.map((x) => `• ${x}`));
    if (s.whats_next.length)
      parts.push("", "WHAT'S NEXT", ...s.whats_next.map((x) => `• ${x}`));
    parts.push("", s.closing);
    return parts.join("\n");
  }

  function copy() {
    if (!summary || typeof navigator === "undefined" || !navigator.clipboard) return;
    navigator.clipboard.writeText(asText(summary)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const tab = (active: boolean) =>
    "px-3 py-1.5 text-xs font-medium border transition-colors disabled:opacity-50 " +
    (active
      ? "bg-ink text-paper border-ink"
      : "bg-paper text-ink border-rule hover:border-ink");
  const h3 = "font-mono text-[9px] tracking-[0.2em] uppercase text-ink-3 mb-1";

  return (
    <section className="px-5 pt-2">
      <div className="border border-rule p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Client update
          </h2>
          <div className="flex gap-2">
            <button type="button" onClick={() => gen("weekly")} disabled={busy} className={tab(period === "weekly")}>
              Weekly
            </button>
            <button type="button" onClick={() => gen("monthly")} disabled={busy} className={tab(period === "monthly")}>
              Monthly
            </button>
          </div>
        </div>

        {busy && (
          <p className="mt-3 font-mono text-[11px] text-accent">
            Writing the {period} update…
          </p>
        )}
        {err && <p className="mt-3 text-sm text-urgent">{err}</p>}

        {summary && !busy && (
          <div className="mt-4 space-y-3 text-sm leading-relaxed">
            <p className="text-foreground">{summary.greeting}</p>
            <div>
              <h3 className={h3}>Budget</h3>
              <p className="text-ink-2">{summary.budget}</p>
            </div>
            <div>
              <h3 className={h3}>Schedule</h3>
              <p className="text-ink-2">{summary.schedule}</p>
            </div>
            {summary.upcoming_selections.length > 0 && (
              <div>
                <h3 className={h3}>Upcoming selections</h3>
                <ul className="space-y-1">
                  {summary.upcoming_selections.map((s, i) => (
                    <li key={i} className="text-ink-2">
                      • {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {summary.whats_next.length > 0 && (
              <div>
                <h3 className={h3}>What&apos;s next</h3>
                <ul className="space-y-1">
                  {summary.whats_next.map((s, i) => (
                    <li key={i} className="text-ink-2">
                      • {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-ink-2">{summary.closing}</p>
            <button
              type="button"
              onClick={copy}
              className="mt-1 border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-paper transition-colors"
            >
              {copied ? "✓ Copied" : "⧉ Copy for client"}
            </button>
          </div>
        )}

        {!summary && !busy && !err && (
          <p className="mt-2 text-xs text-ink-3">
            Generate a share-ready update for the homeowner — budget, schedule,
            and upcoming selections.
          </p>
        )}
      </div>
    </section>
  );
}
