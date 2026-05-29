// Consume a password-reset token and set the new password.

import { NextRequest, NextResponse } from "next/server";
import { lookupResetToken, consumeResetToken } from "@/lib/tokens";
import { setUserPassword } from "@/lib/user-store";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { token?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const token = body.token?.trim() ?? "";
  const password = body.password ?? "";
  if (!token || !password) {
    return NextResponse.json(
      { ok: false, error: "token and password required" },
      { status: 400 }
    );
  }
  if (password.length < 6) {
    return NextResponse.json(
      { ok: false, error: "password must be at least 6 characters" },
      { status: 400 }
    );
  }
  const info = await lookupResetToken(token);
  if (!info || !info.valid) {
    const why =
      info?.reason === "expired"
        ? "This link expired — request a new one."
        : info?.reason === "used"
          ? "This link was already used — request a new one."
          : "This link isn't valid.";
    return NextResponse.json({ ok: false, error: why }, { status: 400 });
  }
  try {
    await setUserPassword(info.email, password);
    await consumeResetToken(token);
    revalidatePath("/admin/users");
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 400 }
    );
  }
}
