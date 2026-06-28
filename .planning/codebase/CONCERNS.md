# Codebase Concerns

**Analysis Date:** 2026-06-26

## Security Issues

### Path Traversal Vulnerability in Scenario Creation

**Issue:** The fixture filename validation in `backend/api/routers/scenarios.py:24` does not prevent path traversal attacks.

**Files:** `backend/api/routers/scenarios.py` (lines 19-27)

**Risk:** An attacker can craft a `fixture` parameter containing `../` sequences to read/reference files outside the intended `data_dir` directory. For example, a request with `fixture="../../../etc/passwd"` could attempt to load files from arbitrary locations on the filesystem.

**Current mitigation:** The code only checks if the file exists with `os.path.isfile(os.path.join(...))`, which does not validate against path traversal.

**Recommendations:**
1. Validate that `body.fixture` contains only alphanumeric characters, underscores, hyphens, and `.json` extension
2. Use `os.path.normpath()` and verify the resolved path stays within `data_dir`
3. Alternatively, maintain a whitelist of allowed fixture names returned by `/fixtures` endpoint

### Unvalidated JSON Size / DoS Vulnerability

**Issue:** JSON loading in `backend/ingest/input_adapter.py:47` has no size limits.

**Files:** `backend/ingest/input_adapter.py` (lines 45-48)

**Risk:** An attacker can craft a malicious fixture file with deeply nested or very large JSON structures, causing memory exhaustion, slow parsing, or server crash (DoS).

**Current mitigation:** None. The file is read completely into memory via `json.load()`.

**Recommendations:**
1. Add file size validation before loading (e.g., max 100 MB for fixture files)
2. Use a streaming JSON parser with strict depth limits for untrusted input
3. Set a timeout on the entire fixture loading operation
4. Document expected file size constraints in the API

### Missing Request Size Limits in FastAPI

**Issue:** FastAPI endpoints do not enforce request body size limits.

**Files:** `backend/api/routers/scenarios.py`, `backend/api/routers/runs.py`

**Risk:** Clients can send arbitrarily large request bodies, potentially causing memory issues or DoS.

**Recommendations:**
1. Configure FastAPI with `max_body_size` parameter (e.g., 1 MB for JSON bodies)
2. Document expected request sizes in API documentation

---

## Database & Transaction Issues

### Unsafe Transaction Handling in get_db Dependency

**Issue:** The `get_db` dependency always commits changes, even when exceptions occur.

**Files:** `backend/api/deps.py` (lines 21-27)

**Code:**
```python
def get_db(settings: Settings = Depends(get_settings)) -> Iterator:
    conn = db.connect(settings.db_path)
    try:
        yield conn
        conn.commit()  # Always commits, even if handler raised an exception
    finally:
        conn.close()
```

**Impact:** If a route handler raises an exception before returning (but after modifying the database), the changes are still committed. This can leave the database in an inconsistent state.

**Fix approach:**
```python
def get_db(settings: Settings = Depends(get_settings)) -> Iterator:
    conn = db.connect(settings.db_path)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()
```

### SQLite check_same_thread=False Threading Risk

**Issue:** In `backend/store/db.py:38`, SQLite connections are created with `check_same_thread=False`.

**Files:** `backend/store/db.py` (line 38)

**Risk:** SQLite normally enforces that connections are used only on the thread that created them. Disabling this check (`check_same_thread=False`) bypasses this safety mechanism. While the codebase creates one connection per worker thread (design is sound), this is fragile—future refactoring could accidentally share connections across threads, leading to silent data corruption.

**Current mitigation:** The code correctly creates a fresh connection per thread in `_execute()` of `backend/services/run_service.py`.

