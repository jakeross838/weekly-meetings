// /subs — activity-first roster (mobile-first).
// Each row answers three questions at a glance: is this sub on a job right now,
// how much have they worked, and are they reliable (absences) + on top of their
// open items. Trade filter + an "On site" filter as a single pill row.
//
// All presence/absence facts come from one daily_logs fetch aggregated in
// memory (aggregateAllSubs) — no per-sub jsonb fan-out.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { Sub, OPEN_STATUSES, Status } from "@/lib/types";
import { subHealth } from "@/lib/sub-health";
import { businessToday, businessDateOffset } from "@/lib/today";
import {
  DailyLogLite,
  buildNameIndex,
  aggregateAllSubs,
  latestLogDate,
  SubListStat,
  FRESH_ON_SITE_DAYS,
} from "@/lib/sub-activity";
import { Header } from "@/components/header";
import { DeleteButton } from "@/components/delete-button";
import { currentUser, canSeeJobByPm } from "@/lib/auth";
import { RequestAccessCard } from "@/components/request-access-card";

export const dynamic = "force-dynamic";

interface SP {
  trade?: string;
  flagged?: string;
  onsite?: string;
}

const EMPTY_STAT: SubListStat = {
  totalDays: 0,
  absenceCount: 0,
  lastSeen: null,
  lastSeenDaysAgo: null,
  currentJobs: [],
};

export default async function SubsPage({ searchParams }: { searchParams: SP }) {
  const supabase = supabaseServer();
  const tradeFilter = searchParams.trade ?? "";
  const flaggedFilter = searchParams.flagged === "1";
  const onsiteFilter = searchParams.onsite === "1";

  const todayIso = businessToday();

  const [subsRes, openTodosRes, jobsRes, assignRes, logsRes] =
    await Promise.all([
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
      // Presence/absence source. Tolerates the table not existing (pre-009).
      supabase
        .from("daily_logs")
        .select("log_date, job_key, crews_present, absent_crews, activity"),
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
  const logs = (logsRes.data ?? []) as DailyLogLite[];

  const in7Iso = businessDateOffset(7);
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

  // Presence/absence rollup — one pass over all logs, bucketed by name index.
  const latest = latestLogDate(logs);
  const stats = aggregateAllSubs(logs, buildNameIndex(subs), { latest });

  const trades = Array.from(
    new Set(subs.map((s) => s.trade).filter(Boolean) as string[])
  ).sort();

  const flaggedCount = subs.filter((s) => s.flagged_for_pm_binder).length;
  const onsiteCount = subs.filter(
    (s) => (stats.get(s.id)?.currentJobs.length ?? 0) > 0
  ).length;

  let rows = subs;
  if (flaggedFilter) rows = rows.filter((s) => s.flagged_for_pm_binder);
  if (onsiteFilter)
    rows = rows.filter(
      (s) => (stats.get(s.id)?.currentJobs.length ?? 0) > 0
    );
  if (tradeFilter) rows = rows.filter((s) => s.trade === tradeFilter);

  // Sort: on a job right now first (most recent first), then idle by recency,
  // then never-logged, with past-due open items breaking remaining ties.
  rows = [...rows].sort((a, b) => {
    const as = stats.get(a.id) ?? EMPTY_STAT;
    const bs = stats.get(b.id) ?? EMPTY_STAT;
    const aOn = as.currentJobs.length > 0 ? 1 : 0;
    const bOn = bs.currentJobs.length > 0 ? 1 : 0;
    if (bOn !== aOn) return bOn - aOn;
    const aSeen = as.lastSeen ?? "";
    const bSeen = bs.lastSeen ?? "";
    if (bSeen !== aSeen) return bSeen.localeCompare(aSeen);
    const ao = openBySub[a.id]?.past_due ?? 0;
    const bo = openBySub[b.id]?.past_due ?? 0;
    if (bo !== ao) return bo - ao;
    return a.name.localeCompare(b.name);
  });

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background">
      <Header />

      <div className="px-5 pt-8 pb-2">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Subs
        </h1>
        <p className="mt-1 text-ink-3 text-sm">
          {subs.length} on file
          {onsiteCount > 0 && (
            <>
              {" · "}
              <span className="text-success">{onsiteCount} on site</span>
            </>
          )}
        </p>
      </div>

      {/* Filter row — On site + Flagged + per-trade pills */}
      <div className="px-5 pt-4 pb-2">
        <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-5 px-5">
          <FilterPill
            href="/subs"
            active={!tradeFilter && !flaggedFilter && !onsiteFilter}
            label="All"
          />
          {onsiteCount > 0 && (
            <FilterPill
              href="/subs?onsite=1"
              active={onsiteFilter}
              label={`● On site · ${onsiteCount}`}
            />
          )}
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
              stat={stats.get(s.id) ?? EMPTY_STAT}
              latest={latest}
              open={openBySub[s.id]?.open ?? 0}
              pastDue={openBySub[s.id]?.past_due ?? 0}
              dueSoon={openBySub[s.id]?.due_soon ?? 0}
              showReason={flaggedFilter}
            />
          ))
        )}
      </ul>

      {latest && (
        <p className="px-5 pt-6 pb-2 text-[10px] font-mono tracking-[0.18em] uppercase text-ink-3">
          presence as of latest daily log · {latest}
        </p>
      )}
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

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);
}

