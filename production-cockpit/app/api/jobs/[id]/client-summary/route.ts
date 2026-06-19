// POST /api/jobs/[id]/client-summary
// Body: { period?: "weekly" | "monthly" }  (default "weekly")
//
// Generates a warm, client-facing update — budget, schedule, and upcoming
// selections — from the job's pay app, POs, recent daily logs, and open todos.
// Uses Claude tool-use for a structurally-guaranteed result. Generated on
// demand (not persisted); the UI offers a copy button for sharing.

import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { supabaseServer } from "@/lib/supabase";
import { businessToday, businessDateOffset } from "@/lib/today";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
const MODEL = "claude-opus-4-7";

interface ClientSummary {
  greeting: string;
  budget: string;
  schedule: string;
  upcoming_selections: string[];
  whats_next: string[];
  closing: string;
}

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const jobId = params.id;
  const supabase = supabaseServer();

  let body: { period?: string } = {};
  try {
    body = await req.json();
  } catch {
    /* empty body fine */
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

  const [payRes, poRes, logsRes, openRes] = await Promise.all([
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
  ]);

  // Budget rollup.
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
  const upcoming = openTodos
    .filter((t) => t.due_date && t.due_date >= todayIso && t.due_date <= untilIso)
    .map((t) => ({ task: t.edited_title ?? t.title, due: t.due_date, category: t.category }));
  const selections = openTodos
    .filter((t) => t.category === "SELECTION")
    .map((t) => ({ task: t.edited_title ?? t.title, due: t.due_date }));

  if (logs.length === 0 && openTodos.length === 0 && sched === 0) {
    return NextResponse.json(
      { ok: false, error: "Not enough data for this job yet — pull logs / pay app first." },
      { status: 400 }
    );
  }

  const usd = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
  const data = {
    contract_value: sched > 0 ? usd(sched) : "unknown",
    billed_to_date: sched > 0 ? usd(comp) : "unknown",
    // Send "unknown" (not null) so the prompt's "omit unknowns" rule applies
    // instead of Claude seeing a literal null.
    percent_complete: pct !== null ? `${pct}%` : "unknown",
    committed_to_vendors: committed > 0 ? usd(committed) : "unknown",
    open_commitments: outstanding > 0 ? usd(outstanding) : usd(0),
    recent_activity: logs.map((l) => ({
      date: l.log_date,
      activities: l.parent_group_activities ?? [],
      notes: (l.notes ?? "").slice(0, 400),
    })),
    upcoming_tasks: upcoming,
    pending_selections: selections,
  };

  const prompt = `You are writing a ${period} construction update FOR THE HOMEOWNER CLIENT of a Ross Built custom home. Warm, clear, confident, and honest — no internal jargon, no sub names unless helpful, no to-do IDs. Speak to the client about THEIR home.

JOB: ${job.name}${job.address ? ` — ${job.address}` : ""}
AS OF: ${todayIso}  (period: ${period})

DATA (already computed; budget figures are exact dollars):
${JSON.stringify(data, null, 2)}

Write a ${period} update with:
- greeting: one warm sentence naming their home/project and the period.
- budget: 2-3 sentences on where the budget stands — contract value, how much is complete/billed, percent complete, and what's committed/outstanding — framed reassuringly but truthfully. If a figure is "unknown", omit it gracefully rather than saying "unknown".
- schedule: 2-4 sentences on what's been accomplished recently (synthesize recent_activity) and whether things are progressing well.
- upcoming_selections: a list of decisions/selections the client should make soon (from pending_selections + any selection-type upcoming_tasks), each with rough timing if known. EMPTY list if none.
- whats_next: 2-4 short bullets of what happens next on site (from upcoming_tasks), in plain client language with dates where known.
- closing: one friendly closing line inviting questions.

Return ONLY via the tool.`;

  const anthropicKey = process.env.ANTHROPIC_API_KEY;
  if (!anthropicKey) {
    return NextResponse.json({ ok: false, error: "Server missing ANTHROPIC_API_KEY" }, { status: 500 });
  }
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

  let parsed: ClientSummary;
  const startedAt = Date.now();
  try {
    const resp = await client.messages.create({
      model: MODEL,
      max_tokens: 2000,
      tools: [tool],
      tool_choice: { type: "tool", name: "emit_client_summary" },
      messages: [{ role: "user", content: prompt }],
    });
    const toolUse = resp.content.find((b) => b.type === "tool_use");
    if (!toolUse || toolUse.type !== "tool_use") {
      return NextResponse.json({ ok: false, error: "Claude returned no tool_use block" }, { status: 502 });
    }
    parsed = toolUse.input as ClientSummary;
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: `Claude error: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 }
    );
  }

  return NextResponse.json({
    ok: true,
    period,
    summary: parsed,
    meta: {
      percent_complete: pct,
      log_count: logs.length,
      upcoming_count: upcoming.length,
      selection_count: selections.length,
      elapsed_ms: Date.now() - startedAt,
    },
  });
}
