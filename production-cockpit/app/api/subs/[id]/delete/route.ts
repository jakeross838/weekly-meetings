// POST /api/subs/[id]/delete
// Soft-delete (hidden=true). Guard: if the sub still has open to-dos assigned,
// returns 409 { requiresForce: true, openTodos } so the UI can warn; a second
// call with { force: true } proceeds (human decides — manual wins). The
// daily-logs scraper's ensureSubsForCrews is insert-only with ignoreDuplicates,
// so a re-scrape never un-hides it. The /subs list and sub pickers filter
// hidden=false.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { OPEN_STATUSES, Status } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const supabase = supabaseServer();

  let force = false;
  try {
    const body = (await req.json()) as { force?: boolean };
    force = body?.force === true;
  } catch {
    // empty/invalid body → treat as a non-forced delete
  }

  if (!force) {
    const { count } = await supabase
      .from("todos")
      .select("id", { count: "exact", head: true })
      .eq("sub_id", params.id)
      .in("status", OPEN_STATUSES as Status[]);
    const openTodos = count ?? 0;
    if (openTodos > 0) {
      return NextResponse.json(
        {
          error: `${openTodos} open to-do${openTodos === 1 ? "" : "s"} still assigned — delete anyway?`,
          openTodos,
          requiresForce: true,
        },
        { status: 409 }
      );
    }
  }

  const { error } = await supabase
    .from("subs")
    .update({ hidden: true, hidden_at: new Date().toISOString() })
    .eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  revalidatePath("/subs");
  revalidatePath("/sub/[id]", "page");
  revalidatePath("/meeting");
  return NextResponse.json({ ok: true });
}
