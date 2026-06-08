// POST /api/bt/sync-all
// Body: { username, password, headed? }
//
// One-click "Import all jobs from Buildertrend":
//   Step 1. scrape_api.py  → daily logs (+ photos) for every active job → upload
//                          → optional Claude vision pass on new photos
//   Step 2. scrape_po.py   → POs with line items for every active job → upload
//   Step 3. scrape_co.py   → change orders for every active job        → upload
//
// All three scrapers auto-discover the active-job list from BT's job-picker
// API, so a brand-new job (e.g. "Clark") is pulled the moment it's created in
// BT — nothing in this route or the cockpit needs to be edited per job. The
// hardcoded JOB_NAME_MAP in the scraper repo is only used to validate the
// optional `--jobs` CLI arg, which this route NEVER passes.
//
// The response is an NDJSON stream (one JSON object per line) so the modal can
// render a live, per-step progress UI. Final line is { kind: "done", ... }.
//
// Local-only: shells out to Python + Playwright, so it refuses on Vercel.

import { NextRequest } from "next/server";
import { spawn } from "child_process";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // informational — route refuses on VERCEL=1

// Per-step child-process kill timers. Generous; BT can be slow.
const DAILY_TIMEOUT_SEC = 1500; // ~25 min — 36 active jobs + photo downloads
const PO_TIMEOUT_SEC = 2700; // ~45 min — ~1,200 POs × 1 line-items request each
const CO_TIMEOUT_SEC = 600; // ~10 min — grid call per job, no line-item drill-down

const DEFAULT_SCRAPER_DIR = "C:\\Users\\Greg\\buildertrend-scraper";

interface SyncBody {
  username?: string;
  password?: string;
  headed?: boolean;
}

type StepName = "daily-logs" | "purchase-orders" | "change-orders";

interface StepStartEvent {
  kind: "step:start";
  step: StepName;
  label: string;
}
interface StepDoneEvent {
  kind: "step:done";
  step: StepName;
  ok: boolean;
  elapsedMs: number;
  scrape: {
    jobCount: number;
    logCount?: number;
    photoCount?: number;
    poCount?: number;
    lineItemCount?: number;
    coCount?: number;
  };
  upload: Record<string, unknown>;
  vision?: { considered?: number; processed?: number; failed?: number } | null;
  error?: string;
  stderrTail?: string;
}
interface DoneEvent {
  kind: "done";
  ok: boolean;
  elapsedMs: number;
}
interface ErrorEvent {
  kind: "error";
  error: string;
}
type Event = StepStartEvent | StepDoneEvent | DoneEvent | ErrorEvent;

function redact(text: string, password: string): string {
  if (!password) return text;
  return text.split(password).join("[redacted-password]");
}

async function runChild(
  pythonExe: string,
  scriptPath: string,
  args: string[],
  scraperDir: string,
  username: string,
  password: string,
  timeoutSec: number,
): Promise<{ exitCode: number; stdout: string; stderr: string; elapsedMs: number }> {
  const startedAt = Date.now();
  let stdoutBuf = "";
  let stderrBuf = "";

  const proc = spawn(pythonExe, [scriptPath, ...args], {
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
  }, timeoutSec * 1000);

  const exitCode: number = await new Promise((resolve) => {
    proc.on("close", (code) => resolve(code ?? -1));
    proc.on("error", () => resolve(-1));
  });
  clearTimeout(killTimer);

  return {
    exitCode,
    stdout: stdoutBuf,
    stderr: stderrBuf,
    elapsedMs: Date.now() - startedAt,
  };
}

