---
phase: 02-full-5-tool-set-safe-validation
plan: "01"
subsystem: constraint-api
tags: [api, validation, llm-stub, tdd, partial-apply]
dependency_graph:
  requires: []
  provides: [ConstraintParseResponse-v2, _resolve_member, _ResolveResult, _clarification-sentinel, conjunction-split]
  affects: [backend/api/schemas.py, backend/api/routers/constraints.py, backend/services/constraint_service.py, backend/llm/stub.py, backend/tests/test_constraints_api.py]
tech_stack:
  added: []
  patterns: [NamedTuple-result, partial-apply-loop, clarification-sentinel, conjunction-split-regex, structured-error-body]
key_files:
  created: []
  modified:
    - backend/api/schemas.py
    - backend/api/routers/constraints.py
    - backend/services/constraint_service.py
    - backend/llm/stub.py
    - backend/tests/test_constraints_api.py
decisions:
  - "Per-call validation failures go to rejected[] / clarification_needed — never raise 400"
  - "_clarification sentinel (OverrideCall with tool='_clarification') is the stub-to-service signal for partial phrasings"
  - "_ResolveResult NamedTuple carries exactly one non-None field (resolved_id | error | clarification)"
  - "Only applied[] entries are persisted; rejected/clarification are response-only (T-02-02)"
metrics:
  duration_min: 6
  completed_date: "2026-06-29"
  tasks_completed: 3
  files_changed: 5
status: complete
---

# Phase 02 Plan 01: Reshape Constraint Endpoint into Phase-2 Partial-Apply Contract Summary

**One-liner:** Structured partial-apply ConstraintParseResponse with conjunction-split stub, _resolve_member helper, and clarification sentinel — all verified with 21 passing tests and zero network calls.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Reshape ConstraintParseResponse + router error contract | f64af99 | api/schemas.py, api/routers/constraints.py |
| 2 | Partial-apply parse_and_store + _resolve_member | dc90064 | services/constraint_service.py |
| 3 (RED) | Update contract tests for Phase-2 parse-UX signals | c3a7275 | tests/test_constraints_api.py |
| 3 (GREEN) | Stub conjunction split + clarification sentinel | 290dff6 | llm/stub.py |

## What Was Built

### Schemas (api/schemas.py)

Added `AppliedConstraint` (id, tool, args, parsed_constraint) and `RejectedConstraint` (tool, error) Pydantic models. Replaced the old flat `ConstraintParseResponse` with a 4-field structured body:

```python
class ConstraintParseResponse(BaseModel):
    applied: list[AppliedConstraint]
    rejected: list[RejectedConstraint]
    clarification_needed: str | None
    no_constraint_found: bool
```

### Router (api/routers/constraints.py)

Removed the `except ValueError -> HTTPException(400)` handler. Only LookupError->404 remains. Per-call failures now flow through the service into the structured response body.

### Service (services/constraint_service.py)

- `_ResolveResult(NamedTuple)`: resolved_id | error | clarification — exactly one non-None field
- `_resolve_task`: rewritten to return `_ResolveResult` (zero match → error, single → resolved_id, multi → clarification) — no longer raises
- `_resolve_member`: new helper mirroring `_resolve_task` against `problem.members` (contact_id and name)
- `parse_and_store`: full partial-apply loop — partitions `_clarification` sentinels, processes real tool calls, buckets results into applied/rejected/clarification, persists ONLY applied entries

### Stub (llm/stub.py)

- `_SPLIT_RE`: splits on `and`/`but`/commas
- `_split_fragments(text)`: returns stripped non-empty fragments
- `_MIN_WORKERS_RE`: generalized with additional synonym forms (`min`, `require at least`)
- `_PARTIAL_WORKERS_RE`: matches `more/fewer/extra people on <task>` — no number
- `parse_constraints`: iterates fragments, matches both regexes, emits `OverrideCall(tool="_clarification")` sentinel for partial phrasings

### Tests (tests/test_constraints_api.py)

Updated 21 tests covering:
- Phase-2 structured body: `applied[0]` field access
- `no_constraint_found=True` for gibberish (NLC-03)
- `clarification_needed` for ambiguous tokens (NLC-05)
- `rejected[0].error` naming unknown token (VAL-02/D-11)
- `clarification_needed` for partial phrasing `more people on <task>` (NLC-05)
- Mixed applied + clarification in one response (D-02)
- Rejected entries not persisted (T-02-02)
- End-to-end threading (plan 01-03 TEST-02) updated for new response shape

## Verification

```
pytest tests/test_constraints_api.py -x -q
21 passed, 1 warning in 2.23s
```

All must-have truths satisfied:
- D-01: POST /constraints returns 200 with {applied[], rejected[], clarification_needed, no_constraint_found}
- D-02: applied[], rejected[], clarification_needed co-exist in one response (mixed test)
- D-03: Gibberish -> no_constraint_found=True, 200
- NLC-03: no_constraint_found for texts with no constraint shape
- NLC-04: Each applied entry carries parsed_constraint string
- NLC-05: Ambiguous/partial phrasings return clarification_needed
- VAL-02/D-11: Unknown task token rejected with plain-English error naming the token
- T-02-02: Only applied entries persisted; rejected/clarification are response-only

## Deviations from Plan

None - plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes beyond what the threat model covers. T-02-01 (tampering via NL reference resolution) and T-02-02 (persistence path only for applied entries) are both mitigated as planned.

## Known Stubs

None — the `set_min_workers_per_task` tool is fully wired end-to-end with real task resolution against scenario fixtures. No placeholder data in response fields.

## Self-Check

| Item | Status |
|------|--------|
| backend/api/schemas.py | FOUND |
| backend/api/routers/constraints.py | FOUND |
| backend/services/constraint_service.py | FOUND |
| backend/llm/stub.py | FOUND |
| backend/tests/test_constraints_api.py | FOUND |
| Commit f64af99 (Task 1) | FOUND |
| Commit dc90064 (Task 2) | FOUND |
| Commit c3a7275 (Task 3 RED) | FOUND |
| Commit 290dff6 (Task 3 GREEN) | FOUND |
| pytest 21 passed | PASSED |

## Self-Check: PASSED
