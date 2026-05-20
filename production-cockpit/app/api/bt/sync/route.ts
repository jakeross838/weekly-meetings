// POST /api/bt/sync
// Body: { username, password, days?, jobs?, skipPhotos?, maxPhotosPerLog?, extractVision? }
//
// Orchestrates a one-click Buildertrend pull from inside the cockpit:
//   1. Spawns the local Python scraper at $BT_SCRAPER_DIR
//      (default C:\Users\Greg\buildertrend-scraper) with the user's BT
//      credentials passed via env vars (BT_USERNAME / BT_PASSWORD). The
//      vars exist only in the child process — never persisted, never
//      logged, never echoed back to the client.
//   2. Reads the scraper's data/daily-logs.json output.
//   3. POSTs it to this app's /v2/api/daily-logs/upload route to upsert
//      into Supabase.
//   4. If extractVision (default true), POSTs to /v2/api/daily-logs/
//      extract-photos to run Claude vision over any new photos.
//   5. Returns an aggregated summary the modal renders.
//
// Hard requirement: this route shells out to a local Python process. It
// will only work when the cockpit is running on the same machine as the
// scraper repo (i.e. `npm run dev` locally). Vercel/serverless deploys
// short-circuit with a clear error.

import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
// Local dev only — the route refuses to run when VERCEL=1, so this
// number is informational. Kept under 60 to avoid Vercel-plan warnings
// during a Next.js compile if the file is ever picked up server-side.
export const maxDuration = 60;
// Manual timeout used for the spawned child process. Independent of
// `maxDuration` above so we control it without tripping any Next checks.
const CHILD_TIMEOUT_SEC = 290;

const DEFAULT_SCRAPER_DIR = "C:\\Users\\Greg\\buildertrend-scraper";

interface SyncBody {
  username?: string;
  password?: string;
  days?: number;
  jobs?: string;
  skipPhotos?: boolean;
  maxPhotosPerLog?: number;
  extractVision?: boolean;
  // Debug — when true, scraper runs with --headed so the operator can
  // see what BT is actually showing. Required for first-time auth on
  // MFA-protected accounts.
  headed?: boolean;
}

function jsonError(message: string, status = 400, extra: object = {}) {
  return NextResponse.json({ ok: false, error: message, ...extra }, { status });
}

// Replace any occurrence of the password in a log string with a stable
// placeholder. Belt-and-suspenders: the scraper doesn't print the
// password, but if a Playwright error message ever does, this prevents
// it leaking back to the client.
function redact(text: string, password: string): string {
  if (!password) return text;
  return text.split(password).join("[redacted-password]");
}

