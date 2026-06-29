---
phase: 02-full-5-tool-set-safe-validation
reviewed: 2026-06-29T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - backend/api/schemas.py
  - backend/api/routers/constraints.py
  - backend/services/constraint_service.py
  - backend/services/serialize.py
  - backend/llm/stub.py
  - backend/config/constants.py
  - backend/engine/cpsat/builder.py
  - backend/engine/cpsat/engine.py
  - backend/domain/result.py
  - backend/tests/test_constraints_api.py
  - backend/tests/test_engine_overrides.py
  - backend/tests/test_engine_degenerate.py
findings:
  critical: 0
  warning: 5
  info: 2
  total: 7
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-29
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the full five-tool override set (`set_min_workers_per_task`, `scale_demand`,
`lock_worker_shift`, `exclude_worker_from_task`, `set_max_hours`), the NL parse/validate
service, the stub provider, the CP-SAT builder integration, degeneracy detection, and the
test suite.

**The two safety-critical invariants hold and I could not break them:**

1. **Soft-only constraints.** Every override path in `builder._build_objectives` and
   `builder._aggregate_demand` adds only penalty terms or bounded slack/overflow variables,
   all routed into `round2_cost` (never `round1_unmet`, never a hard `Add`). Each slack is
   bounded (`short ∈ [0,n]`, `absent ∈ [0,1]`, `over ∈ [0, hard_cap-max]`, unmet ∈ [0,rhs]),
   so no override value — including `scale_demand` factor, oversized `n`, or
   `max_hours > hard_cap` — can make the model infeasible. Tests confirm feasibility
   (`test_lock_worker_shift_stays_feasible`, `test_exclude_worker_from_task_honored`).
2. **Status untouched by warnings.** `CpSatEngine.solve` always returns `status=lex.status`
   and only appends to a separate `warnings` list; degeneracy detection is append-only.

No BLOCKER-class defects were found. The findings below are robustness, security-hardening,
correctness-at-the-edges, and test-quality issues.

## Warnings

### WR-01: Service contract violated — malformed provider args raise instead of bucketing into `rejected[]`

**File:** `backend/services/constraint_service.py:178, 191, 257, 335, 393` (and peers)
**Issue:** The module docstring and `parse_and_store` docstring guarantee the service "raises
only `LookupError`" and that "all per-call validation failures are bucketed into `rejected[]`."
But arg extraction assumes the provider always supplies well-formed keys/values:
`args["task_id"]`, `n = int(args["n"])`, `factor = float(args["factor"])`,
`day = int(args["day"])`, `max_hours = float(args["max_hours"])`. A missing key raises
`KeyError`; a non-numeric value raises `ValueError`. The router (`constraints.py:44`) only
catches `LookupError`, so any such failure escapes as an unhandled 500 rather than a
structured `rejected[]` entry. This is latent with the deterministic stub (it always emits
valid args), but the service is the provider-neutral seam that a real Claude provider plugs
into in Phase 4 — exactly the case the contract was written for.
**Fix:** Wrap per-call arg extraction in a guard that converts malformed args into a rejected
entry, e.g.:
```python
try:
    n = int(args["n"])
except (KeyError, ValueError, TypeError):
    rejected.append({"tool": tool, "error": "missing or non-integer 'n'"})
    continue
```
Apply the same pattern to every `args[...]` / numeric cast in the tool branches.

### WR-02: A worker present in multiple windows can never be resolved by name

**File:** `backend/services/constraint_service.py:99-121` (`_resolve_member`)
**Issue:** `problem.members` contains one `Member` object per (contact, roster/availability
window), so a worker who appears in two windows yields two `Member` entries with the same
`contact_id` and name. Name-based substring resolution then returns `len(matches) == 2` and
always emits `clarification` — and the clarification lists the identical name twice
("'Jae Rerekura', 'Jae Rerekura'. Which did you mean?"), which the user cannot answer. This
makes `lock_worker_shift`, `exclude_worker_from_task`, and `set_max_hours` unusable by name
for any multi-window worker. The test `test_multi_match_member_clarification` bakes this
behavior in as "expected," masking the defect.
**Fix:** Deduplicate matches by `contact_id` before counting:
```python
matched_ids = {m.contact_id for m in matches}
if len(matched_ids) == 1:
    return _ResolveResult(resolved_id=next(iter(matched_ids)), error=None, clarification=None)
```
Build the clarification list from distinct `contact_id`s as well.

