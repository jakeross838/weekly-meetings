// /v2/job/[job_id] — PM home page.
//
// Three sections: Today, Soon, Open. Empty sections hidden.
// Merges two underlying sources into one list:
//   • v2 items table  (job_id = slug)
//   • v1 todos table  (job = display name)
// Each row knows which table it came from so the check-off button can
// hit the right endpoint.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { OPEN_STATUSES, Status } from "@/lib/types";
import { CheckOffButton } from "./check-off-button";
import { RowClient } from "./row-client";
import { CategoryFilterPills } from "@/components/category-filter-pills";
import { AccountingTable } from "@/components/accounting-table";
import { ClientSummaryPanel } from "@/components/client-summary-panel";
import { ChangeOrdersSection, ChangeOrderRow } from "@/components/change-orders-section";
import { CATEGORIES, styleFor } from "@/lib/categories";
import {
  JobSummaryPanel,
  JobSummary,
  SummaryMeta,
} from "./job-summary-panel";
import { currentUser, canSeeJob } from "@/lib/auth";

export const dynamic = "force-dynamic";

// Normalized row shape — both items and todos collapse into this.
interface RowData {
  id: string;
  source: "item" | "todo";
  title: string;
  sub_id: string | null;
  sub_name: string | null;
  owner: string | null;
  target_date: string | null; // ISO yyyy-mm-dd
  category: string | null;
  carryover_count: number;
  created_at: string;
  completed_at: string | null;
  is_signal: boolean;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default async function V2JobPage({
  params,
  searchParams,
}: {
  params: { job_id: string };
  searchParams: { cat?: string };
}) {
  const { job_id } = params;
  const catFilter = searchParams.cat ?? null;
  const supabase = supabaseServer();

  // First fetch the job so we know its display name (todos.job uses
  // display name like "Krauss" while jobs.id is the slug "krauss").
  const jobRes = await supabase
    .from("jobs")
    .select("id, name, address, pm_id")
    .eq("id", job_id)
    .maybeSingle();

  // Show a single "Job not found" surface whether the job is missing OR the
  // signed-in user isn't allowed to see it. Don't leak existence to non-admins.
  const user = currentUser();
  if (!jobRes.data || !canSeeJob(user, job_id)) {
    return (
      <main className="max-w-[560px] mx-auto min-h-screen bg-background px-5 py-16">
        <h1 className="font-head text-2xl text-foreground">Job not found</h1>
        <p className="mt-2 text-ink-3 text-sm">
          No job with id <span className="font-mono">{job_id}</span>.
        </p>
      </main>
    );
  }

  const job = jobRes.data as {
    id: string;
    name: string;
    address: string | null;
    pm_id: string | null;
  };

  // Pull the latest job summary + daily-log photo counts in parallel
  // with the existing queries. Both tolerate missing tables/columns —
  // they just go null/zero so the panel renders an empty-state.
  const [
    itemsRes,
    todosRes,
    completedItemsRes,
    completedTodosRes,
    pendingEventsRes,
    subsRes,
    summaryRes,
    photoLogsRes,
    payAppRes,
    purchaseOrdersRes,
    changeOrdersRes,
  ] = await Promise.all([
      supabase
        .from("items")
        .select(
          "id, title, sub_id, owner, target_date, status, actionability, category, carryover_count, created_at, completed_at, sub:subs(id, name)"
        )
        .eq("job_id", job_id)
        .in("status", ["open", "in_progress", "blocked"]),
      supabase
        .from("todos")
        .select(
          "id, title, edited_title, due_date, status, sub_id, category, created_at, completed_at, sub:subs(id, name)"
        )
        .eq("job", job.name)
        .in("status", OPEN_STATUSES as Status[]),
      supabase
        .from("items")
        .select("id, title, completed_at")
        .eq("job_id", job_id)
        .eq("status", "complete")
        .gte("completed_at", new Date(Date.now() - 7 * 86_400_000).toISOString())
        .order("completed_at", { ascending: false })
        .limit(20),
      supabase
        .from("todos")
        .select("id, title, edited_title, completed_at")
        .eq("job", job.name)
        .eq("status", "COMPLETE")
        .gte("completed_at", new Date(Date.now() - 7 * 86_400_000).toISOString())
        .order("completed_at", { ascending: false })
        .limit(20),
      supabase
        .from("ingestion_events")
        .select("id, proposed_count")
        .eq("job_id", job_id)
        .in("review_state", ["pending", "in_review"]),
      supabase.from("subs").select("id, name").eq("hidden", false).order("name"),
      // F9 — latest job_summaries row for this job. Tolerates missing table.
      supabase
        .from("job_summaries")
        .select(
          "summary, generated_at, last_data_through, log_count, photo_count, open_todo_count, done_todo_count, model, elapsed_ms"
        )
        .eq("job_id", job_id)
        .order("generated_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
      // Daily logs for this job, restricted to ones with photos — used
      // to compute pending vs. analyzed counts for the summary panel.
      supabase
        .from("daily_logs")
        .select("id, photo_urls, photo_summary")
        .ilike("job_key", `${job.name}%`)
        .not("photo_urls", "is", null)
        .limit(500),
      // Pay-app backbone — the schedule of values gives a real contract
      // % complete. Only ~5 jobs have a pay app loaded; tolerate absence.
      supabase
        .from("pay_app_line_items")
        .select("description, division, scheduled_value, total_completed")
        .eq("job_id", job_id),
      // Purchase orders for this job (committed costs + outstanding). Matched
      // by job_key prefix like the daily logs. Tolerates the table being absent.
      supabase
        .from("purchase_orders")
        .select(
          "id, po_number, title, vendor, approval_status, work_status, paid_status, cost, amount_paid, amount_remaining, pct_billed, cost_codes, date_added"
        )
        .ilike("job_key", `${job.name}%`)
        .eq("hidden", false)
        .order("cost", { ascending: false }),
      // Change orders for this job (matched by job_key prefix like POs).
      supabase
        .from("change_orders")
        .select("id, co_number, title, status, owner_price, date_approved")
        .ilike("job_key", `${job.name}%`)
        .eq("hidden", false)
        .order("date_added", { ascending: false }),
    ]);

  const pendingEvents = (pendingEventsRes.data ?? []) as {
    id: string;
    proposed_count: number;
  }[];

  type RawItem = {
    id: string;
    title: string;
    sub_id: string | null;
    owner: string | null;
    target_date: string | null;
    actionability: "actionable" | "signal" | null;
    category: string | null;
    carryover_count: number | null;
    created_at: string;
    completed_at: string | null;
    sub: { id: string; name: string } | null;
  };
  type RawTodo = {
    id: string;
    title: string;
    edited_title: string | null;
    due_date: string | null;
    sub_id: string | null;
    category: string | null;
    created_at: string;
    completed_at: string | null;
    sub: { id: string; name: string } | null;
  };

  const subs = (subsRes.data ?? []) as { id: string; name: string }[];

  // F9 — summary + photo-status derivation. Both pieces are graceful:
  // if the table doesn't exist, summary is null, photoLogs is empty.
  const summaryRow =
    summaryRes && !summaryRes.error
      ? (summaryRes.data as {
          summary: JobSummary;
          generated_at: string;
          last_data_through: string | null;
          log_count: number;
          photo_count: number;
          open_todo_count: number;
          done_todo_count: number;
          model: string | null;
          elapsed_ms: number | null;
        } | null)
      : null;
  const initialSummary: JobSummary | null = summaryRow?.summary ?? null;
  const initialMeta: SummaryMeta | null = summaryRow
    ? {
        generated_at: summaryRow.generated_at,
        log_count: summaryRow.log_count,
        photo_count: summaryRow.photo_count,
        open_todo_count: summaryRow.open_todo_count,
        done_todo_count: summaryRow.done_todo_count,
        last_data_through: summaryRow.last_data_through,
        model: summaryRow.model ?? undefined,
        elapsed_ms: summaryRow.elapsed_ms ?? undefined,
      }
    : null;
  const photoLogs =
    photoLogsRes && !photoLogsRes.error
      ? ((photoLogsRes.data ?? []) as {
          id: string;
          photo_urls: unknown;
          photo_summary: unknown;
        }[])
      : [];
  let totalPhotos = 0;
  let initialPendingPhotos = 0;
  for (const l of photoLogs) {
    const urls = Array.isArray(l.photo_urls) ? l.photo_urls : [];
    if (urls.length === 0) continue;
    totalPhotos += urls.length;
    if (l.photo_summary == null) initialPendingPhotos += urls.length;
  }

  // Pay-app contract progress (graceful: empty when no pay app loaded).
  const payAppLines =
    payAppRes && !payAppRes.error
      ? ((payAppRes.data ?? []) as {
          description: string | null;
          division: string | null;
          scheduled_value: number | null;
          total_completed: number | null;
        }[])
      : [];
  let payScheduled = 0;
  let payCompleted = 0;
  for (const l of payAppLines) {
    payScheduled += Number(l.scheduled_value) || 0;
    payCompleted += Number(l.total_completed) || 0;
  }
  const payPct = payScheduled > 0 ? (payCompleted / payScheduled) * 100 : null;
  // Contract lines (scheduled > 0), biggest first — the breakdown rows.
  const payContractLines = payAppLines
    .map((l) => {
      const sched = Number(l.scheduled_value) || 0;
      const comp = Number(l.total_completed) || 0;
      return {
        description: l.description ?? "—",
        division: l.division ?? null,
        sched,
        comp,
        pct: sched > 0 ? (comp / sched) * 100 : 0,
      };
    })
    .filter((l) => l.sched > 0)
    .sort((a, b) => b.sched - a.sched);

  // Purchase orders + their line items (committed costs / outstanding).
  const purchaseOrders =
    purchaseOrdersRes && !purchaseOrdersRes.error
      ? ((purchaseOrdersRes.data ?? []) as POForJob[])
      : [];
  const poLinesByPo = new Map<string, POLine[]>();
  if (purchaseOrders.length > 0) {
    const liRes = await supabase
      .from("po_line_items")
      .select(
        "id, po_id, cost_code, title, description, quantity, unit_cost, amount, amount_paid"
      )
      .eq("hidden", false)
      .in(
        "po_id",
        purchaseOrders.map((p) => p.id)
      )
      .order("position", { ascending: true });
    for (const li of (liRes.data ?? []) as (POLine & { po_id: string })[]) {
      const arr = poLinesByPo.get(li.po_id) ?? [];
      arr.push(li);
      poLinesByPo.set(li.po_id, arr);
    }
  }
  const poLines = purchaseOrders.flatMap((po) =>
    (poLinesByPo.get(po.id) ?? []).map((l) => ({ ...l, po_id: po.id }))
  );
  // Open-PO outstanding for this job — surfaced on the pay app (committed cost
  // still owed, alongside what's billed).
  const openPoOutstanding = purchaseOrders.reduce(
    (s, p) => s + (Number(p.amount_remaining) || 0),
    0
  );
  const openPoCount = purchaseOrders.filter(
    (p) => (Number(p.amount_remaining) || 0) > 0
  ).length;
  const changeOrders = (changeOrdersRes.data ?? []) as ChangeOrderRow[];

  const items = ((itemsRes.data ?? []) as unknown) as RawItem[];
  const todos = ((todosRes.data ?? []) as unknown) as RawTodo[];
  const completedItems = (completedItemsRes.data ?? []) as {
    id: string;
    title: string;
    completed_at: string;
  }[];
  const completedTodos = ((completedTodosRes.data ?? []) as unknown) as {
    id: string;
    title: string;
    edited_title: string | null;
    completed_at: string;
  }[];

  // Normalize both sources into RowData
  const itemRows: RowData[] = items.map((i) => ({
    id: i.id,
    source: "item",
    title: i.title,
    sub_id: i.sub_id,
    sub_name: i.sub?.name ?? null,
    owner: i.owner,
    target_date: i.target_date,
    category: i.category,
    carryover_count: i.carryover_count ?? 0,
    created_at: i.created_at,
    completed_at: i.completed_at,
    is_signal: i.actionability === "signal",
  }));
  const todoRows: RowData[] = todos.map((t) => ({
    id: t.id,
    source: "todo",
    title: t.edited_title ?? t.title,
    sub_id: t.sub_id,
    sub_name: t.sub?.name ?? null,
    owner: null,
    target_date: t.due_date,
    category: t.category,
    carryover_count: 0,
    created_at: t.created_at,
    completed_at: t.completed_at,
    is_signal: false,
  }));

  const allActionable = [...itemRows, ...todoRows].filter((r) => !r.is_signal);
  const availableCategories = Array.from(
    new Set(allActionable.map((r) => r.category).filter(Boolean) as string[])
  ).sort();
  const actionable = catFilter
    ? allActionable.filter((r) => r.category === catFilter)
    : allActionable;

  const today = todayIso();

  // Group actionable rows by category (canonical CATEGORIES order; uncategorized
  // last). Within a category, soonest / past-due first, then undated by age — so
  // urgency still reads top-to-bottom inside each bundle.
  const UNCATEGORIZED = "(uncategorized)";
  const byCategory = new Map<string, RowData[]>();
  for (const r of actionable) {
    const key = r.category || UNCATEGORIZED;
    const arr = byCategory.get(key) ?? [];
    arr.push(r);
    byCategory.set(key, arr);
  }
  for (const arr of Array.from(byCategory.values())) {
    arr.sort((a, b) => {
      const ad = a.target_date ?? "9999-99-99";
      const bd = b.target_date ?? "9999-99-99";
      if (ad !== bd) return ad.localeCompare(bd);
      return a.created_at.localeCompare(b.created_at);
    });
  }
  const catRank = (c: string) => {
    const i = (CATEGORIES as readonly string[]).indexOf(c);
    return i === -1 ? 900 : i;
  };
  const orderedCategories = Array.from(byCategory.keys()).sort((a, b) => {
    const ra = a === UNCATEGORIZED ? 1000 : catRank(a);
    const rb = b === UNCATEGORIZED ? 1000 : catRank(b);
    return ra - rb || a.localeCompare(b);
  });

  // Done — merge completed items + todos within last 7 days
  const completedRows = [
    ...completedItems.map((i) => ({
      id: i.id,
      source: "item" as const,
      title: i.title,
      completed_at: i.completed_at,
    })),
    ...completedTodos.map((t) => ({
      id: t.id,
      source: "todo" as const,
      title: t.edited_title ?? t.title,
      completed_at: t.completed_at,
    })),
  ];
  completedRows.sort((a, b) => b.completed_at.localeCompare(a.completed_at));

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <header className="px-5 pt-8 pb-6">
        <Link
          href="/"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Jobs
        </Link>
        <div className="mt-4 flex flex-col items-start gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
          <div className="flex-1 min-w-0">
            <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
              {job.name}
            </h1>
            {job.address && (
              <p className="mt-1.5 text-ink-3 text-sm">{job.address}</p>
            )}
          </div>
          {pendingEvents.length > 0 && (
            <Link
              href={`/v2/review`}
              className="self-start shrink-0 text-[10px] font-mono uppercase tracking-[0.12em] text-urgent border border-urgent/60 px-2 py-1 hover:bg-urgent hover:text-paper transition-colors"
            >
              {pendingEvents.length} plaud transcript{pendingEvents.length === 1 ? "" : "s"} to approve
            </Link>
          )}
        </div>
      </header>

      {/* F9 — Claude-generated job summary document + photo analysis status. */}
      <JobSummaryPanel
        jobId={job.id}
        jobName={job.name}
        initialSummary={initialSummary}
        initialMeta={initialMeta}
        initialPendingPhotos={initialPendingPhotos}
        totalPhotos={totalPhotos}
      />

      <PayAppProgress
        pct={payPct}
        scheduled={payScheduled}
        completed={payCompleted}
        lines={payContractLines}
        openPoOutstanding={openPoOutstanding}
        openPoCount={openPoCount}
      />

      <ClientSummaryPanel jobId={job.id} />

      {purchaseOrders.length > 0 && (
        <section className="px-5 pt-2">
          <AccountingTable pos={purchaseOrders} lines={poLines} jobName={job.name} />
        </section>
      )}

      <ChangeOrdersSection cos={changeOrders} />

      <CategoryFilterPills
        basePath={`/v2/job/${job_id}`}
        activeCategory={catFilter}
        availableCategories={availableCategories}
      />

      {actionable.length === 0 && (
        <p className="px-5 pt-8 text-ink-3 text-sm">
          {catFilter ? `No ${catFilter} items.` : "All clear."}
        </p>
      )}

      {orderedCategories.map((cat) => (
        <CategorySection
          key={cat}
          category={cat}
          rows={byCategory.get(cat)!}
          today={today}
          subs={subs}
        />
      ))}

      {completedRows.length > 0 && (
        <section className="px-5 pt-10">
          <details>
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-2">
              Done this week · {completedRows.length}
            </summary>
            <ul className="mt-2 space-y-1.5">
              {completedRows.map((r) => (
                <li
                  key={`${r.source}:${r.id}`}
                  className="flex gap-3 items-baseline py-1 min-h-[32px]"
                >
                  <CheckOffButton itemId={r.id} source={r.source} completed />
                  <span className="text-ink-3 text-sm line-through">
                    {r.title}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </main>
  );
}

type POForJob = {
  id: string;
  po_number: string | null;
  title: string | null;
  vendor: string | null;
  approval_status: string | null;
  work_status: string | null;
  paid_status: string | null;
  cost: number | null;
  amount_paid: number | null;
  amount_remaining: number | null;
  pct_billed: number | null;
  cost_codes: string[] | null;
  date_added: string | null;
};
type POLine = {
  id: string;
  cost_code: string | null;
  title: string | null;
  description: string | null;
  quantity: number | null;
  unit_cost: number | null;
  amount: number | null;
  amount_paid: number | null;
};


function fmtMoney(n: number): string {
  // Exact dollars — pay-app figures are read precisely, never rounded to K/M.
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

// Contract progress from the latest pay app (schedule of values). Renders
// nothing when the job has no pay app loaded, so it's safe on every job.
// Bar/text tone by billed %: amber = in progress/open, green = complete,
// red = overage (billed past the scheduled value).
function barTone(pct: number): { bar: string; text: string } {
  if (pct > 100.5) return { bar: "bg-urgent", text: "text-urgent" };
  if (pct >= 99.5) return { bar: "bg-success", text: "text-success" };
  return { bar: "bg-high", text: "text-ink-2" };
}

function PayAppProgress({
  pct,
  scheduled,
  completed,
  lines,
  openPoOutstanding,
  openPoCount,
}: {
  pct: number | null;
  scheduled: number;
  completed: number;
  lines: {
    description: string;
    division: string | null;
    sched: number;
    comp: number;
    pct: number;
  }[];
  openPoOutstanding: number;
  openPoCount: number;
}) {
  if (pct === null || scheduled <= 0) return null;
  const clamped = Math.max(0, Math.min(100, pct));
  const tone = barTone(pct);
  const over = completed - scheduled;
  return (
    <section className="px-5 pt-2">
      <div className="border border-rule p-4">
        <div className="flex items-baseline justify-between">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Contract progress
          </h2>
          <span className={`font-mono text-sm tabular-nums ${tone.text}`}>
            {pct.toFixed(0)}%
          </span>
        </div>
        <div className="mt-3 h-2 w-full bg-sand-2 overflow-hidden">
          <div className={`h-full ${tone.bar}`} style={{ width: `${clamped}%` }} />
        </div>
        <p className="mt-2 text-ink-3 text-xs">
          {fmtMoney(completed)} of {fmtMoney(scheduled)} billed to date
          {over > 0 && (
            <span className="text-urgent"> · {fmtMoney(over)} over</span>
          )}
        </p>
        {openPoCount > 0 && (
          <p className="mt-1 font-mono text-[10px] tracking-[0.14em] uppercase text-ink-3">
            <span className="text-urgent">{fmtMoney(openPoOutstanding)}</span> open
            on {openPoCount} PO{openPoCount === 1 ? "" : "s"}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[9px] uppercase tracking-wider text-ink-3">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 bg-high" /> in progress
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 bg-success" /> complete
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 bg-urgent" /> overage
          </span>
        </div>

        {lines.length > 0 && (
          <details className="mt-3 border-t border-rule pt-2">
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-1">
              Cost breakdown · {lines.length}
            </summary>
            <ul className="mt-3 space-y-3">
              {lines.map((l, i) => {
                const w = Math.max(0, Math.min(100, l.pct));
                const lt = barTone(l.pct);
                const lineOver = l.comp - l.sched;
                return (
                  <li key={i}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-foreground text-xs truncate">
                        {l.division && (
                          <span className="font-mono text-ink-3">{l.division} · </span>
                        )}
                        {l.description}
                      </span>
                      <span
                        className={`shrink-0 font-mono text-[11px] tabular-nums ${lt.text}`}
                      >
                        {l.pct.toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1 h-1 w-full bg-sand-2 overflow-hidden">
                      <div className={`h-full ${lt.bar}`} style={{ width: `${w}%` }} />
                    </div>
                    <p className="mt-1 font-mono text-[10px] text-ink-3 tabular-nums">
                      {fmtMoney(l.comp)} / {fmtMoney(l.sched)}
                      {lineOver > 0 && (
                        <span className="text-urgent"> · {fmtMoney(lineOver)} over</span>
                      )}
                    </p>
                  </li>
                );
              })}
            </ul>
          </details>
        )}
      </div>
    </section>
  );
}

// One category bundle on the job page: a colored category header + that
// category's actionable rows (past-due first, highlighted). Categories render
// in canonical order; uncategorized last.
function CategorySection({
  category,
  rows,
  today,
  subs,
}: {
  category: string;
  rows: RowData[];
  today: string;
  subs: { id: string; name: string }[];
}) {
  if (rows.length === 0) return null;
  const isUncat = category === "(uncategorized)";
  return (
    <section className="px-5 pt-8">
      <h2 className="mb-3 flex items-center gap-2">
        <span
          className={
            "font-mono text-[10px] tracking-[0.18em] uppercase px-2 py-0.5 " +
            (isUncat ? "text-ink-3 bg-sand-2" : styleFor(category))
          }
        >
          {isUncat ? "Uncategorized" : category}
        </span>
        <span className="font-mono text-[10px] tabular-nums text-ink-3">
          {rows.length}
        </span>
      </h2>
      <ul className="space-y-2">
        {rows.map((r) => (
          <RowClient
            key={`${r.source}:${r.id}`}
            id={r.id}
            source={r.source}
            title={r.title}
            sub_id={r.sub_id}
            sub_name={r.sub_name}
            owner={r.owner}
            target_date={r.target_date}
            category={r.category}
            today={today}
            highlight={r.target_date != null && r.target_date < today}
            subs={subs}
          />
        ))}
      </ul>
    </section>
  );
}
