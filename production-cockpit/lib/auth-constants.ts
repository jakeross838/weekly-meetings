// Edge-safe constants for the auth layer. Kept separate from lib/auth.ts so
// middleware.ts (Edge runtime) can import them without pulling in node:crypto
// or next/headers.

export const SESSION_COOKIE = "rb_session";
export const SESSION_TTL_SEC = 7 * 24 * 60 * 60;