### WR-03: Off-by-one day validation rejects valid final-day locks for non-24h-multiple horizons

**File:** `backend/services/constraint_service.py:258-259`
**Issue:** `max_day = int(problem.horizon_h // 24) - 1` assumes the horizon is an exact
multiple of 24h. The builder assigns a shift's day as `int(sv.start_h // 24)`
(`builder.py:272, 368`). If `horizon_h` is, say, `167.999` (floating-point noise) or any
non-multiple like `174.0`, the validation horizon and the builder's day space disagree: a
lock on the last real day can be rejected as "outside the scenario horizon" even though the
builder would place shifts there. Conversely a fractional final day passes validation but has
no corresponding full day. The valid-day computation and the builder's day assignment derive
the day count from different formulas.
**Fix:** Derive `max_day` from the same expression the builder uses, e.g.
`max_day = int(math.ceil(problem.horizon_h / 24)) - 1`, or compute it once and share it
between the adapter, service, and builder so the two never drift.

### WR-04: Fixture filename used unsanitized in path join (path traversal / arbitrary JSON read)

**File:** `backend/services/constraint_service.py:152`
**Issue:** `fixture_path = os.path.join(data_dir, scenario["fixture"])` then
`load_problem(fixture_path)` → `json.load`. `scenario["fixture"]` originates from
`POST /scenarios` where it is only checked with
`os.path.isfile(os.path.join(settings.data_dir, body.fixture))` (`api/routers/scenarios.py:24`)
— an existence check, not a containment check. A value like `"../../../etc/hostname"` or an
absolute path passes `isfile` (and `os.path.join` discards `data_dir` entirely for an absolute
path), gets persisted, and is then loaded here as an arbitrary file on the host. The new
constraint flow adds a second sink for this untrusted value. Root cause is the scenarios
router (out of changed scope), but this changed file consumes it unsanitized.
**Fix:** Validate `fixture` against the whitelist returned by `list_fixtures` (basename only,
no separators), or resolve and assert containment:
```python
base = os.path.realpath(data_dir)
target = os.path.realpath(os.path.join(base, scenario["fixture"]))
if os.path.commonpath([base, target]) != base:
    raise LookupError("invalid fixture path")
```

### WR-05: Degeneracy detection in `engine.py` is not exercised by its own tests

**File:** `backend/tests/test_engine_degenerate.py:20-33`
**Issue:** `test_engine_degenerate.py` defines a local `_detect_warnings` helper that is a
hand-copied duplicate of the detection loop in `CpSatEngine.solve` (`engine.py:117-124`), and
all assertions run against the copy, not the real engine code. The comment acknowledges this
("Kept as a helper so tests can exercise the condition directly"). If the real loop in
`engine.py` regresses (wrong threshold, message format, or accidentally mutating `status`),
none of these tests fail. The actual ENG-05 code path has no coverage.
**Fix:** Either extract the detection loop into a small pure function imported by both
`engine.py` and the test (single source of truth), or add at least one test that drives
`CpSatEngine.solve` on a constructed zero-supply problem and asserts `result.warnings` and an
unchanged `result.status`.

## Info

### IN-01: Broken/dead comprehension with variable shadowing in test

**File:** `backend/tests/test_engine_degenerate.py:101`
**Issue:**
`family_names = [w for w in ("Pick","Pack","Receive") if any(family in w for family in (...) for w in warnings)]`
reuses `w` as both the outer comprehension variable and the inner generator variable
(shadowing), the `any(...)` ignores the outer `w`, and `family_names` is never used. The
assertions on lines 103-105 are correct and independent, so the test still passes, but this
line is confusing dead code that misleads future readers.
**Fix:** Delete line 101.

### IN-02: Unused test helper `_bodies_per_hour`

**File:** `backend/tests/test_engine_overrides.py:97-102`
**Issue:** `_bodies_per_hour` is defined but never called — every test instead counts bodies
with inline set comprehensions (e.g. `{r.contact_id for r in ... if r.task_id == "Pick"}`).
Dead code.
**Fix:** Remove the helper, or use it in `test_scale_demand_honored` to assert per-hour body
counts (which would make the test's intent — coverage at a specific hour — more precise).

---

_Reviewed: 2026-06-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
