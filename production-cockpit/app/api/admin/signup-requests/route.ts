// Admin-only: list signup requests, approve, or reject.

import { NextRequest, NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";
import { supabaseServer } from "@/lib/supabase";
import { sendEmail, brandWrap } from "@/lib/email";
import { revalidatePath } from "next/cache";

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

  // Approve — the user already exists (they signed up themselves with
  // their own password). All we do is mark the ticket approved and email
  // them a heads-up. Actual job assignment happens via /admin/jobs.
  const origin = req.nextUrl.origin;
  await sendEmail({
    to: r.email,
    subject: "Your Ross Built cockpit access is ready",
    html: brandWrap({
      preheader: "Jake just approved your access — jobs are on the way.",
      intro: `Hey ${r.name.split(" ")[0]} — Jake just approved your access request.`,
      body:
        `You should start seeing the jobs Jake assigns to you on your home page. Refresh ` +
        `<a href="${origin}/" style="color:#5B8497">${origin}/</a> if they don't show up right away.`,
      cta: "Open cockpit",
      ctaUrl: `${origin}/`,
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
