---
phase: "01"
plan: "02"
subsystem: api-llm
tags: [llm-provider, stub, post-constraints, constraint-service, tdd, di-seam]
dependency_graph:
  requires: [domain.overrides.OverrideCall, domain.overrides.override_id]
  provides: [llm.base.LLMProvider, llm.stub.StubLLMProvider, api.deps.get_llm_provider, POST /constraints, services.constraint_service.parse_and_store, store.repositories.ScenarioRepo.update_overrides]
  affects: [backend/api/deps.py, backend/api/main.py, backend/api/schemas.py, backend/store/repositories.py]
tech_stack:
  added: []
  patterns: [protocol-factory-seam, dependency-injection-seam, keyword-regex-extraction, tool-use-internal-translation, content-hash-idempotency, service-raises-router-translates]
key_files:
  created:
    - backend/llm/__init__.py
    - backend/llm/base.py
    - backend/llm/stub.py
    - backend/api/routers/constraints.py
    - backend/services/constraint_service.py
    - backend/tests/test_llm_provider.py
    - backend/tests/test_constraints_api.py
  modified:
    - backend/api/deps.py
    - backend/api/schemas.py
    - backend/api/main.py
    - backend/store/repositories.py
decisions:
  - "StubLLMProvider regex captures 1-3 words after 'on' to support multi-word task tokens like 'C Pick'; single-word 'Pick' still works for plan spec demos"
  - "constraint_service resolves task tokens with case-insensitive substring matching against both task_id and task.name; requires exactly one match (ambiguous -> 400)"
  - "Router maps LookupError -> 404 and ValueError -> 400; service never raises HTTPException (CLAUDE.md convention)"
  - "ScenarioRepo.update_overrides does not commit; caller (router via get_db) owns commit boundary"
metrics:
  duration_min: 5
  completed_date: "2026-06-28"
  tasks_completed: 2
  files_created: 7
  files_modified: 4
status: complete
---

# Phase 01 Plan 02: LLM Provider Seam + POST /constraints Summary

**One-liner:** Vendor-agnostic LLMProvider Protocol + keyword-routed StubLLMProvider behind get_llm_provider DI seam, plus POST /constraints that parses, resolves, and persists soft overrides with content-hash idempotency.

## What Was Built

### Task 1: LLMProvider seam + StubLLMProvider + get_llm_provider (commits 0eb359d RED, ac84f87 GREEN)

**TDD RED** (commit 0eb359d): `backend/tests/test_llm_provider.py` with 12 failing tests:
- `create_provider("stub")` returns stub, `create_provider("bogus")` raises ValueError
- `parse_constraints("at least 2 on Pick")` returns one `OverrideCall` with correct tool/args/id
- Id starts with `ov_`, is stable across calls, matches `override_id()` helper
- Non-matching text returns `[]`
- `get_llm_provider()` returns the stub

**TDD GREEN** (commit ac84f87):
- **`backend/llm/base.py`** (NEW): `LLMProvider` Protocol with `parse_constraints(text) -> list[OverrideCall]` and `name` property; `create_provider` factory with lazy import (mirrors `engine/base.py` exactly). Only `"stub"` registered — real Claude is Phase 4.
- **`backend/llm/stub.py`** (NEW): `StubLLMProvider` with `re` regex matching `at least N on <token>` phrasings. Builds a Claude-faithful `tool_use` dict internally (`type`/`id`/`name`/`input`) then translates via `_to_override_call()` to `OverrideCall`. The `tool_use` shape never crosses the Protocol boundary (D-08/D-09). Non-matching text returns `[]` (D-10).
- **`backend/api/deps.py`** (MOD): Added `get_llm_provider() -> LLMProvider: return create_provider("stub")` — zero-arg dependency mirroring `get_engine`; swappable in tests via `app.dependency_overrides` (LLM-03).

### Task 2: POST /constraints + constraint_service + repo update (commits 56c8724 RED, 2620e88 GREEN)

**TDD RED** (commit 56c8724): `backend/tests/test_constraints_api.py` with 15 failing tests:
- Happy path: 200, correct fields, args.task_id is resolved GUID (not human token)
- Idempotency: re-submitting same constraint returns same id (D-04/D-05)
- Error paths: 404 unknown scenario, 400 no constraint, 400 ambiguous token ("Pick" matches 3 tasks), 400 unknown token, 422 validation errors

**TDD GREEN** (commit 2620e88):
- **`backend/api/schemas.py`** (MOD): Added `ConstraintParseRequest(scenario_id, text: max_length=2000)` and `ConstraintParseResponse(id, tool, args, parsed_constraint)` (T-01-I4 DoS cap).
- **`backend/store/repositories.py`** (MOD): Added `ScenarioRepo.update_overrides(scenario_id, overrides_json)` — parameterized UPDATE, no commit (caller commits, per repo docstring pattern).
- **`backend/services/constraint_service.py`** (NEW): `parse_and_store()` orchestrates:
  1. Load scenario (LookupError if not found)
  2. `provider.parse_constraints(text)` (ValueError if empty)
  3. Load `SchedulingProblem`; for each `OverrideCall`, resolve task token via case-insensitive substring match against task_id/task.name (exactly one match required — T-01-I3); validate `n > 0` (T-01-I6); recompute `override_id` with resolved args (D-05)
  4. Read-modify-write overrides dict; `repo.update_overrides()`; `conn.commit()`
  5. Return `{id, tool, args, parsed_constraint}` with human-readable label
