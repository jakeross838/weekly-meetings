import { supabaseServer } from "@/lib/supabase";
import { Todo, PM, OPEN_STATUSES, Status } from "@/lib/types";
import { isoMondayUtc } from "@/lib/week";
import { Header } from "@/components/header";
import { StatsBar } from "@/components/stats-bar";
import { Filters } from "@/components/filters";
import { PMSection } from "@/components/pm-section";
import { CompletedSection } from "@/components/completed-section";
import { RossBuiltMark } from "@/components/logo";
import { PriorityPanel } from "@/components/priority-panel";

interface SP {
  pm?: string;
  job?: string;
  view?: string;
}

const PRIORITY_RANK: Record<string, number> = {
  URGENT: 0,
  HIGH: 1,
  NORMAL: 2,
};

export const dynamic = "force-dynamic";

export default async function Page({
  searchParams,
}: {
  searchParams: SP;
}) {
  const supabase = supabaseServer();
  const selectedPm = searchParams.pm ?? "";
  const selectedJob = searchParams.job ?? "";
  const view = (searchParams.view === "done" ? "done" : "open") as
    | "open"
    | "done";

  const monday = isoMondayUtc();
  const todayIso = new Date().toISOString().slice(0, 10);
  const sevenDaysAgo = new Date(Date.now() - 7 * 86_400_000).toISOString();

  // Stats — always portfolio-wide (not PM-filtered) so Jake sees totals.
  const [
    openCountRes,
    doneCountRes,
    overdueCountRes,
    pmsRes,
    todosRes,
    completedRes,
  ] = await Promise.all([
    supabase
      .from("todos")
      .select("id", { count: "exact", head: true })
      .in("status", OPEN_STATUSES as Status[]),
    supabase
      .from("todos")
      .select("id", { count: "exact", head: true })
      .eq("status", "COMPLETE")
      .gte("completed_at", monday),
    supabase
      .from("todos")
      .select("id", { count: "exact", head: true })
      .in("status", OPEN_STATUSES as Status[])
      .lt("due_date", todayIso),
    supabase
      .from("pms")
      .select("id, full_name, active")
      .eq("active", true)
      .order("full_name"),
    buildTodoQuery(supabase, view, selectedPm, selectedJob),
    // Recently completed — last 7 days, most recent first, optionally scoped
    // to the selected PM. Capped at 30 rows to keep the bottom section tight.
    (() => {
      let q = supabase
        .from("todos")
        .select("*")
        .eq("status", "COMPLETE")
        .gte("completed_at", sevenDaysAgo)
        .order("completed_at", { ascending: false })
        .limit(30);
      if (selectedPm) q = q.eq("pm_id", selectedPm);
      if (selectedJob) q = q.eq("job", selectedJob);
      return q;
    })(),
  ]);

  const pms = (pmsRes.data ?? []) as PM[];
  const todos = (todosRes.data ?? []) as Todo[];
  const recentlyCompleted = (completedRes.data ?? []) as Todo[];
  const pmNames: Record<string, string> = Object.fromEntries(
    pms.map((p) => [p.id, p.full_name])
  );

  // Job dropdown options for the currently selected PM (or all if no PM)
  const jobsForFilter = Array.from(
    new Set(
      (selectedPm
        ? todos.filter((t) => t.pm_id === selectedPm)
        : todos
      ).map((t) => t.job)
    )
  ).sort();

  // Group by pm, sort URGENT-first then due ascending
  const byPm: Record<string, Todo[]> = {};
  for (const t of todos) {
    if (!byPm[t.pm_id]) byPm[t.pm_id] = [];
    byPm[t.pm_id].push(t);
  }
  Object.values(byPm).forEach((arr) => {
    arr.sort((a, b) => {
      const pr =
        (PRIORITY_RANK[a.priority ?? "NORMAL"] ?? 3) -
        (PRIORITY_RANK[b.priority ?? "NORMAL"] ?? 3);
      if (pr !== 0) return pr;
      const ad = a.due_date ?? "9999-12-31";
      const bd = b.due_date ?? "9999-12-31";
      return ad.localeCompare(bd);
    });
  });

  return (
    <main className="max-w-[480px] lg:max-w-[1200px] mx-auto min-h-screen bg-background">
      <Header />
      <StatsBar
        open={openCountRes.count ?? 0}
        doneThisWeek={doneCountRes.count ?? 0}
        overdue={overdueCountRes.count ?? 0}
      />
      <Filters
        pms={pms}
        jobs={jobsForFilter}
        selectedPm={selectedPm}
        selectedJob={selectedJob}
        view={view}
      />
      {/* Desktop ≥lg becomes a 2-column layout: priority + recently-completed
          on the left rail, PM sections on the right. Mobile stays single-col. */}
      <div className="lg:grid lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)] lg:divide-x lg:divide-rule">
        <div>
          {view === "open" && (
            <PriorityPanel todos={todos} pmNames={pmNames} />
          )}
          {view === "open" && (
            <CompletedSection todos={recentlyCompleted} pmNames={pmNames} />
          )}
        </div>
        <div>
          {pms
            .filter((pm) => (byPm[pm.id] ?? []).length > 0)
            .map((pm, idx) => (
              <PMSection
                key={pm.id}
                pmFullName={pm.full_name}
                todos={byPm[pm.id] ?? []}
                allowComplete={view === "open"}
                index={idx}
              />
            ))}
          {todos.length === 0 && (
            <div className="px-5 py-20 text-center">
              <p className="font-head text-xl text-ink-3">
                {view === "open" ? "Nothing open" : "Nothing closed this week"}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Footer — minimal brand + timestamp */}
      <footer className="mt-8 px-5 py-6 border-t border-rule bg-sand-2/40 flex items-center justify-center gap-2.5 text-ink-3">
        <RossBuiltMark size={18} className="opacity-70" />
        <span className="font-mono text-[11px] tracking-[0.18em] uppercase">
          Ross Built · Updated{" "}
          {new Date().toLocaleTimeString("en-US", {
            hour: "numeric",
            minute: "2-digit",
          })}
        </span>
      </footer>
    </main>
  );
}

function buildTodoQuery(
  supabase: ReturnType<typeof supabaseServer>,
  view: "open" | "done",
  pm: string,
  job: string
) {
  // Embed the linked sub so the row can render trade + rating without a
  // second round-trip. Supabase resolves the FK via the column name `sub_id`.
  let q = supabase
    .from("todos")
    .select("*, sub:subs(id, name, trade, rating, reliability_pct)");
  if (view === "open") {
    q = q.in("status", OPEN_STATUSES as Status[]);
  } else {
    q = q.eq("status", "COMPLETE").gte("completed_at", isoMondayUtc());
  }
  if (pm) q = q.eq("pm_id", pm);
  if (job) q = q.eq("job", job);
  return q.order("due_date", { ascending: true, nullsFirst: false });
}
