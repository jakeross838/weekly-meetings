// Standalone test for sub-activity — same no-framework harness as
// sub-health.test.ts. Compiled by `npm test` and run under node.

import assert from "node:assert/strict";
import {
  DailyLogLite,
  shortJob,
  buildNameIndex,
  latestLogDate,
  aggregateSubActivity,
  aggregateAllSubs,
} from "./sub-activity";

const failures: string[] = [];
let passed = 0;
function check(desc: string, fn: () => void) {
  try {
    fn();
    passed++;
  } catch (e) {
    failures.push(`✗ ${desc}\n    ${(e as Error).message}`);
  }
}

// A small fixture: one stucco sub (with an alias) on two jobs + a no-show,
// plus a painter so we prove name-bucketing doesn't cross subs.
const STUCCO = "Jeff Watts Plastering and Stucco";
const STUCCO_ALIAS = "Watts Stucco";
const PAINT = "TNT Custom Painting";

const logs: DailyLogLite[] = [
  // Fish — stucco present 3 distinct days (one date duplicated to prove dedupe)
  { log_date: "2026-05-01", job_key: "Fish-715 North Shore Dr", crews_present: [STUCCO], absent_crews: [], activity: "Stucco" },
  { log_date: "2026-05-02", job_key: "Fish-715 North Shore Dr", crews_present: [STUCCO, PAINT], absent_crews: [], activity: "Stucco/Paint" },
  { log_date: "2026-05-02", job_key: "Fish-715 North Shore Dr", crews_present: [STUCCO], absent_crews: [], activity: "Stucco" },
  { log_date: "2026-05-05", job_key: "Fish-715 North Shore Dr", crews_present: [STUCCO_ALIAS], absent_crews: [], activity: "Stucco" },
  // Harlee — stucco present 2 days, the most recent (current-window) activity
  { log_date: "2026-06-04", job_key: "Harlee-22 Bay St", crews_present: [STUCCO], absent_crews: [], activity: "Stucco" },
  { log_date: "2026-06-05", job_key: "Harlee-22 Bay St", crews_present: [STUCCO], absent_crews: [PAINT], activity: "Stucco" },
  // Stucco no-show on Fish, long ago (not current)
  { log_date: "2026-05-03", job_key: "Fish-715 North Shore Dr", crews_present: [PAINT], absent_crews: [STUCCO], activity: "Paint" },
  // a null-date row must be ignored
  { log_date: null, job_key: "Ghost-0", crews_present: [STUCCO], absent_crews: [], activity: null },
];

const latest = "2026-06-05";

check("shortJob splits on first hyphen", () => {
  assert.equal(shortJob("Fish-715 North Shore Dr"), "Fish");
  assert.equal(shortJob("Harlee-22 Bay St"), "Harlee");
  assert.equal(shortJob("NoHyphen"), "NoHyphen");
});

check("latestLogDate ignores nulls and finds max", () => {
  assert.equal(latestLogDate(logs), "2026-06-05");
});

check("buildNameIndex maps name + aliases (case-insensitive)", () => {
  const idx = buildNameIndex([
    { id: "s1", name: STUCCO, aliases: [STUCCO_ALIAS] },
  ]);
  assert.equal(idx.get(STUCCO.toLowerCase()), "s1");
  assert.equal(idx.get("watts stucco"), "s1");
});

const act = aggregateSubActivity(logs, [STUCCO, STUCCO_ALIAS], { latest });

check("days-per-job dedupes dates and counts via aliases", () => {
  const fish = act.jobs.find((j) => j.jobShort === "Fish");
  const harlee = act.jobs.find((j) => j.jobShort === "Harlee");
  assert.ok(fish, "Fish job present");
  assert.ok(harlee, "Harlee job present");
  assert.equal(fish!.days, 3, "Fish = 3 distinct days (05-01,05-02,05-05)");
  assert.equal(harlee!.days, 2, "Harlee = 2 distinct days");
  assert.equal(fish!.firstDate, "2026-05-01");
  assert.equal(fish!.lastDate, "2026-05-05");
});

check("jobs sorted by days desc (Fish before Harlee)", () => {
  assert.equal(act.jobs[0].jobShort, "Fish");
});

check("totalDays counts distinct on-site dates across jobs", () => {
  // 05-01, 05-02, 05-05, 06-04, 06-05 = 5
  assert.equal(act.totalDays, 5);
});

check("currentJobs windows on the anchor, not wall-clock", () => {
  // Only Harlee (06-04/06-05) is within 14d of 06-05; Fish (05-05) is not.
  assert.equal(act.currentJobs.length, 1);
  assert.equal(act.currentJobs[0].jobShort, "Harlee");
  assert.equal(act.currentJobs[0].daysAgo, 0); // last seen on the anchor day
});

check("absences captured with date + job, most recent first", () => {
  assert.equal(act.absenceCount, 1);
  assert.equal(act.absences[0].date, "2026-05-03");
  assert.equal(act.absences[0].jobShort, "Fish");
});

check("lastSeen is the freshest on-site date", () => {
  assert.equal(act.lastSeen, "2026-06-05");
});