- **`backend/api/routers/constraints.py`** (NEW): `POST /constraints` — top-level route (D-07), returns 200 (not 201, D-07), no solve trigger (D-06). Maps LookupError -> 404, ValueError -> 400.
- **`backend/api/main.py`** (MOD): `app.include_router(constraints.router)` added.
- **`backend/llm/stub.py`** (MOD): Regex extended to `(\w+(?:\s+\w+){0,2})` to capture multi-word task tokens like "C Pick".

## Verification Results

```
40 passed in 2.56s
backend/tests/test_llm_provider.py .......... 12 passed
backend/tests/test_constraints_api.py ....... 15 passed
backend/tests/test_api.py ................... 5 passed  (no regression)
backend/tests/test_engine_min_workers.py .... 3 passed
backend/tests/test_engine_small.py .......... 2 passed
backend/tests/test_adapter.py ............... 3 passed
```

Manual spot checks:
- `create_provider("stub").parse_constraints("at least 2 on Pick")` → `OverrideCall(id="ov_...", tool="set_min_workers_per_task", args={"task_id": "Pick", "n": 2})`
- `POST /constraints` with `{"scenario_id": "<id>", "text": "at least 2 on C Pick"}` → 200 with `args.task_id = "99260066-B32A-423D-97A1-8A649BABBAAD"` (resolved GUID)
- `POST /constraints` with `text: "at least 2 on Pick"` → 400 (ambiguous: matches C Pick, F Pick, A Pick)
- `/constraints` mounted at top level: confirmed via OpenAPI schema at `/openapi.json`

## Success Criteria Met

- ROADMAP success criterion 1: POST returns 200 and persists a soft override with a stable id to the scenario overrides JSON — **PASSED**
- ROADMAP success criterion 4 (injection + wire-format half): StubLLMProvider behind `get_llm_provider`, Claude-faithful `tool_use` internally, provider-neutral `list[OverrideCall]` — **PASSED**
- LLM-01: `LLMProvider` Protocol in `llm/base.py` with provider-neutral return — **PASSED**
- LLM-03: `get_llm_provider` DI seam, swappable in tests — **PASSED**
- NLC-01: `POST /constraints` returns 200 with echoed override — **PASSED**
- NLC-06: plain-English errors for unknown/ambiguous task and n<=0 — **PASSED**
- TEST-01: stub drives tests; no live LLM API in CI — **PASSED**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stub regex captured only one word after 'on'**
- **Found during:** Task 2 GREEN implementation (first test run)
- **Issue:** `_MIN_WORKERS_RE` used `(\w+)` which extracted only the first word. "at least 2 on C Pick" yielded token `"C"` (matched 6 tasks → ambiguous error instead of 200).
- **Fix:** Changed regex group to `(\w+(?:\s+\w+){0,2})` to capture 1-3 words, supporting multi-word task tokens like "C Pick" while keeping single-word "Pick" from the plan spec working unchanged.
- **Files modified:** `backend/llm/stub.py`
- **Commit:** 2620e88 (included in same GREEN commit)

### Intentional Design Notes

- **Route check in plan's smoke verify:** The plan spec used `any(getattr(r,'path','')=='/constraints' for r in api.main.app.routes)` — FastAPI exposes mounted routers as `_IncludedRouter` objects without a `path` attribute on the top-level `app.routes`. Verified via `GET /openapi.json` which correctly shows `/constraints` in paths. Actual HTTP round-trip tests (15 passing) are the authoritative confirmation.

## TDD Gate Compliance

- Task 1 RED gate: `test(01-02)` commit 0eb359d — 12 failing tests before implementation
- Task 1 GREEN gate: `feat(01-02)` commit ac84f87 — all 12 pass
- Task 2 RED gate: `test(01-02)` commit 56c8724 — 15 failing tests before implementation
- Task 2 GREEN gate: `feat(01-02)` commit 2620e88 — all 15 pass
- REFACTOR gate: No structural changes needed; code is minimal and clean

## Known Stubs

- `StubLLMProvider` is intentionally a stub — it is the Phase-1 default provider (production code, not a test fixture). The real Claude SDK is Phase 4. This is by design, not a gap.

## Threat Surface Scan

New network endpoint introduced: `POST /constraints` at the client→API trust boundary.

| Flag | File | Description |
|------|------|-------------|
| threat_flag: new-endpoint | backend/api/routers/constraints.py | POST /constraints — new untrusted input path for free-text + scenario_id |

All threat mitigations from plan's threat register verified applied:
- T-01-I1 (SQL injection): parameterized placeholders in `update_overrides` and all `ScenarioRepo` methods — confirmed.
- T-01-I3 (hallucinated id): task resolution validates every reference against loaded `SchedulingProblem` before persistence — confirmed.
- T-01-I4 (DoS): `text` field capped at `max_length=2000` in `ConstraintParseRequest` — confirmed.
- T-01-I6 (bad constraint solver): `n > 0` validation, only `set_min_workers_per_task` accepted — confirmed.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `backend/llm/__init__.py` exists | FOUND |
| `backend/llm/base.py` exists | FOUND |
| `backend/llm/stub.py` exists | FOUND |
| `backend/api/routers/constraints.py` exists | FOUND |
| `backend/services/constraint_service.py` exists | FOUND |
| `backend/tests/test_llm_provider.py` exists | FOUND |
| `backend/tests/test_constraints_api.py` exists | FOUND |
| Commit 0eb359d (Task 1 RED) | FOUND |
| Commit ac84f87 (Task 1 GREEN) | FOUND |
| Commit 56c8724 (Task 2 RED) | FOUND |
| Commit 2620e88 (Task 2 GREEN) | FOUND |
| All 40 tests pass | PASSED |
