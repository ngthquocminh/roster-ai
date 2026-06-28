# Testing Patterns

**Analysis Date:** 2026-06-26

## Test Framework

**Runner:**
- pytest
- Config: `backend/pyproject.toml`
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  ```

**Assertion Library:**
- Native Python `assert` statements

**Run Commands:**
```bash
pytest                    # Run all tests from backend/
pytest tests/test_api.py  # Run specific test file
pytest -v                 # Verbose output with test names
```

## Test File Organization

**Location:**
- Tests co-located in `backend/tests/` directory (separate from source)
- Each module has corresponding test file (not 1:1 but logically grouped)

**Naming:**
- Test files: `test_*.py`
- Test functions: `test_<function_or_feature>()`
- Test classes: Not used in this codebase

**Structure:**
```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures
│   ├── test_api.py           # API lifecycle tests
│   ├── test_adapter.py       # Data ingestion tests
│   └── test_engine_small.py  # Core engine logic tests
```

## Test Structure

**Suite Organization:**
```python
"""Module docstring explaining test scope and approach."""
from __future__ import annotations

import os
from fastapi.testclient import TestClient

# Imports of code under test


class StubEngine:
    """Fake implementation replacing real dependency."""
    name = "stub"
    
    def solve(self, problem, config) -> SolveResult:
        return SolveResult(...)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Set up test client with mocked dependencies."""
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    
    # Import after env is set
    from api.main import app
    app.dependency_overrides[get_engine] = lambda: StubEngine()
    
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    """Simple assertion test."""
    assert client.get("/health").json() == {"status": "ok"}
```

**Patterns:**
- Module docstring describes test scope
- Fixtures are defined with `@pytest.fixture()` decorator
- Test functions use fixtures as parameters
- Assertions use native `assert` keyword
- Setup: Configure environment or mocks before yielding client
- Teardown: Clean up overrides after test completes

## Mocking

**Framework:** FastAPI's built-in `dependency_overrides` mechanism

**Patterns:**
```python
# From test_api.py
class StubEngine:
    name = "stub"
    
    def solve(self, problem, config) -> SolveResult:
        return SolveResult(
            status="OPTIMAL",
            schedule=[ScheduleRow(...)]
            metrics=SummaryMetrics(...),
            stats=SolverStats(...),
        )

# In fixture:
app.dependency_overrides[get_engine] = lambda: StubEngine()
```

**What to Mock:**
- Slow/external dependencies: `SchedulerEngine` (replaced with stub)
- Time: Use real time in lifecycle tests (polling for PENDING→COMPLETED)
- Database: Real SQLite with temp directory per test (`tmp_path`)

**What NOT to Mock:**
- Data access layer (SQLite): Use real database with temp file
- Adapters: Test real JSON parsing
- Business logic: Test real scenario and run creation

## Fixtures and Factories

**Test Data:**
```python
# From test_engine_small.py
def _make_problem(demand_volume: float) -> SchedulingProblem:
    """Hand-built problem instance with known optimum."""
    task = Task("T1", "Pick", "Pick", "A1")
    tpl = ShiftTemplate("TPL", "8h", 8.0, ())
    members = [
        Member(
            contact_id=f"M{i}", name=f"m{i}", emp_type="Full Time",
            grade_id="G", eba_id="E", contracted_hours=38.0, wage_per_hour=40.0,
            windows=[Window(id=f"r{i}", start_h=0.0, end_h=8.0, kind=WindowKind.ROSTER)],
            qualifications=[Qualification("T1", 10.0)],
        )
        for i in range(2)
    ]
    demand = [DemandBand("T1", DemandFamily.OUTBOUND, 0.0, 8.0, demand_volume, "OB0")]
    return SchedulingProblem(horizon_h=8.0, members=members, tasks=[task],
                             templates=[tpl], demand=demand)
```

**Location:**
- Factories as helper functions: `_make_problem()` (private, test-file scoped)
- Fixtures in `conftest.py` for shared setup: `client`, `tmp_path` (pytest built-in)
- Real input files in `data/` directory (referenced by path, not copied)

## Coverage

**Requirements:** None enforced (no `--cov` configuration in pyproject.toml)

**View Coverage:** Not configured (would require pytest-cov plugin)

## Test Types

**Unit Tests:**
- Test individual functions in isolation
- Example: `test_adapter_loads_fixture()` validates JSON parsing
- Location: `tests/test_adapter.py`, `tests/test_engine_small.py`

**Integration Tests:**
- Test API endpoint behavior with real database and mocked engine
- Example: `test_full_run_lifecycle()` exercises scenario CRUD, run creation, polling, result retrieval
- Location: `tests/test_api.py`
- Setup: Real SQLite with temp directory, mocked engine via dependency override

**E2E Tests:**
- Not used in this codebase
- Integration tests serve this purpose (exercise full request path)

## Common Patterns

**Polling for Async Completion:**
```python
# From test_api.py
def _wait_terminal(client, run_id, timeout_s=10.0):
    """Poll until run reaches terminal state (COMPLETED/FAILED)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in ("COMPLETED", "FAILED"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")
```

**Test Isolation with Environment Variables:**
```python
# From test_api.py
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)
    
    # Import after env is set so settings don't cache defaults
    from api.deps import get_engine
    from api.main import app
    
    app.dependency_overrides[get_engine] = lambda: StubEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```
- Each test gets fresh temp database
- Imports deferred until after environment setup
- Dependency overrides cleaned up after test

**HTTP Assertion Pattern:**
```python
# From test_api.py
r = client.post("/scenarios", json={...})
assert r.status_code == 201
scenario_id = r.json()["id"]
assert client.get(f"/scenarios/{scenario_id}").json()["name"] == "smoke"
```
- Assert status codes first
- Extract values from JSON for further assertions
- Use meaningful assertion messages (implicit from test name)

**Parametric Testing:**
Not used in this codebase; tests are concrete scenarios

---

*Testing analysis: 2026-06-26*
