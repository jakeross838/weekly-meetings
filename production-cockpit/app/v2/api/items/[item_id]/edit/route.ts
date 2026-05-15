// POST /v2/api/items/[item_id]/edit
// Body: { title?: string, detail?: string, target_date?: string, target_date_text?: string }
//
// Mutates the item and appends edited field names to manually_edited_fields
// (Decision 11 clobber protection — future Reconciler runs will preserve these).

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

const ALLOWED = new Set(["title", "detail", "target_date", "target_date_text"]);

export async function POST(
  req: NextRequest,
  { params }: { params: { item_id: string } },
) {
  const { item_id } = params;
  const supabase = supabaseServer();

  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const update: Record<string, unknown> = {};
  const edited: string[] = [];
  for (const [k, v] of Object.entries(body)) {
    if (ALLOWED.has(k) && v !== undefined) {
      update[k] = v;
      edited.push(k);
    }
  }
  if (Object.keys(update).length === 0) {
    return NextResponse.json({ error: "no allowed fields in body" }, { status: 400 });
  }

  const { data: existing } = await supabase
    .from("items")
    .select("manually_edited_fields")
    .eq("id", item_id)
    .maybeSingle();
  if (!existing) {
    return NextResponse.json({ error: "item not found" }, { status: 404 });
  }
  const cur: string[] = (existing.manually_edited_fields ?? []) as string[];
  const merged = Array.from(new Set([...cur, ...edited]));

  update.manually_edited_at = new Date().toISOString();
  update.manually_edited_fields = merged;
  update.updated_at = new Date().toISOString();

  const { data, error } = await supabase
    .from("items")
    .update(update)
    .eq("id", item_id)
    .select()
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ item: data });
}
