// POST /api/jobs/[id]/refresh-summary
//
// Aggregates everything we know about this job (last 30 days of daily
// logs, open + recently-completed todos, sub crew activity, inspections,
// vision-extracted photo summaries) and asks Claude to produce a single
// structured JSON document that the UI renders as the job's "summary
// document". The result is written to job_summaries (one row per
// refresh, latest wins).
//
// Body: optional { window_days?: number } (default 30)
// Returns the new summary + meta counts.

import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

const MODEL = "claude-opus-4-7";
const DEFAULT_WINDOW_DAYS = 30;

interface JobSummary {
  headline: string;
  phase: string | null;
  whats_happening: string[];
  subs_recently_on_site: Array<{
    name: string;
    days: number;
    primary_activity: string | null;
  }>;
  open_concerns: Array<{
    text: string;
    priority: "URGENT" | "HIGH" | "NORMAL";
    owner: string | null;
  }>;
  coming_up: string[];
  inspections_recent: string[];
  safety_flags: string[];
  confidence: "high" | "medium" | "low";
}

function buildPrompt(
  job: { id: string; name: string; address: string | null },
  windowDays: number,
  logs: Array<Record<string, unknown>>,
  openTodos: Array<Record<string, unknown>>,
  doneTodos: Array<Record<string, unknown>>
): string {
  const todayIso = new Date().toISOString().slice(0, 10);
  return `You are summarizing a Ross Built custom-home job for the Monday meeting binder.

JOB:
- name: ${job.name}
- address: ${job.address ?? "(unknown)"}
- as of: ${todayIso}
- window: last ${windowDays} days of daily logs + open todos + recently completed todos

DAILY LOGS (${logs.length} entries; newest first):
${JSON.stringify(logs, null, 2)}

OPEN TODOS (${openTodos.length}):
${JSON.stringify(openTodos, null, 2)}

RECENTLY COMPLETED TODOS (${doneTodos.length}):
${JSON.stringify(doneTodos, null, 2)}

Return ONE JSON object with this exact shape:

{
  "headline": "<≤120 chars one-sentence current state of the job>",
  "phase": "<one of: site prep, foundation, framing, dry-in, rough-in, drywall, finishes, exterior, punch, closeout, or null if ambiguous>",
  "whats_happening": ["<3-7 concrete observations from the last 2 weeks>"],
  "subs_recently_on_site": [
    {"name": "<sub name>", "days": <int days on site in window>, "primary_activity": "<what they were doing, or null>"}
  ],
  "open_concerns": [
    {"text": "<≤200 chars>", "priority": "URGENT|HIGH|NORMAL", "owner": "<who owns it, or null>"}
  ],
  "coming_up": ["<2-5 items committed for the next 1-2 weeks>"],
  "inspections_recent": ["<inspection name + result + date, one per line>"],
  "safety_flags": ["<any safety hazard surfaced in photo_summary or notes; EMPTY if none>"],
  "confidence": "high|medium|low"
}

Rules:
- "whats_happening" comes from a synthesis of daily log notes + photo_summaries. Use the actual sub names and activities present in the data.
- "subs_recently_on_site" counts unique log dates where the sub appears in crews_present in the window. Order by days desc.
- "open_concerns" prioritizes URGENT todos, past-due items, and items mentioned in safety_flags or hazards.
- "coming_up" pulls due dates in the next 14 days from open todos + any "next week" mentions in recent notes — written with explicit dates, not "next week".
- Lower confidence to "medium" if photo_summary is null on most recent logs, "low" if there are fewer than 3 logs in the window.
- Return ONLY the JSON. No prose, no fences.`;
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const jobId = params.id;
  const supabase = supabaseServer();

  let body: { window_days?: number } = {};
  try {
    body = await req.json();
  } catch {
    /* empty body fine */
  }
  const windowDays =
    Number.isFinite(body.window_days) && body.window_days! > 0
      ? body.window_days!
      : DEFAULT_WINDOW_DAYS;

  const jobRes = await supabase
    .from("jobs")
    .select("id, name, address")
    .eq("id", jobId)
    .maybeSingle();
  if (!jobRes.data) {
    return NextResponse.json(
      { ok: false, error: `job not found: ${jobId}` },
      { status: 404 }
    );
  }
  const job = jobRes.data as {
    id: string;
    name: string;
    address: string | null;
  };

  const sinceIso = new Date(Date.now() - windowDays * 86_400_000)
    .toISOString()
    .slice(0, 10);

  const [logsRes, openRes, doneRes] = await Promise.all([
    supabase
      .from("daily_logs")
      .select(
        "log_date, job_key, crews_present, parent_group_activities, daily_workforce, crew_counts, inspections, notes, photo_summary, photo_urls"
      )
      .ilike("job_key", `${job.name}%`)
      .gte("log_date", sinceIso)
      .order("log_date", { ascending: false })
      .limit(60),
    supabase
      .from("todos")
      .select(
        "id, title, edited_title, due_date, priority, status, category, sub_id, sub:subs(name)"
      )
      .eq("job", job.name)
      .in("status", ["NOT_STARTED", "IN_PROGRESS", "BLOCKED"])
      .order("due_date", { ascending: true, nullsFirst: false })
      .limit(60),
    supabase
      .from("todos")
      .select("id, title, edited_title, completed_at, due_date, category")
      .eq("job", job.name)
      .eq("status", "COMPLETE")
      .gte("completed_at", new Date(Date.now() - windowDays * 86_400_000).toISOString())
      .order("completed_at", { ascending: false })
      .limit(40),
  ]);

  const logs = (logsRes.data ?? []) as Array<Record<string, unknown>>;
  const openTodos = (openRes.data ?? []) as Array<Record<string, unknown>>;
  const doneTodos = (doneRes.data ?? []) as Array<Record<string, unknown>>;

  // Counts for the meta panel.
  const photoCount = logs.reduce((n, l) => {
    const arr = l.photo_urls;
    return n + (Array.isArray(arr) ? arr.length : 0);
  }, 0);
  const lastDataThrough =
    logs.length > 0 ? (logs[0].log_date as string | null) : null;

  if (logs.length === 0 && openTodos.length === 0) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Nothing to summarize — no daily logs in the window and no open todos. Run a scrape first.",
        log_count: 0,
        open_todo_count: 0,
      },
      { status: 400 }
    );
  }

  const anthropicKey = process.env.ANTHROPIC_API_KEY;
  if (!anthropicKey) {
    return NextResponse.json(
      { ok: false, error: "Server missing ANTHROPIC_API_KEY" },
      { status: 500 }
    );
  }
  const client = new Anthropic({ apiKey: anthropicKey });
  const prompt = buildPrompt(job, windowDays, logs, openTodos, doneTodos);

  // Force a valid, schema-shaped object via tool-use. Free-text JSON from the
  // model occasionally came back malformed on big summaries (unescaped chars),
  // which blew up JSON.parse and 502'd the route. A tool schema makes the
  // output structurally guaranteed — no regex, no JSON.parse.
  const summaryTool: Anthropic.Tool = {
    name: "emit_job_summary",
    description:
      "Return the structured job summary for the Monday meeting binder.",
    input_schema: {
      type: "object",
      properties: {
        headline: { type: "string" },
        phase: { type: ["string", "null"] },
        whats_happening: { type: "array", items: { type: "string" } },
        subs_recently_on_site: {
          type: "array",
          items: {
            type: "object",
            properties: {
              name: { type: "string" },
              days: { type: "integer" },
              primary_activity: { type: ["string", "null"] },
            },
            required: ["name", "days"],
          },
        },
        open_concerns: {
          type: "array",
          items: {
            type: "object",
            properties: {
              text: { type: "string" },
              priority: { type: "string", enum: ["URGENT", "HIGH", "NORMAL"] },
              owner: { type: ["string", "null"] },
            },
            required: ["text", "priority"],
          },
        },
        coming_up: { type: "array", items: { type: "string" } },
        inspections_recent: { type: "array", items: { type: "string" } },
        safety_flags: { type: "array", items: { type: "string" } },
        confidence: { type: "string", enum: ["high", "medium", "low"] },
      },
      required: [
        "headline",
        "whats_happening",
        "subs_recently_on_site",
        "open_concerns",
        "coming_up",
        "inspections_recent",
        "safety_flags",
        "confidence",
      ],
    },
  };

  const startedAt = Date.now();
  let parsed: JobSummary;
  try {
    const resp = await client.messages.create({
      model: MODEL,
      max_tokens: 4000,
      tools: [summaryTool],
      tool_choice: { type: "tool", name: "emit_job_summary" },
      messages: [{ role: "user", content: prompt }],
    });
    const toolUse = resp.content.find((b) => b.type === "tool_use");
    if (!toolUse || toolUse.type !== "tool_use") {
      return NextResponse.json(
        { ok: false, error: "Claude returned no tool_use block" },
        { status: 502 }
      );
    }
    parsed = toolUse.input as JobSummary;
  } catch (e) {
    return NextResponse.json(
      {
        ok: false,
        error: `Claude error: ${e instanceof Error ? e.message : String(e)}`,
      },
      { status: 502 }
    );
  }

  const elapsedMs = Date.now() - startedAt;

  // Persist. We keep history so we can diff later.
  const insertRes = await supabase
    .from("job_summaries")
    .insert({
      job_id: job.id,
      summary: parsed,
      last_data_through: lastDataThrough,
      log_count: logs.length,
      photo_count: photoCount,
      open_todo_count: openTodos.length,
      done_todo_count: doneTodos.length,
      model: MODEL,
      elapsed_ms: elapsedMs,
    })
    .select()
    .single();

  // If the insert failed (most commonly: job_summaries table doesn't
  // exist yet because migrations haven't been applied), don't waste the
  // Claude call — return the summary anyway with a clear note so the
  // panel still renders and the operator knows what to fix.
  const persisted = !insertRes.error;
  const metaBase = {
    generated_at:
      insertRes.data?.generated_at ?? new Date().toISOString(),
    log_count: logs.length,
    photo_count: photoCount,
    open_todo_count: openTodos.length,
    done_todo_count: doneTodos.length,
    last_data_through: lastDataThrough,
    model: MODEL,
    elapsed_ms: elapsedMs,
  };

  if (persisted) {
    revalidatePath(`/v2/job/${job.id}`);
  }

  return NextResponse.json({
    ok: true,
    summary: parsed,
    meta: metaBase,
    persisted,
    persist_error: insertRes.error?.message ?? null,
    persist_hint: persisted
      ? null
      : "Summary generated but not saved — apply migrations via /admin/run-migrations to enable persistence.",
  });
}
