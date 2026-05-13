import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Sub, OPEN_STATUSES, Status } from "@/lib/types";
import { Header } from "@/components/header";
import { TradeSelect } from "@/components/trade-select";

export const dynamic = "force-dynamic";

type SortKey = "rating" | "reliability" | "open" | "name";

interface SP {
  sort?: string;
  trade?: string;
}

const SORT_LABEL: Record<SortKey, string> = {
  rating: "Rating",
  reliability: "Avg days",
  open: "Open",
  name: "Name",
};

export default async function SubsPage({ searchParams }: { searchParams: SP }) {
  const supabase = supabaseServer();
  const sortKey: SortKey =
    searchParams.sort === "reliability" ||
    searchParams.sort === "open" ||
    searchParams.sort === "name"
      ? searchParams.sort
      : "rating";
  const tradeFilter = searchParams.trade ?? "";

  // Two parallel queries: full sub catalog + open todos linked to subs.
  // We count client-side because PostgREST embedded filtering on counts is
  // brittle and we already need the open-count for every row.
  const [subsRes, openTodosRes] = await Promise.all([
    supabase.from("subs").select("*"),
    supabase
      .from("todos")
      .select("sub_id")
      .in("status", OPEN_STATUSES as Status[])
      .not("sub_id", "is", null),
  ]);

  const subs = (subsRes.data ?? []) as Sub[];
  const openTodos = (openTodosRes.data ?? []) as { sub_id: string }[];

  const openCountBySub: Record<string, number> = {};
  for (const t of openTodos) {
    if (t.sub_id) openCountBySub[t.sub_id] = (openCountBySub[t.sub_id] ?? 0) + 1;
  }

  // Distinct trades for the filter pill row
  const trades = Array.from(
    new Set(subs.map((s) => s.trade).filter(Boolean) as string[])
  ).sort();

  // Apply filter + sort
  let rows = subs;
  if (tradeFilter) rows = rows.filter((s) => s.trade === tradeFilter);
  rows = [...rows].sort((a, b) => {
    if (sortKey === "name") return a.name.localeCompare(b.name);
    if (sortKey === "open") {
      return (openCountBySub[b.id] ?? 0) - (openCountBySub[a.id] ?? 0);
    }
    if (sortKey === "reliability") {
      // Faster (fewer days/job) ranks higher. NULLs to bottom.
      const av = a.avg_days_per_job ?? 9999;
      const bv = b.avg_days_per_job ?? 9999;
      return av - bv;
    }
    // default rating
    return (b.rating ?? -1) - (a.rating ?? -1);
  });

  const totalSubs = subs.length;
  const ratedSubs = subs.filter((s) => s.rating != null).length;
  const flaggedSubs = subs.filter((s) => s.flagged_for_pm_binder).length;

  return (
    <main className="max-w-[480px] lg:max-w-[1200px] mx-auto min-h-screen bg-background">
      <Header />

      <div className="px-5 py-2 border-b border-rule bg-sand-2/40 flex items-center justify-between">
        <Link
          href="/"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Todos
        </Link>
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Sheet · SUBS-01
        </span>
      </div>

      {/* Page label */}
      <div className="px-5 pt-5 pb-4 border-b border-rule bg-paper rise">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Trade Partners
        </p>
        <h1 className="mt-1 font-head text-3xl font-semibold leading-none text-ink">
          Subs
        </h1>
      </div>

      {/* Stats row */}
      <div
        className="grid grid-cols-3 border-b border-rule rise"
        style={{ animationDelay: "60ms" }}
      >
        <Stat label="Total" value={totalSubs} />
        <Stat label="Rated" value={ratedSubs} divider />
        <Stat
          label="Flagged"
          value={flaggedSubs}
          divider
          accent={flaggedSubs > 0 ? "urgent" : undefined}
        />
      </div>

      {/* Trade filter — native dropdown so every trade is accessible */}
      <div
        className="border-b border-rule rise"
        style={{ animationDelay: "120ms" }}
      >
        <div className="px-5 py-3">
          <label className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 block mb-1.5">
            Filter by trade
          </label>
          <TradeSelect trades={trades} selected={tradeFilter} />
        </div>

        {/* Sort */}
        <div className="px-5 py-3 border-t border-rule">
          <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-2">
            Sort subs by
          </p>
          <div className="flex gap-1.5 flex-wrap">
            {(["rating", "reliability", "open", "name"] as SortKey[]).map((k) => (
              <FilterPill
                key={k}
                href={buildHref(searchParams, {
                  sort: k === "rating" ? undefined : k,
                })}
                active={sortKey === k}
                label={SORT_LABEL[k]}
              />
            ))}
          </div>
        </div>

        {/* How ratings work — disclosed explainer */}
        <details className="border-t border-rule">
          <summary className="px-5 py-3 cursor-pointer flex items-center justify-between font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink list-none">
            <span>How ratings work</span>
            <span className="ml-2">▾</span>
          </summary>
          <div className="px-5 pb-4 text-[12px] leading-relaxed text-ink-2 space-y-1.5">
            <p>
              Each sub starts at <span className="font-mono text-ink">5.0★</span>. Points
              are deducted based on signals from the weekly Buildertrend
              analytics (`data/sub-phase-rollups.json`):
            </p>
            <ul className="font-mono text-[11px] space-y-1 mt-2">
              <li>−1.5 · Flagged for the PM binder on any phase</li>
              <li>−1.0 · Return-burst rate &gt; 50% (frequent callbacks)</li>
              <li>−0.5 · Punch-burst rate &gt; 30% (punch-list rework)</li>
              <li>−0.5 · Each phase labeled &apos;dragging&apos; (capped at −1.5)</li>
            </ul>
            <p className="mt-2">
              Subs without BT data show no rating. Open a sub&apos;s profile to
              see exactly which signals drove the score.
            </p>
          </div>
        </details>
      </div>

      {/* Sub list — single col on mobile, 2-col grid on desktop */}
      <div className="lg:grid lg:grid-cols-2 lg:divide-x lg:divide-rule">
        {rows.length === 0 ? (
          <div className="px-5 py-16 text-center font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 lg:col-span-2">
            No subs match
          </div>
        ) : (
          rows.map((s, idx) => (
            <SubRow
              key={s.id}
              sub={s}
              openCount={openCountBySub[s.id] ?? 0}
              index={idx}
            />
          ))
        )}
      </div>

      <footer className="mt-6 px-5 py-6 border-t border-rule bg-sand-2/40">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
          Ross Built · Trade Partner Index · {totalSubs} on file
        </p>
      </footer>
    </main>
  );
}