**Recommendations:**
1. Keep the current thread-per-connection design (it's correct)
2. Add a code comment explaining why `check_same_thread=False` is necessary and document the threading invariant
3. Consider adding runtime assertions in tests to verify one connection per thread
4. Alternative (safer for future): use thread-local storage or a connection pool with explicit per-thread handling

### Missing Error Handling in Result Deserialization

**Issue:** The `/runs/{run_id}/result` endpoint does not validate the JSON stored in the database.

**Files:** `backend/api/routers/runs.py` (lines 51-63)

**Code:**
```python
def get_run_result(run_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    ...
    return json.loads(run["result_json"])  # Can crash if result_json is malformed
```

**Risk:** If the database contains malformed JSON in the `result_json` column (e.g., due to a bug in `serialize_result()` or database corruption), this endpoint will raise an unhandled `JSONDecodeError` and return a 500 error to the client instead of a graceful error message.

**Fix approach:**
```python
try:
    return json.loads(run["result_json"])
except json.JSONDecodeError as e:
    raise HTTPException(status_code=500, detail=f"Corrupted result data: {e}")
```

---

## Code Quality & Design Issues

### Overly Broad Exception Handling

**Issue:** Bare `except Exception` in `backend/services/run_service.py:90`.

**Files:** `backend/services/run_service.py` (lines 74-94)

**Code:**
```python
except Exception as exc:  # noqa: BLE001 - persist any failure as run state
    repo.set_failed(run_id, f"{type(exc).__name__}: {exc}", _now())
```

**Impact:** While the intent (capture any failure and persist it) is correct, this pattern can hide unexpected bugs. For example, a typo causing an `AttributeError` would be silently caught and stored as a run failure instead of raising an alert.

**Recommendations:**
1. Be more specific: `except (IOError, ValueError, RuntimeError) as exc:`
2. Add logging to distinguish expected failures from unexpected ones
3. Re-raise unexpected exceptions after logging them

### Global Mutable State in Thread Pool

**Issue:** Global `_pool` variable in `backend/services/run_service.py:29`.

**Files:** `backend/services/run_service.py` (lines 29-51)

**Risk:** While the locking is correct, global mutable state is a source of subtle bugs:
- If the app is reloaded or restarted, the pool is recreated
- Testing with repeated app lifespans (as noted in comments) requires `shutdown()` to reset the pool
- Multi-instance deployment would create independent pools per instance, which is fine but adds complexity

**Current mitigation:** Code correctly uses a lock and recreates the pool after shutdown.

**Recommendations:**
1. Add comprehensive lifecycle tests to verify the pool shuts down cleanly
2. Document the assumption that only one app instance runs at a time (or clarify if horizontal scaling is planned)
3. Consider refactoring into a class-based dependency if the app becomes more complex

---

## Dependency & Environment Issues

### Pinned ortools Version Due to Segfault

**Issue:** `backend/pyproject.toml` pins ortools to `9.11.4210` as a workaround.

**Files:** `backend/pyproject.toml` (line 8), `README.md` (line 93)

**Risk:** The newer version (9.15) segfaults on the dev machine but may work on production. This workaround:
- May not apply to other developers or deployment environments
- Blocks security/performance updates to ortools
- Hides the underlying issue (specific to dev machine setup, not code)

**Recommendations:**
1. Investigate the 9.15 segfault (e.g., Python version, numpy/scipy version mismatch, or OS-specific issue)
2. Test 9.15 on production-like environments (CI/CD with the same Python + deps)
3. Document the segfault with full error output and system details
4. Once resolved, upgrade to a newer ortools version

### Unpinned Transitive Dependencies

**Issue:** `pyproject.toml` uses only top-level version constraints; transitive dependencies can drift.

**Files:** `backend/pyproject.toml`, `backend/uv.lock`

**Recommendations:**
1. Ensure `uv.lock` is committed (it is) and CI always uses `uv sync` (not `uv pip install`)
2. Periodically audit transitive dependencies for security updates
3. Document that `uv.lock` is the source of truth for reproducible builds

---

## Test Coverage Gaps

### Missing Security Tests

**Files:** `backend/tests/test_api.py`

**Gaps:**
- No test for path traversal in fixture names (e.g., `fixture="../../../etc/passwd"`)
- No test for large JSON payloads or DoS scenarios
- No test for malformed JSON in the database result deserialization

**Priority:** High (security)

**Recommendations:**
1. Add `test_create_scenario_rejects_path_traversal()` — test fixtures like `../data/other.json`, `/etc/passwd`, etc.
2. Add `test_large_fixture_rejected()` — test that oversized fixtures are rejected
3. Add `test_get_result_handles_corrupt_json()` — manually insert invalid JSON into the database and verify graceful error

### Missing Edge Case Tests

**Gaps:**
- No test for run execution with invalid data (e.g., empty fixture)
- No test for scheduler timeout/infeasible scenarios
- No test for concurrent scenario/run creation

**Recommendations:**
1. Add `test_run_with_infeasible_problem()` — verify status is `INFEASIBLE` or `UNKNOWN`
2. Add `test_scenario_creation_concurrent()` — stress test with parallel requests

---

## Performance & Scaling Issues

### Single-Worker Thread Pool Serializes All Solves

**Issue:** `backend/services/run_service.py:37` creates a `ThreadPoolExecutor(max_workers=1)`.

**Files:** `backend/services/run_service.py` (line 37)

**Impact:** All CP-SAT solves run sequentially, one at a time. A long-running solve blocks subsequent solves.

**Current mitigation:** The design is deliberate (documented in comments and Phase 2 plan). This is acceptable for Phase 2 (single-user demo).

**Future concern:** Once multi-user or multi-tenant is added (Phase 3+), this becomes a bottleneck.

**Recommendations:**
1. Document this in the design as a Phase 2 limitation (it is, in PLAN.md)
2. Add monitoring/logging to track queue depth and solve times
3. Plan for Phase 3+: consider a configurable worker pool or async job queue (Celery, RQ, etc.)

### No Solve Timeout Recovery

**Issue:** If a solver exceeds `time_limit_s`, the run completes with `status=UNKNOWN` but the solve thread may still be running.

**Files:** `backend/engine/cpsat/objective.py:47`, `backend/services/run_service.py:85`

**Impact:** Long-running solves with tight time limits can accumulate threads that don't release resources immediately.

**Recommendations:**
1. Monitor thread count in tests: verify that threads eventually terminate even after timeout
2. Add a hard wall-clock timeout in `_execute()` to forcibly kill the solve if it exceeds time_limit + grace period
3. Log warnings if a solve thread is still running 10s after the time limit

---

## Documentation Gaps

### Incomplete API Error Documentation

**Issue:** The API schemas and OpenAPI docs do not document all error cases.

**Files:** `backend/api/routers/`, `docs/API.md`

**Examples:**
- What happens if a fixture file is corrupted (currently 500 error, should document)
- What happens if JSON result deserialization fails (currently 500 error)
- What if the solver crashes (currently "FAILED" status but error message may be opaque)

**Recommendations:**
1. Add error response examples to each route
2. Standardize error response format (e.g., `{"error": "...", "code": "..."}`)
3. Document what client should do on each error code

### Missing Deployment Notes

**Issue:** The README mentions AWS as the deployment target but provides no runbook or Dockerfile.

**Files:** `README.md` (line 102), `design.md` (section 3.1)

**Recommendations:**
1. Add `docker/` directory with Dockerfile and docker-compose for Phase 3+ (MVP currently only needs local dev)
2. Document environment variables (currently undocumented except in code comments)
3. Add deployment checklist before going to production

---

## Known Limitations (Not Bugs, But Worth Noting)

### Full-Week Fixture Performance

**Issue:** The full-week fixture takes ~20s for round-1 unmet-optimal and ~2 min for round-2 cost-optimal.

**Files:** `PLAN.md` (lines 57-58), `README.md` (lines 99-101)

**Impact:** Interactive use (UI polling) will feel slow if users request cost-optimal solutions.

**Planned resolution:** Phase 2 follow-up (optional) — tune time limits or add relative-gap stop in round 2. (See PLAN.md Phase 1 follow-ups.)

### No Multitenancy

**Issue:** The app assumes single-user/single-tenant operation.

**Files:** `backend/store/db.py`, `design.md` (ADR-0007)

**Impact:** Scenarios and runs are not namespaced by user/tenant. All users see all data.

**Planned resolution:** Phase 3 deferred (documented in ADR-0007).

---

## Summary by Priority

| Priority | Category | Issue | File |
|----------|----------|-------|------|
| **High** | Security | Path traversal in fixture upload | `backend/api/routers/scenarios.py` |
| **High** | Security | No JSON size limits | `backend/ingest/input_adapter.py` |
| **High** | Database | Unsafe transaction commit on error | `backend/api/deps.py` |
| **Medium** | Code Quality | Broad exception handling | `backend/services/run_service.py` |
| **Medium** | Database | Missing JSON deserialization error handling | `backend/api/routers/runs.py` |
| **Medium** | Testing | Security test gaps | `backend/tests/test_api.py` |
| **Low** | Dependency | ortools segfault workaround | `backend/pyproject.toml` |
| **Low** | Performance | Single-worker thread pool | `backend/services/run_service.py` |
| **Low** | Documentation | Incomplete error documentation | `docs/API.md` |

---

*Concerns audit: 2026-06-26*
