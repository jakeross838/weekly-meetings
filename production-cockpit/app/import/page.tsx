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
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Import transcript
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Drop a Plaud .txt — Claude extracts action items and writes them
          straight to the to-do tables.
        </p>
        <p className="mt-2 text-xs text-ink-3">
          For the v2 review pipeline (extract → review → commit), use{" "}
          <Link href="/v2/upload" className="text-accent hover:underline">
            /v2/upload
          </Link>{" "}
          instead.
        </p>
      </div>
      <ImportForm pms={pms} jobs={jobs} assignments={assignments} />
    </main>
  );
}
