// Identity helper. Until real auth ships, the "actor" (who clicked the
// button) comes from one of three places, in priority order:
//
//   1. Request header `x-actor` (lets the client override per-request — useful
//      once a user-switcher UI exists)
//   2. Env var `DEFAULT_ACTOR` (per-deployment default)
//   3. The string "jake" as a final fallback so existing rows keep working
//
// Routes call getActor(req) instead of hardcoding a name. Replace with the
// real session lookup when auth lands.

import { NextRequest } from "next/server";

export function getActor(req: NextRequest | Request): string {
  const h = req.headers.get("x-actor");
  if (h && h.trim().length > 0) return h.trim();
  const env = process.env.DEFAULT_ACTOR;
  if (env && env.trim().length > 0) return env.trim();
  return "jake";
}
