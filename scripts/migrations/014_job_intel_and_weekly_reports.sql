-- 014: Job Intelligence spine + Weekly Review (homeowner report, draft-only gate)
-- Phases 1-3 of the Job Intelligence & Weekly Review brief. Fully idempotent.
--
-- Standing rules honored here:
--  * Client-facing output is DRAFT-ONLY until a human approves it (weekly_reports.status gate).
--  * Recalculate, never increment (watermarks/rollups set absolutely elsewhere).
--  * Org-configurable, never hardcoded (models/cadence seeded into app_config).

-- ---------------------------------------------------------------------------
-- Jobs spine: the columns the brief keys routing + lifecycle to. jobs.id stays
-- the canonical slug (e.g. "krauss"); these add the email-routing + BT-id map.
-- ---------------------------------------------------------------------------
ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS pm_email       text,
  ADD COLUMN IF NOT EXISTS client_emails  text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS buildertrend_id text,
  ADD COLUMN IF NOT EXISTS active         boolean NOT NULL DEFAULT true;

-- ---------------------------------------------------------------------------
-- job_intel: the unified durable-intelligence store. Source-agnostic so email,
-- daily logs, and POs all land in one timeline. message_id dedupes email;
-- NULL for non-email sources (unique only when present).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.job_intel (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id        text REFERENCES public.jobs(id) ON DELETE SET NULL,
  source        text NOT NULL DEFAULT 'email'
                  CHECK (source IN ('email', 'daily_log', 'po', 'manual')),
  message_id    text,                  -- Graph message id (email); dedupe key
  sent_at       timestamptz,           -- when the underlying event happened
  project       text,                  -- inferred job name pre-resolution (audit trail)
  intel_type    text,                  -- commitment|decision|client_approval|schedule_change|issue|scope_change|cost|other
  summary       text NOT NULL,         -- one-line recall
  detail        text,                  -- specifics: amounts, dates, names
  action_needed text,                  -- open action, if any
  recipients    text,                  -- email recipients (email source)
  source_ref    text,                  -- log_id / po id / other source pointer
  created_by    text,
  -- manual-wins: a human edit/hide survives a re-capture (mirrors other tables)
  manually_edited_fields text[] NOT NULL DEFAULT '{}',
  manually_edited_at     timestamptz,
  hidden        boolean NOT NULL DEFAULT false,
  hidden_at     timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS job_intel_message_id_uidx
  ON public.job_intel (message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS job_intel_job_idx
  ON public.job_intel (job_id, sent_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS job_intel_created_idx
  ON public.job_intel (created_at DESC);
CREATE INDEX IF NOT EXISTS job_intel_source_idx
  ON public.job_intel (source);

-- ---------------------------------------------------------------------------
-- sync_state: per-mailbox watermark so the same email is never scanned (or
-- paid for) twice. Set absolutely (never incremented) by the capture service.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.sync_state (
  mailbox           text PRIMARY KEY,
  last_processed_at timestamptz NOT NULL,
  updated_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- weekly_reports: DRAFT-ONLY homeowner report with a human approval gate.
-- Nothing is ever auto-sent. Flow: draft -> approved -> sent (sent = a human
-- exported/sent it from the UI). One row per (job, week); latest generation
-- overwrites the draft body but PM edits live in edited_body and win.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.weekly_reports (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id        text NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  week_start    date NOT NULL,          -- Monday of the report week (recalculated)
  period        text NOT NULL DEFAULT 'weekly',
  status        text NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'approved', 'sent')),
  body          jsonb NOT NULL,         -- generated {greeting,budget,schedule,upcoming_selections[],whats_next[],closing}
  edited_body   jsonb,                  -- PM edits (win over body when present)
  model         text,
  generated_by  text,
  generated_at  timestamptz NOT NULL DEFAULT now(),
  approved_by   text,
  approved_at   timestamptz,
  sent_by       text,
  sent_at       timestamptz,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, week_start)
);
CREATE INDEX IF NOT EXISTS weekly_reports_job_idx
  ON public.weekly_reports (job_id, week_start DESC);
CREATE INDEX IF NOT EXISTS weekly_reports_status_idx
  ON public.weekly_reports (status);

-- ---------------------------------------------------------------------------
-- report_feedback: PM feedback per job, fed as context into the next
-- generation so the output tunes to the PM's voice/priorities over time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.report_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id      text NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  feedback    text NOT NULL,
  created_by  text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_feedback_job_idx
  ON public.report_feedback (job_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- app_config seeds (org-configurable knobs). Idempotent: only inserts a key
-- that is missing, so existing operator values are never clobbered.
-- ---------------------------------------------------------------------------
INSERT INTO public.app_config (key, value)
SELECT v.key, v.value FROM (VALUES
  ('WEEKLY_REPORT_MODEL',  'claude-opus-4-7'),
  ('INTEL_EXTRACT_MODEL',  'claude-haiku-4-5-20251001'),
  ('INTEL_ANALYZE_MODEL',  'claude-sonnet-4-6'),
  ('MEETING_CADENCE',      'weekly'),
  ('REPORT_WEEK_START',    'monday')
) AS v(key, value)
WHERE NOT EXISTS (SELECT 1 FROM public.app_config c WHERE c.key = v.key);