export async function POST(req: NextRequest) {
  if (process.env.VERCEL === "1") {
    return jsonError(
      "BT sync requires a local environment (spawns Python + Playwright). " +
        "Run `npm run dev` on your laptop and use the button there.",
      400
    );
  }

  let body: SyncBody = {};
  try {
    body = (await req.json()) as SyncBody;
  } catch {
    return jsonError("Invalid JSON body");
  }

  const username = body.username?.trim();
  const password = body.password ?? "";
  if (!username || !password) {
    return jsonError("username and password required");
  }

  const days = Number.isFinite(body.days) && body.days! > 0 ? body.days! : 14;
  const jobs = body.jobs?.trim() || "";
  const skipPhotos = Boolean(body.skipPhotos);
  const maxPhotos =
    Number.isFinite(body.maxPhotosPerLog) && body.maxPhotosPerLog! > 0
      ? body.maxPhotosPerLog!
      : 6;
  const extractVision = body.extractVision !== false;

  const scraperDir = process.env.BT_SCRAPER_DIR || DEFAULT_SCRAPER_DIR;
  const pythonExe = path.join(scraperDir, ".venv", "Scripts", "python.exe");
  // scrape_api.py = API-based scraper (BT rebuilt their UI into a SPA + JSON
  // API; the old DOM-walking scrape.py finds nothing). Same CLI + output shape.
  const scriptPath = path.join(scraperDir, "scrape_api.py");
  const outputPath = path.join(scraperDir, "data", "daily-logs.json");

  // Sanity-check the scraper install up-front so we don't waste a
  // process-spawn on a missing path.
  try {
    await fs.access(pythonExe);
    await fs.access(scriptPath);
  } catch {
    return jsonError(
      `Scraper not found at ${scraperDir}. Set BT_SCRAPER_DIR if it lives somewhere else, or follow the buildertrend-scraper README to set up the venv.`,
      500,
      { scraperDir, pythonExe, scriptPath }
    );
  }

  // Build the CLI args — never password.
  const args = [scriptPath, "--days", String(days)];
  if (jobs) args.push("--jobs", jobs);
  if (skipPhotos) args.push("--skip-photos");
  args.push("--max-photos-per-log", String(maxPhotos));
  if (body.headed) args.push("--headed");
  // We always want logs; pass -v so the operator can see what's
  // happening in the response payload.
  args.push("-v");

  const startedAt = Date.now();
  let stdoutBuf = "";
  let stderrBuf = "";

  const proc = spawn(pythonExe, args, {
    cwd: scraperDir,
    env: {
      ...process.env,
      BT_USERNAME: username,
      BT_PASSWORD: password,
      // Force UTF-8 so Windows codepage 1252 doesn't mangle BT's
      // accented chars / em-dashes in logs.
      PYTHONIOENCODING: "utf-8",
    },
    // No shell — args are passed verbatim and never interpolated into a
    // command string, so the password never reaches a shell.
    shell: false,
  });

  proc.stdout.on("data", (chunk: Buffer) => {
    stdoutBuf += chunk.toString("utf-8");
  });
  proc.stderr.on("data", (chunk: Buffer) => {
    stderrBuf += chunk.toString("utf-8");
  });

  // Manual timeout — kill the child if it runs past CHILD_TIMEOUT_SEC.
  const killTimer = setTimeout(() => {
    try {
      proc.kill();
    } catch {
      // ignore
    }
  }, CHILD_TIMEOUT_SEC * 1000);

  const exitCode: number = await new Promise((resolve) => {
    proc.on("close", (code) => resolve(code ?? -1));
    proc.on("error", () => resolve(-1));
  });
  clearTimeout(killTimer);

  const elapsedMs = Date.now() - startedAt;
  const stdoutTail = redact(stdoutBuf.slice(-3000), password);
  const stderrTail = redact(stderrBuf.slice(-3000), password);

  // Server-side: dump the failure to a debug file so the operator (or
  // me, the dev) can inspect it without copy-pasting from the modal.
  // Path is intentionally outside the cockpit repo so it doesn't trigger
  // a Next file-watcher reload. Password is already redacted above.
  if (exitCode !== 0) {
    try {
      const debugPath = path.join(scraperDir, ".session", "last-failure.log");
      await fs.mkdir(path.dirname(debugPath), { recursive: true });
      await fs.writeFile(
        debugPath,
        `=== BT sync failure ${new Date().toISOString()} ===\n` +
          `exit=${exitCode} elapsed=${Math.round(elapsedMs / 1000)}s\n\n` +
          `--- stderr ---\n${stderrTail}\n\n` +
          `--- stdout ---\n${stdoutTail}\n`,
        "utf-8"
      );
      console.error(
        `[bt/sync] scraper failed (exit ${exitCode}, ${Math.round(elapsedMs / 1000)}s). ` +
          `Tail dump at ${debugPath}. stderr last 500 chars: ${stderrBuf
            .slice(-500)
            .replace(password, "[redacted]")}`
      );
    } catch (e) {
      console.error("[bt/sync] failed to write debug dump:", e);
    }
    return jsonError(
      `Scraper exited ${exitCode} after ${Math.round(elapsedMs / 1000)}s`,
      500,
      { stdoutTail, stderrTail, elapsedMs }
    );
  }

  // Read the scraper output.
  let payload: unknown;
  try {
    const raw = await fs.readFile(outputPath, "utf-8");
    payload = JSON.parse(raw);
  } catch (e) {
    return jsonError(
      `Could not read scraper output at ${outputPath}: ${
        e instanceof Error ? e.message : String(e)
      }`,
      500,
      { stdoutTail, stderrTail }
    );
  }

  // Drop the BT credentials immediately after the scraper exits. They
  // were only in this request's local scope to begin with, but explicitly
  // overwriting paranoid-wipes any closure that might capture them.
  body.password = "";

  // Hand to the existing upload route via fetch on the same origin so
  // we reuse the upsert logic (and its de-dupe by job_key+log_id).
  const origin = req.nextUrl.origin;
  let uploadResult: { ok?: boolean; error?: string; inserted?: number; skipped?: number; per_job?: Record<string, { total: number; inserted: number; skipped: number }> } = {};
  try {
    const r = await fetch(`${origin}/v2/api/daily-logs/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "cockpit-bt-sync", payload }),
    });
    uploadResult = (await r.json().catch(() => ({}))) as typeof uploadResult;
    if (!r.ok || uploadResult.ok === false) {
      return jsonError(
        `Upload route returned ${r.status}: ${uploadResult.error ?? "unknown"}`,
        500,
        { stdoutTail, stderrTail, uploadResult, elapsedMs }
      );
    }
  } catch (e) {
    return jsonError(
      `Upload call failed: ${e instanceof Error ? e.message : String(e)}`,
      500,
      { stdoutTail, stderrTail, elapsedMs }
    );
  }

  // Vision pass — optional, hard-capped by the extract-photos route itself.
  let visionResult:
    | { ok?: boolean; considered?: number; processed?: number; failed?: number }
    | null = null;
  let visionError: string | null = null;
  if (extractVision && !skipPhotos) {
    try {
      const r = await fetch(`${origin}/v2/api/daily-logs/extract-photos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 30 }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        visionError = (j as { error?: string }).error ?? `HTTP ${r.status}`;
      } else {
        visionResult = j as typeof visionResult;
      }
    } catch (e) {
      visionError = e instanceof Error ? e.message : String(e);
    }
  }

  // Quick summary derived from the scraper payload so the modal can show
  // "5 jobs, 23 logs, 47 photos" without re-parsing.
  let logCount = 0;
  let photoCount = 0;
  let jobCount = 0;
  try {
    const byJob = (payload as { byJob?: Record<string, unknown[]> }).byJob ?? {};
    jobCount = Object.keys(byJob).length;
    for (const rows of Object.values(byJob)) {
      if (!Array.isArray(rows)) continue;
      logCount += rows.length;
      for (const r of rows) {
        const arr = (r as { photo_urls?: unknown[] })?.photo_urls;
        if (Array.isArray(arr)) photoCount += arr.length;
      }
    }
  } catch {
    // ignore — payload summary is best-effort
  }

  return NextResponse.json({
    ok: true,
    elapsedMs,
    scrape: {
      exitCode,
      jobCount,
      logCount,
      photoCount,
      stdoutTail,
      stderrTail,
    },
    upload: uploadResult,
    vision: visionResult,
    visionError,
  });
}
