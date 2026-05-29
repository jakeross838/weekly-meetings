// Forgot password — issues a one-time reset token + emails the user a link.
// Always returns success even if the email isn't a real account, so the
// endpoint can't be used to enumerate user emails.

import { NextRequest, NextResponse } from "next/server";
import { findUserByEmail } from "@/lib/auth";
import { issueResetToken } from "@/lib/tokens";
import { sendEmail, brandWrap } from "@/lib/email";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { email?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim().toLowerCase() ?? "";
  if (!email) {
    return NextResponse.json({ ok: false, error: "email required" }, { status: 400 });
  }

  // Always claim success — don't reveal whether email exists.
  const user = await findUserByEmail(email);
  if (!user) {
    return NextResponse.json({ ok: true });
  }

  const token = await issueResetToken(user.email);
  const origin = req.nextUrl.origin;
  const resetUrl = `${origin}/reset/${token}`;
  await sendEmail({
    to: user.email,
    subject: "Reset your Ross Built cockpit password",
    html: brandWrap({
      preheader: "Reset your password — link expires in 1 hour.",
      intro: `Hey ${user.name.split(" ")[0]} — somebody (hopefully you) asked to reset your Ross Built cockpit password.`,
      body: "Click the button below to set a new password. The link is good for 1 hour. If you didn't ask for this, ignore this email and your password stays unchanged.",
      cta: "Reset password",
      ctaUrl: resetUrl,
    }),
    text: `Reset your Ross Built cockpit password.\n\n${resetUrl}\n\nThis link expires in 1 hour. If you didn't ask for this, ignore this email.`,
  });

  return NextResponse.json({ ok: true });
}
