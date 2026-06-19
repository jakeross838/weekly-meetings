// POST /v2/api/daily-logs/extract-photos
// Body: { log_ids?: string[], limit?: number }
//
// Walks daily_logs rows that have photo_urls but no photo_summary yet,
// calls Claude (vision) for up to `limit` of them, and writes a structured
// JSON summary back into daily_logs.photo_summary. One log == one Claude
// call so a single failure doesn't poison the batch.
//
// The summary schema is:
//   { headline, work_stage, subs_visible, work_observed, hazards, weather_notes, confidence }
//
// Notes:
//  - Only URL-fetchable photos work. BT-internal URLs that require auth
//    will fail; the route returns the per-log error in the response so the
//    operator can investigate.
//  - This is rate-limited by `limit` (default 10) to keep Claude bills
//    bounded per click.

import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import Anthropic from "@anthropic-ai/sdk";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const maxDuration = 300; // Claude vision over a photo batch — give it room

// Photos in daily_logs.photo_urls may be either remote URLs (presigned BT,
// public hosts, etc.) or absolute local file paths written by the
// buildertrend-scraper (e.g. C:\Users\Greg\buildertrend-scraper\photos\...).
// We detect path-vs-URL and base64-encode local files for the Claude call
// so the scraper-driven flow works without a public host.
function isLocalPath(s: string): boolean {
  if (s.startsWith("file://")) return true;
  if (/^https?:\/\//i.test(s)) return false;
  // Windows: "C:\..." or "C:/..."
  if (/^[A-Za-z]:[\\/]/.test(s)) return true;
  // POSIX absolute
  if (s.startsWith("/")) return true;
  return false;
}

function mediaTypeFor(path: string): "image/jpeg" | "image/png" | "image/webp" | "image/gif" {
  const lower = path.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".gif")) return "image/gif";
  return "image/jpeg";
}

async function buildImageBlock(
  src: string
): Promise<Anthropic.Messages.ContentBlockParam | null> {
  if (!isLocalPath(src)) {
    return {
      type: "image",
      source: { type: "url", url: src },
    } as Anthropic.Messages.ContentBlockParam;
  }
  const filePath = src.startsWith("file://")
    ? decodeURI(src.slice("file://".length).replace(/^\/(?=[A-Za-z]:)/, ""))
    : src;
  try {
    const bytes = await fs.readFile(filePath);
    return {
      type: "image",
      source: {
        type: "base64",
        media_type: mediaTypeFor(filePath),
        data: bytes.toString("base64"),
      },
    } as Anthropic.Messages.ContentBlockParam;
  } catch {
    // Caller treats null as "skip this photo".
    return null;
  }
}

const MAX_PHOTOS_PER_LOG = 6;
const DEFAULT_BATCH_LIMIT = 10;

interface ExtractedSummary {
  headline: string;
  work_stage: string | null;
  subs_visible: string[];
  work_observed: string[];
  hazards: string[];
  weather_notes: string | null;
  confidence: "high" | "medium" | "low";
}

type LogRow = {
  id: string;
  job_key: string;
  log_date: string | null;
  photo_urls: string[] | null;
  notes: string | null;
  parent_group_activities: string[] | null;
  crews_present: string[] | null;
};

function buildPrompt(row: LogRow): string {
  const ctx: string[] = [];
  if (row.log_date) ctx.push(`Date: ${row.log_date}`);
  if (row.job_key) ctx.push(`Job: ${row.job_key}`);
  if (row.crews_present?.length)
    ctx.push(`Crews on site (per BT): ${row.crews_present.join(", ")}`);
  if (row.parent_group_activities?.length)
    ctx.push(`Activities tagged: ${row.parent_group_activities.join(", ")}`);
  if (row.notes) ctx.push(`PM notes: ${row.notes.slice(0, 600)}`);
  const ctxBlock = ctx.length > 0 ? ctx.join("\n") + "\n\n" : "";
  return `${ctxBlock}You are summarizing the photos from a single Buildertrend daily log on a Ross Built custom-home job. Look at every photo and return ONE JSON object with this exact shape:

{
  "headline": "<≤80 chars — one-sentence what's happening overall>",
  "work_stage": "<one of: site prep, foundation, framing, dry-in, rough-in, drywall, finish, exterior, punch, or null if mixed/unclear>",
  "subs_visible": ["<branded trade names visible on shirts/vehicles, else trade nouns like 'electrician', 'framer'>"],
  "work_observed": ["<concrete observation 1>", "<observation 2>", "..."],
  "hazards": ["<safety concern — open trenches, missing fall protection, exposed wire, etc. EMPTY array if none>"],
  "weather_notes": "<conditions visible in photos (sun, rain, mud, standing water) or null>",
  "confidence": "high|medium|low"
}

Rules:
- If the photos do not actually show construction (e.g. blank office photos, screenshots), return confidence "low" and put a note in headline.
- Do NOT invent subs or work that isn't visible.
- The "work_observed" array is the main payload — 3-7 specific items is ideal.
- Return ONLY the JSON, no prose, no fences.`;
}

