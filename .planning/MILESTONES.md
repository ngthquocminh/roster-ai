# Milestones

## v0.4 Frontend (Shipped: 2026-07-20)

**Phases completed:** 4 phases, 28 plans, 53 tasks

**Key accomplishments:**

- FastAPI app now accepts cross-origin requests from an env-driven `CORS_ORIGINS` allow-list (default: the two Vite dev/preview origins), proven by 13 automated tests plus a live curl check — no wildcard, no credentials, never hardcoded.
- Human approved all 9 `[SUS]`-flagged install-bound npm packages after a name/source-repo sanity check; `msw` (`[SLOP]`) stays rejected — plan 01-03's install task is unblocked.
- Vite 8 + React 19 + TypeScript app scaffolded under `frontend/`, shadcn initialized on the `nova` preset (neutral/lucide, Geist web font stripped) with Tailwind v4, a typed `VITE_API_BASE_URL` accessor, and a working Vitest + Testing Library + jsdom harness — with `openapi-fetch`/`openapi-typescript` blocked by a harness permission gate, not a legitimacy or plan issue.
- Codegen'd typed client (`openapi-typescript` + `openapi-fetch`) generating `schema.d.ts` from the backend's own live `app.openapi()`, with three thin wrappers (`listScenarios`, `listFixtures`, `createScenario`) — no hand-typed request/response shapes anywhere in `src/api/`.
- Task 1 — Four-route table with persistent two-tier nav and honest placeholders
- `useScenarios()` (TanStack Query) + `ScenarioTable` render the live backend's scenario list on Home across all five UI-SPEC states (loading/empty/error/populated/overflow), satisfying SCEN-01 end-to-end.
- `useFixtures`/`useCreateScenario` TanStack Query hooks plus a Radix-Select-driven `CreateScenarioDialog`, wired into `Home` as the single backend-unreachable-banner decision point — completing SCEN-02 and Phase 1.
- GET /scenarios/{scenario_id}/overrides returning list[OverrideOut] (legacy-safe, unsorted, natural insertion order), with parsed_constraint now persisted alongside tool/args on every applied constraint.
- Regenerated `schema.d.ts` against the D-01 overrides endpoint, added `getScenario`/`getScenarioOverrides`/`applyConstraint` typed wrappers (all status-attaching on error), unit-tested `applyConstraint`'s 503-vs-422 discrimination, and pulled in the shadcn `Textarea` primitive.
- Three hooks completing the Editor's data layer: two independently-observable reads (scenario detail, dependent overrides list) and one overrides-only-invalidating mutation, all TDD'd against the plan-02-02 typed wrappers.
- Read-only Editor surfaces over the plan-02-03 hooks — a 404-resolving scenario detail header and a durable overrides list that renders `parsed_constraint` verbatim with a graceful legacy fallback, never raw `{tool, args}` JSON.
- The Editor's write half — TranscriptEntry/ConstraintTranscript render all five POST /constraints outcomes (applied, rejected, mixed, clarification, no-match) with genuinely distinct D-04/D-05 treatments, and ConstraintInput submits via useApplyConstraint while honestly distinguishing a 503 provider outage from a validation rejection and preserving the user's text on every non-full-success outcome.
- Composed the read half (ScenarioHeader/OverridesList) and write half (ConstraintTranscript/ConstraintInput) into the live `/scenarios/:scenarioId` Editor route — session transcript state owned above both regions, 404-gated, mounted in place of `EditorPlaceholder`.
- Result: APPROVED
- Typed `listRuns`/`triggerRun` wrappers over the run endpoints and a pure `runStatus.ts` module that is the single source of run-status label/icon/color plus the terminal/active predicates driving both polling and rendering.
- React Query hooks for the run lifecycle: a self-terminating polling list query (`useRuns`) driven by the shared `hasActiveRun` predicate, and a trigger mutation (`useTriggerRun`) that invalidates the same query key so a newly triggered run appears without waiting for the next poll tick.
- RunStatusLabel (icon+text, no Badge) and RunHistoryTable (loading/error/empty/populated read surface with inline FAILED errors) built TDD, both consuming the shared runStatusMeta vocabulary from 03-01.
- TriggerRunButton and RunInFlightPanel — two purely presentational components covering RUN-01's every trigger-CTA state and RUN-03's honest, non-cancelable wait copy, both driven entirely by props from a not-yet-built parent.
- RunHistory.tsx composes one useRuns + one useTriggerRun pair into TriggerRunButton, RunInFlightPanel, and RunHistoryTable, and swaps in for RunsPlaceholder at /scenarios/:scenarioId/runs — the point where RUN-01..RUN-05 become true end to end in the browser.
- Pure `formatTimestamp` utility shortens ISO-8601 UTC timestamps to fixed-width "YYYY-MM-DD HH:MM", wired into all three Run History table timestamp columns to close the column-overflow regression (RUN-04).
- Cleared the recharts `[SUS]` supply-chain gate with a recorded human approval, then source-copied card/chart/tooltip via `npx shadcn@latest add`, landing `recharts@3.9.2` as the sole new dependency.
- Hand-written RunResult TypeScript type (single-cast-point deviation for the untyped `/result` endpoint) plus `getRunInsights`, `getRun`, and a rounding-safe `formatShiftWindow` hour-offset formatter — the read contract plans 04-03..04-07 build against.
- Three TanStack Query hooks (useRun, useRunResult, useRunInsights) implementing D-12's gated dependent-query chain and RES-05's structurally isolated insight mutation, each following an in-repo analog exactly.
- Three presentational components — coverage-honesty warnings banner, null-safe cost/unmet-hours stat cards, and a 1-indexed by-day breakdown table — built TDD (RED/GREEN per task) against already-fetched RunResult fields.
- Recharts grouped bar chart (required outline vs. served indigo fill, per function) via shadcn ChartContainer, plus a server-order-only scrollable schedule table reusing RunHistoryTable's container — both null-safe and XSS-safe.
- On-demand five-state insight report panel that branches strictly on the response body's `ready` field (never HTTP status), with an isolated 502 error state and D-13 retry that never touches the rest of the results page
- Composed ResultsView.tsx — the D-12 status-gated route that swaps in for ResultsPlaceholder and wires all six Phase 4 result components (coverage stats, by-day table, demand-vs-served chart, schedule table, insight panel) to one useRun + useRunResult query pair, with an integration test proving the RES-05 502-isolation guarantee.
- Added an honest "No coverage data for this run." empty-state to DemandVsServedChart, gated strictly on mapped-data length so a zero-demand COMPLETED run no longer renders a blank axes-only chart box (closes UAT gap G-04-4).

