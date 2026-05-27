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
  // F3 — optional shapes the scraper may emit for per-crew headcount. We
  // accept whichever lands first; missing or malformed = empty object.
  crew_counts?: Record<string, number | string | null>;
  crews_with_count?: Array<{ name?: string; count?: number | string | null }>;
  // F6 — optional inspections shapes. Either a JSON array of objects or a
  // free-text string captured directly from BT's "Inspections?" field.
  inspections?:
    | string
    | Array<{
        type?: string;
        inspector?: string;
        result?: string;
        date?: string;
        notes?: string;
      }>;
  inspections_text?: string;
  // F8 — photos as a URL list from the scraper. URLs may be presigned or
  // BT-internal; the vision route handles fetching.
  photo_urls?: string[];
  photos?: Array<{ url?: string } | string>;
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
    return rec.crews_clean
      .map((s) => (s ?? "").trim())
      .filter((s) => s && !CREW_LABELS_TO_STRIP.has(s));
  }
  return parseCrews(rec.crews);
}

// F3 — derive a {sub_name: int} map from whichever shape the scraper sent.
// Order of preference:
//   1) explicit `crew_counts` map
//   2) `crews_with_count` array of {name, count}
//   3) regex sniff on `crews` for "Name (4)" patterns
// Returns {} when nothing parses — never throws.
function parseCrewCounts(rec: BTRecord): Record<string, number> {
  const out: Record<string, number> = {};
  const add = (rawName: unknown, rawCount: unknown) => {
    const name =
      typeof rawName === "string" ? rawName.trim() : String(rawName ?? "").trim();
    if (!name || CREW_LABELS_TO_STRIP.has(name)) return;
    const n =
      typeof rawCount === "number"
        ? rawCount
        : rawCount == null || rawCount === ""
          ? NaN
          : Number(rawCount);
    if (!isFinite(n) || n <= 0) return;
    out[name] = Math.round(n);
  };
  if (rec.crew_counts && typeof rec.crew_counts === "object") {
    for (const [name, count] of Object.entries(rec.crew_counts)) {
      add(name, count);
    }
    if (Object.keys(out).length > 0) return out;
  }
  if (Array.isArray(rec.crews_with_count)) {
    for (const row of rec.crews_with_count) {
      add(row?.name, row?.count);
    }
    if (Object.keys(out).length > 0) return out;
  }
  if (typeof rec.crews === "string" && rec.crews.length > 0) {
    // "Drywall Co (4); Watts Stucco (3)" → {Drywall Co: 4, Watts Stucco: 3}
    const parts = rec.crews.split(";");
    for (const part of parts) {
      const m = part.trim().match(/^(.+?)\s*\((\d+)\)\s*$/);
      if (m) add(m[1], m[2]);
    }
  }
  return out;
}

// F6 — normalize the inspections field to a jsonb-friendly array shape.
// Accepts string, object array, or missing.
function parseInspections(rec: BTRecord): unknown[] {
  if (Array.isArray(rec.inspections)) {
    return rec.inspections.filter(Boolean);
  }
  const text =
    (typeof rec.inspections === "string" ? rec.inspections : null) ??
    rec.inspections_text ??
    null;
  if (text && text.trim() && text.trim().toUpperCase() !== "NONE") {
    return [{ raw: text.trim() }];
  }
  return [];
}

