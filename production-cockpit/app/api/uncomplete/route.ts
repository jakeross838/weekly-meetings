import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  let body: { id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON" },
      { status: 400 }
    );
  }
  const id = body.id?.trim();
  if (!id) {
    return NextResponse.json(
      { ok: false, error: "Missing id" },
      { status: 400 }
    );
  }

  const supabase = supabaseServer();
  const cur = await supabase
    .from("todos")
    .select("status, previous_status")
    .eq("id", id)
    .maybeSingle();
  if (cur.error) {
    return NextResponse.json(
      { ok: false, error: cur.error.message },
      { status: 500 }
    );
  }
  if (!cur.data) {
    return NextResponse.json(
      { ok: false, error: "Todo not found" },
      { status: 404 }
    );
  }
  if (cur.data.status !== "COMPLETE") {
    return NextResponse.json(
      { ok: false, error: "Not complete" },
      { status: 400 }
    );
  }
  const revertTo = cur.data.previous_status || "IN_PROGRESS";

  const { error } = await supabase
    .from("todos")
    .update({
      status: revertTo,
      completed_at: null,
      previous_status: null,
    })
    .eq("id", id);
  if (error) {
    return NextResponse.json(
      { ok: false, error: error.message },
      { status: 500 }
    );
  }
  return NextResponse.json({ ok: true, revertedTo: revertTo });
}
