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
import os from "os";
import { supabaseServer } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // informational — route refuses on VERCEL=1

// Module-level single-run lock. Avoids the chaos of two unified pulls
// fighting over the same BT session (state.json) and spawning competing
// Playwright instances. A second click while a run is in progress returns
// a clear error event instead of starting a parallel scrape.
let RUN_IN_PROGRESS = false;

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
interface StepProgressEvent {
  kind: "step:progress";
  step: StepName;
  message: string;
  jobsDone?: number;
  jobsTotal?: number;
}
type Event = StepStartEvent | StepProgressEvent | StepDoneEvent | DoneEvent | ErrorEvent;

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
  onStderrLine?: (line: string) => void,
): Promise<{ exitCode: number; stdout: string; stderr: string; elapsedMs: number }> {
  const startedAt = Date.now();
  let stdoutBuf = "";
  let stderrBuf = "";
  let stderrLineBuf = "";

  const proc = spawn(pythonExe, [scriptPath, ...args], {
    cwd: scraperDir,
    env: {
      ...process.env,
      BT_USERNAME: username,
      BT_PASSWORD: password,
      PYTHONIOENCODING: "utf-8",
      // Force unbuffered stdio so the per-job [INFO] lines arrive
      // immediately. Without this, Python block-buffers stderr when it's a
      // pipe (which it is here) and the modal would only see progress at
      // ~8KB intervals — defeating the live progress UI.
      PYTHONUNBUFFERED: "1",
    },
    shell: false,
  });

  proc.stdout.on("data", (chunk: Buffer) => {
    stdoutBuf += chunk.toString("utf-8");
  });
  proc.stderr.on("data", (chunk: Buffer) => {
    const s = chunk.toString("utf-8");
    stderrBuf += s;
    if (!onStderrLine) return;
    stderrLineBuf += s;
    let nl: number;
    while ((nl = stderrLineBuf.indexOf("\n")) >= 0) {
      const line = stderrLineBuf.slice(0, nl).replace(/\r$/, "");
      stderrLineBuf = stderrLineBuf.slice(nl + 1);
      try { onStderrLine(line); } catch { /* ignore */ }
    }
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

  if (RUN_IN_PROGRESS) {
    return singleLine({
      kind: "error",
      error:
        "A BT sync is already in progress. Wait for it to finish, then click again. " +
        "(Two concurrent pulls fight over the same BT session and corrupt state.)",
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
  RUN_IN_PROGRESS = true;
  const stream = new ReadableStream({
    async start(controller) {
      function send(event: Event) {
        controller.enqueue(encoder.encode(JSON.stringify(event) + "\n"));
      }
      // Mirror every stream event to the dev-server console so we can see in
      // the terminal what's happening on each step without screen-recording
      // the modal.
      function log(...parts: unknown[]) {
        const t = Math.round((Date.now() - overallStart) / 1000);
        console.log(`[bt/sync-all +${t}s]`, ...parts);
      }

      let overallOk = true;

      // Write a per-step failure dump for any non-zero scraper exit, mirroring
      // the standalone routes. Lets us diagnose what BT replied with even
      // after the modal closes / the stream ends.
      async function dumpFailure(step: StepName, exitCode: number, elapsedSec: number, stderrTail: string, stdoutTail: string) {
        try {
          const fname = `last-failure-${step}.log`;
          const dumpPath = path.join(scraperDir, ".session", fname);
          await fs.mkdir(path.dirname(dumpPath), { recursive: true });
          await fs.writeFile(
            dumpPath,
            `=== BT ${step} sync-all failure ${new Date().toISOString()} ===\n` +
              `exit=${exitCode} elapsed=${elapsedSec}s\n\n` +
              `--- stderr ---\n${stderrTail}\n\n--- stdout ---\n${stdoutTail}\n`,
            "utf-8",
          );
          console.error(`[bt/sync-all] ${step} failed (exit ${exitCode}). dump at ${dumpPath}`);
        } catch (e) {
          console.error("[bt/sync-all] failed to write step failure dump:", e);
        }
      }

      // ─── Step 1: Daily logs ─────────────────────────────────────────
      // Incremental: ask Supabase for the most recent log date we have, then
      // tell the scraper to only pull logs on/after that day (minus a 2-day
      // grace window to catch late edits). First run on an empty DB falls
      // back to 14 days. We cap photos per log at 20 — plenty of context
      // without letting one busy log dominate the whole run with sequential
      // photo downloads (unlimited * 50 logs * ~25 photos = ~20min just on
      // photos and was starving the PO/CO steps).
      let dailySince = "";
      try {
        const sb = supabaseServer();
        // DB column is log_date (the date the log was filed in BT), not date.
        // The upload route writes `log_date: parseLogDate(r.date)`.
        const { data, error } = await sb
          .from("daily_logs")
          .select("log_date")
          .order("log_date", { ascending: false, nullsFirst: false })
          .limit(1);
        if (error) {
          console.error("[bt/sync-all] max(log_date) query failed:", error.message);
        }
        const maxDate = (data?.[0] as { log_date?: string } | undefined)?.log_date ?? null;
        if (maxDate) {
          const d = new Date(maxDate + "T00:00:00Z");
          d.setUTCDate(d.getUTCDate() - 2);
          dailySince = d.toISOString().slice(0, 10);
        }
      } catch (e) {
        console.error("[bt/sync-all] dailySince lookup threw:", e);
      }

      send({
        kind: "step:start",
        step: "daily-logs",
        label: dailySince
          ? `Pulling daily logs since ${dailySince}`
          : "Pulling daily logs (last 14 days)",
      });

      const dailyArgs: string[] = ["--max-photos-per-log", "10", "-v"];
      if (dailySince) {
        dailyArgs.push("--since", dailySince);
      } else {
        dailyArgs.push("--days", "14");
      }
      if (headed) dailyArgs.push("--headed");
      log("daily-logs: starting", { since: dailySince || "(--days 14 fallback)" });

      // Parse scrape_api.py stderr lines in real time so the modal can show
      // per-job progress instead of a 10-min silent spinner.
      //   "Scraping ALL N real active jobs"                     -> jobsTotal=N
      //   "Bedi-...: 0 logs since 2026-05-25"                    -> progress tick
      let dailyJobsDone = 0;
      let dailyJobsTotal = 0;
      const onDailyLine = (line: string) => {
        const m1 = line.match(/Scraping ALL (\d+) real active jobs/);
        if (m1) {
          dailyJobsTotal = parseInt(m1[1], 10);
          send({
            kind: "step:progress",
            step: "daily-logs",
            message: `Discovered ${dailyJobsTotal} active jobs in BT`,
            jobsTotal: dailyJobsTotal,
          });
          return;
        }
        const m2 = line.match(/\[INFO\] __main__: (.+?): (\d+) logs since/);
        if (m2) {
          dailyJobsDone += 1;
          send({
            kind: "step:progress",
            step: "daily-logs",
            message: `${m2[1]} · ${m2[2]} log${m2[2] === "1" ? "" : "s"}`,
            jobsDone: dailyJobsDone,
            jobsTotal: dailyJobsTotal || undefined,
          });
        }
      };

      const dailyRun = await runChild(
        pythonExe,
        scrapeApi,
        dailyArgs,
        scraperDir,
        username,
        password,
        DAILY_TIMEOUT_SEC,
        onDailyLine,
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

      log("daily-logs: scrape exit", {
        code: dailyRun.exitCode,
        elapsedSec: Math.round(dailyRun.elapsedMs / 1000),
        stderrTailFirst300: dailyStderrTail.slice(0, 300),
      });

      if (dailyRun.exitCode !== 0) {
        dailyStep.error = `scrape_api.py exited ${dailyRun.exitCode} after ${Math.round(dailyRun.elapsedMs / 1000)}s`;
        overallOk = false;
        await dumpFailure("daily-logs", dailyRun.exitCode, Math.round(dailyRun.elapsedMs / 1000), dailyStderrTail, redact(dailyRun.stdout.slice(-3000), password));
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

          // Vision pass — loop until every new photo has a summary or we hit
          // a safety cap. Each extract-photos call processes a batch; we keep
          // calling it until `considered` comes back 0 (or the cap trips).
          if (dailyStep.ok) {
            let visionLoops = 0;
            const MAX_LOOPS = 50; // 50 × ~30 photos ≈ 1,500 photos / run
            let cumProcessed = 0;
            let cumFailed = 0;
            let cumConsidered = 0;
            while (visionLoops < MAX_LOOPS) {
              try {
                const vR = await fetch(`${origin}/v2/api/daily-logs/extract-photos`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ limit: 30 }),
                });
                if (!vR.ok) break;
                const v = (await vR.json().catch(() => null)) as {
                  considered?: number;
                  processed?: number;
                  failed?: number;
                } | null;
                if (!v) break;
                cumConsidered += v.considered ?? 0;
                cumProcessed += v.processed ?? 0;
                cumFailed += v.failed ?? 0;
                visionLoops++;
                // No more photos to consider → done.
                if ((v.considered ?? 0) === 0) break;
                // Made no progress on this batch → avoid infinite loop.
                if ((v.processed ?? 0) === 0 && (v.failed ?? 0) === 0) break;
              } catch {
                break;
              }
            }
            dailyStep.vision = {
              considered: cumConsidered,
              processed: cumProcessed,
              failed: cumFailed,
            };
          }
        } catch (e) {
          dailyStep.ok = false;
          dailyStep.error = `daily-logs post-scrape failed: ${e instanceof Error ? e.message : String(e)}`;
          overallOk = false;
        }
        send(dailyStep);
      }

      // ─── Step 2: Purchase orders (all jobs, with line items) ────────
      // Incremental: collect bt_po_ids for which we already have ≥1 line
      // item in Supabase. The scraper will pull the grid (PO totals) for
      // every job, but skip the slow per-PO line-items fetch for IDs in
      // this set — making repeat pulls fast while still grabbing line
      // items for brand-new POs the first time we see them.
      let knownPoIdsPath = "";
      let knownPoCount = 0;
      try {
        const sb = supabaseServer();
        // 1) collect po_ids that have at least one line item already
        const { data: liData } = await sb
          .from("po_line_items")
          .select("po_id")
          .limit(50000);
        const poIdsWithLines = new Set<string>();
        for (const r of (liData ?? []) as { po_id: string | null }[]) {
          if (r.po_id) poIdsWithLines.add(r.po_id);
        }
        // 2) resolve those internal po_ids to bt_po_ids
        const idSet = new Set<number>();
        const idsArr = Array.from(poIdsWithLines);
        for (let i = 0; i < idsArr.length; i += 500) {
          const chunk = idsArr.slice(i, i + 500);
          const { data: poData } = await sb
            .from("purchase_orders")
            .select("bt_po_id")
            .in("id", chunk);
          for (const r of (poData ?? []) as { bt_po_id: number | null }[]) {
            if (typeof r.bt_po_id === "number") idSet.add(r.bt_po_id);
          }
        }
        if (idSet.size > 0) {
          knownPoIdsPath = path.join(
            os.tmpdir(),
            `bt-known-po-ids-${process.pid}-${Date.now()}.txt`,
          );
          await fs.writeFile(knownPoIdsPath, Array.from(idSet).join("\n"), "utf-8");
          knownPoCount = idSet.size;
        }
      } catch {
        // ignore — fall through to a full pull
      }

      send({
        kind: "step:start",
        step: "purchase-orders",
        label: knownPoCount
          ? `Pulling purchase orders (line items only for new POs — ${knownPoCount} already cached)`
          : "Pulling purchase orders (line items for every PO — first run)",
      });

      const poArgs: string[] = ["-v"];
      if (knownPoIdsPath) poArgs.push("--known-po-ids-file", knownPoIdsPath);
      if (headed) poArgs.push("--headed");

      log("purchase-orders: starting", { knownPoCount, knownPoIdsPath });

      // Per-job progress parser for scrape_po.py — matches lines like:
      //   "Found N active jobs"
      //   "Krauss-...: 23 POs · 145 line items"
      //   "Krauss-...: 23 POs"   (when --skip-line-items)
      let poJobsDone = 0;
      let poJobsTotal = 0;
      const onPoLine = (line: string) => {
        const m1 = line.match(/Found (\d+) active jobs/);
        if (m1) {
          poJobsTotal = parseInt(m1[1], 10);
          send({
            kind: "step:progress",
            step: "purchase-orders",
            message: `Found ${poJobsTotal} active jobs · scanning POs`,
            jobsTotal: poJobsTotal,
          });
          return;
        }
        const m2 = line.match(/\[INFO\] __main__: (.+?): (\d+) POs(?: · (\d+) line items)?/);
        if (m2) {
          poJobsDone += 1;
          const li = m2[3] ? ` · ${m2[3]} line items` : "";
          send({
            kind: "step:progress",
            step: "purchase-orders",
            message: `${m2[1]} · ${m2[2]} PO${m2[2] === "1" ? "" : "s"}${li}`,
            jobsDone: poJobsDone,
            jobsTotal: poJobsTotal || undefined,
          });
          return;
        }
        // Parallel line-item heartbeat from the 2-pass scraper. Lets the
        // modal show "Line items: 150 / 1180 POs" instead of a frozen
        // counter while the per-job loop has already finished but parallel
        // fetches are still in flight.
        const m3 = line.match(/\[INFO\] __main__: Line items: (\d+) \/ (\d+) POs/);
        if (m3) {
          send({
            kind: "step:progress",
            step: "purchase-orders",
            message: `Fetching line items in parallel · ${m3[1]} / ${m3[2]} POs`,
          });
          return;
        }
        const m4 = line.match(/Fetching line items for (\d+) POs in parallel/);
        if (m4) {
          send({
            kind: "step:progress",
            step: "purchase-orders",
            message: `Pass 2: parallel-fetching ${m4[1]} new POs' line items`,
          });
        }
      };

      const poRun = await runChild(
        pythonExe,
        scrapePo,
        poArgs,
        scraperDir,
        username,
        password,
        PO_TIMEOUT_SEC,
        onPoLine,
      );
      const poStderrTail = redact(poRun.stderr.slice(-3000), password);
      log("purchase-orders: scrape exit", {
        code: poRun.exitCode,
        elapsedSec: Math.round(poRun.elapsedMs / 1000),
        stderrTailFirst300: poStderrTail.slice(0, 300),
      });

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
        await dumpFailure("purchase-orders", poRun.exitCode, Math.round(poRun.elapsedMs / 1000), poStderrTail, redact(poRun.stdout.slice(-3000), password));
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

      log("change-orders: starting");

      // Per-job progress for scrape_co.py — matches "<JobName>: N change orders"
      let coJobsDone = 0;
      let coJobsTotal = 0;
      const onCoLine = (line: string) => {
        const m1 = line.match(/Found (\d+) active jobs/);
        if (m1) {
          coJobsTotal = parseInt(m1[1], 10);
          send({
            kind: "step:progress",
            step: "change-orders",
            message: `Found ${coJobsTotal} active jobs · scanning COs`,
            jobsTotal: coJobsTotal,
          });
          return;
        }
        const m2 = line.match(/\[INFO\] __main__: (.+?): (\d+) change orders?/);
        if (m2) {
          coJobsDone += 1;
          send({
            kind: "step:progress",
            step: "change-orders",
            message: `${m2[1]} · ${m2[2]} change order${m2[2] === "1" ? "" : "s"}`,
            jobsDone: coJobsDone,
            jobsTotal: coJobsTotal || undefined,
          });
        }
      };

      const coRun = await runChild(
        pythonExe,
        scrapeCo,
        coArgs,
        scraperDir,
        username,
        password,
        CO_TIMEOUT_SEC,
        onCoLine,
      );
      const coStderrTail = redact(coRun.stderr.slice(-3000), password);
      log("change-orders: scrape exit", {
        code: coRun.exitCode,
        elapsedSec: Math.round(coRun.elapsedMs / 1000),
        stderrTailFirst300: coStderrTail.slice(0, 300),
      });

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
        await dumpFailure("change-orders", coRun.exitCode, Math.round(coRun.elapsedMs / 1000), coStderrTail, redact(coRun.stdout.slice(-3000), password));
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

      log("DONE", { overallOk, elapsedSec: Math.round((Date.now() - overallStart) / 1000) });
      send({ kind: "done", ok: overallOk, elapsedMs: Date.now() - overallStart });
      controller.close();
      RUN_IN_PROGRESS = false;
    },
    cancel() {
      // Client disconnected mid-stream. Release the lock so future clicks
      // aren't permanently blocked.
      RUN_IN_PROGRESS = false;
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
