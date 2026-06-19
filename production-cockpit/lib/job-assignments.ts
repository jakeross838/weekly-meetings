// Job→PM assignment helpers, shared between /api/admin/jobs (job CRUD) and
// /lib/user-store (create-PM flow). Single source of truth so both writers
// keep `jobs.pm_id` and the legacy `job_pm_assignments` table in sync.
//
// Visibility logic on every page reads
//   `activePmByJob.get(j.id) ?? j.pm_id`
// so a stale open `job_pm_assignments` row will silently override what admin
// sets in `jobs.pm_id` — reassignments would look successful but the
// previous PM would keep seeing the job. Always go through these helpers.

import { supabaseServer } from "./supabase";
import { businessToday } from "./today";

// Close any active job_pm_assignments rows for this job and (optionally)
// open a fresh one for the new pmId. Pass `null` to unassign.
export async function syncJobPmAssignment(
  jobId: string,
  newPmId: string | null
): Promise<void> {
  const sb = supabaseServer();
  const today = businessToday();
  const { error: closeErr } = await sb
    .from("job_pm_assignments")
    .update({ ended_at: today })
    .eq("job_id", jobId)
    .is("ended_at", null);
  if (closeErr) {
    console.warn("[job-assignments] close failed:", closeErr.message);
  }
  if (newPmId) {
    const { error: insErr } = await sb
      .from("job_pm_assignments")
      .insert({ job_id: jobId, pm_id: newPmId, assigned_at: today });
    if (insErr) {
      console.warn("[job-assignments] insert failed:", insErr.message);
    }
  }
}

// Move a job to a different PM (or unassign). Writes BOTH `jobs.pm_id` and
// closes/opens the matching row in `job_pm_assignments`. Used by the
// create-PM-with-jobs flow and by any future bulk reassign.
export async function setJobPm(jobId: string, newPmId: string | null): Promise<void> {
  const sb = supabaseServer();
  const { error } = await sb
    .from("jobs")
    .update({ pm_id: newPmId, updated_at: new Date().toISOString() })
    .eq("id", jobId);
  if (error) throw new Error(`setJobPm(${jobId}): ${error.message}`);
  await syncJobPmAssignment(jobId, newPmId);
}
