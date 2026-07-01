// POST /v2/api/weekly/[job_id]/generate-todos
//
// Proposes to-dos from the job's OPEN COMMITMENTS + GAPS — captured intel with an
// action_needed, past-due/stale items, unresolved issues, and money left
// outstanding on POs. Returns PROPOSALS ONLY; it writes nothing. A human accepts
// each proposal in the UI (which POSTs to /api/todos/create), honoring the rule
// that AI output is reviewed before it becomes real.
//
// Where the data allows, each proposal carries a `billing_ref` string linking it
// to the draw/PO it relates to — completion drives billing.

import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { supabaseServer } from "@/lib/supabase";
import { businessToday, businessDateOffset } from "@/lib/today";
import { getConfig } from "@/lib/app-config";
import { CATEGORIES } from "@/lib/categories";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(_req: NextRequest, { params }: { params: { job_id: string } }) {
  const jobId = params.job_id;
  const supabase = supabaseServer();

  const jobRes = await supabase.from("jobs").select("id, name").eq("id", jobId).maybeSingle();
  if (!jobRes.data) return NextResponse.json({ ok: false, error: `job not found: ${jobId}` }, { status: 404 });
  const job = jobRes.data as { id: string; name: string };

  const todayIso = businessToday();
  const sinceIso = businessDateOffset(-45);
  const sinceTs = new Date(sinceIso + "T00:00:00Z").toISOString();

  const [intelRes, openRes, poRes] = await Promise.all([
    supabase
      .from("job_intel")
      .select("source, intel_type, summary, detail, action_needed, sent_at")
      .eq("job_id", jobId)
      .eq("hidden", false)
      .gte("created_at", sinceTs)
      .order("sent_at", { ascending: false, nullsFirst: false })
      .limit(60),
    supabase
      .from("todos")
      .select("title, edited_title, due_date, category, status")
      .eq("job", job.name)
      .in("status", ["NOT_STARTED", "IN_PROGRESS", "BLOCKED"])
      .order("due_date", { ascending: true, nullsFirst: false })
      .limit(150),
    supabase
      .from("purchase_orders")
      .select("po_number, title, vendor, amount_remaining, work_status, paid_status")
      .ilike("job_key", `${job.name}%`)
      .eq("hidden", false)
      .gt("amount_remaining", 0)
      .order("amount_remaining", { ascending: false })
      .limit(40),
  ]);

  const intel = (intelRes.data ?? []) as Array<Record<string, unknown>>;
  const openTodos = (openRes.data ?? []) as Array<{
    title: string;
    edited_title: string | null;
    due_date: string | null;
    category: string | null;
    status: string;
  }>;
  const pos = (poRes.data ?? []) as Array<Record<string, unknown>>;

  const pastDue = openTodos.filter((t) => t.due_date && t.due_date < todayIso);

  if (intel.length === 0 && pastDue.length === 0 && pos.length === 0) {
    return NextResponse.json({ ok: true, proposals: [], note: "No open commitments or gaps detected." });
  }

  const data = {
    today: todayIso,
    existing_open_todos: openTodos.map((t) => ({
      task: t.edited_title ?? t.title,
      due: t.due_date,
      status: t.status,
    })),
    past_due_todos: pastDue.map((t) => ({ task: t.edited_title ?? t.title, due: t.due_date })),
    captured_intel: intel.map((i) => ({
      kind: i.intel_type ?? i.source,
      summary: i.summary,
      detail: (typeof i.detail === "string" ? i.detail : "").slice(0, 300),
      action_needed: i.action_needed ?? null,
    })),
    outstanding_pos: pos.map((p) => ({
      po: p.po_number,
      title: p.title,
      vendor: p.vendor,
      outstanding: p.amount_remaining,
      work_status: p.work_status,
    })),
  };

  const prompt = `You are a master construction PM at Ross Built. From the data below for job "${job.name}", propose the FEW highest-leverage NEW to-dos that close open commitments or fill gaps. Rules:
- Only propose what the data supports. Do NOT invent facts.
- Do NOT duplicate something already in existing_open_todos.
- Prefer items tied to a commitment (someone owes something), an unresolved issue, or money left outstanding on a PO.
- Each to-do: a concrete, specific action (who/what), a due date ONLY if the data implies one (else null; never a vague timeframe), a category from this exact set: ${CATEGORIES.join(", ")}, a priority (URGENT | HIGH | NORMAL), a one-line rationale, and — WHERE THE DATA ALLOWS — a billing_ref naming the PO/draw it relates to (else null).
- Return 0 items if nothing is clearly actionable. Quality over quantity (aim 3-8 max).

DATA:
${JSON.stringify(data, null, 2)}

Return ONLY via the tool.`;

  const anthropicKey = process.env.ANTHROPIC_API_KEY;
  if (!anthropicKey) return NextResponse.json({ ok: false, error: "Server missing ANTHROPIC_API_KEY" }, { status: 500 });
  const model = await getConfig("INTEL_ANALYZE_MODEL", "claude-sonnet-4-6");
  const client = new Anthropic({ apiKey: anthropicKey });

  const tool: Anthropic.Tool = {
    name: "emit_todos",
    description: "Return proposed to-dos.",
    input_schema: {
      type: "object",
      properties: {
        todos: {
          type: "array",
          items: {
            type: "object",
            properties: {
              title: { type: "string" },
              due_date: { type: ["string", "null"], description: "YYYY-MM-DD or null" },
              category: { type: "string", enum: CATEGORIES as unknown as string[] },
              priority: { type: "string", enum: ["URGENT", "HIGH", "NORMAL"] },
              rationale: { type: "string" },
              billing_ref: { type: ["string", "null"] },
            },
            required: ["title", "category", "priority", "rationale"],
          },
        },
      },
      required: ["todos"],
    },
  };

  try {
    const resp = await client.messages.create({
      model,
      max_tokens: 1500,
      tools: [tool],
      tool_choice: { type: "tool", name: "emit_todos" },
      messages: [{ role: "user", content: prompt }],
    });
    const toolUse = resp.content.find((b) => b.type === "tool_use");
    if (!toolUse || toolUse.type !== "tool_use") {
      return NextResponse.json({ ok: false, error: "Claude returned no tool_use block" }, { status: 502 });
    }
    const out = toolUse.input as { todos?: unknown };
    const proposals = Array.isArray(out.todos) ? out.todos : [];
    return NextResponse.json({ ok: true, proposals });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: `Claude error: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 }
    );
  }
}
