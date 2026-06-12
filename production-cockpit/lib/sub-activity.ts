// sub-activity — turns Buildertrend daily-log presence/absence into the three
// facts the subs UI cares about:
//   1. Days on each job   — distinct on-site dates per job (from crews_present).
//   2. Currently working  — jobs the sub appeared on inside a recency window of
//                           the freshest log we hold (so a lagging scrape still
//                           reads "on site", not "idle").
//   3. Absences           — count + the actual (date, job) events (absent_crews).
//
// crews_present / absent_crews are jsonb arrays of *exact* legal crew names.
// In production every logged crew name matches a subs.name or alias (verified
// 85/85), so we index name → sub id and bucket in one linear pass — no fuzzy
// matching, no per-sub jsonb fan-out. All functions are pure and take the
// "latest" anchor date explicitly (or derive it from the logs) so callers and
// tests stay deterministic — no Date.now() in here.

export interface DailyLogLite {
  log_date: string | null; // "YYYY-MM-DD"
  job_key: string; // "Fish-715 North Shore Dr"
  crews_present: string[] | null;
  absent_crews: string[] | null;
  activity: string | null; // "Tile/Trim/Drywall" — job-level day summary
}

export interface JobDays {
  jobKey: string;
  jobShort: string;
  days: number; // distinct on-site dates on this job
  firstDate: string;
  lastDate: string;
}

export interface CurrentJob {
  jobKey: string;
  jobShort: string;
  lastDate: string;
  daysAgo: number; // relative to the anchor (freshest log), not wall-clock
}

export interface AbsenceEvent {
  date: string;
  jobShort: string;
}

export interface SubActivity {
  jobs: JobDays[]; // every job worked, most days first
  totalDays: number; // distinct on-site dates across all jobs (a 2-job day = 1)
  currentJobs: CurrentJob[]; // recency-windowed, most recent first
  absenceCount: number;
  absences: AbsenceEvent[]; // most recent first
  lastSeen: string | null; // freshest on-site date, or null if never logged
}

// Per-sub summary for the list page — the cheap subset, computed for all subs
// in one pass so /subs never fans out per sub.
export interface SubListStat {
  totalDays: number;
  absenceCount: number;
  lastSeen: string | null;
  lastSeenDaysAgo: number | null; // vs the anchor (freshest log), null if never
  currentJobs: string[]; // short job names, most recent first
}

// "Currently working" window — anchored on the freshest log date, not
// wall-clock today, so a lagging scrape still reads "on site". The bound is
// inclusive (lastDate >= anchor - windowDays), i.e. it spans the anchor plus
// the `windowDays` days before it.
const DEFAULT_WINDOW_DAYS = 14;
// Within this many days of the anchor a sub reads as "live" (solid green);
// older-but-still-in-window presence renders muted. Keeps a "13d ago" entry
// from wearing the same live dot as a same-day one.
export const FRESH_ON_SITE_DAYS = 3;

function nkey(s: string): string {
  return s.trim().toLowerCase();
}

export function shortJob(jobKey: string): string {
  if (!jobKey) return jobKey;
  return jobKey.split("-")[0].trim() || jobKey;
}

function daysBetween(a: string, b: string): number {
  // Both ISO YYYY-MM-DD → parsed as UTC midnight, so this is exact.
  return Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);
}

// Build a name/alias → sub id index. Last writer wins on collisions, which is
// fine: a crew name maps to one sub, and the catalog is curated.
export function buildNameIndex(
  subs: { id: string; name: string; aliases?: string[] | null }[]
): Map<string, string> {
  const idx = new Map<string, string>();
  for (const s of subs) {
    if (s.name) idx.set(nkey(s.name), s.id);
    for (const a of s.aliases ?? []) {
      if (a) idx.set(nkey(a), s.id);
    }
  }
  return idx;
}

export function latestLogDate(logs: DailyLogLite[]): string | null {
  let max: string | null = null;
  for (const l of logs) {
    if (l.log_date && (max === null || l.log_date > max)) max = l.log_date;
  }
  return max;
}

