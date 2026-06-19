// Buildertrend stores per-job rows (daily_logs, purchase_orders, change_orders)
// under a free-text `job_key` of the form "<JobName>-<Address>" — e.g.
// "Krauss-427 South Blvd" — though a few use a space ("Markgraf closeout").
// Jobs are matched to those rows by the job NAME prefix.
//
// A bare `startsWith(name)` / `ilike('name%')` over-matches when one job name is
// a prefix of another (e.g. "Clark" would also grab "Clarkson-..." rows). This
// helper requires the character right after the name to be a word boundary (or
// end of string), so "Clark" matches "Clark-853..." and "Clark closeout" but
// never "Clarkson-...". Use the broad ilike in the query for index use, then
// filter results through this.

export function jobKeyMatchesName(
  jobKey: string | null | undefined,
  jobName: string | null | undefined
): boolean {
  if (!jobKey || !jobName) return false;
  const key = jobKey.trim().toLowerCase();
  const name = jobName.trim().toLowerCase();
  if (!name) return false;
  if (key === name) return true;
  if (!key.startsWith(name)) return false;
  // The next char after the matched name must NOT be alphanumeric, so we don't
  // treat "Clarkson" as a match for "Clark".
  const next = key.charAt(name.length);
  return next !== "" && !/[a-z0-9]/.test(next);
}
