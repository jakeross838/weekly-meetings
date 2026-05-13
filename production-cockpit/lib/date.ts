/** Compact "M/D" formatter for due dates (US convention, no leading zeros). */
export function shortDate(iso: string | null): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  const month = parseInt(m[2], 10);
  const day = parseInt(m[3], 10);
  return `${month}/${day}`;
}

/** Day delta from today to the given ISO date.
 *  Positive = future, negative = past. Null when input unparseable. */
export function daysFromToday(iso: string | null): number | null {
  if (!iso) return null;
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  const target = new Date(
    Date.UTC(parseInt(m[1]), parseInt(m[2]) - 1, parseInt(m[3]))
  );
  const now = new Date();
  const today = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  );
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/** Human-relative offset like "today", "in 2d", "3d late". */
export function relativeOffset(iso: string | null): string {
  const d = daysFromToday(iso);
  if (d === null) return "";
  if (d === 0) return "today";
  if (d > 0) return `in ${d}d`;
  return `${Math.abs(d)}d late`;
}
