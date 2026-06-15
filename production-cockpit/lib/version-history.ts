// Single source of truth for the app's version history, rendered by the
// VersionFooter at the very bottom of every page. Newest first. Dates are
// absolute YYYY-MM-DD — no relative dates (see lib/scrub-relative-dates).
//
// To cut a release: prepend a new entry here. CURRENT_VERSION always tracks
// the first (newest) row.

export type AppVersion = {
  version: string; // display label, e.g. "1"
  date: string; // YYYY-MM-DD this version shipped
  summary: string; // one-line description of what changed
};

export const APP_VERSION_HISTORY: AppVersion[] = [
  {
    version: "1",
    date: "2026-06-15",
    summary:
      "First tracked release — production cockpit with jobs, subs, meetings, BT daily-log import, and the activity-first sub profiles.",
  },
];

export const CURRENT_VERSION = APP_VERSION_HISTORY[0];