// F8 — normalize photos to a string-URL array regardless of input shape.
function parsePhotoUrls(rec: BTRecord): string[] {
  if (Array.isArray(rec.photo_urls)) {
    return rec.photo_urls.filter(
      (u): u is string => typeof u === "string" && u.length > 0
    );
  }
  if (Array.isArray(rec.photos)) {
    return rec.photos
      .map((p) =>
        typeof p === "string" ? p : typeof p?.url === "string" ? p.url : null
      )
      .filter((u): u is string => !!u && u.length > 0);
  }
  return [];
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

function slugifySub(name: string): string {
  const s = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return s || "sub";
}

// Auto-create a sub profile for any crew BT logged that we don't already have,
// so its trade performance has somewhere to show. Rules honored:
//  - crew names are BT ground-truth (a human picked them in BT), not AI guesses
//  - existing/human-curated subs are NEVER modified (match by name + aliases,
//    insert-only, ignoreDuplicates), so manual data always wins
//  - new rows are marked source='auto' (mirrors sub_specialties.source) so the
//    auto vs. human distinction stays visible
async function ensureSubsForCrews(
  supabase: ReturnType<typeof supabaseServer>,
  crewNames: Set<string>
): Promise<number> {
  if (crewNames.size === 0) return 0;
  const { data: existing, error } = await supabase
    .from("subs")
    .select("id, name, aliases");
  if (error) return 0; // never block the daily-log upload on a subs hiccup
  const known = new Set<string>();
  const ids = new Set<string>();
  for (const s of (existing ?? []) as {
    id: string;
    name: string;
    aliases: string[] | null;
  }[]) {
    ids.add(s.id);
    known.add(s.name.trim().toLowerCase());
    for (const a of s.aliases ?? []) known.add(String(a).trim().toLowerCase());
  }
  const toCreate: {
    id: string;
    name: string;
    source: string;
    flagged_for_pm_binder: boolean;
  }[] = [];
  for (const raw of Array.from(crewNames)) {
    const name = raw.trim();
    const lc = name.toLowerCase();
    if (!lc || CREW_LABELS_TO_STRIP.has(name) || known.has(lc)) continue;
    let id = slugifySub(name);
    const base = id;
    let i = 2;
    while (ids.has(id)) id = `${base}-${i++}`;
    ids.add(id);
    known.add(lc);
    toCreate.push({ id, name, source: "auto", flagged_for_pm_binder: false });
  }
  if (toCreate.length === 0) return 0;
  const { error: insErr } = await supabase
    .from("subs")
    .upsert(toCreate, { onConflict: "id", ignoreDuplicates: true });
  return insErr ? 0 : toCreate.length;
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
  const allCrews = new Set<string>();

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
            ? r.absent_crews
                .map((s) => (s ?? "").trim())
                .filter((s) => s && !CREW_LABELS_TO_STRIP.has(s))
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
          // F3 / F6 / F8 — defensive: pass through whatever the scraper sent.
          // The DB columns default to '{}' / '[]' so omitting still works
          // pre-migration deployments; the upsert just won't see these keys
          // until the new columns exist.
          crew_counts: parseCrewCounts(r),
          inspections: parseInspections(r),
          photo_urls: parsePhotoUrls(r),
        };
      })
      .filter((row) => row.log_id != null); // rows without a logId can't be deduped, skip

    for (const row of rows) {
      for (const c of row.crews_present) allCrews.add(c);
      for (const c of row.absent_crews) allCrews.add(c);
    }

    perJob[jobKey].skipped = records.length - rows.length;
    totalSkipped += perJob[jobKey].skipped;

    if (rows.length === 0) continue;

    // Manual-wins: skip logs the user soft-deleted (hidden), and don't
    // overwrite columns they edited (manually_edited_fields). Keyed by log_id
    // within this job; a job has only a handful of logs so no chunking needed.
    const logIds = rows
      .map((r) => r.log_id)
      .filter((x): x is string => x != null);
    const dlEdited = new Map<string, string[]>();
    const dlHidden = new Set<string>();
    if (logIds.length) {
      const { data } = await supabase
        .from("daily_logs")
        .select("log_id, manually_edited_fields, hidden")
        .eq("job_key", jobKey)
        .in("log_id", logIds);
      for (const r of (data ?? []) as {
        log_id: string;
        manually_edited_fields: string[] | null;
        hidden: boolean;
      }[]) {
        if (Array.isArray(r.manually_edited_fields) && r.manually_edited_fields.length)
          dlEdited.set(r.log_id, r.manually_edited_fields);
        if (r.hidden) dlHidden.add(r.log_id);
      }
    }
    const cleanRows = rows.filter(
      (r) => r.log_id && !dlHidden.has(r.log_id) && !dlEdited.has(r.log_id)
    );
    const editedRows = rows.filter(
      (r) => r.log_id && dlEdited.has(r.log_id) && !dlHidden.has(r.log_id)
    );

    let jobInserted = 0;
    if (cleanRows.length) {
      const { error, count } = await supabase
        .from("daily_logs")
        .upsert(cleanRows, { onConflict: "job_key,log_id", count: "exact" });
      if (error) {
        return NextResponse.json(
          { error: `Upsert failed for ${jobKey}: ${error.message}`, per_job: perJob },
          { status: 500 }
        );
      }
      jobInserted += count ?? cleanRows.length;
    }
    for (const row of editedRows) {
      const r2: Record<string, unknown> = { ...row };
      for (const f of dlEdited.get(row.log_id as string) ?? []) delete r2[f];
      const { error } = await supabase
        .from("daily_logs")
        .upsert([r2], { onConflict: "job_key,log_id" });
      if (error) {
        return NextResponse.json(
          { error: `Upsert failed for ${jobKey} (edited): ${error.message}`, per_job: perJob },
          { status: 500 }
        );
      }
      jobInserted += 1;
    }
    perJob[jobKey].inserted = jobInserted;
    totalInserted += jobInserted;
  }

  // Auto-create profiles for any newly-seen crews (insert-only; never touches
  // existing/human subs). Done once per upload after all jobs are processed.
  const autoSubsCreated = await ensureSubsForCrews(supabase, allCrews);

  revalidatePath("/subs");
  revalidatePath("/sub/[id]", "page");
  revalidatePath("/");
  revalidatePath("/meeting");
  revalidatePath("/import");
  revalidatePath("/v2/job/[job_id]", "page");

  return NextResponse.json({
    ok: true,
    inserted: totalInserted,
    skipped: totalSkipped,
    auto_subs_created: autoSubsCreated,
    per_job: perJob,
  });
}
