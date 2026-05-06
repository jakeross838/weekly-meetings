# Ross Built PM Weekly — Transcript → Binder Prompt

**Use this every Monday/Tuesday after each PM meeting.**

---

## Inputs — paste these, in this order, when prompting Claude

1. **This prompt** (top of message)
2. **PRIOR BINDER JSON** — exported from the HTML binder before the meeting. Contains every OPEN / IN PROGRESS / BLOCKED item from prior weeks with their opened-dates and current status.
3. **TRANSCRIPT** — raw Plaud output from this week's meeting
4. **META** — one line:
   ```
   PM: <name> | Date: YYYY-MM-DD | Type: SITE|OFFICE | Last-ID: <highest ID number used, e.g. MARK-047>
   ```

---

## Claude's job

Output the **updated full binder JSON** matching the exact schema of the input. Replace nothing silently; account for every prior open item. Extract every new action item from the transcript. Use the Ross Built meeting playbook as the structural guide.

---

## Rules — non-negotiable

### 0. Dedup before extraction (Phase 12 polish)

Before creating a new item, scan the existing open items in this PM's binder (the PRIOR BINDER JSON in your inputs).

**If a new item references the same person + same deliverable + same job as an existing open item, MERGE it with the existing item by adding context to the `update` field rather than creating a duplicate.**

- Different aspects of the same task = same item with notes appended.
- Same person doing two genuinely different things = two items.
- A "follow-up" or "next step" on the same deliverable = update on the existing item, not a new item.

Example merges (do these):
- Existing FISH-028 says "Martin to call Tom at D&D / Banko Overhead Doors directly by Thu 4/30..." and the transcript adds "Tom hasn't responded — Martin to escalate to D&D principal" → update FISH-028's `update` field with the escalation note. Do NOT create FISH-049.
- Existing FISH-012 says "Martin to run pond fill test off well pump 4/29" and the transcript mentions "pond test scheduled for 4/29 with photos to Alex" → update FISH-012. Do NOT create FISH-036.

Example NOT-a-merge (these are two items):
- Existing FISH-001 ("Courtney outstanding-selections email follow-up") + FISH-002 ("Farrow & Ball Mahogany interior door color") — same person, same job, but two different deliverables. Two items.
- "Martin to relocate well pump 20ft back" + "Martin to run pond fill test off well pump" — same area, but relocation vs testing are different tasks. Two items.

When in doubt, prefer ADDING context to an existing item over creating a new one. Duplicate items waste meeting time.

### 1. Action item quality

Every action item must pass the **Monday Morning Test**: the owner reads it at 7am Monday and knows exactly what to do without asking a question.

- Specific person (not "the team")
- Specific verb + deliverable (not "follow up" / "discuss" / "check on" / "look into")
- Hard due date (not "ASAP" / "next week")

**If the transcript produces a vague item, rewrite it. If it can't be rewritten, add to a `clarify` array with the raw quote and Jake will clean it up before distribution.**

Examples:

| Transcript (vague) | Output (specific) |
|---|---|
| "Need to follow up with Jerry on paint" | "Martin to request comparable interior paint bid from Myers by Mon 4/28; attach side-by-side to Jerry's $25K quote." |
| "Check in with Gilkey" | "Lee to call Laura at Gilkey by Wed EOD. Request hardscape plan by Fri 4/26. Escalate to principal if no response." |
| "We should probably do something about the stairs" | **Flag to `clarify` — not specific enough.** |

### 2. Priority — auto-assign

| Priority | Trigger (any one) |
|---|---|
| **URGENT** | Due ≤3 days · Aging >14 days · Blocks critical path · Financial exposure · Client trust signal |
| **HIGH** | Due ≤7 days · Aging 8–14 days · Sub coordination · Selection deadline |
| **NORMAL** | Everything else |

### 3. Carry-forward — every prior open item must be accounted for

For each item in the prior binder with status NOT_STARTED / IN_PROGRESS / BLOCKED (post-migration) or OPEN / IN PROGRESS / BLOCKED (pre-migration):

- **If transcript confirms done:** status → COMPLETE, add note to `update` field with evidence
- **If transcript confirms progress but not done:** status → IN_PROGRESS, update `update` field with new status line
- **If transcript confirms external blocker:** status → BLOCKED, update `update` field with what's blocking
- **If transcript mentions item was decided obsolete:** status → COMPLETE with update prefix "Complete — [reason]" ("Scope change — removed from contract" / "Client reversed decision" / etc.)
- **If transcript doesn't mention it at all:** status unchanged, increment age silently, add `update: "Not discussed this meeting. Rolls over."` — but only if age <21 days. At 21+ days, add to `clarify` for Jake to address.

