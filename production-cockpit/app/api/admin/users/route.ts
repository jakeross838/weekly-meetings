// Admin-only CRUD for the user-overlay store. PATCH updates job access for
// an existing user (seed or overlay); POST creates a brand-new PM user;
// DELETE removes an overlay-only user. Seed users (jake/bob/nelson/lee/martin)
// cannot be deleted — only edited.

import { NextRequest, NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";
import { upsertUserAccess, createUser, deleteUser, getAllUsers } from "@/lib/user-store";
import { revalidatePath } from "next/cache";

function bustUserCaches() {
  revalidatePath("/admin/users");
  revalidatePath("/admin");
  revalidatePath("/");
  revalidatePath("/meeting");
}

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
  return NextResponse.json({ ok: true, users: await getAllUsers() });
}

export async function PATCH(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  let body: { email?: string; allowedJobs?: string[] };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim() ?? "";
  const allowedJobs = Array.isArray(body.allowedJobs)
    ? body.allowedJobs.filter((s): s is string => typeof s === "string")
    : null;
  if (!email || !allowedJobs) {
    return NextResponse.json(
      { ok: false, error: "email and allowedJobs[] required" },
      { status: 400 }
    );
  }
  try {
    const user = await upsertUserAccess(email, allowedJobs);
    bustUserCaches();
    return NextResponse.json({ ok: true, user });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 400 }
    );
  }
}

export async function POST(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  let body: {
    email?: string;
    name?: string;
    pmId?: string | null;
    allowedJobs?: string[];
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim() ?? "";
  const name = body.name?.trim() ?? "";
  const allowedJobs = Array.isArray(body.allowedJobs)
    ? body.allowedJobs.filter((s): s is string => typeof s === "string")
    : [];
  if (!email || !name) {
    return NextResponse.json(
      { ok: false, error: "email and name required" },
      { status: 400 }
    );
  }
  try {
    const user = await createUser({
      email,
      name,
      pmId: body.pmId ?? null,
      allowedJobs,
    });
    bustUserCaches();
    return NextResponse.json({ ok: true, user });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 400 }
    );
  }
}

export async function DELETE(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  const url = new URL(req.url);
  const email = url.searchParams.get("email")?.trim() ?? "";
  if (!email) {
    return NextResponse.json(
      { ok: false, error: "?email= required" },
      { status: 400 }
    );
  }
  try {
    await deleteUser(email);
    bustUserCaches();
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 400 }
    );
  }
}
