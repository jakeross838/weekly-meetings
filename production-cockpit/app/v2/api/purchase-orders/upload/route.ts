// POST /v2/api/purchase-orders/upload
// Body: { payload: { byJob: { [jobKey]: PORecord[] } } }  (or the bare payload)
//
// Upserts purchase_orders by bt_po_id and upserts each PO's line items by
// (po_id, bt_line_item_id). Manual-wins: rows the user has HIDDEN are left
// untouched (never resurrected), and columns listed in a row's
// manually_edited_fields are never overwritten by a re-scrape.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
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
  // Incremental flag. Set by the scraper when it skipped the per-PO
  // line-items detail call (because we already had them locally). When
  // true the upload route MUST leave this PO's existing line items
  // untouched — otherwise reconciliation would delete them all.
  line_items_unchanged?: boolean;
}

function chunk<T>(arr: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
  return out;
}

// Scraped columns only — never includes hidden / manually_edited_fields, so an
// upsert never resurrects a hidden row or stomps the manual-edit bookkeeping.
function poRow(po: PORecord, scrapedAt: string): Record<string, unknown> {
  return {
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
  };
}
function lineRow(poId: string, li: LineItem): Record<string, unknown> {
  return {
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
  };
}

export async function POST(req: NextRequest) {
  const supabase = supabaseServer();
  let body: {
    payload?: { byJob?: Record<string, PORecord[]> };
    byJob?: Record<string, PORecord[]>;
    skipLineItems?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  const byJob = body.payload?.byJob ?? body.byJob ?? {};
  // Grid-only pulls omit line items; skip all line-item reconciliation so a
  // PO-totals refresh never deletes the line items a full pull loaded earlier.
  const skipLineItems = body.skipLineItems === true;
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

  // --- existing PO manual state (edits / soft-deletes) ---
  const poEdited = new Map<number, string[]>();
  const poHidden = new Set<number>();
  for (const c of chunk(allPOs.map((p) => p.bt_po_id), 500)) {
    const { data } = await supabase
      .from("purchase_orders")
      .select("bt_po_id, manually_edited_fields, hidden")
      .in("bt_po_id", c);
    for (const r of (data ?? []) as { bt_po_id: number; manually_edited_fields: string[] | null; hidden: boolean }[]) {
      if (Array.isArray(r.manually_edited_fields) && r.manually_edited_fields.length)
        poEdited.set(r.bt_po_id, r.manually_edited_fields);
      if (r.hidden) poHidden.add(r.bt_po_id);
    }
  }

  // --- upsert POs: skip hidden entirely; omit edited columns for edited ones ---
  const cleanPOs = allPOs.filter((p) => !poHidden.has(p.bt_po_id) && !poEdited.has(p.bt_po_id));
  const editedPOs = allPOs.filter((p) => !poHidden.has(p.bt_po_id) && poEdited.has(p.bt_po_id));
  for (const c of chunk(cleanPOs, 400)) {
    const { data, error } = await supabase
      .from("purchase_orders")
      .upsert(c.map((p) => poRow(p, scrapedAt)), { onConflict: "bt_po_id" })
      .select("id, bt_po_id");
    if (error) {
      errors.push(`po upsert: ${error.message}`);
      continue;
    }
    for (const r of (data ?? []) as { id: string; bt_po_id: number }[]) idByBtId.set(r.bt_po_id, r.id);
  }
  for (const po of editedPOs) {
    const row = poRow(po, scrapedAt);
    for (const f of poEdited.get(po.bt_po_id) ?? []) delete row[f];
    const { data, error } = await supabase
      .from("purchase_orders")
      .upsert([row], { onConflict: "bt_po_id" })
      .select("id, bt_po_id");
    if (error) {
      errors.push(`po upsert(edited): ${error.message}`);
      continue;
    }
    for (const r of (data ?? []) as { id: string; bt_po_id: number }[]) idByBtId.set(r.bt_po_id, r.id);
  }

  // --- line items: reconcile only on a full (line-item) pull ---
  let lineItems = 0;
  if (!skipLineItems) {
  // --- existing line-item manual state, keyed `${po_id}|${bt_line_item_id}` ---
  const poIds = Array.from(idByBtId.values());
  const lineEdited = new Map<string, string[]>();
  const lineHidden = new Set<string>();
  const existingByPo = new Map<string, { id: string; btli: number | null; clean: boolean }[]>();
  for (const c of chunk(poIds, 200)) {
    const { data } = await supabase
      .from("po_line_items")
      .select("id, po_id, bt_line_item_id, manually_edited_fields, hidden")
      .in("po_id", c);
    for (const r of (data ?? []) as { id: string; po_id: string; bt_line_item_id: number | null; manually_edited_fields: string[] | null; hidden: boolean }[]) {
      const key = `${r.po_id}|${r.bt_line_item_id}`;
      const edited = Array.isArray(r.manually_edited_fields) && r.manually_edited_fields.length > 0;
      if (edited) lineEdited.set(key, r.manually_edited_fields as string[]);
      if (r.hidden) lineHidden.add(key);
      const arr = existingByPo.get(r.po_id) ?? [];
      arr.push({ id: r.id, btli: r.bt_line_item_id, clean: !edited && !r.hidden });
      existingByPo.set(r.po_id, arr);
    }
  }

  // --- delete only CLEAN lines BT no longer returns (preserve hidden/edited) ---
  // Skip POs flagged line_items_unchanged — the scraper didn't fetch line
  // items for them, so an empty `line_items` array doesn't mean "BT dropped
  // them," it means "we already have them." Deleting would be catastrophic.
  const toDeleteIds: string[] = [];
  for (const po of allPOs) {
    if (po.line_items_unchanged) continue;
    const poId = idByBtId.get(po.bt_po_id);
    if (!poId) continue;
    const incoming = new Set(
      (po.line_items ?? []).map((li) => li.bt_line_item_id).filter((x): x is number => x != null)
    );
    for (const ex of existingByPo.get(poId) ?? []) {
      if (ex.clean && (ex.btli == null || !incoming.has(ex.btli))) toDeleteIds.push(ex.id);
    }
  }
  for (const c of chunk(toDeleteIds, 200)) {
    const { error } = await supabase.from("po_line_items").delete().in("id", c);
    if (error) errors.push(`line delete: ${error.message}`);
  }

  // --- upsert incoming lines: skip hidden; omit edited columns ---
  // Same incremental gate: a line_items_unchanged PO contributes no rows.
  const cleanLines: Record<string, unknown>[] = [];
  const editedLineRows: Record<string, unknown>[] = [];
  for (const po of allPOs) {
    if (po.line_items_unchanged) continue;
    const poId = idByBtId.get(po.bt_po_id);
    if (!poId) continue;
    for (const li of po.line_items ?? []) {
      const key = `${poId}|${li.bt_line_item_id}`;
      if (lineHidden.has(key)) continue; // preserve user delete
      const row = lineRow(poId, li);
      if (lineEdited.has(key)) {
        for (const f of lineEdited.get(key) ?? []) delete row[f];
        editedLineRows.push(row);
      } else {
        cleanLines.push(row);
      }
    }
  }
  for (const c of chunk(cleanLines, 500)) {
    const { error } = await supabase
      .from("po_line_items")
      .upsert(c, { onConflict: "po_id,bt_line_item_id" });
    if (error) errors.push(`line upsert: ${error.message}`);
    else lineItems += c.length;
  }
  for (const row of editedLineRows) {
    const { error } = await supabase
      .from("po_line_items")
      .upsert([row], { onConflict: "po_id,bt_line_item_id" });
    if (error) errors.push(`line upsert(edited): ${error.message}`);
    else lineItems += 1;
  }
  }

  // Bust caches on every surface that reads PO data so a fresh pull is
  // visible on the next navigation without a hard refresh.
  revalidatePath("/");
  revalidatePath("/meeting");
  revalidatePath("/import");
  revalidatePath("/v2/job/[job_id]", "page");

  return NextResponse.json({
    ok: errors.length === 0,
    jobs: Object.keys(byJob).length,
    upserted: idByBtId.size,
    lineItems,
    errors: errors.slice(0, 10),
  });
}
