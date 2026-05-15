-- 004_create_items_decisions_questions_tables.sql
-- v2 rebuild — Gate 1E: items + decisions + open_questions tables.
-- Project: takewvlqgwpdbkvcwpvi
--
-- Idempotent. RLS not enabled (punted).
--
-- items: the unified action/observation/flag table. Carries clobber-prevention
--   columns (previous_status, manually_edited_at, manually_edited_fields) per
--   Decision 11. uuid PK + human_readable_id text (KRAU-001 style) per
--   Decision 1.
-- decisions: separate table for "we picked X" choices so they don't get nagged.
-- open_questions: separate table for unresolved questions so they don't pollute
--   the action list (Decision 2).

CREATE TABLE IF NOT EXISTS public.items (
    id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    human_readable_id        text        UNIQUE NOT NULL,
    job_id                   text        NOT NULL REFERENCES public.jobs(id),
    pm_id                    text        REFERENCES public.pms(id),
    pay_app_line_item_id     uuid        REFERENCES public.pay_app_line_items(id),
    type                     text        NOT NULL CHECK (type IN ('action', 'observation', 'flag')),
    title                    text        NOT NULL,
    detail                   text,
    sub_id                   text        REFERENCES public.subs(id),
    owner                    text,
    target_date              date,
    target_date_text         text,
    status                   text        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'complete', 'blocked', 'cancelled')),
    priority                 text        DEFAULT 'normal' CHECK (priority IN ('urgent', 'normal')),
    confidence               text        DEFAULT 'medium' CHECK (confidence IN ('high', 'medium', 'low')),
    source_meeting_id        uuid        REFERENCES public.meetings(id),
    carryover_count          int         DEFAULT 0,
    previous_status          text,
    manually_edited_at       timestamptz,
    manually_edited_fields   text[],
    completed_at             timestamptz,
    completed_by             text,
    completion_basis         text,
    created_at               timestamptz DEFAULT now(),
    updated_at               timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.decisions (
    id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    human_readable_id        text        UNIQUE NOT NULL,
    job_id                   text        NOT NULL REFERENCES public.jobs(id),
    source_meeting_id        uuid        NOT NULL REFERENCES public.meetings(id),
    description              text        NOT NULL,
    decided_by               text,
    decision_date            date,
    supersedes_decision_id   uuid        REFERENCES public.decisions(id),
    source_claim_id          uuid        REFERENCES public.claims(id),
    created_at               timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.open_questions (
    id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    human_readable_id        text        UNIQUE NOT NULL,
    job_id                   text        NOT NULL REFERENCES public.jobs(id),
    source_meeting_id        uuid        NOT NULL REFERENCES public.meetings(id),
    question                 text        NOT NULL,
    asked_by                 text,
    status                   text        DEFAULT 'open' CHECK (status IN ('open', 'answered', 'dropped')),
    answer                   text,
    answered_at              timestamptz,
    source_claim_id          uuid        REFERENCES public.claims(id),
    created_at               timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_items_job          ON public.items (job_id);
CREATE INDEX IF NOT EXISTS idx_items_status       ON public.items (status);
CREATE INDEX IF NOT EXISTS idx_items_sub          ON public.items (sub_id);
CREATE INDEX IF NOT EXISTS idx_items_pay_app_line ON public.items (pay_app_line_item_id);
CREATE INDEX IF NOT EXISTS idx_decisions_job      ON public.decisions (job_id);
CREATE INDEX IF NOT EXISTS idx_open_questions_job ON public.open_questions (job_id);
