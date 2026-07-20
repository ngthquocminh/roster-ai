# Codebase Concerns

**Analysis Date:** 2026-07-20

## Tech Debt

**D-06 Grounding Guard False-Positive on coverage_by_day Dictionary Keys:**
- Issue: `_grounding_guard()` in `services/insight_service.py:95-108` is designed to admit numeric citations in insight reports. The `_allowed_values()` function (line 40-92) attempts to admit day-index dictionary keys by calling `admit(float(d))` at line 88. However, this admits the float representation (e.g., `0.0`), but when the LLM model generates text like "Day 0: 61%", the regex `_NUM_RE` (line 37) extracts the bare `0` as a numeric token. The guard compares this `0.0` against allowed values and should pass, but live testing (2026-07-13) revealed this path still produces 502 errors on real model output, suggesting the admitted value set or tolerance logic has an edge case.
- Files: `backend/services/insight_service.py:40-92`, `backend/services/insight_service.py:95-108`
- Impact: Live path to HTTP 502 from `GET /runs/{id}/insights` when an LLM-generated report cites day indices. Frontend's ResultsView survives this (RES-05 isolation) without being fixed at the source. Unfixed but not blocking v0.4.
- Fix approach: Either widen `_allowed_values()` to more robustly admit day-index integers across all rounding variants, or adjust the insight prompt to avoid bare day-index citations in favor of tagged references (e.g., "the first day" instead of "Day 0"). Requires either protocol change (prompt adjustment) or empirical testing against real models to isolate the edge case.

**Single-Worker Solve Pool With No Cancellation:**
- Issue: `services/run_service.py:30-51` uses a module-level `ThreadPoolExecutor(max_workers=1)` protected by `_pool_lock`. Once a solve is submitted, there is no way to stop it or inspect the queue. A user who triggers a 2-minute full-week solve by mistake must wait it out; the run holds the single worker for the entire duration.
- Files: `backend/services/run_service.py:30-51`, `backend/services/run_service.py:69-102`
- Impact: Poor UX on the frontend — users cannot cancel runaway solves. No per-scenario fairness; solves queue strictly FIFO. Single-worker simplification was documented as a v0.2 design choice (v2 OPS-01). Carries into v0.4 and later.
- Fix approach: (1) Add a `CANCELLED` run state and store a cancellation flag that `_execute()` polls; (2) Make `max_workers` configurable via settings for larger deployments; (3) Longer-term: move engine into a separate service with a master run-manager for proper queueing and cancellation semantics (overlaps with "extract engine as separate service" todo).

**No Round-2 Relative-Gap Stop:**
- Issue: `engine/cpsat/objective.py:47` limits solve time by wall-clock `max_time_in_seconds` only. Round 1 (unmet-optimal) completes in ~20s and produces a valid solution. Round 2 (cost minimization) can run for 2+ minutes pursuing exact optimality proof — a tail that matters little for interactive use but degrades perceived latency.
- Files: `backend/engine/cpsat/objective.py:43-63`
- Impact: Interactive solve latency is dominated by a diminishing-returns proof step. Users waiting on HTTP polls experience 2-minute waits for a solution that was 99%+ optimal after 15 seconds (v2 OPS-02).
- Fix approach: Use CP-SAT's native `solver.parameters.relative_gap_limit` on round 2 only (e.g., 0.01 = stop when provably within 1% of optimal). Leave round 1 exact for lexicographic guarantees. Consider surfacing achieved gap in `SolveResult.metrics` so the API can report confidence levels.

**Check Same Thread SQLite Bypass:**
- Issue: `store/db.py:48` opens connections with `check_same_thread=False`, disabling SQLite's thread-safety checks. This is safe only because the architecture serializes all writes via a single-worker pool (`run_service._pool`). But this contract is implicit and fragile — if the pool concurrency ever increases, concurrent writes will corrupt the database without warning.
- Files: `backend/store/db.py:48`
- Impact: Silent data corruption if pool concurrency or connection patterns change without updating this safety bypass. No static analysis catches this hazard.
- Fix approach: Either (1) keep the bypass but add a compile-time assertion that `max_workers == 1`, or (2) switch to explicit connection pooling and queuing so thread safety is enforced by the pool, not by honor system.

## Known Bugs

