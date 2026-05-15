# Gate 1E Decisions Document — Reconciler Design Rules

**Date:** May 15, 2026
**Purpose:** Lock down 12 design decisions surfaced by the Gate 1D.5 forward-trace before any Reconciler code gets written. Each decision has Claude's recommendation, the alternatives considered, and your override path.
**How to use this:** Read each decision. If you agree, do nothing — the recommendation is locked. If you disagree, mark the line with "OVERRIDE: <your choice>" and tell me. After you've marked it up, this doc becomes the spec for Gate 1D.6 (ingestion) and Gate 1E (Reconciler).

---

## Decision 1: items table ID format (Gap #5)

**Recommendation:** UUID primary key + separate `human_readable_id` text column (format: `KRAU-001`, `FISH-014`, etc.).

**Why:**
- UUID PK matches every other v2 table (jobs, pay_apps, meetings, claims). Single convention is easier to reason about.
- The human-readable form (KRAU-001) is genuinely useful for LLM context — the Reconciler reading "KRAU-014 is still open" is more grokable than reading a UUID.
- Cost: one extra column + a small id-generator function (auto-increment per job prefix).
- v1's binder items used the human-readable form and it worked. We're keeping that affordance, just moving it off the PK.

**Alternatives considered:**
- UUID only — clean but loses LLM legibility
- Human-readable only — matches v1 but breaks v2's UUID convention

---

## Decision 2: claim_type → items.type mapping (Gap #6)

**Recommendation:** Explicit mapping table, written into the Reconciler prompt:

| claim_type (Extractor output) | items.type (Reconciler output) | Notes |
|---|---|---|
| commitment | action | Most common path. A commitment is something someone agreed to do. |
| decision | decision | One-to-one. Decisions become decisions. Tracked separately so they don't get nagged. |
| condition_observed | observation | Site state. Goes in observations, not actions. |
| status_update | (varies — see below) | Most go to `observation`. If the status reveals a stalled item or new commitment, promote to `action`. |
| complaint | flag OR observation | If naming a sub/process as a problem → `flag`. If just venting → `observation`. Reconciler decides based on whether action could resolve it. |
| question | (none — not stored as item) | Questions surface in the meeting document's "Open questions" panel but don't become items. They're answered, not actioned. |

**Why:**
- status_update is the catch-all from the Extractor side (48% of claims), so it needs the most nuanced routing.
- Questions as their own UI surface is a real need from the Pou transcript ("Lee Ross asked Dave about test scheduling, never confirmed"). Treating them as items pollutes the action list. Treating them as nothing loses them.
- Complaints splitting between flag and observation matches how PMs actually use them — "Jason from Creative Trim overcomplicates work" is a flag; "weather was terrible this week" is an observation.

**Alternatives considered:**
- 1:1 mapping (commitment→action, decision→decision, etc.) — too coarse, doesn't handle status_update's catch-all nature
- Single bucket for everything — defeats the v1 lesson that decisions ≠ actions

---

## Decision 3: items.priority derivation (Gap #7)

**Recommendation:** Two-tier — `urgent` or `normal`. Reconciler sets `urgent` if ANY of:

