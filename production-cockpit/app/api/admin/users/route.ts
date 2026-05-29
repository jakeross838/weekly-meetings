// Admin-only CRUD for the user-overlay store.
// - GET    list all users (admin panel UI). Passwords redacted.
// - PATCH  edit one of { allowedJobs, password, role, disabled } for a user.
//         For seed users that have no overlay row yet, an overlay row is
//         seeded first so the edit can persist.
// - POST   create a brand-new PM user. Also upserts a `pms` row so the new
//         PM shows up in the /admin/jobs dropdown.
// - DELETE remove an OVERLAY row (only). Seed users (jake/bob/nelson/lee/
//         martin) cannot be hard-deleted — use PATCH { disabled: true }
//         to revoke them.

import { NextRequest, NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";
import {
  upsertUserAccess,
  createUser,
  deleteUser,
  getAllUsersIncludingDisabled,
  setUserPassword,
  setUserDisabled,
  setUserRole,
} from "@/lib/user-store";
import { revalidatePath } from "next/cache";

function bustUserCaches() {
  revalidatePath("/admin/users");
  revalidatePath("/admin");
  revalidatePath("/");
  revalidatePath("/meeting");
  revalidatePath("/admin/jobs");
}

export const dynamic = "force-dynamic";

async function adminGuard() {
  const u = await currentUser();
  if (!isAdmin(u)) {
    return NextResponse.json({ ok: false, error: "Admin only" }, { status: 403 });
  }
  return null;
}

// Redact `password` from every response so admin GET never echoes plaintext
// passwords back to the browser (or chat / network logs).
function redactUser<T extends { password?: string }>(u: T): Omit<T, "password"> {
  const rest = { ...u } as { password?: string };
  delete rest.password;
  return rest as Omit<T, "password">;
}

export async function GET() {
  const block = await adminGuard();
  if (block) return block;
  const all = await getAllUsersIncludingDisabled();
  return NextResponse.json({
    ok: true,
    users: all.map((u) => redactUser(u)),
  });
}

export async function PATCH(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  let body: {
    email?: string;
    allowedJobs?: string[];
    password?: string;
    role?: "admin" | "pm";
    disabled?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim() ?? "";
  if (!email) {
    return NextResponse.json({ ok: false, error: "email required" }, { status: 400 });
  }

  const me = await currentUser();
  const isSelf = me?.email?.toLowerCase() === email.toLowerCase();

  try {
    if (Array.isArray(body.allowedJobs)) {
      await upsertUserAccess(
        email,
        body.allowedJobs.filter((s): s is string => typeof s === "string")
      );
    }
    if (typeof body.password === "string" && body.password.length > 0) {
      await setUserPassword(email, body.password);
    }
    if (typeof body.role === "string") {
      // Don't let the only admin demote themselves — they'd lock themselves
      // out of this very panel.
      if (isSelf && body.role !== "admin") {
        return NextResponse.json(
          { ok: false, error: "You can't change your own role" },
          { status: 400 }
        );
      }
      await setUserRole(email, body.role);
    }
    if (typeof body.disabled === "boolean") {
      if (isSelf && body.disabled === true) {
        return NextResponse.json(
          { ok: false, error: "You can't disable your own account" },
          { status: 400 }
        );
      }
      await setUserDisabled(email, body.disabled);
    }

    bustUserCaches();
    // Don't return the password back — even though we just set it, the
    // browser already has the value the user typed.
    const all = await getAllUsersIncludingDisabled();
    const user = all.find((u) => u.email.toLowerCase() === email.toLowerCase());
    return NextResponse.json({ ok: true, user: user ? redactUser(user) : null });
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
    password?: string;
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
      password: body.password,
    });
    bustUserCaches();
    return NextResponse.json({ ok: true, user: redactUser(user) });
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
  const me = await currentUser();
  if (me?.email?.toLowerCase() === email.toLowerCase()) {
    return NextResponse.json(
      { ok: false, error: "You can't delete your own account" },
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
