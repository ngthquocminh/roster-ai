<!-- generated-by: gsd-doc-writer -->
# Testing

ShiftMind has two independent test suites: `pytest` for the Python backend
(`backend/`) and `vitest` for the React/TypeScript frontend (`frontend/`).
Neither suite makes live network calls by default — the backend drives all
LLM-dependent tests through a stub `LLMProvider`, and the frontend mocks the
API client at the module boundary. A small number of backend tests are tagged
`@pytest.mark.live` and exercise a real LLM provider; they are excluded from
the default run and require a real API key.

For a deeper walkthrough of test structure, fixtures, and mocking
conventions with more code examples, see
[`.planning/codebase/TESTING.md`](../.planning/codebase/TESTING.md).

## Backend (pytest)

**Runner:** `pytest`, configured in `backend/pyproject.toml`.

Run from the `backend/` directory (or prefix with `uv run` from anywhere):

```bash
cd backend
uv run pytest                 # default suite — stub LLM provider, no network calls
uv run pytest -v              # verbose output
uv run pytest tests/test_api.py            # single file
uv run pytest tests/test_api.py -k health  # single test by name
```

### Live provider tests

Tests marked `@pytest.mark.live` exercise a real LLM provider (Gemini or
OpenRouter) over the network and are excluded by default via
`addopts = "-m \"not live\""` in `backend/pyproject.toml`. Files such as
`tests/test_gemini_provider.py` and `tests/test_openrouter_provider.py` carry
this marker. To run them:

```bash
cd backend
uv run pytest -m live          # requires GEMINI_API_KEY and/or OPENROUTER_API_KEY
```

`backend/conftest.py` surfaces only `GEMINI_API_KEY` / `OPENROUTER_API_KEY`
from a local `backend/.env` so the `live` marker can detect a developer's key.
It deliberately does **not** load `LLM_PROVIDER` / `LLM_MODEL` from `.env`, so
the default (non-`live`) suite always runs against the keyless `stub`
provider regardless of a developer's local configuration.

### Where tests live

All backend tests are in `backend/tests/`, named `test_*.py`, separate from
the implementation they exercise (no co-location). Existing files include
`test_api.py`, `test_scenarios_api.py`, `test_constraints_api.py`,
`test_engine_small.py`, `test_llm_provider.py`, `test_gemini_provider.py`,
and `test_openrouter_provider.py`.

### Writing a new backend test

1. Add a new `test_*.py` file in `backend/tests/`, or a new `def test_*()`
   function in an existing file. Open with a module docstring describing
   what the file exercises.
2. For API-level tests, reuse the `client` fixture pattern (see
   `tests/test_scenarios_api.py`): it spins up a `TestClient` with a temp
   SQLite database (`ROSTERAI_DB` pointed at `tmp_path`) and stubs both the
   solver engine and the LLM provider via FastAPI's
   `app.dependency_overrides`:

   ```python
   app.dependency_overrides[get_engine] = lambda: StubEngine()
   app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
   ```

3. Only stub what's expensive or non-deterministic — the real CP-SAT solver
   (`StubEngine`) and real LLM calls (`StubLLMProvider`). Let everything else
   run for real: the actual SQLite database (in a temp dir), real fixture
   JSON from `data/`, and real Pydantic validation.
4. If a test needs a real LLM provider (Gemini/OpenRouter), mark it
   `@pytest.mark.live` so it's excluded from the default CI run.
5. Assert the HTTP status code first, then the response body shape.

No coverage tool is configured for the backend.

## Frontend (vitest)

**Runner:** `vitest` (configured via `test` block in `frontend/vite.config.ts`),
with `jsdom` as the DOM environment and `@testing-library/jest-dom` for DOM
matchers.

Run from the `frontend/` directory:

```bash
cd frontend
npm run test              # runs `vitest run` — full suite, single pass
npm run test -- --watch   # watch mode
npm run typecheck         # tsc --noEmit
npm run lint              # oxlint
```

### Where tests live

Frontend tests are co-located with the source file they cover:
`Component.test.tsx` next to `Component.tsx`, `lib.test.ts` next to `lib.ts`.
For example, `src/api/scenarios.test.ts` sits beside `src/api/scenarios.ts`,
and `src/components/editor/ScenarioHeader.test.tsx` sits beside
`ScenarioHeader.tsx`.

### Mocking convention: `vi.mock` boundary mocks, not MSW

This repo's convention is to mock at the module boundary with vitest's
`vi.mock()` — **not** MSW (network-level interception). Mock the `./client`
module (the generated `openapi-fetch` client) at the top of the test file,
before importing it:

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

Reset mocks in a `beforeEach()`:

```typescript
beforeEach(() => {
  mockGET.mockReset();
  mockPOST.mockReset();
});
```

Use `.mockResolvedValueOnce(...)` for a single expected call, or
`.mockImplementation((path) => ...)` when a test drives multiple distinct
endpoints in one case.

### Writing a new frontend test

1. Create `Component.test.tsx` (or `lib.test.ts`) next to the file under
   test. Open with a doc comment describing what's covered and why it's
   mocked the way it is.
2. Mock the API client module boundary (`vi.mock("./client", ...)`), not the
   network layer — do not introduce MSW.
3. For components that route or link, use `createMemoryRouter` from
   `react-router` instead of mocking navigation:

   ```typescript
   const router = createMemoryRouter(
     [{ path: "/scenarios/:scenarioId", Component: () => <ScenarioHeader scenarioQuery={scenarioQuery} /> }],
     { initialEntries: ["/scenarios/abc"] },
   );
   return render(<RouterProvider router={router} />);
   ```

4. Query the DOM with `@testing-library/react`'s `screen.getByRole()` /
   `screen.getByText()` — don't reach into component internals.
5. Group related cases in `describe()` blocks; name `it()` cases after the
   expected behavior (e.g. `"resolves to [] (not null/undefined/throw) when..."`).
6. Do not mock React Query itself, `@testing-library/react`, or plain utility
   functions — only external boundaries (API client, router where relevant).

`src/test/setup.ts` runs before every test file: it imports
`@testing-library/jest-dom` and polyfills a few DOM APIs jsdom lacks
(`hasPointerCapture`, `releasePointerCapture`, `scrollIntoView`) that Radix UI
components need.

No coverage tool is configured for the frontend.

## Cross-cutting principles

- **Isolation:** every test is independent — no shared state between tests.
  Backend tests get a fresh temp SQLite database per test (`tmp_path`);
  frontend mocks are reset in `beforeEach()`.
- **No live network calls by default:** the backend stub LLM provider and
  frontend `vi.mock()` boundary mean the default suites never touch the
  network. Only `pytest -m live` breaks this rule, intentionally, on request.
- **Determinism:** no time-dependent assertions; async completion is polled
  with a timeout rather than relying on fixed sleeps.
