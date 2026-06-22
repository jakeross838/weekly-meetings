// POST /v2/api/change-orders/upload
// Body: { payload: { byJob: { [jobKey]: CORecord[] } } }  (or the bare payload)
//
// Upserts change_orders by bt_co_id. Manual-wins: hidden rows are never
// resurrected; columns in a row's manually_edited_fields are never overwritten.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { guardSyncWrite } from "@/lib/sync-guard";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

interface CORecord {
  bt_co_id: number;
  job_key: string;
  bt_job_id: number | null;
  co_number: string | null;
  title: string | null;
  status: string | null;
  approval_code: number | null;
  owner_price: number | null;
  builder_cost: number | null;
  total_with_tax: number | null;
  owner_name: string | null;
  date_approved: string | null;
  date_added: string | null;
}

function chunk<T>(arr: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
  return out;
}

function coRow(co: CORecord, scrapedAt: string): Record<string, unknown> {
  return {
    bt_co_id: co.bt_co_id,
    job_key: co.job_key,
    bt_job_id: co.bt_job_id ?? null,
    co_number: co.co_number ?? null,
    title: co.title ?? null,
    status: co.status ?? null,
    approval_code: co.approval_code ?? null,
    owner_price: co.owner_price ?? null,
    builder_cost: co.builder_cost ?? null,
    total_with_tax: co.total_with_tax ?? null,
    owner_name: co.owner_name ?? null,
    date_approved: co.date_approved ?? null,
    date_added: co.date_added ?? null,
    scraped_at: scrapedAt,
  };
}

export async function POST(req: NextRequest) {
  const denied = await guardSyncWrite(req);
  if (denied) return denied;
  const supabase = supabaseServer();
  let body: {
    payload?: { byJob?: Record<string, CORecord[]> };
    byJob?: Record<string, CORecord[]>;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  const byJob = body.payload?.byJob ?? body.byJob ?? {};
  const allCOs: CORecord[] = [];
  for (const cos of Object.values(byJob)) {
    if (Array.isArray(cos)) allCOs.push(...cos);
  }
  if (allCOs.length === 0) {
    return NextResponse.json({ ok: true, jobs: 0, upserted: 0, note: "empty payload" });
  }

  const scrapedAt = new Date().toISOString();
  const errors: string[] = [];

  // Existing manual state (edits / soft-deletes).
  const edited = new Map<number, string[]>();
  const hidden = new Set<number>();
  for (const c of chunk(allCOs.map((co) => co.bt_co_id), 500)) {
    const { data } = await supabase
      .from("change_orders")
      .select("bt_co_id, manually_edited_fields, hidden")
      .in("bt_co_id", c);
    for (const r of (data ?? []) as { bt_co_id: number; manually_edited_fields: string[] | null; hidden: boolean }[]) {
      if (Array.isArray(r.manually_edited_fields) && r.manually_edited_fields.length)
        edited.set(r.bt_co_id, r.manually_edited_fields);
      if (r.hidden) hidden.add(r.bt_co_id);
    }
  }

  const cleanCOs = allCOs.filter((co) => !hidden.has(co.bt_co_id) && !edited.has(co.bt_co_id));
  const editedCOs = allCOs.filter((co) => !hidden.has(co.bt_co_id) && edited.has(co.bt_co_id));
  let upserted = 0;
  for (const c of chunk(cleanCOs, 400)) {
    const { error } = await supabase
      .from("change_orders")
      .upsert(c.map((co) => coRow(co, scrapedAt)), { onConflict: "bt_co_id" });
    if (error) errors.push(`co upsert: ${error.message}`);
    else upserted += c.length;
  }
  for (const co of editedCOs) {
    const row = coRow(co, scrapedAt);
    for (const f of edited.get(co.bt_co_id) ?? []) delete row[f];
    const { error } = await supabase
      .from("change_orders")
      .upsert([row], { onConflict: "bt_co_id" });
    if (error) errors.push(`co upsert(edited): ${error.message}`);
    else upserted += 1;
  }

  // Bust caches on every surface that reads CO data so a fresh pull is
  // visible on the next navigation without a hard refresh.
  revalidatePath("/");
  revalidatePath("/meeting");
  revalidatePath("/import");
  revalidatePath("/v2/job/[job_id]", "page");

  return NextResponse.json({
    ok: errors.length === 0,
    jobs: Object.keys(byJob).length,
    upserted,
    errors: errors.slice(0, 10),
  });
}