---

## v0.3 LLM Layer (Shipped: 2026-07-15)

**Phases completed:** 4 phases, 12 plans, 19 tasks

**Key accomplishments:**

- CP-SAT shortfall penalty (`set_min_workers_per_task`) as soft round-2 term via `OverrideCall` domain seam, content-hash id, and `MIN_WORKERS_PENALTY = 100_000` scaled constant.
- Vendor-agnostic LLMProvider Protocol + keyword-routed StubLLMProvider behind get_llm_provider DI seam, plus POST /constraints that parses, resolves, and persists soft overrides with content-hash idempotency.
- run_service._execute now reads scenario['overrides'] JSON into SolverConfig.overrides, closing the NL->override->re-solve vertical slice; verified by a CapturingEngine round-trip test (zero network calls, TEST-02).
- Structured partial-apply ConstraintParseResponse with conjunction-split stub, _resolve_member helper, and clarification sentinel — all verified with 21 passing tests and zero network calls.
- Four new override tools (scale_demand, lock_worker_shift, exclude_worker_from_task, set_max_hours) wired end-to-end — stub regex → service validation → CP-SAT soft penalties — verified by 75 passing tests including five real-engine honor assertions.
- Post-solve zero-coverage detection loop on SolveResult.warnings flowing through serialize_result into runs.result_json (ENG-05).
- Five new stub-driven tests — unknown task/member refs rejected with token+valid-options in error, mixed valid/invalid and valid/OOB multi-tool calls yield applied[]+rejected[] in one 200 response with only valid fragment persisted (criterion 5).
- Sync `GET /runs/{run_id}/insights` with D-06 numeric grounding guard, SQLite insight_json cache column, and deterministic stub provider — full vertical slice from DB to API.
- Negative-path test matrix with FailingInsightProvider, FabricatingInsightProvider, CountingInsightProvider — proves provider failure isolates run state, D-06 grounding guard rejects fabricated numbers, degenerate warnings narrated honestly, and StubLLMProvider is deterministic.
- `LLM_PROVIDER` env var (default `stub`) now selects the backend through a settings-threaded `create_provider`/`get_llm_provider` seam, and every `OverrideCall` — stub today, any future provider tomorrow — is produced by one shared `llm/translate.to_override_call` function.
- Real `GeminiLLMProvider` behind the `LLMProvider` Protocol using the current `google-genai` SDK's native function calling for `parse_constraints` and plain text generation for `generate_insights`, gated by a checkpoint-approved `uv add google-genai` install and a default-excluded `@pytest.mark.live` parity test.
- 1. [Rule 1 - Bug] Fixed inherently flaky + slow calibration regression test file

---
