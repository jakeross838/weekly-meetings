// /admin/users — admin-only panel for managing PM job access.
// Lists every user (seed + overlay), shows which jobs they can see, and lets
// the admin toggle access per job or add a brand-new PM user. All writes go
// through /api/admin/users which persists to data/user-overlay.json.

import { Header } from "@/components/header";
import { supabaseServer } from "@/lib/supabase";
import { currentUser, isAdmin } from "@/lib/auth";
import { getAllUsersIncludingDisabled } from "@/lib/user-store";
import { redirect, notFound } from "next/navigation";
import { UsersAdminClient } from "./users-admin-client";

export const dynamic = "force-dynamic";

export default async function AdminUsersPage() {
  const user = await currentUser();
  if (!user) redirect("/login?next=/admin/users");
  if (!isAdmin(user)) notFound();

  const supabase = supabaseServer();
  const [jobsRes, pmsRes, signupsRes] = await Promise.all([
    supabase.from("jobs").select("id, name, pm_id").order("name"),
    supabase.from("pms").select("id, full_name").order("full_name"),
    supabase
      .from("signup_requests")
      .select("id, email, name, message, created_at")
      .eq("status", "pending")
      .order("created_at", { ascending: false }),
  ]);
  const jobs = (jobsRes.data ?? []) as {
    id: string;
    name: string;
    pm_id: string | null;
  }[];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];
  const pendingSignups = (signupsRes.data ?? []) as {
    id: string;
    email: string;
    name: string;
    message: string | null;
    created_at: string;
  }[];
  const users = await getAllUsersIncludingDisabled();

  return (
    <main className="max-w-[720px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          User access
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Each PM only sees their own jobs. Click a job to assign or
          re-assign it. Reset a password, disable an account, or grant admin
          inline — changes persist immediately.
        </p>
      </div>

      <UsersAdminClient
        users={users}
        jobs={jobs}
        pms={pms}
        selfEmail={user.email}
        pendingSignups={pendingSignups}
      />
    </main>
  );
}