**Never silently drop items.**

### 4. ID scheme

New items: `<JOB-PREFIX>-<###>` where:
- Job prefix = first 4 letters of job name uppercase (MARK, FISH, POU_, RUTH, HARL, CLAR, etc.). For 3-letter names pad with underscore.
- Number = next sequential within that job's prefix, zero-padded to 3 digits.
- If META specifies Last-ID = FISH-010, next Fish item is FISH-011.

### 5. Lookaheads — structured, not narrative

For the 2-week, 4-week, 8-week lookaheads, extract only items that are **explicitly scheduled or named** in the transcript. Each lookahead entry: `{ job: "<name>", text: "<activity + date/status>" }`.

- 2-week: things happening within 14 days, with confirmation status visible
- 4-week: sequencing/coordination items 15-28 days out
- 8-week: long-lead procurement, selections gates, material orders 29-56 days out

**Do not fabricate.** If the transcript doesn't discuss a 4-week lookahead, leave `w4: []` empty — Jake/PM will fill it in during the meeting using the printed sheet.

### 6. Issues — typed, specific, sub-named, **job-tagged**

Types: `Sub` | `Client` | `Design` | `Site` | `Sequencing` | `Selection`

- **Always set `job`** to the job the issue concerns (one of the PM's jobs). Issues that genuinely span all the PM's jobs are rare — prefer a specific job over "General."
- Always name the sub, client member, or designer explicitly.
- Chronic issues that have persisted for multiple weeks: prepend "[CHRONIC]" to the text.

### 7. Financial — only what's stated, **job-tagged**

Extract:
- Dollar figures mentioned in context
- CO amounts / pay app numbers / allowance burn
- Budget overruns discussed

**Always set `job`** on each financial entry. Skip: speculation, vague "getting expensive" mentions without numbers.

### 8. Do not fabricate

When in doubt: leave empty, flag to `clarify`, or reduce detail. A blank section is better than an invented one. The PM will fill gaps with the printed copy during the week.

---

## Daily log reconciliation rules

When DAILY LOG CONTEXT is provided, use it as independent evidence of what happened on site. Rules:

1. Contradiction flagging: If transcript claims a sub was present/absent on a specific day and the log shows otherwise, add to clarify array with both statements and the log date.
2. Status auto-transition: If an action item in the prior binder is NOT_STARTED and the daily logs show that activity occurred, transition to IN_PROGRESS and cite the evidence in the update field.
3. Gap surfacing: If a sub was expected (per prior action item or look-ahead) and logs show zero days of attendance in the window, create a new URGENT action item.
4. Silent activity surfacing: Every entry in daily_logs.summary.notable_activities that wasn't mentioned in the transcript MUST be surfaced as a silent_activity reconciliation entry. Quote the notable activity text verbatim.
5. Citation format: Use "[BT log YYYY-MM-DD]" in the update or notes field when referencing logs.
6. Staleness caveat: If logs are marked stale (>48h old), treat as indicative only.
7. No contradiction does not mean agreement: Flag contradictions only when logs ACTIVELY show something different.
8. Absent-crew pattern detection: If a sub appears in absent_crew_frequency with 2+ absent days, create new URGENT action item of type FOLLOWUP: "Follow up with [crew] on attendance — [N] days absent in last 14 days."
9. Trade-stall detection: Cross-reference activity_tag_frequency against prior binder items. If a tag appears 8+ days in window but the related action item is still NOT_STARTED, auto-transition to IN_PROGRESS with citation.
10. Low-workforce flag: Any day with workforce < 3 on an active job = note in issues: "Low workforce day [DATE] — [N] on site."
11. Scope drift: If a crew in crews_clean appears 3+ days but isn't in any prior binder action item AND isn't in active PO/CO tracked, flag as clarify.
12. Inspection/delivery reconciliation: Cross-check every inspection_events and delivery_events entry against action items. Passed inspection may auto-complete or unblock items.
13. Cross-job contamination: If the transcript indicates an item was placed under the wrong PM/job ("that's a different job", "cross that off", "that shouldn't be here"), set its status to DISMISSED with update explaining the mix-up. Do NOT use COMPLETE for this — dismissed ≠ done.

---

## Last-week look-behind (lookBehind)

Generate a lookBehind object capturing the last 14 days (two weeks) of ground truth per job.

Structure:
```json
"lookBehind": {
  "week_of": "YYYY-MM-DD to YYYY-MM-DD",
  "per_job": {
    "<job>": {
      "workforce": {
        "avg": float_1dp,
        "peak": int,
        "low": int,
        "inferred_target_range": "[X-Y]",
        "variance_note": "description"
      },
      "days_on_site": int,
      "top_activities": ["<tag> (<n> days)", ...],
      "top_crews": ["<crew> (<n>d)", ...],
      "inspections_passed": int,
      "deliveries": int,
      "notable_events": ["<verbatim text with date>", ...],
      "missed_subs": ["<crew> (<n>d absent)", ...],
      "ppc_narrative": "1-2 sentences referencing specific crews/activities",
      "completion_vs_plan": "<approximate % or qualitative>"
    }
  }
}
```

Rules:
- 14-day window ending meeting_date - 1 (two full weeks of ground truth, not one)
- Infer workforce targets from job phase:
  - Site prep / foundation / excavation: 3-6 avg
  - Framing / rough-ins: 5-10 avg
  - Drywall / interior trim / early finish: 6-12 avg
  - Late finish / punch / closeout: 3-8 avg
  - Warranty / maintenance: 0-3 avg
  Mark as "inferred", not authoritative.
- ppc_narrative references specific evidence.
- If no logs in window: `{ "status": "no activity logged", "days_on_site": 0 }`.

---

## Action item taxonomy

Every action item has these required fields:

**type** — one of exactly:
- SELECTION — waiting on client/designer to pick something (color, finish, product)
- CONFIRMATION — need written verification of info from someone
- PRICING — get quote, compare bids, estimate a scope
- SCHEDULE — coordinate sub timing, sequence work, book a date
- CO_INVOICE — issue/process CO, bill, payment, credit
- FIELD — physical site work, coordination, inspection, walk-through
- FOLLOWUP — chase sub/client/vendor for a response

Pick the MOST specific type. Never "GENERAL" or "OTHER". If genuinely unclear, default to FOLLOWUP.

**category** — one of exactly the following 8 values (Phase 12 Part B — drives meeting-prep section grouping):

- **SCHEDULE** — sub start dates, schedule confirmations, duration, sequencing, schedule moves. The most common bucket for "confirm X by Y date" items.
- **PROCUREMENT** — material orders, deliveries, lead times, PO creation, **sub buyouts** (buyouts go here, NOT in SUB-TRADE).
- **SUB-TRADE** — sub *performance* concerns: hire/fire decisions, credits, scope disputes, chronic non-performance escalation. NOT scheduling-style sub items (those are SCHEDULE).
- **CLIENT** — homeowner decisions, client communication, walkthroughs, owner approvals/CO sign-off, client sentiment.
- **QUALITY** — field defects, rework, punch items, dust control, workmanship issues, hold-point fails.
- **BUDGET** — cost estimates, budget variances, change orders to process, GP exposure, pay app status, pricing/quote work.
- **ADMIN** — permits, inspections (passing — failing inspections are QUALITY), insurance/COI, internal process, company events, holiday schedules.
- **SELECTION** — finish selections, design decisions, material choices, designer items, swatches/samples.

Pick the MOST specific category. Default to ADMIN only when nothing else fits — ADMIN should be rare. Buyouts go in PROCUREMENT, NOT SUB-TRADE.

**source** — one of exactly:
- `transcript` — captured from a meeting transcript (this is the default for items extracted by this prompt)
- `system_predicted` — auto-generated by the system (e.g., from the 2-week look-ahead computation). The LLM never assigns this; it's only set programmatically.
- `manual` — entered by hand outside the meeting flow.

For new items extracted from a transcript, always emit `source: "transcript"`.

**status** — one of exactly:
- NOT_STARTED — not begun. Owner hasn't touched it.
- IN_PROGRESS — owner has begun (email sent, quote requested, sub called, measurement taken).
- BLOCKED — cannot proceed without external input. Waiting on someone specific.
- COMPLETE — done.
- DISMISSED — erroneously created or belongs to a different PM/job. Use when the PM says "that's a different job", "cross that off", "that shouldn't be here", or equivalent. Note the reason in `update`.

If KILLED in prior binder, migrate to COMPLETE with update: "Complete — [original kill reason]."
If OPEN in prior binder, migrate to NOT_STARTED.
If DONE in prior binder, migrate to COMPLETE.

**priority** — URGENT / HIGH / NORMAL (unchanged).

**action** — must start with owner name, use specific verb, name specific deliverable, include hard due date. Never "Discuss", "Review", "Follow up", "Check on", "Look into", "ASAP".

**due** — YYYY-MM-DD format. Must be a specific date, never "next week" or "TBD".

**update** — 1-2 sentences max. Reference specific BT log dates when available.

**close_date** — YYYY-MM-DD format. **Required when status=COMPLETE or DISMISSED.** Omit otherwise. Rules:
- If the transcript explicitly states a close date ("done Tuesday", "completed 4/26"), use that.
- If the item just transitions to COMPLETE/DISMISSED without an explicit date, use the transcript meeting date (the META Date field).
- If `close_date` is already set on a prior item AND the item stays COMPLETE, preserve the existing close_date — do not rewrite it to today's meeting date.

---

## Heads Up watchlist

Generate a `headsUp` object in output JSON that synthesizes risk signals for the week ahead. This is **proactive intelligence, not reflection** — the PM walks through this during the meeting so they know what to watch over the coming 7 days.

Place the `headsUp` object in the output JSON **after `lookBehind` and before `lookAhead`**.

Structure:

```json
"headsUp": {
  "aging_into_stale": [
    {"item_id": "FISH-001", "current_age_days": 12, "due": "2026-04-28", "why_it_matters": "Client trust risk if not addressed"}
  ],
  "subs_to_watch": [
    {"crew": "Tom Sanger Pool", "concern": "absent entire 14-day window despite scheduled work", "action_needed": "Hard commit on chip-down schedule before Nemesio tiles"}
  ],
  "sequencing_risks": [
    {"risk": "Plaster duration undefined", "downstream_impact": "blocks tile layout, blocks wood floor install", "mitigating_action": "FISH-003 due 4/27"}
  ],
  "selections_due_this_week": [
    {"item_id": "FISH-014", "selection": "Door hardware finish", "due": "2026-04-25", "cost_of_wrong_choice": "Major rework if white bronze ordered instead of dark"}
  ],
  "client_trust_signals": [
    {"concern": "3 CO items aging, banquette CO (FISH-004) unsent 14+ days", "action": "Issue all pending COs this week to reset trust"}
  ],
  "exterior_work_flags": []
}
```

### Rules per category

- **aging_into_stale** — items whose `days_open` will hit 14 within the next 7 days. Pull from binder items where `7 <= days_open < 14`. Field: `why_it_matters` = 1-sentence reason the aging matters now, not a generic flag.
- **subs_to_watch** — crews with absence patterns (from `absent_crew_frequency`), chronic issues (from `[CHRONIC]`-marked issues), scope drift flags. Name the sub. State a concrete concern + the next action needed.
- **sequencing_risks** — items where one OPEN blocker cascades to multiple downstream items. Usually **1-3 highest-risk chains**. Show the chain (what blocks what) and a mitigating action.
- **selections_due_this_week** — `SELECTION` type items with due dates in the next 5 days. Include `cost_of_wrong_choice` to surface the stakes.
- **client_trust_signals** — `CO_INVOICE` items aging, unresolved client requests, communication gaps. **Max 2-3 items** — keep this list tight so the actionable signals stand out.
- **exterior_work_flags** — empty array for now. Reserved for future weather integration.

### Quality bar

Each entry must be **concrete and actionable**, not generic.

- Bad: "Sub X might not show up"
- Good: "Sub X absent 4 of 14 days, blocks tile start — confirm attendance by Mon"

### Fabrication rule

If no risks in a category, use an empty array. **Do not fabricate risks.** A short list of real concerns beats a padded list with manufactured ones.

### Job tagging

Every `aging_into_stale`, `subs_to_watch`, `sequencing_risks`, `selections_due_this_week`, and `client_trust_signals` entry must carry an explicit `job` field (one of the PM's jobs). This lets the binder render per-job Heads Up blocks so risks don't intermix across jobs. If a risk genuinely spans all of a PM's jobs (rare — usually a workflow/admin observation), put it in `generalNotes` instead.

---

## General notes (`generalNotes`)

A flat array for **cross-job or non-job-specific observations** raised in the meeting. Examples:
- Workflow / process ideas ("we should start requiring written plaster duration on all jobs")
- Admin / scheduling ("Martin out 4/29-4/30")
- PM-level concerns not tied to any one job ("need to re-evaluate our sub-performance tracking")
- Cross-cutting reminders ("remember the merge-freeze next week")

Keep entries short, one sentence or bullet-length. `context` is an optional tag like `workflow`, `admin`, `process`, `observation`. If unclear, omit `context` and just write the note in `text`.

**What NOT to put in generalNotes:** job-specific action items (those are `items[]`), typed issues about a sub/client (those are `issues[]`), dollar figures (those are `financial[]`). Use generalNotes only for the cross-cutting residue.

---

## Output schema — match exactly

```json
{
  "meta": {
    "pm": "<name>",
    "date": "YYYY-MM-DD",
    "type": "SITE|OFFICE",
    "week": <int>
  },
  "jobs": [
    { "name": "<job>", "phase": "<phase>", "status": "green|amber|red", "targetCO": "YYYY-MM-DD|—", "gp": "<val>|—", "address": "<addr>" }
  ],
  "lookAhead": {
    "w2": [ { "job": "<name>", "text": "<activity>" } ],
    "w4": [ { "job": "<name>", "text": "<activity>" } ],
    "w8": [ { "job": "<name>", "text": "<activity>" } ]
  },
  "lookBehind": {
    "week_of": "YYYY-MM-DD to YYYY-MM-DD",
    "per_job": {
      "<job>": {
        "workforce": { "avg": 0.0, "peak": 0, "low": 0, "inferred_target_range": "[X-Y]", "variance_note": "<description>" },
        "days_on_site": 0,
        "top_activities": ["<tag> (<n> days)"],
        "top_crews": ["<crew> (<n>d)"],
        "inspections_passed": 0,
        "deliveries": 0,
        "notable_events": ["<verbatim text with date>"],
        "missed_subs": ["<crew> (<n>d absent)"],
        "ppc_narrative": "<1-2 sentences referencing specific crews/activities>",
        "completion_vs_plan": "<approximate % or qualitative>"
      }
    }
  },
  "headsUp": {
    "aging_into_stale":          [ { "job": "<job name>", "item_id": "PREFIX-###", "current_age_days": 0, "due": "YYYY-MM-DD", "why_it_matters": "<1-sentence>" } ],
    "subs_to_watch":             [ { "job": "<job name>", "crew": "<name>", "concern": "<specific>", "action_needed": "<specific>" } ],
    "sequencing_risks":          [ { "job": "<job name>", "risk": "<specific>", "downstream_impact": "<what gets blocked>", "mitigating_action": "<specific>" } ],
    "selections_due_this_week":  [ { "job": "<job name>", "item_id": "PREFIX-###", "selection": "<what>", "due": "YYYY-MM-DD", "cost_of_wrong_choice": "<specific>" } ],
    "client_trust_signals":      [ { "job": "<job name>", "concern": "<specific>", "action": "<specific>" } ],
    "exterior_work_flags":       []
  },
  "generalNotes": [
    { "context": "<optional tag: workflow|admin|process|observation>", "text": "<cross-job observation or non-job-specific note>" }
  ],
  "items": [
    {
      "id": "PREFIX-###",
      "job": "<name>",
      "type": "SELECTION|CONFIRMATION|PRICING|SCHEDULE|CO_INVOICE|FIELD|FOLLOWUP",
      "category": "SCHEDULE|PROCUREMENT|SUB-TRADE|CLIENT|QUALITY|BUDGET|ADMIN|SELECTION",
      "source": "transcript",
      "action": "<verb phrase w/ owner + deliverable + due>",
      "owner": "<person>",
      "opened": "YYYY-MM-DD",
      "due": "YYYY-MM-DD",
      "status": "NOT_STARTED|IN_PROGRESS|BLOCKED|COMPLETE|DISMISSED",
      "priority": "URGENT|HIGH|NORMAL",
      "update": "<what changed since prior binder>",
      "close_date": "YYYY-MM-DD"
    }
  ],
  "issues": [
    { "job": "<job name>", "type": "Sub|Client|Design|Site|Sequencing|Selection", "text": "<specific>" }
  ],
  "financial": [
    { "job": "<job name>", "text": "<specific dollar/scope item>" }
  ],
  "clarify": [
    { "raw_quote": "<verbatim from transcript>", "issue": "<why unclear>" }
  ],
  "reconciliation": [
    { "type": "contradiction|gap|silent_activity|auto_transition", "item_id": "<optional>", "text": "<specific observation with BT log date citation>", "log_date": "YYYY-MM-DD" }
  ]
}
```

---

## Output format

Output the JSON in a single fenced code block. Then a brief 3-line summary below it:

- **New this week:** <count>
- **Escalations (aging >14d):** <count>, list IDs
- **Top 3 Monday morning priorities for the PM:** <1-liner each>

That summary is what Jake scans. The JSON is what gets imported back into the HTML binder.

---

## Context Claude should use

- **PM → Job assignments** (current): Martin→Fish; Jason→Pou, Dewberry, Harllee (post-CO); Lee→Krauss, Ruthven; Bob→Drummond, Molinari, Biales; Nelson→Markgraf, Clark, Johnson.
- **Common sub names** (for accurate extraction): Seth (deck/pool carpentry), Myers Paint, Watts Stucco, Nemesio (mason), First Choice (cabinets), DB Fabrication (metal), Tom Sanger (pool), Metro Electric, Smart Home/Mark (LV - problematic), Fuse Appliance/Josh, Dwayne (laborer), WG Quality (drywall), Brock (painter), Real Woods (front door), Lonestar Electric, Jerry (Fish painter - problematic), Terry (TNT Custom Painting - overextended), Darryl (doors - bury-in-back pattern), Gilkey (landscape - bottleneck), Precision Stairs, Scott/Creative Trim, Rick/Easy Living LV, Dave/glass, Kuchin Ricci (Pou cabs), Integrity Floors, M&J Florida (siding - non-performing).
- **Canonical vendor / sub names — company name only** — when writing `action`, `update`, `issues.text`, `financial.text`, or `lookBehind.*.ppc_narrative`, use the COMPANY name (no "(Person)" trailer) whenever the daily logs or transcript make the company clear. Do NOT invent companies from thin air — if a first-name / short-form sub appears in the transcript and you don't have a confirmed company for them in the list below or in the current transcript's context, use the short form as-is. Jake will clarify ambiguous names in the meeting transcripts over time; **as new transcripts refine who works for which company, update this list and adopt the new canonical going forward.** Confirmed canonicals (from Buildertrend daily logs):
  - Oleg → **Volcano Stone, LLC**
  - Sanger / Tom Sanger (pool) → **Tom Sanger Pool and Spa**
  - Rangel (tile) → **Rangel Custom Tile**
  - Nemesio (mason) → **Nemesio Mason**
  - Rosa (cast stone) → **Rosa's Cast Stone**
  - Watts (plaster/stucco) → **Jeff Watts Plastering + Stucco**
  - Myers (paint) → **Myers Painting**
  - Faust (renovations) → **Faust Renovations**
  - Terry / TNT → **TNT Custom Painting**
  - Gilkey (landscape) → **Michael A. Gilkey, Inc.**
  - Parrish (well drilling) → **Parrish Well Drilling**
  - Rosser / Key Rosser → **Elizabeth Key Rosser**
  - HBS → **HBS Drywall**
  - Integrity → **Integrity Floors**
  - Sight to See / SMS → **Sight to See Construction**
  - Campbell → **Campbell Cabinetry**
  - Banko → **Banko Overhead Doors**
  - Cucine Ricci / Kuchin Ricci → **Cucine Ricci**
  - First Choice → **First Choice Custom Cabinets**
  - Fuse → **Fuse Specialty Appliances**
  - DB Welding / DB Fabrication (metal) → **DB Welding Inc.**
  - DB Improvements → **DB Improvement Services**
  - Real Woods (front door) → **Real Woods**
  - Metro Electric → **Metro Electric**
  - Lonestar Electric → **Lonestar Electric**
  - Precision Stairs → **Precision Stairs**

  For any short-form name NOT in this list (Jerry, Brock, Darryl, Seth, Dwayne, Dave, Mark, Josh, Scott, Rick, etc.), leave it as-is — using whatever the transcript says. Jake will flag the company name in future meetings and this list will grow from there.
- **Common clients**: Fish (715 N Shore), Krauss, Markgraf, Pou, Ruthven, Molinari, Drummond, Dewberry, Clark, Biales, Johnson, Harllee (delivered).
- **Plaud transcripts mis-hear:** "Plod" = Plaud, "Josh/Jason" often confused, "pew" = Pou, "Margrave/Margraf" = Markgraf, "Kraus/Krauss" interchangeable.

---

## Reminder

The playbook is the source of truth for meeting structure. This prompt's job is to **convert conversation into structured tracking output** — not to invent structure that wasn't in the meeting. Where the transcript is loose, the output is loose. Where it's specific, the output is specific.
