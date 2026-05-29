// /subs — simplified list (mobile-first).
// One row per sub: name, trade, open count (past-due in red).
// Trade filter as a single pill row. No stats bar, no ratings, no decoration.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Sub, OPEN_STATUSES, Status } from "@/lib/types";
import { subHealth } from "@/lib/sub-health";
import { Header } from "@/components/header";
import { DeleteButton } from "@/components/delete-button";
import { currentUser, canSeeJobByPm } from "@/lib/auth";
import { RequestAccessCard } from "@/components/request-access-card";

export const dynamic = "force-dynamic";

interface SP {
  trade?: string;
  flagged?: string;
}

export default async function SubsPage({ searchParams }: { searchParams: SP }) {
  const supabase = supabaseServer();
  const tradeFilter = searchParams.trade ?? "";
  const flaggedFilter = searchParams.flagged === "1";

  const todayIso = new Date().toISOString().slice(0, 10);

  const [subsRes, openTodosRes, jobsRes, assignRes] = await Promise.all([
    supabase.from("subs").select("*").eq("hidden", false),
    supabase
      .from("todos")
      .select("sub_id, due_date")
      .in("status", OPEN_STATUSES as Status[])
      .not("sub_id", "is", null),
    supabase.from("jobs").select("id, pm_id"),
    supabase
      .from("job_pm_assignments")
      .select("job_id, pm_id")
      .is("ended_at", null),
  ]);

  // Visibility gate: a non-admin who has no jobs assigned to them should see
  // the same empty/"request access" state on /subs as they see on /. Subs
  // is a portfolio-wide catalog; if they have no portfolio they shouldn't
  // see it.
  const user = await currentUser();
  if (user && user.role !== "admin") {
    const _assignPm = new Map<string, string>();
    for (const a of (assignRes.data ?? []) as { job_id: string; pm_id: string }[]) {
      _assignPm.set(a.job_id, a.pm_id);
    }
    const _visibleJobs = ((jobsRes.data ?? []) as { id: string; pm_id: string | null }[])
      .filter((j) => canSeeJobByPm(user, _assignPm.get(j.id) ?? j.pm_id));
    if (_visibleJobs.length === 0) {
      return (
        <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
          <Header />
          <div className="px-5 pt-8 pb-2">
            <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
              Subs
            </h1>
            <p className="mt-1 text-ink-3 text-sm">
              You&apos;ll see the sub catalog once Jake grants you access.
            </p>
          </div>
          <RequestAccessCard />
        </main>
      );
    }
  }

  const subs = (subsRes.data ?? []) as Sub[];
  const openTodos = (openTodosRes.data ?? []) as {
    sub_id: string;
    due_date: string | null;
  }[];

  const in7Iso = new Date(Date.now() + 7 * 86_400_000)
    .toISOString()
    .slice(0, 10);
  const openBySub: Record<
    string,
    { open: number; past_due: number; due_soon: number }
  > = {};
  for (const t of openTodos) {
    if (!t.sub_id) continue;
    const rec = openBySub[t.sub_id] ?? { open: 0, past_due: 0, due_soon: 0 };
    rec.open += 1;
    if (t.due_date && t.due_date < todayIso) rec.past_due += 1;
    else if (t.due_date && t.due_date >= todayIso && t.due_date <= in7Iso)
      rec.due_soon += 1;
    openBySub[t.sub_id] = rec;
  }

  const trades = Array.from(
    new Set(subs.map((s) => s.trade).filter(Boolean) as string[])
  ).sort();

  const flaggedCount = subs.filter((s) => s.flagged_for_pm_binder).length;

  let rows = subs;
  if (flaggedFilter) rows = rows.filter((s) => s.flagged_for_pm_binder);
  if (tradeFilter) rows = rows.filter((s) => s.trade === tradeFilter);
  // Sort: past-due desc, then open desc, then name
  rows = [...rows].sort((a, b) => {
    const ao = openBySub[a.id] ?? { open: 0, past_due: 0, due_soon: 0 };
    const bo = openBySub[b.id] ?? { open: 0, past_due: 0, due_soon: 0 };
    if (bo.past_due !== ao.past_due) return bo.past_due - ao.past_due;
    if (bo.open !== ao.open) return bo.open - ao.open;
    return a.name.localeCompare(b.name);
  });

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background">
      <Header />

      <div className="px-5 pt-8 pb-2">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Subs
        </h1>
        <p className="mt-1 text-ink-3 text-sm">{subs.length} on file</p>
      </div>

      {/* Trade filter — single horizontal pill row */}
      <div className="px-5 pt-4 pb-2">
        <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-5 px-5">
          <FilterPill
            href="/subs"
            active={!tradeFilter && !flaggedFilter}
            label="All"
          />
          {flaggedCount > 0 && (
            <FilterPill
              href="/subs?flagged=1"
              active={flaggedFilter}
              label={`⚑ Flagged · ${flaggedCount}`}
            />
          )}
          {trades.map((t) => (
            <FilterPill
              key={t}
              href={`/subs?trade=${encodeURIComponent(t)}`}
              active={tradeFilter === t}
              label={t}
            />
          ))}
        </div>
      </div>

      <ul className="mt-4 stagger-children">
        {rows.length === 0 ? (
          <li className="px-5 py-16 text-center text-ink-3 text-sm">
            No subs match
          </li>
        ) : (
          rows.map((s) => (
            <SubRow
              key={s.id}
              sub={s}
              open={openBySub[s.id]?.open ?? 0}
              pastDue={openBySub[s.id]?.past_due ?? 0}
              dueSoon={openBySub[s.id]?.due_soon ?? 0}
              showReason={flaggedFilter}
            />
          ))
        )}
      </ul>
    </main>
  );
}

