-- 006_add_actionability_and_carryover_display.sql
-- v2 rebuild — Gate 2A.5: strict actionable classification.
--
-- Add items.actionability — judged by the Reconciler LLM per the strict
-- definition in docs/gate-1e-decisions.md addendum (Gate 2A.5):
--   actionable = has all three of (specific actor, specific deliverable,
--                explicit or inferable timing)
--   signal     = lacks one or more — information worth knowing, not an action
--
-- Idempotent. RLS untouched.

ALTER TABLE public.items
  ADD COLUMN IF NOT EXISTS actionability text
    CHECK (actionability IN ('actionable', 'signal'));

CREATE INDEX IF NOT EXISTS idx_items_actionability ON public.items (actionability);
