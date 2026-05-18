// POST /api/sub-specialties
// Body:
//   { sub_id, specialty, action: "add" }                         — declare
//   { sub_id, specialty, action: "remove" }                      — drop manual decl
//   { sub_id, specialty, action: "set_duration", duration_days } — override avg duration
//                                                                  (null clears it)
//
// Manual specialties layer on top of auto-detected ones (from BT
// parent_group_activities). The duration override always wins over the
// daily-log-streak estimate when present.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { getActor } from "@/lib/actor";

export const dynamic = "force-dynamic";

type Action = "add" | "remove" | "set_duration";

interface Body {
  sub_id?: string;
  specialty?: string;
  action?: Action;
  duration_days?: number | null;
}

function explain(err: { message: string }): string {
  if (/PGRST205|does not exist/i.test(err.message)) {
    return "sub_specialties table missing — apply migration 012_create_sub_specialties_table.sql in Supabase Studio";
  }
  if (/duration_days_manual_override/i.test(err.message)) {
    return "sub_specialties.duration_days_manual_override column missing — apply the migration block (it's included in the combined SQL)";
  }
  return err.message;
}

export async function POST(req: NextRequest) {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const sub_id = (body.sub_id ?? "").trim();
  const specialty = (body.specialty ?? "").trim();
  const action = body.action;

  if (!sub_id) {
    return NextResponse.json({ error: "missing sub_id" }, { status: 400 });
  }
  if (!specialty) {
    return NextResponse.json({ error: "missing specialty" }, { status: 400 });
  }
  if (action !== "add" && action !== "remove" && action !== "set_duration") {
    return NextResponse.json(
      { error: "action must be 'add', 'remove', or 'set_duration'" },
      { status: 400 }
    );
  }

  const supabase = supabaseServer();
  const actor = getActor(req);

  if (action === "add") {
    const { error } = await supabase
      .from("sub_specialties")
      .upsert(
        { sub_id, specialty, source: "manual", created_by: actor },
        { onConflict: "sub_id,specialty" }
      );
    if (error) {
      return NextResponse.json({ error: explain(error) }, { status: 500 });
    }
  } else if (action === "remove") {
    const { error } = await supabase
      .from("sub_specialties")
      .delete()
      .eq("sub_id", sub_id)
      .eq("specialty", specialty)
      .eq("source", "manual");
    if (error) {
      return NextResponse.json({ error: explain(error) }, { status: 500 });
    }
  } else {
    // set_duration — upsert so an override can be added even for auto rows
    // (auto rows don't exist in sub_specialties; we promote them to manual
    // when the operator sets a duration on them).
    const duration =
      body.duration_days === null || body.duration_days === undefined
        ? null
        : Number(body.duration_days);
    if (duration !== null && (isNaN(duration) || duration < 0)) {
      return NextResponse.json(
        { error: "duration_days must be a non-negative number or null" },
        { status: 400 }
      );
    }
    const { error } = await supabase
      .from("sub_specialties")
      .upsert(
        {
          sub_id,
          specialty,
          source: "manual",
          created_by: actor,
          duration_days_manual_override: duration,
        },
        { onConflict: "sub_id,specialty" }
      );
    if (error) {
      return NextResponse.json({ error: explain(error) }, { status: 500 });
    }
  }

  revalidatePath(`/sub/${sub_id}`);
  return NextResponse.json({ ok: true });
}
