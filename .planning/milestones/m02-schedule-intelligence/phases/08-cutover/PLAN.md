# Phase 6.6 Wrap + Phase 8 Cutover (Phase 7 deferred to m03)

## 1. Schedule the Monday accountability validation run

Schedule an agent for next Monday morning (May 6, 2026) before 8am ET. Task:

```
1. Run: python monday-binder-v2/build_meeting_prep.py
2. Read: data/meeting-commitments.json
3. Compute and report:
   - Last week (2026-W18): N commitments captured
   - This week (2026-W19): N commitments captured
   - Closed (in last week, absent this week): count + list
   - Carried (in both weeks): count + list  
   - New (this week only): count + list
   - Stuck-3w+ flagged: count + list
4. Flag any near-misses where content_hash didn't match but text is 80%+ similar
   (these are likely the same commitment phrased differently — surface for review)
5. Do NOT open or modify the rendered PDFs
6. Output a single markdown report saved to data/accountability-week-2026-W19.md
7. Print "ACCOUNTABILITY VALIDATION COMPLETE — review report" and stop
```

If anything errors during the run, capture the traceback in the report and continue with whatever can be computed.

## 2. Eyeball the visual style before Monday

Before scheduled run fires, open one Nightwork-styled PDF in Acrobat (suggest Nelson's office packet — it's representative). Verify:
- Slate/stone/sand palette renders correctly (not just grayscale)
- Space Grotesk loads on headers (not falling back to Times)
- JetBrains Mono on data values (not falling back to Courier)
- No broken layout, no overflow on landscape

If anything's off, fix before Monday's run. Cheap to verify, expensive to discover at the meeting.

## 3. Skip Phase 7. Go straight to Phase 8 Cutover.

Phase 7 Schedule Builder as originally specced builds a generic baseline schedule from historical medians. That's the wrong foundation. Three things have shifted:

- Schedules need to be plan-aware (size, scope, specs)
- Logs need inference for missed days
- Existing BT schedules are placeholders, not ground truth

The right home for Schedule Builder is `m03-schedule-generation`, kicked off when plans land. Don't build it twice.

## Phase 8 — Cutover

Move v1 → archived, v2 → primary. Lock the milestone.

### Steps

1. **Archive v1**:
   - Rename current `monday-binder/` to `monday-binder-v1-archive/`
   - Add README in archive: "Replaced 2026-04-30 by monday-binder-v2/. Read-only, retained for reference."

2. **Promote v2**:
   - Rename `monday-binder-v2/` to `monday-binder/`
   - Update any internal links/scripts referencing v2 paths
   - Smoke test: build_meeting_prep.py runs from new path

3. **Update memory + project state**:
   - Note that `m02-schedule-intelligence` is shipped
   - Note that `m03-schedule-generation` is the next milestone, blocked on plan ingestion
   - List the deferred items from m02 that move to m03:
     - Generator 4 (stage-should-be-doing)
     - Generator 7 (schedule reality check)
     - Generators 5, 6 (transcript pattern, Markgraf-lesson triggers)
     - Schedule Builder (plan-aware version)
     - Log inference for missed days
     - Size-class baselines

4. **Lock the milestone**:
   - Write final SUMMARY.md in `.planning/milestones/m02-schedule-intelligence/`
   - List all phases shipped, key artifacts, known limits, deferred work

5. **Document the production cadence**:
   - Weekly: Monday agent runs build_meeting_prep.py before 8am
   - Manual: PMs review their packets, run their meetings, mark commitments
   - Weekly: Same agent diffs against prior week, surfaces stuck items

### Verification

1. v1 archived, v2 promoted, smoke test passes
2. SUMMARY.md written with full inventory
3. m03 milestone stub created with deferred items listed
4. Production cadence documented somewhere PMs can find

### Stop conditions

Phase 8 ships when v1 archived, v2 promoted, smoke test green, SUMMARY.md committed, m03 stub created.

Begin.
