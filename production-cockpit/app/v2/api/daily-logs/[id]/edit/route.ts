// POST /v2/api/daily-logs/[id]/edit
// Body: any of { notes, activity, daily_workforce, weather_high, weather_low,
//   crews_present, absent_crews, parent_group_activities }.
// Appends edited fields to manually_edited_fields so the next scrape's upload
// skips them (manual wins).

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

const ALLOWED = new Set([
  "notes", "activity", "daily_workforce", "weather_high", "weather_low",
  "crews_present", "absent_crews", "parent_group_activities",
]);

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const supabase = supabaseServer();
  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const update: Record<string, unknown> = {};
  const edited: string[] = [];
  for (const [k, v] of Object.entries(body)) {
    if (ALLOWED.has(k) && v !== undefined) {
      update[k] = v === "" ? null : v;
      edited.push(k);
    }
  }
  if (edited.length === 0) {
    return NextResponse.json({ error: "no allowed fields in body" }, { status: 400 });
  }
  const { data: existing } = await supabase
    .from("daily_logs")
    .select("manually_edited_fields")
    .eq("id", params.id)
    .maybeSingle();
  if (!existing) {
    return NextResponse.json({ error: "daily log not found" }, { status: 404 });
  }
  const cur = (existing.manually_edited_fields ?? []) as string[];
  update.manually_edited_fields = Array.from(new Set([...cur, ...edited]));
  update.manually_edited_at = new Date().toISOString();

  const { data, error } = await supabase
    .from("daily_logs")
    .update(update)
    .eq("id", params.id)
    .select()
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  revalidatePath("/sub/[id]", "page");
  revalidatePath("/v2/job/[job_id]", "page");
  return NextResponse.json({ ok: true, daily_log: data });
}
