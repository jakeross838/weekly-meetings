# Forward-trace: one v2 Extractor claim → Monday document

**Date:** 2026-05-15
**Purpose:** Walk a single real claim from the Gate 1D.5 Extractor output all the way through the v2 system the plan describes, using real data where it exists and surfacing gaps where it doesn't. No code or schema changes. Thinking artifact only.

---

## 1. The chosen claim

```json
{
  "speaker": "Lee Worthy",
  "claim_type": "commitment",
  "subject": "DB Welding railings",
  "statement": "Lee told DB Welding that all railings need to be on the house by July 4th.",
  "raw_quote": "I told DB Welding yesterday that all railings need to be on the house by July 4 t h.",
  "position_in_transcript": 42870
}
```

**Source meeting:** Krauss/Ruthven Office Production Meeting, 2026-05-07
**Source file:** `C:/Users/Jake/Downloads/05-07 Krauss_Ruthven Office Production Meeting-transcript.txt`
**v2 Extractor output:** `/tmp/extractor-out-v2/05-07_Krauss_Ruthven_Office_Production_Meeting-transcript.json`
**Inferred job:** `krauss` (subject + meeting context — see §subject-routing gap)
**Inferred PM:** `lee` (Lee Worthy from `pms` table — though Lee Ross also attended)

### Why this claim over the alternatives

I shortlisted 13 commitment/decision claims that named a sub and referenced a pay-app-bearing job. The DB-Welding-railings claim wins on five dimensions, which makes it the most demanding test case:

| Criterion | Why it matters | Status |
|---|---|---|
| **Named sub + alias in catalog** | Forces real sub-lookup, not "TODO" | ✓ DB Welding Inc. is in subs with "DB Welding" as an alias |
| **Scope maps to a real pay app line item** | Forces real `pay_app_line_item_id` resolution | ✓ Krauss line 26110 "Exterior Railings" $82,500 / 0% |
| **Explicit target_date** | Tests the easy case for date extraction | ✓ "July 4th" is unambiguous |
| **Specific actor** | Tests `owner` vs `sub_id` split (Lee said it, DB Welding does it) | ✓ Lee Worthy is the speaker, DB Welding is the doer |
| **High intrinsic confidence** | Reconciler should land this at `confidence=high` | ✓ Direct first-person commitment by the PM |

Alternatives like "Walter is going to come back and fix the bad drywall corners" lacked a date; "Going to use the siding guy from Pou rather than Miguel" had no target deadline; "Backer board: Kerfboard instead of Durock" had no named sub. The DB Welding claim is the gold-standard shape.

---

## 2. Walking the claim forward

### Step A — The claim as stored

**What the schema says:** `public.claims` was created in Gate 1D (migration 003). One row per claim, FK to `meetings`.

**What the Reconciler should see if it queried right now:**

```sql
SELECT * FROM public.claims
WHERE meeting_id = '<the 5/07 Krauss/Ruthven meeting uuid>';
```

**Actual result of running this:** **zero rows**.

**Gap:** The Extractor is dry-run only. It writes JSON to `/tmp/extractor-out-v2/`, not to `public.claims`. The `meetings` row also doesn't exist — there's been no ingestion step for meetings/claims analogous to Gate 1C's pay app ingestion. Gate 1E (Reconciler) will need this data to do anything useful, so an ingestion step (gates 1D.6 or part of 1E) must land before the Reconciler can run.

When it does land, the expected row will look like:

```text
id                     = <new uuid>
meeting_id             = <5/07 meeting uuid>
speaker                = 'Lee Worthy'
claim_type             = 'commitment'
subject                = 'DB Welding railings'
statement              = 'Lee told DB Welding that all railings need to be on the house by July 4th.'
raw_quote              = 'I told DB Welding yesterday that all railings need to be on the house by July 4 t h.'
position_in_transcript = 42870
extracted_at           = now()
```

### Step B — Reconciler input

Per the plan (Section 3, Call 2), the Reconciler needs four input streams:

#### B1. Existing open items for this job

```sql
SELECT id, type, title, sub_id, target_date, status, pay_app_line_item_id
FROM public.items
WHERE job_id = 'krauss' AND status IN ('open', 'in_progress', 'blocked')
ORDER BY created_at;
```

