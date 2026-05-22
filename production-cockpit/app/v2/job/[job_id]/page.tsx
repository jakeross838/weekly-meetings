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
import { EditableText } from "@/components/editable-text";
import { DeleteButton } from "@/components/delete-button";
import {
  JobSummaryPanel,
  JobSummary,
  SummaryMeta,
} from "./job-summary-panel";

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

function inDaysIso(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
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

  if (!jobRes.data) {
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
        .select("description, scheduled_value, total_completed")
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
  const poWithLines = purchaseOrders.map((po) => ({
    po,
    lines: poLinesByPo.get(po.id) ?? [],
  }));
  const poTotalCost = purchaseOrders.reduce(
    (s, p) => s + (Number(p.cost) || 0),
    0
  );
  const poOutstanding = purchaseOrders.reduce(
    (s, p) => s + (Number(p.amount_remaining) || 0),
    0
  );

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
  const in7 = inDaysIso(7);
  const in60 = inDaysIso(60);

  // 1. Today — past-due, carryover ≥2, or due in next 7 days
  const todayRows = actionable.filter((r) => {
    if (r.target_date && r.target_date < today) return true;
    if (r.carryover_count >= 2) return true;
    if (r.target_date && r.target_date >= today && r.target_date <= in7) return true;
    return false;
  });
  todayRows.sort((a, b) =>
    (a.target_date ?? "9999").localeCompare(b.target_date ?? "9999")
  );

  const usedKeys = new Set(todayRows.map((r) => `${r.source}:${r.id}`));

  // 2. Soon — due 8..60 days out
  const soonRows = actionable.filter(
    (r) =>
      !usedKeys.has(`${r.source}:${r.id}`) &&
      r.target_date &&
      r.target_date > in7 &&
      r.target_date <= in60
  );
  soonRows.sort((a, b) =>
    (a.target_date ?? "").localeCompare(b.target_date ?? "")
  );
  soonRows.forEach((r) => usedKeys.add(`${r.source}:${r.id}`));

  // 3. Open — no date (or >60d)
  const openRows = actionable.filter(
    (r) => !usedKeys.has(`${r.source}:${r.id}`)
  );
  openRows.sort((a, b) => a.created_at.localeCompare(b.created_at));

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
      />

      <PurchaseOrders
        pos={poWithLines}
        totalCost={poTotalCost}
        outstanding={poOutstanding}
      />

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

      <Section title="Today" rows={todayRows} today={today} subs={subs} highlight />
      <Section title="Soon" rows={soonRows} today={today} subs={subs} />
      <Section title="Open" rows={openRows} today={today} subs={subs} hideRightSlot />

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

// One editable PO field rendered as a label/value row in the PO body's
// definition list. Edits append the field to manually_edited_fields server-side
// so the next scrape won't clobber them.
function POField({
  label,
  poId,
  field,
  value,
  type,
  display,
}: {
  label: string;
  poId: string;
  field: string;
  value: string | number | null;
  type?: "text" | "money";
  display?: string;
}) {
  return (
    <>
      <dt className="self-center font-mono text-[9px] uppercase tracking-wider text-ink-3">
        {label}
      </dt>
      <dd className="min-w-0">
        <EditableText
          value={value}
          field={field}
          endpoint={`/v2/api/purchase-orders/${poId}/edit`}
          type={type}
          display={display}
          placeholder={label.toLowerCase()}
          className="text-foreground"
        />
      </dd>
    </>
  );
}

// Purchase orders for a job — committed costs, outstanding, and the line-item
// breakdown (nested <details>: PO section → each PO → its lines). Renders
// nothing when the job has no POs.
function PurchaseOrders({
  pos,
  totalCost,
  outstanding,
}: {
  pos: { po: POForJob; lines: POLine[] }[];
  totalCost: number;
  outstanding: number;
}) {
  if (pos.length === 0) return null;
  const paid = totalCost - outstanding;
  return (
    <section className="px-5 pt-2">
      <details className="border border-rule p-4">
        <summary className="cursor-pointer flex items-baseline justify-between gap-3">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Purchase orders · {pos.length}
          </h2>
          <span className="font-mono text-sm text-foreground tabular-nums">
            {fmtMoney(outstanding)}{" "}
            <span className="text-ink-3 text-xs">left</span>
          </span>
        </summary>
        <p className="mt-2 text-ink-3 text-xs">
          {fmtMoney(totalCost)} committed · {fmtMoney(paid)} paid ·{" "}
          {fmtMoney(outstanding)} outstanding
        </p>
        <ul className="mt-3 space-y-2">
          {pos.map(({ po, lines }) => {
            const out = Number(po.amount_remaining) || 0;
            return (
              <li key={po.id} className="border-t border-rule-soft pt-2">
                <details>
                  <summary className="cursor-pointer flex items-baseline justify-between gap-3">
                    <span className="min-w-0 flex-1">
                      <span className="font-mono text-[11px] text-ink-3">
                        {po.po_number ?? "PO"}
                      </span>{" "}
                      <span className="text-foreground text-sm">
                        {po.title ?? "—"}
                      </span>
                      <span className="block text-ink-3 text-xs truncate">
                        {po.vendor ?? "—"}
                        {po.paid_status ? ` · ${po.paid_status}` : ""}
                      </span>
                    </span>
                    <span className="shrink-0 text-right font-mono text-xs tabular-nums">
                      <span className="text-foreground">
                        {fmtMoney(Number(po.cost) || 0)}
                      </span>
                      {out > 0 && (
                        <span className="block text-urgent">
                          {fmtMoney(out)} left
                        </span>
                      )}
                    </span>
                  </summary>

                  {/* Editable PO fields live in the body — clicking an input
                      inside <summary> would fight the open/close toggle. */}
                  <dl className="mt-2 grid grid-cols-[3.5rem_1fr] items-baseline gap-x-2 gap-y-1 pl-1 text-xs">
                    <POField label="Title" poId={po.id} field="title" value={po.title} />
                    <POField label="Vendor" poId={po.id} field="vendor" value={po.vendor} />
                    <POField
                      label="Cost"
                      poId={po.id}
                      field="cost"
                      value={po.cost}
                      type="money"
                      display={fmtMoney(Number(po.cost) || 0)}
                    />
                    <POField
                      label="Status"
                      poId={po.id}
                      field="paid_status"
                      value={po.paid_status}
                    />
                  </dl>
                  <div className="mt-1.5 pl-1">
                    <DeleteButton
                      endpoint={`/v2/api/purchase-orders/${po.id}/delete`}
                      label={`PO ${po.po_number ?? ""}`.trim()}
                      confirmLabel="Delete this PO?"
                    />
                  </div>

                  {lines.length > 0 ? (
                    <ul className="mt-2 space-y-1 border-t border-rule-soft pt-2 pl-1">
                      {lines.map((li) => (
                        <li
                          key={li.id}
                          className="flex items-baseline justify-between gap-2 text-xs"
                        >
                          <span className="min-w-0 flex-1 text-ink-2">
                            {li.cost_code && (
                              <span className="text-ink-3">{li.cost_code} · </span>
                            )}
                            <EditableText
                              value={li.title}
                              display={li.title || li.description || "—"}
                              field="title"
                              endpoint={`/v2/api/po-line-items/${li.id}/edit`}
                              placeholder="line item"
                            />
                            {li.quantity != null && li.unit_cost != null && (
                              <span className="text-ink-3">
                                {" "}
                                ({li.quantity} × {fmtMoney(Number(li.unit_cost) || 0)})
                              </span>
                            )}
                          </span>
                          <EditableText
                            value={li.amount}
                            type="money"
                            display={fmtMoney(Number(li.amount) || 0)}
                            field="amount"
                            endpoint={`/v2/api/po-line-items/${li.id}/edit`}
                            className="shrink-0 font-mono tabular-nums text-ink-2"
                            inputClassName="bg-paper border border-ink px-1 py-0.5 text-xs text-ink focus:outline-none w-20"
                          />
                          <DeleteButton
                            endpoint={`/v2/api/po-line-items/${li.id}/delete`}
                            label="line item"
                          />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 border-t border-rule-soft pt-2 pl-1 text-ink-3 text-xs">
                      {(po.cost_codes ?? []).join(", ") || "No line items."}
                    </p>
                  )}
                </details>
              </li>
            );
          })}
        </ul>
      </details>
    </section>
  );
}

function fmtMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
}

// Contract progress from the latest pay app (schedule of values). Renders
// nothing when the job has no pay app loaded, so it's safe on every job.
function PayAppProgress({
  pct,
  scheduled,
  completed,
  lines,
}: {
  pct: number | null;
  scheduled: number;
  completed: number;
  lines: { description: string; sched: number; comp: number; pct: number }[];
}) {
  if (pct === null || scheduled <= 0) return null;
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <section className="px-5 pt-2">
      <div className="border border-rule p-4">
        <div className="flex items-baseline justify-between">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Contract progress
          </h2>
          <span className="font-mono text-sm text-foreground tabular-nums">
            {pct.toFixed(0)}%
          </span>
        </div>
        <div className="mt-3 h-2 w-full bg-sand-2 overflow-hidden">
          <div className="h-full bg-ink" style={{ width: `${clamped}%` }} />
        </div>
        <p className="mt-2 text-ink-3 text-xs">
          {fmtMoney(completed)} of {fmtMoney(scheduled)} billed to date
        </p>

        {lines.length > 0 && (
          <details className="mt-3 border-t border-rule pt-2">
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-1">
              Cost breakdown · {lines.length}
            </summary>
            <ul className="mt-3 space-y-3">
              {lines.map((l, i) => {
                const w = Math.max(0, Math.min(100, l.pct));
                return (
                  <li key={i}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-foreground text-xs truncate">
                        {l.description}
                      </span>
                      <span className="shrink-0 font-mono text-[11px] text-ink-2 tabular-nums">
                        {l.pct.toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1 h-1 w-full bg-sand-2 overflow-hidden">
                      <div className="h-full bg-accent" style={{ width: `${w}%` }} />
                    </div>
                    <p className="mt-1 font-mono text-[10px] text-ink-3 tabular-nums">
                      {fmtMoney(l.comp)} / {fmtMoney(l.sched)}
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

function Section({
  title,
  rows,
  today,
  subs,
  highlight,
  hideRightSlot,
}: {
  title: string;
  rows: RowData[];
  today: string;
  subs: { id: string; name: string }[];
  highlight?: boolean;
  hideRightSlot?: boolean;
}) {
  if (rows.length === 0) return null;
  return (
    <section className="px-5 pt-8">
      <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
        {title} · {rows.length}
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
            highlight={
              highlight && r.target_date != null && r.target_date < today
            }
            hideRightSlot={hideRightSlot}
            subs={subs}
          />
        ))}
      </ul>
    </section>
  );
}
