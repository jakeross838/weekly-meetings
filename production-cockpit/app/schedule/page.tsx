import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Todo, OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";
import { ScheduleList } from "@/components/schedule-list";

export const dynamic = "force-dynamic";

interface SP {
  pm?: string;
  days?: string;
}

export default async function SchedulePage({
  searchParams,
}: {
  searchParams: SP;
}) {
  const supabase = supabaseServer();
  const selectedPm = searchParams.pm ?? "";
  const horizonDays = searchParams.days === "30" ? 30 : 14;

  const today = new Date();
  const todayIso = today.toISOString().slice(0, 10);
  const horizon = new Date(today.getTime() + horizonDays * 86_400_000)
    .toISOString()
    .slice(0, 10);

  // Upcoming todos in the horizon, sub-embedded
  let q = supabase
    .from("todos")
    .select("*, sub:subs(id, name, trade, rating)")
    .in("status", OPEN_STATUSES as Status[])
    .gte("due_date", todayIso)
    .lte("due_date", horizon)
    .order("due_date", { ascending: true });
  if (selectedPm) q = q.eq("pm_id", selectedPm);

  // All open todos for prerequisite lookup
  const [todosRes, allOpenRes, pmsRes] = await Promise.all([
    q,
    supabase
      .from("todos")
      .select("id, job, category, due_date, status, title, edited_title, priority")
      .in("status", OPEN_STATUSES as Status[])
      .lte("due_date", horizon),
    supabase
      .from("pms")
      .select("id, full_name, active")
      .eq("active", true)
      .order("full_name"),
  ]);

  const todos = (todosRes.data ?? []) as Todo[];
  const allOpen = allOpenRes.data ?? [];
  const pms = (pmsRes.data ?? []) as { id: string; full_name: string }[];

  return (
    <main className="max-w-[480px] lg:max-w-[1200px] mx-auto min-h-screen bg-background">
      <Header />

      <div className="px-6 lg:px-10 pt-6 pb-3 border-b border-rule">
        <p className="text-[12px] tracking-[0.18em] uppercase text-ink-3 font-medium">
          Upcoming · next {horizonDays} days
        </p>
        <h1 className="mt-1 font-head text-4xl font-semibold leading-tight text-ink">
          Schedule
        </h1>
      </div>

      {/* PM + horizon filters */}
      <div className="px-6 lg:px-10 py-3 border-b border-rule flex flex-wrap items-center gap-3 text-[13px]">
        <span className="text-ink-3 font-medium tracking-[0.12em] uppercase text-[11px]">
          PM
        </span>
        <FilterLink href={`/schedule${horizonDays !== 14 ? `?days=${horizonDays}` : ""}`} active={!selectedPm}>
          All
        </FilterLink>
        {pms.map((p) => {
          const q2 = new URLSearchParams();
          q2.set("pm", p.id);
          if (horizonDays !== 14) q2.set("days", String(horizonDays));
          return (
            <FilterLink key={p.id} href={`/schedule?${q2}`} active={selectedPm === p.id}>
              {p.full_name.split(" ")[0]}
            </FilterLink>
          );
        })}
        <span className="ml-auto flex gap-2">
          <FilterLink
            href={selectedPm ? `/schedule?pm=${selectedPm}` : "/schedule"}
            active={horizonDays === 14}
          >
            14d
          </FilterLink>
          <FilterLink
            href={`/schedule?${selectedPm ? `pm=${selectedPm}&` : ""}days=30`}
            active={horizonDays === 30}
          >
            30d
          </FilterLink>
        </span>
      </div>

      <ScheduleList todos={todos} allOpen={allOpen} />
    </main>
  );
}

function FilterLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={
        "px-3 py-1.5 text-[13px] font-medium border transition-colors " +
        (active
          ? "bg-ink text-paper border-ink"
          : "bg-paper text-ink border-rule hover:border-ink")
      }
    >
      {children}
    </Link>
  );
}
