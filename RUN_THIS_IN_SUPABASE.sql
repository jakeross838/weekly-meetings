-- Paste this whole file into Supabase SQL editor → click Run.
-- Idempotent (safe to re-run).
-- Project: takewvlqgwpdbkvcwpvi
--
-- This is the manual-paste MIRROR of MIGRATIONS_SQL in
-- production-cockpit/app/api/admin/run-migrations/route.ts (the /admin/migrate
-- button runs the same statements over a direct pg connection). Keep the two in
-- sync — if you edit one, edit the other. Last synced: 2026-05-20.

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

-- subs.source — distinguishes the human-curated catalog ("manual") from subs
-- auto-created from logged BT crews ("auto"). Mirrors sub_specialties.source.
ALTER TABLE public.subs ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'manual';

-- F3,F6,F8: extend daily_logs to hold per-sub crew sizes, inspections,
-- and photo data + vision summaries. All jsonb so they tolerate scraper
-- shape evolution without further migrations.
ALTER TABLE public.daily_logs
    ADD COLUMN IF NOT EXISTS crew_counts      jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS inspections      jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS photo_urls       jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS photo_summary    jsonb,
    ADD COLUMN IF NOT EXISTS photo_summary_at timestamptz;

CREATE INDEX IF NOT EXISTS daily_logs_crew_counts_idx
    ON public.daily_logs USING GIN (crew_counts);
CREATE INDEX IF NOT EXISTS daily_logs_inspections_idx
    ON public.daily_logs USING GIN (inspections);

-- F5: Canonical schedule items so durations can be compared across subs
-- regardless of how Buildertrend's parent_group_activities tag spells it.
-- A small reference table; everything maps to it by name (lowercased).
CREATE TABLE IF NOT EXISTS public.schedule_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,         -- "Electrical Rough"
    trade text,                        -- "Electrical"
    sequence_order int,                -- rough sort order across a job
    typical_duration_days numeric,
    aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS schedule_items_trade_idx ON public.schedule_items (trade);

-- Optional link from sub_specialties to a canonical schedule_item. When set,
-- the sub profile renders the canonical name and rolls durations up under it.
ALTER TABLE public.sub_specialties
    ADD COLUMN IF NOT EXISTS schedule_item_id uuid REFERENCES public.schedule_items(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS sub_specialties_schedule_item_idx
    ON public.sub_specialties (schedule_item_id);

-- F7: Running checklist items per sub, two lenses (safety / schedule).
-- Free-text item, check-off state, optional note. Order via position int.
CREATE TABLE IF NOT EXISTS public.sub_checklist_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_id text NOT NULL REFERENCES public.subs(id) ON DELETE CASCADE,
    lens text NOT NULL CHECK (lens IN ('SAFETY', 'SCHEDULE')),
    item_text text NOT NULL,
    is_done boolean NOT NULL DEFAULT false,
    done_at timestamptz,
    done_by text,
    notes text,
    position int NOT NULL DEFAULT 0,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sub_checklist_items_sub_idx
    ON public.sub_checklist_items (sub_id);
CREATE INDEX IF NOT EXISTS sub_checklist_items_lens_idx
    ON public.sub_checklist_items (sub_id, lens, position);

-- Seed canonical schedule items if the table is empty. Idempotent: only
-- inserts rows whose name does not already exist. Captures the items Jake
-- specifically called out (T-pole, electrical rough) plus a starter sweep
-- across the trades referenced in v2-plan.md so the canonical layer is
-- useful on day one.
INSERT INTO public.schedule_items (name, trade, sequence_order, typical_duration_days)
SELECT * FROM (VALUES
    ('T-Pole'                  , 'Electrical' ,  5,  1.0),
    ('Underground Electrical'  , 'Electrical' , 15,  3.0),
    ('Electrical Rough'        , 'Electrical' , 50,  7.0),
    ('Electrical Trim'         , 'Electrical' , 90,  5.0),
    ('Electrical Punch'        , 'Electrical' ,100,  2.0),
    ('Underground Plumbing'    , 'Plumbing'   , 10,  3.0),
    ('Plumbing Rough'          , 'Plumbing'   , 48,  7.0),
    ('Plumbing Trim'           , 'Plumbing'   , 88,  4.0),
    ('Plumbing Punch'          , 'Plumbing'   ,100,  2.0),
    ('HVAC Rough'              , 'HVAC'       , 52, 10.0),
    ('HVAC Equipment Set'      , 'HVAC'       , 70,  3.0),
    ('HVAC Trim'              , 'HVAC'       , 92,  4.0),
    ('Excavation / Site Prep'  , 'Site Work'  ,  1,  5.0),
    ('Foundation'              , 'Concrete'   ,  8, 10.0),
    ('Slab'                    , 'Concrete'   , 25,  3.0),
    ('Wall Framing'            , 'Framing'    , 30, 14.0),
    ('Roof Framing'            , 'Framing'    , 38,  7.0),
    ('Sheathing / Dry-In'      , 'Framing'    , 42,  4.0),
    ('Roofing'                 , 'Roofing'    , 45,  5.0),
    ('Window Install'          , 'Windows'    , 47,  3.0),
    ('Stucco Wire/Lath'        , 'Stucco'     , 55,  3.0),
    ('Stucco Scratch'          , 'Stucco'     , 58,  3.0),
    ('Stucco Brown'            , 'Stucco'     , 62,  3.0),
    ('Stucco Finish'           , 'Stucco'     , 95,  4.0),
    ('Insulation'              , 'Insulation' , 60,  3.0),
    ('Drywall Hang'            , 'Drywall'    , 65,  4.0),
    ('Drywall Tape/Finish'     , 'Drywall'    , 68,  6.0),
    ('Drywall Texture'         , 'Drywall'    , 72,  2.0),
    ('Tile Set'                , 'Tile'       , 80,  5.0),
    ('Tile Grout'              , 'Tile'       , 83,  2.0),
    ('Cabinetry Install'       , 'Cabinetry'  , 85,  4.0),
    ('Wood Floor Install'      , 'Flooring'   , 87,  4.0),
    ('Paint Prime'             , 'Paint'      , 75,  3.0),
    ('Paint Body'              , 'Paint'      , 78,  4.0),
    ('Paint Trim'              , 'Paint'      , 89,  3.0),
    ('Interior Trim'           , 'Trim'       , 82,  6.0),
    ('Punch'                   , 'General'    , 99,  5.0)
) AS v(name, trade, sequence_order, typical_duration_days)
WHERE NOT EXISTS (
    SELECT 1 FROM public.schedule_items s WHERE s.name = v.name
);

-- Per-job summary documents — one row per refresh, latest wins. Powers
-- the big AI-generated summary panel on /v2/job/[id]. We keep history
-- (not just overwrite) so we can diff "what changed this week".
CREATE TABLE IF NOT EXISTS public.job_summaries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id text NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    generated_at timestamptz NOT NULL DEFAULT now(),
    summary jsonb NOT NULL,
    last_data_through date,       -- most recent daily_log.log_date considered
    log_count int NOT NULL DEFAULT 0,
    photo_count int NOT NULL DEFAULT 0,
    open_todo_count int NOT NULL DEFAULT 0,
    done_todo_count int NOT NULL DEFAULT 0,
    model text,                   -- e.g. claude-opus-4-7
    elapsed_ms int
);

