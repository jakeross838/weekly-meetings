// POST /v2/api/change-orders/[id]/delete
// Soft-delete (hidden=true); the upload route never resurrects hidden COs.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const supabase = supabaseServer();
  const { error } = await supabase
    .from("change_orders")
    .update({ hidden: true, hidden_at: new Date().toISOString() })
    .eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  revalidatePath("/v2/job/[job_id]", "page");
  return NextResponse.json({ ok: true });
}
