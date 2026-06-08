// Admin-only PMs table maintenance.
//
// GET     — list PMs (id, full_name, active)
// DELETE  ?id=<pm_id> — remove a PM record. Refuses if any job still has
//                       pm_id = the target id (manual reassignment first).
//
// The `pms` table is just the catalog used by dropdowns and per-PM filter
// pills; deleting a PM here does NOT touch user accounts (those live in
// auth/user_overlay). Use /api/admin/users for that.

import { NextRequest, NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";
import { supabaseServer } from "@/lib/supabase";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

async function adminGuard() {
  const u = await currentUser();
  if (!isAdmin(u)) {
    return NextResponse.json({ ok: false, error: "Admin only" }, { status: 403 });
  }
  return null;
}

export async function GET() {
  const block = await adminGuard();
  if (block) return block;
  const sb = supabaseServer();
  const { data, error } = await sb
    .from("pms")
    .select("id, full_name, active")
    .order("full_name");
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, pms: data ?? [] });
}

export async function DELETE(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  const id = new URL(req.url).searchParams.get("id")?.trim().toLowerCase() ?? "";
  if (!id) {
    return NextResponse.json({ ok: false, error: "?id= required" }, { status: 400 });
  }
  const sb = supabaseServer();

  // Refuse if any job is still owned by this pm. Forces the operator to
  // reassign first so nobody silently loses access to their work.
  const { data: ownedJobs } = await sb
    .from("jobs")
    .select("id")
    .eq("pm_id", id);
  if (ownedJobs && ownedJobs.length > 0) {
    return NextResponse.json(
      {
        ok: false,
        error: `PM "${id}" still owns ${ownedJobs.length} job(s): ${ownedJobs
          .map((j) => j.id)
          .join(", ")}. Reassign first, then retry.`,
      },
      { status: 409 },
    );
  }

  // The job_pm_assignments table holds an FK to pms(id), so closing rows
  // (setting ended_at) doesn't release the constraint — we have to actually
  // delete them. Any historical attribution is lost; the jobs themselves
  // keep their pm_id reassignment (set before this route is hit).
  await sb.from("job_pm_assignments").delete().eq("pm_id", id);

  // Null out the FK on every dependent table so the PM record can actually
  // be removed. The rows still belong to their job — they just stop being
  // attributed to the departed PM. Best-effort: a missing table just falls
  // through to the .from() error which we ignore.
  for (const table of ["todos", "meetings", "items"]) {
    try {
      await sb.from(table).update({ pm_id: null }).eq("pm_id", id);
    } catch {
      // ignore — table may not exist or may not have pm_id column
    }
  }

  const { error } = await sb.from("pms").delete().eq("id", id);
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }

  revalidatePath("/");
  revalidatePath("/admin");
  revalidatePath("/admin/users");
  revalidatePath("/admin/jobs");
  return NextResponse.json({ ok: true });
}
