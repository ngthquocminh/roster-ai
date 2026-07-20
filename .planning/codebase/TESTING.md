# Testing Patterns

**Analysis Date:** 2026-07-20

This document covers testing frameworks, patterns, and practices for both **backend** (Python, `backend/`) and **frontend** (React + TypeScript, `frontend/`) parts of the RosterAI codebase.

---

## BACKEND (Python)

### Test Framework

**Runner:**
- `pytest` 
- Config: `backend/pyproject.toml` (testpaths, markers, addopts)

**Execution:**
```bash
cd backend
pytest                     # Run all tests (excludes @pytest.mark.live)
pytest -m live            # Run only live LLM API tests (requires GEMINI_API_KEY or OPENROUTER_API_KEY)
pytest -v                 # Verbose output
pytest tests/test_api.py  # Single file
```

**Test Markers:**
- `@pytest.mark.live` — exercises real network-backed LLM provider
- Excluded by default via `addopts = "-m \"not live\""` in `pyproject.toml`
- Live tests require environment variables: `GEMINI_API_KEY` or `OPENROUTER_API_KEY`

### Test File Organization

**Location:**
- All tests in `backend/tests/` directory
- Test files named `test_*.py`
- No co-location with source (tests separate from implementation)

**Naming Convention:**
- Descriptive test file names: `test_api.py`, `test_scenarios_api.py`, `test_llm_provider.py`, `test_engine_small.py`
- Descriptive test function names: `test_create_scenario_rejects_unknown_fixture()`, `test_parse_constraints_returns_list_of_override_call()`

### Test Structure

**Module Docstrings:**
- Always present; explain what the test file exercises
- Example from `tests/test_scenarios_api.py:1-12`:
  ```python
  """Tests for GET /scenarios/{scenario_id}/overrides (plan 02-01).

  Exercises (D-01, SCEN-03):
  - 200 with the scenario's persisted overrides as a JSON array of
    {id, tool, args, parsed_constraint}
  - 404 for an unknown scenario id
  - A legacy override stored without a parsed_constraint key deserializes with
    parsed_constraint=null and the endpoint returns 200, never 500
  - Empty overrides -> 200 + []
  - Idempotent re-submission of the same constraint text overwrites the same
    content-hash override id in place (one entry, not two)
  """
  ```

**Setup and Teardown:**
- Fixtures handle all setup/teardown
- Fixtures yield once per test (resource cleanup automatic)
- Example from `tests/test_scenarios_api.py:24-41`:
  ```python
  @pytest.fixture()
  def client(tmp_path, monkeypatch):
      monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
      monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

      from api.deps import get_engine, get_llm_provider
      from api.main import app
      from llm.stub import StubLLMProvider

      from tests.test_constraints_api import StubEngine

      app.dependency_overrides[get_engine] = lambda: StubEngine()
      app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
      with TestClient(app) as c:
          yield c
      app.dependency_overrides.clear()
  ```

**Assertion Style:**
- Direct assertions with meaningful messages
- Example from `tests/test_scenarios_api.py:69-79`:
  ```python
  r = client.get(f"/scenarios/{scenario_id}/overrides")
  assert r.status_code == 200
  body = r.json()
  assert isinstance(body, list)
  assert len(body) == 1
  entry = body[0]
  assert set(entry.keys()) == {"id", "tool", "args", "parsed_constraint"}
  ```

### Fixtures and Factories

**Built-in pytest Fixtures:**
- `tmp_path` — temporary directory (isolated per test)
- `monkeypatch` — safely modify environment and attributes
- `capsys` — capture stdout/stderr

**Custom Fixtures:**
- `client` — TestClient with stubbed engine and LLM provider
- `scenario_id` — creates a test scenario via POST /scenarios (depends on `client` fixture)
- Example from `tests/test_scenarios_api.py:44-53`:
  ```python
  @pytest.fixture()
  def scenario_id(client):
      """Create a scenario using the real tiny fixture and return its id."""
      r = client.post("/scenarios", json={
          "name": "test-overrides",
          "fixture": "sample_tiny_input.json",
          "time_limit_s": 5,
      })
      assert r.status_code == 201
      return r.json()["id"]
  ```

