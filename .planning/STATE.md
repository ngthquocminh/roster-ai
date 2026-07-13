---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 04
status: verifying
stopped_at: Completed 04-02-PLAN.md
last_updated: "2026-07-08T02:38:11.096Z"
last_activity: 2026-07-08
last_activity_desc: Phase 04 complete
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 12
  completed_plans: 12
  percent: 100
current_phase_name: real-claude-provider-penalty-calibration
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-28)

**Core value:** A user can express a scheduling constraint change in plain English and get back a re-solved schedule that honors it (as a soft constraint) plus a readable explanation of what changed.
**Current focus:** Phase 04 — real-claude-provider-penalty-calibration

## Current Position

Phase: 04
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-07-13 — Completed quick task 260713-o5e: add @pytest.mark.live tests covering all LLMProvider operations

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 4 | - | - |
| 03 | 2 | - | - |
| 04 | 3 | - | - |

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
| Phase 04 P01 | 8min | 3 tasks | 6 files |
| Phase 04 P03 | 45min | 3 tasks | 3 files |
| Phase 04 P02 | 60min | 3 tasks | 5 files |

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
- [Phase ?]: Shared to_override_call helper (D-07): stub and future providers both call llm/translate.to_override_call(tool_name, args); no vendor payload shape crosses it
- [Phase ?]: create_provider(name, *, settings=None) threads Settings through the factory ahead of the gemini branch landing in 04-02
- [Phase ?]: LLM-02 spans plans 04-01 and 04-02; requirement checkbox intentionally left pending until 04-02 lands the real Gemini provider branch
- [Phase 04]: 04-03 calibration regression tests were rebased from the full-week fixture onto small hand-built deterministic problems for fast/reliable CI, because CP-SAT wall-clock convergence on the full week is non-deterministic; the sweep harness (scripts/calibrate_penalties.py) retains the full-week target for on-demand magnitude calibration.
- [Phase ?]: GeminiLLMProvider defers genai.Client construction to first use (_get_client) instead of eager construction in __init__, so create_provider('gemini', settings=...) succeeds keylessly (D-04 invariant).
- [Phase 04]: parse_constraints uses AUTO tool-calling mode (not ANY) so non-constraint text can legitimately yield zero function calls, matching the stub's NLC-03 no-constraint-found behavior.
- [Phase 04]: Task 1's blocking human-verify supply-chain checkpoint for google-genai (SUS legitimacy verdict) was approved via the official Google SDK cookbook sample before this session.

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

- [Phase 4 / api]: Harden scenario fixture path against traversal (WR-04) — add containment check before `json.load` in `constraint_service.py:152`
- [testing]: Add real-engine test for ENG-05 degeneracy detection (WR-05) — current tests validate a copied mirror, not `CpSatEngine.solve()`
- [engine / improvement]: Demand scheduling should target deadline fill, not flat hourly distribution — `_aggregate_demand` spreads volume demand evenly per hour but real requirement is to accumulate labour before `b.end_h`; INDIRECT (headcount) demand is fine as-is (`builder.py:111`)
- [architecture / post-POC]: Extract solver engine into a separate service + master run-manager — FastAPI becomes thin API+LLM layer; `SchedulerEngine` Protocol is already the clean seam for this split

### Blockers/Concerns

[Issues that affect future work]

- [Phase 4]: Penalty-weight calibration needs an empirical matrix of solver runs against the committed full-week fixture — flag for a focused validation pass at plan time (per research SUMMARY.md research flags).

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260708-e7z | Add .env support for backend LLM provider config (python-dotenv; committed .env.example, gitignored .env) | 2026-07-08 | 2d2510b | [260708-e7z-add-env-support-for-backend-llm-provider](./quick/260708-e7z-add-env-support-for-backend-llm-provider/) |
| 260708-jov | Make Gemini parse_constraints reliable (system instruction, keeps AUTO/NLC-03) + load .env in conftest so `-m live` works from .env; live parity test now passes against real Gemini | 2026-07-08 | 734a146 | [260708-jov-make-gemini-parse-constraints-reliable-s](./quick/260708-jov-make-gemini-parse-constraints-reliable-s/) |
| 260709-m9m | Map LLM provider errors → clean 503 (neutral `LLMProviderError`, no vendor exception crosses the seam) instead of bare 500; also scoped conftest `.env` load to GEMINI_API_KEY only so a dev's `LLM_PROVIDER=gemini` no longer breaks stub-default tests | 2026-07-09 | 8d0c785 | [260709-m9m-map-llm-provider-errors-to-a-clean-503-i](./quick/260709-m9m-map-llm-provider-errors-to-a-clean-503-i/) |
| 260713-o5e | Add `@pytest.mark.live` tests covering all LLMProvider ops vs real Gemini: `generate_insights` now runs the real D-06 grounding guard (regression net for insight-api-502-ungrounded), and live `parse_constraints` parity broadened to scale_demand/set_max_hours | 2026-07-13 | 1623dae | [260713-o5e-add-pytest-mark-live-tests-covering-all-](./quick/260713-o5e-add-pytest-mark-live-tests-covering-all-/) |

### Roadmap Evolution

- Phase 4 edited: reworded Claude-specific title/goal/criteria to provider-generic (free-tier LLM, Gemini first); also updated REQUIREMENTS LLM-02/TEST-04

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-07-08T01:53:32.406Z
Stopped at: Completed 04-02-PLAN.md
Resume file: None
