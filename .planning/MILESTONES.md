# Milestones

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
