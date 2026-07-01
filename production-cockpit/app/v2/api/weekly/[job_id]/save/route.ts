// POST /v2/api/weekly/[job_id]/save
// Body: { week_start: string, body: ReportBody }
//
// Saves the PM's edited report body. Editing invalidates any prior approval:
// the report drops back to DRAFT and must be re-approved before it can be sent.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { normalizeBody } from "@/lib/weekly";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: { job_id: string } }) {
  let payload: { week_start?: string; body?: unknown } = {};
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  if (!payload.week_start) {
    return NextResponse.json({ ok: false, error: "week_start required" }, { status: 400 });
  }
  const edited = normalizeBody(payload.body);

  const supabase = supabaseServer();
  const { data, error } = await supabase
    .from("weekly_reports")
    .update({
      edited_body: edited,
      status: "draft",
      approved_by: null,
      approved_at: null,
      sent_by: null,
      sent_at: null,
      updated_at: new Date().toISOString(),
    })
    .eq("job_id", params.job_id)
    .eq("week_start", payload.week_start)
    .select("*")
    .maybeSingle();

  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ ok: false, error: "report not found" }, { status: 404 });
  return NextResponse.json({ ok: true, report: data });
}
