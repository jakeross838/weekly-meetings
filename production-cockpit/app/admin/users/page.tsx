// /admin/users — admin-only panel for managing PM job access.
// Lists every user (seed + overlay), shows which jobs they can see, and lets
// the admin toggle access per job or add a brand-new PM user. All writes go
// through /api/admin/users which persists to data/user-overlay.json.

import { Header } from "@/components/header";
import { supabaseServer } from "@/lib/supabase";
import { currentUser, isAdmin } from "@/lib/auth";
import { getAllUsers } from "@/lib/user-store";
import { redirect, notFound } from "next/navigation";
import { UsersAdminClient } from "./users-admin-client";

export const dynamic = "force-dynamic";

export default async function AdminUsersPage() {
  const user = currentUser();
  if (!user) redirect("/login?next=/admin/users");
  if (!isAdmin(user)) notFound();

  const supabase = supabaseServer();
  const [jobsRes, pmsRes] = await Promise.all([
    supabase.from("jobs").select("id, name").order("name"),
    supabase.from("pms").select("id, full_name").order("full_name"),
  ]);
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];
  const users = getAllUsers();

  return (
    <main className="max-w-[720px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          User access
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Each PM only sees their own jobs. Toggle access per user, or add a
          new PM. Changes persist immediately.
        </p>
      </div>

      <UsersAdminClient users={users} jobs={jobs} pms={pms} />
    </main>
  );
}