**Result of running today:** **error — table `public.items` does not exist.** Gate 1E builds this table.

**Implication for Gate 1E:** the Reconciler must handle the cold-start case (no prior items) cleanly. The first run on a job creates items; the second run reconciles against the first run's output.

#### B2. Recent claims for this sub across other meetings

```sql
SELECT c.id, c.meeting_id, c.statement, c.position_in_transcript, m.meeting_date, m.job_id
FROM public.claims c
JOIN public.meetings m ON m.id = c.meeting_id
WHERE
    (c.subject ILIKE '%DB Welding%'
     OR c.statement ILIKE '%DB Welding%'
     OR c.raw_quote ILIKE '%DB Welding%')
ORDER BY m.meeting_date DESC
LIMIT 20;
```

**Result of running today:** **zero rows** — same blocker as B1: claims aren't ingested yet.

**Subtler gap:** even when ingested, this query relies on free-text ILIKE matching of the sub *name*. The subs catalog has `aliases` (DB Welding has "DB Welding", "DB Fabrication", "Dave at DB"). The Reconciler can't just ILIKE on one form — it must search by all aliases. That's a real query the Reconciler needs to compose, and there's no helper function in v1's process.py that does sub-alias-aware claim search.

#### B3. Pay app line items for this job

```sql
SELECT line_number, description, scheduled_value, total_completed,
       pct_complete, balance_to_finish, division
FROM public.pay_app_line_items
WHERE job_id = 'krauss'
  AND (description ILIKE '%rail%'
       OR description ILIKE '%weld%'
       OR description ILIKE '%metal%'
       OR description ILIKE '%iron%'
       OR description ILIKE '%balcony%');
```

**Result of running today (real data):**

| line_number | description | scheduled | done | pct |
|---|---|--:|--:|--:|
| **26110** | **Exterior Railings-includes roof railings/posts** | **$82,500.00** | **$0.00** | **0.0%** |
| 39101 | Dump Trailer Usage | $1,000.00 | $600.00 | 60.0% (false positive on "rail") |

**The Reconciler should pick `26110`.** Exact and only sensible match.

**Gap:** keyword search worked here because "railings" is a strong, unique term. It won't work for vague claims like "DB Welding to handle the rough-in pieces" (which `26110` would still match, but so would `26111` and any other 26-division line). A more structured matcher (LLM-assisted "best line item" classifier, like v1's `ai_link_subs.py` for subs) probably belongs in the Reconciler. For now, simple ILIKE is acceptable for high-confidence claims; ambiguous ones should leave `pay_app_line_item_id` NULL and flag for review.

#### B4. Recent daily logs for this job

```sql
SELECT log_date, notes_text, activity_summary, crews_on_site
FROM public.daily_logs
WHERE job_id = 'krauss' AND log_date >= '2026-04-01'
ORDER BY log_date DESC;
```

**Result of running today:** **error — table `public.daily_logs` does not exist.**

The data exists outside Supabase: `C:\Users\Jake\buildertrend-scraper\data\daily-logs.json` contains 329 Krauss logs as of the May 4 manual scrape (Gate 0 audit). The plan's Week 3 builds the `daily_logs` table and ingests these.

**Gap that compounds:** without `daily_logs`, the Reconciler can only operate on two of the four planned signal sources (claims + pay_app_line_items). The "did Sanger actually show up this week" cross-check is *not* possible until the scraper is repaired and daily logs are ingested. The Reconciler can still output reconciled items — they just won't carry daily-log evidence in their `confidence` or `completion_basis`. Worth deciding whether Gate 1E ships without daily-log integration or waits.

### Step C — The `items` row the Reconciler should produce

The plan's Section 5c schema, filled out for this claim:

