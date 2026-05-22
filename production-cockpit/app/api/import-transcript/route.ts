import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { supabaseServer } from "@/lib/supabase";
import { scrubRelativeDates } from "@/lib/scrub-relative-dates";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // Allow up to 60s for Claude call

interface ExtractedItem {
  title: string;
  sub_name: string | null;
  job: string;
  priority: "URGENT" | "HIGH" | "NORMAL";
  due_date: string | null;
  // AI-suggested fallback due date for open-ended items (when due_date is
  // null). Populated for every item with a defensible estimate based on
  // priority + category. The UI shows it as a one-click "use this" hint
  // next to the empty date field — never auto-applied.
  suggested_due_date: string | null;
  suggested_due_date_reason: string | null;
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
  // Verbatim transcript snippet (≤200 chars) that grounds this item.
  // Used by the UI to show "where Claude got this" and to keep extraction
  // honest — items without quotable evidence are filtered out.
  source_excerpt: string | null;
}

interface ExtractionResult {
  summary: string;
  items: ExtractedItem[];
  // Job names referenced anywhere in the transcript, including jobs that
  // don't have action items of their own. Powers the "also mentioned" banner
  // on the preview screen — reminds the operator to check those job pages.
  jobs_mentioned: string[];
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
  meetingType: "SITE" | "OFFICE" | "OTHER",
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

KNOWN SUBS (canonicalize references to these exact "name" strings — match aliases first, then partial/last-name matches; only leave sub_name null if no sub is plausibly referenced):
${catalog}

Read the transcript. Return a JSON object with this exact shape:

{
  "summary": "<1-2 sentence overview of the meeting>",
  "jobs_mentioned": ["<job-name>", ...],
  "items": [
    {
      "title": "<owner + verb + specific deliverable + hard due date>",
      "sub_name": "<exact name from catalog above, or null>",
      "job": "<job name — Fish, Krauss, Markgraf, Pou, Dewberry, Drummond, Molinari, Ruthven, Biales, Harllee, Clark, Johnson, etc.>",
      "priority": "URGENT" | "HIGH" | "NORMAL",
      "due_date": "<YYYY-MM-DD or null>",
      "suggested_due_date": "<YYYY-MM-DD — your best-guess fallback even when due_date is null>",
      "suggested_due_date_reason": "<≤80 chars explaining why this date>",
      "category": "SELECTION|SCHEDULE|PROCUREMENT|SUB-TRADE|CLIENT|QUALITY|BUDGET|ADMIN",
      "type": "SELECTION|CONFIRMATION|PRICING|SCHEDULE|CO_INVOICE|FIELD|FOLLOWUP",
      "source_excerpt": "<≤200 chars verbatim transcript snippet that grounds this item>"
    }
  ]
}

AUTO-MATCH RULES (do these before emitting any item):

1. SUB MATCHING — work hard to fill sub_name. If the speaker says "Terry", check the aliases in the catalog above. If they say "Walter", match "Walter Drywall". If they say "Watts", match "Jeff Watts Plastering and Stucco". Only return null when the action is genuinely PM-internal (Lee to send X, Jake to draft Y) AND no sub is named.

2. DATE INFERENCE from the meeting date ${meetingDate}:
   - "today" → ${meetingDate}
   - "tomorrow" → meeting_date + 1 day
   - "by Friday" / "this Friday" → next Friday on or after meeting_date
   - "by next week" / "early next week" → meeting_date + 7 days
   - "by end of month" → last day of meeting_date's month
   - "by [Month] [Day]" → resolve to YYYY-MM-DD using meeting_date's year (or next year if the date already passed)
   Return YYYY-MM-DD in due_date. Leave due_date null only if the transcript is genuinely open-ended.

   TITLE-DATE RULE — STRICT:
   The "title" field must NEVER contain a relative-time phrase. Forbidden
   substrings (case-insensitive): "today", "tomorrow", "yesterday", "tonight",
   "this week", "next week", "this month", "next month", "by Friday",
   "by Monday", "by [any weekday]", "this Friday", "next Friday",
   "this [weekday]", "end of week", "end of month", "soon", "ASAP",
   "in a few days", "shortly".

   If the action has a date, write the resolved YYYY-MM-DD into the title
   instead, e.g. "Walter to confirm drywall start 2026-05-22" — not
   "Walter to confirm drywall start tomorrow". If the action is
   genuinely open-ended, leave the date out of the title entirely
   (the due_date and suggested_due_date fields carry timing — the title
   should not duplicate or paraphrase relative time).

   If you find yourself writing one of the forbidden phrases, STOP, look up
   the resolved YYYY-MM-DD via the rules above, and substitute it.

