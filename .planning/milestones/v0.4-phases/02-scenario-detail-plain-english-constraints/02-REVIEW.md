---
phase: 02-scenario-detail-plain-english-constraints
reviewed: 2026-07-17T00:00:00Z
depth: standard
files_reviewed: 31
files_reviewed_list:
  - backend/api/routers/scenarios.py
  - backend/api/schemas.py
  - backend/services/constraint_service.py
  - backend/tests/test_constraints_api.py
  - backend/tests/test_scenarios_api.py
  - docs/API.md
  - frontend/src/App.tsx
  - frontend/src/api/constraints.test.ts
  - frontend/src/api/constraints.ts
  - frontend/src/api/scenarios.ts
  - frontend/src/api/schema.d.ts
  - frontend/src/components/editor/ConstraintInput.test.tsx
  - frontend/src/components/editor/ConstraintInput.tsx
  - frontend/src/components/editor/ConstraintTranscript.test.tsx
  - frontend/src/components/editor/ConstraintTranscript.tsx
  - frontend/src/components/editor/OverridesList.test.tsx
  - frontend/src/components/editor/OverridesList.tsx
  - frontend/src/components/editor/ProviderDownBanner.tsx
  - frontend/src/components/editor/ScenarioHeader.test.tsx
  - frontend/src/components/editor/ScenarioHeader.tsx
  - frontend/src/components/editor/TranscriptEntry.test.tsx
  - frontend/src/components/editor/TranscriptEntry.tsx
  - frontend/src/components/ui/textarea.tsx
  - frontend/src/hooks/useApplyConstraint.test.tsx
  - frontend/src/hooks/useApplyConstraint.ts
  - frontend/src/hooks/useOverrides.test.tsx
  - frontend/src/hooks/useOverrides.ts
  - frontend/src/hooks/useScenario.test.tsx
  - frontend/src/hooks/useScenario.ts
  - frontend/src/lib/toolLabels.ts
  - frontend/src/routes/Editor.test.tsx
  - frontend/src/routes/Editor.tsx
  - frontend/src/routes/router.test.tsx
findings:
  critical: 4
  warning: 4
  info: 0
  total: 8
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-17T00:00:00Z
**Depth:** standard
**Files Reviewed:** 31
**Status:** issues_found

## Summary

This phase ships the scenario-detail editor: `GET /scenarios/{id}/overrides`,
persistence of `parsed_constraint` on applied overrides, and a full new
frontend surface (`Editor`, `ConstraintInput`, `ConstraintTranscript`,
`TranscriptEntry`, `OverridesList`, `ScenarioHeader`, supporting hooks/API
wrappers). Test coverage is broad and mostly precise (backend has strong
error-path and idempotency coverage; frontend unit tests correctly branch on
`error.status`, never message text).

Four blocker-level issues were found. Two are latent defects in
`constraint_service.py` (member-resolution ambiguity handling, and untrusted
LLM-arg coercion) that predate this diff but are directly exercised — and in
one case explicitly validated as "working as designed" by this phase's own
test suite — by the new plain-English constraint UI this phase ships; the bug
is therefore now user-visible for the first time. One is a pre-existing path
handling gap in the fixture lookup (also present in `scenarios.py`/
`constraint_service.py`, not new to this diff, but still live in reviewed
files). One is a genuine new-in-phase frontend correctness bug: the overrides
list renders a false "no constraints applied yet" state whenever its
dependent query hasn't run yet (initial load) or never will (a non-404
scenario error), rather than reflecting the real state.

## Structural Findings (fallow)

None provided for this review.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Member-resolution ambiguity check doesn't dedupe by contact_id — produces a self-contradictory clarification prompt

