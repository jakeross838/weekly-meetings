// /v2/review — pending-review queue.
//
// Lists ingestion_events with review_state IN ('pending', 'in_review').
// Each card → /v2/review/[id]. Read-only listing; no actions here.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type IngestionEvent = {
  id: string;
  source_type: "transcript" | "daily_log" | "pay_app" | "manual";
  source_meeting_id: string | null;
  ingested_at: string;
  ingested_by: string | null;
  review_state: "pending" | "in_review" | "committed" | "rejected" | "partial";
  proposed_count: number;
  job_id: string | null;
  source_file_path: string | null;
};

type MeetingRow = {
  id: string;
  meeting_date: string;
  meeting_type: "site" | "office" | null;
  job_id: string;
};

type ProposedTypeRow = {
  ingestion_event_id: string;
  change_type: string;
  count: number;
};

function shortMeetingLabel(m: MeetingRow | null, sourceType: string): string {
  if (!m) return sourceType;
  const d = new Date(m.meeting_date + "T00:00:00Z");
  const md = `${d.getUTCMonth() + 1}/${String(d.getUTCDate()).padStart(2, "0")}`;
  const job = m.job_id.charAt(0).toUpperCase() + m.job_id.slice(1);
  const type = m.meeting_type ?? "";
  return `${md} ${job} ${type}`.trim();
}

function relativeAge(iso: string): string {
  const now = Date.now();
  const t = new Date(iso).getTime();
  const mins = Math.max(0, Math.floor((now - t) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function isStale(iso: string): boolean {
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000;
  return days > 7;
}

export default async function ReviewQueuePage() {
  const supabase = supabaseServer();

  const [eventsRes, meetingsRes] = await Promise.all([
    supabase
      .from("ingestion_events")
      .select("*")
      .in("review_state", ["pending", "in_review"])
      .order("ingested_at", { ascending: false }),
    supabase
      .from("meetings")
      .select("id, meeting_date, meeting_type, job_id"),
  ]);

  const events = (eventsRes.data ?? []) as IngestionEvent[];
  const meetings = (meetingsRes.data ?? []) as MeetingRow[];
  const meetingsById = new Map(meetings.map((m) => [m.id, m]));

  // Per-event counts by change_type
  const eventIds = events.map((e) => e.id);
  let typeCountsByEvent = new Map<string, Record<string, number>>();
  if (eventIds.length > 0) {
    const { data: changes } = await supabase
      .from("proposed_changes")
      .select("ingestion_event_id, change_type")
      .in("ingestion_event_id", eventIds);
    for (const c of (changes ?? []) as { ingestion_event_id: string; change_type: string }[]) {
      const map = typeCountsByEvent.get(c.ingestion_event_id) ?? {};
      map[c.change_type] = (map[c.change_type] ?? 0) + 1;
      typeCountsByEvent.set(c.ingestion_event_id, map);
    }
  }

  return (
    <main className="max-w-[480px] lg:max-w-[960px] mx-auto min-h-screen bg-background pb-24">
      <header className="px-5 pt-10 pb-6 border-b border-rule">
        <h1 className="font-head text-[28px] lg:text-[32px] leading-none tracking-tight text-foreground">
          Pending review
        </h1>
        <p className="mt-2 text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">
          {events.length === 0
            ? "no events queued"
            : `${events.length} event${events.length === 1 ? "" : "s"} · ${events.reduce((n, e) => n + e.proposed_count, 0)} proposals total`}
        </p>
      </header>

      {events.length === 0 ? (
        <div className="px-5 pt-12 text-center">
          <p className="text-ink-3 text-sm">Nothing pending review.</p>
          <p className="mt-2 text-ink-3 text-xs">
            Drop a transcript at{" "}
            <Link href="/v2/upload" className="text-accent underline">
              /v2/upload
            </Link>
            .
          </p>
        </div>
      ) : (
        <ul className="px-5 pt-6 space-y-3">
          {events.map((ev) => {
            const m = ev.source_meeting_id ? meetingsById.get(ev.source_meeting_id) ?? null : null;
            const counts = typeCountsByEvent.get(ev.id) ?? {};
            const adds = counts["add_item"] ?? 0;
            const updates = counts["update_item"] ?? 0;
            const signals = counts["add_signal"] ?? 0;
            const decisions = counts["add_decision"] ?? 0;
            const questions = counts["add_open_question"] ?? 0;
            return (
              <li key={ev.id}>
                <Link
                  href={`/v2/review/${ev.id}`}
                  className="block p-4 lg:p-5 border border-rule hover:border-accent bg-paper transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
                          {ev.source_type}
                        </span>
                        {isStale(ev.ingested_at) && (
                          <span className="font-mono text-[10px] tracking-[0.12em] uppercase text-urgent border border-urgent/60 px-1.5 py-0.5">
                            stale
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-foreground text-base font-medium leading-tight">
                        {shortMeetingLabel(m, ev.source_type)}
                      </p>
                      <p className="mt-1 text-ink-3 text-xs">
                        {ev.proposed_count} proposals
                        {adds > 0 && ` · ${adds} add`}
                        {updates > 0 && ` · ${updates} update`}
                        {signals > 0 && ` · ${signals} signal`}
                        {decisions > 0 && ` · ${decisions} decision`}
                        {questions > 0 && ` · ${questions} question`}
                      </p>
                      <p className="mt-1 text-ink-3 text-xs font-mono">
                        {relativeAge(ev.ingested_at)} · by {ev.ingested_by ?? "?"}
                      </p>
                    </div>
                    <div className="text-accent text-xs font-mono uppercase tracking-[0.18em] shrink-0 pt-1">
                      review →
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
