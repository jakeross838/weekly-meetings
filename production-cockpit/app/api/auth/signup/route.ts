// POST /api/auth/signup
// Public route. Creates the user_overlay row immediately + auto-issues a
// session cookie so the user is signed in on success. They land on /
// with zero jobs visible until admin approves their access request and
// assigns them jobs in /admin/jobs.
//
// Email is normalized lowercase; pmId auto-generated from the local-part
// (sanitized to lowercase letters / digits / _ / -) so the new user has
// a stable id Jake can assign jobs to later.

import { NextRequest, NextResponse } from "next/server";
import { createUser } from "@/lib/user-store";
import { findUserByEmail } from "@/lib/auth";
import {
  encodeSession,
  SESSION_COOKIE,
  SESSION_TTL_SEC,
} from "@/lib/auth";
import { sendEmail, brandWrap } from "@/lib/email";

export const dynamic = "force-dynamic";

const ADMIN_NOTIFY_EMAIL = "jakeross838@gmail.com";

function pmIdFromEmail(email: string): string {
  const local = email.split("@")[0].toLowerCase();
  return local.replace(/[^a-z0-9_-]/g, "").slice(0, 32) || "user";
}

export async function POST(req: NextRequest) {
  let body: { email?: string; name?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim() ?? "";
  const name = body.name?.trim() ?? "";
  const password = body.password ?? "";
  if (!email || !name || !password) {
    return NextResponse.json(
      { ok: false, error: "name, email, and password required" },
      { status: 400 }
    );
  }
  if (!email.includes("@")) {
    return NextResponse.json({ ok: false, error: "invalid email" }, { status: 400 });
  }
  if (password.length < 6) {
    return NextResponse.json(
      { ok: false, error: "password must be at least 6 characters" },
      { status: 400 }
    );
  }

  // Block if a user with that email already exists (covers seed + overlay).
  const existing = await findUserByEmail(email);
  if (existing) {
    return NextResponse.json(
      { ok: false, error: "An account with that email already exists. Try signing in." },
      { status: 400 }
    );
  }

  const pmId = pmIdFromEmail(email);
  try {
    await createUser({
      email,
      name,
      pmId,
      allowedJobs: [],
      password,
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 400 }
    );
  }

  // Heads-up to admin so they know someone new just showed up. Body is
  // intentionally low-key — the formal "request access" ticket comes when
  // the user clicks the button on their empty cockpit.
  const origin = req.nextUrl.origin;
  await sendEmail({
    to: ADMIN_NOTIFY_EMAIL,
    subject: `New cockpit signup — ${name}`,
    html: brandWrap({
      preheader: `${name} just created an account.`,
      intro: `${name} (${email}) just created a cockpit account.`,
      body: `They have zero jobs assigned and won't see anything until you grant access. If they're someone you know, head to <a href="${origin}/admin/users" style="color:#5B8497">/admin/users</a> to set them up; if not, you can disable them from the same panel.`,
      cta: "Open /admin/users",
      ctaUrl: `${origin}/admin/users`,
    }),
    text: `New cockpit signup — ${name} (${email}). Review at ${origin}/admin/users`,
  });

  // Auto-login: set the session cookie so the browser is signed in.
  const token = encodeSession(email);
  const res = NextResponse.json({
    ok: true,
    user: { email, name, role: "pm" },
  });
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SEC,
  });
  return res;
}
