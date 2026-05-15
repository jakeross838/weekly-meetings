-- 002_create_pay_app_tables.sql
-- v2 rebuild — Gate 1B: pay app schema (header + line items).
-- Project: takewvlqgwpdbkvcwpvi
--
-- Idempotent: safe to re-run. Uses CREATE TABLE IF NOT EXISTS and
-- CREATE INDEX IF NOT EXISTS. RLS intentionally not enabled (punted).
--
-- pay_apps holds one row per parsed pay app (one xlsx file).
-- pay_app_line_items holds the G703 line items for each pay app.
-- source_file_hash is UNIQUE so re-ingesting the same file is rejected.
-- (job_id, pay_app_number) is also UNIQUE to catch human re-uploads with
-- a renamed file.

CREATE TABLE IF NOT EXISTS public.pay_apps (
    id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                   text        NOT NULL REFERENCES public.jobs(id),
    pay_app_number           int         NOT NULL,
    application_date         date,
    contract_amount          numeric,
    total_completed_stored   numeric,
    retainage                numeric,
    current_payment_due      numeric,
    source_file_name         text,
    source_file_hash         text        UNIQUE,
    parsed_at                timestamptz DEFAULT now(),
    raw_g702_json            jsonb,
    UNIQUE (job_id, pay_app_number)
);

CREATE TABLE IF NOT EXISTS public.pay_app_line_items (
    id                          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    pay_app_id                  uuid        NOT NULL REFERENCES public.pay_apps(id) ON DELETE CASCADE,
    job_id                      text        NOT NULL REFERENCES public.jobs(id),
    line_number                 text        NOT NULL,
    description                 text,
    division                    text,
    scheduled_value             numeric,
    work_completed_previous     numeric,
    work_completed_this_period  numeric,
    materials_stored            numeric,
    total_completed             numeric,
    pct_complete                numeric,
    balance_to_finish           numeric,
    retainage                   numeric,
    raw_row_index               int,
    created_at                  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pay_app_line_items_job     ON public.pay_app_line_items (job_id);
CREATE INDEX IF NOT EXISTS idx_pay_app_line_items_pay_app ON public.pay_app_line_items (pay_app_id);
CREATE INDEX IF NOT EXISTS idx_pay_apps_job               ON public.pay_apps (job_id);
