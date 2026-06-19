// POST /api/jobs/[id]/process-pending
//
// Finds every daily_log for this job that has photos but no
// photo_summary yet, then asks /v2/api/daily-logs/extract-photos to run
// the vision pass on exactly that set. Returns the same shape the
// extract-photos route does — so the UI can render the per-log results
// directly.
//
// "This job" is resolved by matching daily_logs.job_key ILIKE
// '{job.name}%' (job names are unique prefixes of the BT job_key) so we
// don't need a separate jobs↔job_keys mapping table.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const maxDuration = 300; // Claude vision over many photos — give it room

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const jobId = params.id;
  const supabase = supabaseServer();

  const jobRes = await supabase
    .from("jobs")
    .select("id, name")
    .eq("id", jobId)
    .maybeSingle();
  if (!jobRes.data) {
    return NextResponse.json(
      { ok: false, error: `job not found: ${jobId}` },
      { status: 404 }
    );
  }
  const job = jobRes.data as { id: string; name: string };

  // Find pending logs. We can't reliably check `photo_urls != '[]'`
  // through the JS client without an RPC, so pull a wider net and
  // filter in code.
  const candRes = await supabase
    .from("daily_logs")
    .select("id, photo_urls, photo_summary")
    .ilike("job_key", `${job.name}%`)
    .is("photo_summary", null)
    .limit(200);
  if (candRes.error) {
    return NextResponse.json(
      { ok: false, error: `candidate query failed: ${candRes.error.message}` },
      { status: 500 }
    );
  }
  const candidates = (candRes.data ?? []) as {
    id: string;
    photo_urls: unknown;
  }[];
  const log_ids = candidates
    .filter((c) => Array.isArray(c.photo_urls) && c.photo_urls.length > 0)
    .map((c) => c.id);

  if (log_ids.length === 0) {
    return NextResponse.json({
      ok: true,
      considered: 0,
      processed: 0,
      failed: 0,
      results: [],
      message: "No pending photos to process.",
    });
  }

  // Hand off to the shared extract-photos route so we use one Claude
  // prompt + writeback path. Same-origin fetch keeps it simple.
  const origin = req.nextUrl.origin;
  const visionRes = await fetch(`${origin}/v2/api/daily-logs/extract-photos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ log_ids, limit: log_ids.length }),
  });
  const visionData = await visionRes.json().catch(() => ({}));
  if (!visionRes.ok) {
    return NextResponse.json(
      {
        ok: false,
        error: `vision route returned ${visionRes.status}`,
        detail: visionData,
      },
      { status: 500 }
    );
  }
  return NextResponse.json(visionData);
}