function buildHref(current: SP, patch: { sort?: string; trade?: string }) {
  const p = new URLSearchParams();
  const sort = patch.sort !== undefined ? patch.sort : current.sort;
  const trade = patch.trade !== undefined ? patch.trade : current.trade;
  if (sort) p.set("sort", sort);
  if (trade) p.set("trade", trade);
  const q = p.toString();
  return q ? `/subs?${q}` : "/subs";
}

function Stat({
  label,
  value,
  divider,
  accent,
}: {
  label: string;
  value: number;
  divider?: boolean;
  accent?: "urgent";
}) {
  return (
    <div
      className={
        "px-4 py-5 flex flex-col items-start " +
        (divider ? "border-l border-rule" : "")
      }
    >
      <span
        className={
          "font-mono text-4xl font-medium leading-none tabular-nums " +
          (accent === "urgent" ? "text-urgent" : "text-ink")
        }
      >
        {String(value).padStart(3, "0")}
      </span>
      <span className="mt-2 font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
        {label}
      </span>
    </div>
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
        "shrink-0 px-3 py-1.5 text-sm font-medium border transition-colors " +
        (active
          ? "bg-ink text-paper border-ink"
          : "bg-transparent text-foreground border-rule hover:border-foreground")
      }
    >
      {label}
    </Link>
  );
}

function SubRow({
  sub,
  openCount,
  index,
}: {
  sub: Sub;
  openCount: number;
  index: number;
}) {
  const hasRating = sub.rating != null;
  return (
    <Link
      href={`/sub/${sub.id}`}
      className="flex items-stretch border-b border-rule active:bg-muted/60 transition-colors rise"
      style={{ animationDelay: `${180 + Math.min(index, 12) * 30}ms` }}
    >
      <span
        className={`w-[3px] shrink-0 ${
          sub.flagged_for_pm_binder ? "bg-urgent" : "bg-rule"
        }`}
        aria-hidden
      />
      <div className="flex-1 min-w-0 px-4 py-3.5">
        {/* Top: name + rating */}
        <div className="flex items-start justify-between gap-3 mb-1">
          <p className="text-[15px] leading-snug text-ink font-medium truncate">
            {sub.name}
          </p>
          <div className="shrink-0 font-mono tabular-nums text-right leading-tight">
            <div className="text-[13px] text-ink">
              {hasRating ? (
                <>
                  {sub.rating!.toFixed(1)}
                  <span className="text-high ml-0.5">★</span>
                </>
              ) : (
                <span className="text-ink-3">—</span>
              )}
            </div>
            {sub.avg_days_per_job != null && (
              <div className="font-mono text-[10px] tracking-[0.12em] uppercase text-ink-3">
                {sub.avg_days_per_job.toFixed(1)}d/job
              </div>
            )}
          </div>
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.12em] uppercase text-ink-3">
          <span>{sub.trade ?? "Trade ?"}</span>
          {sub.jobs_performed != null && (
            <>
              <span>·</span>
              <span>{sub.jobs_performed} jobs</span>
            </>
          )}
          {openCount > 0 && (
            <>
              <span>·</span>
              <span className={openCount > 5 ? "text-ink" : ""}>
                {openCount} open
              </span>
            </>
          )}
          {sub.flagged_for_pm_binder && (
            <span className="ml-auto text-urgent">Flagged</span>
          )}
        </div>
      </div>
    </Link>
  );
}