| Field | Value | Source / Notes |
|---|---|---|
| `id` | **see gap below** | Plan says `KRAU-001` style; Gates 1A/B/C used `uuid`. **Inconsistency to resolve in Gate 1E.** |
| `job_id` | `'krauss'` | Inferred from subject + meeting context (the 5/07 meeting covers both Krauss and Ruthven; "railings" + speaker context puts this on Krauss) |
| `pm_id` | `'lee'` | Lee Worthy ran the meeting; PM_JOBS maps Lee Worthy → Krauss |
| `pay_app_line_item_id` | uuid of `26110` (Exterior Railings) | Matched via the ILIKE query in B3. Confidence: high (only sensible match). |
| `type` | `'action'` | Derived from `claim_type='commitment'` → `type='action'`. **Mapping not specified anywhere — see gap.** |
| `title` | `'DB Welding: all railings on house by Jul 4'` | Compressed from `claim.statement` |
| `detail` | `'Lee Worthy told DB Welding yesterday that all railings need to be on the house by July 4th. Source: Krauss/Ruthven office meeting 2026-05-07. Maps to pay app line item 26110 "Exterior Railings" ($82,500 scheduled, 0% complete as of pay app #10).'` | Constructed text — includes pay-app cross-reference |
| `sub_id` | `'db-welding-inc'` | Resolved from subs by name + aliases (Step §sub-identity) |
| `owner` | `NULL` | Sub-owned items leave `owner` NULL per Section 5c |
| `target_date` | `2026-07-04` | Parsed from "July 4th" + current year (today is May 15, July 4 is the next future July 4) |
| `status` | `'open'` | Initial value |
| `priority` | **see gap** | Plan says `urgent` or `normal`. Reconciler derivation rule not specified. Defensible default: `normal` (7 weeks to deadline, no slippage flag yet). |
| `confidence` | `'high'` | First-person, named sub, named scope, explicit date, mapped to a pay app line item |
| `source_meeting_id` | <5/07 meeting uuid> | FK to meetings (once that row exists) |
| `source_daily_log_id` | `NULL` | No daily logs ingested yet |
| `created_at` | `now()` | Default |
| `completed_at` | `NULL` | Initial |
| `completed_by` | `NULL` | Initial |
| `completion_basis` | `NULL` | Set only at completion |
| `carryover_count` | `0` | Fresh item |

### Step D — Schema fit check

Walking each field in Section 5c for *this* claim:

| Field | Fit verdict | Notes |
|---|---|---|
| `id` | ⚠️ **AMBIGUOUS** | Plan says "KRAU-001 LLM-friendly id pattern" but Gates 1A/B/C all use uuid. Pick one. Suggestion: uuid for PK + a separate `human_readable_id` text column ("KRAU-001") for LLM legibility. |
| `job_id` | ✓ | Exists on `jobs`. Note 5/07 meeting metadata may need both job_ids — see §subject-routing gap. |
| `pm_id` | ✓ | Exists on `pms`. Multi-PM meetings (very rare here) would need a list, but for 5/07 office meeting one PM is fine. |
| `pay_app_line_item_id` | ✓ | FK works. NULL when no match — acceptable. |
| `type` | ⚠️ | Plan enum is `action / decision / observation / flag / question`. Claim enum is `commitment / decision / condition_observed / status_update / complaint / question`. **No mapping table is anywhere in the plan or code.** Gate 1E must specify it. (Suggested: commitment→action, decision→decision, condition_observed→observation, complaint→flag, question→question, status_update→observation OR observation-with-status-flavor.) |
| `title` | ✓ | Text, derived from `statement`. |
| `detail` | ✓ | Text, can hold the full context + cross-references. |
| `sub_id` | ✓ | Found in subs. See §sub-identity for the DB Welding vs DB Improvement disambiguation case. |
| `owner` | ✓ | Text. NULL when `sub_id` is set. |
| `target_date` | ⚠️ | Works for this claim (explicit "July 4th"). Most claims won't have explicit dates. **No date extraction strategy is specified.** Vague claims like "next week" or "after the slab pour" need a policy: store as NULL + reasoning, or normalize to a best-guess date with low confidence, or add a `target_date_text` field for free-text? |
| `status` | ✓ | Enum is clear. |
| `priority` | ⚠️ | Enum is clear (urgent / normal). **Derivation rule not specified.** Possible signals: explicit "urgent" / "ASAP" in the claim; pay-app gap (e.g. 0% complete + deadline within 30 days); sub drift history; PM tone. Gate 1E should write the rule down. |
| `confidence` | ⚠️ | Enum (high / medium / low) is clear, **derivation rule not specified.** Plausible signals: speaker identity (PM > sub > unknown), claim_type (commitment > status_update), explicit-vs-inferred date, pay-app mapping success. |
| `source_meeting_id` | ✓ | FK works. |
| `source_daily_log_id` | ✓ but unusable | FK to a table that doesn't exist yet. |
| `created_at`, `completed_at`, `completed_by`, `completion_basis`, `carryover_count` | ⚠️ | Schema is fine but `carryover_count` increment logic is unspecified — does it tick every Reconciler run, every meeting, or only when nothing changes? |

