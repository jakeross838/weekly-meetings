// "Today" for due-date math, anchored to the builder's operating timezone.
//
// The whole app compares date-only strings ("YYYY-MM-DD"): due_date < today →
// past due, due_date <= today+7 → due soon, etc. Computing "today" with
// `new Date().toISOString().slice(0,10)` yields the *UTC* date. Production runs
// on Vercel (UTC) while Ross Built operates in Florida (US Eastern), so every
// evening — once it's past midnight UTC but still "today" in Florida — a to-do
// due today would silently flip to "past due" and the dashboards would over-
// count late work by several hours. Anchoring to America/New_York fixes that.
//
// (Eastern covers Florida, where every job address sits; if the company ever
// spans timezones, this single constant is the place to revisit.)

const TZ = "America/New_York";

// Today's date in the operating timezone as "YYYY-MM-DD".
export function businessToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

// `businessToday()` shifted by whole days, still as "YYYY-MM-DD". Day math is
// done on the date-only value (UTC midnight) so DST never adds/drops an hour.
export function businessDateOffset(days: number, now: Date = new Date()): string {
  const d = new Date(businessToday(now) + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
