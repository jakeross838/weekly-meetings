// POST /api/todos/[id]/edit  (v1 todos table)
// Body: { title?, due_date?, category?, sub_id?, priority? }
//
// Id-in-URL twin of /api/edit-todo, so the reusable <EditableText> component
// (which POSTs only { [field]: value }) can drive inline todo edits the same way
// it drives items / subs / POs. For title changes the new value is stored in
// `edited_title` (+ `edited_at`) so the original LLM-extracted title stays
// auditable in `title` — identical semantics to /api/edit-todo.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { scrubRelativeDates } from "@/lib/scrub-relative-dates";
import { businessToday } from "@/lib/today";

export const dynamic = "force-dynamic";

const ALLOWED_DIRECT = new Set(["due_date", "category", "sub_id", "priority"]);

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const id = (params.id ?? "").trim();
  if (!id) {
    return NextResponse.json({ error: "missing id" }, { status: 400 });
  }

  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const update: Record<string, unknown> = {};

  if (typeof body.title === "string" && body.title.trim().length > 0) {
    // A hand-edit happens "now", so resolve relative phrases against today.
    update.edited_title = scrubRelativeDates(body.title.trim(), businessToday());
    update.edited_at = new Date().toISOString();
  }

  for (const [k, v] of Object.entries(body)) {
    if (ALLOWED_DIRECT.has(k) && v !== undefined) {
      update[k] = v === "" ? null : v;
    }
  }

  if (Object.keys(update).length === 0) {
    return NextResponse.json(
      { error: "no editable fields in body" },
      { status: 400 }
    );
  }

  const supabase = supabaseServer();

  const prior = await supabase
    .from("todos")
    .select("job, sub_id")
    .eq("id", id)
    .maybeSingle();
  if (!prior.data) {
    return NextResponse.json({ error: "todo not found" }, { status: 404 });
  }

  const { data, error } = await supabase
    .from("todos")
    .update(update)
    .eq("id", id)
    .select()
    .maybeSingle();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // Invalidate every surface that aggregates from todos.
  revalidatePath("/");
  revalidatePath("/subs");
  revalidatePath("/meeting");
  revalidatePath(`/sub/${prior.data.sub_id ?? ""}`);
  if (typeof body.sub_id === "string" && body.sub_id !== prior.data.sub_id) {
    revalidatePath(`/sub/${body.sub_id}`);
  }

  return NextResponse.json({ ok: true, todo: data });
}
