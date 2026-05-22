// POST /api/todos/[id]/delete  (v1 todos table)
// Hard delete — todos are user/transcript data, not scraped, so removal is
// permanent (re-approving a transcript would re-create, which is intended).

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const supabase = supabaseServer();
  const { data: prior } = await supabase
    .from("todos")
    .select("sub_id")
    .eq("id", params.id)
    .maybeSingle();
  const { error } = await supabase.from("todos").delete().eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  revalidatePath("/");
  revalidatePath("/subs");
  revalidatePath("/meeting");
  revalidatePath("/v2/job/[job_id]", "page");
  if (prior?.sub_id) revalidatePath(`/sub/${prior.sub_id}`);
  return NextResponse.json({ ok: true });
}
