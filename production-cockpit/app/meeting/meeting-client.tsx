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
        <ol>
          {jobs.map((j, i) => (
            <JobSection
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

function JobSection({
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

  return (
    <li
      className={
        "border-b border-rule px-5 py-5 transition-opacity " +
        (covered ? "opacity-45" : "")
      }
    >
      <div className="flex items-start justify-between gap-3">
        <Link href={`/v2/job/${job.id}`} className="flex-1 min-w-0 group">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[10px] text-ink-3 tabular-nums">
              {String(index).padStart(2, "0")}
            </span>
            <h2 className="font-head text-lg leading-none tracking-tight text-foreground group-hover:text-accent transition-colors truncate">
              {job.name}
            </h2>
          </div>
          <p className="mt-1 text-ink-3 text-xs">
            {job.pmName ?? "—"}
            {job.contractPct != null && <> · {job.contractPct}% billed</>}
            {job.pending > 0 && (
              <span className="text-accent"> · {job.pending} to approve</span>
            )}
          </p>
        </Link>
        <button
          onClick={onToggle}
          className={
            "shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] border px-2 py-1 transition-colors " +
            (covered
              ? "bg-ink text-paper border-ink"
              : "bg-transparent text-ink-2 border-rule hover:border-ink hover:text-ink")
          }
        >
          {covered ? "✓ covered" : "mark covered"}
        </button>
      </div>

      {!covered && (
        <div className="mt-4 space-y-4">
          {nothing && (
            <p className="text-ink-3 text-sm">
              Nothing open — quick confirm and move on.
            </p>
          )}
          {job.pastDue.length > 0 && (
            <Bucket title="Past due" tone="urgent" count={job.pastDue.length}>
              {job.pastDue.map((it) => (
                <ItemRow key={it.id} it={it} pastDue />
              ))}
            </Bucket>
          )}
          {job.dueSoon.length > 0 && (
            <Bucket title="This week" count={job.dueSoon.length}>
              {job.dueSoon.map((it) => (
                <ItemRow key={it.id} it={it} />
              ))}
            </Bucket>
          )}
          {job.attentionSubs.length > 0 && (
            <Bucket title="Subs to watch" count={job.attentionSubs.length}>
              {job.attentionSubs.map((s) => (
                <li key={s.id}>
                  <Link
                    href={`/sub/${s.id}`}
                    className="flex items-baseline gap-2 py-1 group"
                  >
                    <span
                      className={`shrink-0 self-center h-2 w-2 rounded-full ${s.dotClass}`}
                    />
                    <span className="shrink-0 text-foreground text-sm group-hover:text-accent transition-colors">
                      {s.name}
                    </span>
                    {s.reason && (
                      <span className="text-ink-3 text-xs truncate">
                        · {s.reason}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </Bucket>
          )}
          {job.laterCount > 0 && (
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">
              + {job.laterCount} more open (no near date)
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function Bucket({
  title,
  count,
  tone,
  children,
}: {
  title: string;
  count: number;
  tone?: "urgent";
  children: ReactNode;
}) {
  return (
    <div>
      <h3
        className={
          "font-mono text-[10px] tracking-[0.18em] uppercase mb-2 " +
          (tone === "urgent" ? "text-urgent" : "text-ink-3")
        }
      >
        {title} · {count}
      </h3>
      <ul className="space-y-1.5">{children}</ul>
    </div>
  );
}

function ItemRow({ it, pastDue }: { it: MeetingItem; pastDue?: boolean }) {
  return (
    <li
      className={
        "flex gap-3 items-baseline " +
        (pastDue ? "border-l-2 border-urgent pl-2 -ml-2" : "")
      }
    >
      <span className="flex-1 min-w-0 text-foreground text-sm leading-snug">
        {it.title}
        {it.subName && <span className="text-ink-3"> · {it.subName}</span>}
      </span>
      <span
        className={
          "shrink-0 font-mono text-xs tabular-nums " +
          (pastDue ? "text-urgent" : "text-ink-3")
        }
      >
        {pastDue
          ? `-${it.daysOver}d`
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