**Flat Hourly Demand Distribution Misaligns With Real Scheduling Model:**
- Symptoms: Coverage penalty is computed hour-by-hour, so the solver front-loads work suboptimally. A demand band 08:00–16:00 with volume=8 is modeled as "need 1 unit/hour" rather than "accumulate 8 units by 16:00", penalizing valid schedules that batch work earlier.
- Files: `backend/engine/cpsat/builder.py:111` (line 125–137 in `_aggregate_demand`)
- Trigger: Any VOLUME demand that spans multiple hours; INDIRECT (headcount) demand works correctly as-is.
- Workaround: None — real solution requires re-modeling demand as cumulative-by-deadline.
- Fix approach: Introduce a `demand_deadline_mode` flag in `SolverConfig` to coexist with the old hourly model. Rewrite coverage penalty terms and objective cost functions to track labour-units cumulated across the band window, penalizing shortfall at `end_h` instead of per-hour sub-shortfalls. Indirect demand path unchanged.

## Security Considerations

**No Authentication or Authorization:**
- Risk: Every scenario and its results are globally visible to any caller of the API. A shared or public deployment exposes all workforce data without access control.
- Files: Full codebase — no auth layer in `api/`, `llm/`, or `services/`.
- Current mitigation: Out of scope per design (noted in `.planning/PROJECT.md` Context section). Deployment is currently assumed to be internal/trusted-network only.
- Recommendations: Before any shared or public deployment, implement session-based auth (OAuth, JWT, or simple API key) with per-user scenario isolation. Flag this as a hard gate for v0.5+.

**No Input Upload Endpoint:**
- Risk: Scenarios can only be created from pre-existing fixtures on disk. A future upload endpoint without proper path containment (WR-04 prerequisite already resolved in Phase 2) would allow an attacker to write arbitrary files into `data/` or overwrite existing fixtures.
- Files: `backend/api/routers/scenarios.py:17-31` (only reads from disk), `backend/api/routers/fixtures.py` (no write path)
- Current mitigation: WR-04 (fixture path traversal hardening) was resolved in Phase 2 code-review fixes. `settings.resolve_fixture_path()` now rejects absolute paths and `../`-escaping. Upload endpoint design must build on top of this hardening.
- Recommendations: If uploading user data, validate file size strictly (real weekly input is ~16 MB; set a reasonable limit), use streaming/multipart handlers (not naive `json.load` of request body), and test path containment exhaustively before shipping.

**CORS Configuration Resolved at Import Time:**
- Risk: CORS origins are set once in `api.main:38-43` at app startup. Environment changes after import (e.g., a config reload hook trying to swap `CORS_ORIGINS`) will silently fail — the middleware was already added with the old list, and FastAPI does not re-evaluate middleware on each request.
- Files: `backend/api/main.py:28-37`
- Current mitigation: Documented as a "conscious tradeoff" in the comment (line 28–34). Callers are expected to know this behavior.
- Recommendations: Add a startup-phase unit test that mocks `get_settings()` with different CORS origins and verifies the returned list matches what was passed to `CORSMiddleware`. Document explicitly in `.planning/codebase/` or an ADR that CORS origins must be set at deploy time, not runtime.

## Performance Bottlenecks

**Solve Time Dominated by Round-2 Tail:**
- Problem: Round 1 (unmet minimization) completes in ~20s with a valid solution. Round 2 (cost minimization) consumes ~2 minutes pursuing exact optimality. Wall-clock limit applies to both rounds together, so no natural degradation point when time is tight.
- Files: `backend/engine/cpsat/objective.py:43-63`
- Cause: CP-SAT's default search strategy prioritises optimality proof over wall-clock budget. No relative-gap stop configured.
- Improvement path: Add `relative_gap_limit` to round 2 only, stop when provably within 1% of optimal, surface achieved gap in metrics. Measure improvement on full-week fixture and on various fixture sizes.

**No Demand Deadline Accumulation Model:**
- Problem: Coverage penalty spreads demand evenly across hours, forcing uniform workforce distribution. Real model should accumulate labour toward a deadline, allowing front-loaded or batched work.
- Files: `backend/engine/cpsat/builder.py:111` (aggregate_demand, coverage_terms in objective)
- Cause: Per-hour penalty structure couples coverage spread to labour distribution. Fixing requires objective restructuring.
- Improvement path: Implement cumulative-deadline mode; benchmark against current model on multi-hour demand bands. Indirect demand (headcount) stays hourly; VOLUME demand switches to cumulative.

