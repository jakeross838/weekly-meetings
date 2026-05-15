// POST /v2/api/items/[item_id]/convert-to-action
//
// Queues a proposed_changes row (change_type='update_item') flipping
// actionability='signal' -> 'actionable', optionally with proposed target/sub.
// Jake approves via /v2/review.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function POST(
  req: NextRequest,
  { params }: { params: { item_id: string } },
) {
  const { item_id } = params;
  const supabase = supabaseServer();

  let body: { proposed_target_date?: string; proposed_target_date_text?: string; proposed_sub_id?: string } = {};
  try {
    body = (await req.json()) as typeof body;
  } catch {}

  const { data: item } = await supabase
    .from("items")
    .select("*")
    .eq("id", item_id)
    .maybeSingle();
  if (!item) return NextResponse.json({ error: "item not found" }, { status: 404 });

  const field_changes: Record<string, { before: unknown; after: unknown }> = {
    actionability: { before: item.actionability, after: "actionable" },
  };
  if (body.proposed_target_date) {
    field_changes.target_date = { before: item.target_date, after: body.proposed_target_date };
  }
  if (body.proposed_target_date_text) {
    field_changes.target_date_text = { before: item.target_date_text, after: body.proposed_target_date_text };
  }
  if (body.proposed_sub_id) {
    field_changes.sub_id = { before: item.sub_id, after: body.proposed_sub_id };
  }

  // Create a manual ingestion_event to host this proposal
  const { data: ie, error: ieErr } = await supabase
    .from("ingestion_events")
    .insert({
      source_type: "manual",
      source_meeting_id: null,
      job_id: item.job_id,
      review_state: "pending",
      proposed_count: 1,
      ingested_by: "jake",
      notes: `convert-to-action for ${item.human_readable_id}`,
    })
    .select("id")
    .maybeSingle();
  if (ieErr || !ie) return NextResponse.json({ error: ieErr?.message ?? "ingestion_event insert failed" }, { status: 500 });

  const { data: pc, error: pcErr } = await supabase
    .from("proposed_changes")
    .insert({
      ingestion_event_id: ie.id,
      change_type: "update_item",
      target_item_id: item_id,
      field_changes,
      job_id: item.job_id,
      sub_id: body.proposed_sub_id ?? item.sub_id,
      confidence: "medium",
      notes: "Convert signal to actionable, queued for Jake review.",
    })
    .select("id")
    .maybeSingle();
  if (pcErr || !pc) return NextResponse.json({ error: pcErr?.message ?? "proposed_changes insert failed" }, { status: 500 });

  return NextResponse.json({ ingestion_event_id: ie.id, proposed_change_id: pc.id });
}
