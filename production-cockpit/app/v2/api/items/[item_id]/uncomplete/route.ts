// POST /v2/api/items/[item_id]/uncomplete — revert to previous_status.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function POST(
  _req: NextRequest,
  { params }: { params: { item_id: string } },
) {
  const { item_id } = params;
  const supabase = supabaseServer();

  const { data: existing } = await supabase
    .from("items")
    .select("previous_status, manually_edited_fields")
    .eq("id", item_id)
    .maybeSingle();
  if (!existing) {
    return NextResponse.json({ error: "item not found" }, { status: 404 });
  }

  const prev = (existing.previous_status as string) ?? "open";
  const meFields: string[] = ((existing.manually_edited_fields ?? []) as string[]).filter((f) => f !== "status");

  const { data, error } = await supabase
    .from("items")
    .update({
      status: prev,
      completed_at: null,
      completed_by: null,
      completion_basis: null,
      previous_status: null,
      manually_edited_fields: meFields,
      updated_at: new Date().toISOString(),
    })
    .eq("id", item_id)
    .select()
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ item: data });
}
