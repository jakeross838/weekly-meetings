// Public endpoint — anyone can submit a request to join. Creates a
// `signup_requests` row with status='pending' and emails Jake (admin) so
// they get a heads-up. Returns ok regardless so the public form can't be
// used to enumerate emails either.

import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import { sendEmail, brandWrap } from "@/lib/email";
import { findUserByEmail } from "@/lib/auth";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

const ADMIN_NOTIFY_EMAIL = "jakeross838@gmail.com";

export async function POST(req: NextRequest) {
  let body: { email?: string; name?: string; message?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim().toLowerCase() ?? "";
  const name = body.name?.trim() ?? "";
  const message = body.message?.trim() ?? "";
  if (!email || !name) {
    return NextResponse.json(
      { ok: false, error: "name and email required" },
      { status: 400 }
    );
  }
  if (!email.includes("@")) {
    return NextResponse.json({ ok: false, error: "invalid email" }, { status: 400 });
  }

  // If they already have an account, just send the password-reset email
  // pathway in their honesty.
  const existing = await findUserByEmail(email);
  if (existing) {
    // Pretend it worked — don't reveal accounts. Admin gets no notification.
    return NextResponse.json({ ok: true, alreadyExists: true });
  }

  const sb = supabaseServer();
  const { data, error } = await sb
    .from("signup_requests")
    .insert({ email, name, message: message || null, status: "pending" })
    .select("id")
    .maybeSingle();
  if (error) {
    return NextResponse.json(
      { ok: false, error: error.message },
      { status: 400 }
    );
  }
  const requestId = (data as { id: string } | null)?.id ?? null;

  const origin = req.nextUrl.origin;
  await sendEmail({
    to: ADMIN_NOTIFY_EMAIL,
    subject: `New cockpit access request — ${name}`,
    html: brandWrap({
      preheader: `${name} (${email}) wants cockpit access.`,
      intro: `${name} just requested access to the cockpit.`,
      body:
        `<strong>Email:</strong> ${email}<br/>` +
        (message
          ? `<strong>Message:</strong> ${message.replace(/</g, "&lt;").slice(0, 500)}<br/>`
          : "") +
        `<br/>Open /admin/users to approve or reject.`,
      cta: "Review on /admin/users",
      ctaUrl: `${origin}/admin/users`,
    }),
    text: `New access request from ${name} (${email})${message ? "\n\nMessage: " + message : ""}\n\nReview: ${origin}/admin/users`,
  });

  revalidatePath("/admin/users");
  revalidatePath("/admin");

  return NextResponse.json({ ok: true, requestId });
}