### Step E — Monday document rendering

Per the plan's Section 4, the document has three lanes: Flags / This week / Open.

Today (2026-05-15) the target is **Jul 4 (50 days out)**. Status is `open`. No slippage signal yet. This item belongs in **Open**.

```
─────────────────────────────────────────────────────────────────────────
OPEN — Krauss (Lee Worthy)
─────────────────────────────────────────────────────────────────────────
● DB Welding: all railings on house by Jul 4                  50 days · 8d open
   from 5/07 office · pay app line 26110 ($82.5K · 0%)
─────────────────────────────────────────────────────────────────────────
```

Breakdown of the line:

- **Section:** Open (not Flags — no slippage; not This week — Jul 4 is not this week)
- **Row text:** title compressed from `statement` to single line; sub-line gives source meeting and pay-app cross-reference
- **Confidence dot:** green `●` (high — first-person PM commitment with named sub + named scope + explicit date + pay-app match)
- **Right-edge indicator:** target date countdown ("50 days") on top; days-open since claim creation ("8d open") underneath
- **Source attribution:** "from 5/07 office" — short form of meeting type + date. Clicking through goes to the meeting page with the original transcript and the raw_quote highlighted at position 42870.
- **Pay-app annotation:** "pay app line 26110 ($82.5K · 0%)" — pulls scheduled value + current % from the linked line item, giving the PM real-time financial context without leaving the row.

