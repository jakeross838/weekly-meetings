// Standalone test for scrubRelativeDates — no test framework in this repo, so
// this compiles with the project's tsc and runs under node:
//   npx tsc lib/scrub-relative-dates.ts lib/scrub-relative-dates.test.ts \
//     --outDir .tmp-tdd --module commonjs --target ES2020 --skipLibCheck \
//     --moduleResolution node
//   node .tmp-tdd/lib/scrub-relative-dates.test.js
//
// Reference date for every case: 2026-05-20, which is a WEDNESDAY.

import assert from "node:assert/strict";
import { scrubRelativeDates } from "./scrub-relative-dates";

const REF = "2026-05-20"; // Wednesday

const cases: Array<[string, string, string]> = [
  // [description, input title, expected output]

  // --- single relative words resolve to an exact ISO date ---
  ["tomorrow", "Confirm slab tomorrow", "Confirm slab 2026-05-21"],
  ["today", "Call client today", "Call client 2026-05-20"],
  ["tonight", "Send recap tonight", "Send recap 2026-05-20"],
  ["yesterday", "Note inspection from yesterday", "Note inspection from 2026-05-19"],
  ["day after tomorrow", "Pour footer day after tomorrow", "Pour footer 2026-05-22"],

  // --- weekdays: 'this/by/<bare>' = next on-or-after ref; 'next' = the week after ---
  ["by Friday", "Confirm drywall start by Friday", "Confirm drywall start 2026-05-22"],
  ["this Friday", "Schedule inspection this Friday", "Schedule inspection 2026-05-22"],
  ["bare Friday", "Order tile Friday", "Order tile 2026-05-22"],
  ["next Friday", "Walter to start next Friday", "Walter to start 2026-05-29"],
  ["by Monday", "Submit RFI by Monday", "Submit RFI 2026-05-25"],
  ["next Monday", "Frame walls next Monday", "Frame walls 2026-06-01"],
  ["bare same-day weekday (Wednesday)", "Meet GC Wednesday", "Meet GC 2026-05-20"],

  // --- week / month spans that map to a concrete offset ---
  ["next week", "Deliver windows next week", "Deliver windows 2026-05-27"],
  ["by next week", "Get pricing by next week", "Get pricing 2026-05-27"],
  ["end of month", "Close out permits end of month", "Close out permits 2026-05-31"],
  ["by the end of the month", "Invoice by the end of the month", "Invoice 2026-05-31"],

  // --- explicit "in N days/weeks" ---
  ["in 3 days", "Backcharge sub in 3 days", "Backcharge sub 2026-05-23"],
  ["in 2 weeks", "Re-pour in 2 weeks", "Re-pour 2026-06-03"],

  // --- genuinely vague phrases get stripped (no date to substitute) ---
  ["ASAP", "Order the tile ASAP", "Order the tile"],
  ["soon", "Send the proposal soon", "Send the proposal"],
  ["shortly", "Follow up shortly", "Follow up"],
  ["this week (vague span -> strip)", "Pour the slab this week", "Pour the slab"],
  ["by end of week (strip)", "Finish punch by end of week", "Finish punch"],
  ["in a few days", "Reschedule in a few days", "Reschedule"],

  // --- whole-sentence + multiple phrases ---
  [
    "sentence with tomorrow",
    "Walter to confirm drywall start tomorrow",
    "Walter to confirm drywall start 2026-05-21",
  ],
  [
    "mid-sentence by Friday",
    "Schedule inspection by Friday for Krauss",
    "Schedule inspection 2026-05-22 for Krauss",
  ],
  [
    "two phrases in one title",
    "Call client today and follow up tomorrow",
    "Call client 2026-05-20 and follow up 2026-05-21",
  ],

  // --- things that must be left exactly alone ---
  ["no relative phrase", "Order 30 windows for Pou", "Order 30 windows for Pou"],
  ["already ISO", "Confirm start 2026-05-22", "Confirm start 2026-05-22"],
  ["'weekday' substring not a word", "Reframe Sundayhouse gable", "Reframe Sundayhouse gable"],
];

let passed = 0;
const failures: string[] = [];
for (const [desc, input, expected] of cases) {
  let got: string;
  try {
    got = scrubRelativeDates(input, REF);
  } catch (e) {
    failures.push(`✗ ${desc}\n    threw: ${(e as Error).message}`);
    continue;
  }
  try {
    assert.equal(got, expected);
    passed++;
  } catch {
    failures.push(`✗ ${desc}\n    input:    ${JSON.stringify(input)}\n    expected: ${JSON.stringify(expected)}\n    got:      ${JSON.stringify(got)}`);
  }
}

if (failures.length > 0) {
  console.error(`\n${failures.length} FAILED, ${passed} passed:\n`);
  console.error(failures.join("\n\n"));
  process.exit(1);
}
console.log(`All ${passed} scrubRelativeDates tests passed.`);
