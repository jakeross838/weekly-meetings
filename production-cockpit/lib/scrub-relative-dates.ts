// scrubRelativeDates — turn relative-time phrases in a to-do title into exact
// ISO dates, or strip them when no concrete date can be inferred.
//
// Why this exists (Jake's rule, 2026-05-20): a to-do that lands on the active
// list must never read "…tomorrow" or "…by Friday". Either the title carries a
// hard YYYY-MM-DD, or it carries no timeframe at all (the due_date field holds
// the timing). The extraction prompt asks Claude for this, but Claude slips;
// this is the deterministic safety net applied at the write boundary so the
// guarantee holds regardless of which UI produced or edited the text.
//
// All date math is UTC to match the rest of the cockpit (lib/date.ts) and to
// stay stable across the server's timezone.

const WEEKDAYS: Record<string, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};
const WEEKDAY_ALT = Object.keys(WEEKDAYS).join("|");

function parseRef(refDateIso: string): Date | null {
  const m = refDateIso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  const d = new Date(
    Date.UTC(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10))
  );
  return isNaN(d.getTime()) ? null : d;
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function addDays(ref: Date, n: number): string {
  return iso(new Date(ref.getTime() + n * 86_400_000));
}

function lastDayOfMonth(year: number, monthIndex0: number): string {
  // Day 0 of the *next* month is the last day of this month.
  return iso(new Date(Date.UTC(year, monthIndex0 + 1, 0)));
}

// Next occurrence of `targetDow` on or after ref (delta 0 means ref itself).
function weekdayOnOrAfter(ref: Date, targetDow: number): string {
  const delta = (targetDow - ref.getUTCDay() + 7) % 7;
  return addDays(ref, delta);
}

/**
 * Replace/strip relative-time phrases in `title`.
 * @param refDateIso anchor date (the meeting date), "YYYY-MM-DD".
 */
export function scrubRelativeDates(title: string, refDateIso: string): string {
  if (!title) return title;
  const ref = parseRef(refDateIso);
  let out = title;

  // ---- 1. SUBSTITUTIONS (only possible when we have a valid anchor) ----
  if (ref) {
    // Order matters: most-specific first so e.g. "next Friday" and
    // "day after tomorrow" win before the shorter patterns.

    // "day after tomorrow" -> ref + 2
    out = out.replace(/\bday after tomorrow\b/gi, addDays(ref, 2));

    // "next <weekday>" -> the weekday in the following week.
    out = out.replace(
      new RegExp(`\\b(?:by\\s+)?next\\s+(${WEEKDAY_ALT})\\b`, "gi"),
      (_m, wd: string) =>
        addDays(
          new Date(weekdayOnOrAfter(ref, WEEKDAYS[wd.toLowerCase()]) + "T00:00:00Z"),
          7
        )
    );

    // "next week" (also "by next week" / "early next week") -> ref + 7
    out = out.replace(/\b(?:by\s+|early\s+)?next week\b/gi, addDays(ref, 7));

    // "end of (the) month" (also "by (the) end of (the) month") -> month end
    out = out.replace(
      /\b(?:by\s+)?(?:the\s+)?end of (?:the\s+)?month\b/gi,
      lastDayOfMonth(ref.getUTCFullYear(), ref.getUTCMonth())
    );

    // bare / "this" / "by" / "on" <weekday> -> next on-or-after ref
    out = out.replace(
      new RegExp(`\\b(?:by\\s+|on\\s+|this\\s+)?(${WEEKDAY_ALT})\\b`, "gi"),
      (_m, wd: string) => weekdayOnOrAfter(ref, WEEKDAYS[wd.toLowerCase()])
    );

    // single-word anchors (optionally prefixed with "by ")
    out = out.replace(/\b(?:by\s+)?tomorrow\b/gi, addDays(ref, 1));
    out = out.replace(/\byesterday\b/gi, addDays(ref, -1));
    out = out.replace(
      /\b(?:by\s+)?(?:today|tonight|this morning|this afternoon|this evening)\b/gi,
      iso(ref)
    );

    // "in N day(s)/week(s)"
    out = out.replace(/\bin (\d{1,3}) days?\b/gi, (_m, n: string) =>
      addDays(ref, parseInt(n, 10))
    );
    out = out.replace(/\bin (\d{1,2}) weeks?\b/gi, (_m, n: string) =>
      addDays(ref, parseInt(n, 10) * 7)
    );
  }

  // ---- 2. STRIPS — vague spans with no defensible single date. ----
  // Leading whitespace is consumed so removal doesn't leave a double space,
  // and an optional leading "by"/"by the" connector is eaten with it.
  const STRIP = [
    /\s*\b(?:by\s+)?a\.?s\.?a\.?p\.?\b/gi,
    /\s*\b(?:really\s+|very\s+)?soon\b/gi,
    /\s*\bshortly\b/gi,
    /\s*\b(?:by\s+)?(?:the\s+)?end of (?:the\s+)?(?:week|day)\b/gi,
    /\s*\b(?:by\s+)?this week\b/gi,
    /\s*\b(?:by\s+)?this month\b/gi,
    /\s*\bin a (?:few|couple)(?: of)? (?:days|weeks)\b/gi,
    /\s*\b(?:at some point|eventually|when (?:you can|possible)|whenever)\b/gi,
  ];
  for (const re of STRIP) out = out.replace(re, "");

  // ---- 3. TIDY whitespace + connectors left dangling by a strip. ----
  out = out
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([,.;:])/g, "$1")
    .replace(/[ \t]+$/g, "")
    .trim();

  return out;
}
