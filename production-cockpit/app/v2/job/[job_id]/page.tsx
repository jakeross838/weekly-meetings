// v2 surface — read-only job document. Gate 2A.
//
// Reads items + decisions + open_questions for one job_id from the v2
// Supabase schema (Gates 1A–1F). Renders three sections: Flags, This Week,
// Open. No interactions. Mobile-first, max-width 720 on desktop.
//
// This route is intentionally isolated under /v2/* so it doesn't touch
// the frozen v1 cockpit at /, /pace, /selections, etc.

import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// ----- Types (defined inline; lib/types.ts is part of v1 and not modified) -----

type ItemType = "action" | "observation" | "flag";
type ItemStatus = "open" | "in_progress" | "complete" | "blocked" | "cancelled";
type ItemPriority = "urgent" | "normal";
type ItemConfidence = "high" | "medium" | "low";
type AuditState = "clean" | "needs_retry" | "needs_review" | null;

interface JobRow {
  id: string;
  name: string;
  address: string | null;
  pm_id: string | null;
  phase: string | null;
}

interface PMRow {
  id: string;
  full_name: string;
}

interface SubRow {
  id: string;
  name: string;
  trade: string | null;
}

interface LineItemRow {
  id: string;
  line_number: string | null;
  description: string | null;
}

interface PayAppRow {
  id: string;
  pay_app_number: number;
  application_date: string | null;
  contract_amount: number | string | null;
  total_completed_stored: number | string | null;
}

interface MeetingRow {
  id: string;
  meeting_date: string;
  meeting_type: "site" | "office" | null;
  job_id: string;
}

interface ItemRow {
  id: string;
  human_readable_id: string;
  job_id: string;
  type: ItemType;
  title: string;
  detail: string | null;
  sub_id: string | null;
  owner: string | null;
  pay_app_line_item_id: string | null;
  target_date: string | null;
  target_date_text: string | null;
  status: ItemStatus;
  priority: ItemPriority;
  confidence: ItemConfidence;
  source_meeting_id: string | null;
  audit_state: AuditState;
  created_at: string;
  sub: SubRow | null;
  line: LineItemRow | null;
}

// ----- Helpers -----

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function inDaysIso(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
}

function formatPayAppDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function shortMeetingLabel(m: MeetingRow): string {
  // "5/07 office" / "4/30 site"
  const d = new Date(m.meeting_date);
  const md = `${d.getUTCMonth() + 1}/${String(d.getUTCDate()).padStart(2, "0")}`;
  return `${md} ${m.meeting_type ?? ""}`.trim();
}

function relativeAge(createdAt: string): string {
  const now = Date.now();
  const t = new Date(createdAt).getTime();
  const days = Math.max(0, Math.floor((now - t) / 86_400_000));
  if (days < 7) return `${days}d`;
  if (days < 30) return `${Math.floor(days / 7)}w`;
  if (days < 365) return `${Math.floor(days / 30)}mo`;
  return `${Math.floor(days / 365)}y`;
}

function daysOpen(createdAt: string): string {
  return relativeAge(createdAt);
}

function dayOfWeek(iso: string): string {
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
    weekday: "short",
    timeZone: "UTC",
  });
}

// ----- Confidence dot -----

