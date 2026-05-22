// POST /api/subs/[id]/delete
// Soft-delete (hidden=true). The daily-logs scraper's ensureSubsForCrews is
// insert-only with ignoreDuplicates, so a re-scrape never un-hides it. The
// /subs list and sub pickers filter hidden=false.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const supabase = supabaseServer();
  const { error } = await supabase
    .from("subs")
    .update({ hidden: true, hidden_at: new Date().toISOString() })
    .eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  revalidatePath("/subs");
  revalidatePath("/sub/[id]", "page");
  return NextResponse.json({ ok: true });
}