**Test Fixtures (Data):**
- Real fixture files in `data/` directory
- Fixtures loaded during tests (not mocked)
- Example: `sample_tiny_input.json` used by `scenario_id` fixture

**Stubs:**
- `StubEngine` — replaces the real CP-SAT solver for API tests
- `StubLLMProvider` — replaces real LLM for constraint parsing tests
- Both inject via `app.dependency_overrides[dependency] = stub_implementation`

### Mocking

**Strategy:**
- Dependency injection via FastAPI's `app.dependency_overrides`
- Mocks replace dependencies at the API layer (not module-level)
- Example from `tests/test_scenarios_api.py:36-38`:
  ```python
  app.dependency_overrides[get_engine] = lambda: StubEngine()
  app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
  ```

**When to Mock:**
- Real network calls (LLM APIs) → use stubs
- CPU-heavy solves → use `StubEngine`
- Database access → use real `TestClient` with temp SQLite database
- Filesystem → use real files from `data/` directory

**When NOT to Mock:**
- Database operations (real SQLite in temp directory)
- Fixture loading (real JSON files from `data/` directory)
- Request/response handling (real FastAPI app)
- Data validation (real Pydantic models)

### Test Types

**Unit Tests:**
- Test a single function or class in isolation
- Scope: Domain logic, validation, type conversions
- Example: `test_parse_constraints_correct_tool()` — verifies LLM provider output

**Integration Tests:**
- Test multiple components together via HTTP API
- Scope: API lifecycle, database persistence, async execution
- Example: `test_create_scenario_rejects_unknown_fixture()` — exercises router → service → database

**E2E Tests:**
- Not used; scope covered by integration tests with real fixtures

### Common Patterns

**Async Testing:**
- All tests are synchronous (sync wrapper around async code)
- Example from `tests/test_api.py:71-72`:
  ```python
  def test_health(client):
      assert client.get("/health").json() == {"status": "ok"}
  ```
- `TestClient` handles async-to-sync translation internally

**Error Testing:**
- Assert status code first, then check response body
- Example from `tests/test_api.py:80-82`:
  ```python
  def test_create_scenario_rejects_unknown_fixture(client):
      r = client.post("/scenarios", json={"name": "bad", "fixture": "nope.json"})
      assert r.status_code == 400
  ```

**Parametrized Tests:**
- Use `@pytest.mark.parametrize` for multiple input/output combinations
- Example from `tests/test_api.py:85-100`:
  ```python
  @pytest.mark.parametrize(
      "fixture",
      [
          "../../backend/settings.py",       # relative traversal out of data_dir
          "..\\..\\backend\\settings.py",    # Windows-style traversal
          "/etc/passwd",                     # POSIX absolute path
          "C:\\Windows\\win.ini",            # Windows absolute path
      ],
  )
  def test_create_scenario_rejects_path_traversal_fixture(client, fixture):
      r = client.post("/scenarios", json={"name": "bad", "fixture": fixture})
      assert r.status_code == 400
  ```

**Waiting for Async Completion:**
- Use polling loop for background tasks
- Example from `tests/test_api.py:61-68`:
  ```python
  def _wait_terminal(client, run_id, timeout_s=10.0):
      deadline = time.time() + timeout_s
      while time.time() < deadline:
          run = client.get(f"/runs/{run_id}").json()
          if run["status"] in ("COMPLETED", "FAILED"):
              return run
          time.sleep(0.05)
      raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")
  ```

### Test Configuration

