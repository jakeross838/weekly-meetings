// /v2/upload — Jake-only transcript drop.
//
// Reads jobs + pms server-side, renders a form. Client component handles
// the file upload + POST to /v2/api/upload.

import { supabaseServer } from "@/lib/supabase";
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
    <main className="max-w-[480px] lg:max-w-[640px] mx-auto min-h-screen bg-background pb-24">
      <header className="px-5 pt-10 pb-6 border-b border-rule">
        <h1 className="font-head text-[28px] lg:text-[32px] leading-none tracking-tight text-foreground">
          Drop a transcript
        </h1>
        <p className="mt-2 text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">
          Jake-only · v1
        </p>
      </header>

      <div className="px-5 pt-8">
        <UploadForm jobs={jobs} pms={pms} assignments={assignments} />
        <p className="mt-8 text-ink-3 text-xs">
          On submit, the transcript is saved to the database. The brain pipeline
          (Extractor → Reconciler) currently runs separately as a Python job —
          a queued upload appears at <span className="font-mono">/v2/review</span>
          once processing completes (manual trigger for v1).
        </p>
      </div>
    </main>
  );
}
