// POST /v2/api/weekly/[job_id]/feedback
// Body: { feedback: string }
//
// Stores PM feedback for a job. The generate route feeds the most recent
// feedback back into Claude so the report's voice/emphasis tunes over time.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { currentUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: { job_id: string } }) {
  let payload: { feedback?: string } = {};
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  const text = (payload.feedback ?? "").trim();
  if (!text) return NextResponse.json({ ok: false, error: "feedback required" }, { status: 400 });

  const user = await currentUser();
  const supabase = supabaseServer();
  const { data, error } = await supabase
    .from("report_feedback")
    .insert({ job_id: params.job_id, feedback: text, created_by: user?.email ?? null })
    .select("*")
    .maybeSingle();

  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, feedback: data });
}
