// /v2/daily-logs/upload — drop a Buildertrend daily-log JSON file.
// Server component renders the form; client handles the file read + POST.

import Link from "next/link";
import { Header } from "@/components/header";
import { DailyLogUploadForm } from "./upload-form";

export const dynamic = "force-dynamic";

export default function DailyLogUploadPage() {
  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Drop a daily log
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Buildertrend scraper JSON — populates the no-show tracking on{" "}
          <Link href="/subs" className="text-accent hover:underline">
            /subs
          </Link>
          .
        </p>
        <p className="mt-2 text-xs text-ink-3">
          Expected shape:{" "}
          <span className="font-mono">{`{ byJob: { jobKey: [...] } }`}</span>.
          Rows dedupe by (job_key, logId).
        </p>
      </div>

      <div className="px-5 pt-6">
        <DailyLogUploadForm />
      </div>
    </main>
  );
}
