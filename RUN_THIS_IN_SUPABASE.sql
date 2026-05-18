-- Paste this whole file into Supabase SQL editor → click Run.
-- All four migrations bundled. Idempotent (safe to re-run).
-- Project: takewvlqgwpdbkvcwpvi

CREATE TABLE IF NOT EXISTS public.daily_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_key text NOT NULL,
    log_id text,
    log_date date,
    crews_present jsonb NOT NULL DEFAULT '[]'::jsonb,
    absent_crews jsonb NOT NULL DEFAULT '[]'::jsonb,
    parent_group_activities jsonb NOT NULL DEFAULT '[]'::jsonb,
    daily_workforce int,
    weather_high int,
    weather_low int,
    activity text,
    notes text,
    enriched_at timestamptz,
    source text DEFAULT 'bt_scraper',
    inserted_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_key, log_id)
);

CREATE INDEX IF NOT EXISTS daily_logs_job_date_idx
    ON public.daily_logs (job_key, log_date);
CREATE INDEX IF NOT EXISTS daily_logs_absent_crews_idx
    ON public.daily_logs USING GIN (absent_crews);
CREATE INDEX IF NOT EXISTS daily_logs_crews_present_idx
    ON public.daily_logs USING GIN (crews_present);
CREATE INDEX IF NOT EXISTS daily_logs_parent_group_idx
    ON public.daily_logs USING GIN (parent_group_activities);

ALTER TABLE public.items ADD COLUMN IF NOT EXISTS category text;

CREATE INDEX IF NOT EXISTS items_category_idx
    ON public.items (category) WHERE category IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.sub_specialties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_id text NOT NULL REFERENCES public.subs(id) ON DELETE CASCADE,
    specialty text NOT NULL,
    source text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'auto')),
    duration_days_manual_override numeric,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sub_id, specialty)
);

CREATE INDEX IF NOT EXISTS sub_specialties_sub_idx
    ON public.sub_specialties (sub_id);
CREATE INDEX IF NOT EXISTS sub_specialties_specialty_idx
    ON public.sub_specialties (specialty);
