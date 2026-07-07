---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 4
current_phase_name: Real Claude Provider + Penalty Calibration
status: executing
stopped_at: Phase 4 context gathered
last_updated: "2026-07-07T00:58:32.462Z"
last_activity: 2026-06-30
last_activity_desc: Phase 03 complete, transitioned to Phase 4
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 9
  completed_plans: 9
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-28)

**Core value:** A user can express a scheduling constraint change in plain English and get back a re-solved schedule that honors it (as a soft constraint) plus a readable explanation of what changed.
**Current focus:** Phase 03 — on-demand-insight-reports

## Current Position

Phase: 4 — Real Claude Provider + Penalty Calibration
Plan: Not started
Status: Ready to execute
Last activity: 2026-06-30 — Phase 03 complete, transitioned to Phase 4

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 4 | - | - |
| 03 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 7 | 2 tasks | 6 files |
| Phase 01 P03 | 8 | 2 tasks | 2 files |
| Phase 02 P01 | 6 | 3 tasks | 5 files |
| Phase 02 P03 | 15 | 2 tasks | 4 files |
| Phase 02 P02 | 13 | 3 tasks | 6 files |
| Phase 02 P04 | 2 | 2 tasks | 1 files |
| Phase 03 P01 | 4 | 3 tasks | 8 files |
| Phase 03 P02 | 17 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Vertical-slice MVP — Phase 1 proves the LLM→solver seam with ONE tool end-to-end (stub-driven); later phases broaden the tool set, add insights, swap in real Claude.
- [Roadmap]: `OverrideCall` types live in `domain/` (not `llm/`) to avoid an engine→llm import cycle.
- [Roadmap]: Overrides apply as SOFT penalties in round-2 (cost) only; never round-1, never infeasible.
- [Roadmap]: Insights are a separate on-demand, cached step — an LLM failure never fails a valid schedule.
- [Phase ?]: MIN_WORKERS_PENALTY = 100_000 scaled cents; Phase-4 calibration deferred (ENG-04)
- [Phase ?]: Plan 01-03 decision
- [Phase ?]: scale_demand applied in _aggregate_demand (D-10)
- [Phase ?]: Four new override penalties in round2_cost only (T-02-05..T-02-08)
- [Phase ?]: TEST-03 tests pass at write time (GREEN immediate): implementation pre-exists from plan 02-02
- [Phase ?]: sync-def insight route runs on anyio threadpool (D-02); grounding guard runs before cache write (D-06)

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

- [Phase 4 / api]: Harden scenario fixture path against traversal (WR-04) — add containment check before `json.load` in `constraint_service.py:152`
- [testing]: Add real-engine test for ENG-05 degeneracy detection (WR-05) — current tests validate a copied mirror, not `CpSatEngine.solve()`

### Blockers/Concerns

[Issues that affect future work]

- [Phase 4]: Penalty-weight calibration needs an empirical matrix of solver runs against the committed full-week fixture — flag for a focused validation pass at plan time (per research SUMMARY.md research flags).

### Roadmap Evolution

- Phase 4 edited: reworded Claude-specific title/goal/criteria to provider-generic (free-tier LLM, Gemini first); also updated REQUIREMENTS LLM-02/TEST-04

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-07-06T15:42:22.618Z
Stopped at: Phase 4 context gathered
Resume file: .planning/phases/04-real-claude-provider-penalty-calibration/04-CONTEXT.md