// Single-sub aggregation. `names` is the sub's name + aliases (any casing).
export function aggregateSubActivity(
  logs: DailyLogLite[],
  names: string[],
  opts?: { windowDays?: number; latest?: string | null }
): SubActivity {
  const want = new Set(names.map(nkey).filter(Boolean));
  const windowDays = opts?.windowDays ?? DEFAULT_WINDOW_DAYS;
  const latest =
    opts?.latest !== undefined ? opts.latest : latestLogDate(logs);

  // job_key → { jobShort, dates:Set, first, last }
  const perJob = new Map<
    string,
    { jobShort: string; dates: Set<string>; first: string; last: string }
  >();
  const allDates = new Set<string>();
  const absences: AbsenceEvent[] = [];
  const seenAbs = new Set<string>(); // (jobShort|date) — dedupe duplicate logs

  for (const log of logs) {
    const d = log.log_date;
    if (!d) continue;
    const present = log.crews_present ?? [];
    const hit = present.some((c) => c && want.has(nkey(c)));
    if (hit) {
      const rec =
        perJob.get(log.job_key) ??
        ({
          jobShort: shortJob(log.job_key),
          dates: new Set<string>(),
          first: d,
          last: d,
        } as const);
      const r = rec as {
        jobShort: string;
        dates: Set<string>;
        first: string;
        last: string;
      };
      r.dates.add(d);
      if (d < r.first) r.first = d;
      if (d > r.last) r.last = d;
      perJob.set(log.job_key, r);
      allDates.add(d);
    }
    // Present wins: a crew listed in both arrays on one log is a present-day,
    // not an absence. Otherwise dedupe absences by (jobShort|date) so duplicate
    // logs don't inflate the count the way the present-day Sets already prevent.
    const absent = log.absent_crews ?? [];
    if (!hit && absent.some((c) => c && want.has(nkey(c)))) {
      const js = shortJob(log.job_key);
      const k = js + "|" + d;
      if (!seenAbs.has(k)) {
        seenAbs.add(k);
        absences.push({ date: d, jobShort: js });
      }
    }
  }

  const jobs: JobDays[] = Array.from(perJob.entries())
    .map(([jobKey, r]) => ({
      jobKey,
      jobShort: r.jobShort,
      days: r.dates.size,
      firstDate: r.first,
      lastDate: r.last,
    }))
    .sort((a, b) => b.days - a.days || b.lastDate.localeCompare(a.lastDate));

  const cutoff = latest
    ? new Date(Date.parse(latest) - windowDays * 86_400_000)
        .toISOString()
        .slice(0, 10)
    : null;
  const currentJobs: CurrentJob[] = (
    cutoff
      ? jobs.filter((j) => j.lastDate >= cutoff)
      : []
  )
    .map((j) => ({
      jobKey: j.jobKey,
      jobShort: j.jobShort,
      lastDate: j.lastDate,
      daysAgo: latest ? daysBetween(j.lastDate, latest) : 0,
    }))
    .sort((a, b) => b.lastDate.localeCompare(a.lastDate));

  absences.sort((a, b) => b.date.localeCompare(a.date));

  let lastSeen: string | null = null;
  for (const d of Array.from(allDates))
    if (lastSeen === null || d > lastSeen) lastSeen = d;

  return {
    jobs,
    totalDays: allDates.size,
    currentJobs,
    absenceCount: absences.length,
    absences,
    lastSeen,
  };
}

// All-subs aggregation for the list page — one linear pass over the logs,
// bucketing each present/absent crew name straight to its sub id.
export function aggregateAllSubs(
  logs: DailyLogLite[],
  nameIndex: Map<string, string>,
  opts?: { windowDays?: number; latest?: string | null }
): Map<string, SubListStat> {
  const windowDays = opts?.windowDays ?? DEFAULT_WINDOW_DAYS;
  const latest =
    opts?.latest !== undefined ? opts.latest : latestLogDate(logs);
  const cutoff = latest
    ? new Date(Date.parse(latest) - windowDays * 86_400_000)
        .toISOString()
        .slice(0, 10)
    : null;

  type Acc = {
    dates: Set<string>;
    absences: number;
    absKeys: Set<string>; // (jobShort|date) already counted — dedupe dup logs
    lastSeen: string | null;
    // keyed by full job_key (not jobShort) so multiplicity matches the detail
    // page's per-job_key "On site now" list; short label kept for display.
    jobLast: Map<string, { jobShort: string; last: string }>;
  };
  const acc = new Map<string, Acc>();
  const get = (id: string): Acc => {
    let a = acc.get(id);
    if (!a) {
      a = {
        dates: new Set(),
        absences: 0,
        absKeys: new Set(),
        lastSeen: null,
        jobLast: new Map(),
      };
      acc.set(id, a);
    }
    return a;
  };

  for (const log of logs) {
    const d = log.log_date;
    if (!d) continue;
    const jobShort = shortJob(log.job_key);
    const presentIds = new Set<string>();
    for (const c of log.crews_present ?? []) {
      if (!c) continue;
      const id = nameIndex.get(nkey(c));
      if (!id) continue;
      presentIds.add(id);
      const a = get(id);
      a.dates.add(d);
      if (a.lastSeen === null || d > a.lastSeen) a.lastSeen = d;
      const prev = a.jobLast.get(log.job_key);
      if (!prev || d > prev.last) a.jobLast.set(log.job_key, { jobShort, last: d });
    }
    for (const c of log.absent_crews ?? []) {
      if (!c) continue;
      const id = nameIndex.get(nkey(c));
      if (!id || presentIds.has(id)) continue; // present wins
      const a = get(id);
      const k = jobShort + "|" + d;
      if (a.absKeys.has(k)) continue; // dedupe duplicate logs
      a.absKeys.add(k);
      a.absences += 1;
    }
  }

  const out = new Map<string, SubListStat>();
  for (const [id, a] of Array.from(acc.entries())) {
    const currentJobs = Array.from(a.jobLast.values())
      .filter((v) => (cutoff ? v.last >= cutoff : false))
      .sort((x, y) => y.last.localeCompare(x.last))
      .map((v) => v.jobShort);
    out.set(id, {
      totalDays: a.dates.size,
      absenceCount: a.absences,
      lastSeen: a.lastSeen,
      lastSeenDaysAgo:
        a.lastSeen && latest ? daysBetween(a.lastSeen, latest) : null,
      currentJobs,
    });
  }
  return out;
}
