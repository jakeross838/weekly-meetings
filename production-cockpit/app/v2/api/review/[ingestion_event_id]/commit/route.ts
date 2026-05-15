// POST /v2/api/review/[ingestion_event_id]/commit
//
// Body: { decisions: [{ proposed_change_id, action: 'accept'|'reject'|'edit', edited_data? }] }
//
// Applies accepted/edited proposed_changes to items / decisions / open_questions tables.
// Generates human_readable_ids on insert. Respects Decision 11 clobber prevention
// for update_item types. Updates ingestion_events review_state + counts.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type Decision = {
  proposed_change_id: string;
  action: "accept" | "reject" | "edit";
  edited_data?: Record<string, unknown>;
};

const JOB_PREFIXES: Record<string, string> = {
  drummond: "DRUM",
  molinari: "MOLI",
  biales: "BIAL",
  pou: "POU",
  dewberry: "DEWB",
  harllee: "HARL",
  krauss: "KRAU",
  ruthven: "RUTH",
  fish: "FISH",
  markgraf: "MARK",
  clark: "CLAR",
  johnson: "JOHN",
};

async function nextHumanId(
  supabase: ReturnType<typeof supabaseServer>,
  jobId: string,
  kind: "item" | "decision" | "question",
): Promise<string> {
  const prefix = JOB_PREFIXES[jobId] ?? jobId.slice(0, 4).toUpperCase();
  const like = kind === "item" ? `${prefix}-%` : kind === "decision" ? `${prefix}-D-%` : `${prefix}-Q-%`;
  const table = kind === "item" ? "items" : kind === "decision" ? "decisions" : "open_questions";
  const { data } = await supabase
    .from(table)
    .select("human_readable_id")
    .like("human_readable_id", like);
  let max = 0;
  for (const row of (data ?? []) as { human_readable_id: string }[]) {
    const m = row.human_readable_id.match(/(\d+)$/);
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  const next = max + 1;
  const padded = String(next).padStart(3, "0");
  if (kind === "item") return `${prefix}-${padded}`;
  if (kind === "decision") return `${prefix}-D-${padded}`;
  return `${prefix}-Q-${padded}`;
}

export async function POST(
  req: NextRequest,
  { params }: { params: { ingestion_event_id: string } },
) {
  const { ingestion_event_id } = params;
  const supabase = supabaseServer();

  let body: { decisions: Decision[] };
  try {
    body = (await req.json()) as { decisions: Decision[] };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (!body.decisions || !Array.isArray(body.decisions)) {
    return NextResponse.json({ error: "missing decisions array" }, { status: 400 });
  }

  // Verify the event exists
  const { data: event, error: eventErr } = await supabase
    .from("ingestion_events")
    .select("id, review_state, job_id")
    .eq("id", ingestion_event_id)
    .maybeSingle();
  if (eventErr || !event) {
    return NextResponse.json({ error: "ingestion_event not found" }, { status: 404 });
  }
  if (event.review_state === "committed") {
    return NextResponse.json({ error: "already committed" }, { status: 409 });
  }

  const changeIds = body.decisions.map((d) => d.proposed_change_id);
  const { data: changes } = await supabase
    .from("proposed_changes")
    .select("*")
    .in("id", changeIds);
  const changesById = new Map<string, Record<string, unknown>>(
    (changes ?? []).map((c) => [c.id as string, c as Record<string, unknown>]),
  );

  let acceptedCount = 0;
  let rejectedCount = 0;
  let editedCount = 0;
  const results: Record<string, unknown>[] = [];

  for (const d of body.decisions) {
    const change = changesById.get(d.proposed_change_id);
    if (!change) {
      results.push({ proposed_change_id: d.proposed_change_id, error: "not found" });
      continue;
    }
    if (d.action === "reject") {
      await supabase
        .from("proposed_changes")
        .update({ review_state: "rejected", reviewed_at: new Date().toISOString() })
        .eq("id", change.id as string);
      rejectedCount++;
      results.push({ proposed_change_id: d.proposed_change_id, applied: "rejected" });
      continue;
    }

    // Accept or edit-then-accept
    const isEdit = d.action === "edit" && d.edited_data != null;
    const ct = change.change_type as string;
    let resultingItemId: string | null = null;
    let resultingDecisionId: string | null = null;
    let resultingQuestionId: string | null = null;

    try {
      if (ct === "add_item" || ct === "add_signal") {
        const base = (change.proposed_item_data ?? {}) as Record<string, unknown>;
        const merged = isEdit ? { ...base, ...(d.edited_data as Record<string, unknown>) } : base;
        const jobId = (merged.job_id ?? change.job_id) as string;
        const hid = await nextHumanId(supabase, jobId, "item");
        const insertRow = {
          human_readable_id: hid,
          job_id: jobId,
          pm_id: merged.pm_id ?? null,
          type: merged.type,
          title: merged.title,
          detail: merged.detail ?? null,
          sub_id: merged.sub_id ?? null,
          owner: merged.owner ?? null,
          target_date: merged.target_date ?? null,
          target_date_text: merged.target_date_text ?? null,
          status: merged.status ?? "open",
          priority: merged.priority ?? "normal",
          confidence: merged.confidence ?? "medium",
          source_meeting_id: merged.source_meeting_id ?? null,
          pay_app_line_item_id: merged.pay_app_line_item_id ?? null,
          carryover_count: 0,
          actionability: merged.actionability ?? "actionable",
          audit_state: "clean",
        };
        const { data: ins, error: insErr } = await supabase
          .from("items")
          .insert(insertRow)
          .select("id")
          .maybeSingle();
        if (insErr || !ins) throw new Error(insErr?.message ?? "items insert failed");
        resultingItemId = ins.id as string;
      } else if (ct === "update_item") {
        // Apply field_changes diff to existing item, with Decision 11 clobber protection
        const targetId = change.target_item_id as string | null;
        if (!targetId) throw new Error("update_item missing target_item_id");
        const { data: existing } = await supabase
          .from("items")
          .select("*")
          .eq("id", targetId)
          .maybeSingle();
        if (!existing) throw new Error(`target item ${targetId} not found`);
        const fc = (change.field_changes ?? {}) as Record<string, { before: unknown; after: unknown }>;
        const editedFc = isEdit && d.edited_data ? (d.edited_data as Record<string, { before: unknown; after: unknown }>) : fc;
        const update: Record<string, unknown> = { updated_at: new Date().toISOString() };
        const manuallyEditedFields: string[] = (existing.manually_edited_fields ?? []) as string[];
        const manuallyEditedAt = existing.manually_edited_at as string | null;
        for (const [field, pair] of Object.entries(editedFc)) {
          // Skip fields the human has manually edited (clobber protection)
          if (manuallyEditedAt && manuallyEditedFields.includes(field)) continue;
          update[field] = pair.after;
        }
        // Always preserve manual completion
        if (existing.status === "complete" && existing.completed_at) {
          update.status = "complete";
          update.completed_at = existing.completed_at;
          if (existing.completion_basis) update.completion_basis = existing.completion_basis;
        }
        update.carryover_count = (Number(existing.carryover_count) || 0) + 1;
        await supabase.from("items").update(update).eq("id", targetId);
        resultingItemId = targetId;
      } else if (ct === "add_decision") {
        const base = (change.proposed_decision_data ?? {}) as Record<string, unknown>;
        const merged = isEdit ? { ...base, ...(d.edited_data as Record<string, unknown>) } : base;
        const jobId = (merged.job_id ?? change.job_id) as string;
        const hid = await nextHumanId(supabase, jobId, "decision");
        const { data: ins, error: insErr } = await supabase
          .from("decisions")
          .insert({
            human_readable_id: hid,
            job_id: jobId,
            source_meeting_id: merged.source_meeting_id,
            description: merged.description,
            decided_by: merged.decided_by ?? null,
            decision_date: merged.decision_date ?? null,
            source_claim_id: merged.source_claim_id ?? null,
          })
          .select("id")
          .maybeSingle();
        if (insErr || !ins) throw new Error(insErr?.message ?? "decisions insert failed");
        resultingDecisionId = ins.id as string;
      } else if (ct === "add_open_question") {
        const base = (change.proposed_question_data ?? {}) as Record<string, unknown>;
        const merged = isEdit ? { ...base, ...(d.edited_data as Record<string, unknown>) } : base;
        const jobId = (merged.job_id ?? change.job_id) as string;
        const hid = await nextHumanId(supabase, jobId, "question");
        const { data: ins, error: insErr } = await supabase
          .from("open_questions")
          .insert({
            human_readable_id: hid,
            job_id: jobId,
            source_meeting_id: merged.source_meeting_id,
            question: merged.question,
            asked_by: merged.asked_by ?? null,
            source_claim_id: merged.source_claim_id ?? null,
          })
          .select("id")
          .maybeSingle();
        if (insErr || !ins) throw new Error(insErr?.message ?? "open_questions insert failed");
        resultingQuestionId = ins.id as string;
      } else {
        // resolve_item, merge_items, add_sub_event — not implemented in v1
        throw new Error(`change_type ${ct} not yet implemented`);
      }

      // If this was an edit, log a correction
      if (isEdit && d.edited_data) {
        await supabase.from("corrections").insert({
          item_id: resultingItemId,
          field_changed: "bulk_edit",
          before_value: JSON.stringify({
            proposed: change.proposed_item_data ?? change.field_changes ?? change.proposed_decision_data ?? change.proposed_question_data,
          }),
          after_value: JSON.stringify({ edited: d.edited_data }),
          correction_reason: "human edited before accept",
          corrected_by: "jake",
          context: {
            ingestion_event_id,
            proposed_change_id: change.id,
            change_type: ct,
          },
        });
      }

      await supabase
        .from("proposed_changes")
        .update({
          review_state: isEdit ? "edited_and_accepted" : "accepted",
          reviewed_at: new Date().toISOString(),
          resulting_item_id: resultingItemId,
          resulting_decision_id: resultingDecisionId,
          resulting_question_id: resultingQuestionId,
        })
        .eq("id", change.id as string);
      if (isEdit) editedCount++;
      else acceptedCount++;
      results.push({
        proposed_change_id: d.proposed_change_id,
        applied: isEdit ? "edited_and_accepted" : "accepted",
        resulting_item_id: resultingItemId,
        resulting_decision_id: resultingDecisionId,
        resulting_question_id: resultingQuestionId,
      });
    } catch (e) {
      results.push({ proposed_change_id: d.proposed_change_id, error: String(e) });
    }
  }

  // Roll the event state
  let finalState: "committed" | "partial" | "rejected" = "committed";
  if (acceptedCount === 0 && editedCount === 0 && rejectedCount > 0) finalState = "rejected";
  else if (rejectedCount > 0) finalState = "partial";
  await supabase
    .from("ingestion_events")
    .update({
      review_state: finalState,
      reviewed_at: new Date().toISOString(),
      reviewed_by: "jake",
      accepted_count: acceptedCount,
      rejected_count: rejectedCount,
      edited_count: editedCount,
    })
    .eq("id", ingestion_event_id);

  return NextResponse.json({
    ingestion_event_id,
    final_state: finalState,
    accepted: acceptedCount,
    rejected: rejectedCount,
    edited: editedCount,
    results,
  });
}
