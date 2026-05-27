// /admin/jobs — admin-only CRUD for the `jobs` table.

import { Header } from "@/components/header";
import { supabaseServer } from "@/lib/supabase";
import { currentUser, isAdmin } from "@/lib/auth";
import { redirect, notFound } from "next/navigation";
import { JobsAdminClient } from "./jobs-admin-client";

export const dynamic = "force-dynamic";

export default async function AdminJobsPage() {
  const user = await currentUser();
  if (!user) redirect("/login?next=/admin/jobs");
  if (!isAdmin(user)) notFound();

  const sb = supabaseServer();
  const [jobsRes, pmsRes] = await Promise.all([
    sb.from("jobs").select("id, name, address, pm_id, status").order("name"),
    sb.from("pms").select("id, full_name").order("full_name"),
  ]);
  const jobs = (jobsRes.data ?? []) as {
    id: string;
    name: string | null;
    address: string | null;
    pm_id: string | null;
    status: string | null;
  }[];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];

  return (
    <main className="max-w-[720px] mx-auto min-h-screen bg-background pb-24">
      <Header />
      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Jobs
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Add new jobs to the portfolio, rename, reassign PM, or remove. Use a
          short slug for the id (e.g. <span className="font-mono">krauss</span>).
        </p>
      </div>
      <JobsAdminClient jobs={jobs} pms={pms} />
    </main>
  );
}
