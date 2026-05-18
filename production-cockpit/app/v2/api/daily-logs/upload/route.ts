// POST /v2/api/daily-logs/upload
// Body: { source?: string, payload: { byJob: { [jobKey]: BTRecord[] } } }
//
// Parses Buildertrend daily-log JSON (shape produced by buildertrend-scraper)
// and upserts each record into daily_logs by (job_key, log_id). Unknown / null
// log_id rows are still inserted but won't dedupe — caller should make sure
// the upstream scraper stamps logId.
//
// Returns: { inserted: int, updated: int, skipped: int, byJob: {...} }

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type BTRecord = {
  logId?: string;
  date?: string;
  crews_clean?: string[];
  crews?: string;
  absent_crews?: string[];
  parent_group_activities?: string[];
  daily_workforce?: number | string | null;
  weatherHigh?: number | string | null;
  weatherLow?: number | string | null;
  activity?: string;
  notes_full?: string;
  notes?: string;
  enriched_at?: string;
};

type Body = {
  source?: string;
  payload?: { byJob?: Record<string, BTRecord[]> };
};

const CREW_LABELS_TO_STRIP = new Set([
  "on Site",
  "Daily Workforce",
  "Absent Crew(s)",
  "NONE",
  "Parent Group Activity",
  "Inspections?",
  "Deliveries?",
  "Read more",
]);

function parseCrews(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(";")
    .map((s) => s.trim())
    .filter((s) => s && !CREW_LABELS_TO_STRIP.has(s));
}

function pickCrews(rec: BTRecord): string[] {
  if (Array.isArray(rec.crews_clean) && rec.crews_clean.length > 0) {
    return rec.crews_clean.map((s) => (s ?? "").trim()).filter(Boolean);
  }
  return parseCrews(rec.crews);
}

function parseLogDate(raw: string | undefined): string | null {
  if (!raw) return null;
  const cleaned = raw.trim();
  // Try a few common BT formats; fall back to Date constructor.
  const patterns: RegExp[] = [
    /^[A-Za-z]{3},\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})$/, // "Wed, Apr 15, 2026"
    /^[A-Za-z]{3},\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$/, // "Mon, 14 Jan 2026"
    /^([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})$/, // "Apr 15, 2026"
  ];
  for (const re of patterns) {
    if (re.test(cleaned)) {
      const d = new Date(cleaned.replace(/^[A-Za-z]{3},\s+/, ""));
      if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
    }
  }
  const d = new Date(cleaned);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  return null;
}

function safeInt(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return isNaN(n) ? null : Math.round(n);
}

export async function POST(req: NextRequest) {
  const supabase = supabaseServer();

  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  const byJob = body.payload?.byJob;
  if (!byJob || typeof byJob !== "object") {
    return NextResponse.json(
      { error: "Body must include payload.byJob object" },
      { status: 400 }
    );
  }

  const source = body.source ?? "bt_scraper";
  const perJob: Record<string, { total: number; inserted: number; skipped: number }> = {};
  let totalInserted = 0;
  let totalSkipped = 0;

  for (const [jobKey, records] of Object.entries(byJob)) {
    if (!Array.isArray(records)) continue;
    perJob[jobKey] = { total: records.length, inserted: 0, skipped: 0 };

    // Build batch rows
    const rows = records
      .map((r) => {
        const log_date = parseLogDate(r.date);
        const log_id = (r.logId ?? "").trim() || null;
        return {
          job_key: jobKey,
          log_id,
          log_date,
          crews_present: pickCrews(r),
          absent_crews: Array.isArray(r.absent_crews)
            ? r.absent_crews.map((s) => (s ?? "").trim()).filter(Boolean)
            : [],
          parent_group_activities: Array.isArray(r.parent_group_activities)
            ? r.parent_group_activities.map((s) => (s ?? "").trim()).filter(Boolean)
            : [],
          daily_workforce: safeInt(r.daily_workforce),
          weather_high: safeInt(r.weatherHigh),
          weather_low: safeInt(r.weatherLow),
          activity: r.activity ?? null,
          notes: r.notes_full || r.notes || null,
          enriched_at: r.enriched_at ?? null,
          source,
        };
      })
      .filter((row) => row.log_id != null); // rows without a logId can't be deduped, skip

    perJob[jobKey].skipped = records.length - rows.length;
    totalSkipped += perJob[jobKey].skipped;

    if (rows.length === 0) continue;

    const { error, count } = await supabase
      .from("daily_logs")
      .upsert(rows, { onConflict: "job_key,log_id", count: "exact" });

    if (error) {
      return NextResponse.json(
        {
          error: `Upsert failed for ${jobKey}: ${error.message}`,
          per_job: perJob,
        },
        { status: 500 }
      );
    }
    perJob[jobKey].inserted = count ?? rows.length;
    totalInserted += count ?? rows.length;
  }

  revalidatePath("/subs");
  revalidatePath("/sub/[id]", "page");

  return NextResponse.json({
    ok: true,
    inserted: totalInserted,
    skipped: totalSkipped,
    per_job: perJob,
  });
}
