"use client";

// The job's "summary document" panel — top of /v2/job/[id]. Renders a
// Claude-generated narrative summary plus a status row that shows how
// much data backs it, with two action buttons:
//   - "Process N pending photos" (only when there are unprocessed photos)
//   - "Refresh summary" (runs the Claude pass)
//
// Server passes initialSummary + initialMeta + initialPendingPhotos so
// the first render is data-driven. The component then handles refresh
// actions client-side via fetch.

import { useState } from "react";
import { useRouter } from "next/navigation";

export interface JobSummary {
  headline: string;
  phase: string | null;
  whats_happening: string[];
  subs_recently_on_site: Array<{
    name: string;
    days: number;
    primary_activity: string | null;
  }>;
  open_concerns: Array<{
    text: string;
    priority: "URGENT" | "HIGH" | "NORMAL";
    owner: string | null;
  }>;
  coming_up: string[];
  inspections_recent: string[];
  safety_flags: string[];
  confidence: "high" | "medium" | "low";
}

export interface SummaryMeta {
  generated_at: string;
  log_count: number;
  photo_count: number;
  open_todo_count: number;
  done_todo_count: number;
  last_data_through: string | null;
  model?: string;
  elapsed_ms?: number;
}

interface Props {
  jobId: string;
  jobName: string;
  initialSummary: JobSummary | null;
  initialMeta: SummaryMeta | null;
  initialPendingPhotos: number;
  totalPhotos: number;
}