function FilterPill({
  href,
  active,
  label,
}: {
  href: string;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={
        "shrink-0 px-3 py-1.5 text-xs font-medium border transition-colors " +
        (active
          ? "bg-ink text-paper border-ink"
          : "bg-transparent text-ink-2 border-rule hover:border-ink hover:text-ink")
      }
    >
      {label}
    </Link>
  );
}

function SubRow({
  sub,
  open,
  pastDue,
  dueSoon,
  showReason,
}: {
  sub: Sub;
  open: number;
  pastDue: number;
  dueSoon: number;
  showReason?: boolean;
}) {
  const health = subHealth({
    pastDue,
    dueSoon,
    flagged: sub.flagged_for_pm_binder,
  });
  const healthTitle =
    pastDue > 0
      ? `${health.label} — ${pastDue} past due`
      : sub.flagged_for_pm_binder
        ? `${health.label} — flagged for PM binder`
        : dueSoon > 0
          ? `${health.label} — ${dueSoon} due within 7 days`
          : health.label;
  return (
    <li className="flex items-stretch border-b border-rule hover:bg-oceanside/30 transition-colors">
      <Link
        href={`/sub/${sub.id}`}
        className="flex flex-1 items-baseline gap-3 px-5 py-3 min-w-0"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 min-w-0">
            <span
              className={`shrink-0 self-center h-2 w-2 rounded-full ${health.dotClass}`}
              title={healthTitle}
              aria-label={healthTitle}
            />
            {sub.flagged_for_pm_binder && (
              <span className="shrink-0 text-gold" title="Flagged for PM binder">
                ⚑
              </span>
            )}
            <p className="text-foreground text-sm leading-snug truncate">
              {sub.name}
            </p>
            {sub.source === "auto" && (
              <span
                className="shrink-0 font-mono text-[9px] tracking-[0.12em] uppercase text-ink-3"
                title="Auto-added from a Buildertrend daily log"
              >
                auto
              </span>
            )}
          </div>
          {showReason && sub.flag_reasons?.[0] ? (
            <p className="mt-0.5 text-ink-3 text-xs leading-snug">
              {sub.flag_reasons[0]}
            </p>
          ) : (
            sub.trade && (
              <p className="mt-0.5 text-ink-3 text-xs">{sub.trade}</p>
            )
          )}
        </div>
        <div className="shrink-0 flex items-baseline gap-2 font-mono text-xs">
          {pastDue > 0 && (
            <span className="text-urgent">{pastDue} late</span>
          )}
          {open > 0 ? (
            <span className="text-ink-2">{open} open</span>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </div>
      </Link>
      <DeleteButton
        endpoint={`/api/subs/${sub.id}/delete`}
        label={sub.name}
        confirmLabel="Delete?"
        className="self-center pr-4 pl-1 text-sm"
      />
    </li>
  );
}
