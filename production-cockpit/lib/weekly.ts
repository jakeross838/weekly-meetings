// Shared types + helpers for the Weekly Review feature (Phase 3).
//
// A homeowner report is generated as a DRAFT, edited by the PM, then explicitly
// APPROVED before it can be copied/sent. Nothing is ever auto-sent. edited_body
// (PM edits) wins over the generated body when present.

import { isoMondayUtc } from "@/lib/week";

export interface ReportBody {
  greeting: string;
  budget: string;
  schedule: string;
  upcoming_selections: string[];
  whats_next: string[];
  closing: string;
}

export type ReportStatus = "draft" | "approved" | "sent";

export interface WeeklyReport {
  id: string;
  job_id: string;
  week_start: string; // YYYY-MM-DD
  period: string;
  status: ReportStatus;
  body: ReportBody;
  edited_body: ReportBody | null;
  model: string | null;
  generated_by: string | null;
  generated_at: string;
  approved_by: string | null;
  approved_at: string | null;
  sent_by: string | null;
  sent_at: string | null;
  updated_at: string;
}

export interface JobIntel {
  id: string;
  job_id: string | null;
  source: "email" | "daily_log" | "po" | "manual";
  message_id: string | null;
  sent_at: string | null;
  project: string | null;
  intel_type: string | null;
  summary: string;
  detail: string | null;
  action_needed: string | null;
  recipients: string | null;
  source_ref: string | null;
  created_by: string | null;
  hidden: boolean;
  created_at: string;
}

// Monday (UTC) of the current ISO week as a date-only "YYYY-MM-DD". This is the
// canonical week_start key for weekly_reports (recalculated, never stored ad hoc).
export function currentWeekStart(now: Date = new Date()): string {
  return isoMondayUtc(now).slice(0, 10);
}

// PM edits win over the generated body.
export function effectiveBody(r: {
  body: ReportBody;
  edited_body: ReportBody | null;
}): ReportBody {
  return r.edited_body ?? r.body;
}

const EMPTY: ReportBody = {
  greeting: "",
  budget: "",
  schedule: "",
  upcoming_selections: [],
  whats_next: [],
  closing: "",
};

// Coerce arbitrary jsonb into a well-formed ReportBody so the UI never crashes
// on a partial/legacy row.
export function normalizeBody(v: unknown): ReportBody {
  if (!v || typeof v !== "object") return { ...EMPTY };
  const o = v as Record<string, unknown>;
  const str = (x: unknown) => (typeof x === "string" ? x : "");
  const arr = (x: unknown) =>
    Array.isArray(x) ? x.filter((s): s is string => typeof s === "string") : [];
  return {
    greeting: str(o.greeting),
    budget: str(o.budget),
    schedule: str(o.schedule),
    upcoming_selections: arr(o.upcoming_selections),
    whats_next: arr(o.whats_next),
    closing: str(o.closing),
  };
}

// Plain-text render of a report for the "copy for client" button.
export function reportToText(s: ReportBody): string {
  const parts = [s.greeting, "", `BUDGET\n${s.budget}`, "", `SCHEDULE\n${s.schedule}`];
  if (s.upcoming_selections.length)
    parts.push("", "UPCOMING SELECTIONS", ...s.upcoming_selections.map((x) => `• ${x}`));
  if (s.whats_next.length)
    parts.push("", "WHAT'S NEXT", ...s.whats_next.map((x) => `• ${x}`));
  parts.push("", s.closing);
  return parts.join("\n").trim();
}
