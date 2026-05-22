// /v2/review/[ingestion_event_id] — diff detail page.
//
// Server component: fetches the ingestion event, its proposed_changes,
// and the meeting + claims for context. Hands off all the per-row
// editing + commit UX to the client ReviewForm component.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Header } from "@/components/header";
import {
  ReviewForm,
  ProposedChange,
  ClaimLite,
} from "./review-form";

export const dynamic = "force-dynamic";

function jobLabel(jobId: string | null): string {
  if (!jobId) return "—";
  return jobId.charAt(0).toUpperCase() + jobId.slice(1);
}

export default async function ReviewDetailPage({
  params,
}: {
  params: { ingestion_event_id: string };
}) {
  const { ingestion_event_id } = params;
  const supabase = supabaseServer();

  const [eventRes, changesRes, subsRes, jobsRes] = await Promise.all([
    supabase
      .from("ingestion_events")
      .select("*")
      .eq("id", ingestion_event_id)
      .maybeSingle(),
    supabase
      .from("proposed_changes")
      .select("*")
      .eq("ingestion_event_id", ingestion_event_id)
      .order("change_type", { ascending: true })
      .order("created_at", { ascending: true }),
    supabase.from("subs").select("id, name").eq("hidden", false).order("name"),
    supabase.from("jobs").select("id, name").order("name"),
  ]);

  if (!eventRes.data) {
    return (
      <main className="max-w-[560px] mx-auto min-h-screen bg-background">
        <Header />
        <div className="px-5 py-16">
          <h1 className="font-head text-2xl text-foreground">Event not found</h1>
          <p className="mt-2 text-ink-3 text-sm">
            No ingestion event with id{" "}
            <span className="font-mono">{ingestion_event_id}</span>.
          </p>
          <Link
            href="/v2/review"
            className="mt-4 inline-block text-accent text-sm underline"
          >
            ← back to review queue
          </Link>
        </div>
      </main>
    );
  }

  const event = eventRes.data as {
    id: string;
    source_type: string;
    source_meeting_id: string | null;
    review_state: string;
    proposed_count: number;
    job_id: string | null;
  };
  const changes = (changesRes.data ?? []) as ProposedChange[];
  const subs = (subsRes.data ?? []) as { id: string; name: string }[];
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];

  // Pull meeting + claims for context + per-row quotes
  type Meeting = {
    id: string;
    meeting_date: string;
    meeting_type: string | null;
    job_id: string;
  };
  let meeting: Meeting | null = null;
  const claimById: Record<string, ClaimLite> = {};
  if (event.source_meeting_id) {
    const [mRes, cRes] = await Promise.all([
      supabase
        .from("meetings")
        .select("id, meeting_date, meeting_type, job_id")
        .eq("id", event.source_meeting_id)
        .maybeSingle(),
      supabase
        .from("claims")
        .select("id, speaker, statement, raw_quote")
        .eq("meeting_id", event.source_meeting_id)
        .limit(500),
    ]);
    meeting = ((mRes.data as unknown) as Meeting | null) ?? null;
    const rows = ((cRes.data as unknown) as {
      id: string;
      speaker: string | null;
      statement: string;
      raw_quote: string | null;
    }[] | null) ?? [];
    for (const c of rows) {
      claimById[c.id] = {
        speaker: c.speaker,
        statement: c.statement,
        raw_quote: c.raw_quote,
      };
    }
  }

  const closed =
    event.review_state !== "pending" && event.review_state !== "in_review";

  // Multi-job detection: count proposals per job_id. If more than one job
  // appears we surface a banner so the user knows the transcript spans
  // multiple sites before approving.
  const jobNameById: Record<string, string> = {};
  for (const j of jobs) jobNameById[j.id] = j.name;
  const countsByJob: Record<string, number> = {};
  for (const c of changes) {
    const jid =
      (c.job_id as string | null) ??
      ((c.proposed_item_data as { job_id?: string } | null)?.job_id ?? null) ??
      ((c.proposed_decision_data as { job_id?: string } | null)?.job_id ?? null) ??
      ((c.proposed_question_data as { job_id?: string } | null)?.job_id ?? null);
    if (!jid) continue;
    countsByJob[jid] = (countsByJob[jid] ?? 0) + 1;
  }
  const jobBreakdown = Object.entries(countsByJob).sort(
    (a, b) => b[1] - a[1]
  );
  const multiJob = jobBreakdown.length > 1;

  return (
    <main className="max-w-[640px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <header className="px-5 pt-8 pb-6 border-b border-rule">
        <Link
          href="/v2/review"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Review queue
        </Link>
        <h1 className="mt-3 font-head text-[24px] leading-none tracking-tight text-foreground">
          {meeting
            ? `${meeting.meeting_date} · ${jobLabel(meeting.job_id)} ${
                meeting.meeting_type ?? ""
              } meeting`
            : "Ingestion event"}
        </h1>
        <p className="mt-2 text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">
          {event.source_type} · {event.proposed_count} proposal
          {event.proposed_count === 1 ? "" : "s"} · {event.review_state}
        </p>
      </header>

      {multiJob && (
        <div className="px-5 pt-4">
          <div className="border-2 border-high bg-high/5 px-4 py-3">
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-high mb-2">
              Multi-job transcript · {jobBreakdown.length} jobs
            </p>
            <p className="text-ink-2 text-sm leading-snug mb-2">
              This Plaud transcript proposes changes across multiple jobs.
              Approvals will land on each job&apos;s page separately.
            </p>
            <ul className="space-y-1">
              {jobBreakdown.map(([jid, count]) => (
                <li
                  key={jid}
                  className="flex items-baseline justify-between gap-3 text-sm"
                >
                  <Link
                    href={`/v2/job/${jid}`}
                    className="text-accent hover:underline"
                  >
                    {jobNameById[jid] ?? jid}
                  </Link>
                  <span className="font-mono text-xs text-ink-3 tabular-nums">
                    {count} proposal{count === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="px-5 pt-6">
        <ReviewForm
          ingestionEventId={event.id}
          changes={changes}
          claimById={claimById}
          subs={subs}
          jobs={jobs}
          alreadyClosed={closed}
        />
      </div>
    </main>
  );
}
