import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth-constants";

// Gate UI routes behind a session cookie. API routes are intentionally NOT
// gated here — they're called by internal server-to-server fetches (e.g. the
// BT sync route POSTs to /v2/api/daily-logs/upload) that don't carry the
// browser cookie. Pages enforce per-job visibility on render.
//
// Middleware runs in the Edge runtime so we can't use node:crypto. The
// signature is verified via Web Crypto (subtle.crypto), which matches the
// HMAC-SHA256 used by lib/auth.ts:sign(). Invalid signatures (e.g. a stale
// cookie from before AUTH_SECRET was rotated) are treated as "no cookie".

const PUBLIC_PREFIXES = ["/login", "/api", "/_next", "/favicon"];

const DEV_FALLBACK_SECRET = "ross-built-dev-secret-please-change-me-now";

function getSecret(): string {
  const s = process.env.AUTH_SECRET;
  return s && s.length >= 16 ? s : DEV_FALLBACK_SECRET;
}

function base64urlToBytes(s: string): Uint8Array {
  // Pad and convert from base64url → base64 → bytes.
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function verifyToken(token: string): Promise<boolean> {
  const dot = token.lastIndexOf(".");
  if (dot < 1 || dot === token.length - 1) return false;
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  try {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(getSecret()),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    );
    const ok = await crypto.subtle.verify(
      "HMAC",
      key,
      base64urlToBytes(sig),
      new TextEncoder().encode(body)
    );
    if (!ok) return false;
    // Also check exp.
    const payload = JSON.parse(
      new TextDecoder().decode(base64urlToBytes(body))
    ) as { exp?: number };
    if (!payload.exp || payload.exp < Math.floor(Date.now() / 1000)) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (
    PUBLIC_PREFIXES.some(
      (p) =>
        pathname === p ||
        pathname.startsWith(p + "/") ||
        pathname === p
    )
  ) {
    return NextResponse.next();
  }
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const valid = token ? await verifyToken(token) : false;
  if (!valid) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname + (req.nextUrl.search || ""));
    const res = NextResponse.redirect(url);
    // Clear the stale cookie so the browser stops sending it.
    if (token) res.cookies.delete(SESSION_COOKIE);
    return res;
  }
  return NextResponse.next();
}

export const config = {
  // Match everything except static files. The PUBLIC_PREFIXES list above
  // does the fine-grained whitelist.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|ross-built-logo.svg|ross-built-mark.svg).*)",
  ],
};
