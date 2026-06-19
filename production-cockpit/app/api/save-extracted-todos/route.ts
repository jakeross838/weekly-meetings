import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { scrubRelativeDates } from "@/lib/scrub-relative-dates";

export const dynamic = "force-dynamic";

interface SaveItem {
  title: string;
  sub_id: string | null;
  job: string;
  priority: string;
  due_date: string | null;
  category: string;
  type: string;
  source_excerpt?: string | null;
}

interface SaveBody {
  pm_id?: string;
  meeting_date?: string;
  source_label?: string;
  items?: SaveItem[];
}

/**
 * Persist AI-extracted items as new todos in Supabase.
 * IDs follow `<JOB-PREFIX>-C<timestamp_ms_short>` so they never collide with
 * the binder-derived `<JOB-PREFIX>-<###>` IDs from process.py.
 */
export async function POST(req: NextRequest) {
  let body: SaveBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON" },
      { status: 400 }
    );
  }
  const pmId = body.pm_id?.trim();
  const meetingDate = body.meeting_date?.trim();
  const items = body.items ?? [];
  if (!pmId || !meetingDate || items.length === 0) {
    return NextResponse.json(
      { ok: false, error: "Missing pm_id, meeting_date, or items" },
      { status: 400 }
    );
  }

  const supabase = supabaseServer();

  // F2 — hard dedup: refuse to re-import a transcript whose filename already
  // produced to-dos, so a double upload can't create duplicates. The form also
  // warns before processing; this is the server-side guarantee.
  const sourceLabel = body.source_label?.trim();
  if (sourceLabel && sourceLabel !== "cockpit-import") {
    const { count } = await supabase
      .from("todos")
      .select("id", { count: "exact", head: true })
      .eq("source_transcript", sourceLabel);
    if ((count ?? 0) > 0) {
      return NextResponse.json(
        {
          ok: false,
          duplicate: true,
          error: `"${sourceLabel}" was already imported (${count} to-do${count === 1 ? "" : "s"} exist). Delete those first if you need to re-import.`,
        },
        { status: 409 }
      );
    }
  }

  // Canonicalize each item's job to a real jobs.name. The job page matches
  // todos.job to jobs.name EXACTLY, so a slightly-off name from the extractor
  // ("Kraus" → "Krauss") would silently orphan the to-do off its job page.
  // Exact (case/punctuation-insensitive) match wins; else a prefix match;
  // else keep what we were given.
  const { data: jobsData } = await supabase.from("jobs").select("name");
  const knownJobNames = ((jobsData ?? []) as { name: string }[]).map((j) => j.name);
  const nrm = (s: string) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const canonJob = (raw: string): string => {
    const r = nrm(raw);
    if (!r) return raw || "Unknown";
    const exact = knownJobNames.find((n) => nrm(n) === r);
    if (exact) return exact;
    const partial = knownJobNames.find((n) => {
      const nn = nrm(n);
      return nn.startsWith(r) || r.startsWith(nn);
    });
    return partial ?? (raw || "Unknown");
  };

  // Build rows
  const now = Date.now();
  const rows = items.map((item, i) => {
    const jobPrefix = (item.job || "JOB")
      .replace(/[^A-Za-z]/g, "")
      .slice(0, 4)
      .toUpperCase()
      .padEnd(4, "_");
    const suffix = `C${(now % 10_000_000).toString(36)}${i.toString(36)}`;
    return {
      id: `${jobPrefix}-${suffix}`,
      pm_id: pmId,
      job: canonJob(item.job),
      // Hard guarantee: no broad timeframe survives onto the active to-do
      // list. Resolve "tomorrow"/"by Friday"/etc. to an exact date (or strip
      // vague spans) against the meeting date — even if the operator hand-typed
      // it in the review screen. See lib/scrub-relative-dates.ts.
      title: scrubRelativeDates(item.title, meetingDate),
      due_date: item.due_date || null,
      priority: item.priority || "NORMAL",
      status: "NOT_STARTED",
      type: item.type || "FOLLOWUP",
      category: item.category || "ADMIN",
      created_at: `${meetingDate}T00:00:00Z`,
      sub_id: item.sub_id || null,
      source_transcript: body.source_label || "cockpit-import",
      // Keep the verbatim transcript snippet Claude grounded each item in, so
      // the to-do stays auditable back to what was actually said.
      source_excerpt: item.source_excerpt || null,
    };
  });

  try {
    const { error } = await supabase
      .from("todos")
      .upsert(rows, { onConflict: "id" });
    if (error) {
      return NextResponse.json(
        { ok: false, error: error.message },
        { status: 500 }
      );
    }
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }

  const jobNames = Array.from(new Set(rows.map((r) => r.job)));
  const subIds = Array.from(
    new Set(rows.map((r) => r.sub_id).filter(Boolean) as string[])
  );
  revalidatePath("/");
  revalidatePath("/subs");
  for (const sid of subIds) revalidatePath(`/sub/${sid}`);
  for (const jname of jobNames) {
    const slug = jname.toLowerCase().replace(/[^a-z0-9]+/g, "");
    if (slug) revalidatePath(`/v2/job/${slug}`);
  }

  return NextResponse.json({ ok: true, saved: rows.length });
}
