---
phase: 260714-owo
plan: 01
subsystem: testing
tags: [fixture, json, cp-sat, input-adapter, test-data]

# Dependency graph
requires: []
provides:
  - "data/sample_tiny_input_more_tm.json: throwaway fixture adding 12 qualified+rostered Team Members for task 99260066-B32A-423D-97A1-8A649BABBAAD"
affects: [manual API experimentation with POST /constraints and POST /scenarios/{id}/runs against set_min_workers_per_task]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fixture-variant-by-generator-script: build derived JSON test fixtures via a scratchpad Python script that deep-copies an existing row as a template, rather than hand-editing large JSON files"

key-files:
  created: [data/sample_tiny_input_more_tm.json]
  modified: []

key-decisions:
  - "Used Roster Profile (not Availability) for the 12 new members' windows — plan only required >=1 window type per input_adapter.py:122-123, and Roster Profile was simpler to generate as a single 3-day rolling block"
  - "Reused the exact Full Time / Grade 3 / EA2020-2023 template row (Rally Masula's shape) for all 12 new members to guarantee the (EBAID, GradeID) wage lookup resolves"

patterns-established: []

requirements-completed: [QT-260714-owo]

coverage:
  - id: D1
    description: "data/sample_tiny_input_more_tm.json exists, valid JSON, loads via input_adapter.load_problem without error, and preserves all original rows from sample_tiny_input.json unchanged"
    requirement: "QT-260714-owo"
    verification:
      - kind: other
        ref: "python inline script: table-set equality + untouched-table content equality + touched-table prefix equality (Task 1 verify)"
        status: pass
      - kind: integration
        ref: "python inline script: backend.ingest.input_adapter.load_problem('data/sample_tiny_input_more_tm.json') loads cleanly; qualified-member count for target task rises from 9 to 21 (+12)"
        status: pass
    human_judgment: false
  - id: D2
    description: "All 98 demanded hourly buckets for task 99260066-B32A-423D-97A1-8A649BABBAAD have >=3 (target >=4) qualified members with a covering window"
    requirement: "QT-260714-owo"
    verification:
      - kind: other
        ref: "python inline script: per-bucket coverage count over Roster Profile/Availability windows joined to Team Member Qualification and Performance rows (Task 2 verify)"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-07-14
status: complete
---

# Quick Task 260714-owo: New Data Fixture Variant with More Qualified Team Members Summary

**Added `data/sample_tiny_input_more_tm.json`, a superset of the source fixture with 12 new Full Time/Grade 3 Team Members qualified and rostered for task "C Pick | Picking chill 080", raising qualified-member coverage from a floor of <3 to a floor of 4 across all 98 demanded hourly buckets.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-14T11:01:00Z (approx)
- **Completed:** 2026-07-14T11:13:06Z
- **Tasks:** 2 completed
- **Files modified:** 1

## Accomplishments
- Generated `data/sample_tiny_input_more_tm.json` via a throwaway scratchpad script that deep-copies an existing Team Member row as a template and appends 12 new members, 12 qualification rows, and 36 Roster Profile window rows (3 per member, rolling 3-consecutive-day coverage across the 7-day scenario window).
- Confirmed all 17 untouched tables are byte-for-byte identical to the source, and the 3 touched tables (Team Member, Team Member Qualification and Performance, Roster Profile) retain every original row unchanged with only new rows appended.
- Verified via the real `input_adapter.load_problem` that the new fixture loads without error and qualified-member count for the target task rises from 9 to 21 (a delta of exactly +12, matching the number of new members added).
- Verified per-hour coverage directly from the fixture: all 98 demanded hourly buckets for the target task now have >=3 qualified members with a covering window, with the actual floor reaching 4 (all 98/98 buckets at >=4) — confirming real headroom for the `set_min_workers_per_task n=3` soft constraint to become satisfiable in round 2 of the CP-SAT solve.

## Task Commits

Each task was committed atomically:

1. **Task 1: Generate data/sample_tiny_input_more_tm.json with 12 new qualified + rostered members** - `c7709ff` (feat)
2. **Task 2: Verify adapter load and >=3 qualified-member coverage across all 98 demanded hours** - verification-only task; no code changes produced (all assertions passed against the Task 1 artifact on first run, so no fixture regeneration was needed). No separate commit.

**Plan metadata:** committed separately by the orchestrator (docs commit, per constraints).

## Files Created/Modified
- `data/sample_tiny_input_more_tm.json` - New throwaway test fixture: source fixture (21 tables, all original rows preserved) + 12 new Team Members (Full Time/Grade 3/EA2020-2023) + 12 matching qualification rows for task 99260066-B32A-423D-97A1-8A649BABBAAD + 36 Roster Profile window rows (05:00-23:00, rolling 3-day blocks per member).

## Decisions Made
- Used Roster Profile (not Availability) for the new members' windows since the adapter only requires >=1 window of either kind, and a single-table rolling-block scheme was simpler to generate and verify than splitting across both tables.
- Kept the generator script (`gen_fixture.py`) in the session scratchpad directory, not under `backend/` or committed to the repo — it is a one-off build tool for a throwaway data file, not application code, consistent with the plan's explicit instruction.

## Deviations from Plan

None - plan executed exactly as written. One factual note: the plan's grounding facts stated "8 existing qualified members" as the baseline; the actual baseline measured via `input_adapter.load_problem` was 9. This did not affect any pass/fail assertion — both Task 1 and Task 2 verify blocks check relative deltas (+10 to +15 new members; qualified count rises by exactly the number of new members added), which held regardless of the exact baseline value.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. This fixture is intended for manual follow-up API experimentation (POST /constraints, POST /scenarios/{id}/runs) outside the scope of this quick task.

## Next Phase Readiness
`data/sample_tiny_input_more_tm.json` is ready for manual use: point a scenario at this fixture, apply `set_min_workers_per_task n=3` as a soft constraint via POST /constraints, and re-solve to test whether the added supply resolves the previously-observed infeasibility ceiling for task 99260066-B32A-423D-97A1-8A649BABBAAD.

---
*Phase: 260714-owo*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: data/sample_tiny_input_more_tm.json
- FOUND: c7709ff (Task 1 commit)
- FOUND: .planning/quick/260714-owo-create-a-new-data-fixture-variant-of-dat/260714-owo-SUMMARY.md
