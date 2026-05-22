// POST /v2/api/items/[item_id]/delete  (v2 items table)
// Hard delete.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function POST(_req: NextRequest, { params }: { params: { item_id: string } }) {
  const supabase = supabaseServer();
  const { data: prior } = await supabase
    .from("items")
    .select("job_id, sub_id")
    .eq("id", params.item_id)
    .maybeSingle();
  const { error } = await supabase.from("items").delete().eq("id", params.item_id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  revalidatePath("/");
  if (prior?.job_id) revalidatePath(`/v2/job/${prior.job_id}`);
  if (prior?.sub_id) revalidatePath(`/sub/${prior.sub_id}`);
  return NextResponse.json({ ok: true });
}
