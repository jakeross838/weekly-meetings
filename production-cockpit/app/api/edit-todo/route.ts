// POST /api/edit-todo  (v1 todos table)
// Body: { id, title?, due_date?, category?, sub_id?, priority? }
//
// Mutates the v1 todo. For title changes, stores the new value in
// `edited_title` and stamps `edited_at` so the original LLM-extracted
// title stays auditable in `title`.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { getActor } from "@/lib/actor";

export const dynamic = "force-dynamic";

const ALLOWED_DIRECT = new Set([
  "due_date",
  "category",
  "sub_id",
  "priority",
]);

export async function POST(req: NextRequest) {
  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const id = typeof body.id === "string" ? body.id.trim() : "";
  if (!id) {
    return NextResponse.json({ error: "missing id" }, { status: 400 });
  }

  const update: Record<string, unknown> = {};

  if (typeof body.title === "string" && body.title.trim().length > 0) {
    update.edited_title = body.title.trim();
    update.edited_at = new Date().toISOString();
  }

  for (const [k, v] of Object.entries(body)) {
    if (ALLOWED_DIRECT.has(k) && v !== undefined) {
      // Coerce empty string for nullable fields → null
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
  const actor = getActor(req);
  void actor; // logged once auth ships

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
  revalidatePath(`/sub/${prior.data.sub_id ?? ""}`);
  // /v2/job lookups need the slug, not the display name in todos.job — best
  // effort: revalidate every job by tag would be ideal, but for now the user
  // can re-tap to refresh if needed.
  if (typeof body.sub_id === "string" && body.sub_id !== prior.data.sub_id) {
    revalidatePath(`/sub/${body.sub_id}`);
  }

  return NextResponse.json({ ok: true, todo: data });
}
