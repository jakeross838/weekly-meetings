// Admin-only CRUD for the `jobs` table.
// POST   { id, name, address?, pm_id? }           — create
// PATCH  { id, name?, address?, pm_id? }          — update
// DELETE ?id=...                                  — delete (warns about
//   orphaned downstream rows like POs and daily logs, but proceeds; those
//   tables don't have FKs onto jobs).

import { NextRequest, NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";
import { supabaseServer } from "@/lib/supabase";
import { revalidatePath } from "next/cache";
import { syncJobPmAssignment } from "@/lib/job-assignments";

export const dynamic = "force-dynamic";

// Invalidate every route whose render reads the jobs list / per-job
// data, so admin edits show up on the next request without a hard refresh.
function bustJobCaches(jobId?: string) {
  revalidatePath("/");
  revalidatePath("/meeting");
  revalidatePath("/admin/jobs");
  revalidatePath("/admin/users");
  revalidatePath("/admin");
  revalidatePath("/subs");
  if (jobId) revalidatePath(`/v2/job/${jobId}`);
}

async function adminGuard() {
  const u = await currentUser();
  if (!isAdmin(u)) {
    return NextResponse.json({ ok: false, error: "Admin only" }, { status: 403 });
  }
  return null;
}

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/;

export async function GET() {
  const block = await adminGuard();
  if (block) return block;
  const sb = supabaseServer();
  const { data, error } = await sb
    .from("jobs")
    .select("id, name, address, pm_id, status, phase")
    .order("name");
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, jobs: data ?? [] });
}

export async function POST(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  let body: { id?: string; name?: string; address?: string; pm_id?: string | null };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const id = body.id?.trim().toLowerCase() ?? "";
  const name = body.name?.trim() ?? "";
  if (!id || !SLUG_RE.test(id)) {
    return NextResponse.json(
      { ok: false, error: "id must be a slug (lowercase letters, digits, _ or -)" },
      { status: 400 }
    );
  }
  if (!name) {
    return NextResponse.json(
      { ok: false, error: "name is required" },
      { status: 400 }
    );
  }
  const sb = supabaseServer();
  const { data, error } = await sb
    .from("jobs")
    .insert({
      id,
      name,
      address: body.address?.trim() || null,
      pm_id: body.pm_id?.trim() || null,
    })
    .select("id, name, address, pm_id")
    .maybeSingle();
  if (error) {
    return NextResponse.json(
      { ok: false, error: error.message },
      { status: 400 }
    );
  }
  // Mirror the new owner into job_pm_assignments so the legacy table doesn't
  // hide the assignment.
  await syncJobPmAssignment(id, body.pm_id?.trim() || null);
  bustJobCaches(id);
  return NextResponse.json({ ok: true, job: data });
}

export async function PATCH(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  let body: {
    id?: string;
    name?: string;
    address?: string | null;
    pm_id?: string | null;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const id = body.id?.trim().toLowerCase() ?? "";
  if (!id) {
    return NextResponse.json({ ok: false, error: "id required" }, { status: 400 });
  }
  const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
  if (body.name !== undefined) patch.name = body.name?.trim() || null;
  if (body.address !== undefined) patch.address = body.address?.trim() || null;
  if (body.pm_id !== undefined) patch.pm_id = body.pm_id?.trim() || null;
  const sb = supabaseServer();
  const { data, error } = await sb
    .from("jobs")
    .update(patch)
    .eq("id", id)
    .select("id, name, address, pm_id")
    .maybeSingle();
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
  // Only sync assignments if pm_id was in the body — a pure name/address
  // edit shouldn't churn the assignments table.
  if (body.pm_id !== undefined) {
    await syncJobPmAssignment(id, body.pm_id?.trim() || null);
  }
  bustJobCaches(id);
  return NextResponse.json({ ok: true, job: data });
}

export async function DELETE(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  const url = new URL(req.url);
  const id = url.searchParams.get("id")?.trim().toLowerCase() ?? "";
  if (!id) {
    return NextResponse.json({ ok: false, error: "?id= required" }, { status: 400 });
  }
  const sb = supabaseServer();
  const { error } = await sb.from("jobs").delete().eq("id", id);
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
  // Close any open assignments so a deleted job doesn't keep haunting a PM's
  // visible list via the legacy assignment table.
  await syncJobPmAssignment(id, null);
  bustJobCaches(id);
  return NextResponse.json({ ok: true });
}
