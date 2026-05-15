# Ross Built Production Intelligence — v2 Plan

**Status:** Draft for Jake to mark up. Not final.
**Date:** May 14, 2026

---

## 1. The system in one page

**What it is:** A single intelligent system that ingests every form of information about an active Ross Built job — meeting transcripts, daily logs, pay app line items, eventually emails and selections — and produces one trustworthy document per job. That document is the basis for Monday meetings, the source of truth between meetings, and the historical record after the job closes.

**What it does:**
- Cross-checks every claim against multiple sources before treating it as fact
- Surfaces accountability — who owes what, when, and whether they delivered
- Tracks sub performance by trade and phase across all jobs over time
- Replaces the current weekly meeting chaos with a structured operating document everyone works off of
- Builds institutional memory automatically — every meeting feeds back

**What it explicitly does NOT do (in v1):**
- Punchlist photos as a structured feature (deferred to v1.1)
- Real-time mid-meeting collaboration with multiple cursors (deferred)
- Email/SMS ingestion (Phase 2)
- Spontaneous Plaud transcripts beyond formal meetings (Phase 2)
- Schedule forecasting / look-ahead Gantt (explicitly not the goal per your input)
- Buildertrend write-back (read-only from BT, ever)

**The core insight that drove this design:** The pay app line items are the master to-do list for every job. They're already structured, already budgeted, already tracked by % complete. Everything else — transcripts, daily logs, action items — *attaches* to pay app line items. This is the unlock the v1 architecture missed completely.

---

## 2. The four data sources and how they cross-validate

The system has four inputs. None of them alone is trustworthy. Together they triangulate truth.

### 2a. Meeting transcripts (Plaud)
- **What they're good at:** Capturing intent, decisions, commitments, observations, client/sub psychology
- **What they're bad at:** Accuracy (50%+ noise per the transcripts you sent), names, dates, technical specs
- **Frequency:** Weekly per job + spontaneous (Phase 2)
- **Truth weight:** Low when alone. High when corroborated.

### 2b. Buildertrend daily logs
- **What they're good at:** Ground truth on who was on site, what they did, photos of conditions, weather
- **What they're bad at:** Don't capture decisions, intent, or sub commitments. PM-dependent quality.
- **Frequency:** Daily per job
- **Truth weight:** High for "did X happen" questions. Zero for "what should happen next."

### 2c. Pay app line items (G703)
- **What they're good at:** The structured ~220-item master list of everything that must get done, with budget and % complete
- **What they're bad at:** Updated monthly, not daily. Doesn't tell you who's responsible day-to-day.
- **Frequency:** Monthly per job
- **Truth weight:** High for "how complete is the job." Authoritative for scope.

### 2d. (Phase 2) Emails, SMS, additional Plaud captures
- Deferred. Mentioned for completeness. The system architecture leaves room for these without rework.

### How they cross-validate — the Reconciler logic

When a new transcript comes in, every claim it produces gets scored against the other sources:

| Claim type | Cross-check | Confidence rules |
|---|---|---|
| "Sub X completed task Y" | Daily logs for that week + pay app line item % movement | All three agree → auto-mark complete. Two agree → mark complete, flag for review. One only → leave open, flag. |
| "Sub X committed to date Y" | Compare to prior commitments for same sub on same task | If sub has slipped 2+ times → flag as drift. If new → add to commitments table. |
| "Decision made about Z" | No external corroboration possible → trust transcript | Always recorded. Surfaced as a decision, not a todo. |
| "Item X is open / pending" | Cross-check against pay app % complete + daily logs | If pay app shows item closed → contradiction → flag. |
| "PM observed condition Q" | Daily log photos for same day | Photos referenced if available. Otherwise stand alone. |

**The Reconciler's job is not to be right. It's to be honest about confidence.** Every output item carries a confidence label and a source citation. You see the same surface for high-confidence and low-confidence items, but you can tell them apart at a glance.

---

