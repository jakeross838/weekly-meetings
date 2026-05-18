// POST /api/uncomplete  (v1 todos table)
// Body: { id: string }
//
// Reverts a v1 todo from COMPLETE back to its previous_status (default
// NOT_STARTED if missing).

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { getActor } from "@/lib/actor";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { id?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const id = body.id?.trim();
  if (!id) {
    return NextResponse.json({ error: "Missing id" }, { status: 400 });
  }

  const supabase = supabaseServer();
  const actor = getActor(req);

  const prior = await supabase
    .from("todos")
    .select("status, previous_status, sub_id")
    .eq("id", id)
    .maybeSingle();
  if (prior.error) {
    return NextResponse.json({ error: prior.error.message }, { status: 500 });
  }
  if (!prior.data) {
    return NextResponse.json({ error: "Todo not found" }, { status: 404 });
  }

  const target = (prior.data.previous_status as string) || "NOT_STARTED";

  const { error } = await supabase
    .from("todos")
    .update({
      status: target,
      completed_at: null,
      previous_status: null,
    })
    .eq("id", id);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  revalidatePath("/");
  revalidatePath("/subs");
  revalidatePath(`/sub/${prior.data.sub_id ?? ""}`);
  void actor;

  return NextResponse.json({ ok: true });
}
