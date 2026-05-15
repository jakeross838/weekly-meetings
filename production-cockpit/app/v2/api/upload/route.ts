// POST /v2/api/upload — minimal: SHA-256, dedup, save meeting.
// Body: { filename, text, job_id, meeting_type, meeting_date, pm_id }
//
// The heavy brain pipeline (Extractor + Reconciler) is NOT invoked from
// this route — Next.js on Vercel has no Python runtime here. For v1, the
// uploaded transcript is saved + a meeting row is created; the Python
// pipeline runs offline via scripts/run_gate_1e_reconcile.py and produces
// the ingestion_event + proposed_changes.

import { NextRequest, NextResponse } from "next/server";
import { createHash } from "crypto";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type Body = {
  filename?: string;
  text?: string;
  job_id?: string;
  meeting_type?: "site" | "office" | "spontaneous";
  meeting_date?: string;
  pm_id?: string;
};

export async function POST(req: NextRequest) {
  const supabase = supabaseServer();
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (!body.text || !body.job_id || !body.meeting_type || !body.meeting_date) {
    return NextResponse.json({ error: "missing required fields" }, { status: 400 });
  }

  const allowedTypes = new Set(["site", "office"]); // meetings CHECK enum is site/office; map 'spontaneous' to 'office' for v1
  const meetingType = allowedTypes.has(body.meeting_type) ? body.meeting_type : "office";

  const hash = createHash("sha256").update(body.text).digest("hex");

  // Dedup check
  const { data: existing } = await supabase
    .from("meetings")
    .select("id")
    .eq("source_file_hash", hash)
    .maybeSingle();
  if (existing) {
    // Find the ingestion_event tied to this meeting, if any
    const { data: ie } = await supabase
      .from("ingestion_events")
      .select("id")
      .eq("source_meeting_id", existing.id)
      .order("ingested_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    return NextResponse.json({
      ok: true,
      duplicate_of: existing.id,
      ingestion_event_id: ie?.id ?? null,
    });
  }

  // Insert meeting
  const { data: meeting, error: mErr } = await supabase
    .from("meetings")
    .insert({
      job_id: body.job_id,
      pm_id: body.pm_id ?? null,
      meeting_date: body.meeting_date,
      meeting_type: meetingType,
      raw_transcript_text: body.text,
      transcript_file_path: body.filename ?? null,
      source_file_hash: hash,
    })
    .select("id")
    .maybeSingle();
  if (mErr || !meeting) {
    return NextResponse.json({ error: mErr?.message ?? "meeting insert failed" }, { status: 500 });
  }

  return NextResponse.json({
    ok: true,
    meeting_id: meeting.id,
    ingestion_event_id: null,
    note: "Saved. Pipeline processing is offline for v1 — run scripts/run_gate_1e_reconcile.py to produce review proposals.",
  });
}
