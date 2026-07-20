<!-- generated-by: gsd-doc-writer -->
# Development Guide

ShiftMind is two independently run halves that talk to each other over HTTP in
local development: a Python backend (`backend/`, FastAPI + OR-Tools CP-SAT +
the LLM layer) and a TypeScript frontend (`frontend/`, Vite + React 19). Each
has its own package manager, its own test runner, and its own `.env` file —
neither shares configuration except through `CORS_ORIGINS` (backend) and
`VITE_API_BASE_URL` (frontend), covered in
[`docs/CONFIGURATION.md`](CONFIGURATION.md) rather than repeated here.

This guide covers the day-to-day loop: running each half locally, running
tests, following code style, and the two Protocol seams (`SchedulerEngine`,
`LLMProvider`) that exist specifically so new solver/LLM backends can be added
without touching service or route code.

## Local setup

### Backend (`backend/`)

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`backend/pyproject.toml`,
`backend/uv.lock`). Python 3.10–3.12 (`requires-python = ">=3.10,<3.13"`).

```bash
cd backend
uv sync                              # create .venv + install from uv.lock
cp .env.example .env                 # fill in LLM_PROVIDER / API keys if needed (see CONFIGURATION.md)
uv run uvicorn api.main:app --reload # http://127.0.0.1:8000  (/docs for Swagger)
```

With the default `LLM_PROVIDER=stub`, the backend runs fully keyless — no
`.env` values are required to get the API serving requests.

### Frontend (`frontend/`)

Needs the backend already running (above) and its origin configured.

```bash
cd frontend
npm install
cp .env.example .env                 # set VITE_API_BASE_URL to the backend's origin
npm run dev                          # http://localhost:5173
```

`frontend/src/lib/env.ts` fails loudly at import time if `VITE_API_BASE_URL`
is missing, so a misconfigured `.env` shows up immediately rather than as a
silent failed request.

## Build & script commands

### Backend (run from `backend/`, prefixed with `uv run`)