   SUGGESTED FALLBACK (suggested_due_date) — ALWAYS populate this, even when
   due_date is set. When due_date has a value, suggested_due_date should
   equal it. When due_date is null, infer a sensible fallback from priority
   + category (each builds off meeting_date ${meetingDate}):
     • URGENT → meeting_date + 3 days
     • HIGH → meeting_date + 7 days
     • NORMAL + SELECTION/CLIENT → meeting_date + 14 days
     • NORMAL + SCHEDULE/PROCUREMENT/SUB-TRADE/QUALITY → meeting_date + 10 days
     • NORMAL + BUDGET/ADMIN → meeting_date + 21 days
   Write a short suggested_due_date_reason (≤80 chars) explaining the pick,
   e.g. "urgent — 3-day buffer" or "no explicit date, NORMAL procurement default".

3. CATEGORY INFERENCE — pick the most specific:
   - SELECTION = waiting on client/designer choice (colors, fixtures, finishes, hardware, paint specs)
   - SCHEDULE = sub start/end dates, sequencing, moves
   - PROCUREMENT = orders, deliveries, vendor buyouts, lead times
   - SUB-TRADE = sub performance concerns / quality / back-charges (NOT routine scheduling)
   - CLIENT = client communication, status updates, written approvals
   - QUALITY = quality assurance, rework, callbacks, hinge replacements, paint touch-ups
   - BUDGET = pricing, change orders, cost coding, back-charges with $ amounts
   - ADMIN = permits, policies, internal documents, company-wide rules

4. JOBS_MENTIONED — list every job name that appears in the transcript, even ones with no action items. The operator may need to check those job pages too. Dedupe but keep them.

5. SOURCE_EXCERPT — for each item, copy 1-3 sentences verbatim from the transcript that contain the trigger phrase. Cap at 200 characters with an ellipsis if you have to. DO NOT paraphrase. If you cannot find a quotable line, DROP THE ITEM — do not include it.

6. Every item must pass the Monday Morning Test: specific person + specific verb + specific deliverable + hard date.

7. Priority: URGENT if due ≤3 days or blocks critical path or has financial exposure; HIGH if due ≤7 days or involves sub coordination; NORMAL otherwise.

NEVER fabricate. If the transcript is vague, drop the item. The source_excerpt check is your honesty gate.

Return ONLY the JSON. No prose, no fences.`;
}

export async function POST(req: NextRequest) {
  let body: {
    transcript?: string;
    pm_id?: string;
    pm_name?: string;
    meeting_date?: string;
    meeting_type?: "SITE" | "OFFICE" | "OTHER";
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
  const meetingType =
    body.meeting_type === "OFFICE"
      ? "OFFICE"
      : body.meeting_type === "OTHER"
        ? "OTHER"
        : "SITE";

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

  // Force valid structured output via tool-use. Free-text JSON occasionally
  // came back malformed on big extractions (up to 8k tokens of nested items),
  // which blew up JSON.parse and 502'd the whole import. A tool schema makes
  // the output structurally guaranteed — no regex, no JSON.parse.
  const extractTool: Anthropic.Tool = {
    name: "emit_action_items",
    description: "Return the extracted meeting summary + action items.",
    input_schema: {
      type: "object",
      properties: {
        summary: { type: "string" },
        jobs_mentioned: { type: "array", items: { type: "string" } },
        items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              title: { type: "string" },
              sub_name: { type: ["string", "null"] },
              job: { type: "string" },
              priority: {
                type: "string",
                enum: ["URGENT", "HIGH", "NORMAL"],
              },
              due_date: { type: ["string", "null"] },
              suggested_due_date: { type: ["string", "null"] },
              suggested_due_date_reason: { type: ["string", "null"] },
              category: {
                type: "string",
                enum: [
                  "SELECTION",
                  "SCHEDULE",
                  "PROCUREMENT",
                  "SUB-TRADE",
                  "CLIENT",
                  "QUALITY",
                  "BUDGET",
                  "ADMIN",
                ],
              },
              type: {
                type: "string",
                enum: [
                  "SELECTION",
                  "CONFIRMATION",
                  "PRICING",
                  "SCHEDULE",
                  "CO_INVOICE",
                  "FIELD",
                  "FOLLOWUP",
                ],
              },
              source_excerpt: { type: ["string", "null"] },
            },
            required: ["title", "job", "priority", "category", "type"],
          },
        },
      },
      required: ["summary", "jobs_mentioned", "items"],
    },
  };

  let parsed: ExtractionResult;
  try {
    const resp = await client.messages.create({
      model: "claude-opus-4-7",
      max_tokens: 8000,
      tools: [extractTool],
      tool_choice: { type: "tool", name: "emit_action_items" },
      messages: [
        {
          role: "user",
          content: `${prompt}\n\n---\n\nTRANSCRIPT:\n${transcript}`,
        },
      ],
    });
    const toolUse = resp.content.find((b) => b.type === "tool_use");
    if (!toolUse || toolUse.type !== "tool_use") {
      return NextResponse.json(
        { ok: false, error: "Claude returned no tool_use block" },
        { status: 502 }
      );
    }
    parsed = toolUse.input as ExtractionResult;
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: `Claude error: ${err instanceof Error ? err.message : String(err)}`,
      },
      { status: 502 }
    );
  }

  // Defence-in-depth scrub: even with the strict prompt rule above, Claude
  // occasionally slips a relative-time phrase into the title. scrubRelativeDates
  // resolves every supported phrase ("tomorrow", "by Friday", "next week",
  // "end of month", "in 3 days", …) to an exact YYYY-MM-DD against the meeting
  // date, and strips genuinely vague spans ("ASAP", "soon", "this week"). The
  // same util runs again at the save boundary so manual edits can't reintroduce
  // a relative phrase. See lib/scrub-relative-dates.ts.
  for (const item of parsed.items ?? []) {
    item.title = scrubRelativeDates(item.title ?? "", meetingDate);
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
    jobs_mentioned: Array.isArray(parsed.jobs_mentioned)
      ? Array.from(new Set(parsed.jobs_mentioned.filter(Boolean)))
      : [],
    grouped: Object.values(groupedBySub),
    totalItems: (parsed.items ?? []).length,
  });
}
