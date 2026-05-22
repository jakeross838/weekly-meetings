// POST /api/bt/sync-co
// Body: { username, password, jobs?, headed? }
//
// One-click Buildertrend change-order pull: spawns scrape_co.py at
// $BT_SCRAPER_DIR (BT creds via child env, never persisted), reads
// data/change-orders.json, POSTs it to /v2/api/change-orders/upload.
// Local-only (spawns Python + Playwright); refuses on Vercel.

import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // informational — route refuses on VERCEL=1
const CHILD_TIMEOUT_SEC = 600;

const DEFAULT_SCRAPER_DIR = "C:\\Users\\Greg\\buildertrend-scraper";

interface SyncBody {
  username?: string;
  password?: string;
  jobs?: string;
  headed?: boolean;
}

function jsonError(message: string, status = 400, extra: object = {}) {
  return NextResponse.json({ ok: false, error: message, ...extra }, { status });
}
function redact(text: string, password: string): string {
  if (!password) return text;
  return text.split(password).join("[redacted-password]");
}

export async function POST(req: NextRequest) {
  if (process.env.VERCEL === "1") {
    return jsonError(
      "Change-order sync requires a local environment (spawns Python + Playwright). " +
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
  if (!username || !password) return jsonError("username and password required");
  const jobs = body.jobs?.trim() || "";

  const scraperDir = process.env.BT_SCRAPER_DIR || DEFAULT_SCRAPER_DIR;
  const pythonExe = path.join(scraperDir, ".venv", "Scripts", "python.exe");
  const scriptPath = path.join(scraperDir, "scrape_co.py");
  const outputPath = path.join(scraperDir, "data", "change-orders.json");

  try {
    await fs.access(pythonExe);
    await fs.access(scriptPath);
  } catch {
    return jsonError(
      `Scraper not found at ${scraperDir}. Set BT_SCRAPER_DIR or follow the buildertrend-scraper README.`,
      500,
      { scraperDir, scriptPath }
    );
  }

  const args = [scriptPath];
  if (jobs) args.push("--jobs", jobs);
  args.push("-v");
  if (body.headed) args.push("--headed");

  const startedAt = Date.now();
  let stdoutBuf = "";
  let stderrBuf = "";
  const proc = spawn(pythonExe, args, {
    cwd: scraperDir,
    env: { ...process.env, BT_USERNAME: username, BT_PASSWORD: password, PYTHONIOENCODING: "utf-8" },
    shell: false,
  });
  proc.stdout.on("data", (c: Buffer) => { stdoutBuf += c.toString("utf-8"); });
  proc.stderr.on("data", (c: Buffer) => { stderrBuf += c.toString("utf-8"); });
  const killTimer = setTimeout(() => { try { proc.kill(); } catch { /* */ } }, CHILD_TIMEOUT_SEC * 1000);
  const exitCode: number = await new Promise((resolve) => {
    proc.on("close", (code) => resolve(code ?? -1));
    proc.on("error", () => resolve(-1));
  });
  clearTimeout(killTimer);

  const elapsedMs = Date.now() - startedAt;
  const stdoutTail = redact(stdoutBuf.slice(-3000), password);
  const stderrTail = redact(stderrBuf.slice(-3000), password);

  if (exitCode !== 0) {
    return jsonError(`Scraper exited ${exitCode} after ${Math.round(elapsedMs / 1000)}s`, 500, {
      stdoutTail, stderrTail, elapsedMs,
    });
  }

  let payload: unknown;
  try {
    payload = JSON.parse(await fs.readFile(outputPath, "utf-8"));
  } catch (e) {
    return jsonError(`Could not read ${outputPath}: ${e instanceof Error ? e.message : String(e)}`, 500, { stdoutTail });
  }
  body.password = "";

  const origin = req.nextUrl.origin;
  let uploadResult: { ok?: boolean; error?: string; jobs?: number; upserted?: number; errors?: string[] } = {};
  try {
    const r = await fetch(`${origin}/v2/api/change-orders/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    });
    uploadResult = (await r.json().catch(() => ({}))) as typeof uploadResult;
    if (!r.ok || uploadResult.ok === false) {
      return jsonError(`Upload returned ${r.status}: ${uploadResult.error ?? (uploadResult.errors ?? []).join("; ")}`, 500, { stdoutTail, uploadResult });
    }
  } catch (e) {
    return jsonError(`Upload call failed: ${e instanceof Error ? e.message : String(e)}`, 500, { stdoutTail });
  }

  let coCount = 0;
  let jobCount = 0;
  try {
    const pj = (payload as { byJob?: Record<string, unknown[]> }).byJob ?? {};
    jobCount = Object.keys(pj).length;
    for (const rows of Object.values(pj)) if (Array.isArray(rows)) coCount += rows.length;
  } catch { /* best-effort */ }

  return NextResponse.json({
    ok: true,
    elapsedMs,
    scrape: { exitCode, jobCount, coCount, stdoutTail, stderrTail },
    upload: uploadResult,
  });
}
