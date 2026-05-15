// /v2/review/[ingestion_event_id] — diff detail page.
//
// LEFT column: proposed_changes grouped by type (adds / updates / signals
// / decisions / questions). Each row shows the proposed data.
// RIGHT column (desktop) / inline (mobile): meeting context, claims summary.
// Bottom: commit form (Accept All / Reject All / Commit).

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { CommitForm } from "./commit-form";

export const dynamic = "force-dynamic";

type ProposedChange = {
  id: string;
  ingestion_event_id: string;
  change_type:
    | "add_item"
    | "update_item"
    | "resolve_item"
    | "merge_items"
    | "add_decision"
    | "add_open_question"
    | "add_signal"
    | "add_sub_event";
  proposed_item_data: Record<string, unknown> | null;
  target_item_id: string | null;
  field_changes: Record<string, { before: unknown; after: unknown }> | null;
  proposed_decision_data: Record<string, unknown> | null;
  proposed_question_data: Record<string, unknown> | null;
  review_state: "pending" | "accepted" | "rejected" | "edited_and_accepted";
  source_claim_ids: string[] | null;
  confidence: "high" | "medium" | "low" | null;
  job_id: string | null;
  sub_id: string | null;
  notes: string | null;
  created_at: string;
};

function jobLabel(jobId: string | null): string {
  if (!jobId) return "—";
  return jobId.charAt(0).toUpperCase() + jobId.slice(1);
}

function ConfDot({ c }: { c: string | null }) {
  if (!c || c === "high") return null;
  const color = c === "medium" ? "bg-high" : "bg-rule";
  return <span className={`inline-block w-1.5 h-1.5 rounded-full ${color}`} title={`confidence: ${c}`} />;
}

