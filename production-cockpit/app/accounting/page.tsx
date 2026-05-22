// /accounting — portfolio purchase-order ledger. Every job's POs in one dense,
// sortable / filterable table with committed / paid / outstanding totals,
// expandable line items, and CSV export (POs + line items). The "accounting
// view" of the cockpit; mirrors what you'd export from Buildertrend's
// accounting view, but kept in sync from the scraper.

import { supabaseServer } from "@/lib/supabase";
import { Header } from "@/components/header";
import { AccountingTable, AcctPO, AcctLine } from "./accounting-table";

export const dynamic = "force-dynamic";

// Supabase returns at most 1000 rows per request — page through with .range()
// so the whole portfolio (1,200+ POs / 2,000+ lines) loads, not just the first
// 1000.
async function fetchAll<T>(
  run: (from: number, to: number) => PromiseLike<{ data: T[] | null }>
): Promise<T[]> {
  const PAGE = 1000;
  const out: T[] = [];
  for (let from = 0; ; from += PAGE) {
    const { data } = await run(from, from + PAGE - 1);
    const rows = data ?? [];
    out.push(...rows);
    if (rows.length < PAGE) break;
  }
  return out;
}

export default async function AccountingPage() {
  const supabase = supabaseServer();

  const [pos, lines, jobsRes] = await Promise.all([
    fetchAll<Omit<AcctPO, "jobId" | "jobName">>(
      (from, to) =>
        supabase
          .from("purchase_orders")
          .select(
            "id, po_number, vendor, paid_status, approval_status, work_status, cost, amount_paid, amount_remaining, pct_billed, date_added, job_key"
          )
          .eq("hidden", false)
          .order("cost", { ascending: false })
          .range(from, to) as unknown as PromiseLike<{
          data: Omit<AcctPO, "jobId" | "jobName">[] | null;
        }>
    ),
    fetchAll<AcctLine>(
      (from, to) =>
        supabase
          .from("po_line_items")
          .select(
            "id, po_id, cost_code, title, description, quantity, unit_cost, amount, amount_paid"
          )
          .eq("hidden", false)
          .order("position", { ascending: true })
          .range(from, to) as unknown as PromiseLike<{ data: AcctLine[] | null }>
    ),
    supabase.from("jobs").select("id, name"),
  ]);

  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  // Match a PO's job_key ("Krauss-427 South Blvd…") to a job by name prefix.
  // Longest name first so a more specific job wins over a shorter prefix.
  const byLen = [...jobs].sort((a, b) => b.name.length - a.name.length);
  const jobFor = (jobKey: string): { id: string | null; name: string } => {
    const j = byLen.find((x) => jobKey.startsWith(x.name));
    return j ? { id: j.id, name: j.name } : { id: null, name: jobKey };
  };

  const enriched: AcctPO[] = pos.map((p) => {
    const j = jobFor(p.job_key);
    return { ...p, jobId: j.id, jobName: j.name };
  });

  return (
    <main className="min-h-screen bg-background pb-24">
      <Header />
      <AccountingTable pos={enriched} lines={lines} />
    </main>
  );
}
