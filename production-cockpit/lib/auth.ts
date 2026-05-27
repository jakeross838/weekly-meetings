// Auth: HMAC-signed session cookie + user lookup. The seed user list lives in
// lib/auth-users.ts; lib/user-store.ts merges that with a JSON overlay so the
// admin panel can add users / edit job access at runtime without a code change.
// Passwords are plaintext literals — internal MVP only. Move to a real
// provider before this goes anywhere public.

import crypto from "node:crypto";
import { cookies } from "next/headers";
import { SESSION_COOKIE, SESSION_TTL_SEC } from "./auth-constants";
import { getAllUsers } from "./user-store";

export type { Role, User } from "./auth-users";
import type { User } from "./auth-users";

function getSecret(): string {
  const s = process.env.AUTH_SECRET;
  if (s && s.length >= 16) return s;
  // Dev fallback so the app boots without manual env setup. Logged once.
  if (!process.env._RB_AUTH_FALLBACK_WARNED) {
    console.warn("[auth] AUTH_SECRET not set — using insecure dev fallback. Set AUTH_SECRET in .env.local before deploying.");
    process.env._RB_AUTH_FALLBACK_WARNED = "1";
  }
  return "ross-built-dev-secret-please-change-me-now";
}

function b64url(buf: Buffer | string): string {
  return Buffer.from(buf).toString("base64url");
}

function fromB64url(s: string): Buffer {
  return Buffer.from(s, "base64url");
}

function sign(payload: string): string {
  return crypto
    .createHmac("sha256", getSecret())
    .update(payload)
    .digest("base64url");
}

interface SessionPayload {
  email: string;
  exp: number; // unix seconds
}

export function encodeSession(email: string): string {
  const payload: SessionPayload = {
    email,
    exp: Math.floor(Date.now() / 1000) + SESSION_TTL_SEC,
  };
  const body = b64url(JSON.stringify(payload));
  const sig = sign(body);
  return `${body}.${sig}`;
}

export async function decodeSession(token: string | undefined): Promise<User | null> {
  if (!token) return null;
  const [body, sig] = token.split(".");
  if (!body || !sig) return null;
  const expected = sign(body);
  // Constant-time compare to avoid timing side channels on the HMAC.
  if (
    sig.length !== expected.length ||
    !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))
  ) {
    return null;
  }
  let payload: SessionPayload;
  try {
    payload = JSON.parse(fromB64url(body).toString("utf-8"));
  } catch {
    return null;
  }
  if (!payload?.email || !payload?.exp) return null;
  if (payload.exp < Math.floor(Date.now() / 1000)) return null;
  return findUserByEmail(payload.email);
}

export async function findUserByEmail(email: string): Promise<User | null> {
  const norm = email.trim().toLowerCase();
  const users = await getAllUsers();
  return users.find((u) => u.email.toLowerCase() === norm) ?? null;
}

export async function checkPassword(email: string, password: string): Promise<User | null> {
  const u = await findUserByEmail(email);
  if (!u) return null;
  // Plaintext comparison — see file header.
  if (u.password !== password) return null;
  return u;
}

// Server-component / route-handler helper. Reads the session cookie.
export async function currentUser(): Promise<User | null> {
  const token = cookies().get(SESSION_COOKIE)?.value;
  return decodeSession(token);
}

export function isAdmin(u: User | null): boolean {
  return !!u && u.role === "admin";
}

// Single source of truth for "can this user see this job":
// admin → yes; otherwise the job's PM (from `jobs.pm_id`, or an active row in
// `job_pm_assignments`) must match the user's own pmId. Pass `null` when the
// job has no PM assigned — non-admins won't see it; admins still will.
export function canSeeJobByPm(u: User | null, jobPmId: string | null): boolean {
  if (!u) return false;
  if (u.role === "admin") return true;
  return !!jobPmId && jobPmId === u.pmId;
}

// Re-export edge-safe constants so callers can `import { SESSION_COOKIE } from "@/lib/auth"`.
export { SESSION_COOKIE, SESSION_TTL_SEC };
