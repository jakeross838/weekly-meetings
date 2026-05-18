-- 012_create_sub_specialties_table.sql
-- Per-sub specialty tags: what each sub typically does. Two sources:
--   • manual — Jake/PM declared "TNT does exterior painting"
--   • auto   — derived from daily_logs.parent_group_activities when this sub
--              appears in crews_present on a log with that tag
-- The cockpit unions both at display time; this table is the persistence for
-- manual additions. Auto specialties are computed on the fly from daily_logs.
--
-- Idempotent. RLS untouched.

CREATE TABLE IF NOT EXISTS public.sub_specialties (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_id        text        NOT NULL REFERENCES public.subs(id) ON DELETE CASCADE,
    specialty     text        NOT NULL,
    source        text        NOT NULL DEFAULT 'manual'
                              CHECK (source IN ('manual', 'auto')),
    created_by    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sub_id, specialty)
);

CREATE INDEX IF NOT EXISTS sub_specialties_sub_idx
    ON public.sub_specialties (sub_id);

CREATE INDEX IF NOT EXISTS sub_specialties_specialty_idx
    ON public.sub_specialties (specialty);
