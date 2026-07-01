// POST /v2/api/weekly/[job_id]/generate
// Body: { period?: "weekly" | "monthly" }
//
// Generates the homeowner report as a DRAFT and upserts it into weekly_reports
// for this job + current week. Reasons over the same spine the cockpit already
// has — pay app, POs, recent daily logs, open todos — PLUS captured job_intel
// (emails/logs/POs) and the PM's stored feedback so the voice tunes over time.
//
// This route only ever writes a DRAFT. Approval + sending are separate,
// human-gated steps (approve / mark-sent routes). Nothing is auto-sent.

import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { supabaseServer } from "@/lib/supabase";
import { businessToday, businessDateOffset } from "@/lib/today";
import { currentUser } from "@/lib/auth";
import { getConfig } from "@/lib/app-config";
import { currentWeekStart, normalizeBody, type ReportBody } from "@/lib/weekly";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(req: NextRequest, { params }: { params: { job_id: string } }) {
  const jobId = params.job_id;
  const supabase = supabaseServer();

  let body: { period?: string } = {};
  try {
    body = await req.json();
  } catch {
    /* empty body ok */
  }
  const period = body.period === "monthly" ? "monthly" : "weekly";
  const lookbackDays = period === "monthly" ? 35 : 10;
  const lookaheadDays = period === "monthly" ? 35 : 14;

  const jobRes = await supabase
    .from("jobs")
    .select("id, name, address")
    .eq("id", jobId)
    .maybeSingle();
  if (!jobRes.data) {
    return NextResponse.json({ ok: false, error: `job not found: ${jobId}` }, { status: 404 });
  }
  const job = jobRes.data as { id: string; name: string; address: string | null };

  const todayIso = businessToday();
  const sinceIso = businessDateOffset(-lookbackDays);
  const untilIso = businessDateOffset(lookaheadDays);
  const sinceTs = new Date(sinceIso + "T00:00:00Z").toISOString();

  // One batch of independent reads — no per-row/per-job loops (avoids the old
  // N+1). Budget from pay app + POs; activity from logs; work from todos;
  // durable signals from job_intel; voice from stored feedback.
  const [payRes, poRes, logsRes, openRes, intelRes, fbRes] = await Promise.all([
    supabase.from("pay_app_line_items").select("scheduled_value, total_completed").eq("job_id", jobId),
    supabase
      .from("purchase_orders")
      .select("cost, amount_remaining")
      .ilike("job_key", `${job.name}%`)
      .eq("hidden", false),
    supabase
      .from("daily_logs")
      .select("log_date, parent_group_activities, notes")
      .ilike("job_key", `${job.name}%`)
      .eq("hidden", false)
      .gte("log_date", sinceIso)
      .order("log_date", { ascending: false })
      .limit(40),
    supabase
      .from("todos")
      .select("title, edited_title, due_date, category, status")
      .eq("job", job.name)
      .in("status", ["NOT_STARTED", "IN_PROGRESS", "BLOCKED"])
      .order("due_date", { ascending: true, nullsFirst: false })
      .limit(100),
    supabase
      .from("job_intel")
      .select("source, intel_type, summary, detail, action_needed, sent_at, created_at")
      .eq("job_id", jobId)
      .eq("hidden", false)
      .gte("created_at", sinceTs)
      .order("sent_at", { ascending: false, nullsFirst: false })
      .limit(40),
    supabase
      .from("report_feedback")
      .select("feedback, created_at")
      .eq("job_id", jobId)
      .order("created_at", { ascending: false })
      .limit(8),
  ]);

  let sched = 0,
    comp = 0;
  for (const l of payRes.data ?? []) {
    sched += Number(l.scheduled_value) || 0;
    comp += Number(l.total_completed) || 0;
  }
  const pct = sched > 0 ? Math.round((comp / sched) * 100) : null;
  let committed = 0,
    outstanding = 0;
  for (const p of poRes.data ?? []) {
    committed += Number(p.cost) || 0;
    outstanding += Number(p.amount_remaining) || 0;
  }

  const logs = (logsRes.data ?? []) as Array<{
    log_date: string | null;
    parent_group_activities: string[] | null;
    notes: string | null;
  }>;
  const openTodos = (openRes.data ?? []) as Array<{
    title: string;
    edited_title: string | null;
    due_date: string | null;
    category: string | null;
  }>;
  const intel = (intelRes.data ?? []) as Array<{
    source: string;
    intel_type: string | null;
    summary: string;
    detail: string | null;
    action_needed: string | null;
  }>;
  const feedback = (fbRes.data ?? []) as Array<{ feedback: string }>;

  const upcoming = openTodos
    .filter((t) => t.due_date && t.due_date >= todayIso && t.due_date <= untilIso)
    .map((t) => ({ task: t.edited_title ?? t.title, due: t.due_date, category: t.category }));
  const selections = openTodos
    .filter((t) => t.category === "SELECTION")
    .map((t) => ({ task: t.edited_title ?? t.title, due: t.due_date }));

  if (logs.length === 0 && openTodos.length === 0 && sched === 0 && intel.length === 0) {
    return NextResponse.json(
      { ok: false, error: "Not enough data for this job yet — pull logs / pay app / emails first." },
      { status: 400 }
    );
  }

  const usd = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
  const data = {
    contract_value: sched > 0 ? usd(sched) : "unknown",
    billed_to_date: sched > 0 ? usd(comp) : "unknown",
    percent_complete: pct !== null ? `${pct}%` : "unknown",
    committed_to_vendors: committed > 0 ? usd(committed) : "unknown",
    open_commitments: outstanding > 0 ? usd(outstanding) : usd(0),
    recent_activity: logs.map((l) => ({
      date: l.log_date,
      activities: l.parent_group_activities ?? [],
      notes: (l.notes ?? "").slice(0, 400),
    })),
    captured_intel: intel.map((i) => ({
      kind: i.intel_type ?? i.source,
      summary: i.summary,
      detail: (i.detail ?? "").slice(0, 300),
      action_needed: i.action_needed ?? null,
    })),
    upcoming_tasks: upcoming,
    pending_selections: selections,
  };

  const feedbackBlock = feedback.length
    ? `\nPM FEEDBACK ON PRIOR UPDATES (apply this to voice + emphasis; newest first):\n${feedback
        .map((f) => `- ${f.feedback}`)
        .join("\n")}\n`
    : "";

  const prompt = `You are writing a ${period} construction update FOR THE HOMEOWNER CLIENT of a Ross Built custom home. Warm, clear, confident, and honest — no internal jargon, no sub names unless helpful, no to-do IDs. Speak to the client about THEIR home.

JOB: ${job.name}${job.address ? ` — ${job.address}` : ""}
AS OF: ${todayIso}  (period: ${period})
${feedbackBlock}
DATA (already computed; budget figures are exact dollars):
${JSON.stringify(data, null, 2)}

Write a ${period} update with:
- greeting: one warm sentence naming their home/project and the period.
- budget: 2-3 sentences on where the budget stands — contract value, how much is complete/billed, percent complete, and what's committed/outstanding — framed reassuringly but truthfully. If a figure is "unknown", omit it gracefully rather than saying "unknown".
- schedule: 2-4 sentences on what's been accomplished recently (synthesize recent_activity + captured_intel) and whether things are progressing well.
- upcoming_selections: a list of decisions/selections the client should make soon (from pending_selections + selection-type upcoming_tasks), each with rough timing if known. EMPTY list if none.
- whats_next: 2-4 short bullets of what happens next on site (from upcoming_tasks + captured_intel commitments), plain client language with dates where known.
- closing: one friendly closing line inviting questions.

Return ONLY via the tool.`;

  const anthropicKey = process.env.ANTHROPIC_API_KEY;
  if (!anthropicKey) {
    return NextResponse.json({ ok: false, error: "Server missing ANTHROPIC_API_KEY" }, { status: 500 });
  }
  const model = await getConfig("WEEKLY_REPORT_MODEL", "claude-opus-4-7");
  const client = new Anthropic({ apiKey: anthropicKey });
  const tool: Anthropic.Tool = {
    name: "emit_client_summary",
    description: "Return the client-facing project update.",
    input_schema: {
      type: "object",
      properties: {
        greeting: { type: "string" },
        budget: { type: "string" },
        schedule: { type: "string" },
        upcoming_selections: { type: "array", items: { type: "string" } },
        whats_next: { type: "array", items: { type: "string" } },
        closing: { type: "string" },
      },
      required: ["greeting", "budget", "schedule", "upcoming_selections", "whats_next", "closing"],
    },
  };

  let parsed: ReportBody;
  const startedAt = Date.now();
  try {
    const resp = await client.messages.create({
      model,
      max_tokens: 2000,
      tools: [tool],
      tool_choice: { type: "tool", name: "emit_client_summary" },
      messages: [{ role: "user", content: prompt }],
    });
    const toolUse = resp.content.find((b) => b.type === "tool_use");
    if (!toolUse || toolUse.type !== "tool_use") {
      return NextResponse.json({ ok: false, error: "Claude returned no tool_use block" }, { status: 502 });
    }
    parsed = normalizeBody(toolUse.input);
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: `Claude error: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 }
    );
  }

  const user = await currentUser();
  const weekStart = currentWeekStart();

  // Upsert the DRAFT. A regenerate supersedes the prior draft: reset status to
  // draft, clear PM edits + any approval so a stale approval can't ride along.
  const { data: saved, error: upErr } = await supabase
    .from("weekly_reports")
    .upsert(
      {
        job_id: jobId,
        week_start: weekStart,
        period,
        status: "draft",
        body: parsed,
        edited_body: null,
        model,
        generated_by: user?.email ?? null,
        generated_at: new Date().toISOString(),
        approved_by: null,
        approved_at: null,
        sent_by: null,
        sent_at: null,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "job_id,week_start" }
    )
    .select("*")
    .maybeSingle();

  if (upErr) {
    return NextResponse.json({ ok: false, error: `save failed: ${upErr.message}` }, { status: 500 });
  }

  return NextResponse.json({
    ok: true,
    period,
    week_start: weekStart,
    report: saved,
    meta: {
      percent_complete: pct,
      log_count: logs.length,
      intel_count: intel.length,
      upcoming_count: upcoming.length,
      selection_count: selections.length,
      feedback_count: feedback.length,
      elapsed_ms: Date.now() - startedAt,
    },
  });
}