function relativeAge(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

const PRIORITY_TONE: Record<JobSummary["open_concerns"][number]["priority"], string> = {
  URGENT: "text-urgent border-urgent",
  HIGH: "text-high border-high",
  NORMAL: "text-ink-2 border-rule",
};

export function JobSummaryPanel({
  jobId,
  jobName,
  initialSummary,
  initialMeta,
  initialPendingPhotos,
  totalPhotos,
}: Props) {
  const router = useRouter();
  const [summary, setSummary] = useState<JobSummary | null>(initialSummary);
  const [meta, setMeta] = useState<SummaryMeta | null>(initialMeta);
  const [pending, setPending] = useState(initialPendingPhotos);
  const [busy, setBusy] = useState<"refresh" | "process" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refreshSummary() {
    setBusy("refresh");
    setErr(null);
    try {
      const r = await fetch(`/api/jobs/${jobId}/refresh-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ window_days: 30 }),
      });
      const data = await r.json();
      if (!r.ok || data.ok === false) {
        setErr(data.error || `HTTP ${r.status}`);
        return;
      }
      setSummary(data.summary);
      setMeta(data.meta);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function processPending() {
    if (pending === 0) return;
    setBusy("process");
    setErr(null);
    try {
      const r = await fetch(`/api/jobs/${jobId}/process-pending`, {
        method: "POST",
      });
      const data = await r.json();
      if (!r.ok || data.ok === false) {
        setErr(data.error || `HTTP ${r.status}`);
        return;
      }
      // Backend returned per-log results. Trust the processed count and
      // assume any leftover failures are still pending.
      const processed = data.processed ?? 0;
      const failed = data.failed ?? 0;
      setPending((p) => Math.max(0, p - processed));
      if (failed > 0) {
        setErr(`${processed} processed · ${failed} failed (check console)`);
      }
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="px-5 pt-6">
      {/* Status row */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-3">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Summary
        </h2>
        <div className="font-mono text-[10px] tabular-nums text-ink-3 flex-1">
          {meta ? (
            <>
              {meta.log_count} log{meta.log_count === 1 ? "" : "s"} · {meta.photo_count}{" "}
              photo{meta.photo_count === 1 ? "" : "s"} · {meta.open_todo_count} open ·
              refreshed {relativeAge(meta.generated_at)}
              {meta.last_data_through && (
                <span className="text-ink-3"> · through {meta.last_data_through}</span>
              )}
            </>
          ) : (
            <>no summary yet — click Refresh to generate one</>
          )}
        </div>
      </div>

      {/* Action row */}
      <div className="flex flex-wrap gap-2 mb-4">
        {pending > 0 && (
          <button
            type="button"
            onClick={processPending}
            disabled={busy !== null}
            className="px-3 py-1.5 text-xs border border-accent text-accent hover:bg-accent hover:text-paper transition-colors disabled:opacity-50"
          >
            {busy === "process"
              ? `Processing ${pending}…`
              : `✨ Process ${pending} pending photo${pending === 1 ? "" : "s"}`}
          </button>
        )}
        {pending === 0 && totalPhotos > 0 && (
          <span className="px-2 py-1 text-[10px] font-mono tracking-[0.18em] uppercase text-success">
            ✓ all {totalPhotos} photo{totalPhotos === 1 ? "" : "s"} analyzed
          </span>
        )}
        <button
          type="button"
          onClick={refreshSummary}
          disabled={busy !== null}
          className="px-3 py-1.5 text-xs border border-ink text-ink hover:bg-ink hover:text-paper transition-colors disabled:opacity-50"
        >
          {busy === "refresh"
            ? "Refreshing…"
            : summary
              ? "↻ Refresh summary"
              : "Generate summary"}
        </button>
      </div>

      {err && (
        <p className="mb-3 text-xs text-urgent leading-snug">{err}</p>
      )}

      {/* The summary body */}
      {summary ? (
        <SummaryBody summary={summary} jobName={jobName} />
      ) : (
        <p className="text-sm text-ink-3 italic leading-relaxed border border-dashed border-rule p-4">
          No summary generated for {jobName} yet. Click <strong>Generate summary</strong>{" "}
          above — it will pull recent daily logs, open todos, sub activity, and
          photo context, and ask Claude to write a structured digest.
        </p>
      )}
    </section>
  );
}

function SummaryBody({
  summary,
  jobName,
}: {
  summary: JobSummary;
  jobName: string;
}) {
  return (
    <article className="border border-rule bg-paper p-4 sm:p-5 space-y-5">
      <header>
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          {jobName}
          {summary.phase && (
            <span className="text-accent"> · {summary.phase}</span>
          )}
          <span className="ml-2 opacity-70">confidence: {summary.confidence}</span>
        </p>
        <h3 className="mt-1.5 font-head text-lg leading-snug text-foreground">
          {summary.headline}
        </h3>
      </header>

      {summary.whats_happening?.length > 0 && (
        <section>
          <h4 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            What&apos;s happening
          </h4>
          <ul className="space-y-1.5 text-sm text-ink-2 leading-snug">
            {summary.whats_happening.map((s, i) => (
              <li key={i} className="pl-3 -indent-3">
                <span className="text-ink-3">•</span> {s}
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary.subs_recently_on_site?.length > 0 && (
        <section>
          <h4 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            Subs on site
          </h4>
          <ul className="text-sm text-ink-2 space-y-1">
            {summary.subs_recently_on_site.map((s, i) => (
              <li
                key={i}
                className="flex items-baseline justify-between gap-3 border-b border-rule-soft last:border-b-0 py-1"
              >
                <span>
                  <span className="text-foreground">{s.name}</span>
                  {s.primary_activity && (
                    <span className="text-ink-3"> — {s.primary_activity}</span>
                  )}
                </span>
                <span className="font-mono text-[11px] tabular-nums text-ink-3">
                  {s.days}d
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary.open_concerns?.length > 0 && (
        <section>
          <h4 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            Open concerns
          </h4>
          <ul className="space-y-2">
            {summary.open_concerns.map((c, i) => (
              <li
                key={i}
                className={`border-l-2 pl-2 ${PRIORITY_TONE[c.priority] ?? "border-rule"}`}
              >
                <p className="text-sm leading-snug text-ink-2">{c.text}</p>
                <p className="mt-0.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
                  {c.priority}
                  {c.owner && <span> · {c.owner}</span>}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary.coming_up?.length > 0 && (
        <section>
          <h4 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            Coming up
          </h4>
          <ul className="space-y-1 text-sm text-ink-2">
            {summary.coming_up.map((s, i) => (
              <li key={i} className="pl-3 -indent-3">
                <span className="text-ink-3">→</span> {s}
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary.inspections_recent?.length > 0 && (
        <section>
          <h4 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            Inspections
          </h4>
          <ul className="space-y-1 text-sm text-ink-2 font-mono text-[12px]">
            {summary.inspections_recent.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      {summary.safety_flags?.length > 0 && (
        <section>
          <h4 className="font-mono text-[10px] tracking-[0.22em] uppercase text-urgent mb-1.5">
            Safety flags
          </h4>
          <ul className="space-y-1 text-sm text-urgent">
            {summary.safety_flags.map((s, i) => (
              <li key={i} className="pl-3 -indent-3">
                <span>⚠</span> {s}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
