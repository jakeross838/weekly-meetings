// POST /api/auth/request-access
// Logged-in user opens a ticket to admin asking for job access. Inserts a
// `signup_requests` row (status=pending) and emails Jake. The /admin/users
// "Pending access requests" card already renders these.

import { NextRequest, NextResponse } from "next/server";
import { currentUser } from "@/lib/auth";
import { supabaseServer } from "@/lib/supabase";
import { sendEmail, brandWrap } from "@/lib/email";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

const ADMIN_NOTIFY_EMAIL = "jakeross838@gmail.com";

export async function POST(req: NextRequest) {
  const me = await currentUser();
  if (!me) {
    return NextResponse.json(
      { ok: false, error: "Not signed in" },
      { status: 401 }
    );
  }
  let body: { message?: string };
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const message = body.message?.trim() ?? "";
  const sb = supabaseServer();

  // Dedup: if there's already a pending request for this email, just
  // re-stamp the message instead of stacking duplicates.
  const { data: existing } = await sb
    .from("signup_requests")
    .select("id")
    .ilike("email", me.email)
    .eq("status", "pending")
    .maybeSingle();

  if (existing) {
    const id = (existing as { id: string }).id;
    await sb
      .from("signup_requests")
      .update({ message: message || null, created_at: new Date().toISOString() })
      .eq("id", id);
  } else {
    const { error } = await sb.from("signup_requests").insert({
      email: me.email,
      name: me.name,
      message: message || null,
      status: "pending",
    });
    if (error) {
      return NextResponse.json(
        { ok: false, error: error.message },
        { status: 400 }
      );
    }
  }

  const origin = req.nextUrl.origin;
  await sendEmail({
    to: ADMIN_NOTIFY_EMAIL,
    subject: `Access request — ${me.name}`,
    html: brandWrap({
      preheader: `${me.name} (${me.email}) is asking for job access.`,
      intro: `${me.name} (${me.email}) is signed in but has no jobs yet.`,
      body:
        (message
          ? `<strong>Their note:</strong> ${message.replace(/</g, "&lt;").slice(0, 500)}<br/><br/>`
          : "") +
        `Head to /admin/users to approve and use /admin/jobs to assign jobs to <code style="background:#EBEEF0;padding:2px 4px;">pm_id=${me.pmId ?? "unknown"}</code>.`,
      cta: "Review on /admin/users",
      ctaUrl: `${origin}/admin/users`,
    }),
    text: `Access request from ${me.name} (${me.email})${message ? "\n\nNote: " + message : ""}\n\nReview: ${origin}/admin/users`,
  });

  revalidatePath("/admin/users");
  revalidatePath("/admin");
  revalidatePath("/");

  return NextResponse.json({ ok: true });
}
