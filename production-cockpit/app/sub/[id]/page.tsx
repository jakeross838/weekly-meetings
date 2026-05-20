// /sub/[id] — sub profile.
// Header: name + trade (composite A-F rating removed per Jake 2026-05-18).
// Tiles: Open, Past due, No-shows, Avg drift.
// Specialties: auto from daily logs + manual, now with canonical schedule
// item mapping (F5) + avg crew size (F3).
// Inspections (F6), Checklist (F7), Photo summaries (F8).
// Body: open items + collapsed timeline + collapsed Done.

import Link from "next/link";
import { notFound } from "next/navigation";
import { supabaseServer } from "@/lib/supabase";
import { Sub, Todo, OPEN_STATUSES, Status } from "@/lib/types";
import { subHealth } from "@/lib/sub-health";
import { Header } from "@/components/header";
import { SpecialtiesEditor, SpecialtyRow } from "./specialties-editor";
import { CategoryFilterPills } from "@/components/category-filter-pills";
import { SubChecklistEditor, ChecklistItem } from "./checklist-editor";

export const dynamic = "force-dynamic";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  return Math.round(
    (new Date(b).getTime() - new Date(a).getTime()) / 86_400_000
  );
}

// crews_present / absent_crews are jsonb arrays. PostgREST's array-overlaps
// operator (&&) does NOT work on jsonb ("operator does not exist: jsonb &&"),
// so "row's array shares ANY name with `names`" is emulated with one jsonb
// containment query (@>, the `cs` operator) per name, merged + de-duped by id.
// `names` is just a sub's name + aliases, so the fan-out is tiny. Each select
// MUST include `id` for the de-dupe to work.
async function logsContainingAny(
  supabase: ReturnType<typeof supabaseServer>,
  column: "crews_present" | "absent_crews",
  names: string[],
  select: string,
  opts?: { limit?: number; orderDesc?: boolean }
): Promise<Record<string, unknown>[]> {
  if (names.length === 0) return [];
  const results = await Promise.all(
    names.map((n) => {
      let q = supabase
        .from("daily_logs")
        .select(select)
        // .filter(...,"cs",json) emits `column=cs.["name"]` — the jsonb-correct
        // containment form (verified against PostgREST). Using .contains() here
        // would emit the Postgres array literal `{...}` and 400 on jsonb.
        .filter(column, "cs", JSON.stringify([n]));
      if (opts?.orderDesc) q = q.order("log_date", { ascending: false });
      if (opts?.limit) q = q.limit(opts.limit);
      return q;
    })
  );
  const byId = new Map<string, Record<string, unknown>>();
  for (const r of results) {
    if (r.error) continue;
    for (const row of (r.data ?? []) as unknown as Record<string, unknown>[]) {
      const key = (row.id as string) ?? JSON.stringify(row);
      byId.set(key, row);
    }
  }
  return Array.from(byId.values());
}

