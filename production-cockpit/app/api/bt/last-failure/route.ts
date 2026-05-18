// GET /api/bt/last-failure
// Returns the contents of $BT_SCRAPER_DIR/.session/last-failure.log so
// the operator (or Claude when debugging) can read the most recent
// scraper stderr/stdout tail without copy-pasting from the modal.
//
// Returns 404 if there's no last-failure dump (which is the happy path —
// no failures have happened yet).

import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

const DEFAULT_SCRAPER_DIR = "C:\\Users\\Greg\\buildertrend-scraper";

export async function GET() {
  const scraperDir = process.env.BT_SCRAPER_DIR || DEFAULT_SCRAPER_DIR;
  const dumpPath = path.join(scraperDir, ".session", "last-failure.log");
  try {
    const contents = await fs.readFile(dumpPath, "utf-8");
    const stat = await fs.stat(dumpPath);
    return NextResponse.json({
      ok: true,
      path: dumpPath,
      writtenAt: stat.mtime.toISOString(),
      contents,
    });
  } catch (e) {
    return NextResponse.json(
      {
        ok: false,
        error: "no last-failure log",
        detail: e instanceof Error ? e.message : String(e),
        expectedPath: dumpPath,
      },
      { status: 404 }
    );
  }
}
