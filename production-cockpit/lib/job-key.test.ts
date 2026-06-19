// Tests for jobKeyMatchesName — boundary-aware job-name → job_key matching.

import { jobKeyMatchesName } from "./job-key";

let passed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  passed++;
}

// Real shapes seen in the data.
ok(jobKeyMatchesName("Krauss-427 South Blvd of the Presidents", "Krauss"), "dash form");
ok(jobKeyMatchesName("Markgraf closeout", "Markgraf"), "space form");
ok(jobKeyMatchesName("Markgraf-5939 River Forest Circle", "Markgraf"), "dash form 2");
ok(jobKeyMatchesName("Fish", "Fish"), "exact equal");
ok(jobKeyMatchesName("fish-715 north shore dr", "Fish"), "case-insensitive");

// The whole point: a prefix that runs into more letters is NOT a match.
ok(!jobKeyMatchesName("Clarkson-1 Main St", "Clark"), "Clarkson is not Clark");
ok(!jobKeyMatchesName("Fisher-9 Bay", "Fish"), "Fisher is not Fish");

// Guards.
ok(!jobKeyMatchesName(null, "Fish"), "null key");
ok(!jobKeyMatchesName("Fish-1", null), "null name");
ok(!jobKeyMatchesName("Other-1", "Fish"), "no shared prefix");

console.log(`All ${passed} jobKeyMatchesName tests passed.`);
