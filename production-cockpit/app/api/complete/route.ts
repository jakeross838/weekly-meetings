// POST /api/complete  (v1 todos table)
// Body: { id: string }
//
// Marks a v1 todo COMPLETE, capturing prior status so /api/uncomplete can revert.

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
    .select("status, job, sub_id")
    .eq("id", id)
    .maybeSingle();
  if (prior.error) {
    return NextResponse.json({ error: prior.error.message }, { status: 500 });
  }
  if (!prior.data) {
    return NextResponse.json({ error: "Todo not found" }, { status: 404 });
  }
  if (prior.data.status === "COMPLETE") {
    return NextResponse.json({ ok: true, alreadyComplete: true });
  }

  const { error } = await supabase
    .from("todos")
    .update({
      status: "COMPLETE",
      completed_at: new Date().toISOString(),
      previous_status: prior.data.status,
    })
    .eq("id", id);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // Mirror the v2 cache-invalidation pattern so counts on every surface stay
  // fresh after a v1 toggle. Job-detail page lookups jobs by slug, but
  // todos.job is the display name — we revalidate the portfolio + subs
  // surfaces that aggregate from todos. Per-job revalidation is best-effort
  // (we don't have the slug here).
  revalidatePath("/");
  revalidatePath("/subs");
  revalidatePath(`/sub/${prior.data.sub_id ?? ""}`);
  // Suppress unused warning; actor is logged once auth ships.
  void actor;

  return NextResponse.json({ ok: true });
}
