// /v2/job/[job_id] — rebuilt job page (Gate 2B).
//
// Seven sections: Slipping, This Week, Next Up, Coming, Open, Signals, Recently Done.
// Reads from items table (only contains Jake-approved rows after Gate 2B).
// Shows "pending review" badge if there are ingestion_events for this job
// in review_state='pending'/'in_review'.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { CheckOffButton } from "./check-off-button";

export const dynamic = "force-dynamic";

type ItemType = "action" | "observation" | "flag";
type ItemStatus = "open" | "in_progress" | "complete" | "blocked" | "cancelled";

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
  priority: "urgent" | "normal";
  confidence: "high" | "medium" | "low";
  source_meeting_id: string | null;
  audit_state: string | null;
  actionability: "actionable" | "signal" | null;
  carryover_count: number | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  sub: { id: string; name: string; trade: string | null } | null;
  line: { id: string; line_number: string | null; description: string | null } | null;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function inDaysIso(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  return Math.floor((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);
}

function relativeAge(iso: string): string {
  const days = Math.max(0, daysBetween(iso, new Date().toISOString().slice(0, 10)));
  if (days < 7) return `${days}d`;
  if (days < 30) return `${Math.floor(days / 7)}w`;
  if (days < 365) return `${Math.floor(days / 30)}mo`;
  return `${Math.floor(days / 365)}y`;
}

function dayOfWeek(iso: string): string {
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
    weekday: "short",
    timeZone: "UTC",
  });
}

function daysOut(iso: string): number {
  return daysBetween(new Date().toISOString().slice(0, 10), iso);
}

