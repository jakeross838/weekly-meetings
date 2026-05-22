// POST /v2/api/purchase-orders/upload
// Body: { payload: { byJob: { [jobKey]: PORecord[] } } }  (or the bare payload)
//
// Upserts purchase_orders by bt_po_id and replaces each PO's line items
// (delete-by-po_id + insert). Batched so a full ~1,400-PO pull is a handful
// of round-trips, not thousands.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

interface LineItem {
  bt_line_item_id: number | null;
  cost_code: string | null;
  title: string | null;
  description: string | null;
  quantity: number | null;
  unit_cost: number | null;
  amount: number | null;
  amount_paid: number | null;
  amount_billed: number | null;
  position: number;
}
interface PORecord {
  bt_po_id: number;
  job_key: string;
  bt_job_id: number | null;
  po_number: string | null;
  is_bill: boolean;
  title: string | null;
  vendor: string | null;
  bt_vendor_id: number | null;
  approval_status: string | null;
  work_status: string | null;
  paid_status: string | null;
  cost: number | null;
  amount_paid: number | null;
  amount_remaining: number | null;
  pct_paid: number | null;
  pct_remaining: number | null;
  pct_billed: number | null;
  cost_codes: string[];
  date_added: string | null;
  line_items: LineItem[];
}

function chunk<T>(arr: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
  return out;
}

export async function POST(req: NextRequest) {
  const supabase = supabaseServer();
  let body: { payload?: { byJob?: Record<string, PORecord[]> }; byJob?: Record<string, PORecord[]> };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  const byJob = body.payload?.byJob ?? body.byJob ?? {};
  const allPOs: PORecord[] = [];
  for (const pos of Object.values(byJob)) {
    if (Array.isArray(pos)) allPOs.push(...pos);
  }
  if (allPOs.length === 0) {
    return NextResponse.json({ ok: true, jobs: 0, upserted: 0, lineItems: 0, note: "empty payload" });
  }

  const scrapedAt = new Date().toISOString();
  const idByBtId = new Map<number, string>();
  const errors: string[] = [];

  // 1. Upsert POs (chunked), capturing id ⇄ bt_po_id.
  for (const c of chunk(allPOs, 400)) {
    const rows = c.map((po) => ({
      bt_po_id: po.bt_po_id,
      job_key: po.job_key,
      bt_job_id: po.bt_job_id ?? null,
      po_number: po.po_number ?? null,
      is_bill: !!po.is_bill,
      title: po.title ?? null,
      vendor: po.vendor ?? null,
      bt_vendor_id: po.bt_vendor_id ?? null,
      approval_status: po.approval_status ?? null,
      work_status: po.work_status ?? null,
      paid_status: po.paid_status ?? null,
      cost: po.cost ?? null,
      amount_paid: po.amount_paid ?? null,
      amount_remaining: po.amount_remaining ?? null,
      pct_paid: po.pct_paid ?? null,
      pct_remaining: po.pct_remaining ?? null,
      pct_billed: po.pct_billed ?? null,
      cost_codes: Array.isArray(po.cost_codes) ? po.cost_codes : [],
      date_added: po.date_added ?? null,
      scraped_at: scrapedAt,
    }));
    const { data, error } = await supabase
      .from("purchase_orders")
      .upsert(rows, { onConflict: "bt_po_id" })
      .select("id, bt_po_id");
    if (error) {
      errors.push(`po upsert: ${error.message}`);
      continue;
    }
    for (const r of data ?? []) idByBtId.set(r.bt_po_id as number, r.id as string);
  }

  // 2. Replace line items: delete for these POs, then insert fresh.
  const poIds = Array.from(idByBtId.values());
  for (const c of chunk(poIds, 200)) {
    const { error } = await supabase.from("po_line_items").delete().in("po_id", c);
    if (error) errors.push(`line delete: ${error.message}`);
  }
  const allLines: Array<Record<string, unknown>> = [];
  for (const po of allPOs) {
    const poId = idByBtId.get(po.bt_po_id);
    if (!poId) continue;
    for (const li of po.line_items ?? []) {
      allLines.push({
        po_id: poId,
        bt_line_item_id: li.bt_line_item_id ?? null,
        cost_code: li.cost_code ?? null,
        title: li.title ?? null,
        description: li.description ?? null,
        quantity: li.quantity ?? null,
        unit_cost: li.unit_cost ?? null,
        amount: li.amount ?? null,
        amount_paid: li.amount_paid ?? null,
        amount_billed: li.amount_billed ?? null,
        position: li.position ?? 0,
      });
    }
  }
  let lineItems = 0;
  for (const c of chunk(allLines, 500)) {
    const { error } = await supabase.from("po_line_items").insert(c);
    if (error) errors.push(`line insert: ${error.message}`);
    else lineItems += c.length;
  }

  return NextResponse.json({
    ok: errors.length === 0,
    jobs: Object.keys(byJob).length,
    upserted: idByBtId.size,
    lineItems,
    errors: errors.slice(0, 10),
  });
}
