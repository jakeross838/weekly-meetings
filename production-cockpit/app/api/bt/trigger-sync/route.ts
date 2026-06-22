// POST /api/bt/trigger-sync
// Kicks off the cloud Buildertrend sync (the GitHub Actions workflow) on demand,
// so "Sync now" works from ANY device — phone included — with no laptop running.
// The scheduled 12h run is the primary, always-on path; this is the "right now"
// backup for when you don't want to wait for the next slot.
//
// Admin-only. Needs these env vars set in the deployment (Vercel):
//   GITHUB_SYNC_TOKEN     GitHub token with Actions: write on the scraper repo
//   GITHUB_SYNC_REPO      "owner/repo" of the scraper repo (holds bt-sync.yml)
//   GITHUB_SYNC_WORKFLOW  workflow file name (default "bt-sync.yml")
//   GITHUB_SYNC_REF       branch to run on (default "main")

import { NextResponse } from "next/server";
import { currentUser, isAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST() {
  if (!isAdmin(await currentUser())) {
    return NextResponse.json({ ok: false, error: "Admin only" }, { status: 403 });
  }

  const token = process.env.GITHUB_SYNC_TOKEN;
  const repo = process.env.GITHUB_SYNC_REPO;
  const workflow = process.env.GITHUB_SYNC_WORKFLOW || "bt-sync.yml";
  const ref = process.env.GITHUB_SYNC_REF || "main";

  if (!token || !repo) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Cloud sync isn't wired yet. Set GITHUB_SYNC_TOKEN (a GitHub token " +
          "with Actions:write) and GITHUB_SYNC_REPO (owner/repo) in the " +
          "deployment env. See buildertrend-scraper/CI-SETUP.md.",
      },
      { status: 503 }
    );
  }

  try {
    const r = await fetch(
      `https://api.github.com/repos/${repo}/actions/workflows/${encodeURIComponent(
        workflow
      )}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref, inputs: { kind: "manual" } }),
      }
    );
    // GitHub returns 204 No Content on a successful dispatch.
    if (r.status === 204) {
      return NextResponse.json({
        ok: true,
        message:
          "Sync started in the cloud. It runs on its own (a few minutes once " +
          "warmed up); the history below updates when it finishes.",
      });
    }
    const detail = await r.text().catch(() => "");
    return NextResponse.json(
      {
        ok: false,
        error:
          r.status === 404
            ? "GitHub couldn't find the workflow. Check GITHUB_SYNC_REPO / GITHUB_SYNC_WORKFLOW / GITHUB_SYNC_REF and that the scraper repo is pushed."
            : `GitHub returned ${r.status}.`,
        detail: detail.slice(0, 400),
      },
      { status: 502 }
    );
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 502 }
    );
  }
}