function ConfDot({ confidence }: { confidence: string }) {
  if (confidence === "high") return null;
  const color = confidence === "medium" ? "bg-high" : "bg-rule";
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full ${color}`}
      title={`confidence: ${confidence}`}
    />
  );
}

function jobLabel(jobId: string | null): string {
  if (!jobId) return "—";
  return jobId.charAt(0).toUpperCase() + jobId.slice(1);
}

export default async function V2JobPage({
  params,
}: {
  params: { job_id: string };
}) {
  const { job_id } = params;
  const supabase = supabaseServer();

  const [jobRes, itemsRes, completedRes, payAppRes, pmAssignRes, pendingEventsRes] = await Promise.all([
    supabase
      .from("jobs")
      .select("id, name, address, pm_id, phase")
      .eq("id", job_id)
      .maybeSingle(),
    supabase
      .from("items")
      .select(
        "id, human_readable_id, job_id, type, title, detail, sub_id, owner, pay_app_line_item_id, target_date, target_date_text, status, priority, confidence, source_meeting_id, audit_state, actionability, carryover_count, created_at, updated_at, completed_at, sub:subs(id, name, trade), line:pay_app_line_items(id, line_number, description)"
      )
      .eq("job_id", job_id)
      .in("status", ["open", "in_progress", "blocked"]),
    supabase
      .from("items")
      .select(
        "id, human_readable_id, job_id, type, title, status, completed_at, sub:subs(id, name)"
      )
      .eq("job_id", job_id)
      .eq("status", "complete")
      .gte("completed_at", new Date(Date.now() - 7 * 86_400_000).toISOString())
      .order("completed_at", { ascending: false })
      .limit(20),
    supabase
      .from("pay_apps")
      .select("id, pay_app_number, application_date, contract_amount, total_completed_stored")
      .eq("job_id", job_id)
      .order("pay_app_number", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("job_pm_assignments")
      .select("pm_id")
      .eq("job_id", job_id)
      .is("ended_at", null)
      .order("assigned_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("ingestion_events")
      .select("id, review_state, proposed_count")
      .eq("job_id", job_id)
      .in("review_state", ["pending", "in_review"]),
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

  const job = jobRes.data as { id: string; name: string; address: string | null; pm_id: string | null; phase: string | null };
  const items = ((itemsRes.data ?? []) as unknown) as ItemRow[];
  const completed = ((completedRes.data ?? []) as unknown) as ItemRow[];
  const payApp = payAppRes.data as { pay_app_number: number; application_date: string | null; contract_amount: number | string | null; total_completed_stored: number | string | null } | null;
  const activePm = (pmAssignRes.data?.pm_id as string | undefined) ?? job.pm_id;
  const pendingEvents = (pendingEventsRes.data ?? []) as { id: string; proposed_count: number }[];

  let pmName: string | null = null;
  if (activePm) {
    const pmR = await supabase.from("pms").select("full_name").eq("id", activePm).maybeSingle();
    pmName = (pmR.data?.full_name as string) ?? null;
  }

  let payAppSummary = "";
  if (payApp) {
    const ca = Number(payApp.contract_amount) || 0;
    const tc = Number(payApp.total_completed_stored) || 0;
    const pct = ca > 0 ? Math.round((tc / ca) * 100) : 0;
    const dateLabel = payApp.application_date
      ? new Date(payApp.application_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })
      : "";
    payAppSummary = `${pct}% complete · Pay app #${payApp.pay_app_number}${dateLabel ? ` (${dateLabel})` : ""}`;
  } else if (job.phase) {
    payAppSummary = `Phase: ${job.phase}`;
  }

  const today = todayIso();
  const in7 = inDaysIso(7);
  const in21 = inDaysIso(21);
  const in60 = inDaysIso(60);

  // Section partitioning per spec
  const actionableItems = items.filter((i) => i.actionability !== "signal");
  const signalItems = items.filter((i) => i.actionability === "signal");

  // 1. Slipping — past target_date or target_date committed >1 meeting ago and not refreshed
  const slipping = actionableItems.filter((i) => {
    if (i.target_date && i.target_date < today) return true;
    if ((i.carryover_count ?? 0) >= 2) return true;
    return false;
  });
  slipping.sort((a, b) => (a.target_date ?? "9999").localeCompare(b.target_date ?? "9999"));

  const slippingSet = new Set(slipping.map((i) => i.id));

  // 2. This Week — target_date in 0..7 days
  const thisWeek = actionableItems.filter(
    (i) => !slippingSet.has(i.id) && i.target_date && i.target_date >= today && i.target_date <= in7
  );
  thisWeek.sort((a, b) => (a.target_date ?? "").localeCompare(b.target_date ?? ""));

  const tier2Set = new Set<string>([...Array.from(slippingSet), ...thisWeek.map((i) => i.id)]);

  // 3. Next Up — target_date in 8..21 days
  const nextUp = actionableItems.filter(
    (i) => !tier2Set.has(i.id) && i.target_date && i.target_date > in7 && i.target_date <= in21
  );
  nextUp.sort((a, b) => (a.target_date ?? "").localeCompare(b.target_date ?? ""));

  const tier3Set = new Set<string>([...Array.from(tier2Set), ...nextUp.map((i) => i.id)]);

  // 4. Coming — target_date in 22..60 days (collapsed)
  const coming = actionableItems.filter(
    (i) => !tier3Set.has(i.id) && i.target_date && i.target_date > in21 && i.target_date <= in60
  );
  coming.sort((a, b) => (a.target_date ?? "").localeCompare(b.target_date ?? ""));

  const tier4Set = new Set<string>([...Array.from(tier3Set), ...coming.map((i) => i.id)]);

  // 5. Open — no target_date (or >60d)
  const open = actionableItems.filter((i) => !tier4Set.has(i.id));
  open.sort((a, b) => a.created_at.localeCompare(b.created_at));

  // Sub map for inline display
  const subMap = new Map<string, string>();
  for (const i of items) if (i.sub) subMap.set(i.sub.id, i.sub.name);

  const pendingProposals = pendingEvents.reduce((n, e) => n + (e.proposed_count ?? 0), 0);

  return (
    <main className="max-w-[480px] lg:max-w-[720px] mx-auto min-h-screen bg-background pb-24">
      {/* HEADER */}
      <header className="px-5 pt-10 pb-6 border-b border-rule">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
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
          </div>
          {pendingEvents.length > 0 && (
            <Link
              href={`/v2/review`}
              className="shrink-0 text-[10px] font-mono uppercase tracking-[0.12em] text-urgent border border-urgent/60 px-2 py-1 hover:bg-urgent hover:text-paper transition-colors"
            >
              {pendingEvents.length} pending review · {pendingProposals} proposals
            </Link>
          )}
        </div>
      </header>

      {/* 1. Slipping */}
      <Section
        title="Slipping"
        count={slipping.length}
        emptyText="Nothing slipping. Good."
        hideWhenEmpty={false}
      >
        {slipping.map((i) => (
          <ActionRow key={i.id} item={i} rightSlot={<SlippingRightSlot item={i} />} highlight="slipping" />
        ))}
      </Section>

      {/* 2. This Week */}
      <Section
        title="This Week"
        count={thisWeek.length}
        emptyText="Nothing committed this week"
        hideWhenEmpty={false}
      >
        {thisWeek.map((i) => (
          <ActionRow
            key={i.id}
            item={i}
            rightSlot={
              i.target_date ? (
                <span className="text-ink-2 text-xs font-mono">{dayOfWeek(i.target_date)}</span>
              ) : null
            }
          />
        ))}
      </Section>

      {/* 3. Next Up */}
      <Section
        title="Next Up"
        count={nextUp.length}
        emptyText="Nothing scheduled"
        hideWhenEmpty={false}
      >
        {nextUp.map((i) => (
          <ActionRow
            key={i.id}
            item={i}
            rightSlot={
              i.target_date ? (
                <span className="text-ink-3 text-xs font-mono">
                  {daysOut(i.target_date)}d
                </span>
              ) : null
            }
          />
        ))}
      </Section>

      {/* 4. Coming — collapsed */}
      {coming.length > 0 && (
        <section className="px-5 pt-8" aria-labelledby="coming-heading">
          <SectionHeading id="coming-heading">Coming · {coming.length}</SectionHeading>
          <details className="group">
            <summary className="cursor-pointer text-accent text-sm py-2">
              Show {coming.length} item{coming.length === 1 ? "" : "s"} (22-60 days out)
            </summary>
            <ul className="mt-3 space-y-3">
              {coming.map((i) => (
                <ActionRow
                  key={i.id}
                  item={i}
                  rightSlot={
                    i.target_date ? (
                      <span className="text-ink-3 text-xs font-mono">
                        {daysOut(i.target_date)}d
                      </span>
                    ) : null
                  }
                />
              ))}
            </ul>
          </details>
        </section>
      )}

      {/* 5. Open */}
      <Section title="Open" count={open.length} emptyText="Nothing open without a date" hideWhenEmpty={false}>
        {open.slice(0, 15).map((i) => (
          <ActionRow
            key={i.id}
            item={i}
            rightSlot={<span className="text-ink-3 text-xs font-mono">{relativeAge(i.created_at)}</span>}
          />
        ))}
        {open.length > 15 && (
          <p className="mt-3 text-center text-ink-3 text-xs font-mono uppercase tracking-[0.18em]">
            + {open.length - 15} more
          </p>
        )}
      </Section>

      {/* 6. Signals — collapsed, hidden when empty */}
      {signalItems.length > 0 && (
        <section className="px-5 pt-8" aria-labelledby="signals-heading">
          <SectionHeading id="signals-heading">
            Signals · {signalItems.length}{" "}
            <span className="text-ink-3 normal-case tracking-normal">(awareness only)</span>
          </SectionHeading>
          <details className="group">
            <summary className="cursor-pointer text-accent text-sm py-2">
              Show {signalItems.length} signal{signalItems.length === 1 ? "" : "s"}
            </summary>
            <ul className="mt-3 space-y-2">
              {signalItems.map((i) => (
                <li key={i.id} className="px-3 py-2 bg-sand-2/40 border border-rule-soft">
                  <p className="text-ink-2 text-sm leading-snug">{i.title}</p>
                  <p className="mt-0.5 text-ink-3 text-xs">
                    {i.sub?.name ?? ""}
                    {i.line?.description ? `${i.sub?.name ? " · " : ""}${i.line.description}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}

      {/* 7. Recently Done — collapsed, hidden when empty */}
      {completed.length > 0 && (
        <section className="px-5 pt-8" aria-labelledby="done-heading">
          <SectionHeading id="done-heading">Recently Done · {completed.length}</SectionHeading>
          <details className="group">
            <summary className="cursor-pointer text-accent text-sm py-2">
              Show {completed.length} completed (last 7 days)
            </summary>
            <ul className="mt-3 space-y-2">
              {completed.map((i) => (
                <li key={i.id} className="px-3 py-2 text-ink-3 text-sm line-through">
                  {i.title}
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </main>
  );
}

// ----- View pieces -----

function SectionHeading({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <h2
      id={id}
      className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-4"
    >
      {children}
    </h2>
  );
}

function Section({
  title,
  count,
  emptyText,
  hideWhenEmpty,
  children,
}: {
  title: string;
  count: number;
  emptyText: string;
  hideWhenEmpty: boolean;
  children: React.ReactNode;
}) {
  if (count === 0 && hideWhenEmpty) return null;
  return (
    <section className="px-5 pt-8">
      <SectionHeading>{title} · {count}</SectionHeading>
      {count === 0 ? (
        <p className="text-ink-3 text-sm py-2">{emptyText}</p>
      ) : (
        <ul className="space-y-3">{children}</ul>
      )}
    </section>
  );
}

function SlippingRightSlot({ item }: { item: ItemRow }) {
  if (item.target_date) {
    const days = Math.abs(daysOut(item.target_date));
    return <span className="text-urgent text-xs font-mono">-{days}d</span>;
  }
  return <span className="text-urgent text-xs font-mono">stale</span>;
}

function ActionRow({
  item,
  rightSlot,
  highlight,
}: {
  item: ItemRow;
  rightSlot: React.ReactNode;
  highlight?: "slipping";
}) {
  const subLabel = item.sub?.name ?? null;
  const lineLabel = item.line?.description ?? null;
  return (
    <li
      className={`py-2 lg:py-1.5 min-h-[44px] ${highlight === "slipping" ? "border-l-2 border-urgent pl-2 -ml-2" : ""}`}
    >
      <div className="flex gap-3 items-start">
        <CheckOffButton itemId={item.id} />
        <div className="flex-1 min-w-0">
          <p className="text-foreground text-sm leading-snug">{item.title}</p>
          {(subLabel || lineLabel) && (
            <p className="mt-1 text-ink-3 text-xs">
              {subLabel ?? ""}
              {subLabel && lineLabel ? " · " : ""}
              {lineLabel ?? ""}
            </p>
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