1. Claim contains explicit urgency tokens: "urgent", "ASAP", "critical", "now", "today", "tomorrow", "immediately", "blocking"
2. target_date is within 7 days of meeting_date
3. The matched pay_app_line_item shows >90% complete (we're at the finish line — late items hurt more)
4. The sub has 2+ slipped commitments in the last 30 days (sub-drift override)

Otherwise: `normal`.

**Why:**
- Simple, auditable, deterministic. PMs can predict what gets marked urgent.
- The four triggers are real Ross Built signals — they map to actual reasons something becomes a flag.
- Rule 4 (sub-drift) means a sub that's been screwing up gets their commitments flagged automatically. That's the value of cross-source intelligence.

**Override path:** PMs can manually flip priority in the cockpit. The cockpit edit is preserved across Reconciler runs (Decision 12, clobber protection).

**Alternatives considered:**
- Three tiers (urgent/high/normal) — overhead with no signal benefit
- LLM-scored — non-deterministic, hard to audit
- PM-only manual — defeats the purpose of intelligence layer

---

## Decision 4: items.confidence derivation (Gap #8)

**Recommendation:** Three-tier — `high`, `medium`, `low`. Reconciler sets based on source agreement:

- **high** — Two or more sources corroborate (transcript + daily log, transcript + pay app movement, etc.)
- **medium** — Only the transcript supports it AND the claim itself is clear (named sub, specific scope, explicit commitment language)
- **low** — Only the transcript AND the claim is vague (no named actor, fuzzy scope, hedged language like "we should probably")

Default for cold-start (no daily_logs yet, no prior items): `medium` for clear claims, `low` for vague. No item starts `high` until cross-source data exists.

**Why:**
- The trace surfaced this as load-bearing — confidence is what tells PMs to trust vs verify.
- Tying it to source count makes it auditable: "why is this high? because the daily log on May 10 shows DB Welding on site."
- Cold-start defaulting to medium-or-low is honest. v1 pretended every extracted item was equally trustworthy. It wasn't.

**Alternatives considered:**
- Binary (confirmed/unconfirmed) — too crude
- 0-1 numeric score — looks precise but is fake precision
- LLM-judged — non-deterministic, hides reasoning

---

## Decision 5: target_date extraction (Gap #9)

**Recommendation:** Two columns — `target_date` (date, nullable) + `target_date_text` (text, nullable).

The Reconciler attempts to parse a real date. If it can ("July 4th" → 2026-07-04), `target_date` is populated and `target_date_text` is NULL.

If it can't ("next week", "before the slab pour", "by the end of the month", "ASAP"), `target_date` stays NULL and `target_date_text` captures the raw phrase. confidence drops to medium or low.

Cockpit displays `target_date` if present, falls back to `target_date_text` ("by end of month") if not.

**Why:**
- The trace example ("July 4th") was the easy case. The Pou transcript has tons of "next week"-style commitments.
- Fake-normalizing "next week" to a specific date creates bugs ("Sanger said next week, system says May 22, we missed it on May 22" — but Sanger meant the following week).
- Letting target_date_text survive preserves the PM's intent.

**Alternatives considered:**
- Parse everything to a date with reduced confidence — produces wrong dates, confuses the flag-promotion logic
- NULL only with no text fallback — loses information
- Free-text only (no target_date column) — loses the easy cases

---

## Decision 6: sub-matching strategy (Gap #16)

**Recommendation:** Three-stage cascade, reusing v1's patterns:

1. **Stage 1 — Exact alias match.** For each known sub, check if any alias appears as a substring (case-insensitive) in the claim's `subject` or `statement`. If exactly one sub matches → use it.
2. **Stage 2 — Loose ILIKE on name.** If Stage 1 returns 0 or >1 matches, run an ILIKE %name% query against subs.name. If exactly one match → use it.
3. **Stage 3 — Haiku classifier.** If Stages 1 and 2 both ambiguous or empty, send the claim + the full subs catalog (54 rows) to Claude Haiku as a classification prompt. Use the result. Log the classifier output for later audit.

If Stage 3 returns "none" or null: `sub_id = NULL`, flag the item with `confidence = low`, set `subject` text to whatever the claim said.

**Why:**
- v1 already has `backfill_sub_links.py` (Stages 1-2) and `ai_link_subs.py` (Stage 3) working. Reuse the logic, don't re-import the code (per the freeze).
- Three-stage cascade means cheap matches happen cheaply; expensive Haiku calls only happen when needed.
- Logging classifier outputs builds training data for future improvement.

**Cost estimate:** Maybe 10% of claims hit Stage 3. ~5 cents per Haiku call. Per-meeting ingestion cost stays well under $1.

**Override path:** PM can correct sub assignment in cockpit. Correction is preserved across Reconciler runs.

---

## Decision 7: pay-app line-item matching strategy (Gap #17)

**Recommendation:** Two-stage cascade:

1. **Stage 1 — Keyword ILIKE on description.** Take significant nouns from the claim's `subject` + `statement` (skip common words). Query pay_app_line_items WHERE job_id = X AND description ILIKE '%<keyword>%'. If exactly one match → use it. If 2-3 candidates → use Stage 2. If 0 → `pay_app_line_item_id = NULL`, log "no match found".
2. **Stage 2 — Haiku classifier.** Send the claim + the 2-3 candidate line items to Haiku, ask "which one best matches, or none?" Use the result.

Never go to LLM if Stage 1 returns 0 (no candidates) — leaving NULL is honest. The Reconciler should NOT invent matches.

**Why:**
- The trace's DB Welding → "Exterior Railings" example worked on simple keyword match. That's the common case.
- Some line items are genuinely scope-less ("Contingency", "Bobcat Usage") and shouldn't be matched against. The Stage 1 → NULL path handles this naturally.
- Stage 2 is bounded to 2-3 candidates → cheap classifier call.

**Cost estimate:** Maybe 30% of claims hit Stage 2 (more ambiguity than sub-matching). ~5 cents per call.

**Known limitation logged in v1-known-issues.md:** PCCO change-order items aren't in pay_app_line_items yet (Gate 1B/1C limitation). Claims referencing change orders will get `pay_app_line_item_id = NULL` until PCCO ingestion lands.

---

## Decision 8: multi-job-in-one-meeting routing (Gap #18)

**Recommendation:** Per-claim routing using `subject` text. `meetings.job_id` becomes "the primary job" but is not authoritative — each claim independently resolves its own job_id.

Routing logic in the Reconciler:
1. Check if the claim's `subject` or `statement` contains a job name from the jobs table (matching jobs.name case-insensitively, or jobs.address tokens).
2. If exactly one job name appears → use it.
3. If multiple appear → use the one mentioned closest to the claim's `position_in_transcript`.
4. If none → fall back to `meetings.job_id`.

For meeting metadata: `meetings.job_id` stays singular (no schema change). For office meetings covering multiple jobs, this stores the "primary" job — the Reconciler doesn't trust it for routing but uses it as fallback.

**Why:**
- The trace example (5/07 Krauss+Ruthven office meeting) showed the Extractor already produces subject fields that distinguish jobs. Use what's already there.
- Position-based proximity heuristic handles the "Krauss section, then Ruthven section" pattern that emerges in office meetings naturally.
- Avoiding a meeting_jobs join table keeps the schema simple. If multi-job meetings become a serious pattern later, we add the join table then.

**Alternatives considered:**
- meetings.jobs as array — schema complexity, doesn't help routing decisions
- meeting_jobs join table — overkill for what's mostly single-job meetings
- Trust meetings.job_id only — breaks the office meeting case the trace identified

---

## Decision 9: cross-meeting dedup (Gap #19)

**Recommendation:** Match on the tuple `(job_id, sub_id, pay_app_line_item_id, status='open')`. If a claim's reconciled item would match an existing open item on all three fields → update that item, don't create a new one.

Update logic:
- target_date updates to the more recent commitment
- statement / detail get appended (the meeting that closed it referenced it again — keep the history)
- carryover_count increments
- confidence may increase (new corroboration) or decrease (slipped commitment)

If `pay_app_line_item_id` is NULL on either side, fall back to matching on `(job_id, sub_id, subject_keywords)`. This is fuzzier but handles the case where pay app linking failed.

**Why:**
- The trace example (DB Welding railings) — if next week's Krauss meeting mentions railings again, we want one item with updates, not two.
- Three-field tuple is tight enough to avoid false merges (different railing items wouldn't collide because they'd hit different line items).
- The fallback for NULL pay_app_line_item_id is necessary but flagged as lower-confidence.

---

## Decision 10: ingestion idempotency (Gap #20)

**Recommendation:** Three-layer idempotency:

1. **Meeting layer:** `meetings.source_file_hash` is UNIQUE. Same transcript file → same meeting row. (Already in the schema.)
2. **Claim layer:** Claims are tied to meeting_id and `position_in_transcript`. On re-ingestion of the same meeting, delete existing claims for that meeting_id, re-insert from new Extractor output. Claims are derived artifacts — they're disposable.
3. **Items layer:** Items survive re-ingestion. The Reconciler runs against current items + new claims. If it would re-create an item that already exists (per Decision 9 dedup logic), it updates instead.

**Why:**
- Re-running ingestion needs to be safe (Claude Code or you might re-run during debugging).
- Claims being disposable means we can re-extract with a tuned prompt and replace cleanly.
- Items being durable means cockpit edits and completion history survive.

**Edge case:** If the Extractor prompt changes substantially between runs and produces different claim shapes, re-ingestion will create a one-time blip where items get re-reconciled against new claims. Acceptable for a build-phase system.

---

## Decision 11: clobber prevention on items (Gap #13)

**Recommendation:** Add three columns to the items table schema:
- `previous_status` (text, nullable)
- `manually_edited_at` (timestamptz, nullable)
- `manually_edited_fields` (text[], nullable) — list of column names that have been manually edited

Reconciler upsert logic (mirrors v1's sink_to_supabase patch):
1. Before upserting an item, SELECT the existing row by id.
2. If `manually_edited_at` is NOT NULL on the existing row:
   - For each column in `manually_edited_fields` — preserve the existing value, do not overwrite.
   - For other columns — Reconciler values win.
3. If status was manually set to 'complete' (existing.status='complete' AND existing.completed_at IS NOT NULL):
   - Force new row.status = 'complete', new row.completed_at = existing.completed_at.
   - Reconciler cannot un-complete an item.

Cockpit UPDATE behavior:
- Any manual edit in the cockpit appends the edited column name to `manually_edited_fields` and sets `manually_edited_at = now()`.
- Manual "complete" tap captures `previous_status` before setting to 'complete'.

**Why:**
- This is the same fix v1 just shipped. Non-negotiable. We are not making this mistake twice.
- Tracking edited fields by name (instead of mirroring every field to a `_edited` shadow) keeps the schema clean and lets us extend later.

**This decision is locked. There's no override option. The clobber bug must not return.**

---

## Decision 12: Reconciler retry / Auditor loop (Plan §3, Call 3)

**Recommendation:** Implement Auditor as specified in v2-plan.md Section 3 — but cap retries at 1 (not 2). If the Auditor rejects the Reconciler output twice in a row, surface as "needs Jake's review" and stop.

The Auditor checks:
1. Every claim from the input is accounted for (mapped to an item, mapped to a decision, or explicitly dropped with reason).
2. No item references a sub_id that doesn't exist in subs.
3. No item references a pay_app_line_item_id that doesn't exist for this job_id.
4. Type mappings match Decision 2.
5. Confidence assignments match Decision 4.
6. No duplicate items created (per Decision 9 dedup).

Failure mode: Auditor produces a structured "issues" list. Reconciler runs again with the issues list in context. Max one retry.

**Why:**
- Two retries per meeting × 12 active jobs × 1 meeting per week = 24 retry-attempts per week of unbounded LLM cost. One retry is plenty for the common case (Reconciler missed one item), without runaway costs.
- "Needs review" surfacing is the honest fallback. v1 pretended its output was always correct. v2 admits when it's not sure.

---

## What's not decided here

These remain open and will be decided in later gates:

- **Daily log integration** (Gap #3, #4) — Week 3 scope. Reconciler designed to gracefully handle empty daily_logs in Weeks 1-2.
- **completed_by identity** (Gap #14) — Week 6 (auth gate).
- **Flag promotion rule** (Gap #21) — Week 5 (flag generation logic).
- **completion_note field** (Gap #15) — adding the column is cheap, decide later if cockpit needs the UI.
- **Carryover_count rule** (Gap #11) — Reconciler defaults to "increment on every meeting where item is open and not updated"; revisit if it produces noise.
- **parent_item_id / supersedes** (Gap #12) — sub_events table will cover the sub-phase relationship; revisit if items themselves need linking.

---

## Sign-off

To approve: reply with "approved" or list of overrides.

To override any decision, format your reply as:

```
Decision N: OVERRIDE: <your choice + reasoning>
Decision M: OVERRIDE: <your choice + reasoning>
```

Once approved, this doc gets committed to the repo and the Reconciler is built against it.
