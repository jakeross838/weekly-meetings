-- 007_brain_hardening.sql
-- v2 rebuild — Gate 2A.6: dynamic, learnable, low-hardcode brain.
--
-- Adds:
--  * internal_people — Ross Built non-PM roles (Jake, Andrew, Lee Ross)
--  * pms.aliases + pms.notes — alias support for PMs (subs already had it from v1)
--  * job_pm_assignments — historical PM-to-job assignments (PMs transition cleanly)
--  * corrections — learning loop (every override teaches future Reconciler runs)
--  * claims canonical columns — speaker_canonical, subject_canonical, plus FK ids
--
-- Idempotent. RLS untouched.

CREATE TABLE IF NOT EXISTS public.internal_people (
    id          text        PRIMARY KEY,
    full_name   text        NOT NULL,
    role        text,
    aliases     text[]      DEFAULT ARRAY[]::text[],
    active      bool        DEFAULT true,
    notes       text,
    created_at  timestamptz DEFAULT now(),
    updated_at  timestamptz DEFAULT now()
);

ALTER TABLE public.pms
    ADD COLUMN IF NOT EXISTS aliases text[] DEFAULT ARRAY[]::text[],
    ADD COLUMN IF NOT EXISTS notes   text;

CREATE TABLE IF NOT EXISTS public.job_pm_assignments (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      text        NOT NULL REFERENCES public.jobs(id),
    pm_id       text        NOT NULL REFERENCES public.pms(id),
    assigned_at date        NOT NULL,
    ended_at    date,
    reason      text,
    created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_pm_assignments_job ON public.job_pm_assignments (job_id);
CREATE INDEX IF NOT EXISTS idx_job_pm_assignments_current
    ON public.job_pm_assignments (job_id, ended_at)
    WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS public.corrections (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id            uuid        REFERENCES public.items(id),
    field_changed      text        NOT NULL,
    before_value       text,
    after_value        text,
    correction_reason  text,
    corrected_by       text        DEFAULT 'jake',
    context            jsonb,
    applied_count      int         DEFAULT 0,
    created_at         timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_corrections_field  ON public.corrections (field_changed);
CREATE INDEX IF NOT EXISTS idx_corrections_recent ON public.corrections (created_at DESC);

-- Canonical-name columns on claims (populated by the extractor/ingestor pipeline)
ALTER TABLE public.claims
    ADD COLUMN IF NOT EXISTS speaker_canonical    text,
    ADD COLUMN IF NOT EXISTS subject_canonical    text,
    ADD COLUMN IF NOT EXISTS speaker_canonical_id text,
    ADD COLUMN IF NOT EXISTS subject_canonical_id text;

-- ----- MINIMAL SEED -----

-- Internal people (Ross Built, non-PM roles)
INSERT INTO public.internal_people (id, full_name, role, aliases) VALUES
    ('jake-ross',   'Jake Ross',   'Director of Construction',                ARRAY['Jake','Jacob']::text[]),
    ('andrew-ross', 'Andrew Ross', 'Director of Pre-Construction & Finance',  ARRAY['Andrew']::text[]),
    ('lee-ross',    'Lee Ross',    'Owner',                                    ARRAY['Lee Roth']::text[])
ON CONFLICT (id) DO NOTHING;

-- PM aliases (only set when no aliases yet)
UPDATE public.pms SET aliases = ARRAY['Bob']::text[]
    WHERE id = 'bob'    AND coalesce(array_length(aliases, 1), 0) = 0;
UPDATE public.pms SET aliases = ARRAY['Jason']::text[]
    WHERE id = 'jason'  AND coalesce(array_length(aliases, 1), 0) = 0;
UPDATE public.pms SET aliases = ARRAY['Lee Worthy','Worthy']::text[]
    WHERE id = 'lee'    AND coalesce(array_length(aliases, 1), 0) = 0;
UPDATE public.pms SET aliases = ARRAY['Martin']::text[]
    WHERE id = 'martin' AND coalesce(array_length(aliases, 1), 0) = 0;
UPDATE public.pms SET aliases = ARRAY['Nelson']::text[]
    WHERE id = 'nelson' AND coalesce(array_length(aliases, 1), 0) = 0;

-- Seed job_pm_assignments from current jobs.pm_id
INSERT INTO public.job_pm_assignments (job_id, pm_id, assigned_at, reason)
SELECT id, pm_id, DATE '2025-01-01', 'initial seed'
FROM public.jobs
WHERE pm_id IS NOT NULL
  AND id NOT IN (SELECT job_id FROM public.job_pm_assignments WHERE ended_at IS NULL);
