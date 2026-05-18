import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { PM } from "@/lib/types";
import { Header } from "@/components/header";
import { ImportForm } from "@/components/import-form";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const supabase = supabaseServer();
  const [pmsRes, jobsRes, assignRes] = await Promise.all([
    supabase
      .from("pms")
      .select("id, full_name, active")
      .eq("active", true)
      .order("full_name"),
    supabase.from("jobs").select("id, name").order("name"),
    supabase
      .from("job_pm_assignments")
      .select("job_id, pm_id")
      .is("ended_at", null),
  ]);
  const pms = (pmsRes.data ?? []) as PM[];
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background">
      <Header />
      <div className="px-5 pt-8">
        <Link
          href="/"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Back
        </Link>
        <h1 className="mt-4 font-head text-[28px] leading-none tracking-tight text-foreground">
          Import transcript
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Drop a Plaud .txt — PM, job, date, and meeting type auto-fill from the
          filename.
        </p>
      </div>
      <ImportForm pms={pms} jobs={jobs} assignments={assignments} />
    </main>
  );
}
