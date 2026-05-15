-- 008_diff_review_infrastructure.sql
-- v2 rebuild — Gate 2B: diff-review architecture.
--
-- The Reconciler no longer writes items directly; it writes proposed_changes
-- that go to /v2/review for Jake to accept/edit/reject. The items table stays
-- the source of truth and only contains Jake-approved rows.
--
-- Idempotent. RLS untouched.

CREATE TABLE IF NOT EXISTS public.ingestion_events (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type        text        NOT NULL CHECK (source_type IN (
                            'transcript', 'daily_log', 'pay_app', 'manual')),
    source_meeting_id  uuid        REFERENCES public.meetings(id),
    source_file_path   text,
    source_file_hash   text,
    ingested_at        timestamptz DEFAULT now(),
    ingested_by        text        DEFAULT 'jake',
    review_state       text        NOT NULL DEFAULT 'pending' CHECK (review_state IN (
                            'pending', 'in_review', 'committed', 'rejected', 'partial')),
    reviewed_at        timestamptz,
    reviewed_by        text,
    proposed_count     int         DEFAULT 0,
    accepted_count     int         DEFAULT 0,
    rejected_count     int         DEFAULT 0,
    edited_count       int         DEFAULT 0,
    job_id             text        REFERENCES public.jobs(id),
    notes              text
);

CREATE TABLE IF NOT EXISTS public.proposed_changes (
    id                     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_event_id     uuid        NOT NULL REFERENCES public.ingestion_events(id) ON DELETE CASCADE,
    change_type            text        NOT NULL CHECK (change_type IN (
                                'add_item', 'update_item', 'resolve_item', 'merge_items',
                                'add_decision', 'add_open_question', 'add_signal',
                                'add_sub_event')),

    -- For 'add_item' / 'add_signal' — full proposed row payload
    proposed_item_data     jsonb,

    -- For 'update_item' / 'resolve_item' — pointer to existing + field-diff
    target_item_id         uuid        REFERENCES public.items(id),
    field_changes          jsonb,

    -- For 'merge_items' — destination + source ids
    merge_target_id        uuid        REFERENCES public.items(id),
    merged_from_ids        uuid[],

    -- For 'add_decision' / 'add_open_question'
    proposed_decision_data jsonb,
    proposed_question_data jsonb,

    -- Review state machine
    review_state           text        NOT NULL DEFAULT 'pending' CHECK (review_state IN (
                                'pending', 'accepted', 'rejected', 'edited_and_accepted')),
    reviewed_at            timestamptz,

    -- After acceptance: pointers back into the canonical tables
    resulting_item_id      uuid        REFERENCES public.items(id),
    resulting_decision_id  uuid        REFERENCES public.decisions(id),
    resulting_question_id  uuid        REFERENCES public.open_questions(id),

    -- Audit
    source_claim_ids       uuid[],

    -- Reconciler-supplied confidence
    confidence             text        CHECK (confidence IN ('high', 'medium', 'low')),

    -- Filtering / sort
    job_id                 text        REFERENCES public.jobs(id),
    sub_id                 text        REFERENCES public.subs(id),

    notes                  text,
    created_at             timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proposed_changes_event ON public.proposed_changes (ingestion_event_id);
CREATE INDEX IF NOT EXISTS idx_proposed_changes_state ON public.proposed_changes (review_state);
CREATE INDEX IF NOT EXISTS idx_ingestion_events_state ON public.ingestion_events (review_state);
CREATE INDEX IF NOT EXISTS idx_ingestion_events_job   ON public.ingestion_events (job_id);
