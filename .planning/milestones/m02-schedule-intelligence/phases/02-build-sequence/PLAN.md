# Phase 2 — 15-Stage Build Sequence Integration · PLAN

## Goal
Apply the canonical 15-stage build sequence (currently lives implicitly in the Phase 1 keyword library) as an **explicit, queryable taxonomy** that downstream views read against. Every phase code binds to a stage, predecessors, successors, typical_subs, inspection metadata. Every per-job phase data point binds to that taxonomy.

This is the spine the rest of the rebuild stands on.

## Inputs
- `config/phase-keywords.yaml` — Phase 1 keyword library (~700 patterns, 84 phase codes)
- `data/derived-phases.json` — 5,547 classified log records from Phase 1 (high/tag_disambiguated/low_review/manual_review)
- `SPEC.md` PART 3 — canonical 15-stage build sequence definition
- 11 active jobs + completed jobs in the daily-logs corpus

## Method (7 steps)

### Step 1 — Build canonical phase taxonomy
Create `config/phase-taxonomy.yaml`. One entry per phase code with: `name`, `stage`, `stage_name`, `category`, `typical_subs`, `predecessors[]`, `successors[]`, `parallel_with[]`, `requires_inspection`, `inspection_name`, `notes`.

Cover every phase code in `config/phase-keywords.yaml`. Codes not in SPEC PART 3 (e.g., classifier-only catch-all codes) get explicit notation.

### Step 2 — Validate predecessor/successor graph
- Symmetry: every successor in entry X has X in its predecessors list
- No circular dependencies
- Roots: 1.1 Permits + 1.2 Site Clearing (no predecessors)
- Terminus: 15.6 Owner Move-In (no successors)

Print all inconsistencies. Don't proceed until graph is clean.

### Step 3 — Bind classified logs to taxonomy
Walk `data/derived-phases.json` and enrich each record with `stage`, `stage_name`, `category` from taxonomy lookup. Flag records whose `derived_phase_code` doesn't resolve to a taxonomy entry. Output to `data/derived-phases-v2.json`.

### Step 4 — Build per-job phase instances
For every (job × phase_code) combination, aggregate log records into a phase instance. Fields: `job_id`, `phase_code`, `phase_name`, `stage`, `stage_name`, `status`, `first_log_date`, `last_log_date`, `active_days`, `span_days`, `log_count`, `subs_involved[]`, `predecessors`, `successors`, `predecessors_complete`, `successors_started`.

Status values:
- `complete` — last log >14d ago AND ≥1 successor has logs
- `ongoing` — logs within last 14 days
- `not_started` — no logs (BT schedule integration deferred to later phase)

Save to `data/phase-instances.json`.

### Step 5 — Job stage detection
For every job, compute `current_stage` from most-advanced ongoing or recently-completed phase. Save to `data/job-stages.json` keyed by job short-name.

### Step 6 — Sequencing audit
For every active job, walk the build sequence and surface anomalies. Save to `data/sequencing-audit.md`. Examples of anomalies to surface:
- Phase X complete but successor Y has no logs
- Phase X ongoing while predecessor not yet logged
- Density anomalies (Phase 4 will formalize, but flag the obvious ones)
- Out-of-sequence work (e.g., 7.6 Stucco Finish ongoing while 7.4 Siding has no logs)

These deductions are the early signal of what the Phase 6 Insight Engine will formalize. Phase 2 surfaces them as a flat audit.

### Step 7 — Persist artifacts
- `config/phase-taxonomy.yaml`
- `data/derived-phases-v2.json`
- `data/phase-instances.json`
- `data/job-stages.json`
- `data/sequencing-audit.md`
- `phases/02-build-sequence/PLAN.md` — this file
- `phases/02-build-sequence/VERIFICATION.md` — QA artifacts

## Verification (paste-back required)

The following 7 items must be addressed in `VERIFICATION.md`:

1. **Taxonomy completeness** — every phase code in the keyword library resolves to a taxonomy entry. List orphans (codes in keyword library but not taxonomy).
2. **Dependency graph clean** — no circular dependencies, predecessor/successor symmetry verified, roots/terminus correct.
3. **Phase instance count** — total + by status + by stage. Should be roughly `(11 active jobs × ~60 reachable phases) - (not-yet-reached) = several hundred instances`.
4. **Markgraf full read-down** — paste Markgraf's job-stages entry + all phase instances in stage order. Verify CoatRite at 2.4 (not 3.1), floor trusses at 3.4 (not bundled into 3.7), 15.2 Punch Repairs ongoing.
5. **Clark sequencing** — paste Clark's sequencing audit. Should show Stage 2 active, 1.x complete, 2.1 ongoing, no anomalies.
6. **Fish sequencing audit** — paste it. Should surface Watts stucco density issue + any out-of-sequence work + any predecessor-not-complete-when-successor-scheduled conditions.
7. **Top 10 sequencing anomalies across all jobs** — ranked by severity. Early signal of what Insight Engine will formalize.

## Stop conditions
- Taxonomy covers every phase code from the keyword library
- Dependency graph validates clean (no unresolved cycles)
- Phase instances generated for all 11 active jobs
- Sequencing audit produces anomalies that match field reality (Watts density, Markgraf punch, etc.)
- All 7 verification items addressed

## Stop-and-ask triggers
- Unresolvable dependency cycles in the graph — flag with the cycle, don't paper over
- Phase codes in keyword library that have no logical place in the 15-stage sequence — flag rather than force-fit
- Sequencing anomalies that don't match Jake's field knowledge — paste in chat for confirmation before persisting

## Standing rules (unchanged)
- v1 stays running. Output to v2 paths only.
- Recalculate, don't increment.
- Org-configurable: taxonomy in YAML.
- Backward compatible.
- Print-legible labels.
