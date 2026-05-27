"use client";

// Interactive run-of-show. The server hands us a fully-computed, ordered
// agenda; this component only owns the "covered" walk-through state so a PM
// can step through jobs in the meeting and watch progress. Ephemeral by
// design (resets on reload) — covering a job is a meeting gesture, not data.

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { DeleteButton } from "@/components/delete-button";

export interface MeetingItem {
  id: string;
  title: string;
  daysOver: number | null; // set when past due
  daysTo: number | null; // set when due in the future
  subName: string | null;
}
export interface AttentionSub {
  id: string;
  name: string;
  status: "red" | "yellow" | "green";
  dotClass: string;
  reason: string | null;
}
export interface MeetingJob {
  id: string;
  name: string;
  pmName: string | null;
  contractPct: number | null;
  pending: number;
  pastDue: MeetingItem[];
  dueSoon: MeetingItem[];
  laterCount: number;
  attentionSubs: AttentionSub[];
}

export function MeetingAgenda({ jobs }: { jobs: MeetingJob[] }) {
  const [covered, setCovered] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setCovered((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const done = covered.size;
  const pct = jobs.length ? Math.round((done / jobs.length) * 100) : 0;

  return (
    <>
      {/* Sticky progress — stays visible while walking the agenda. */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur px-5 pt-3 pb-3 border-b border-rule">
        <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          <span>
            {done} of {jobs.length} covered
          </span>
          {done > 0 && (
            <button
              onClick={() => setCovered(new Set())}
              className="hover:text-ink transition-colors"
            >
              reset
            </button>
          )}
        </div>
        <div className="mt-2 h-1 w-full bg-sand-2 overflow-hidden">
          <div
            className="h-full bg-ink transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {jobs.length === 0 ? (
        <p className="px-5 pt-10 text-ink-3 text-sm">No jobs in scope.</p>
      ) : (
        <ol className="px-5 pt-5 pb-12 space-y-4">
          {jobs.map((j, i) => (
            <JobCard
              key={j.id}
              job={j}
              index={i + 1}
              covered={covered.has(j.id)}
              onToggle={() => toggle(j.id)}
            />
          ))}
        </ol>
      )}
    </>
  );
}

function JobCard({
  job,
  index,
  covered,
  onToggle,
}: {
  job: MeetingJob;
  index: number;
  covered: boolean;
  onToggle: () => void;
}) {
  const nothing =
    job.pastDue.length === 0 &&
    job.dueSoon.length === 0 &&
    job.attentionSubs.length === 0 &&
    job.pending === 0;

  // Side accent bar tone: urgent if past-due exists, accent if anything else
  // needs attention, neutral when nothing's open.
  const accent =
    job.pastDue.length > 0
      ? "before:bg-urgent"
      : !nothing
        ? "before:bg-accent"
        : "before:bg-rule";

  return (
    <li
      className={
        "relative border border-rule bg-paper transition-all duration-300 overflow-hidden " +
        // left accent stripe via ::before pseudo
        "before:content-[''] before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1 " +
        accent +
        " " +
        (covered
          ? "opacity-60 bg-background"
          : "shadow-[0_1px_0_rgba(0,0,0,0.02)] hover:shadow-md")
      }
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
        <Link href={`/v2/job/${job.id}`} className="flex items-start gap-3 flex-1 min-w-0 group">
          <span
            aria-hidden
            className={
              "shrink-0 mt-0.5 grid h-7 w-7 place-items-center rounded-full font-mono text-[11px] tabular-nums transition-colors " +
              (covered
                ? "bg-ink/10 text-ink-3"
                : "bg-oceanside/40 text-ink group-hover:bg-accent group-hover:text-paper")
            }
          >
            {String(index).padStart(2, "0")}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="font-head text-[19px] leading-tight tracking-tight text-foreground group-hover:text-accent transition-colors truncate">
              {job.name}
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink-3">
              {job.pmName && <span className="font-mono uppercase tracking-[0.1em]">{job.pmName}</span>}
              {job.contractPct != null && (
                <>
                  <Dot />
                  <span className="font-mono tabular-nums">{job.contractPct}% billed</span>
                </>
              )}
              {job.pending > 0 && (
                <>
                  <Dot />
                  <span className="font-mono text-accent uppercase tracking-[0.1em]">
                    {job.pending} to approve
                  </span>
                </>
              )}
            </div>
          </div>
        </Link>
        <button
          onClick={onToggle}
          className={
            "shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] border px-2.5 py-1.5 transition-colors " +
            (covered
              ? "bg-ink text-paper border-ink"
              : "bg-transparent text-ink-2 border-rule hover:border-ink hover:text-ink hover:bg-oceanside/30")
          }
        >
          {covered ? "✓ covered" : "cover"}
        </button>
      </div>

      {!covered && (
        <div className="px-5 pb-4">
          {nothing ? (
            <div className="border-t border-rule pt-3 text-ink-3 text-sm italic">
              Nothing open — quick confirm and move on.
            </div>
          ) : (
            <div className="border-t border-rule pt-3 grid gap-3">
              {job.pastDue.length > 0 && (
                <Bucket tone="urgent" title="Past due" count={job.pastDue.length}>
                  <ul className="divide-y divide-urgent/15">
                    {job.pastDue.map((it) => (
                      <ItemRow key={it.id} it={it} pastDue />
                    ))}
                  </ul>
                </Bucket>
              )}
              {job.dueSoon.length > 0 && (
                <Bucket tone="accent" title="This week" count={job.dueSoon.length}>
                  <ul className="divide-y divide-rule">
                    {job.dueSoon.map((it) => (
                      <ItemRow key={it.id} it={it} />
                    ))}
                  </ul>
                </Bucket>
              )}
              {job.attentionSubs.length > 0 && (
                <Bucket tone="neutral" title="Subs to watch" count={job.attentionSubs.length}>
                  <ul className="flex flex-wrap gap-1.5 pt-1">
                    {job.attentionSubs.map((s) => (
                      <SubChip key={s.id} sub={s} />
                    ))}
                  </ul>
                </Bucket>
              )}
              {job.laterCount > 0 && (
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3 pt-1">
                  + {job.laterCount} more open (no near date)
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function Dot() {
  return <span aria-hidden className="text-ink-3/60">·</span>;
}

function Bucket({
  title,
  count,
  tone,
  children,
}: {
  title: string;
  count: number;
  tone: "urgent" | "accent" | "neutral";
  children: ReactNode;
}) {
  // Each bucket gets a soft tinted background + header to chunk the content
  // visually, so the page reads as discrete blocks instead of one wall.
  const bg =
    tone === "urgent"
      ? "bg-urgent/[0.04] border-urgent/20"
      : tone === "accent"
        ? "bg-oceanside/30 border-rule"
        : "bg-sand/40 border-rule";
  const titleColor =
    tone === "urgent" ? "text-urgent" : tone === "accent" ? "text-ink" : "text-ink-2";
  return (
    <section className={`border ${bg}`}>
      <header
        className={`flex items-baseline justify-between px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.18em] ${titleColor}`}
      >
        <span>{title}</span>
        <span className="tabular-nums">{count}</span>
      </header>
      <div className="bg-paper">{children}</div>
    </section>
  );
}

function ItemRow({ it, pastDue }: { it: MeetingItem; pastDue?: boolean }) {
  return (
    <li className="flex gap-3 items-baseline px-3 py-2.5">
      <span className="flex-1 min-w-0 text-foreground text-sm leading-snug">
        {it.title}
        {it.subName && (
          <span className="ml-2 inline-block font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
            · {it.subName}
          </span>
        )}
      </span>
      <span
        className={
          "shrink-0 font-mono text-xs tabular-nums whitespace-nowrap " +
          (pastDue ? "text-urgent" : "text-ink-3")
        }
      >
        {pastDue
          ? `${it.daysOver}d over`
          : it.daysTo === 0
            ? "today"
            : `${it.daysTo}d`}
      </span>
      <DeleteButton
        endpoint={`/api/todos/${it.id}/delete`}
        label="to-do"
        className="self-center text-sm"
      />
    </li>
  );
}

function SubChip({ sub }: { sub: AttentionSub }) {
  return (
    <li>
      <Link
        href={`/sub/${sub.id}`}
        className="inline-flex items-center gap-1.5 border border-rule bg-paper px-2 py-1 text-xs hover:border-ink-2 hover:bg-oceanside/30 transition-colors group"
        title={sub.reason ?? undefined}
      >
        <span className={`shrink-0 h-2 w-2 rounded-full ${sub.dotClass}`} />
        <span className="text-foreground group-hover:text-accent transition-colors">
          {sub.name}
        </span>
        {sub.reason && (
          <span className="text-ink-3 font-mono text-[10px] uppercase tracking-[0.1em] hidden sm:inline">
            · {sub.reason}
          </span>
        )}
      </Link>
    </li>
  );
}
