-- 003_create_meeting_claims_tables.sql
-- v2 rebuild — Gate 1D: meetings + claims tables (Call 1 of 3 brain).
-- Project: takewvlqgwpdbkvcwpvi
--
-- Idempotent. RLS not enabled (punted).
--
-- meetings holds one row per processed transcript. extracted_at /
-- reconciled_at / audited_at let the three-call pipeline track which
-- stage has run.
-- claims holds the raw output of Call 1 (Extractor). Kept for audit:
-- you can always go back to "what did the brain see and how did it
-- classify it" without re-running the LLM.

CREATE TABLE IF NOT EXISTS public.meetings (
    id                     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                 text        NOT NULL REFERENCES public.jobs(id),
    pm_id                  text        REFERENCES public.pms(id),
    meeting_date           date        NOT NULL,
    meeting_type           text        CHECK (meeting_type IN ('site', 'office')),
    attendees              text[],
    transcript_file_path   text,
    raw_transcript_text    text,
    source_file_hash       text        UNIQUE,
    extracted_at           timestamptz,
    reconciled_at          timestamptz,
    audited_at             timestamptz,
    reconciler_version     text,
    created_at             timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.claims (
    id                     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id             uuid        NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    speaker                text,
    claim_type             text        NOT NULL CHECK (claim_type IN (
                              'commitment','decision','condition_observed',
                              'status_update','question','complaint')),
    subject                text,
    statement              text        NOT NULL,
    raw_quote              text,
    position_in_transcript int,
    extracted_at           timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_claims_meeting ON public.claims (meeting_id);
CREATE INDEX IF NOT EXISTS idx_meetings_job   ON public.meetings (job_id);