export default async function ReviewDetailPage({
  params,
}: {
  params: { ingestion_event_id: string };
}) {
  const { ingestion_event_id } = params;
  const supabase = supabaseServer();

  const [eventRes, changesRes] = await Promise.all([
    supabase.from("ingestion_events").select("*").eq("id", ingestion_event_id).maybeSingle(),
    supabase
      .from("proposed_changes")
      .select("*")
      .eq("ingestion_event_id", ingestion_event_id)
      .order("change_type", { ascending: true })
      .order("created_at", { ascending: true }),
  ]);

  if (!eventRes.data) {
    return (
      <main className="max-w-[480px] lg:max-w-[960px] mx-auto min-h-screen bg-background px-5 py-16">
        <h1 className="font-head text-2xl text-foreground">Event not found</h1>
        <p className="mt-2 text-ink-3 text-sm">
          No ingestion event with id <span className="font-mono">{ingestion_event_id}</span>.
        </p>
        <Link href="/v2/review" className="mt-4 inline-block text-accent text-sm underline">
          ← back to review queue
        </Link>
      </main>
    );
  }

  const event = eventRes.data as {
    id: string;
    source_type: string;
    source_meeting_id: string | null;
    ingested_at: string;
    ingested_by: string | null;
    review_state: string;
    proposed_count: number;
    job_id: string | null;
    source_file_path: string | null;
  };
  const changes = (changesRes.data ?? []) as ProposedChange[];

  // Pull meeting + claims for the right column context
  type Meeting = {
    id: string;
    meeting_date: string;
    meeting_type: string | null;
    job_id: string;
  };
  type Claim = {
    id: string;
    speaker: string | null;
    statement: string;
    raw_quote: string | null;
    position_in_transcript: number | null;
  };
  let meeting: Meeting | null = null;
  let claims: Claim[] = [];
  if (event.source_meeting_id) {
    const [mRes, cRes] = await Promise.all([
      supabase
        .from("meetings")
        .select("id, meeting_date, meeting_type, job_id")
        .eq("id", event.source_meeting_id)
        .maybeSingle(),
      supabase
        .from("claims")
        .select("id, speaker, statement, raw_quote, position_in_transcript")
        .eq("meeting_id", event.source_meeting_id)
        .order("position_in_transcript", { ascending: true })
        .limit(500),
    ]);
    meeting = ((mRes.data as unknown) as Meeting | null) ?? null;
    claims = ((cRes.data as unknown) as Claim[] | null) ?? [];
  }
  const claimById = new Map(claims.map((c) => [c.id, c]));

  // Group changes by type
  const groups: Record<string, ProposedChange[]> = {
    add_item: [],
    update_item: [],
    resolve_item: [],
    merge_items: [],
    add_decision: [],
    add_open_question: [],
    add_signal: [],
    add_sub_event: [],
  };
  for (const c of changes) {
    groups[c.change_type]?.push(c);
  }

  const counts = Object.fromEntries(
    Object.entries(groups).map(([k, v]) => [k, v.length])
  );

  return (
    <main className="max-w-[480px] lg:max-w-[1200px] mx-auto min-h-screen bg-background pb-24">
      {/* HEADER */}
      <header className="px-5 pt-10 pb-6 border-b border-rule">
        <div className="flex items-center gap-3">
          <Link href="/v2/review" className="text-ink-3 text-xs font-mono uppercase tracking-[0.18em] hover:text-accent">
            ← review queue
          </Link>
        </div>
        <h1 className="mt-3 font-head text-[24px] lg:text-[28px] leading-none tracking-tight text-foreground">
          {meeting
            ? `${meeting.meeting_date} · ${jobLabel(meeting.job_id)} ${meeting.meeting_type ?? ""} meeting`
            : "Ingestion event"}
        </h1>
        <p className="mt-2 text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">
          {event.source_type} · {event.proposed_count} proposals · {event.review_state}
        </p>
      </header>

      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-8 lg:px-5 lg:pt-8">
        {/* LEFT — proposed changes */}
        <div className="px-5 lg:px-0 pt-6 lg:pt-0">
          {/* Add items */}
          {groups.add_item.length > 0 && (
            <section className="pb-8">
              <SectionHeading>
                New items · {counts.add_item}
              </SectionHeading>
              <ul className="space-y-3">
                {groups.add_item.map((c) => (
                  <li key={c.id}>
                    <AddItemRow change={c} claimById={claimById} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Updates */}
          {groups.update_item.length > 0 && (
            <section className="pb-8">
              <SectionHeading>
                Updates · {counts.update_item}
              </SectionHeading>
              <ul className="space-y-3">
                {groups.update_item.map((c) => (
                  <li key={c.id}>
                    <UpdateItemRow change={c} claimById={claimById} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Decisions */}
          {groups.add_decision.length > 0 && (
            <section className="pb-8">
              <SectionHeading>
                Decisions · {counts.add_decision}
              </SectionHeading>
              <ul className="space-y-3">
                {groups.add_decision.map((c) => (
                  <li key={c.id}>
                    <DecisionRow change={c} claimById={claimById} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Open questions */}
          {groups.add_open_question.length > 0 && (
            <section className="pb-8">
              <SectionHeading>
                Open questions · {counts.add_open_question}
              </SectionHeading>
              <ul className="space-y-3">
                {groups.add_open_question.map((c) => (
                  <li key={c.id}>
                    <QuestionRow change={c} claimById={claimById} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Signals — collapsed by default */}
          {groups.add_signal.length > 0 && (
            <section className="pb-8">
              <SectionHeading>
                Signals · {counts.add_signal}{" "}
                <span className="text-ink-3 normal-case tracking-normal">(awareness only, no action)</span>
              </SectionHeading>
              <details className="group">
                <summary className="cursor-pointer text-accent text-sm py-2">
                  Show {counts.add_signal} signal{counts.add_signal === 1 ? "" : "s"}
                </summary>
                <ul className="mt-3 space-y-2">
                  {groups.add_signal.map((c) => (
                    <li key={c.id}>
                      <SignalRow change={c} />
                    </li>
                  ))}
                </ul>
              </details>
            </section>
          )}

          {/* Commit form */}
          {event.review_state === "pending" || event.review_state === "in_review" ? (
            <CommitForm
              ingestionEventId={event.id}
              proposedChangeIds={changes.map((c) => c.id)}
            />
          ) : (
            <p className="text-ink-3 text-sm py-4">
              This event is already {event.review_state}. No further action.
            </p>
          )}
        </div>

        {/* RIGHT — context */}
        <aside className="px-5 lg:px-0 pt-8 lg:pt-0 border-t lg:border-t-0 lg:sticky lg:top-4 lg:self-start">
          <SectionHeading>Context</SectionHeading>
          <dl className="text-sm space-y-2">
            <ContextRow label="Source" value={event.source_type} />
            <ContextRow
              label="Meeting"
              value={meeting ? `${meeting.meeting_date} ${meeting.meeting_type}` : "—"}
            />
            <ContextRow label="Primary job" value={jobLabel(event.job_id)} />
            <ContextRow label="Claims" value={`${claims.length}`} />
            <ContextRow label="Proposed" value={`${event.proposed_count}`} />
            <ContextRow label="State" value={event.review_state} />
          </dl>
          <p className="mt-6 text-ink-3 text-xs">
            Per-row context (raw claim quote, matched pay-app line, sub history) appears inline next to each
            proposed change on smaller viewports.
          </p>
        </aside>
      </div>
    </main>
  );
}

// ----- Components -----

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-4">
      {children}
    </h2>
  );
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-3 text-xs uppercase tracking-[0.06em]">{label}</dt>
      <dd className="text-foreground text-sm font-mono text-right">{value}</dd>
    </div>
  );
}

function ClaimSnippet({
  claim,
}: {
  claim: { speaker: string | null; statement: string; raw_quote: string | null } | undefined;
}) {
  if (!claim) return null;
  const quote = (claim.raw_quote ?? "").trim();
  return (
    <div className="mt-2 pt-2 border-t border-rule-soft">
      <p className="text-ink-3 text-xs">
        <span className="font-mono uppercase tracking-[0.06em] mr-1">from</span>
        <span className="text-ink-2">{claim.speaker ?? "?"}</span>
      </p>
      {quote && (
        <p className="mt-1 text-ink-2 text-xs italic leading-snug">
          “{quote.length > 220 ? quote.slice(0, 220) + "…" : quote}”
        </p>
      )}
    </div>
  );
}

function AddItemRow({
  change,
  claimById,
}: {
  change: ProposedChange;
  claimById: Map<string, { speaker: string | null; statement: string; raw_quote: string | null }>;
}) {
  const d = (change.proposed_item_data ?? {}) as Record<string, string | number | null | undefined>;
  const claimId = change.source_claim_ids?.[0];
  const claim = claimId ? claimById.get(claimId) : undefined;
  return (
    <div className="p-4 border border-rule bg-paper">
      <div className="flex items-start gap-2">
        <span className="mt-1 inline-block w-4 h-4 border border-rule shrink-0" aria-hidden />
        <div className="flex-1 min-w-0">
          <p className="text-foreground text-sm font-medium leading-snug">{d.title as string}</p>
          <p className="mt-1 text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">
            {d.type as string} · {d.actionability as string} · {jobLabel(d.job_id as string)}
            {d.sub_id ? ` · ${d.sub_id}` : ""}
            {d.target_date ? ` · target ${d.target_date}` : d.target_date_text ? ` · ${d.target_date_text}` : ""}
            {d.priority === "urgent" ? " · urgent" : ""}
            {change.confidence && change.confidence !== "high" ? ` · confidence ${change.confidence}` : ""}
          </p>
          {d.detail && (
            <p className="mt-1 text-ink-2 text-xs leading-snug">{d.detail as string}</p>
          )}
          <ClaimSnippet claim={claim} />
        </div>
        <ConfDot c={change.confidence} />
      </div>
    </div>
  );
}

function UpdateItemRow({
  change,
  claimById,
}: {
  change: ProposedChange;
  claimById: Map<string, { speaker: string | null; statement: string; raw_quote: string | null }>;
}) {
  const fc = change.field_changes ?? {};
  const claimId = change.source_claim_ids?.[0];
  const claim = claimId ? claimById.get(claimId) : undefined;
  return (
    <div className="p-4 border border-rule bg-paper">
      <div className="flex items-start gap-2">
        <span className="mt-1 inline-block w-4 h-4 border border-rule shrink-0" aria-hidden />
        <div className="flex-1 min-w-0">
          <p className="text-foreground text-sm font-medium leading-snug">
            Update existing item ({change.target_item_id?.slice(0, 8)}…)
          </p>
          <dl className="mt-2 text-xs space-y-1">
            {Object.entries(fc).map(([field, change_pair]) => (
              <div key={field} className="flex gap-2 items-baseline">
                <dt className="text-ink-3 font-mono uppercase tracking-[0.06em] w-32 shrink-0">{field}</dt>
                <dd className="flex-1">
                  <span className="text-ink-3 line-through">{String((change_pair as { before: unknown }).before ?? "—")}</span>
                  <span className="text-ink-3 mx-1">→</span>
                  <span className="text-foreground">{String((change_pair as { after: unknown }).after ?? "—")}</span>
                </dd>
              </div>
            ))}
          </dl>
          <ClaimSnippet claim={claim} />
        </div>
      </div>
    </div>
  );
}

function DecisionRow({
  change,
  claimById,
}: {
  change: ProposedChange;
  claimById: Map<string, { speaker: string | null; statement: string; raw_quote: string | null }>;
}) {
  const d = (change.proposed_decision_data ?? {}) as Record<string, string | null>;
  const claimId = change.source_claim_ids?.[0];
  const claim = claimId ? claimById.get(claimId) : undefined;
  return (
    <div className="p-4 border border-rule bg-paper">
      <p className="text-foreground text-sm leading-snug">{d.description}</p>
      <p className="mt-1 text-ink-3 text-xs">
        {d.decided_by ? `decided by ${d.decided_by}` : ""}
        {d.decision_date ? ` · ${d.decision_date}` : ""}
        {" · "}
        {jobLabel((d.job_id as string) ?? null)}
      </p>
      <ClaimSnippet claim={claim} />
    </div>
  );
}

function QuestionRow({
  change,
  claimById,
}: {
  change: ProposedChange;
  claimById: Map<string, { speaker: string | null; statement: string; raw_quote: string | null }>;
}) {
  const q = (change.proposed_question_data ?? {}) as Record<string, string | null>;
  const claimId = change.source_claim_ids?.[0];
  const claim = claimId ? claimById.get(claimId) : undefined;
  return (
    <div className="p-4 border border-rule bg-paper">
      <p className="text-foreground text-sm leading-snug">{q.question}</p>
      <p className="mt-1 text-ink-3 text-xs">
        {q.asked_by ? `asked by ${q.asked_by}` : ""}
        {" · "}
        {jobLabel((q.job_id as string) ?? null)}
      </p>
      <ClaimSnippet claim={claim} />
    </div>
  );
}

function SignalRow({ change }: { change: ProposedChange }) {
  const d = (change.proposed_item_data ?? {}) as Record<string, string | number | null | undefined>;
  return (
    <div className="px-3 py-2 bg-sand-2/40 border border-rule-soft">
      <p className="text-ink-2 text-sm leading-snug">{d.title as string}</p>
      <p className="mt-0.5 text-ink-3 text-xs">
        {jobLabel(d.job_id as string)}
        {d.sub_id ? ` · ${d.sub_id}` : ""}
      </p>
    </div>
  );
}
