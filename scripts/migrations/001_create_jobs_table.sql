-- 001_create_jobs_table.sql
-- v2 rebuild — Gate 1A: create and seed the jobs table.
-- Project: takewvlqgwpdbkvcwpvi
--
-- Idempotent: safe to re-run. Uses CREATE TABLE IF NOT EXISTS,
-- CREATE INDEX IF NOT EXISTS, and INSERT ... ON CONFLICT DO NOTHING.
--
-- RLS is intentionally NOT enabled (punted to Phase 2 per Gate 1A scope).
-- No foreign-key constraint is added between todos.job and jobs.name (free
-- text mismatch audit deferred to a later gate); only an index on todos.job.

CREATE TABLE IF NOT EXISTS public.jobs (
    id              text        PRIMARY KEY,
    name            text,
    address         text,
    pm_id           text        REFERENCES public.pms(id),
    phase           text,
    status          text,
    target_co_date  date,
    gp_pct          numeric,
    contract_amount numeric,
    bt_long_key     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_pm_id ON public.jobs (pm_id);
CREATE INDEX IF NOT EXISTS idx_todos_job  ON public.todos (job);

INSERT INTO public.jobs (id, name, address, pm_id, phase, bt_long_key) VALUES
    ('drummond', 'Drummond', '501 74th St',                      'bob',    NULL,               'Drummond-501 74th St'),
    ('molinari', 'Molinari', '791 North Shore Dr',               'bob',    NULL,               'Molinari-791 North Shore Dr'),
    ('biales',   'Biales',   '103 Seagrape Ln',                  'bob',    NULL,               'Biales-103 Seagrape Ln'),
    ('pou',      'Pou',      '109 Seagrape Ln',                  'jason',  NULL,               'Pou-109 Seagrape Ln'),
    ('dewberry', 'Dewberry', '681 Key Royale Dr',                'jason',  NULL,               'Dewberry-681 Key Royale Dr'),
    ('harllee',  'Harllee',  '215 Sycamore',                     'jason',  NULL,               'Harllee-215 Sycamore'),
    ('krauss',   'Krauss',   '427 South Blvd of the Presidents', 'lee',    NULL,               'Krauss-427 South Blvd of the Presidents'),
    ('ruthven',  'Ruthven',  '673 Dream Island Rd',              'lee',    NULL,               'Ruthven-673 Dream Island Rd'),
    ('fish',     'Fish',     '715 North Shore Dr',               'martin', NULL,               'Fish-715 North Shore Dr'),
    ('markgraf', 'Markgraf', '5939 River Forest Circle',         'nelson', NULL,               'Markgraf-5939 River Forest Circle'),
    ('clark',    'Clark',    '853 North Shore Dr',               'nelson', NULL,               'Clark-853 North Shore Dr'),
    ('johnson',  'Johnson',  NULL,                               'nelson', 'pre-construction', NULL)
ON CONFLICT (id) DO NOTHING;