## Fragile Areas

**Insight Generation Error Isolation:**
- Files: `backend/services/insight_service.py:1-177`, `backend/api/routers/runs.py:67-92`
- Why fragile: Grounding guard failure (D-06) or LLM provider error (D-08) both raise `InsightGenerationError`, which routes to 502. Caller (frontend) must branch on `ready` field in response body, not HTTP status code — an unusual contract that breaks common REST clients' assumptions. If frontend logic is ever simplified to treat 502 as "error", it will mask the intended degradation (invalid result) from real errors (provider down).
- Safe modification: Changes to insight generation must preserve the contract: `200 + ready=false` for not-yet-completed runs, `200 + ready=true` for completed runs, `502` for generation failure. Add integration tests that mock both success and LLMProviderError paths and verify the status codes and body structure match the contract.
- Test coverage: Covered by `services/insight_service.py` tests and `api/routers/runs.py` tests, but contract fragility is not explicitly tested (e.g., "verify that a grounding-guard rejection returns 502, not 200").

**Constraint Validation and Deduplication:**
- Files: `backend/services/constraint_service.py:44-56`, `backend/services/constraint_service.py:59-147`
- Why fragile: `_dedupe_by_key()` and resolution logic assume problem.members/problem.tasks may have duplicates (same contact_id/task_id on multiple rows). If the ingest adapter changes and stops creating duplicates, stale deduplication logic remains silent. Conversely, if duplicate rates increase (e.g., more rostering rows per person), the dedup is critical but invisible to callers.
- Safe modification: Add explicit tests for deduplication edge cases (e.g., "resolve_member with 3 roster rows for 1 contact_id returns 1 unique match, not 3"). Document the assumption in constraint_service.py docstring: "This service dedupes ingest artifacts at resolution time; assume problem.members/tasks may have duplicate rows."
- Test coverage: Covered by constraint service tests, but deduplication itself is tested only implicitly through resolution results.

**Database Schema Migration Ad-Hoc:**
- Files: `backend/store/db.py:56-64`
- Why fragile: Schema evolved by hand — `insight_json` column added via `ALTER TABLE IF NOT EXISTS`. No schema versioning, no rollback mechanism. If a future change adds a column, existing deployments must detect the absence and run the ALTER, or fail silently.
- Safe modification: Each schema change must ship with detection logic (e.g., `_has_column()` check). Add a `schema_version` table or `CREATE TABLE IF NOT EXISTS` for versioning so future migrations can reference schema state. Document the schema evolution path in ARCHITECTURE.md.
- Test coverage: `conftest.py` tests start with an empty DB, so fresh-install path is covered. Upgrade path (existing DB + new code) is not tested.

## Scaling Limits

**Single-Worker Thread Pool Hard Limit:**
- Current capacity: 1 concurrent solve
- Limit: Nth solve queues behind 1..N-1; no fairness or priority
- Scaling path: (1) Short-term: increase `max_workers` via settings for single-machine deployments; (2) Long-term: extract engine into a separate service with a dedicated run-manager that handles queueing, concurrency limits, and cancellation; integrate via gRPC or REST.

**SQLite Write Serialization:**
- Current capacity: 1 writer (worker thread) + many readers (request handlers)
- Limit: WAL mode allows concurrent reads, but if solve pool expands to multiple workers, serialization becomes a bottleneck
- Scaling path: Switch to PostgreSQL or similar multi-writer RDBMS; or implement a run-submission queue (Redis/RabbitMQ) decoupled from the database.

**Fixture Size:**
- Current capacity: ~16 MB JSON, committed tiny subsample ~100 KB
- Limit: Full fixture is git-ignored; upload endpoint has no size limit designed yet
- Scaling path: Implement streaming/multipart upload with a reasonable size cap (e.g., 100 MB); consider compressing fixtures or migrating to an artifact store (S3, GCS).

## Dependencies at Risk

**OR-Tools Pinned to 9.11.4210:**
- Risk: Fixed version due to segfault in 9.15 on dev machine (noted in `pyproject.toml:8`). Future versions may have new API changes or deprecations. No plan to upgrade or test newer releases.
- Impact: Locked version may miss critical security fixes or performance improvements in OR-Tools.
- Migration plan: Test 9.15+ on CI before committing to an upgrade. If segfault persists, file an issue with OR-Tools and track blockers.

