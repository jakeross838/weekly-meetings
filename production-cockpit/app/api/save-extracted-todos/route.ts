import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

interface SaveItem {
  title: string;
  sub_id: string | null;
  job: string;
  priority: string;
  due_date: string | null;
  category: string;
  type: string;
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
      job: item.job || "Unknown",
      title: item.title,
      due_date: item.due_date || null,
      priority: item.priority || "NORMAL",
      status: "NOT_STARTED",
      type: item.type || "FOLLOWUP",
      category: item.category || "ADMIN",
      created_at: `${meetingDate}T00:00:00Z`,
      sub_id: item.sub_id || null,
      source_transcript: body.source_label || "cockpit-import",
      source_excerpt: null,
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

  return NextResponse.json({ ok: true, saved: rows.length });
}
