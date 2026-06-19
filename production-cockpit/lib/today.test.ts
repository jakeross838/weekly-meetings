// Tests for businessToday / businessDateOffset — Eastern-anchored "today".

import { businessToday, businessDateOffset } from "./today";

let passed = 0;
function eq(a: string, b: string, msg: string) {
  if (a !== b) throw new Error(`FAIL: ${msg}\n  got "${a}" expected "${b}"`);
  passed++;
}
function ok(cond: boolean, msg: string) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  passed++;
}

// The bug this guards: 02:30 UTC on 2026-06-20 is still 22:30 on 2026-06-19 in
// Eastern. A naive toISOString().slice(0,10) returns "2026-06-20"; we must
// return "2026-06-19".
eq(businessToday(new Date("2026-06-20T02:30:00Z")), "2026-06-19", "late-evening ET stays prior day");
// Midday UTC is the same calendar day in ET.
eq(businessToday(new Date("2026-06-19T16:00:00Z")), "2026-06-19", "midday matches");
// Winter (EST, UTC-5): 04:30 UTC 2026-01-02 is 23:30 2026-01-01 ET.
eq(businessToday(new Date("2026-01-02T04:30:00Z")), "2026-01-01", "EST late evening");

// Offsets are exact whole-day shifts off the ET anchor.
const anchor = new Date("2026-06-19T16:00:00Z");
eq(businessDateOffset(0, anchor), "2026-06-19", "offset 0 == today");
eq(businessDateOffset(7, anchor), "2026-06-26", "+7 days");
eq(businessDateOffset(-7, anchor), "2026-06-12", "-7 days");
eq(businessDateOffset(1, new Date("2026-06-30T16:00:00Z")), "2026-07-01", "month rollover");

// Shape sanity for the live call.
ok(/^\d{4}-\d{2}-\d{2}$/.test(businessToday()), "live businessToday is YYYY-MM-DD");

console.log(`All ${passed} today tests passed.`);