**Google Genai and OpenAI SDK Versions:**
- Risk: `google-genai>=2.10.0` and `openai>=1.40` are soft-pinned (minimum versions only). Breaking changes in minor releases can silently break the LLM provider seam.
- Impact: CI installs latest; if a provider SDK makes a breaking change to function-calling or error handling, tests may pass locally (pinned .venv) but fail in CI.
- Migration plan: Pin to exact minor versions (e.g., `openai==1.40.0`); set up a dedicated CI job that tests against the latest within the major version range and alerts on failures.

## Missing Critical Features

**Input Upload Endpoint:**
- Problem: Scenarios can only be created from fixtures already in `data/`. Vision (v0.4 omission) states "Upload workforce & demand data" as the entry point. No HTTP upload path exists.
- Blocks: Users cannot bring their own scheduling data. Demo must use pre-committed fixtures. v0.4 frontend omits this deliberately (scope cut for first release).
- Priority: Medium (v0.5 candidate). Depends on WR-04 (path containment) being resolved — which it was in Phase 2.

**Per-Scenario Engine Selection:**
- Problem: `SchedulerEngine` Protocol exists but is never swapped at runtime. Always uses CP-SAT.
- Blocks: Future solver backends (LP relaxation, heuristic, third-party) cannot be selected per-scenario or via config.
- Priority: Low. Current use case doesn't require solver swapping. Protocol exists for future extension.

**Run Cancellation:**
- Problem: Once submitted, a solve cannot be cancelled. Single-worker pool means queued solves are invisible.
- Blocks: Interactive users cannot stop long-running solves. No queue visibility.
- Priority: High (v2 OPS-01). Affects UX on frontend.

**Round-2 Relative-Gap Stop:**
- Problem: Solve time limited by wall-clock only; no optimality-proof cutoff for round 2.
- Blocks: Interactive solve latency is 2+ minutes for full-week fixture even when 15s solution is 99%+ optimal.
- Priority: Medium (v2 OPS-02). Improves perceived latency.

## Test Coverage Gaps

**Insight Generation Contract (ready field):**
- What's not tested: Explicit verification that `GET /runs/{id}/insights` returns `200 + ready=false` before completion and `200 + ready=true` after, and that `502` is only returned on generation failure (not 409 or other status codes).
- Files: `backend/tests/test_api.py` (or dedicated test for insights endpoint)
- Risk: Contract violation (e.g., returning 409 instead of 200 + ready=false) will break frontend without triggering test failure.
- Priority: High. Contract is non-standard and critical to frontend logic.

**Database Upgrade Path:**
- What's not tested: Schema migration on an existing database (upgrade scenario). Only fresh-install path (empty DB) is tested via `conftest.py`.
- Files: `backend/store/db.py:56-64`, `backend/tests/test_db.py` (or `test_api.py` with persistent DB)
- Risk: A column addition or schema change ships and existing deployments fail silently or fail on first write.
- Priority: Medium. Becomes critical before production deployment.

**Grounding Guard Edge Cases:**
- What's not tested: Explicit tests for day-index citations in insight reports (e.g., "Day 0: 61%", "Day 6: 85%") to verify guard does not reject valid day-index numbers. Current D-06 false-positive is known but not unit-tested.
- Files: `backend/tests/test_insight_service.py` (grounding guard unit tests)
- Risk: D-06 false positive surfaces only on live model output; regressions are invisible in default CI.
- Priority: High. Fix the false-positive and add explicit test cases to prevent regression.

**Constraint Deduplication with Multiple Roster Rows:**
- What's not tested: Explicit test fixture with duplicate contact_ids (same person on multiple roster rows) to verify deduplication in `_resolve_member()` and `_resolve_task()`.
- Files: `backend/tests/test_constraint_service.py`
- Risk: If ingest adapter changes to avoid duplicates, or if dedup logic breaks, constraint resolution may return multiple matches where dedup was supposed to collapse them. Not caught by regression tests using fixtures with unique contact_ids.
- Priority: Medium. Safety feature; should be unit-tested.

---

*Concerns audit: 2026-07-20*
