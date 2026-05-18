// POST /v2/api/items/[item_id]/complete
// Body: { completion_basis?: string }

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { getActor } from "@/lib/actor";

export const dynamic = "force-dynamic";

export async function POST(
  req: NextRequest,
  { params }: { params: { item_id: string } },
) {
  const { item_id } = params;
  const supabase = supabaseServer();
  const actor = getActor(req);

  let body: { completion_basis?: string } = {};
  try {
    body = (await req.json()) as { completion_basis?: string };
  } catch {}

  const { data: existing } = await supabase
    .from("items")
    .select("status, manually_edited_fields")
    .eq("id", item_id)
    .maybeSingle();
  if (!existing) {
    return NextResponse.json({ error: "item not found" }, { status: 404 });
  }

  const prevStatus = existing.status as string;
  const meFields: string[] = (existing.manually_edited_fields ?? []) as string[];
  if (!meFields.includes("status")) meFields.push("status");

  const { data, error } = await supabase
    .from("items")
    .update({
      status: "complete",
      completed_at: new Date().toISOString(),
      previous_status: prevStatus,
      completed_by: actor,
      completion_basis: body.completion_basis ?? "manual",
      manually_edited_at: new Date().toISOString(),
      manually_edited_fields: meFields,
      updated_at: new Date().toISOString(),
    })
    .eq("id", item_id)
    .select()
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  // Invalidate all surfaces that show item counts so the next render is fresh.
  const jobId = (data?.job_id as string | undefined) ?? undefined;
  if (jobId) revalidatePath(`/v2/job/${jobId}`);
  revalidatePath("/");
  revalidatePath("/schedule");

  return NextResponse.json({ item: data });
}
