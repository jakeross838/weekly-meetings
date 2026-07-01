// POST /v2/api/weekly/[job_id]/mark-sent
// Body: { week_start: string }
//
// Records that a HUMAN sent the (already-approved) report to the client. The app
// never sends anything itself — this only marks that the PM did, so the timeline
// reflects it. Requires status = approved.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { currentUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: { job_id: string } }) {
  let payload: { week_start?: string } = {};
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  if (!payload.week_start) {
    return NextResponse.json({ ok: false, error: "week_start required" }, { status: 400 });
  }
  const user = await currentUser();
  const supabase = supabaseServer();
  const { data, error } = await supabase
    .from("weekly_reports")
    .update({
      status: "sent",
      sent_by: user?.email ?? "pm",
      sent_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    .eq("job_id", params.job_id)
    .eq("week_start", payload.week_start)
    .eq("status", "approved")
    .select("*")
    .maybeSingle();

  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  if (!data)
    return NextResponse.json({ ok: false, error: "report must be approved before it can be marked sent" }, { status: 409 });
  return NextResponse.json({ ok: true, report: data });
}
