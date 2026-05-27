import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth-constants";

// Gate UI routes behind a session cookie. API routes are intentionally NOT
// gated here — they're called by internal server-to-server fetches (e.g. the
// BT sync route POSTs to /v2/api/daily-logs/upload) that don't carry the
// browser cookie. Pages enforce per-job visibility on render.

const PUBLIC_PREFIXES = ["/login", "/api", "/_next", "/favicon"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/") || pathname === p)) {
    return NextResponse.next();
  }
  // We can't import the full auth.ts here (it uses node:crypto + next/headers),
  // so just check the cookie's presence. Real signature verification happens
  // server-side in pages via currentUser().
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname + (req.nextUrl.search || ""));
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Match everything except static files. The PUBLIC_PREFIXES list above
  // does the fine-grained whitelist.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|ross-built-logo.svg|ross-built-mark.svg).*)"],
};
