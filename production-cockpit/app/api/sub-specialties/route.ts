// POST /api/sub-specialties
// Body: { sub_id: string, specialty: string, action: "add" | "remove" }
//
// Manages manual sub specialties. Auto-detected specialties from BT
// parent_group_activities are NOT stored here — they're computed on the fly
// from daily_logs when /sub/[id] renders. This table is just the manual
// declarations layered on top.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { getActor } from "@/lib/actor";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { sub_id?: string; specialty?: string; action?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const sub_id = (body.sub_id ?? "").trim();
  const specialty = (body.specialty ?? "").trim();
  const action = body.action;

  if (!sub_id) {
    return NextResponse.json({ error: "missing sub_id" }, { status: 400 });
  }
  if (!specialty) {
    return NextResponse.json({ error: "missing specialty" }, { status: 400 });
  }
  if (action !== "add" && action !== "remove") {
    return NextResponse.json(
      { error: "action must be 'add' or 'remove'" },
      { status: 400 }
    );
  }

  const supabase = supabaseServer();
  const actor = getActor(req);

  function explain(err: { message: string; code?: string }): string {
    if (/PGRST205|does not exist/i.test(err.message)) {
      return "sub_specialties table missing — apply migration 012_create_sub_specialties_table.sql in Supabase Studio";
    }
    return err.message;
  }

  if (action === "add") {
    const { error } = await supabase
      .from("sub_specialties")
      .upsert(
        { sub_id, specialty, source: "manual", created_by: actor },
        { onConflict: "sub_id,specialty" }
      );
    if (error) {
      return NextResponse.json({ error: explain(error) }, { status: 500 });
    }
  } else {
    const { error } = await supabase
      .from("sub_specialties")
      .delete()
      .eq("sub_id", sub_id)
      .eq("specialty", specialty)
      .eq("source", "manual");
    if (error) {
      return NextResponse.json({ error: explain(error) }, { status: 500 });
    }
  }

  revalidatePath(`/sub/${sub_id}`);
  return NextResponse.json({ ok: true });
}
