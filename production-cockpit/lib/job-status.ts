import { Todo } from "./types";
import { daysFromToday } from "./date";

export type JobStatus = "green" | "amber" | "red";

export interface JobStatusResult {
  status: JobStatus;
  reasons: string[];
}

/**
 * Compute a traffic-light status for a set of OPEN todos on one job.
 *
 *  RED   — any URGENT overdue, OR ≥3 HIGH overdue, OR ≥1 URGENT due ≤3d
 *  AMBER — any URGENT due 4-7d, OR any HIGH overdue, OR ≥3 HIGH due ≤7d
 *  GREEN — none of the above
 */
export function computeJobStatus(todos: Todo[]): JobStatusResult {
  let urgentOverdue = 0;
  let urgentSoon = 0;
  let urgentNearWeek = 0;
  let highOverdue = 0;
  let highSoon = 0;
  for (const t of todos) {
    const d = daysFromToday(t.due_date);
    const overdue = d != null && d < 0;
    if (t.priority === "URGENT") {
      if (overdue) urgentOverdue++;
      else if (d != null && d <= 3) urgentSoon++;
      else if (d != null && d <= 7) urgentNearWeek++;
    } else if (t.priority === "HIGH") {
      if (overdue) highOverdue++;
      else if (d != null && d <= 7) highSoon++;
    }
  }

  const reasons: string[] = [];
  if (urgentOverdue > 0) reasons.push(`${urgentOverdue} URGENT overdue`);
  if (urgentSoon > 0) reasons.push(`${urgentSoon} URGENT due ≤3d`);
  if (highOverdue > 0)
    reasons.push(`${highOverdue} HIGH overdue`);
  if (urgentNearWeek > 0)
    reasons.push(`${urgentNearWeek} URGENT due ≤7d`);
  if (highSoon >= 3) reasons.push(`${highSoon} HIGH due ≤7d`);

  if (urgentOverdue > 0 || highOverdue >= 3 || urgentSoon > 0) {
    return { status: "red", reasons };
  }
  if (urgentNearWeek > 0 || highOverdue > 0 || highSoon >= 3) {
    return { status: "amber", reasons };
  }
  return { status: "green", reasons: ["On plan"] };
}