CREATE INDEX IF NOT EXISTS job_summaries_job_recent_idx
    ON public.job_summaries (job_id, generated_at DESC);

-- Purchase Orders + line items scraped from Buildertrend (/api/PurchaseOrders).
-- amount_remaining is the outstanding (committed-but-unpaid) cost.
CREATE TABLE IF NOT EXISTS public.purchase_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bt_po_id bigint NOT NULL UNIQUE,
    job_key text NOT NULL,
    bt_job_id bigint,
    po_number text,
    title text,
    vendor text,
    bt_vendor_id bigint,
    approval_status text,
    work_status text,
    paid_status text,
    is_bill boolean NOT NULL DEFAULT false,
    cost numeric,
    amount_paid numeric,
    amount_remaining numeric,
    pct_paid numeric,
    pct_remaining numeric,
    pct_billed numeric,
    cost_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
    date_added date,
    scraped_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS purchase_orders_job_idx ON public.purchase_orders (job_key);

CREATE TABLE IF NOT EXISTS public.po_line_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    po_id uuid NOT NULL REFERENCES public.purchase_orders(id) ON DELETE CASCADE,
    bt_line_item_id bigint,
    cost_code text,
    title text,
    description text,
    quantity numeric,
    unit_cost numeric,
    amount numeric,
    amount_paid numeric,
    amount_billed numeric,
    position int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS po_line_items_po_idx ON public.po_line_items (po_id);

-- Manual-wins for scraped tables: user edits/deletes survive the next scrape.
ALTER TABLE public.purchase_orders
    ADD COLUMN IF NOT EXISTS manually_edited_fields text[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS manually_edited_at timestamptz,
    ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS hidden_at timestamptz;
ALTER TABLE public.po_line_items
    ADD COLUMN IF NOT EXISTS manually_edited_fields text[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS manually_edited_at timestamptz,
    ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS hidden_at timestamptz;
ALTER TABLE public.daily_logs
    ADD COLUMN IF NOT EXISTS manually_edited_fields text[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS manually_edited_at timestamptz,
    ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS hidden_at timestamptz;
ALTER TABLE public.subs
    ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS hidden_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS po_line_items_po_btli_uidx
    ON public.po_line_items (po_id, bt_line_item_id);
