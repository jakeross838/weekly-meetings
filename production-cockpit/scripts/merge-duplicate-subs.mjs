// merge-duplicate-subs.mjs — one-time, reversible dedup of subcontractor rows
// that are the SAME vendor logged under name variants (legal suffix / punctuation
// / a trailing "service(s)" word), e.g. "Metro Electric" vs "Metro Electric, LLC".
//
// It derives the duplicate groups FROM THE DATA (no hardcoded vendor list):
// normalize each visible sub's name, group by the normalized key, and act only
// on groups with >1 distinct row. For each group it:
//   1. picks a canonical row  (human-curated source wins, then most references,
//      then the cleanest/shortest name),
//   2. sets the canonical display name to the cleanest variant and folds every
//      other variant name + alias into canonical.aliases (so daily-log crew-name
//      matching still resolves every variant to the one profile),
//   3. reassigns items/todos/sub_specialties/sub_checklist_items.sub_id from the
//      duplicates to the canonical,
//   4. soft-hides the duplicate rows (hidden=true) — never hard-deletes — so the
//      merge is fully reversible (un-hide + the names live on as aliases).
//
// Dry-run by default. Pass --apply to execute.
//
//   node scripts/merge-duplicate-subs.mjs           # show the plan
//   node scripts/merge-duplicate-subs.mjs --apply   # do it

import { createClient } from "@supabase/supabase-js";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APPLY = process.argv.includes("--apply");
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envPath = path.join(__dirname, "..", ".env.local");
const env = Object.fromEntries(
  fs
    .readFileSync(envPath, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
    })
);
const sb = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false },
});

// Grouping key: lowercase, drop punctuation, strip trailing company words /
// legal suffixes. Tuned to catch genuine variants only. Verified against the
// live catalog: produces only same-vendor groups (eyeball the printed plan).
const STRIP_TOKENS = new Set([
  "llc", "l.l.c", "inc", "inc.", "co", "co.", "company", "corp", "corp.",
  "ltd", "ltd.", "service", "services", "the",
]);
function normKey(name) {
  return (name || "")
    .toLowerCase()
    .replace(/[.,&/]/g, " ")
    .split(/\s+/)
    .filter((t) => t && !STRIP_TOKENS.has(t))
    .join(" ")
    .trim();
}
const lc = (s) => (s || "").trim().toLowerCase();

// "Cleanliness" of a display name — lower is cleaner. Penalize legal suffixes,
// commas, and length, so "Metro Electric" beats "Metro Electric, LLC".
function uncleanScore(name) {
  const n = lc(name);
  let s = name.length;
  if (/(,|\bllc\b|\binc\b|\bl\.l\.c\b|\bcorp\b|\bltd\b)/.test(n)) s += 100;
  if (name.includes(",")) s += 20;
  return s;
}

async function countRefs(table, ids) {
  const out = new Map(ids.map((id) => [id, 0]));
  const { data, error } = await sb.from(table).select("sub_id").in("sub_id", ids);
  if (error) return out;
  for (const r of data || []) out.set(r.sub_id, (out.get(r.sub_id) || 0) + 1);
  return out;
}

