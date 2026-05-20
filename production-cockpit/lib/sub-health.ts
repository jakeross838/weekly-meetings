// subHealth — a factual, glanceable triage status for a sub. NOT a quality
// grade (Jake removed A–F grading 2026-05-18). It answers one question:
// "does this sub need attention this week?" purely from hard signals.
//
//   RED    — has past-due open todos (a broken commitment; the hardest signal).
//   YELLOW — not red, but flagged for the PM binder OR has todos due within the
//            next 7 days (warrants a look). The auto-flag tops out here, never
//            red, because it's an unconfirmed signal.
//   GREEN  — nothing overdue, imminent, or flagged.

export type HealthStatus = "red" | "yellow" | "green";

export interface SubHealthInput {
  pastDue: number; // open todos whose due_date < today
  dueSoon: number; // open todos due today..today+7 (not past due)
  flagged: boolean; // subs.flagged_for_pm_binder
}

export interface SubHealth {
  status: HealthStatus;
  label: string; // human-readable, used as tooltip / pill label
  dotClass: string; // brand background utility for the status dot
}

export function subHealth({
  pastDue,
  dueSoon,
  flagged,
}: SubHealthInput): SubHealth {
  if (pastDue > 0) {
    return { status: "red", label: "Needs attention", dotClass: "bg-urgent" };
  }
  if (flagged || dueSoon > 0) {
    return { status: "yellow", label: "Watch", dotClass: "bg-high" };
  }
  return { status: "green", label: "Clear", dotClass: "bg-success" };
}
