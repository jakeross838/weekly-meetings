// Tests for normalizeSubName — the rule that folds vendor name variants
// (legal suffixes / punctuation) onto one key while keeping genuinely distinct
// vendors apart.

import { normalizeSubName } from "./sub-name";

let passed = 0;
function eq(a: string, b: string, msg: string) {
  if (a !== b) throw new Error(`FAIL: ${msg}\n  got:      "${a}"\n  expected: "${b}"`);
  passed++;
}
function same(a: string, b: string, msg: string) {
  eq(normalizeSubName(a), normalizeSubName(b), msg);
}
function differ(a: string, b: string, msg: string) {
  if (normalizeSubName(a) === normalizeSubName(b))
    throw new Error(`FAIL: ${msg} — both normalized to "${normalizeSubName(a)}"`);
  passed++;
}

// Legal-suffix + punctuation variants collapse to the same key.
same("Metro Electric", "Metro Electric, LLC", "comma + LLC");
same("WG Quality", "WG QUALITY INC", "case + INC");
same("Integrity Floors", "Integrity Floors LLC", "trailing LLC no comma");
same("Parrish Well Drilling", "Parrish Well Drilling, Inc.", "Inc. with dot");
same("Banko Overhead Doors", "Banko Overhead Doors, Inc", "Inc no dot");
same("Sight to See Construction", "Sight to See Construction, LLC", "construction kept, LLC stripped");
same("ALL Valencia Construction", "ALL VALENCIA CONSTRUCTION LLC", "all caps");

// Descriptive words are NOT stripped — different vendors stay different.
differ("Creative Electric Services", "Creative Plumbing Services", "different trade word");
differ("Metro Electric", "Metro Plumbing", "different vendor");
differ("Scranton Elevator", "Scranton Roofing", "shared first word only");

// Edge cases.
eq(normalizeSubName(null), "", "null → empty");
eq(normalizeSubName("   LLC  "), "llc", "lone suffix is not stripped to empty");
eq(normalizeSubName("Myers Painting, LLC"), "myers painting", "exact normalized value");

console.log(`All ${passed} normalizeSubName tests passed.`);
