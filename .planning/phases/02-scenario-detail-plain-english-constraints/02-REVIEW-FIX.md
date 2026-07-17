---
phase: 02-scenario-detail-plain-english-constraints
fixed_at: 2026-07-18T00:03:00Z
review_path: .planning/phases/02-scenario-detail-plain-english-constraints/02-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-07-18T00:03:00Z
**Source review:** .planning/phases/02-scenario-detail-plain-english-constraints/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (4 critical + 4 warning; `fix_scope: critical_warning`)
- Fixed: 8
- Skipped: 0

**Verification:** Backend `uv run --directory backend python -m pytest -q` — **153
passed, 6 deselected** (deselected = live-provider tests requiring real API keys,
pre-existing marker, not affected by this fix pass). Frontend `npx vitest run` —
**113 passed across 19 files**. Frontend `npx tsc --noEmit` — clean, zero errors.

## Fixed Issues

### CR-01: Member-resolution ambiguity check doesn't dedupe by contact_id

**Files modified:** `backend/services/constraint_service.py`, `backend/tests/test_constraints_api.py`
**Commit:** `1fe78fb`
**Applied fix:** Added a `_dedupe_by_key(items, key_fn)` helper and used it in
`_resolve_member` to collapse raw substring matches by `contact_id` before
counting candidates — a person spanning multiple roster/availability rows now
counts as one candidate, not one-per-row. Also deduped the zero-match "Valid
members" listing. Updated `test_multi_match_member_clarification` (renamed
`test_multi_row_same_person_resolves_without_clarification`) to assert the
corrected behavior: "Jae" now resolves and applies cleanly instead of
producing the previous self-contradictory clarification prompt.

### CR-02: Unhandled type coercion / missing-key access on untrusted LLM tool-call args

**Files modified:** `backend/services/constraint_service.py`, `backend/tests/test_constraints_api.py`
**Commit:** `5577801`
**Applied fix:** Wrapped every tool branch's arg resolution
(`_resolve_task`/`_resolve_member` calls keyed off `args["task_id"]`/
`args["member_id"]`) and numeric coercion (`int`/`float` on `n`, `factor`,
`day`, `max_hours`) in `try/except (KeyError, TypeError, ValueError` /
`AttributeError)`, routing every failure into `rejected[]` with a plain-English
message instead of letting the exception propagate to a bare 500. Added
`test_malformed_llm_tool_args_rejected_not_500`, which stubs the LLM provider
to emit five malformed tool calls (missing key, non-numeric value, `None`
member_id) across all five tool branches and asserts a clean 200 with 5
rejected entries.

### CR-03: Fixture path is not constrained to the data directory (path traversal)

**Files modified:** `backend/settings.py`, `backend/api/routers/scenarios.py`, `backend/services/constraint_service.py`, `backend/tests/test_api.py`, `backend/tests/test_constraints_api.py`
**Commit:** `c87fad9`
**Applied fix:** Added `settings.resolve_fixture_path(data_dir, fixture)`,
which rejects an absolute `fixture` value or one that normalizes outside
`data_dir`, returning `None` for both. `POST /scenarios` now uses it and
returns 400 for an escaping fixture (before ever touching the filesystem).
`constraint_service.parse_and_store` uses the same helper as
defense-in-depth and raises `LookupError` (mapped to the existing 404 path)
if the stored fixture is invalid, rather than trusting the DB row blindly.
Added parametrized tests for `../` traversal and POSIX/Windows absolute
paths at creation time, plus a test that tampers a scenario's stored
`fixture` directly via SQL and confirms `/constraints` still returns 404,
not 500.

### CR-04: `OverridesList` renders a false "no constraints applied yet" state

**Files modified:** `frontend/src/components/editor/OverridesList.tsx`, `frontend/src/components/editor/OverridesList.test.tsx`
**Commit:** `6f6821b`
**Applied fix:** Added an explicit `!isSuccess` branch (after the existing
`isLoading`/`isError` branches) that renders the same "Loading overrides…"
state instead of falling through to the empty-state copy. This covers both
the transient "not yet enabled" window on every mount and the persistent
case where a non-404 scenario error leaves the dependent query disabled
forever. The verified happy path (constraint applied -> row appears;
page reload -> list still populated) is untouched — those paths reach
`isSuccess: true` exactly as before. Updated the existing test helper's
default to `isSuccess: false` (matching real TanStack Query idle
semantics) and added `isSuccess: true` to every test asserting the
populated/empty/legacy branches; added two new tests asserting the
loading state (never the empty-state heading) renders while
disabled/idle.

### WR-01: Text-clearing rule doesn't account for a mixed applied+rejected outcome

**Files modified:** `frontend/src/components/editor/ConstraintInput.tsx`, `frontend/src/components/editor/ConstraintInput.test.tsx`
**Commit:** `3774a82`
**Applied fix:** Added `data.rejected.length === 0` to the textarea-clear
condition, so a 200 response carrying both `applied[]` and `rejected[]`
(with `clarification_needed: null`) now preserves the typed text instead of
clearing it. Added a new test asserting text is preserved on
`applied.length > 0 && rejected.length > 0`.

### WR-02: `{"id": k, **v}` spread is fragile if a stored override value ever gains an `id` key

**Files modified:** `backend/api/routers/scenarios.py`, `backend/tests/test_scenarios_api.py`
**Commit:** `7d31985`
**Applied fix:** Flipped the spread order to `{**v, "id": k}` so the dict's
real key always wins over any same-named field a stored value might carry.
Added a regression test that stores an override value with a colliding
`"id"` field and asserts the endpoint returns the real key, not the stored
value's `id`.

### WR-03: Duplicated `error.status` extraction pattern across three components

**Files modified:** `frontend/src/lib/errors.ts` (new), `frontend/src/lib/errors.test.ts` (new), `frontend/src/components/editor/ScenarioHeader.tsx`, `frontend/src/components/editor/ConstraintInput.tsx`, `frontend/src/routes/Editor.tsx`
**Commit:** `7f89110`
**Applied fix:** Extracted a typed `getErrorStatus(error: unknown): number |
undefined` helper into a new `src/lib/errors.ts` module and replaced the
three verbatim `(error as { status?: number } | null)?.status` casts with
calls to it. Added a small unit test suite for the helper covering the
`{status}` shape, `null`, a plain `Error`, a non-numeric `status`, and
primitive inputs.

### WR-04: "Unknown member/task" error listing repeats duplicate names for multi-row members

**Files modified:** `backend/services/constraint_service.py`, `backend/tests/test_resolve_dedup.py` (new)
**Commit:** `d5bfedc`
**Applied fix:** Applied the `_dedupe_by_key` helper (introduced for CR-01)
to `_resolve_task`'s zero-match "Valid tasks" listing, so a `task_id`
appearing in more than one `problem.tasks` row is listed once. (The
member-side listing was already fixed as part of CR-01, since both
findings shared the same root cause.) Added a new unit-level test module
(`test_resolve_dedup.py`) exercising `_resolve_member`/`_resolve_task`
directly against synthetic Member/Task objects — independent of the
shipped fixture's actual duplicate rows — covering: (1) multiple rows for
the same entity dedupe to a single candidate, (2) genuinely different
entities sharing a substring still trigger clarification with each name
listed once, and (3) zero-match listings never repeat a multi-row entity.

## Skipped Issues

None — all 8 in-scope findings were fixed.

---

_Fixed: 2026-07-18T00:03:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
