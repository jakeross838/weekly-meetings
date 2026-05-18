// /v2/upload — Jake-only transcript drop.
//
// Reads jobs + pms server-side, renders a form. Client component handles
// the file upload + POST to /v2/api/upload.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Header } from "@/components/header";
import { UploadForm } from "./upload-form";

export const dynamic = "force-dynamic";

export default async function UploadPage() {
  const supabase = supabaseServer();
  const [jobsRes, pmsRes, assignRes] = await Promise.all([
    supabase.from("jobs").select("id, name").order("name"),
    supabase.from("pms").select("id, full_name").eq("active", true).order("full_name"),
    supabase.from("job_pm_assignments").select("job_id, pm_id").is("ended_at", null),
  ]);

  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];
  const assignments = (assignRes.data ?? []) as { job_id: string; pm_id: string }[];

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Drop a transcript
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          v2 review pipeline · queues the meeting for the brain to extract,
          then you review and commit at{" "}
          <Link href="/v2/review" className="text-accent hover:underline">
            /v2/review
          </Link>
          .
        </p>
        <p className="mt-2 text-xs text-ink-3">
          For the direct v1 extract (writes straight to to-dos), use{" "}
          <Link href="/import" className="text-accent hover:underline">
            /import
          </Link>
          .
        </p>
      </div>

      <div className="px-5 pt-6">
        <UploadForm jobs={jobs} pms={pms} assignments={assignments} />
        <p className="mt-8 text-ink-3 text-xs">
          On submit the transcript is saved. The brain pipeline (Extractor →
          Reconciler) runs separately as a Python job — a queued upload appears
          at <span className="font-mono">/v2/review</span> once processing
          completes (manual trigger for v1).
        </p>
      </div>
    </main>
  );
}
