// POST /v2/api/weekly/[job_id]/approve
// Body: { week_start: string, approve: boolean }
//
// The human review gate. approve=true moves draft -> approved (records who/when);
// approve=false reverts approved -> draft. Only an approved report can be sent.
// Nothing here sends anything to a client.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { currentUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: { job_id: string } }) {
  let payload: { week_start?: string; approve?: boolean } = {};
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  if (!payload.week_start) {
    return NextResponse.json({ ok: false, error: "week_start required" }, { status: 400 });
  }
  const user = await currentUser();
  const approve = payload.approve !== false;

  const supabase = supabaseServer();
  const update = approve
    ? { status: "approved", approved_by: user?.email ?? "pm", approved_at: new Date().toISOString(), updated_at: new Date().toISOString() }
    : { status: "draft", approved_by: null, approved_at: null, updated_at: new Date().toISOString() };

  const { data, error } = await supabase
    .from("weekly_reports")
    .update(update)
    .eq("job_id", params.job_id)
    .eq("week_start", payload.week_start)
    // Guard: never approve a report that's already been sent (it's terminal).
    .in("status", approve ? ["draft"] : ["approved"])
    .select("*")
    .maybeSingle();

  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  if (!data)
    return NextResponse.json(
      { ok: false, error: approve ? "no draft to approve (already approved or sent?)" : "no approved report to revert" },
      { status: 409 }
    );
  return NextResponse.json({ ok: true, report: data });
}