**File:** `backend/services/constraint_service.py:97-121`
**Issue:**
`_resolve_member`'s substring-match path builds `matches` from `problem.members`
without deduplicating by `contact_id`. The ingest adapter
(`backend/ingest/input_adapter.py:117-134`) creates one `Member` object **per
row** in the "Team Member" table, and the shipped fixture
(`data/sample_tiny_input.json`) has two rows for "Jae Rerekura" sharing the
same `ContactID` (`DF47249E-8864-41B6-93CB-004100655A58`) — confirmed by
`backend/tests/test_constraints_api.py:682-695`
(`test_multi_match_member_clarification`), whose own docstring says: *"The
fixture has two roster entries for Jae Rerekura (same contact_id but two
Member objects from two windows), triggering the multi-match path."*

Because `matches` isn't deduped, a name-substring lookup for any member who
has more than one underlying roster/availability row always returns
`len(matches) == 2` (or more) and falls into the "ask for clarification"
branch at line 116, even though every match resolves to the **same**
`contact_id`. The generated question is built from
`", ".join(f"{m.name!r}" for m in matches)` — for Jae this literally produces:

```
'Jae Rerekura' matches multiple members: 'Jae Rerekura', 'Jae Rerekura'. Which did you mean?
```

This string is rendered **verbatim** to the end user by this phase's new UI
(`TranscriptEntry.tsx:71-80`: `Needs clarification: {clarification_needed}`).
There is no way for a user to answer a question offering two textually
identical options — the plain-English constraint feature becomes unusable for
any member with more than one roster window, which (per the fixture) is a
realistic, not hypothetical, occurrence. The same dedup gap also pollutes the
"Unknown member" error's suggestion list (`valid_names` at line 107), which
will list a multi-window member's name more than once.

**Fix:** Deduplicate `matches` by `contact_id` before deciding ambiguity vs.
unique resolution — the number of *distinct people* matched should drive the
clarification branch, not the number of underlying roster rows:
```python
token_lower = token.lower()
raw_matches = [
    m for m in problem.members
    if token_lower in m.contact_id.lower() or token_lower in m.name.lower()
]
# Dedupe by contact_id — multiple roster windows for the same person must
# not be treated as multiple distinct candidates.
seen: dict[str, str] = {}
for m in raw_matches:
    seen.setdefault(m.contact_id, m.name)

if len(seen) == 1:
    (cid, _name), = seen.items()
    return _ResolveResult(resolved_id=cid, error=None, clarification=None)

if len(seen) == 0:
    ...
matched_names = ", ".join(f"{name!r}" for name in seen.values())
```
Apply the same dedup to the `valid_names` listing used in the zero-match error.

---

### CR-02: Unhandled type coercion / missing-key access on untrusted LLM tool-call args

**File:** `backend/services/constraint_service.py:176-355`
**Issue:** For every tool branch, the service does direct dict-key access and
unguarded numeric coercion on `args` returned by `provider.parse_constraints(text)`:
```python
n = int(args["n"])                       # line 190
factor = float(args["factor"])           # line 222
day = int(args["day"])                   # line 257
max_hours = float(args["max_hours"])     # line 335
```
plus `args["task_id"]` / `args["member_id"]` lookups at lines 178, 211, 246,
284-285, 324. None of this is wrapped in `try/except`. The router
(`backend/api/routers/constraints.py:37-52`) only catches `LookupError` and
`LLMProviderError` — a `KeyError` (missing arg), `ValueError` (non-numeric
string), or `TypeError` (e.g. `None`) raised here propagates uncaught and
becomes a bare `500 Internal Server Error` instead of a graceful `rejected[]`
entry.

The CLAUDE.md project constraints explicitly call out that "NL-derived
constraints must be validated... never able to make a solve infeasible" and
that LLM failures must be handled gracefully; the `stub` provider used in
CI is deterministic and always well-formed, so this gap is invisible in the
test suite, but the docs (`docs/API.md`) document `gemini`/`openrouter` as
real provider options — a live LLM occasionally emitting a malformed or
missing tool argument (e.g. `"n": "two"` or an omitted `factor`) will 500 the
endpoint rather than surfacing a rejected-with-reason entry, which is exactly
the class of failure `rejected[]` exists to prevent.