async function main() {
  const { data: subs, error } = await sb
    .from("subs")
    .select("id, name, aliases, source, trade, hidden")
    .eq("hidden", false);
  if (error) throw error;

  const groups = new Map();
  for (const s of subs) {
    const k = normKey(s.name);
    if (!k) continue;
    (groups.get(k) || groups.set(k, []).get(k)).push(s);
  }
  const dupeGroups = [...groups.entries()].filter(([, arr]) => arr.length > 1);
  if (!dupeGroups.length) {
    console.log("No duplicate sub groups found. Nothing to do.");
    return;
  }

  // Pull ref counts for every candidate id across the four FK tables.
  const allIds = dupeGroups.flatMap(([, arr]) => arr.map((s) => s.id));
  const [itemsC, todosC, specC, checkC] = await Promise.all([
    countRefs("items", allIds),
    countRefs("todos", allIds),
    countRefs("sub_specialties", allIds),
    countRefs("sub_checklist_items", allIds),
  ]);
  const refsOf = (id) =>
    (itemsC.get(id) || 0) +
    (todosC.get(id) || 0) +
    (specC.get(id) || 0) +
    (checkC.get(id) || 0);

  console.log(
    `${APPLY ? "APPLYING" : "DRY RUN"} — ${dupeGroups.length} duplicate group(s):\n`
  );

  const plan = [];
  for (const [key, arr] of dupeGroups) {
    // Canonical: human source first, then most references, then cleanest name.
    const ranked = [...arr].sort((a, b) => {
      const ah = a.source === "auto" ? 1 : 0;
      const bh = b.source === "auto" ? 1 : 0;
      if (ah !== bh) return ah - bh; // human (0) before auto (1)
      const ar = refsOf(a.id);
      const br = refsOf(b.id);
      if (ar !== br) return br - ar; // more refs first
      return uncleanScore(a.name) - uncleanScore(b.name);
    });
    const canonical = ranked[0];
    const dupes = ranked.slice(1);

    // Cleanest display name across the whole group.
    const cleanName = [...arr].sort(
      (a, b) => uncleanScore(a.name) - uncleanScore(b.name)
    )[0].name;

    // Union of every name + alias, minus the chosen display name.
    const aliasSet = new Map(); // lc -> original casing
    for (const s of arr) {
      for (const nm of [s.name, ...(s.aliases || [])]) {
        if (nm && lc(nm) !== lc(cleanName)) aliasSet.set(lc(nm), nm);
      }
    }
    const newAliases = [...aliasSet.values()];

    plan.push({ key, canonical, dupes, cleanName, newAliases });
    console.log(`• [${key}]`);
    console.log(
      `    canonical: ${canonical.id} "${canonical.name}" (source=${canonical.source ?? "?"}, refs=${refsOf(canonical.id)}) → display "${cleanName}"`
    );
    for (const d of dupes)
      console.log(
        `    merge ←   ${d.id} "${d.name}" (source=${d.source ?? "?"}, refs=${refsOf(d.id)}: items=${itemsC.get(d.id) || 0} todos=${todosC.get(d.id) || 0} spec=${specC.get(d.id) || 0} check=${checkC.get(d.id) || 0})`
      );
    console.log(`    aliases →  [${newAliases.join(" | ")}]`);
    console.log("");
  }

  if (!APPLY) {
    console.log("Dry run only. Re-run with --apply to execute.");
    return;
  }

  const now = new Date().toISOString();
  let merged = 0;
  for (const { canonical, dupes, cleanName, newAliases } of plan) {
    // 1. Canonical: clean display name + merged aliases.
    const { error: upErr } = await sb
      .from("subs")
      .update({ name: cleanName, aliases: newAliases, updated_at: now })
      .eq("id", canonical.id);
    if (upErr) {
      console.log(`  ! canonical ${canonical.id} update failed: ${upErr.message}`);
      continue;
    }
    // 2. Reassign references, then 3. hide each dupe.
    for (const d of dupes) {
      for (const table of ["items", "todos", "sub_specialties", "sub_checklist_items"]) {
        const { error: rErr } = await sb
          .from(table)
          .update({ sub_id: canonical.id })
          .eq("sub_id", d.id);
        if (rErr)
          console.log(`  ! reassign ${table} ${d.id}→${canonical.id}: ${rErr.message}`);
      }
      const { error: hErr } = await sb
        .from("subs")
        .update({
          hidden: true,
          hidden_at: now,
          notes: `[merged into ${canonical.id} (${cleanName}) on ${now.slice(0, 10)} — duplicate vendor]`,
        })
        .eq("id", d.id);
      if (hErr) console.log(`  ! hide ${d.id}: ${hErr.message}`);
      else merged++;
    }
  }
  console.log(`\nDone. Merged + hid ${merged} duplicate sub row(s).`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
