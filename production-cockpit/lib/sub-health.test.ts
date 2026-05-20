// Standalone test for subHealth — same harness as scrub-relative-dates.test.ts
// (no test framework in this repo). Compile with the project's tsc and run
// under node:
//   npx tsc lib/sub-health.ts lib/sub-health.test.ts --outDir .tmp-tdd \
//     --module commonjs --target ES2020 --skipLibCheck --moduleResolution node \
//     --esModuleInterop
//   node .tmp-tdd/lib/sub-health.test.js

import assert from "node:assert/strict";
import { subHealth } from "./sub-health";

type Case = [
  desc: string,
  input: { pastDue: number; dueSoon: number; flagged: boolean },
  status: "red" | "yellow" | "green"
];

const cases: Case[] = [
  // RED — any past-due open commitment is the hardest signal.
  ["past-due → red", { pastDue: 2, dueSoon: 0, flagged: false }, "red"],
  ["past-due wins over flagged", { pastDue: 1, dueSoon: 0, flagged: true }, "red"],
  ["past-due wins over due-soon", { pastDue: 1, dueSoon: 3, flagged: false }, "red"],

  // YELLOW — warrants a look but nothing overdue.
  ["flagged only → yellow", { pastDue: 0, dueSoon: 0, flagged: true }, "yellow"],
  ["due-soon only → yellow", { pastDue: 0, dueSoon: 1, flagged: false }, "yellow"],
  ["flagged + due-soon → yellow", { pastDue: 0, dueSoon: 2, flagged: true }, "yellow"],

  // GREEN — nothing overdue, imminent, or flagged.
  ["clear → green", { pastDue: 0, dueSoon: 0, flagged: false }, "green"],
];

const DOT: Record<string, string> = {
  red: "bg-urgent",
  yellow: "bg-high",
  green: "bg-success",
};

let passed = 0;
const failures: string[] = [];
for (const [desc, input, status] of cases) {
  let got: ReturnType<typeof subHealth>;
  try {
    got = subHealth(input);
  } catch (e) {
    failures.push(`✗ ${desc}\n    threw: ${(e as Error).message}`);
    continue;
  }
  try {
    assert.equal(got.status, status);
    assert.equal(got.dotClass, DOT[status]);
    assert.ok(
      typeof got.label === "string" && got.label.length > 0,
      "label must be a non-empty string"
    );
    passed++;
  } catch {
    failures.push(
      `✗ ${desc}\n    input:    ${JSON.stringify(input)}\n    expected: ${status}\n    got:      ${JSON.stringify(got)}`
    );
  }
}

if (failures.length > 0) {
  console.error(`\n${failures.length} FAILED, ${passed} passed:\n`);
  console.error(failures.join("\n\n"));
  process.exit(1);
}
console.log(`All ${passed} subHealth tests passed.`);
