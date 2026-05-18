-- 009_create_daily_logs_table.sql
-- Persists Buildertrend daily-log entries so the cockpit can compute
-- sub no-shows from the absent_crews array.
--
-- Source JSON shape (BT scraper output, indexed by job key):
--   {"byJob": {"<job_key>": [
--      { "logId": str, "date": "Wed, Apr 15, 2026",
--        "crews_clean": [str, ...], "absent_crews": [str, ...],
--        "daily_workforce": int, "weatherHigh": int, "weatherLow": int,
--        "activity": str, "notes_full": str, "enriched_at": iso8601
--      }, ...
--   ]}}
--
-- Each (job_key, log_id) is unique. log_date is the parsed date.
-- crews_present and absent_crews are stored as jsonb arrays of trimmed
-- crew name strings, matched against subs.name (with subs.aliases as
-- a fallback) when computing per-sub no-show counts.
--
-- Idempotent. RLS untouched.

CREATE TABLE IF NOT EXISTS public.daily_logs (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_key         text        NOT NULL,
    log_id          text,
    log_date        date,
    crews_present   jsonb       NOT NULL DEFAULT '[]'::jsonb,
    absent_crews    jsonb       NOT NULL DEFAULT '[]'::jsonb,
    daily_workforce int,
    weather_high    int,
    weather_low     int,
    activity        text,
    notes           text,
    enriched_at     timestamptz,
    source          text        DEFAULT 'bt_scraper',
    inserted_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_key, log_id)
);

CREATE INDEX IF NOT EXISTS daily_logs_job_date_idx
    ON public.daily_logs (job_key, log_date);

-- GIN index on absent_crews so sub-no-show queries (jsonb @> '"Sub Name"')
-- stay fast as the table grows.
CREATE INDEX IF NOT EXISTS daily_logs_absent_crews_idx
    ON public.daily_logs USING GIN (absent_crews);

CREATE INDEX IF NOT EXISTS daily_logs_crews_present_idx
    ON public.daily_logs USING GIN (crews_present);
