-- 010_add_category_to_items.sql
-- Adds a nullable category column to items so v2 items can carry the same
-- categorization the v1 todos table already uses.
--
-- Categories in active use (from todos): SCHEDULE, QUALITY, PROCUREMENT,
-- SELECTION, BUDGET, CLIENT, ADMIN, SUB-TRADE. Left as plain text (no enum)
-- to keep the migration backward-compatible if new categories appear.
--
-- Idempotent. RLS untouched.

ALTER TABLE public.items
    ADD COLUMN IF NOT EXISTS category text;

CREATE INDEX IF NOT EXISTS items_category_idx
    ON public.items (category)
    WHERE category IS NOT NULL;
