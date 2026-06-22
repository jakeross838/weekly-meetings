// Protect the public BT upload routes from anonymous internet writes once the
// cloud sync (GitHub Actions) starts POSTing to them over the open web.
//
// Enforced ONLY when BT_SYNC_TOKEN is set — i.e. on the deployed site. There it
// allows two callers: the cloud sync (presents the matching x-bt-sync-token) and
// a logged-in admin (the in-app manual JSON upload). Anyone else gets 401.
//
// When BT_SYNC_TOKEN is UNSET (local dev, and the local /api/bt/sync-all
// server-to-server flow that never carries the header), the routes stay open
// exactly as before — so this is a zero-impact opt-in: nothing changes until the
// operator sets BT_SYNC_TOKEN in the deployed env.

import { NextRequest, NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";

export async function guardSyncWrite(
  req: NextRequest
): Promise<NextResponse | null> {
  const token = process.env.BT_SYNC_TOKEN;
  if (!token) return null; // not configured → preserve trusted-internal behavior
  const provided = req.headers.get("x-bt-sync-token");
  if (provided && provided === token) return null;
  if (isAdmin(await currentUser())) return null;
  return NextResponse.json(
    { ok: false, error: "unauthorized sync write" },
    { status: 401 }
  );
}