export async function POST(req: NextRequest) {
  const encoder = new TextEncoder();

  // For very-early errors (bad body, Vercel, missing scraper) we don't need
  // a stream — just return a single-line NDJSON payload so the client can use
  // the same parser everywhere.
  function singleLine(event: Event, status = 400): Response {
    return new Response(JSON.stringify(event) + "\n", {
      status,
      headers: { "Content-Type": "application/x-ndjson" },
    });
  }

  if (process.env.VERCEL === "1") {
    return singleLine({
      kind: "error",
      error:
        "Buildertrend sync requires a local environment (spawns Python + Playwright). " +
        "Run `npm run dev` on your laptop and use the button there.",
    });
  }

  let body: SyncBody = {};
  try {
    body = (await req.json()) as SyncBody;
  } catch {
    return singleLine({ kind: "error", error: "Invalid JSON body" });
  }

  const username = body.username?.trim();
  const password = body.password ?? "";
  if (!username || !password) {
    return singleLine({ kind: "error", error: "username and password required" });
  }

  const scraperDir = process.env.BT_SCRAPER_DIR || DEFAULT_SCRAPER_DIR;
  const pythonExe = path.join(scraperDir, ".venv", "Scripts", "python.exe");
  const scrapeApi = path.join(scraperDir, "scrape_api.py");
  const scrapePo = path.join(scraperDir, "scrape_po.py");
  const scrapeCo = path.join(scraperDir, "scrape_co.py");
  const dailyOutput = path.join(scraperDir, "data", "daily-logs.json");
  const poOutput = path.join(scraperDir, "data", "purchase-orders.json");
  const coOutput = path.join(scraperDir, "data", "change-orders.json");

  for (const f of [pythonExe, scrapeApi, scrapePo, scrapeCo]) {
    try {
      await fs.access(f);
    } catch {
      return singleLine({
        kind: "error",
        error: `Scraper missing: ${f}. Set BT_SCRAPER_DIR if it lives elsewhere, or follow the buildertrend-scraper README to set up the venv.`,
      });
    }
  }

  const origin = req.nextUrl.origin;
  const overallStart = Date.now();
  const headed = body.headed === true;

  // Wipe the credential from this request's outer scope as soon as we no
  // longer need it (just before we close the stream).
  // The closures below capture the local `username`/`password` values.
  const stream = new ReadableStream({
    async start(controller) {
      function send(event: Event) {
        controller.enqueue(encoder.encode(JSON.stringify(event) + "\n"));
      }

      let overallOk = true;

      // ─── Step 1: Daily logs ─────────────────────────────────────────
      send({ kind: "step:start", step: "daily-logs", label: "Pulling daily logs" });

      const dailyArgs: string[] = ["--days", "14", "--max-photos-per-log", "6", "-v"];
      if (headed) dailyArgs.push("--headed");

      const dailyRun = await runChild(
        pythonExe,
        scrapeApi,
        dailyArgs,
        scraperDir,
        username,
        password,
        DAILY_TIMEOUT_SEC,
      );
      const dailyStderrTail = redact(dailyRun.stderr.slice(-3000), password);

      const dailyStep: StepDoneEvent = {
        kind: "step:done",
        step: "daily-logs",
        ok: dailyRun.exitCode === 0,
        elapsedMs: dailyRun.elapsedMs,
        scrape: { jobCount: 0, logCount: 0, photoCount: 0 },
        upload: {},
        vision: null,
        stderrTail: dailyStderrTail,
      };

      if (dailyRun.exitCode !== 0) {
        dailyStep.error = `scrape_api.py exited ${dailyRun.exitCode} after ${Math.round(dailyRun.elapsedMs / 1000)}s`;
        overallOk = false;
        send(dailyStep);
      } else {
        try {
          const raw = await fs.readFile(dailyOutput, "utf-8");
          const payload = JSON.parse(raw) as { byJob?: Record<string, unknown[]> };
          const byJob = payload.byJob ?? {};
          dailyStep.scrape.jobCount = Object.keys(byJob).length;
          for (const rows of Object.values(byJob)) {
            if (!Array.isArray(rows)) continue;
            dailyStep.scrape.logCount! += rows.length;
            for (const r of rows) {
              const arr = (r as { photo_urls?: unknown[] })?.photo_urls;
              if (Array.isArray(arr)) dailyStep.scrape.photoCount! += arr.length;
            }
          }

          const upR = await fetch(`${origin}/v2/api/daily-logs/upload`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source: "cockpit-bt-sync-all", payload }),
          });
          dailyStep.upload = (await upR.json().catch(() => ({}))) as Record<string, unknown>;
          if (!upR.ok) {
            dailyStep.ok = false;
            dailyStep.error = `daily-logs upload returned ${upR.status}`;
            overallOk = false;
          }

          // Vision pass — best-effort. A vision failure shouldn't fail the step.
          if (dailyStep.ok) {
            try {
              const vR = await fetch(`${origin}/v2/api/daily-logs/extract-photos`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ limit: 30 }),
              });
              if (vR.ok) {
                dailyStep.vision = (await vR.json().catch(() => null)) as StepDoneEvent["vision"];
              }
            } catch {
              // ignore
            }
          }
        } catch (e) {
          dailyStep.ok = false;
          dailyStep.error = `daily-logs post-scrape failed: ${e instanceof Error ? e.message : String(e)}`;
          overallOk = false;
        }
        send(dailyStep);
      }

      // ─── Step 2: Purchase orders (all jobs, with line items) ────────
      send({
        kind: "step:start",
        step: "purchase-orders",
        label: "Pulling purchase orders (line items included)",
      });

      const poArgs: string[] = ["-v"];
      if (headed) poArgs.push("--headed");

      const poRun = await runChild(
        pythonExe,
        scrapePo,
        poArgs,
        scraperDir,
        username,
        password,
        PO_TIMEOUT_SEC,
      );
      const poStderrTail = redact(poRun.stderr.slice(-3000), password);

      const poStep: StepDoneEvent = {
        kind: "step:done",
        step: "purchase-orders",
        ok: poRun.exitCode === 0,
        elapsedMs: poRun.elapsedMs,
        scrape: { jobCount: 0, poCount: 0, lineItemCount: 0 },
        upload: {},
        stderrTail: poStderrTail,
      };

      if (poRun.exitCode !== 0) {
        poStep.error = `scrape_po.py exited ${poRun.exitCode} after ${Math.round(poRun.elapsedMs / 1000)}s`;
        overallOk = false;
        send(poStep);
      } else {
        try {
          const raw = await fs.readFile(poOutput, "utf-8");
          const payload = JSON.parse(raw) as { byJob?: Record<string, unknown[]> };
          const byJob = payload.byJob ?? {};
          poStep.scrape.jobCount = Object.keys(byJob).length;
          for (const rows of Object.values(byJob)) {
            if (!Array.isArray(rows)) continue;
            poStep.scrape.poCount! += rows.length;
            for (const po of rows) {
              const li = (po as { line_items?: unknown[] })?.line_items;
              if (Array.isArray(li)) poStep.scrape.lineItemCount! += li.length;
            }
          }

          const upR = await fetch(`${origin}/v2/api/purchase-orders/upload`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ payload, skipLineItems: false }),
          });
          poStep.upload = (await upR.json().catch(() => ({}))) as Record<string, unknown>;
          if (!upR.ok) {
            poStep.ok = false;
            poStep.error = `PO upload returned ${upR.status}`;
            overallOk = false;
          }
        } catch (e) {
          poStep.ok = false;
          poStep.error = `PO post-scrape failed: ${e instanceof Error ? e.message : String(e)}`;
          overallOk = false;
        }
        send(poStep);
      }

      // ─── Step 3: Change orders (all jobs) ───────────────────────────
      send({
        kind: "step:start",
        step: "change-orders",
        label: "Pulling change orders",
      });

      const coArgs: string[] = ["-v"];
      if (headed) coArgs.push("--headed");

      const coRun = await runChild(
        pythonExe,
        scrapeCo,
        coArgs,
        scraperDir,
        username,
        password,
        CO_TIMEOUT_SEC,
      );
      const coStderrTail = redact(coRun.stderr.slice(-3000), password);

      const coStep: StepDoneEvent = {
        kind: "step:done",
        step: "change-orders",
        ok: coRun.exitCode === 0,
        elapsedMs: coRun.elapsedMs,
        scrape: { jobCount: 0, coCount: 0 },
        upload: {},
        stderrTail: coStderrTail,
      };

      if (coRun.exitCode !== 0) {
        coStep.error = `scrape_co.py exited ${coRun.exitCode} after ${Math.round(coRun.elapsedMs / 1000)}s`;
        overallOk = false;
        send(coStep);
      } else {
        try {
          const raw = await fs.readFile(coOutput, "utf-8");
          const payload = JSON.parse(raw) as { byJob?: Record<string, unknown[]> };
          const byJob = payload.byJob ?? {};
          coStep.scrape.jobCount = Object.keys(byJob).length;
          for (const rows of Object.values(byJob)) {
            if (!Array.isArray(rows)) continue;
            coStep.scrape.coCount! += rows.length;
          }

          const upR = await fetch(`${origin}/v2/api/change-orders/upload`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ payload }),
          });
          coStep.upload = (await upR.json().catch(() => ({}))) as Record<string, unknown>;
          if (!upR.ok) {
            coStep.ok = false;
            coStep.error = `CO upload returned ${upR.status}`;
            overallOk = false;
          }
        } catch (e) {
          coStep.ok = false;
          coStep.error = `CO post-scrape failed: ${e instanceof Error ? e.message : String(e)}`;
          overallOk = false;
        }
        send(coStep);
      }

      send({ kind: "done", ok: overallOk, elapsedMs: Date.now() - overallStart });
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson",
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
    },
  });
}
