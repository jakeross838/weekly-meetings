import { NextRequest, NextResponse } from "next/server";
import {
  checkPassword,
  encodeSession,
  SESSION_COOKIE,
  SESSION_TTL_SEC,
} from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { email?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim() ?? "";
  const password = body.password ?? "";
  if (!email || !password) {
    return NextResponse.json(
      { ok: false, error: "Email and password required" },
      { status: 400 }
    );
  }
  const user = checkPassword(email, password);
  if (!user) {
    return NextResponse.json(
      { ok: false, error: "Wrong email or password" },
      { status: 401 }
    );
  }
  const token = encodeSession(user.email);
  const res = NextResponse.json({
    ok: true,
    user: { email: user.email, name: user.name, role: user.role },
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
