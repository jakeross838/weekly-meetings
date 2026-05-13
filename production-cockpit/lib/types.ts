export type Priority = "URGENT" | "HIGH" | "NORMAL";
export type Status = "NOT_STARTED" | "IN_PROGRESS" | "BLOCKED" | "COMPLETE";

export interface SubEmbedded {
  id: string;
  name: string;
  trade: string | null;
  rating: number | null;
  reliability_pct: number | null;
  avg_days_per_job: number | null;
}

export interface Sub extends SubEmbedded {
  aliases: string[] | null;
  jobs_performed: number | null;
  flagged_for_pm_binder: boolean;
  flag_reasons: string[] | null;
  rating_basis: string[] | null;
  notes: string | null;
  updated_at: string;
}

export interface Todo {
  id: string;
  pm_id: string;
  job: string;
  title: string;
  due_date: string | null;
  priority: Priority | null;
  status: Status;
  type: string | null;
  category: string | null;
  created_at: string;
  completed_at: string | null;
  source_transcript: string | null;
  source_excerpt: string | null;
  sub_id: string | null;
  sub?: SubEmbedded | null;
  previous_status: Status | null;
  edited_title: string | null;
  edited_at: string | null;
}

export interface PM {
  id: string;
  full_name: string;
  active: boolean;
}

export const OPEN_STATUSES: Status[] = ["NOT_STARTED", "IN_PROGRESS", "BLOCKED"];