This is what the row looks like in the **Open** view filtered to Krauss. In the **whole-company Flags+This-week** view (Jake's Monday morning view), this row would NOT appear yet — it's not slipping and not due this week. If Jul 4 approaches without movement on pay app % complete, the Reconciler should *promote* it to Flags.

**Gap:** "promotion to Flags" logic isn't specified in the plan. When does a not-yet-slipped item escalate? Probably: target_date approaching + linked pay app pct_complete = 0 → flag at T−14 days. Gate 1E or a later gate needs the rule.

### Step F — Check-off write-back

If a PM taps this item complete in the cockpit, the literal SQL would be:

```sql
UPDATE public.items
SET
    status = 'complete',
    completed_at = now(),
    completed_by = '<user identifier>',
    completion_basis = 'manual'
WHERE id = '<this item id>'
RETURNING id, status, completed_at;
```

**Fields that need to be captured at check-off but aren't trivially present:**

- `completed_by` — Section 5c schema says "user or 'auto'". The v1 cockpit doesn't currently authenticate per-user (it uses a service-role connection). **Gap:** v2 cockpit needs identity. Vercel password-protect (mentioned in Week 6) doesn't identify *which* PM tapped; that's a missing capability the plan should address before /api/complete-v2 is built.
- `completion_basis` — fixed string "manual" for manual taps; but Section 4 also describes auto-resolution by the brain ("daily log + pay app shows item done → auto-mark complete with note"). The Reconciler running between meetings would write `completion_basis='daily log + pay app'`. The schema field is text, which works, but **the controlled vocabulary isn't defined**: `manual` / `daily log + pay app` / `transcript inference` / something else? Gate 1E should fix.
- `completion_note` (NOT IN SCHEMA) — if a PM taps complete on partial work ("DB Welding got the back-yard rails up but not the front porch"), the system loses that nuance. Plan describes the system silently asking "based on what?" — but there's no field to store the basis text beyond the controlled-vocabulary one. **Gap:** consider adding a `completion_note` free-text field, or repurposing `completion_basis` as free-text rather than enum.

### Step G — Round-trip: next meeting

Setup: it's now early June. The next Krauss meeting transcript mentions DB Welding doing follow-up work — say, "DB Welding installed the railings, looks great, now they're doing the kitchen welding fabrication."

What should the Reconciler do?

1. **Auto-complete the existing railings item.** The new transcript explicitly says "installed". If pay app #11 has also moved line 26110's pct_complete from 0% → 100%, that's two-source confirmation; Reconciler writes:
   ```
   UPDATE items SET status='complete', completed_at=now(),
       completed_by='auto',
       completion_basis='transcript inference + pay app'
   WHERE id = <railings item id>;
   ```
2. **Create a *new* item for the kitchen welding scope.** Different `pay_app_line_item_id` (the outdoor kitchen line, whatever number), same `sub_id='db-welding-inc'`, new commitment.

**How does the Reconciler know NOT to extend the railings item?** Two signals would tell it:
- `pay_app_line_item_id` differs (railings 26110 vs kitchen welding ~28xxx)
- `subject` text differs ("DB Welding railings" vs "DB Welding kitchen fab")

**Does the schema support "X follow-up after Y" relationships?** **No.** Section 5c has no `parent_item_id`, `supersedes_item_id`, or `related_item_ids` field on the items table. The two items would be entirely independent rows. The history of the relationship lives only in the `detail` text and the `source_meeting_id` chain — there's no first-class relationship to query.

For the railings → kitchen welding scenario this is probably fine — they're genuinely separate items. The relationship that *would* be nice to model is **multi-phase work** for the same sub (electrical rough-in → trim-out → punch). The plan's Week 5 (sub profiles + flags) cares about sub-phase events tracked in `sub_events`, which is a *separate* event log table — so the relationship modeling is on `sub_events`, not `items`. That's probably right, but worth confirming.

**One more wrinkle:** in the v1 system, the LLM round-trip "clobbered" cockpit edits (which is what the May 14 `63d75fe` patch fixed). The v2 Reconciler has the same hazard: if a PM has manually edited an item's title or marked it complete, and then a new transcript references that item, the Reconciler must NOT overwrite the manual state. **Gap:** the plan doesn't say how this is prevented. Section 5c doesn't have `manually_edited_at` or similar flags on items. The clobber-prevention pattern from v1 (preserve cockpit edits + completions on LLM round-trip) needs to be ported into the Reconciler's UPDATE logic, and the schema needs the flag fields v1 has (`previous_status`, `edited_title`, `edited_at`).

---

## 3. Sub-identity reality check

The plan (Section 9C) warned subs identity is messier than the schema implies. For the chosen claim, the relevant query is:

```sql
SELECT id, name, trade, aliases
FROM public.subs
WHERE name ILIKE '%db%' OR name ILIKE '%welding%' OR name ILIKE '%improvement%'
   OR EXISTS (
       SELECT 1 FROM unnest(coalesce(aliases, ARRAY[]::text[])) a
       WHERE a ILIKE '%db%' OR a ILIKE '%welding%' OR a ILIKE '%improvement%'
   );
```

**Actual result (run today):**

| id | name | trade | aliases |
|---|---|---|---|
| `db-welding-inc` | DB Welding Inc. | Metal/Welding | `[DB Welding, DB Fabrication, Dave at DB]` |
| `db-improvement-services` | DB Improvement Services | Trim/Finish | `[DB Improvements, DB Improvement]` |

So there are **two `DB-`-prefixed companies** in the catalog. They are clearly distinct entities (different trades, different aliases). The good news: the v1 alias system already disambiguates them — a search for "DB Welding" via `aliases @> ARRAY['DB Welding']` matches only `db-welding-inc`, and a search for "DB Improvement" matches only the other.

**But the Reconciler's matching strategy isn't yet specified.** Plausible strategies:

1. **Exact alias match (strictest):** match only if the claim's text contains an alias verbatim. Pros: zero false positives in this case. Cons: misses transcription errors ("D B Welding" with a space).
2. **Loose ILIKE on alias-joined text:** match if any alias appears as a substring. Pros: catches transcription noise. Cons: would still differentiate DB Welding from DB Improvement here because their aliases don't overlap.
3. **LLM classifier (v1's `ai_link_subs.py` pattern):** for any claim where the simple matcher returns 0 or 2+ candidates, route to a Haiku classifier with the full subs catalog as context. Pros: robust. Cons: API cost + latency on every Reconciler run.

**Recommended for Gate 1E:** strategy 2 (loose ILIKE on aliases) as the default, fall back to strategy 3 (Haiku classifier) when 0 or >1 candidates match. v1's `backfill_sub_links.py` already implements strategy 2; v1's `ai_link_subs.py` already implements strategy 3. They're frozen but they're reusable templates — the v2 Reconciler can replicate the logic without importing from v1.

**Looking beyond DB:** the broader sub-identity check on the 54-row subs table:
- I checked one prefix (DB) and found two real entities. Other prefixes likely have similar near-duplicates (Mike's Plumbing vs Mike Smith Plumbing, etc.) — I didn't enumerate them here.
- The `aliases` array is the load-bearing structure. It's only as good as the curation effort behind it. The May 5 dedup pass on binders (`scripts/dedup_binders.py`) tightened things; whether the subs catalog itself was deduped is unclear from the v1 freeze.

**For this specific claim**, the lookup is unambiguous: `'db-welding-inc'`. The Reconciler will land it cleanly. But the framework needs the strategy written down.

---

## 4. Gap inventory

Numbered, ruthlessly. Severity tags: **BLOCKS-1E** (blocks Gate 1E build), **BLOCKS-LATER** (blocks a downstream gate), **DECIDE-LATER** (won't block, but needs a written answer).

### Data plumbing

1. **`claims` and `meetings` tables aren't populated.** Extractor writes to `/tmp/extractor-out-v2/` only. Gate 1D didn't include the ingestion step. **BLOCKS-1E** — the Reconciler can't read what isn't there. Suggested: add an ingestion gate (1D.6) or roll it into 1E.
2. **`items` table doesn't exist yet.** Section 5c spec is written but not migrated. **BLOCKS-1E** — Gate 1E creates it.
3. **`daily_logs` table doesn't exist yet.** The Buildertrend scraper produces `daily-logs.json` (3,253 logs, 329 for Krauss). The plan's Week 3 builds the table. **BLOCKS-LATER** — the Reconciler can produce useful output without it, but its cross-source confidence claims will be weak.
4. **Buildertrend scraper is broken** (stale Supabase URL, daily failures since 2026-03-26 per the Gate 0 audit). Even when `daily_logs` is built, the scraper needs repair first. **BLOCKS-LATER** (Week 3).

### Schema decisions

5. **`items.id` format inconsistent with rest of v2.** Plan says `KRAU-001` (human-readable). Gates 1A/B/C/D all chose uuid. **BLOCKS-1E** — pick one. Suggested: uuid for PK + a separate text `human_readable_id` column for LLM legibility.
6. **`claim_type` → `items.type` mapping not specified.** Six claim types map to five item types. **BLOCKS-1E** — Gate 1E needs the explicit mapping table.
7. **`items.priority` derivation rule unspecified.** Enum is clear, but how the Reconciler chooses `urgent` vs `normal` isn't. **BLOCKS-1E** — write the rule. (Plausible: explicit "urgent"/"ASAP" tokens; pay-app gap + tight deadline; sub-drift history.)
8. **`items.confidence` derivation rule unspecified.** Same shape of gap. **BLOCKS-1E** — write the rule.
9. **`items.target_date` extraction for vague dates is unspecified.** Easy case ("July 4th") is easy. Vague cases ("next week", "after the slab pour", "before the holiday weekend") aren't. **BLOCKS-1E** — pick: NULL + free-text reasoning, normalized best-guess with low confidence, or add a `target_date_text` column.
10. **`items.completion_basis` controlled vocabulary undefined.** Schema is text, but what strings does it accept? "manual"/"daily log + pay app"/"transcript inference"/...? **DECIDE-LATER** — fine as free-text in 1E, lock down later.
11. **`carryover_count` increment rule unspecified.** Per Reconciler run, per meeting, or only on no-change? **DECIDE-LATER**.
12. **No `parent_item_id` / `supersedes_item_id` on items.** Sub follow-up work over multiple phases becomes separate rows with no first-class link. **DECIDE-LATER** — `sub_events` covers the sub-phase relationship; whether items also needs to link is a judgment call.
13. **No clobber-prevention flags on items.** Need `previous_status`, `edited_title`, `edited_at` analogous to v1's todos table — otherwise the v1 LLM-clobber bug recurs in v2 the first time a PM manually edits and the Reconciler re-runs. **BLOCKS-1E** — add these columns to the migration.
14. **No `completed_by` identity capture path.** Schema field exists but the cockpit has no per-user identity today. **BLOCKS-LATER** (Week 6 auth gate).
15. **No `completion_note` free-text field.** PMs marking complete on partial scope lose the "complete *with caveats*" nuance. **DECIDE-LATER**.

### Reconciler logic

16. **Sub-matching strategy not specified.** Aliases exist but how the Reconciler uses them (strict / loose / LLM fallback) is undefined. **BLOCKS-1E** — write the strategy. v1's `backfill_sub_links.py` + `ai_link_subs.py` are reusable templates.
17. **Pay-app line-item matching strategy not specified.** Keyword ILIKE worked for this claim; ambiguous cases need a fallback (LLM-assisted classifier? leave NULL + flag?). **BLOCKS-1E** — pick.
18. **Multi-job-in-one-meeting routing.** The 5/07 office meeting metadata has `job_id='krauss'`, but the transcript covers both Krauss and Ruthven. The Extractor produced subject fields that distinguish them; the Reconciler must use `subject` text (not `meeting.job_id` alone) to route each claim to the right job. **BLOCKS-1E** — write the routing rule and decide whether `meetings.job_id` is even meaningful for office-type meetings.
19. **Cross-meeting dedup logic not specified.** If "DB Welding railings July 4" appears in multiple meetings, should those be one item with updates or many items? **BLOCKS-1E** — write the rule (likely: same sub + same pay_app_line_item_id + open status → update existing item; else create new).
20. **Re-running ingestion idempotency.** If the same transcript is ingested twice, does the Reconciler create duplicate items? `meetings.source_file_hash` is UNIQUE so the *meeting* is idempotent; what about the items downstream? **BLOCKS-1E**.
21. **Flag-promotion rule unspecified.** When does a not-yet-slipped item move from Open → Flags? **DECIDE-LATER** (likely Week 5).

### Cross-system

22. **Subject ↔ job_id routing for office meetings.** Related to gap 18 — but specifically, should `meetings.job_id` be required and singular, or should the meetings table support multi-job sessions (array, or separate meeting_jobs join table)? Section 5c implies singular. **DECIDE-LATER** — singular is fine for now if the Reconciler routes via `subject`.
23. **`stop_reason` handling on the Extractor.** Adaptive thinking + json_schema can produce `stop_reason='refusal'` if the model balks. The extractor today raises a generic error. **DECIDE-LATER** — Gate 1E could share a brain-call helper that handles refusal cleanly.
24. **Token cost ceiling per gate.** Gate 1D.5 used $1.28 to extract 5 transcripts. The Reconciler will likely use 2–3× more tokens (it has to read items, claims, pay_app_line_items, daily_logs and reason about them). **DECIDE-LATER** — set a per-meeting budget in Gate 1E.

---

## 5. Closing observations

- The plan's schema is **roughly the right shape** for this claim. Every required field has somewhere to land. The ambiguities are at the edges: ID format, type mapping, derivation rules for the soft fields (priority, confidence), and date extraction policy.
- The most concrete-blocking gap for Gate 1E is **#1 (claims aren't ingested yet)**. Everything else is solvable inside the Reconciler's design phase.
- The **DB Welding case worked clean from end to end** — the sub catalog had the right alias, the pay app had a single sensible line-item match, the date was explicit, the speaker was identified. This is the *best* shape of claim. Gate 1E should be tested against *worse-shaped* claims too: claims with vague dates, claims with sub names that don't match anything in the catalog, claims that cross multiple line items, and claims that contradict prior commitments.
- The **clobber-prevention gap (#13)** is the one I'd flag hardest. v1 had this exact bug, fixed it on May 14, and the v2 schema as written doesn't carry the fix forward. Easy to add a column to migration 004, hard to fix retroactively.
