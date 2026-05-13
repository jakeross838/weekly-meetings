/** Returns the Monday 00:00 UTC for the current ISO week as ISO string. */
export function isoMondayUtc(now: Date = new Date()): string {
  const d = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  );
  // getUTCDay: Sun=0..Sat=6. We want Mon=0..Sun=6.
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day);
  return d.toISOString();
}
