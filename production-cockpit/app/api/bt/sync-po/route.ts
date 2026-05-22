// POST /api/bt/sync-po
// Body: { username, password, jobs?, includeLineItems?, headed? }
//
// One-click Buildertrend Purchase-Order pull from inside the cockpit:
//   1. Spawns the local Python scraper (scrape_po.py) at $BT_SCRAPER_DIR with
//      BT_USERNAME / BT_PASSWORD in the child env (never persisted/logged).
//   2. Reads data/purchase-orders.json.
//   3. POSTs it to /v2/api/purchase-orders/upload (with skipLineItems matching
//      the scrape mode, so a grid-only pull never deletes existing line items).
//
// Default is a fast grid-only pull (PO totals/status across all jobs, ~2-3 min).
// Line items are slow (one request per PO); only pull them for a few jobs at a
// time via the `jobs` filter or you'll hit the child timeout.
//
// Local-only: shells out to Python + Playwright, so it refuses on Vercel.

import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // informational — route refuses on VERCEL=1
const CHILD_TIMEOUT_SEC = 290;

const DEFAULT_SCRAPER_DIR = "C:\\Users\\Greg\\buildertrend-scraper";

interface SyncBody {
  username?: string;
  password?: string;
  jobs?: string;
  includeLineItems?: boolean;
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
      "PO sync requires a local environment (spawns Python + Playwright). " +
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

  const jobs = body.jobs?.trim() || "";
  const includeLineItems = body.includeLineItems === true;

  const scraperDir = process.env.BT_SCRAPER_DIR || DEFAULT_SCRAPER_DIR;
  const pythonExe = path.join(scraperDir, ".venv", "Scripts", "python.exe");
  const scriptPath = path.join(scraperDir, "scrape_po.py");
  const outputPath = path.join(scraperDir, "data", "purchase-orders.json");

  try {
    await fs.access(pythonExe);
    await fs.access(scriptPath);
  } catch {
    return jsonError(
      `Scraper not found at ${scraperDir}. Set BT_SCRAPER_DIR if it lives elsewhere, or follow the buildertrend-scraper README to set up the venv.`,
      500,
      { scraperDir, pythonExe, scriptPath }
    );
  }

  // Build CLI args — never the password. Grid-only unless includeLineItems.
  const args = [scriptPath];
  if (jobs) args.push("--jobs", jobs);
  if (!includeLineItems) args.push("--skip-line-items");
  args.push("-v");
  if (body.headed) args.push("--headed");

  const startedAt = Date.now();
  let stdoutBuf = "";
  let stderrBuf = "";

  const proc = spawn(pythonExe, args, {
    cwd: scraperDir,
    env: {
      ...process.env,
      BT_USERNAME: username,
      BT_PASSWORD: password,
      PYTHONIOENCODING: "utf-8",
    },
    shell: false,
  });

  proc.stdout.on("data", (chunk: Buffer) => {
    stdoutBuf += chunk.toString("utf-8");
  });
  proc.stderr.on("data", (chunk: Buffer) => {
    stderrBuf += chunk.toString("utf-8");
  });

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

  if (exitCode !== 0) {
    try {
      const debugPath = path.join(scraperDir, ".session", "last-po-failure.log");
      await fs.mkdir(path.dirname(debugPath), { recursive: true });
      await fs.writeFile(
        debugPath,
        `=== BT PO sync failure ${new Date().toISOString()} ===\n` +
          `exit=${exitCode} elapsed=${Math.round(elapsedMs / 1000)}s\n\n` +
          `--- stderr ---\n${stderrTail}\n\n--- stdout ---\n${stdoutTail}\n`,
        "utf-8"
      );
    } catch (e) {
      console.error("[bt/sync-po] failed to write debug dump:", e);
    }
    return jsonError(
      `Scraper exited ${exitCode} after ${Math.round(elapsedMs / 1000)}s` +
        (elapsedMs >= CHILD_TIMEOUT_SEC * 1000
          ? " (timed out — try a jobs filter, or pull without line items)"
          : ""),
      500,
      { stdoutTail, stderrTail, elapsedMs }
    );
  }

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

  // Wipe the credential from this request's scope.
  body.password = "";

  // Hand to the PO upload route; skipLineItems matches the scrape mode so a
  // grid-only pull preserves previously-loaded line items.
  const origin = req.nextUrl.origin;
  let uploadResult: {
    ok?: boolean;
    error?: string;
    jobs?: number;
    upserted?: number;
    lineItems?: number;
    errors?: string[];
  } = {};
  try {
    const r = await fetch(`${origin}/v2/api/purchase-orders/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload, skipLineItems: !includeLineItems }),
    });
    uploadResult = (await r.json().catch(() => ({}))) as typeof uploadResult;
    if (!r.ok || uploadResult.ok === false) {
      return jsonError(
        `Upload route returned ${r.status}: ${uploadResult.error ?? (uploadResult.errors ?? []).join("; ") ?? "unknown"}`,
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

  // Summarize the scrape payload.
  let poCount = 0;
  let lineItemCount = 0;
  let jobCount = 0;
  try {
    const pj = (payload as { byJob?: Record<string, unknown[]> }).byJob ?? {};
    jobCount = Object.keys(pj).length;
    for (const rows of Object.values(pj)) {
      if (!Array.isArray(rows)) continue;
      poCount += rows.length;
      for (const po of rows) {
        const li = (po as { line_items?: unknown[] })?.line_items;
        if (Array.isArray(li)) lineItemCount += li.length;
      }
    }
  } catch {
    // best-effort
  }

  return NextResponse.json({
    ok: true,
    elapsedMs,
    includeLineItems,
    scrape: { exitCode, jobCount, poCount, lineItemCount, stdoutTail, stderrTail },
    upload: uploadResult,
  });
}
