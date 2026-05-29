// One-time tokens for password reset. Tokens are 32-byte cryptographically
// random strings stored in `public.password_reset_tokens` (PK on token, +
// expires_at). They're marked `used_at` on success — single-use.

import crypto from "node:crypto";
import { supabaseServer } from "./supabase";

const TOKEN_TTL_HOURS = 1; // tokens expire after 1 hour

export function generateToken(): string {
  return crypto.randomBytes(32).toString("base64url");
}

export async function issueResetToken(email: string): Promise<string> {
  const token = generateToken();
  const expiresAt = new Date(
    Date.now() + TOKEN_TTL_HOURS * 60 * 60 * 1000
  ).toISOString();
  const sb = supabaseServer();
  const { error } = await sb.from("password_reset_tokens").insert({
    token,
    email: email.trim().toLowerCase(),
    expires_at: expiresAt,
  });
  if (error) throw new Error(error.message);
  return token;
}

export interface ResetTokenInfo {
  email: string;
  valid: boolean;
  reason?: "missing" | "expired" | "used";
}

export async function lookupResetToken(token: string): Promise<ResetTokenInfo | null> {
  const sb = supabaseServer();
  const { data } = await sb
    .from("password_reset_tokens")
    .select("email, expires_at, used_at")
    .eq("token", token)
    .maybeSingle();
  if (!data) return { email: "", valid: false, reason: "missing" };
  const row = data as { email: string; expires_at: string; used_at: string | null };
  if (row.used_at) return { email: row.email, valid: false, reason: "used" };
  if (new Date(row.expires_at).getTime() < Date.now()) {
    return { email: row.email, valid: false, reason: "expired" };
  }
  return { email: row.email, valid: true };
}

export async function consumeResetToken(token: string): Promise<void> {
  const sb = supabaseServer();
  const { error } = await sb
    .from("password_reset_tokens")
    .update({ used_at: new Date().toISOString() })
    .eq("token", token);
  if (error) throw new Error(error.message);
}