export async function POST(req: NextRequest) {
  const supabase = supabaseServer();

  let body: { log_ids?: string[]; limit?: number } = {};
  try {
    body = await req.json();
  } catch {
    // empty body is fine — defaults
  }

  const anthropicKey = process.env.ANTHROPIC_API_KEY;
  if (!anthropicKey) {
    return NextResponse.json(
      { ok: false, error: "Server missing ANTHROPIC_API_KEY" },
      { status: 500 }
    );
  }
  const client = new Anthropic({ apiKey: anthropicKey });

  const limit = Math.max(
    1,
    Math.min(50, body.limit ?? DEFAULT_BATCH_LIMIT)
  );

  // Pull candidate rows. If log_ids passed, use those; otherwise grab the
  // most recent N logs that have photos but no summary yet.
  let query = supabase
    .from("daily_logs")
    .select(
      "id, job_key, log_date, photo_urls, notes, parent_group_activities, crews_present, photo_summary"
    )
    .not("photo_urls", "is", null)
    .limit(limit);
  if (Array.isArray(body.log_ids) && body.log_ids.length > 0) {
    query = query.in("id", body.log_ids);
  } else {
    query = query.is("photo_summary", null).order("log_date", {
      ascending: false,
    });
  }
  const { data: rows, error } = await query;
  if (error) {
    return NextResponse.json(
      { ok: false, error: `daily_logs query failed: ${error.message}` },
      { status: 500 }
    );
  }
  const candidates = (rows ?? []) as (LogRow & { photo_summary: unknown })[];
  const work = candidates.filter(
    (r) => Array.isArray(r.photo_urls) && r.photo_urls.length > 0
  );

  type PerLog = {
    log_id: string;
    job_key: string;
    log_date: string | null;
    ok: boolean;
    photoCount: number;
    summary?: ExtractedSummary;
    error?: string;
  };
  const results: PerLog[] = [];

  // Tool-use forces valid structured output (no regex / JSON.parse), matching
  // the summary + extractor routes. Defined once, reused for every log.
  const photoTool: Anthropic.Tool = {
    name: "emit_photo_summary",
    description: "Return the structured summary of this daily log's photos.",
    input_schema: {
      type: "object",
      properties: {
        headline: { type: "string" },
        work_stage: { type: ["string", "null"] },
        subs_visible: { type: "array", items: { type: "string" } },
        work_observed: { type: "array", items: { type: "string" } },
        hazards: { type: "array", items: { type: "string" } },
        weather_notes: { type: ["string", "null"] },
        confidence: { type: "string", enum: ["high", "medium", "low"] },
      },
      required: [
        "headline",
        "subs_visible",
        "work_observed",
        "hazards",
        "confidence",
      ],
    },
  };

  for (const row of work) {
    const photos = (row.photo_urls ?? []).slice(0, MAX_PHOTOS_PER_LOG);
    if (photos.length === 0) continue;

    const content: Anthropic.Messages.ContentBlockParam[] = [];
    let skipped = 0;
    for (const src of photos) {
      const block = await buildImageBlock(src);
      if (block) content.push(block);
      else skipped += 1;
    }
    if (content.length === 0) {
      results.push({
        log_id: row.id,
        job_key: row.job_key,
        log_date: row.log_date,
        ok: false,
        photoCount: photos.length,
        error: `All ${photos.length} photos unreadable (local files missing? URLs require auth?)`,
      });
      continue;
    }
    if (skipped > 0) {
      // Don't fail the whole log on a single missing file — just note it.
      console.warn(
        `[extract-photos] log ${row.id}: skipped ${skipped} unreadable photo(s)`
      );
    }
    content.push({ type: "text", text: buildPrompt(row) });

    try {
      const resp = await client.messages.create({
        model: "claude-opus-4-7",
        max_tokens: 1200,
        tools: [photoTool],
        tool_choice: { type: "tool", name: "emit_photo_summary" },
        messages: [{ role: "user", content }],
      });
      const toolUse = resp.content.find((b) => b.type === "tool_use");
      if (!toolUse || toolUse.type !== "tool_use") {
        results.push({
          log_id: row.id,
          job_key: row.job_key,
          log_date: row.log_date,
          ok: false,
          photoCount: photos.length,
          error: "Claude returned no tool_use block",
        });
        continue;
      }
      const parsed = toolUse.input as ExtractedSummary;

      // Persist. The column is jsonb so we can write the object directly.
      const { error: upErr } = await supabase
        .from("daily_logs")
        .update({
          photo_summary: parsed,
          photo_summary_at: new Date().toISOString(),
        })
        .eq("id", row.id);
      if (upErr) {
        results.push({
          log_id: row.id,
          job_key: row.job_key,
          log_date: row.log_date,
          ok: false,
          photoCount: photos.length,
          error: `update: ${upErr.message}`,
        });
        continue;
      }

      results.push({
        log_id: row.id,
        job_key: row.job_key,
        log_date: row.log_date,
        ok: true,
        photoCount: photos.length,
        summary: parsed,
      });
    } catch (e) {
      // Vision call can fail if BT URLs require auth or if Claude rejects
      // the image. Surface the message verbatim so the operator knows
      // whether to switch to base64 / re-host.
      results.push({
        log_id: row.id,
        job_key: row.job_key,
        log_date: row.log_date,
        ok: false,
        photoCount: photos.length,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }

  // Invalidate sub profiles since they render photo_summary rows.
  revalidatePath("/sub/[id]", "page");
  revalidatePath("/subs");

  return NextResponse.json({
    ok: true,
    considered: candidates.length,
    processed: results.filter((r) => r.ok).length,
    failed: results.filter((r) => !r.ok).length,
    results,
  });
}