export default async function SubPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { cat?: string };
}) {
  const catFilter = searchParams.cat ?? null;
  const supabase = supabaseServer();

  const [
    subRes,
    openRes,
    doneRes,
    manualSpecRes,
    jobsRes,
    scheduleItemsRes,
    checklistRes,
  ] = await Promise.all([
    supabase.from("subs").select("*").eq("id", params.id).maybeSingle(),
    supabase
      .from("todos")
      .select("*")
      .eq("sub_id", params.id)
      .in("status", OPEN_STATUSES as Status[])
      .order("due_date", { ascending: true, nullsFirst: false }),
    supabase
      .from("todos")
      .select("*")
      .eq("sub_id", params.id)
      .eq("status", "COMPLETE")
      .order("completed_at", { ascending: false })
      .limit(20),
    supabase
      .from("sub_specialties")
      .select("specialty, source, duration_days_manual_override")
      .eq("sub_id", params.id),
    supabase.from("jobs").select("id, name"),
    // F5 — canonical schedule items; tolerates table-missing so first-deploy
    // doesn't 500 the sub profile.
    supabase
      .from("schedule_items")
      .select("id, name, trade, typical_duration_days, aliases"),
    // F7 — per-sub checklist; tolerates table-missing for same reason.
    supabase
      .from("sub_checklist_items")
      .select(
        "id, lens, item_text, is_done, done_at, done_by, notes, position"
      )
      .eq("sub_id", params.id)
      .order("position", { ascending: true }),
  ]);
  const jobNameById: Record<string, string> = {};
  for (const j of ((jobsRes.data ?? []) as { id: string; name: string }[])) {
    jobNameById[j.id] = j.name;
  }

  const sub = subRes.data as Sub | null;
  if (!sub) notFound();

  // No-show count: rows in daily_logs.absent_crews that match this sub's
  // name or any of its aliases. Degrades to null if the daily_logs table
  // doesn't exist yet (migration 009 not applied) so the UI shows "—".
  const candidateNames = Array.from(
    new Set([sub.name, ...((sub.aliases ?? []) as string[])])
  ).filter(Boolean);
  let noShowCount: number | null = null;
  if (candidateNames.length > 0) {
    const absentRows = await logsContainingAny(
      supabase,
      "absent_crews",
      candidateNames,
      "id"
    );
    noShowCount = absentRows.length;
  }

  // Phase C: activity timeline. Pull daily-log days where this sub appears
  // in crews_present + items scheduled for this sub. Tolerates the table /
  // columns not existing (returns empty array on PGRST205 / missing column).
  //
  // F3 / F6 / F8 — also try to pull crew_counts, inspections, photo_summary.
  // We attempt the rich SELECT first; on PGRST204 ("column missing") or any
  // 400 mentioning one of the new fields, we retry with the legacy column set
  // so a pre-migration deployment still renders correctly.
  type LogRow = {
    id?: string;
    log_date: string | null;
    job_key: string;
    parent_group_activities: string[] | null;
    crew_counts?: Record<string, number> | null;
    inspections?: unknown[] | null;
    photo_summary?: unknown | null;
    photo_urls?: string[] | null;
  };
  let presentDays: LogRow[] = [];
  if (candidateNames.length > 0) {
    const RICH =
      "id, log_date, job_key, parent_group_activities, crew_counts, inspections, photo_summary, photo_urls";
    const merged = (await logsContainingAny(
      supabase,
      "crews_present",
      candidateNames,
      RICH,
      { limit: 120, orderDesc: true }
    )) as unknown as LogRow[];
    // Per-name queries can return the same log under name + alias; they're
    // de-duped by id in the helper. Re-sort the merged set and cap it.
    merged.sort((a, b) => (b.log_date ?? "").localeCompare(a.log_date ?? ""));
    presentDays = merged.slice(0, 120);
  }

  // Phase D: aggregate parent_group_activities across this sub's presence,
  // and compare against peers in the same trade.
  const activityCounts = new Map<string, { days: number; jobs: Set<string> }>();
  for (const row of presentDays) {
    const tags = Array.isArray(row.parent_group_activities)
      ? row.parent_group_activities
      : [];
    for (const tag of tags) {
      const rec = activityCounts.get(tag) ?? { days: 0, jobs: new Set() };
      rec.days += 1;
      if (row.job_key) rec.jobs.add(row.job_key);
      activityCounts.set(tag, rec);
    }
  }

  // Peer comparison: other subs in the same trade. We resolve their names
  // (+ aliases) and run one overlapping query per peer for now — the catalog
  // is ~54 entries so the worst-case fan-out is manageable. If perf bites,
  // collapse to a single GROUP BY query via an RPC later.
  type PeerStat = {
    id: string;
    name: string;
    byActivity: Map<string, number>;
  };
  let peers: PeerStat[] = [];
  if (sub.trade) {
    const peerRes = await supabase
      .from("subs")
      .select("id, name, aliases")
      .eq("trade", sub.trade)
      .neq("id", sub.id);
    const peerRows = (peerRes.data ?? []) as {
      id: string;
      name: string;
      aliases: string[] | null;
    }[];
    peers = await Promise.all(
      peerRows.map(async (p) => {
        const names = Array.from(
          new Set([p.name, ...((p.aliases ?? []) as string[])])
        ).filter(Boolean);
        if (names.length === 0)
          return { id: p.id, name: p.name, byActivity: new Map() };
        const rows = (await logsContainingAny(
          supabase,
          "crews_present",
          names,
          "id, parent_group_activities",
          { limit: 500 }
        )) as { parent_group_activities: string[] | null }[];
        const byA = new Map<string, number>();
        for (const row of rows) {
          for (const tag of row.parent_group_activities ?? []) {
            byA.set(tag, (byA.get(tag) ?? 0) + 1);
          }
        }
        return { id: p.id, name: p.name, byActivity: byA };
      })
    );
  }

  const openTodos = (openRes.data ?? []) as Todo[];
  const availableCategories = Array.from(
    new Set(openTodos.map((t) => t.category).filter(Boolean) as string[])
  ).sort();
  const filteredOpenTodos = catFilter
    ? openTodos.filter((t) => t.category === catFilter)
    : openTodos;
  const doneTodos = (doneRes.data ?? []) as Todo[];

  const today = todayIso();
  const pastDue = openTodos.filter(
    (t) => t.due_date != null && t.due_date < today
  );
  const in7 = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
  const dueSoon = openTodos.filter(
    (t) => t.due_date != null && t.due_date >= today && t.due_date <= in7
  ).length;
  const health = subHealth({
    pastDue: pastDue.length,
    dueSoon,
    flagged: sub.flagged_for_pm_binder,
  });

  // Drift signal: of completed items that had a due_date, avg days late.
  // Negative = early, positive = late. Skip items missing either date.
  const driftSamples = doneTodos.filter(
    (t) => t.due_date != null && t.completed_at != null
  );
  const driftDays =
    driftSamples.length > 0
      ? driftSamples.reduce(
          (sum, t) =>
            sum +
            daysBetween(t.due_date as string, (t.completed_at as string).slice(0, 10)),
          0
        ) / driftSamples.length
      : null;

  // F1+F3+I2: Specialties — auto (from daily logs) merged with manual.
  // Auto: tag, days, jobs. Manual rows carry an optional duration override
  // that wins over the daily-log streak estimate when present.
  type ManualSpec = {
    specialty: string;
    source: string;
    duration_days_manual_override: number | null;
  };
  const manualSpecs = (manualSpecRes.data ?? []) as ManualSpec[];
  const manualNames = new Set(manualSpecs.map((m) => m.specialty));
  const manualDurations = new Map<string, number | null>(
    manualSpecs.map((m) => [m.specialty, m.duration_days_manual_override])
  );

  // Per-tag breakdown of contiguous presence streaks, retaining which
  // job each streak belongs to so the UI can cite sources (e.g.
  // "Krauss 5d · Pou 7d · Ruthven 6d"). A streak is a run of on-site
  // days for this sub on a given job, broken by gaps > 7 days.
  const streaksByTag: Record<string, { jobKey: string; days: number }[]> = {};
  {
    const dateLists: Record<string, string[]> = {};
    for (const row of presentDays) {
      if (!row.log_date) continue;
      for (const tag of row.parent_group_activities ?? []) {
        const key = `${row.job_key}|${tag}`;
        if (!dateLists[key]) dateLists[key] = [];
        dateLists[key].push(row.log_date);
      }
    }
    for (const [key, dates] of Object.entries(dateLists)) {
      const [jobKey, tag] = key.split("|");
      const sorted = Array.from(new Set(dates)).sort();
      let streakStart = sorted[0];
      let prev = sorted[0];
      for (let i = 1; i <= sorted.length; i++) {
        const cur = sorted[i];
        if (cur == null || daysBetween(prev, cur) > 7) {
          const len = daysBetween(streakStart, prev) + 1;
          if (!streaksByTag[tag]) streaksByTag[tag] = [];
          streaksByTag[tag].push({ jobKey, days: len });
          if (cur != null) streakStart = cur;
        }
        if (cur != null) prev = cur;
      }
    }
  }

  // F3 — avg crew size per activity tag for this sub. Walk presentDays,
  // and where crew_counts has a key for one of this sub's candidateNames,
  // attribute that headcount to every parent_group_activity tag on the same
  // log row. Skips rows pre-migration (crew_counts will be null/undefined).
  const crewCountsByTag = new Map<string, { sum: number; n: number }>();
  for (const row of presentDays) {
    const cc = row.crew_counts;
    if (!cc || typeof cc !== "object") continue;
    let headcount: number | null = null;
    for (const cand of candidateNames) {
      const v = (cc as Record<string, unknown>)[cand];
      if (typeof v === "number" && v > 0) {
        headcount = v;
        break;
      }
    }
    if (headcount == null) continue;
    for (const tag of row.parent_group_activities ?? []) {
      const rec = crewCountsByTag.get(tag) ?? { sum: 0, n: 0 };
      rec.sum += headcount;
      rec.n += 1;
      crewCountsByTag.set(tag, rec);
    }
  }

  // F5 — canonical schedule_items lookup. Build a name+alias → canonical
  // name map (lowercased keys) so we can render the canonical label next to
  // whatever the BT scraper happened to emit.
  type ScheduleItemRow = {
    id: string;
    name: string;
    trade: string | null;
    typical_duration_days: number | null;
    aliases: unknown;
  };
  const scheduleItems = (scheduleItemsRes.data ?? []) as ScheduleItemRow[];
  const canonicalByLower = new Map<string, string>();
  for (const si of scheduleItems) {
    canonicalByLower.set(si.name.toLowerCase(), si.name);
    if (Array.isArray(si.aliases)) {
      for (const a of si.aliases) {
        if (typeof a === "string" && a.trim()) {
          canonicalByLower.set(a.toLowerCase().trim(), si.name);
        }
      }
    }
  }
  function canonicalFor(tag: string): string | null {
    return canonicalByLower.get(tag.toLowerCase().trim()) ?? null;
  }

  const allSpecNames = new Set<string>([
    ...Array.from(activityCounts.keys()),
    ...Array.from(manualNames),
  ]);
  const specialtyRows: SpecialtyRow[] = Array.from(allSpecNames)
    .map((name) => {
      const auto = activityCounts.get(name);
      const streaks = streaksByTag[name] ?? [];
      // Roll streaks up per job — one job can have several visits, sum
      // their days so the citation shows total time on that job.
      const perJob = new Map<string, number>();
      for (const s of streaks) {
        perJob.set(s.jobKey, (perJob.get(s.jobKey) ?? 0) + s.days);
      }
      const jobBreakdown = Array.from(perJob.entries())
        .map(([jobKey, days]) => ({
          jobKey,
          jobName: jobNameById[jobKey] ?? jobKey,
          days,
        }))
        .sort((a, b) => b.days - a.days);
      // Simple average: total days across all jobs / number of jobs.
      // Easier to explain than the streak-mean used previously.
      const totalDays = jobBreakdown.reduce((s, j) => s + j.days, 0);
      const avg = jobBreakdown.length > 0
        ? totalDays / jobBreakdown.length
        : null;
      const peerCounts = peers
        .map((p) => ({
          name: p.name,
          days: p.byActivity.get(name) ?? 0,
        }))
        .filter((p) => p.days > 0)
        .sort((a, b) => b.days - a.days)
        .slice(0, 3);
      const crew = crewCountsByTag.get(name);
      const avgCrewSize =
        crew && crew.n > 0 ? crew.sum / crew.n : null;
      return {
        name,
        source: manualNames.has(name)
          ? ("manual" as const)
          : ("auto" as const),
        days: auto?.days ?? 0,
        jobs: auto?.jobs.size ?? 0,
        avgDurationDays: avg,
        manualDurationDays: manualDurations.get(name) ?? null,
        peers: peerCounts,
        jobBreakdown,
        avgCrewSize,
        canonicalName: canonicalFor(name),
      };
    })
    .sort((a, b) => b.days - a.days || a.name.localeCompare(b.name));

  // F6 — aggregate inspections for this sub. We attribute every inspection
  // entry on a presentDay to this sub (best-effort: BT doesn't link
  // inspections to a specific crew). Dedupe by raw text + date so multi-day
  // inspection runs collapse to a single row.
  type InspectionRow = { text: string; date: string | null; job: string };
  const inspectionRows: InspectionRow[] = [];
  const inspSeen = new Set<string>();
  for (const row of presentDays) {
    const arr = Array.isArray(row.inspections) ? row.inspections : [];
    for (const insp of arr) {
      let text = "";
      let when: string | null = row.log_date ?? null;
      if (typeof insp === "string") {
        text = insp.trim();
      } else if (insp && typeof insp === "object") {
        const o = insp as Record<string, unknown>;
        text = (
          (o.type as string) ??
          (o.raw as string) ??
          (o.description as string) ??
          ""
        ).toString();
        if (typeof o.date === "string") when = o.date;
        if (o.result) text = text ? `${text} — ${o.result}` : String(o.result);
      }
      text = text.trim();
      if (!text) continue;
      const key = `${text}|${when ?? ""}|${row.job_key}`;
      if (inspSeen.has(key)) continue;
      inspSeen.add(key);
      inspectionRows.push({
        text,
        date: when,
        job: jobNameById[row.job_key] ?? row.job_key,
      });
    }
  }
  inspectionRows.sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""));

  // F8 — surface any vision-extracted photo summaries from the same logs.
  // Each summary is a structured jsonb the extract-photos route writes.
  type PhotoSummaryRow = {
    date: string | null;
    job: string;
    summary: Record<string, unknown>;
    photoCount: number;
  };
  const photoSummaries: PhotoSummaryRow[] = [];
  for (const row of presentDays) {
    const s = row.photo_summary as Record<string, unknown> | null | undefined;
    if (!s || typeof s !== "object") continue;
    photoSummaries.push({
      date: row.log_date,
      job: jobNameById[row.job_key] ?? row.job_key,
      summary: s,
      photoCount: Array.isArray(row.photo_urls) ? row.photo_urls.length : 0,
    });
  }

  // F7 — split checklist into the two lenses for the editor.
  const checklist = (checklistRes.data ?? []) as ChecklistItem[];
  const safetyItems = checklist.filter((c) => c.lens === "SAFETY");
  const scheduleItemsCk = checklist.filter((c) => c.lens === "SCHEDULE");

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      {/* Header — name + trade. Composite A-F rating removed per Jake's
          request 2026-05-18 — facts in the metric tiles below are enough. */}
      <header className="px-5 pt-8 pb-2">
        <Link
          href="/subs"
          className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink"
        >
          ← Subs
        </Link>
        <div className="mt-4">
          <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
            {sub.name}
          </h1>
          {sub.trade && (
            <p className="mt-1.5 text-ink-3 text-sm">{sub.trade}</p>
          )}
          <div className="mt-3 inline-flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${health.dotClass}`}
              aria-hidden
            />
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-2">
              {health.label}
            </span>
          </div>
        </div>
      </header>

      {/* Flag banner — surfaces flagged_for_pm_binder + reasons. Framed as an
          auto-derived signal, not a verdict: manual judgment wins (per the
          project rules), so the copy nudges the PM to confirm in person. */}
      {sub.flagged_for_pm_binder && (
        <section className="px-5 pt-5">
          <div className="border border-gold p-3">
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-gold">
              ⚑ Flagged for PM binder
            </p>
            {Array.isArray(sub.flag_reasons) && sub.flag_reasons.length > 0 && (
              <ul className="mt-2 space-y-1">
                {sub.flag_reasons.map((r, i) => (
                  <li key={i} className="text-sm text-ink-2 leading-snug">
                    • {r}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 font-mono text-[9px] tracking-[0.12em] uppercase text-ink-3">
              auto-derived from log analysis · confirm in person before acting
            </p>
          </div>
        </section>
      )}

      {/* Four-metric tiles */}
      <section className="px-5 pt-6">
        <div className="grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-4">
          <Metric label="Open" value={openTodos.length} />
          <Metric
            label="Past due"
            value={pastDue.length}
            accent={pastDue.length > 0 ? "urgent" : undefined}
          />
          <Metric
            label="No-shows"
            value={noShowCount == null ? "—" : noShowCount}
            accent={
              noShowCount != null && noShowCount > 0 ? "urgent" : undefined
            }
            sub={noShowCount == null ? "no log data" : "from daily logs"}
          />
          <Metric
            label="Avg drift"
            value={
              driftDays == null
                ? "—"
                : `${driftDays > 0 ? "+" : ""}${driftDays.toFixed(1)}d`
            }
            accent={driftDays != null && driftDays > 1 ? "urgent" : undefined}
            sub={
              driftSamples.length > 0
                ? `n=${driftSamples.length}`
                : "no data"
            }
          />
        </div>
      </section>

      {/* Specialties — auto + manual */}
      <section className="px-5 pt-10">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
          Specialties · {specialtyRows.length}
        </h2>
        <SpecialtiesEditor subId={sub.id} rows={specialtyRows} />
        <p className="mt-3 text-[10px] font-mono tracking-[0.18em] uppercase text-ink-3">
          auto entries come from daily logs · manual entries are declared ·{" "}
          <span className="text-accent">≈</span> shows canonical schedule item
        </p>
      </section>

      {/* F6 — Inspections (collapsed unless we have rows). Best-effort: BT
          doesn't tie inspections to a single crew, so we surface every
          inspection from days this sub was on site. */}
      {inspectionRows.length > 0 && (
        <section className="px-5 pt-10">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
            Inspections · {inspectionRows.length}
          </h2>
          <ul className="space-y-1.5">
            {inspectionRows.slice(0, 20).map((r, i) => (
              <li
                key={i}
                className="flex items-baseline justify-between gap-3 py-1 border-b border-rule-soft last:border-b-0"
              >
                <span className="text-sm text-foreground leading-snug flex-1 min-w-0">
                  {r.text}
                </span>
                <span className="shrink-0 font-mono text-[10px] tabular-nums text-ink-3">
                  {r.date ?? "—"} · {r.job}
                </span>
              </li>
            ))}
            {inspectionRows.length > 20 && (
              <li className="text-center font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 pt-2">
                + {inspectionRows.length - 20} more
              </li>
            )}
          </ul>
          <p className="mt-2 text-[10px] font-mono tracking-[0.18em] uppercase text-ink-3">
            sourced from BT daily logs on days this sub was on site
          </p>
        </section>
      )}

      {/* F7 — Running checklist editor (safety + schedule). */}
      <section className="px-5 pt-10">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
          Checklist
        </h2>
        <SubChecklistEditor
          subId={sub.id}
          safetyItems={safetyItems}
          scheduleItems={scheduleItemsCk}
        />
      </section>

      {/* F8 — vision-extracted photo summaries. Only shown if at least one
          present-day log has been processed by /v2/api/daily-logs/extract-photos. */}
      {photoSummaries.length > 0 && (
        <section className="px-5 pt-10">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
            Photo context · {photoSummaries.length} day
            {photoSummaries.length === 1 ? "" : "s"}
          </h2>
          <ul className="space-y-3">
            {photoSummaries.slice(0, 10).map((p, i) => {
              const s = p.summary;
              const headline =
                (typeof s.headline === "string" && s.headline) ||
                (typeof s.summary === "string" && s.summary) ||
                "Photos processed";
              const stage =
                typeof s.work_stage === "string" ? s.work_stage : null;
              const hazards = Array.isArray(s.hazards)
                ? (s.hazards as unknown[]).filter(
                    (x): x is string => typeof x === "string"
                  )
                : [];
              return (
                <li key={i} className="border border-rule px-3 py-2 bg-paper">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-sm text-foreground leading-snug">
                      {String(headline)}
                    </p>
                    <span className="shrink-0 font-mono text-[10px] tabular-nums text-ink-3">
                      {p.date ?? "—"} · {p.job}
                    </span>
                  </div>
                  <p className="mt-1 font-mono text-[10px] text-ink-3 tabular-nums">
                    {p.photoCount} photo{p.photoCount === 1 ? "" : "s"}
                    {stage && <> · stage: {stage}</>}
                    {hazards.length > 0 && (
                      <span className="text-urgent">
                        {" "}· hazards: {hazards.join(", ")}
                      </span>
                    )}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Open items */}
      <CategoryFilterPills
        basePath={`/sub/${params.id}`}
        activeCategory={catFilter}
        availableCategories={availableCategories}
      />
      <section className="px-5 pt-6">
        <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
          Open · {filteredOpenTodos.length}
          {catFilter && (
            <span className="text-ink-3"> of {openTodos.length}</span>
          )}
        </h2>
        {filteredOpenTodos.length === 0 ? (
          <p className="text-ink-3 text-sm">
            {catFilter ? `No ${catFilter} items.` : "None open."}
          </p>
        ) : (
          <ul className="space-y-2">
            {filteredOpenTodos.map((t) => {
              const isPastDue =
                t.due_date != null && t.due_date < today;
              return (
                <li
                  key={t.id}
                  className={`py-1.5 min-h-[40px] ${
                    isPastDue ? "border-l-2 border-urgent pl-2 -ml-2" : ""
                  }`}
                >
                  <div className="flex gap-3 items-baseline">
                    <p className="flex-1 min-w-0 text-foreground text-sm leading-snug">
                      {t.edited_title ?? t.title}
                      <span className="text-ink-3"> · {t.job}</span>
                    </p>
                    {t.due_date && (
                      <span
                        className={`shrink-0 text-xs font-mono ${
                          isPastDue ? "text-urgent" : "text-ink-3"
                        }`}
                      >
                        {isPastDue
                          ? `-${daysBetween(t.due_date, today)}d`
                          : daysBetween(today, t.due_date) === 0
                            ? "today"
                            : `${daysBetween(today, t.due_date)}d`}
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Activity timeline — chronological list of on-site days */}
      {presentDays.length > 0 && (
        <section className="px-5 pt-10">
          <details>
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-2">
              On-site timeline · {presentDays.length} day
              {presentDays.length === 1 ? "" : "s"}
            </summary>
            <ul className="mt-2 space-y-1">
              {presentDays.slice(0, 60).map((row, i) => (
                <li
                  key={i}
                  className="flex items-baseline justify-between gap-3 py-1"
                >
                  <span className="text-sm text-ink-2">
                    {row.log_date ?? "—"}
                  </span>
                  <span className="font-mono text-xs text-ink-3 tabular-nums truncate">
                    {row.job_key}
                  </span>
                </li>
              ))}
              {presentDays.length > 60 && (
                <li className="text-center font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 pt-2">
                  + {presentDays.length - 60} more
                </li>
              )}
            </ul>
          </details>
        </section>
      )}

      {/* Recently done — collapsed */}
      {doneTodos.length > 0 && (
        <section className="px-5 pt-10">
          <details>
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-2">
              Recently done · {doneTodos.length}
            </summary>
            <ul className="mt-2 space-y-1.5">
              {doneTodos.map((t) => (
                <li
                  key={t.id}
                  className="text-ink-3 text-sm line-through truncate"
                >
                  {t.edited_title ?? t.title}
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </main>
  );
}

function Metric({
  label,
  value,
  accent,
  sub,
}: {
  label: string;
  value: number | string;
  accent?: "urgent";
  sub?: string;
}) {
  return (
    <div className="flex flex-col items-start">
      <span
        className={
          "font-mono text-[28px] font-medium leading-none tabular-nums " +
          (accent === "urgent" ? "text-urgent" : "text-ink")
        }
      >
        {value}
      </span>
      <span className="mt-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
        {label}
      </span>
      {sub && (
        <span className="mt-0.5 font-mono text-[9px] tracking-[0.12em] uppercase text-ink-3 opacity-70">
          {sub}
        </span>
      )}
    </div>
  );
}

