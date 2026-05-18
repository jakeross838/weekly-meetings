-- 011_add_parent_group_activities_to_daily_logs.sql
-- BT daily-log entries carry a parent_group_activities array (e.g.
-- ["Exterior Paint", "Stucco Scratch"]) tagging the high-level work
-- buckets that day. We persist it so the cockpit can compute
-- per-sub × activity-type breakdowns (Phase D).
--
-- Idempotent.

ALTER TABLE public.daily_logs
    ADD COLUMN IF NOT EXISTS parent_group_activities jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS daily_logs_parent_group_idx
    ON public.daily_logs USING GIN (parent_group_activities);