## 3. The brain — three LLM calls, one job each

### Call 1: Extractor
**Input:** Raw transcript + meeting metadata (PM, job, date, site/office)
**Output:** A list of structured *claims*. No judgment. No reconciliation. Just structured statements.

Each claim has:
- speaker (Jake, the PM, Lee Ross, client, sub)
- claim_type (commitment, decision, condition_observed, status_update, question, complaint)
- subject (sub name, person, line item, scope area)
- statement (the actual content, paraphrased)
- timestamp_in_transcript
- raw_quote (the actual words)

This is the dumb-but-careful step. Its only job is to *not* lose information.

### Call 2: Reconciler
**Input:** The claims from Call 1 + the current state of this job (open items, prior commitments, recent daily logs, pay app % complete by line item)
**Output:** Reconciled updates — what's new, what changed, what got resolved, what contradicts something, what needs human review.

This is where the system gets smart. The Reconciler:
- Maps each claim to a pay app line item where possible (this is the backbone)
- Detects slipped commitments (sub said X by Tuesday, daily log shows nothing, transcript now says Friday)
- Detects redundant items (the v1 system's repeat-repeat-repeat problem ends here)
- Updates statuses based on cross-source agreement
- Flags contradictions for review rather than silently picking one

### Call 3: Auditor
**Input:** Call 2's output
**Output:** Either ✅ "this is internally consistent" or a list of issues for the Reconciler to fix.

Sanity check pass. Catches: double-counted items, items assigned to wrong PM, contradictions the Reconciler missed, scope creep (claims that reference work outside this job).

If the Auditor rejects, Call 2 runs again with the audit notes attached. Max 2 iterations. After that, surfaces as "needs Jake's review."

**Why three calls, not one big agent:** Each call is auditable on its own. If something goes wrong, you can read Call 1's output and see whether the problem was extraction, reconciliation, or audit. Single-call systems hide their failures.

---

## 4. The Monday meeting document

### One format for site and office

You said one format for both. The information is the same; only how you gather it differs. Here's the format:

**Top section — the Today block:**
- Date, job, PM, meeting type (site/office), attendees
- One-line "where we are" summary auto-generated from pay app % complete

**Middle — three lanes, in order of urgency:**

1. **Flags** (top, urgent only) — slipped commitments, sub drift, contradictions, things needing Jake's call. 0–5 items typically.
2. **This week** — committed actions with target dates this week. Each shows: action, owner, target date, source (transcript / pay app / log), confidence dot.
3. **Open** — everything else open on this job, sorted by oldest first (the squeaky wheels). Days-open count on the right.

**Bottom — captured-this-meeting:**
A working drafts area that fills up live during the meeting. New items, decisions, conditions noted. Goes through the Reconciler after upload to merge into the main document.

### How items get checked off

Three ways, all valid:
1. **In the meeting** — tap to check, the change is captured and goes through the next Reconciler run
2. **Between meetings** — same tap-to-check, immediate
3. **Auto-resolved by the brain** — if daily logs + pay app show an item is done, it gets marked done automatically with a note "auto-resolved [date] — confirmed by daily log and pay app"

When you check something manually, the system asks one question silently: "based on what?" It logs the basis. Not because you owe it justification, but so the Reconciler doesn't second-guess your check next week.

### Sorting and filtering

The same document, three views:
- **By job** (default during job-specific meetings)
- **By PM** (Bob's view across his three jobs)
- **Whole company** (Jake's Monday morning view — every flag, every job)

Filter chips: trade, sub, status, source, age. The defaults match the use case — by-job defaults to "open + this week", whole-company defaults to "flags + this week."

### What it looks like in the meeting

Projected on a screen in the office; on Jake's iPad on site. The PM has the same view on their phone. Everyone is literally looking at the same document. Items get checked, new ones get typed in (or dictated via Plaud and Reconciled after).

**The single biggest behavioral change:** Meetings stop with "anything else?" and the doc gets reviewed for completeness in the last 2 minutes — not Jake reading aloud "repeat, repeat, repeat" from a stale list.

---

## 5. The Supabase schema

Eight tables. No more than necessary.

### 5a. Core entities (mostly already exist)

**pms** — exists today. Add: phone, email, active jobs (computed).

**jobs** — exists today (per audit). Columns: id, name, address, pm_id, phase, status (green/amber/red), target_co_date, gp_pct, contract_amount, project_start, projected_completion. Add: pay_app_doc_id (link to current pay app file in storage).

**subs** — exists today. Add: trades (array, e.g. [Electrician, Lighting]), primary_contact, current_phase_avg_drift_days (computed).

### 5b. The pay app layer (NEW — the backbone)

**pay_app_line_items**
- id (uuid)
- job_id (FK to jobs)
- line_number (e.g. "01105")
- description (e.g. "Development and Permitting Services")
- division (e.g. "01 — General Requirements")
- original_estimate ($)
- contract_amount ($)
- total_to_date ($)
- pct_complete (0–1)
- balance_to_finish ($)
- as_of_date (last pay app application date)
- last_updated_at

One row per line item per job. Krauss has ~220. Five active jobs × 220 = ~1100 rows total. Refreshed when a new pay app is uploaded.

This table is the master to-do list. Everything else attaches here.

### 5c. Action / observation layer

**items**
- id (e.g. KRAU-001 — keeping the LLM-friendly id pattern)
- job_id (FK)
- pm_id (FK)
- pay_app_line_item_id (FK, nullable) ← attaches to a specific pay app item when possible
- type (action, decision, observation, flag, question)
- title (the action / decision / observation in one line)
- detail (longer description if needed)
- sub_id (FK, nullable) — who's responsible if a sub
- owner (text, nullable) — for non-sub owners ("Jake", "Bob/Jason", "Lee Ross")
- target_date (date, nullable)
- status (open, in_progress, complete, blocked, cancelled)
- priority (urgent, normal)
- confidence (high, medium, low) — set by Reconciler
- source_meeting_id (FK to meetings)
- source_daily_log_id (FK to daily_logs, nullable)
- created_at, completed_at, completed_by (user or "auto")
- completion_basis (text — "manual check", "daily log + pay app", "transcript inference")
- carryover_count (int) — how many meetings has this rolled over without movement?

**commitments**
- id
- sub_id (FK)
- job_id (FK)
- description (what they committed to)
- committed_date (when they said they'd do it)
- source_meeting_id (where the commitment came from)
- delivered (bool, nullable) — null until resolved
- delivered_date (nullable)
- slip_days (computed: delivered_date - committed_date)

This is a separate table from items because commitments are the unit of sub accountability. They might be a subset of items, but tracking them separately makes the sub scorecard a one-query job.

**decisions**
- id, job_id, meeting_id, description, decided_by, decision_date, supersedes_decision_id (nullable)

Decisions are first-class because today they evaporate. "We decided to go with Progressive Bug Screens" — that's a decision, not a todo, and it shouldn't get nagged about. But you need to find it later.

### 5d. The intelligence layer

**meetings**
- id, job_id, pm_id, date, type (site/office), attendees (array), transcript_file_path, raw_transcript_text, processed_at, reconciler_version

**claims** (the raw output of Call 1, kept for audit)
- id, meeting_id, speaker, claim_type, subject, statement, raw_quote, timestamp_in_transcript

We keep claims so you can always go back to "what did the brain see and how did it interpret it" — debug-ability.

**daily_logs**
- id, job_id, log_date, pm_id, notes_text, activity_summary, crews_on_site (array), workforce_count, parent_group_activity (array), inspections, deliveries, photo_urls (array)

Scraped from Buildertrend. Photo URLs are stored but photos themselves stay in BT — we don't host them.

### 5e. Trade phase reference data (small but important)

**trade_phases**
- id, trade, phase, typical_duration_days, sequence_order

Seeded with your trades and phases. Used by the sub scorecard to compute show-rate and avg-days-per-phase. Static reference data, ~50 rows total.

**sub_events**
- id, sub_id, job_id, trade_phase_id, event_type (committed, scheduled, showed_up, completed, no_show, dragged)
- event_date, source (daily_log, transcript, manual)
- notes

Append-only event log. The sub scorecard derives all its numbers from this table.

---

## 6. The schedule + sub tracking model

This is the part you wanted simpler. Here's the simple model:

### Trades you have (my draft — correct me)
- Excavation / Site Work
- Foundation / Concrete
- Masonry (CMU block)
- Framing / Carpentry
- Roofing
- Plumbing
- Electrical
- HVAC
- Insulation
- Drywall
- Stucco / Plaster
- Interior Trim / Millwork
- Cabinetry
- Tile / Stone
- Wood Flooring
- Paint
- Pool / Hardscape
- Landscape / Irrigation
- Glass / Windows / Doors
- Garage Doors
- Low Voltage / AV / Security
- Appliances
- Specialty (railings, metal fab, etc.)

### Phases per trade (my draft for top trades — correct me)

| Trade | Phases |
|---|---|
| Electrical | Under-slab, Rough-in, Trim-out, Punch |
| Plumbing | Under-slab, Rough-in, Trim-out, Punch |
| HVAC | Rough-in, Equipment set, Trim-out, Punch |
| Framing | Wall frame, Roof frame, Sheathing, Punch |
| Stucco | Wire/lath, Scratch, Brown, Finish, Patch |
| Tile | Prep, Set, Grout, Punch |
| Drywall | Hang, Tape/finish, Texture, Punch |
| Paint | Prime, Body, Trim, Punch |
| Cabinetry | Install, Adjust, Trim/touch-up |

For trades not yet phased: default single-phase ("Performed"). Refine as needed when you see real data.

### What gets tracked per sub × phase × job

Pulled from sub_events:
- **Committed-to-date** — when sub said they'd be there
- **Actual start** — first daily log showing them on site
- **Actual end** — daily log + pay app % shows the phase done
- **Show rate** — % of committed slots where they showed up within 1 day of commitment
- **Avg duration** — actual_end - actual_start, by phase
- **Drift** — actual_start - committed_date, averaged

Sub scorecard surfaces this. Each sub has a profile page with by-phase breakdown.

---

## 7. Build sequence — six weeks to launch

### Week 1: Foundation
**Goal:** Schema, ingestion plumbing, pay app parser. No UI yet.
- Migrate Supabase to the v2 schema (additive — keep v1 todos table alive for now)
- Build the pay app parser (G703 → pay_app_line_items)
- Backfill: parse pay apps for all 5 active jobs
- Seed trade_phases reference table
- Smoke test: can I query "what % complete is Krauss" and get the right answer
- **Gate to Week 2:** All 5 jobs have parsed pay app data in Supabase. Numbers match the actual pay apps.

### Week 2: The brain (Reconciler)
**Goal:** Three-call pipeline producing reconciled output for one job from one transcript.
- Build Call 1 (Extractor) — prompt + parser
- Build Call 2 (Reconciler) — prompt + cross-source logic
- Build Call 3 (Auditor) — prompt + retry logic
- Test on real transcripts (Krauss 5/07 has most action-item content)
- Compare outputs to what the v1 system would have produced. Visibly better, or stop and fix.
- **Gate to Week 3:** Reconciler output for 5 transcripts. ≥4 of 5 visibly better than v1. If not, prompt engineering week starts.

### Week 3: Daily log scraper + cross-source intelligence
**Goal:** Daily logs flow into Supabase. Reconciler starts using them.
- Buildertrend scraper for daily logs (you have a starting point already)
- daily_logs table populated for last 30 days, all 5 jobs
- Reconciler updated to cross-check transcript claims against daily logs
- Sub_events derived from daily logs
- **Gate to Week 4:** Sub scorecard query returns sensible numbers for top 5 most-used subs.

### Week 4: The Monday document — surface
**Goal:** The actual interactive document. Built against real reconciled data.
- Next.js app (extending the existing cockpit or new project, your call)
- Three views: by-job, by-PM, whole-company
- Check-off interaction with completion_basis capture
- Working-drafts section for live capture
- Mobile-first, desktop-responsive
- **Gate to Week 5:** You can sit at your kitchen table, pull up the Krauss document, and feel like it's ready for a meeting.

### Week 5: Sub profiles + flags
**Goal:** Sub scorecard pages, flag generation, the intelligence surfaces.
- /subs catalog page
- /sub/[id] profile page (matches the mock you've already seen)
- Flag generation logic (slipped commitments, sub drift, contradictions)
- Decisions page per job
- **Gate to Week 6:** Browse 3 sub profiles. Numbers make sense. Flags surface things you'd actually want to know.

### Week 6: Polish + launch prep
**Goal:** Production-ready. All 5 PMs onboarded simultaneously.
- Auth gate (Vercel password protect at minimum)
- Onboarding doc for PMs (one page)
- Final transcript through the system to confirm end-to-end works
- Decide: kill v1 cockpit, or run both for a transition week
- **Gate to launch:** You've personally used the system for 3 days. Confident PMs won't be confused.

### What's not in the 6 weeks
- Punchlist photos (Phase 1.1, ~1 week)
- Email/SMS ingestion (Phase 2)
- Buildertrend selection scraping (Phase 2)
- Forecasting / look-ahead schedules (explicitly not goal)

---

## 8. Open questions

Locked answers (per chat through Gate 1C):
- Q1: Extend existing cockpit Next.js app, same Supabase
- Q3: Martin stays on Fish, no transition modeling
- Q4: Punt RLS to Phase 2
- Q9: Buildertrend scraper exists but is broken (DNS) — fix in Week 3
- Q10: Decisions superseded, not deleted

Still open as of Gate 1C:
- Q2: Pay app upload mechanism → Upload UI in the cockpit (locked, but UI is a later gate)
- Q5: v1 cockpit during weeks 2–5 — UNDECIDED (A: hard freeze / B: critical fixes / C: sunset now)
- Q6/Q7: Trades and phases list — Jake to confirm in Week 3 prep
- Q8: Low-confidence routing → on the document with a flag (locked default)

---

## 9. What I'm uncertain about

**A. The pay-app-as-backbone idea is the load-bearing bet of this whole design.** Confirmed at Gate 1C — 5 jobs ingested cleanly, 651 line items, reconciliations balance to the cent. The bet is paying off.

**B. The three-call brain may need to be a four-call brain.** A "Linker" call between Extractor and Reconciler — whose only job is to map each claim to a pay app line item — might be cleaner than rolling it into the Reconciler. Won't know until we see Call 2 trying to do too much. Decide during Week 2.

**C. Sub identity is messier than my schema implies.** Subs table has 54 entries. Some are probably aliases of the same person. v1 has an alias system. v2 schema assumes it works. We may need to dedup mid-build.

**D. The "completion_basis" field on items is doing a lot of work.** It needs to be granular enough to be useful but not so granular that PMs avoid checking things off.

**E. Six weeks is aggressive.** With 20+ hours/week and Claude Code executing well, doable. First unexpected thing will eat the buffer. Mentally pad to 7–8 weeks.

**F. PCCO change order rollups not yet ingested.** Logged in v1-known-issues.md. ~$1.77M across 5 jobs sits in the gap between header totals and line-item sums. Address when financial views need full reconciliation.

---

## 10. What happens after sign-off

1. Mark up disagreements, send back
2. Revise, converge
3. Write each week's Claude Code prompts as we go (one gate at a time, 4 gates per week ish)
4. Execute, gate-check, proceed
