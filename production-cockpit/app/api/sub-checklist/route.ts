// POST /api/sub-checklist
// Body: { sub_id, action: "add" | "remove" | "toggle" | "edit",
//         item_id?, lens?, item_text?, is_done? }
//
// One endpoint for all checklist mutations to keep client-side wiring small.
// Each mutation revalidates /sub/[id] so the server-rendered counts refresh.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type Body = {
  sub_id?: string;
  action?: "add" | "remove" | "toggle" | "edit";
  item_id?: string;
  lens?: "SAFETY" | "SCHEDULE";
  item_text?: string;
  is_done?: boolean;
  notes?: string | null;
  done_by?: string | null;
};

export async function POST(req: NextRequest) {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON" },
      { status: 400 }
    );
  }
  const subId = body.sub_id?.trim();
  const action = body.action;
  if (!subId || !action) {
    return NextResponse.json(
      { ok: false, error: "sub_id and action required" },
      { status: 400 }
    );
  }

  const supabase = supabaseServer();

  switch (action) {
    case "add": {
      const lens = body.lens;
      const text = body.item_text?.trim();
      if (!lens || (lens !== "SAFETY" && lens !== "SCHEDULE")) {
        return NextResponse.json(
          { ok: false, error: "lens must be SAFETY or SCHEDULE" },
          { status: 400 }
        );
      }
      if (!text) {
        return NextResponse.json(
          { ok: false, error: "item_text required" },
          { status: 400 }
        );
      }
      // Next position = max(existing) + 1, scoped per lens
      const { data: maxRow } = await supabase
        .from("sub_checklist_items")
        .select("position")
        .eq("sub_id", subId)
        .eq("lens", lens)
        .order("position", { ascending: false })
        .limit(1)
        .maybeSingle();
      const nextPosition = ((maxRow?.position ?? -1) as number) + 1;
      const { error } = await supabase.from("sub_checklist_items").insert({
        sub_id: subId,
        lens,
        item_text: text,
        position: nextPosition,
      });
      if (error) {
        return NextResponse.json(
          { ok: false, error: error.message },
          { status: 500 }
        );
      }
      break;
    }
    case "remove": {
      if (!body.item_id) {
        return NextResponse.json(
          { ok: false, error: "item_id required" },
          { status: 400 }
        );
      }
      const { error } = await supabase
        .from("sub_checklist_items")
        .delete()
        .eq("id", body.item_id)
        .eq("sub_id", subId);
      if (error) {
        return NextResponse.json(
          { ok: false, error: error.message },
          { status: 500 }
        );
      }
      break;
    }
    case "toggle": {
      if (!body.item_id || typeof body.is_done !== "boolean") {
        return NextResponse.json(
          { ok: false, error: "item_id and is_done required" },
          { status: 400 }
        );
      }
      const patch = body.is_done
        ? {
            is_done: true,
            done_at: new Date().toISOString(),
            done_by: body.done_by ?? null,
            updated_at: new Date().toISOString(),
          }
        : {
            is_done: false,
            done_at: null,
            done_by: null,
            updated_at: new Date().toISOString(),
          };
      const { error } = await supabase
        .from("sub_checklist_items")
        .update(patch)
        .eq("id", body.item_id)
        .eq("sub_id", subId);
      if (error) {
        return NextResponse.json(
          { ok: false, error: error.message },
          { status: 500 }
        );
      }
      break;
    }
    case "edit": {
      if (!body.item_id) {
        return NextResponse.json(
          { ok: false, error: "item_id required" },
          { status: 400 }
        );
      }
      const text = body.item_text?.trim();
      if (!text) {
        return NextResponse.json(
          { ok: false, error: "item_text required" },
          { status: 400 }
        );
      }
      const { error } = await supabase
        .from("sub_checklist_items")
        .update({ item_text: text, updated_at: new Date().toISOString() })
        .eq("id", body.item_id)
        .eq("sub_id", subId);
      if (error) {
        return NextResponse.json(
          { ok: false, error: error.message },
          { status: 500 }
        );
      }
      break;
    }
    default:
      return NextResponse.json(
        { ok: false, error: `Unknown action: ${action}` },
        { status: 400 }
      );
  }

  revalidatePath(`/sub/${subId}`);
  return NextResponse.json({ ok: true });
}
