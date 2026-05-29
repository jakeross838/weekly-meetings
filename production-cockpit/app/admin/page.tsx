// /admin — index hub. Lists every admin surface (users, jobs, migrate).

import Link from "next/link";
import { Header } from "@/components/header";
import { currentUser, isAdmin } from "@/lib/auth";
import { notFound, redirect } from "next/navigation";

export const dynamic = "force-dynamic";

const SECTIONS = [
  {
    href: "/admin/users",
    label: "User access",
    blurb: "Add PMs, toggle which jobs each one can see.",
  },
  {
    href: "/admin/jobs",
    label: "Jobs",
    blurb: "Create, rename, or remove jobs from the portfolio.",
  },
  // Migrations card removed 2026-05-29 — Jake didn't want the raw "Supabase
  // DDL" surface visible in the panel. The /admin/migrate route still exists
  // for emergency schema changes; just not linked from the hub.
];

export default async function AdminHub() {
  const user = await currentUser();
  if (!user) redirect("/login?next=/admin");
  if (!isAdmin(user)) notFound();

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />
      <div className="px-5 pt-8">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Admin
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          Internal tools — only Jake sees these.
        </p>
      </div>
      <ul className="mt-6 border-t border-rule">
        {SECTIONS.map((s) => (
          <li key={s.href}>
            <Link
              href={s.href}
              className="flex items-baseline gap-3 px-5 py-4 border-b border-rule hover:bg-oceanside/30 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="font-head text-[15px] text-foreground">
                  {s.label}
                </p>
                <p className="mt-0.5 text-xs text-ink-3">{s.blurb}</p>
              </div>
              <span aria-hidden className="shrink-0 text-ink-3">
                →
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