| Command | Description |
|---|---|
| `uv sync` | Install/update dependencies from `uv.lock` into `.venv` |
| `uv run uvicorn api.main:app --reload` | Start the FastAPI dev server with autoreload |
| `uv run python run.py <input> [engine] [time_limit_s]` | Solve a fixture directly from the CLI (no API/DB) and print metrics |
| `uv run pytest -q` | Run the backend test suite (see [Running tests](#running-tests)) |
| `uv run python fixtures/build_short_input.py` | Regenerate the small fixture from a full weekly input |
| `uv run python scripts/export_openapi.py <out>` | Export the live OpenAPI schema (used by the frontend's `codegen:export`) |

### Frontend (run from `frontend/`, via `npm run`)

| Command | Description |
|---|---|
| `npm run dev` | Start the Vite dev server (`http://localhost:5173`) |
| `npm run build` | Type-check (`tsc -b`) then production-build to `frontend/dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run typecheck` | `tsc --noEmit` — type-check without emitting |
| `npm test` | Run the Vitest suite once (`vitest run`) |
| `npm run lint` | Run `oxlint` |
| `npm run codegen:export` | Export the backend's OpenAPI schema to `frontend/openapi.json` (shells out to `uv run --directory ../backend`) |
| `npm run codegen:types` | Generate `src/api/schema.d.ts` from `openapi.json` via `openapi-typescript` |
| `npm run codegen` | Runs both codegen steps in sequence — do this after changing any backend route/schema |

## Running tests

### Backend

```bash
cd backend
uv run pytest -q                     # default suite — no network, no API keys required
uv run pytest -q -m live             # also run the network-backed live provider tests
```

Tests live in `backend/tests/` as `test_*.py` files (e.g. `test_api.py`,
`test_engine_small.py`, `test_llm_provider.py`, `test_gemini_provider.py`,
`test_openrouter_provider.py`). `backend/pyproject.toml` registers a `live`
pytest marker:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "live: exercises a real network-backed LLM provider; excluded by default (run with `pytest -m live`)",
]
addopts = "-m \"not live\""
```

The default `addopts` excludes `live`-marked tests, so `uv run pytest -q`
never requires `GEMINI_API_KEY` or `OPENROUTER_API_KEY` and is safe to run in
CI or on a fresh machine. The handful of `@pytest.mark.live` tests (in
`test_gemini_provider.py` and `test_openrouter_provider.py`) are additionally
gated with `@pytest.mark.skipif(not _HAS_KEY, ...)`, so even an explicit
`pytest -m live` run skips them cleanly if the relevant API key isn't set in
the environment. `backend/conftest.py` also pops `LLM_PROVIDER` /
`LLM_MODEL` from the process environment after import so a developer's local
`.env` can never flip the default provider under test — every non-`live`
test always observes the keyless `stub` provider.

### Frontend

```bash
cd frontend
npm test                             # vitest run
```

Test files are co-located with the code they cover (`Component.test.tsx`,
`useHook.test.tsx`, `lib.test.ts`) throughout `frontend/src/`. Vitest runs in
`jsdom` (configured in `vite.config.ts`), with `frontend/src/test/setup.ts`
loaded globally — it imports `@testing-library/jest-dom` matchers and
polyfills a few DOM APIs (`hasPointerCapture`, `releasePointerCapture`,
`scrollIntoView`) that jsdom doesn't implement but that Radix UI components
call internally. `vite.config.ts` also pins a fixed
`VITE_API_BASE_URL=http://127.0.0.1:8000` for the `test` block only, so the
suite never depends on a developer's local `.env`.

## Code style

- **Backend:** no linter or formatter is configured (no `ruff.toml`,
  `.pylintrc`, or `.flake8` present) — code follows PEP 8 by convention, with
  a ~100-character line length in multi-line constructs.
- **Frontend:** [`oxlint`](https://oxc.rs/) (`frontend/.oxlintrc.json`), run via
  `npm run lint`. Notable enabled rules: `react/rules-of-hooks` (error),
  `react/only-export-components` (warn). TypeScript runs in strict mode with
  `noUnusedLocals`, `noUnusedParameters`, and `noFallthroughCasesInSwitch` all
  enabled (`frontend/tsconfig*.json`) — `npm run typecheck` enforces these.

For full naming, import-order, error-handling, and module-design conventions
across both halves, see the freshly regenerated
[`.planning/codebase/CONVENTIONS.md`](../.planning/codebase/CONVENTIONS.md) —
this guide intentionally doesn't re-derive that detail.

## Extension points: the two Protocol seams

Two `typing.Protocol` interfaces are the designed extension points for
swapping backends without touching service or route code. Both follow the
same shape: a Protocol, a lazy-import factory function, and a name-keyed
registry.

### `SchedulerEngine` (`backend/engine/base.py`)

```python
class SchedulerEngine(Protocol):
    def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult: ...
    @property
    def name(self) -> str: ...

def create_engine(name: str) -> SchedulerEngine:
    ...  # {"cpsat": CpSatEngine}
```

Currently one implementation is registered: `cpsat`
(`backend/engine/cpsat/engine.py`, Google OR-Tools CP-SAT). Adding a new
solver backend means adding a new `engine/<name>/` package implementing the
Protocol and a new branch in `create_engine()` — domain types and the input
adapter are untouched.

### `LLMProvider` (`backend/llm/base.py`)

```python
class LLMProvider(Protocol):
    def parse_constraints(self, text: str) -> list[OverrideCall]: ...
    def generate_insights(self, summary: dict) -> str: ...
    @property
    def name(self) -> str: ...

def create_provider(name: str, *, settings=None) -> LLMProvider:
    ...  # {"stub", "gemini", "openrouter"}
```

Three implementations are registered today: `stub`
(`backend/llm/stub.py`, deterministic regex-based, keyless — the CI/test
default), `gemini` (`backend/llm/gemini.py`, via `google-genai`), and
`openrouter` (`backend/llm/openrouter.py`, via the `openai` SDK against
OpenRouter's OpenAI-compatible API). Every provider implementation unpacks
its own vendor-specific tool-call shape before calling the shared
`llm/translate.to_override_call` helper, so no vendor payload format ever
crosses the `LLMProvider` boundary — this is what let two real providers get
added with no changes to `services/constraint_service.py` or its router.
Select the active provider via the `LLM_PROVIDER` environment variable (see
[`docs/CONFIGURATION.md`](CONFIGURATION.md)); adding a fourth provider means
adding a new `llm/<name>.py` module and a new branch in `create_provider()`.

## How the backend and frontend talk locally

The frontend calls the backend over plain HTTP; there's no shared process or
IPC. Two environment variables — one on each side — have to agree for this to
work in development:

- `CORS_ORIGINS` (backend) must include the frontend's dev origin.
- `VITE_API_BASE_URL` (frontend) must point at the backend's origin.

The defaults for both are already set to match each other
(`http://localhost:5173`/`http://localhost:4173` on the backend side,
matching Vite's dev/preview ports), so the default `npm run dev` +
`uv run uvicorn ... --reload` setup works with no extra configuration. Full
variable reference, defaults, and required-vs-optional status live in
[`docs/CONFIGURATION.md`](CONFIGURATION.md) — this guide doesn't duplicate
that table.

Frontend request/response types are never hand-authored: `npm run codegen`
exports the backend's live OpenAPI schema
(`scripts/export_openapi.py`) and regenerates `frontend/src/api/schema.d.ts`
from it via `openapi-typescript`. Run it after changing any backend route or
Pydantic schema so the frontend's types stay accurate.

## Branch and workflow conventions

This is an internal project (no `LICENSE`, no `CONTRIBUTING.md` — not
currently open source), so there's no external contribution process to
document. In practice: `main` is the only long-lived branch; there's no
enforced branch-naming convention or PR template checked into the repo.
