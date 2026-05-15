-- 005_add_items_audit_state.sql
-- v2 rebuild — Gate 1F: track Auditor state on items.
-- Project: takewvlqgwpdbkvcwpvi
--
-- Idempotent. RLS untouched (punted).
--
-- audit_state captures the Auditor's verdict for each item. Three values:
--   'clean'        — passed all checks
--   'needs_retry'  — flagged but the Reconciler can plausibly fix it
--   'needs_review' — flagged in a way that needs human attention
-- audit_issues stores the specific issue records as JSON for debugging.

ALTER TABLE public.items
  ADD COLUMN IF NOT EXISTS audit_state  text,
  ADD COLUMN IF NOT EXISTS audit_issues jsonb DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_items_audit_state ON public.items (audit_state);
