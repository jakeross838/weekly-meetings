// POST /api/todos/create  (v1 todos table)
// Body: { job_id: string (slug), title: string, due_date?, category?, sub_id?, priority? }
//
// Creates a brand-new, hand-entered to-do on a job — the manual counterpart to
// the transcript-extracted todos. Marked source_transcript="manual" so it's
// distinguishable from imported items. Buildertrend re-syncs never touch the
// todos table, so a manual to-do always survives a re-scrape.
//
// Mirrors the write rules used everywhere else:
//   • scrubRelativeDates on the title (no broad timeframes ever reach the list)
//   • status forced to NOT_STARTED — the column default is 'OPEN', which is NOT
//     in OPEN_STATUSES, so a defaulted row would be invisible on the job page.
//   • PM scoping: a non-admin can only add to jobs they can see.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { scrubRelativeDates } from "@/lib/scrub-relative-dates";
import { businessToday } from "@/lib/today";
import { currentUser, canSeeJobByPm } from "@/lib/auth";
import { CATEGORIES } from "@/lib/categories";

export const dynamic = "force-dynamic";

const PRIORITIES = new Set(["URGENT", "HIGH", "NORMAL"]);

export async function POST(req: NextRequest) {
  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const jobId = typeof body.job_id === "string" ? body.job_id.trim() : "";
  const rawTitle = typeof body.title === "string" ? body.title.trim() : "";
  if (!jobId) {
    return NextResponse.json({ error: "missing job_id" }, { status: 400 });
  }
  if (!rawTitle) {
    return NextResponse.json({ error: "title is required" }, { status: 400 });
  }

  const supabase = supabaseServer();

  // Resolve the job slug → display name. todos.job stores the display name
  // ("Krauss"), matched EXACTLY by the job/meeting pages — so we must look it
  // up, not trust a slug. Also gives us the job's PM for scoping.
  const jobRes = await supabase
    .from("jobs")
    .select("id, name, pm_id")
    .eq("id", jobId)
    .maybeSingle();
  const job = jobRes.data as
    | { id: string; name: string; pm_id: string | null }
    | null;
  if (!job) {
    return NextResponse.json({ error: "job not found" }, { status: 404 });
  }

  // PM scoping — a non-admin can only add todos to jobs they can see.
  const user = await currentUser();
  if (!canSeeJobByPm(user, job.pm_id)) {
    return NextResponse.json(
      { error: "not allowed for this job" },
      { status: 403 }
    );
  }

  // Same no-broad-timeframe rule as the import + edit paths. A hand-entry
  // happens "now", so resolve relative phrases against today's date.
  const title = scrubRelativeDates(rawTitle, businessToday());

  const category =
    typeof body.category === "string" &&
    (CATEGORIES as readonly string[]).includes(body.category)
      ? body.category
      : "ADMIN";
  const priority =
    typeof body.priority === "string" && PRIORITIES.has(body.priority)
      ? body.priority
      : "NORMAL";
  const dueDate =
    typeof body.due_date === "string" && body.due_date.trim()
      ? body.due_date.trim()
      : null;
  const subId =
    typeof body.sub_id === "string" && body.sub_id.trim()
      ? body.sub_id.trim()
      : null;

  // ID mirrors the extractor's scheme (<JOB-PREFIX>-C<base36>) so manual and
  // extracted todos share one keyspace and never collide.
  const prefix = job.name
    .replace(/[^A-Za-z]/g, "")
    .slice(0, 4)
    .toUpperCase()
    .padEnd(4, "_");
  const now = Date.now();
  const suffix = `C${(now % 10_000_000).toString(36)}${Math.floor(
    Math.random() * 1296
  )
    .toString(36)
    .padStart(2, "0")}`;
  const id = `${prefix}-${suffix}`;

  const row = {
    id,
    pm_id: job.pm_id ?? user?.pmId ?? null,
    job: job.name,
    title,
    due_date: dueDate,
    priority,
    status: "NOT_STARTED",
    type: "FOLLOWUP",
    category,
    sub_id: subId,
    source_transcript: "manual",
  };

  const { data, error } = await supabase
    .from("todos")
    .insert(row)
    .select()
    .maybeSingle();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // Refresh every surface that aggregates from todos.
  revalidatePath("/");
  revalidatePath("/subs");
  revalidatePath("/meeting");
  revalidatePath(`/v2/job/${job.id}`);
  if (subId) revalidatePath(`/sub/${subId}`);

  return NextResponse.json({ ok: true, todo: data });
}