function ConfDot({ confidence }: { confidence: ItemConfidence }) {
  const color =
    confidence === "high"
      ? "bg-success"
      : confidence === "medium"
        ? "bg-high"
        : "bg-rule";
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full ${color}`}
      title={`confidence: ${confidence}`}
    />
  );
}

// ----- Page -----

export default async function V2JobPage({
  params,
}: {
  params: { job_id: string };
}) {
  const { job_id } = params;
  const supabase = supabaseServer();

  const [jobRes, itemsRes, payAppRes, meetingsRes, pmsRes] = await Promise.all([
    supabase
      .from("jobs")
      .select("id, name, address, pm_id, phase")
      .eq("id", job_id)
      .maybeSingle(),
    supabase
      .from("items")
      .select(
        "id, human_readable_id, job_id, type, title, detail, sub_id, owner, pay_app_line_item_id, target_date, target_date_text, status, priority, confidence, source_meeting_id, audit_state, created_at, sub:subs(id, name, trade), line:pay_app_line_items(id, line_number, description)"
      )
      .eq("job_id", job_id)
      .in("status", ["open", "in_progress", "blocked"])
      .in("audit_state", ["clean", "needs_retry"])
      .order("created_at", { ascending: true }),
    supabase
      .from("pay_apps")
      .select("id, pay_app_number, application_date, contract_amount, total_completed_stored")
      .eq("job_id", job_id)
      .order("pay_app_number", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("meetings")
      .select("id, meeting_date, meeting_type, job_id"),
    supabase.from("pms").select("id, full_name"),
  ]);

  if (!jobRes.data) {
    return (
      <main className="max-w-[480px] lg:max-w-[720px] mx-auto min-h-screen bg-background px-5 py-16">
        <h1 className="font-head text-2xl text-foreground">Job not found</h1>
        <p className="mt-2 text-ink-3 text-sm">
          No job with id <span className="font-mono">{job_id}</span>.
        </p>
      </main>
    );
  }

  const job = jobRes.data as JobRow;
  const items = (itemsRes.data as ItemRow[] | null) ?? [];
  const payApp = (payAppRes.data as PayAppRow | null) ?? null;
  const meetings = (meetingsRes.data as MeetingRow[] | null) ?? [];
  const pms = (pmsRes.data as PMRow[] | null) ?? [];
  const meetingMap = new Map(meetings.map((m) => [m.id, m]));
  const pmName = pms.find((p) => p.id === job.pm_id)?.full_name ?? null;

  // Where-we-are header summary
  let payAppSummary = "";
  if (payApp) {
    const ca = Number(payApp.contract_amount) || 0;
    const tc = Number(payApp.total_completed_stored) || 0;
    const pct = ca > 0 ? Math.round((tc / ca) * 100) : 0;
    const dateLabel = formatPayAppDate(payApp.application_date);
    payAppSummary = `${pct}% complete · Pay app #${payApp.pay_app_number}${
      dateLabel ? ` (${dateLabel})` : ""
    }`;
  } else if (job.phase) {
    payAppSummary = `Phase: ${job.phase}`;
  }

  // Section partitioning
  const today = todayIso();
  const in7 = inDaysIso(7);

  const flagSet = new Set<string>();
  const flags = items.filter((i) => {
    const isFlag =
      i.type === "flag" ||
      i.priority === "urgent" ||
      i.audit_state === "needs_retry";
    if (isFlag) flagSet.add(i.id);
    return isFlag;
  });
  flags.sort((a, b) => b.created_at.localeCompare(a.created_at));

  const thisWeekSet = new Set<string>();
  const thisWeek = items.filter((i) => {
    if (flagSet.has(i.id)) return false;
    if (!i.target_date) return false;
    if (i.target_date < today || i.target_date > in7) return false;
    thisWeekSet.add(i.id);
    return true;
  });
  thisWeek.sort((a, b) =>
    (a.target_date ?? "").localeCompare(b.target_date ?? "")
  );

  const open = items.filter(
    (i) => !flagSet.has(i.id) && !thisWeekSet.has(i.id)
  );
  open.sort((a, b) => a.created_at.localeCompare(b.created_at));

  return (
    <main className="max-w-[480px] lg:max-w-[720px] mx-auto min-h-screen bg-background pb-24">
      {/* HEADER */}
      <header className="px-5 pt-10 pb-6 border-b border-rule">
        <h1 className="font-head text-[28px] lg:text-[32px] leading-none tracking-tight text-foreground">
          {job.name}
        </h1>
        {job.address && (
          <p className="mt-1.5 text-ink-2 text-sm">{job.address}</p>
        )}
        {(pmName || payAppSummary) && (
          <p className="mt-2 text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">
            {pmName && <span>{pmName}</span>}
            {pmName && payAppSummary && <span> · </span>}
            {payAppSummary && <span>{payAppSummary}</span>}
          </p>
        )}
      </header>

      {/* FLAGS — hidden entirely when empty */}
      {flags.length > 0 && (
        <section className="px-5 pt-8" aria-labelledby="flags-heading">
          <SectionHeading id="flags-heading">Flags · {flags.length}</SectionHeading>
          <ul className="space-y-3">
            {flags.map((f) => (
              <FlagRowView
                key={f.id}
                item={f}
                meeting={f.source_meeting_id ? meetingMap.get(f.source_meeting_id) ?? null : null}
              />
            ))}
          </ul>
        </section>
      )}

      {/* THIS WEEK */}
      <section className="px-5 pt-8" aria-labelledby="this-week-heading">
        <SectionHeading id="this-week-heading">
          This Week · {thisWeek.length}
        </SectionHeading>
        {thisWeek.length === 0 ? (
          <p className="text-ink-3 text-sm py-2">Nothing committed this week</p>
        ) : (
          <ul className="space-y-3">
            {thisWeek.map((t) => (
              <RowView
                key={t.id}
                item={t}
                meeting={t.source_meeting_id ? meetingMap.get(t.source_meeting_id) ?? null : null}
                rightSlot={
                  t.target_date ? (
                    <span className="text-ink-2 text-xs font-mono">
                      {dayOfWeek(t.target_date)}
                    </span>
                  ) : null
                }
              />
            ))}
          </ul>
        )}
      </section>

      {/* OPEN */}
      <section className="px-5 pt-8" aria-labelledby="open-heading">
        <SectionHeading id="open-heading">Open · {open.length}</SectionHeading>
        {open.length === 0 ? (
          <p className="text-ink-3 text-sm py-2">All caught up</p>
        ) : (
          <>
            <ul className="space-y-3">
              {open.slice(0, 10).map((o) => (
                <RowView
                  key={o.id}
                  item={o}
                  meeting={o.source_meeting_id ? meetingMap.get(o.source_meeting_id) ?? null : null}
                  rightSlot={
                    <span className="text-ink-3 text-xs font-mono">
                      {daysOpen(o.created_at)}
                    </span>
                  }
                />
              ))}
            </ul>
            {open.length > 10 && (
              <p className="mt-5 text-center text-ink-3 text-xs font-mono uppercase tracking-[0.18em]">
                + {open.length - 10} more
              </p>
            )}
          </>
        )}
      </section>
    </main>
  );
}

// ----- View pieces -----

function SectionHeading({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  return (
    <h2
      id={id}
      className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-4"
    >
      {children}
    </h2>
  );
}

function FlagRowView({
  item,
  meeting,
}: {
  item: ItemRow;
  meeting: MeetingRow | null;
}) {
  const dotColor =
    item.priority === "urgent" && item.audit_state === "needs_retry"
      ? "bg-urgent"
      : item.priority === "urgent"
        ? "bg-urgent"
        : "bg-high";
  const meta: string[] = [];
  if (meeting) meta.push(`from ${shortMeetingLabel(meeting)}`);
  if (item.sub?.name) meta.push(item.sub.name);
  if (item.line?.description) meta.push(item.line.description);

  return (
    <li className="py-2 lg:py-1.5 min-h-[44px]">
      <div className="flex gap-3 items-start">
        <span
          className={`mt-1.5 inline-block w-2 h-2 rounded-full shrink-0 ${dotColor}`}
        />
        <div className="flex-1 min-w-0">
          <p className="text-foreground text-sm leading-snug font-medium">
            {item.title}
          </p>
          {meta.length > 0 && (
            <p className="mt-1 text-ink-3 text-xs">
              {meta.join(" · ")}
            </p>
          )}
        </div>
        <span className="text-ink-3 text-xs font-mono shrink-0 pt-0.5">
          {relativeAge(item.created_at)}
        </span>
      </div>
    </li>
  );
}

function RowView({
  item,
  meeting,
  rightSlot,
}: {
  item: ItemRow;
  meeting: MeetingRow | null;
  rightSlot: React.ReactNode;
}) {
  const meta: string[] = [];
  if (item.sub?.name) meta.push(item.sub.name);
  if (item.line?.description) meta.push(item.line.description);
  if (meta.length === 0 && meeting) meta.push(`from ${shortMeetingLabel(meeting)}`);

  return (
    <li className="py-2 lg:py-1.5 min-h-[44px]">
      <div className="flex gap-3 items-start">
        {/* Empty checkbox affordance (not functional in this gate) */}
        <span
          className="mt-0.5 inline-block w-4 h-4 border border-rule shrink-0"
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <p className="text-foreground text-sm leading-snug">
            {item.title}
          </p>
          {meta.length > 0 && (
            <p className="mt-1 text-ink-3 text-xs">{meta.join(" · ")}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0 pt-0.5">
          {rightSlot}
          <ConfDot confidence={item.confidence} />
        </div>
      </div>
    </li>
  );
}
