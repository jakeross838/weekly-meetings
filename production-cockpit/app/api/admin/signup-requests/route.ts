// Admin-only: list signup requests, approve, or reject.

import { NextRequest, NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";
import { supabaseServer } from "@/lib/supabase";
import { createUser, setUserPassword } from "@/lib/user-store";
import { sendEmail, brandWrap } from "@/lib/email";
import { revalidatePath } from "next/cache";
import crypto from "node:crypto";

export const dynamic = "force-dynamic";

async function adminGuard() {
  const u = await currentUser();
  if (!isAdmin(u)) {
    return NextResponse.json({ ok: false, error: "Admin only" }, { status: 403 });
  }
  return null;
}

function bust() {
  revalidatePath("/admin/users");
  revalidatePath("/admin");
}

export async function GET() {
  const block = await adminGuard();
  if (block) return block;
  const sb = supabaseServer();
  const { data, error } = await sb
    .from("signup_requests")
    .select("id, email, name, role_requested, message, status, created_at")
    .eq("status", "pending")
    .order("created_at", { ascending: false });
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, requests: data ?? [] });
}

// POST { id, action: 'approve' | 'reject', pmId?, password? }
export async function POST(req: NextRequest) {
  const block = await adminGuard();
  if (block) return block;
  const me = await currentUser();

  let body: {
    id?: string;
    action?: "approve" | "reject";
    pmId?: string | null;
    password?: string;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const id = body.id?.trim() ?? "";
  const action = body.action;
  if (!id || (action !== "approve" && action !== "reject")) {
    return NextResponse.json(
      { ok: false, error: "id and action (approve|reject) required" },
      { status: 400 }
    );
  }

  const sb = supabaseServer();
  const { data: row } = await sb
    .from("signup_requests")
    .select("id, email, name, status")
    .eq("id", id)
    .maybeSingle();
  if (!row || (row as { status: string }).status !== "pending") {
    return NextResponse.json(
      { ok: false, error: "request not pending" },
      { status: 400 }
    );
  }
  const r = row as { id: string; email: string; name: string };

  if (action === "reject") {
    await sb
      .from("signup_requests")
      .update({
        status: "rejected",
        reviewed_by: me?.email ?? null,
        reviewed_at: new Date().toISOString(),
      })
      .eq("id", id);
    bust();
    return NextResponse.json({ ok: true });
  }

  // Approve — create user + assign a fresh password + email it to them.
  const initialPassword =
    body.password?.trim() || crypto.randomBytes(6).toString("base64url");
  try {
    await createUser({
      email: r.email,
      name: r.name,
      pmId: body.pmId?.trim() || null,
      allowedJobs: [],
      password: initialPassword,
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 400 }
    );
  }
  // Belt-and-suspenders: explicitly set the password too (createUser also
  // accepts it but setting again is a no-op idempotent safeguard).
  await setUserPassword(r.email, initialPassword);

  const origin = req.nextUrl.origin;
  await sendEmail({
    to: r.email,
    subject: "Your Ross Built cockpit account is ready",
    html: brandWrap({
      preheader: "Your access has been approved.",
      intro: `Welcome, ${r.name.split(" ")[0]} — Jake just approved your access.`,
      body:
        `Sign in at <a href="${origin}/login" style="color:#5B8497">${origin}/login</a> with these credentials:<br/><br/>` +
        `<strong>Email:</strong> ${r.email}<br/>` +
        `<strong>Temporary password:</strong> <code style="background:#EBEEF0;padding:2px 6px;">${initialPassword}</code><br/><br/>` +
        `Once you sign in, set a new password from the user menu.`,
      cta: "Open cockpit",
      ctaUrl: `${origin}/login`,
    }),
    text: `Your Ross Built cockpit account is ready.\n\nSign in: ${origin}/login\nEmail: ${r.email}\nTemporary password: ${initialPassword}`,
  });

  await sb
    .from("signup_requests")
    .update({
      status: "approved",
      reviewed_by: me?.email ?? null,
      reviewed_at: new Date().toISOString(),
    })
    .eq("id", id);

  bust();
  return NextResponse.json({ ok: true });
}