**Fix:** Wrap the per-call arg extraction/coercion in a guard and route
failures into `rejected[]` instead of letting exceptions escape, e.g.:
```python
try:
    n = int(args["n"])
except (KeyError, TypeError, ValueError):
    rejected.append({"tool": tool, "error": "Missing or non-numeric 'n' argument."})
    continue
```
applied uniformly across all five tool branches.

---

### CR-03: Fixture path is not constrained to the data directory (path traversal / arbitrary file reference)

**File:** `backend/api/routers/scenarios.py:25-26`, `backend/services/constraint_service.py:152`
**Issue:** `ScenarioCreate.fixture` (`backend/api/schemas.py:11`) is validated
only with `Field(min_length=1)` — no path-safety check. Both the
create-scenario existence check and the constraint-parsing fixture load use
`os.path.join(data_dir, fixture)`:
```python
os.path.join(settings.data_dir, body.fixture)          # scenarios.py:25
fixture_path = os.path.join(data_dir, scenario["fixture"])  # constraint_service.py:152
```
`os.path.join` discards all preceding components when the second argument is
an absolute path (e.g. `fixture: "/etc/passwd"` or `C:\Windows\...`), and a
relative `fixture` containing `../` sequences escapes `data_dir` even without
being absolute. `os.path.isfile()` then reports success for any file
reachable this way, and `load_problem()` will attempt to parse it as the
scenario's fixture. This is present in a file under review (`scenarios.py`)
even though it predates this specific diff; flagging per the review's stated
scope (path traversal is explicitly Critical-tier per the review rubric).

**Fix:** Reject any `fixture` value that is absolute or that normalizes
outside `data_dir`:
```python
candidate = os.path.normpath(os.path.join(settings.data_dir, body.fixture))
if os.path.isabs(body.fixture) or not candidate.startswith(os.path.abspath(settings.data_dir) + os.sep):
    raise HTTPException(status_code=400, detail=f"Unknown fixture: {body.fixture!r}")
```

---

### CR-04: `OverridesList` renders a false "no constraints applied yet" state while its query is disabled or permanently un-fetched

**File:** `frontend/src/components/editor/OverridesList.tsx:51-84`, `frontend/src/routes/Editor.tsx:44-49`, `frontend/src/hooks/useOverrides.ts:18-24`
**Issue:** `useOverrides` is a dependent query gated by
`enabled: scenarioQuery.isSuccess` (`Editor.tsx:47-49`). While disabled
(TanStack Query v5 semantics, confirmed by this phase's own test
`frontend/src/hooks/useOverrides.test.tsx:38-47`, which explicitly asserts
`isLoading === false` and `fetchStatus === "idle"` while `enabled: false`),
`OverridesList` has no branch for "not yet enabled" — it only checks
`isLoading` / `isError`, then falls through to:
```js
const overrides = data ?? [];
if (overrides.length === 0) { /* "No constraints applied yet" */ }
```
Since `data` is `undefined` and neither `isLoading` nor `isError` is true
while the query is disabled, the component renders the **empty-state UI** —
"No constraints applied yet" — even though the query has not run at all.

This is not a rare edge case:
1. **Every** page load hits this window: from mount until `scenarioQuery`
   resolves, `OverridesList` shows a false "empty" state instead of a
   loading indicator (in production, `ScenarioHeader` correctly shows
   "Loading scenario…" at the same time — the two regions visibly disagree
   about whether data is ready).
2. If `scenarioQuery` errors with a **non-404** status (Editor.tsx's own
   comment states this state falls through to the full four-region layout,
   not the 404 gate), `overridesQuery` never becomes enabled and this
   incorrect "No constraints applied yet" persists indefinitely, directly
   beside `ScenarioHeader`'s `ErrorBanner` — actively misinformative, not
   merely a transient flash.

**Fix:** Distinguish "hasn't started" from "loaded, genuinely empty" —
either pass the query's `fetchStatus`/`isPending` through and treat
`fetchStatus === "idle" && !isSuccess` as a loading/neutral state, or thread
an explicit `enabled` prop into `OverridesList` so it can render nothing (or
a neutral placeholder) until the parent scenario query has actually
succeeded:
```jsx
if (isLoading || (!overridesQuery.isSuccess && !isError)) {
  return <LoadingSpinner .../>;
}
```