**Pytest Configuration (`backend/pyproject.toml`):**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "live: exercises a real network-backed LLM provider; excluded by default (run with `pytest -m live`)",
]
addopts = "-m \"not live\""
```

**Environment Setup (`backend/conftest.py`):**
- Loads `.env` file only for LLM provider keys (GEMINI_API_KEY, OPENROUTER_API_KEY)
- Deliberately **does NOT** load LLM_PROVIDER, LLM_MODEL to enforce stub-only default
- Purpose: Maintain "CI stub-only invariant" — tests never accidentally use a developer's real LLM config
- Example from `conftest.py:8-21`:
  ```python
  # Surface ONLY GEMINI_API_KEY / OPENROUTER_API_KEY from a local backend/.env so
  # the @pytest.mark.live gate can detect a developer's key. Deliberately do NOT
  # load LLM_PROVIDER / LLM_MODEL / OPENROUTER_MODEL from .env — the test suite
  # must observe the keyless `stub` default regardless of a developer's .env
  # (stub-only-CI invariant).
  ```

### Coverage

**Coverage Tool:**
- Not configured; no coverage requirements enforced

**View Coverage (manual setup):**
```bash
pip install pytest-cov
pytest --cov=. --cov-report=html
```

---

## FRONTEND (React + TypeScript)

### Test Framework

**Runner:**
- `vitest` (Vite-native test runner, Vitest 4.x)
- Config: `vite.config.ts` (merged Vitest + Vite configuration)

**DOM Environment:**
- `jsdom` (lightweight browser-like DOM for tests)

**Assertion Library:**
- `@testing-library/jest-dom` (DOM matchers: `toBeInTheDocument()`, `toHaveAttribute()`)

**Execution:**
```bash
cd frontend
npm run test              # Run all tests (vitest run)
npm run test -- --watch  # Watch mode (live reload)
npm run typecheck        # TypeScript type checking
npm run lint             # Run oxlint
```

### Test File Organization

**Location:**
- Co-located with implementation files
- Test files in same directory as source

**Naming Convention:**
- Component tests: `Component.test.tsx`
- Library/utility tests: `lib.test.ts`
- Hook tests: included in component tests or separate `hook.test.ts`

**Structure:**
```
src/
├── api/
│   ├── scenarios.ts
│   ├── scenarios.test.ts      ← Co-located
│   ├── runs.ts
│   └── runs.test.ts           ← Co-located
├── components/
│   ├── editor/
│   │   ├── ScenarioHeader.tsx
│   │   ├── ScenarioHeader.test.tsx  ← Co-located
│   │   ├── ConstraintInput.tsx
│   │   └── ConstraintInput.test.tsx ← Co-located
└── lib/
    ├── errors.ts
    └── errors.test.ts          ← Co-located
