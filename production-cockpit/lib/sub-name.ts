// Sub (vendor) name normalization — the single rule for deciding whether two
// subcontractor names are the SAME vendor written differently. Used to keep the
// catalog free of near-duplicate rows like "Metro Electric" vs "Metro Electric,
// LLC" that Buildertrend crew names introduce.
//
// Deliberately MINIMAL: it lowercases, collapses whitespace, drops punctuation,
// and strips trailing legal-entity suffixes (LLC / Inc / Co / Corp / Ltd). It
// does NOT strip descriptive words like "Construction" or "Services", because
// those can distinguish genuinely different vendors. (The one-time cleanup
// utility scripts/merge-duplicate-subs.mjs uses a slightly broader key for the
// initial sweep; this runtime rule stays conservative so it can't wrongly fold
// two real vendors together on a live upsert.)

const LEGAL_SUFFIXES = new Set([
  "llc",
  "l.l.c",
  "llc.",
  "inc",
  "inc.",
  "co",
  "co.",
  "corp",
  "corp.",
  "ltd",
  "ltd.",
]);

export function normalizeSubName(name: string | null | undefined): string {
  if (!name) return "";
  const tokens = name
    .toLowerCase()
    .replace(/[.,&/]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  // Strip legal suffixes only where they appear at the end of the name.
  while (tokens.length > 1 && LEGAL_SUFFIXES.has(tokens[tokens.length - 1])) {
    tokens.pop();
  }
  return tokens.join(" ");
}
