// POST /api/subs/[id]/edit
// Body: any of { name, trade, notes, flagged_for_pm_binder, flag_note, aliases }.
// Subs are insert-only from the scraper (never overwritten), so no
// manually_edited_fields needed. aliases accepts an array or comma string.
// flag_note replaced the auto-derived flag_reasons array — a single human
// sentence the PM types when flagging a sub.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

const ALLOWED = new Set([
  "name",
  "trade",
  "notes",
  "flagged_for_pm_binder",
  "flag_note",
  "aliases",
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
  for (const [k, v] of Object.entries(body)) {
    if (!ALLOWED.has(k) || v === undefined) continue;
    if (k === "aliases") {
      update.aliases = Array.isArray(v)
        ? v
        : typeof v === "string"
          ? v.split(",").map((s) => s.trim()).filter(Boolean)
          : [];
    } else if (k === "flagged_for_pm_binder") {
      update.flagged_for_pm_binder = !!v;
    } else {
      update[k] = v === "" ? null : v;
    }
  }
  if (Object.keys(update).length === 0) {
    return NextResponse.json({ error: "no allowed fields in body" }, { status: 400 });
  }
  update.updated_at = new Date().toISOString();

  const { data, error } = await supabase
    .from("subs")
    .update(update)
    .eq("id", params.id)
    .select()
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  revalidatePath("/subs");
  revalidatePath("/sub/[id]", "page");
  revalidatePath("/meeting");
  return NextResponse.json({ ok: true, sub: data });
}