// All-subs pass must bucket crews to the right sub and not bleed across.
const idx = buildNameIndex([
  { id: "stucco", name: STUCCO, aliases: [STUCCO_ALIAS] },
  { id: "paint", name: PAINT, aliases: [] },
]);
const all = aggregateAllSubs(logs, idx, { latest });

check("aggregateAllSubs: stucco stats match single-sub pass", () => {
  const s = all.get("stucco");
  assert.ok(s, "stucco present");
  assert.equal(s!.totalDays, 5);
  assert.equal(s!.absenceCount, 1);
  assert.equal(s!.lastSeen, "2026-06-05");
  assert.deepEqual(s!.currentJobs, ["Harlee"]);
});

check("aggregateAllSubs: painter bucketed separately, with its own absence", () => {
  const p = all.get("paint");
  assert.ok(p, "paint present");
  // painter present 05-02 and 05-03 = 2 days; absent once on Harlee 06-05
  assert.equal(p!.totalDays, 2);
  assert.equal(p!.absenceCount, 1);
  assert.deepEqual(p!.currentJobs, []); // last present 05-03, outside window
});

check("unknown crew names are ignored (no phantom sub)", () => {
  const extra: DailyLogLite[] = [
    { log_date: "2026-06-05", job_key: "X-1", crews_present: ["Nobody Co"], absent_crews: [], activity: null },
  ];
  const m = aggregateAllSubs(extra, idx, { latest });
  assert.equal(m.size, 0);
});

// --- review fixes: absence dedupe, present-wins, list/detail parity ---

check("duplicate absent rows for one (job,date) count once, both paths", () => {
  const dup: DailyLogLite[] = [
    { log_date: "2026-06-05", job_key: "Fish-715 North Shore Dr", crews_present: [PAINT], absent_crews: [STUCCO], activity: null },
    { log_date: "2026-06-05", job_key: "Fish-715 North Shore Dr", crews_present: [PAINT], absent_crews: [STUCCO_ALIAS], activity: null },
  ];
  const single = aggregateSubActivity(dup, [STUCCO, STUCCO_ALIAS], { latest });
  assert.equal(single.absenceCount, 1, "single-sub dedupes (job,date) absence");
  const m = aggregateAllSubs(dup, idx, { latest });
  assert.equal(m.get("stucco")!.absenceCount, 1, "all-subs dedupes too");
});

check("present wins: same crew present AND absent on one log → 0 absences", () => {
  const both: DailyLogLite[] = [
    { log_date: "2026-06-05", job_key: "Fish-715 North Shore Dr", crews_present: [STUCCO], absent_crews: [STUCCO], activity: null },
  ];
  const single = aggregateSubActivity(both, [STUCCO], { latest });
  assert.equal(single.absenceCount, 0, "present wins (single)");
  assert.equal(single.totalDays, 1, "still counts the present day");
  const m = aggregateAllSubs(both, idx, { latest });
  assert.equal(m.get("stucco")!.absenceCount, 0, "present wins (all-subs)");
});

check("current-job multiplicity agrees across same-short job_keys", () => {
  // Two DISTINCT job_keys that share the short name "Bay", both recent.
  const same: DailyLogLite[] = [
    { log_date: "2026-06-04", job_key: "Bay-1 First St", crews_present: [STUCCO], absent_crews: [], activity: null },
    { log_date: "2026-06-05", job_key: "Bay-2 Second St", crews_present: [STUCCO], absent_crews: [], activity: null },
  ];
  const single = aggregateSubActivity(same, [STUCCO], { latest });
  const m = aggregateAllSubs(same, idx, { latest });
  assert.equal(single.currentJobs.length, 2, "detail enumerates both job_keys");
  assert.equal(
    m.get("stucco")!.currentJobs.length,
    2,
    "list count matches detail (keyed by job_key, not short name)"
  );
});

check("lastSeenDaysAgo is set relative to the anchor", () => {
  const m = aggregateAllSubs(logs, idx, { latest });
  // stucco last seen on the anchor day 06-05 → 0 days ago
  assert.equal(m.get("stucco")!.lastSeenDaysAgo, 0);
});

check("absence carries evidence (logId, activity, notes, jobKey)", () => {
  const ev: DailyLogLite[] = [
    {
      id: "log-123",
      log_date: "2026-06-05",
      job_key: "Pou-109 Seagrape Ln",
      crews_present: [PAINT],
      absent_crews: [STUCCO],
      activity: "Tile/Paint",
      notes: "Activity Summary (...)\n\nStucco crew was a no-show today.",
    },
  ];
  const a = aggregateSubActivity(ev, [STUCCO], { latest });
  assert.equal(a.absences.length, 1);
  const e = a.absences[0];
  assert.equal(e.logId, "log-123");
  assert.equal(e.jobKey, "Pou-109 Seagrape Ln");
  assert.equal(e.activity, "Tile/Paint");
  assert.ok((e.notes ?? "").includes("no-show"), "notes carried for citation");
});

if (failures.length > 0) {
  console.error(`\n${failures.length} FAILED, ${passed} passed:\n`);
  console.error(failures.join("\n\n"));
  process.exit(1);
}
console.log(`All ${passed} sub-activity tests passed.`);
