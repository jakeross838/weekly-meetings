-- 013_create_sub_specialty_durations_table.sql
-- Per (sub × canonical specialty × job) duration with cited daily-log evidence.
--
-- Rows are derived ('auto') from daily_logs by classifying each crew's logged
-- activity (notes/activity) against the schedule_items taxonomy, then measuring
-- how many distinct on-site days that sub spent on that specialty per job. Each
-- row carries its evidence: the source daily_log ids + the attributed dates + a
-- sample quote, so the number is auditable on the sub page.
--
-- source='manual' rows are human-authored and MUST win — the auto refresh only
-- deletes/replaces source='auto' rows. Idempotent. RLS untouched.

CREATE TABLE IF NOT EXISTS public.sub_specialty_durations (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_id         text        NOT NULL REFERENCES public.subs(id) ON DELETE CASCADE,
    specialty      text        NOT NULL,                 -- canonical schedule_items.name
    trade          text,
    job_key        text        NOT NULL,                 -- evidence: the full job key
    job_short      text        NOT NULL,                 -- short job label (e.g. "Fish")
    active_days    int         NOT NULL DEFAULT 0,        -- distinct on-site days on this specialty/job
    first_date     date,
    last_date      date,
    span_days      int,                                   -- last - first + 1 (calendar)
    log_ids        jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- evidence daily_log ids
    evidence_dates jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- the attributed YYYY-MM-DD dates
    sample_quote   text,                                  -- one cited snippet from the notes
    confidence     text        NOT NULL DEFAULT 'medium'
                               CHECK (confidence IN ('high', 'medium', 'low')),
    source         text        NOT NULL DEFAULT 'auto'
                               CHECK (source IN ('auto', 'manual')),
    generated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sub_id, specialty, job_short)
);

CREATE INDEX IF NOT EXISTS sub_spec_dur_sub_idx
    ON public.sub_specialty_durations (sub_id);
CREATE INDEX IF NOT EXISTS sub_spec_dur_specialty_idx
    ON public.sub_specialty_durations (specialty);