function SubRow({
  sub,
  stat,
  latest,
  open,
  pastDue,
  dueSoon,
  showReason,
}: {
  sub: Sub;
  stat: SubListStat;
  latest: string | null;
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

  const onSite = stat.currentJobs.length > 0;
  // "Live" (solid green) only if seen within the freshness window; older-but-
  // still-on-a-job presence reads muted so a 13-day-old entry doesn't wear the
  // same green dot as a same-day one.
  const fresh =
    onSite &&
    stat.lastSeenDaysAgo != null &&
    stat.lastSeenDaysAgo <= FRESH_ON_SITE_DAYS;
  const idleDays =
    !onSite && stat.lastSeen && latest
      ? daysBetween(stat.lastSeen, latest)
      : null;

  return (
    <li className="flex items-stretch border-b border-rule hover:bg-oceanside/30 transition-colors">
      <Link
        href={`/sub/${sub.id}`}
        className="flex flex-1 flex-col gap-1 px-5 py-3 min-w-0"
      >
        {/* Line 1 — health dot + name, current-job status on the right */}
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
          <p className="flex-1 min-w-0 text-foreground text-sm leading-snug truncate">
            {sub.name}
          </p>
          {onSite ? (
            <span
              className={
                "shrink-0 inline-flex items-center gap-1 font-mono text-[11px] max-w-[45%] " +
                (fresh ? "text-success" : "text-ink-2")
              }
              title={
                `On site: ${stat.currentJobs.join(", ")}` +
                (stat.lastSeenDaysAgo
                  ? ` · last seen ${stat.lastSeenDaysAgo}d ago`
                  : "")
              }
            >
              <span
                className={
                  "shrink-0 h-1.5 w-1.5 rounded-full " +
                  (fresh ? "bg-success" : "bg-ink-3")
                }
              />
              <span className="truncate">{stat.currentJobs[0]}</span>
              {stat.currentJobs.length > 1 && (
                <span className="shrink-0 text-ink-3">
                  +{stat.currentJobs.length - 1}
                </span>
              )}
            </span>
          ) : idleDays != null ? (
            <span className="shrink-0 font-mono text-[11px] text-ink-3">
              {idleDays}d idle
            </span>
          ) : (
            <span className="shrink-0 font-mono text-[11px] text-ink-3">—</span>
          )}
        </div>

        {/* Line 2 — trade + site-days on the left, reliability/open on the right */}
        <div className="flex items-baseline gap-2 min-w-0 pl-4">
          <p className="flex-1 min-w-0 truncate text-ink-3 text-xs">
            {showReason && sub.flag_note ? (
              sub.flag_note
            ) : (
              <>
                {sub.trade ?? "—"}
                {stat.totalDays > 0 && (
                  <span className="text-ink-3">
                    {" · "}
                    {stat.totalDays} site-day
                    {stat.totalDays === 1 ? "" : "s"}
                  </span>
                )}
              </>
            )}
          </p>
          <div className="shrink-0 flex items-baseline gap-2 font-mono text-[11px]">
            {stat.absenceCount > 0 && (
              <span
                className="text-urgent"
                title={`${stat.absenceCount} logged absence${stat.absenceCount === 1 ? "" : "s"}`}
              >
                {stat.absenceCount} absent
              </span>
            )}
            {pastDue > 0 ? (
              <span className="text-urgent">{pastDue} late</span>
            ) : open > 0 ? (
              <span className="text-ink-2">{open} open</span>
            ) : null}
          </div>
        </div>
      </Link>
      <DeleteButton
        endpoint={`/api/subs/${sub.id}/delete`}
        label={sub.name}
        className="self-center pr-4 pl-1 text-sm"
      />
    </li>
  );
}