```

### Test Structure

**Module Docstrings:**
- Always present; explain coverage scope and reference design docs
- Example from `src/api/scenarios.test.ts:1-8`:
  ```typescript
  /**
   * SHELL-02 coverage for the three thin typed wrappers. Mocks at the `./client`
   * module boundary with `vi.mock` (not `msw` — see COVERAGE.md / RESEARCH.md;
   * `msw` is `[SLOP]`-rejected and its network-level interception is unneeded
   * for this 3-endpoint surface). The unit under test is each wrapper's
   * handling of the `{ data, error, response }` shapes `openapi-fetch` produces
   * — the mocked `client.GET`/`client.POST` calls return those shapes directly.
   */
  ```

**Setup and Teardown:**
- `beforeEach()` resets mocks before each test
- Setup helpers (render helpers, mock factories) defined before test suites
- Example from `src/api/scenarios.test.ts:24-27`:
  ```typescript
  beforeEach(() => {
    mockGET.mockReset();
    mockPOST.mockReset();
  });
  ```

**Describe Blocks:**
- Group related tests by function or scenario
- Example from `src/api/scenarios.test.ts:29-76`:
  ```typescript
  describe("listScenarios", () => {
    it("issues GET /scenarios and resolves to the response array", async () => { ... });
    it("resolves to [] (not null/undefined/throw) when...", async () => { ... });
    it("preserves server order exactly...", async () => { ... });
    it("rejects (does not resolve to an error-shaped value) on a non-2xx response", async () => { ... });
  });
  ```

### Fixtures and Helpers

**Test Helpers:**
- Helper functions defined in test files for setup/rendering
- Example `queryResult()` from `src/components/editor/ScenarioHeader.test.tsx:22-32`:
  ```typescript
  function queryResult(
    overrides: Partial<UseQueryResult<ScenarioOut, unknown>>,
  ): UseQueryResult<ScenarioOut, unknown> {
    return {
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      ...overrides,
    } as UseQueryResult<ScenarioOut, unknown>;
  }
  ```

- Example `renderHeader()` from same file:
  ```typescript
  function renderHeader(scenarioQuery: UseQueryResult<ScenarioOut, unknown>) {
    const router = createMemoryRouter(
      [
        {
          path: "/scenarios/:scenarioId",
          Component: () => <ScenarioHeader scenarioQuery={scenarioQuery} />,
        },
        { path: "/", Component: () => <p>home-route</p> },
      ],
      { initialEntries: ["/scenarios/abc"] },
    );
    return render(<RouterProvider router={router} />);
  }
  ```

**Test Data:**
- Inline mock data in test file
- Example from `src/api/scenarios.test.ts:31-33`:
  ```typescript
  const rows = [
    { id: "a", name: "week1", fixture: "f.json", time_limit_s: 60, created_at: "2026-01-01T00:00:00Z" },
  ];
  ```

### Mocking

**Framework:** `vitest`'s `vi.mock()` (not MSW)

**Strategy:**
- Mock at module boundaries using `vi.mock()`
- Mocks defined at top of file, before imports
- Example from `src/api/scenarios.test.ts:11-16`:
  ```typescript
  vi.mock("./client", () => ({
    client: {
      GET: vi.fn(),
      POST: vi.fn(),
    },
  }));

  import { client } from "./client";
  const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;
  const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;
  ```

**When to Mock:**
- API client (vi.mock) — test wrapper behavior without network
- External libraries (vi.mock) — test component isolation
- React Router (createMemoryRouter) — test routing without navigation spies

**When NOT to Mock:**
- @testing-library/react DOM queries (use real DOM)
- React component rendering (use real components; only mock dependencies)
- React Query (use real `useQuery`, mock underlying API)
- Utility functions (use real functions)

**Mock Reset Pattern:**
```typescript
beforeEach(() => {
  mockGET.mockReset();  // Clear call history and return value
  mockPOST.mockReset();
});
```

**Mock Implementation:**
- Use `.mockResolvedValueOnce()` for success paths
- Use `.mockImplementation()` for dynamic behavior
- Example from `src/api/scenarios.test.ts:136-144`:
  ```typescript
  mockGET.mockImplementation((path: string) => {
    if (path === "/scenarios") {
      return Promise.resolve({ data: scenarioRows, error: undefined, response: { status: 200 } });
    }
    if (path === "/fixtures") {
      return Promise.resolve({ data: fixtureRows, error: undefined, response: { status: 200 } });
    }
    throw new Error(`unexpected path: ${path}`);
  });
  ```

### Test Types

**Unit Tests (API / Utility):**
- Test function behavior in isolation
- Scope: Input → output (no DOM, no React)
- Example: `src/api/scenarios.test.ts` (API wrapper tests), `src/lib/errors.test.ts` (utility tests)

**Component Tests:**
- Test React component rendering and user interactions
- Scope: Props → DOM output
- Use `@testing-library/react` for queries and assertions
- Example from `src/components/editor/ScenarioHeader.test.tsx:48-54`:
  ```typescript
  describe("ScenarioHeader: loading [UI-SPEC E1/loading]", () => {
    it("renders a centered spinner and 'Loading scenario…' with no header fields", () => {
      renderHeader(queryResult({ isLoading: true }));

      expect(screen.getByText("Loading scenario…")).toBeInTheDocument();
      expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    });
  });
  ```

**Integration Tests:**
- Test multiple components or layers together
- Scope: User flow across components
- Example: Router tests with `createMemoryRouter` (test link navigation)

**E2E Tests:**
- Not used in CI; coverage via component + integration tests

### Common Patterns

**Async Testing:**
- Use `async` / `await` in test functions
- TanStack Query promises resolve in `onSuccess`/`onError` callbacks
- Example from `src/api/scenarios.test.ts:30-39`:
  ```typescript
  it("issues GET /scenarios and resolves to the response array", async () => {
    const rows = [{ id: "a", name: "week1", fixture: "f.json", time_limit_s: 60, created_at: "2026-01-01T00:00:00Z" }];
    mockGET.mockResolvedValueOnce({ data: rows, error: undefined, response: { status: 200 } });

    const result = await listScenarios();

    expect(mockGET).toHaveBeenCalledWith("/scenarios");
    expect(result).toEqual(rows);
  });
  ```

**Error Testing:**
- Test error paths (rejected promises, component error states)
- Use `.rejects.toMatchObject()` for promise rejection assertions
- Example from `src/api/scenarios.test.ts:104-113`:
  ```typescript
  it("rejects with an error carrying status === 400 (unknown fixture)", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "fixture not found" },
      response: { status: 400 },
    });

    await expect(
      createScenario({ name: "week1", fixture: "does-not-exist.json" }),
    ).rejects.toMatchObject({ status: 400 });
  });
  ```

**Concurrency Testing:**
- Use `Promise.all()` to assert multiple concurrent calls
- Example from `src/api/scenarios.test.ts:129-150`:
  ```typescript
  it("two concurrent calls each resolve with their own response; neither observes the other's", async () => {
    mockGET.mockImplementation((path: string) => {
      if (path === "/scenarios") {
        return Promise.resolve({ data: scenarioRows, error: undefined, response: { status: 200 } });
      }
      if (path === "/fixtures") {
        return Promise.resolve({ data: fixtureRows, error: undefined, response: { status: 200 } });
      }
      throw new Error(`unexpected path: ${path}`);
    });

    const [scenarios, fixtures] = await Promise.all([listScenarios(), listFixtures()]);

    expect(scenarios).toEqual(scenarioRows);
    expect(fixtures).toEqual(fixtureRows);
  });
  ```

**React Component Testing:**
- Use `screen.getByRole()` / `screen.getByText()` for queries
- Use real routing for link tests (createMemoryRouter)
- Mock console to suppress expected warnings
- Example from `src/components/editor/ScenarioHeader.test.tsx:87-96`:
  ```typescript
  it("renders ErrorBanner when the error carries no status at all", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderHeader(queryResult({ isError: true, error: new Error("network error") }));

    expect(
      screen.getByText("Can't reach the ShiftMind API."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });
  ```

### Test Configuration

**Vitest Configuration (`frontend/vite.config.ts`):**
```typescript
test: {
  environment: 'jsdom',                    // Use DOM environment
  globals: true,                           // Global test functions (describe, it, etc.)
  setupFiles: ['./src/test/setup.ts'],    // Run before tests
  env: {
    VITE_API_BASE_URL: 'http://127.0.0.1:8000',  // Fixed test API URL
  },
}
```

**Setup File (`src/test/setup.ts`):**
- Imports `@testing-library/jest-dom` for DOM matchers
- Polyfills missing jsdom DOM APIs (pointer capture, scrollIntoView)
- Example:
  ```typescript
  import "@testing-library/jest-dom";

  // jsdom doesn't implement pointer capture; Radix Select needs these
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => {};
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
  ```

### Coverage

**Coverage Tool:**
- Not configured; no coverage requirements enforced

**View Coverage (manual setup):**
```bash
npm run test -- --coverage
```

---

## Cross-Codebase Testing Principles

### Test Isolation
- Each test is independent (no shared state)
- Fixtures/mocks reset before each test
- Temp databases/directories for each test run

### Determinism
- Tests produce consistent results regardless of execution order
- No time-dependent behavior (use fake time if needed)
- No network calls (all network access stubbed)

### Clarity
- Test names describe expected behavior: `test_creates_scenario_with_valid_input()`
- Setup code is minimal and clear
- Assertions are specific (not overly broad)

### Speed
- **Backend:** ~100ms per unit test, integration tests slower (DB ops)
- **Frontend:** ~10-50ms per test (mocked dependencies)
- No sleep loops; use polling with timeout

---

*Testing analysis: 2026-07-20*