## Warnings

### WR-01: Text-clearing rule doesn't account for a mixed applied+rejected outcome

**File:** `frontend/src/components/editor/ConstraintInput.tsx:68-79`
**Issue:** The clear condition is `data.applied.length > 0 && data.clarification_needed === null`.
The backend explicitly supports (and this phase's own tests exercise) a
response that carries **both** `applied[]` and `rejected[]` in the same 200
with `clarification_needed: null`
(`backend/tests/test_constraints_api.py:824-857`,
`test_mixed_valid_invalid_multi_tool` / `test_mixed_valid_oob_multi_tool`).
Under the current rule, this "partial success" outcome clears the textarea —
even though a fragment of the user's original text was just rejected and they
likely want to see/retype it. The component's own header comment documents
"Rejected-only... preserve[s] the typed text," implying the mixed case's
intended behavior is at least ambiguous, and neither
`ConstraintInput.test.tsx` nor `Editor.test.tsx` covers this exact
applied+rejected (no clarification) combination.

**Fix:** Decide and test the intended behavior explicitly — most likely,
preserve the text whenever `rejected.length > 0`, regardless of `applied`:
```js
if (data.applied.length > 0 && data.rejected.length === 0 && data.clarification_needed === null) {
  setText("");
}
```
and add a test asserting text is preserved on `applied.length > 0 && rejected.length > 0`.

### WR-02: `{"id": k, **v}` spread is fragile if a stored override value ever gains an `id` key

**File:** `backend/api/routers/scenarios.py:53-55`
**Issue:** `[{"id": k, **v} for k, v in raw.items()]` silently lets a
future/legacy stored value's own `"id"` field (if one is ever introduced by a
change to `constraint_service.py`'s persisted shape) clobber the dict's real
key `k`. Currently harmless (stored values only ever carry `tool`/`args`/
`parsed_constraint`), but there's no guard against the collision and no test
covering it.

**Fix:** Make the intent explicit and defensive:
```python
return [{**v, "id": k} for k, v in raw.items()]  # id always wins
```
(spread order flipped so `"id": k` is applied last, guaranteeing the
override's own id can never be shadowed by stored data).

### WR-03: Duplicated `error.status` extraction pattern across three components

**File:** `frontend/src/components/editor/ScenarioHeader.tsx:55`, `frontend/src/components/editor/ConstraintInput.tsx:56-57`, `frontend/src/routes/Editor.tsx:56-58`
**Issue:** The same cast-and-extract idiom —
`(error as { status?: number } | null)?.status` — is repeated verbatim in
three places with no shared helper or type. A future change to the thrown
error shape (e.g. `api/scenarios.ts`/`api/constraints.ts`'s
`throw { status: response.status, ...error }`) requires hunting down and
updating every call site by hand.

**Fix:** Extract a single typed helper, e.g. `getErrorStatus(error: unknown): number | undefined`,
in a shared module (`@/lib/errors.ts`) and use it in all three places.

### WR-04: "Unknown member/task" error listing repeats duplicate names for multi-row members

**File:** `backend/services/constraint_service.py:67`, `:107`
**Issue:** `valid_names = ", ".join(f"{m.name!r} ({m.contact_id})" for m in problem.members)`
enumerates `problem.members` without deduplication (same root cause as
CR-01). For a member with multiple underlying roster rows (e.g. Jae
Rerekura in the shipped fixture), the "Unknown member ... Valid members: ..."
rejection message will list that person's name/id pair twice, degrading the
VAL-03 "list valid options" guidance the message is meant to provide.

**Fix:** Apply the same `contact_id`-based dedup recommended in CR-01 to the
`valid_names` construction (and the analogous `valid_names` for tasks, if
`problem.tasks` can ever contain duplicate `task_id`s).

---

_Reviewed: 2026-07-17T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
