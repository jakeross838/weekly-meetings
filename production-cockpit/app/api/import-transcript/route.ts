import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // Allow up to 60s for Claude call

interface ExtractedItem {
  title: string;
  sub_name: string | null;
  job: string;
  priority: "URGENT" | "HIGH" | "NORMAL";
  due_date: string | null;
  category:
    | "SELECTION"
    | "SCHEDULE"
    | "PROCUREMENT"
    | "SUB-TRADE"
    | "CLIENT"
    | "QUALITY"
    | "BUDGET"
    | "ADMIN";
  type:
    | "SELECTION"
    | "CONFIRMATION"
    | "PRICING"
    | "SCHEDULE"
    | "CO_INVOICE"
    | "FIELD"
    | "FOLLOWUP";
}

interface ExtractionResult {
  summary: string;
  items: ExtractedItem[];
}

/**
 * Stripped-down version of the weekly-prompt.md instructions — focused on
 * action-item extraction only, grouped per sub. Skips the lookBehind /
 * headsUp / lookAhead / financial / issues sections.
 */
function buildPrompt(
  transcript: string,
  pmName: string,
  meetingDate: string,
  meetingType: "SITE" | "OFFICE",
  subCatalog: { id: string; name: string; aliases: string[] | null }[]
): string {
  const catalog = subCatalog
    .map((s) => {
      const aliases = (s.aliases ?? []).filter(Boolean).join(", ");
      return `  ${s.name}${aliases ? ` [aliases: ${aliases}]` : ""}`;
    })
    .join("\n");

  return `You are extracting action items from a Ross Built construction meeting transcript.

META: PM=${pmName} | Date=${meetingDate} | Type=${meetingType}

KNOWN SUBS (use the exact "name" string when referenced):
${catalog}

Read the transcript. Return a JSON object with this exact shape:

{
  "summary": "<1-2 sentence overview of the meeting>",
  "items": [
    {
      "title": "<owner + verb + specific deliverable + hard due date>",
      "sub_name": "<exact name from catalog, or null if no sub is referenced>",
      "job": "<job name — e.g., Fish, Krauss, Markgraf, Pou, etc.>",
      "priority": "URGENT" | "HIGH" | "NORMAL",
      "due_date": "<YYYY-MM-DD or null>",
      "category": "SELECTION|SCHEDULE|PROCUREMENT|SUB-TRADE|CLIENT|QUALITY|BUDGET|ADMIN",
      "type": "SELECTION|CONFIRMATION|PRICING|SCHEDULE|CO_INVOICE|FIELD|FOLLOWUP"
    }
  ]
}

Rules:
- Every item must pass the Monday Morning Test: specific person + specific verb + specific deliverable + hard date.
- Priority: URGENT if due ≤3 days or blocks critical path or financial exposure; HIGH if due ≤7 days or sub coordination; NORMAL otherwise.
- Category SELECTION = waiting on client/designer to pick something (colors, finishes, hardware).
- Category SCHEDULE = sub start/end dates, schedule moves.
- Category PROCUREMENT = orders, deliveries, buyouts.
- Category SUB-TRADE = sub performance concerns (NOT scheduling).
- Use sub_name = null when the item is purely internal (PM action only).
- Do NOT fabricate. Skip vague items entirely rather than inventing detail.

Return ONLY the JSON. No prose, no fences.`;
}

export async function POST(req: NextRequest) {
  let body: {
    transcript?: string;
    pm_id?: string;
    pm_name?: string;
    meeting_date?: string;
    meeting_type?: "SITE" | "OFFICE";
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON" },
      { status: 400 }
    );
  }

  const transcript = body.transcript?.trim();
  const pmId = body.pm_id?.trim();
  const pmName = body.pm_name?.trim();
  const meetingDate = body.meeting_date?.trim();
  const meetingType = body.meeting_type === "OFFICE" ? "OFFICE" : "SITE";

  if (!transcript || transcript.length < 100) {
    return NextResponse.json(
      { ok: false, error: "Transcript missing or too short" },
      { status: 400 }
    );
  }
  if (!pmId || !pmName || !meetingDate) {
    return NextResponse.json(
      { ok: false, error: "Missing pm_id, pm_name, or meeting_date" },
      { status: 400 }
    );
  }

  // Load sub catalog so Claude can canonicalize names.
  const supabase = supabaseServer();
  const subsRes = await supabase.from("subs").select("id, name, aliases");
  const subCatalog = (subsRes.data ?? []) as {
    id: string;
    name: string;
    aliases: string[] | null;
  }[];
  const subByName: Record<string, { id: string; name: string }> = {};
  for (const s of subCatalog) {
    subByName[s.name.toLowerCase()] = { id: s.id, name: s.name };
  }

  const anthropicKey = process.env.ANTHROPIC_API_KEY;
  if (!anthropicKey) {
    return NextResponse.json(
      { ok: false, error: "Server missing ANTHROPIC_API_KEY" },
      { status: 500 }
    );
  }

  const client = new Anthropic({ apiKey: anthropicKey });
  const prompt = buildPrompt(transcript, pmName, meetingDate, meetingType, subCatalog);

  let raw = "";
  try {
    const resp = await client.messages.create({
      model: "claude-opus-4-7",
      max_tokens: 8000,
      messages: [
        {
          role: "user",
          content: `${prompt}\n\n---\n\nTRANSCRIPT:\n${transcript}`,
        },
      ],
    });
    raw = resp.content
      .filter((b) => b.type === "text")
      .map((b) => (b as { type: "text"; text: string }).text)
      .join("");
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: `Claude error: ${err instanceof Error ? err.message : String(err)}`,
      },
      { status: 502 }
    );
  }

  // Parse JSON from response (Claude sometimes wraps in ```json)
  const m = raw.match(/\{[\s\S]*\}/);
  if (!m) {
    return NextResponse.json(
      { ok: false, error: "No JSON in Claude response", raw: raw.slice(0, 500) },
      { status: 502 }
    );
  }
  let parsed: ExtractionResult;
  try {
    parsed = JSON.parse(m[0]) as ExtractionResult;
  } catch (e) {
    return NextResponse.json(
      {
        ok: false,
        error: `JSON parse failed: ${e instanceof Error ? e.message : String(e)}`,
      },
      { status: 502 }
    );
  }

  // Canonicalize sub_name → sub_id, group items per sub
  const groupedBySub: Record<
    string,
    { sub_id: string | null; sub_name: string | null; items: ExtractedItem[] }
  > = {};
  const noSubKey = "__no_sub__";
  for (const item of parsed.items ?? []) {
    let sid: string | null = null;
    let sname: string | null = null;
    if (item.sub_name) {
      const matched = subByName[item.sub_name.toLowerCase()];
      if (matched) {
        sid = matched.id;
        sname = matched.name;
      } else {
        sname = item.sub_name;
      }
    }
    const key = sid || sname || noSubKey;
    if (!groupedBySub[key]) {
      groupedBySub[key] = { sub_id: sid, sub_name: sname, items: [] };
    }
    groupedBySub[key].items.push(item);
  }

  return NextResponse.json({
    ok: true,
    summary: parsed.summary,
    grouped: Object.values(groupedBySub),
    totalItems: (parsed.items ?? []).length,
  });
}
