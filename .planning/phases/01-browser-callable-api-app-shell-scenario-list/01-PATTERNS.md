# Phase 1: Browser-Callable API + App Shell + Scenario List - Pattern Map

**Mapped:** 2026-07-16
**Files analyzed:** 22 (1 backend modification + 1 backend new test + ~20 frontend new files)
**Analogs found:** 4 / 22 (backend only) — 0 / ~20 frontend files have in-repo analogs (repo is 100% Python; `frontend/` is greenfield). This is expected, not a gap — see "No Analog Found" below.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/settings.py` (modify — add `cors_origins` field) | config | request-response | `backend/settings.py` (itself — extend existing pattern) | exact |
| `backend/api/main.py` (modify — add `CORSMiddleware`) | config/middleware | request-response | `backend/api/main.py` (itself — extend existing pattern) | exact |
| `backend/tests/test_cors.py` (new) | test | request-response | `backend/tests/test_api.py` (fixture pattern) | exact |
| `frontend/src/api/client.ts` | service | request-response | none — greenfield | no analog |
| `frontend/src/api/scenarios.ts` | service | CRUD | none — greenfield | no analog |
| `frontend/src/api/schema.d.ts` (generated) | model/types | — | none — greenfield, generated artifact | no analog |
| `frontend/src/hooks/useScenarios.ts` | hook | CRUD (read) | none — greenfield | no analog |
| `frontend/src/hooks/useFixtures.ts` | hook | CRUD (read) | none — greenfield | no analog |
| `frontend/src/hooks/useCreateScenario.ts` | hook | CRUD (write) | none — greenfield | no analog |
| `frontend/src/App.tsx` | route/provider | request-response | none — greenfield | no analog |
| `frontend/src/main.tsx` | provider | — | none — greenfield | no analog |
| `frontend/src/routes/Home.tsx` | component/route | CRUD | none — greenfield | no analog |
| `frontend/src/routes/ScenarioLayout.tsx` | component/route | request-response | none — greenfield | no analog |
| `frontend/src/routes/{Editor,Runs,Results}Placeholder.tsx` | component/route | — | none — greenfield | no analog |
| `frontend/src/components/layout/AppBar.tsx` | component | — | none — greenfield | no analog |
| `frontend/src/components/layout/ErrorBanner.tsx` | component | — | none — greenfield | no analog |
| `frontend/src/components/scenarios/ScenarioTable.tsx` | component | CRUD (read) | none — greenfield | no analog |
| `frontend/src/components/scenarios/CreateScenarioDialog.tsx` | component | CRUD (write) | none — greenfield | no analog |
| `frontend/src/lib/utils.ts` | utility | transform | none — greenfield (shadcn-generated) | no analog |
| `frontend/src/lib/env.ts` | utility | config | none — greenfield | no analog |
| `frontend/vite.config.ts` | config | — | none — greenfield | no analog |
| `frontend/.env.example` | config | — | `backend/.env.example` (established env-config *convention*, not code) | pattern-only |

## Pattern Assignments

### `backend/settings.py` (config, request-response)

**Analog:** itself — this phase extends the existing `Settings` dataclass/`default_settings()` pattern with one more field, following the exact shape of every other field already there. Do not invent a second config mechanism.

**Existing field pattern to copy** (`backend/settings.py:30-63`):
```python
@dataclass(frozen=True)
class Settings:
    db_path: str            # SQLite file
    data_dir: str           # directory holding input fixtures (*.json)
    llm_provider: str       # "stub" (default) | "gemini" | "openrouter"
    llm_model: str          # model id passed to the selected provider
    # T-04-01: keep the API key out of the auto-generated __repr__ ...
    llm_api_key: str | None = field(repr=False, default=None)
    ...

def default_settings() -> Settings:
    """Read settings fresh each call so env overrides apply at request time."""
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    ...
    return Settings(db_path=db_path, data_dir=data_dir, ...)
```

**New field to add, same shape** (per RESEARCH.md Code Examples — not secret, so no `repr=False` needed):
```python
cors_origins: tuple[str, ...] = field(default=())
# in default_settings():
cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:4173")
cors_origins = tuple(o.strip() for o in cors_origins_raw.split(",") if o.strip())
```

**Convention notes:**
- snake_case field name, tuple (not list) for an immutable frozen dataclass field — matches `llm_provider`, `llm_model` etc.
- Env var name follows the existing `ROSTERAI_*`/`LLM_*` uppercase convention: `CORS_ORIGINS`.
- Do not mark `repr=False` — that treatment (`backend/settings.py:36-40`) is reserved for actual secrets (`llm_api_key`, `openrouter_api_key`); CORS origins are not secret and weakening/copying that pattern onto a non-secret field would blur its meaning.

---

### `backend/api/main.py` (middleware/config, request-response)

**Analog:** itself — small, clean file; `CORSMiddleware` inserts directly after `app = FastAPI(...)`, before the `include_router` calls.

**Current structure** (`backend/api/main.py:1-32`, full file):
```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.deps import get_settings
from api.routers import constraints, fixtures, health, runs, scenarios
from services import run_service
from store import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(get_settings().db_path)
    yield
    run_service.shutdown()


app = FastAPI(title="ShiftMind API", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(fixtures.router)
app.include_router(scenarios.router)
app.include_router(runs.router)
app.include_router(constraints.router)
```

**Insertion point and pattern** (per RESEARCH.md Code Examples, using the existing `get_settings` import already present at line 12):
```python
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ShiftMind API", version="0.1.0", lifespan=lifespan)

# NOTE: CORS origins are resolved once here, at process/import time — unlike
# every other Settings field (which re-reads env per request), because
# CORSMiddleware itself only registers once at app construction. This is a
# conscious tradeoff, not a bug — see RESEARCH.md "Common Pitfalls" #1.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    # allow_credentials left at its default False — D-02 (no auth) means no
    # cookie/Authorization-header requests ever need it; combining a real
    # origin allow-list with credentials=True is unnecessary surface area.
)

app.include_router(health.router)
...
```

**Key constraint:** `get_settings()` is called once at import time here — do not thread `Depends(get_settings)` into this call site the way routers do; middleware registration happens outside the request lifecycle.

---

### `backend/tests/test_cors.py` (test, request-response)

**Analog:** `backend/tests/test_api.py` — specifically its `client` fixture (lines 46-58), which already solves "set env before importing `api.main`" for exactly this reason (module-level settings/app caching).

**Fixture pattern to copy** (`backend/tests/test_api.py:46-58`):
```python
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", _DATA_DIR)

    # Import after env is set so nothing caches the default settings.
    from api.deps import get_engine
    from api.main import app

    app.dependency_overrides[get_engine] = lambda: StubEngine()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

**Adapted for CORS** (per RESEARCH.md Code Examples — set `CORS_ORIGINS` *before* importing `api.main`, same reasoning as `ROSTERAI_DB`/`ROSTERAI_DATA_DIR` above, since CORS is resolved once at import time):
```python
def test_cors_reflects_configured_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    from api.main import app
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"

        resp2 = client.get("/health", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in resp2.headers
```

**Imports** — same top-of-file shape as `test_api.py:1-14` (`from __future__ import annotations`, `import os`, `import pytest`, `from fastapi.testclient import TestClient`); no need for the `domain.result` imports (`test_api.py` needs those for `StubEngine`, this test doesn't touch the engine).

**Existing endpoint to exercise:** use `GET /health` (already exists per `api/main.py`'s `health.router` — cheapest endpoint for asserting header presence/absence, no DB/fixture setup needed beyond what the fixture already sets for module import safety).

---

## No Analog Found

All frontend files — the entire `frontend/` tree (routes, components, hooks, API client, config) — have **no in-repo analog**. The repository is 100% Python prior to this phase; there is no existing JS/TS/React code, no `package.json` outside `.claude/`'s unrelated GSD tooling, and no prior frontend build config. This was called out explicitly in both CONTEXT.md ("Python/backend conventions do not transfer... `frontend/` is genuinely greenfield") and RESEARCH.md ("No existing frontend conventions to inherit").

| File(s) | Role | Data Flow | Reason |
|---|---|---|---|
| `frontend/src/api/*` (client.ts, scenarios.ts, schema.d.ts) | service/model | request-response, CRUD | No existing TS/JS in repo. Follow RESEARCH.md Pattern 1 (codegen'd typed client via `openapi-typescript` + `openapi-fetch`) verbatim — it is the concrete code to copy from, not a codebase analog. |
| `frontend/src/hooks/*` | hook | CRUD | No existing React hooks in repo. Follow RESEARCH.md Pattern 3 (TanStack Query `useQuery`/`useMutation`) verbatim. |
| `frontend/src/routes/*`, `App.tsx`, `main.tsx` | route/provider | request-response | No existing router config in repo. Follow RESEARCH.md Pattern 2 (`createBrowserRouter` with nested `ScenarioLayout`) verbatim — route table already fixed by `01-UI-SPEC.md`. |
| `frontend/src/components/**` | component | CRUD, transform | No existing React components in repo. shadcn CLI (`npx shadcn add button input select dialog table alert tabs`) generates `components/ui/*` primitives per UI-SPEC; hand-write `layout/` and `scenarios/` components against RESEARCH.md's Recommended Project Structure. |
| `frontend/vite.config.ts`, `frontend/src/lib/*` | config/utility | — | No existing Vite/build config in repo. Follow RESEARCH.md's scaffold command (`npm create vite@latest frontend -- --template react-ts`) + shadcn init output verbatim. |

**Directive for the planner:** for every frontend file above, cite RESEARCH.md's "Architecture Patterns" section (Pattern 1/2/3), "Recommended Project Structure," and "Code Examples" as the pattern source instead of a codebase analog — those sections already contain concrete, ready-to-copy code (imports, client construction, route tables, query/mutation hooks).

## Shared Patterns

### Settings/config extension (backend)
**Source:** `backend/settings.py:30-63` (whole `Settings` dataclass + `default_settings()`)
**Apply to:** `backend/settings.py`'s `cors_origins` addition only (this phase's sole backend config change)
- New fields: dataclass field with type + default, plus a matching `os.environ.get(...)` line inside `default_settings()`.
- Never invent a second config file/mechanism; env-with-sane-default via `default_settings()` is the only config path in this codebase.

### Env-before-import test fixture (backend)
**Source:** `backend/tests/test_api.py:46-58`
**Apply to:** `backend/tests/test_cors.py`
- `monkeypatch.setenv(...)` for every relevant env var, THEN `from api.main import app` inside the test/fixture body (not at module top) — this is required because `Settings`/`CORSMiddleware` resolution happens at import/construction time, and a module-level import would freeze env before the test sets it.

### CORS is resolved once, not per-request (backend)
**Source:** RESEARCH.md "Common Pitfalls" #1, confirmed by reading `backend/api/main.py` (router includes are the only prior precedent for "runs once at import").
**Apply to:** `backend/api/main.py`'s `add_middleware` call — add the one-line comment documenting this is a conscious tradeoff (see Pattern Assignments above), since it's the one place in this codebase where "settings read fresh per call" (the documented promise in `settings.py`'s docstring) does not hold.

### No frontend shared pattern from codebase — use RESEARCH.md directly
Since there is no existing frontend code, "shared patterns" for the frontend files are RESEARCH.md's own cross-cutting sections, not codebase excerpts:
- **Typed client wrapper shape** — RESEARCH.md "Pattern 1" (`src/api/scenarios.ts`'s `listScenarios`/`createScenario` shape: `{ data, error } = await client.METHOD(...)`, throw on `error`) — apply to every future typed-client wrapper function in later phases too.
- **Query key + invalidation shape** — RESEARCH.md "Pattern 3" (`useQuery({ queryKey: [...], queryFn })`, `useMutation({ mutationFn, onSuccess: () => qc.invalidateQueries(...) })`) — apply to every hook this phase and future phases add.
- **Error surfacing copy** — governed by `01-UI-SPEC.md`'s Copywriting Contract (referenced but not re-read here per phase directive to avoid re-reading already-covered ground); RESEARCH.md's Common Pitfalls #5 warns against inventing CORS-vs-network distinction logic — apply the same fixed non-diagnostic banner text to every future error-surfacing component.

## Metadata

**Analog search scope:** `backend/` (settings.py, api/main.py, api/deps.py, tests/test_api.py — all read directly); `frontend/` does not exist yet (confirmed via RESEARCH.md's Environment Availability table: "frontend/ directory — No (does not exist yet)").
**Files scanned:** 4 backend source/test files (all directly relevant; no broader glob/grep needed given the phase's stated small backend footprint — CONTEXT.md explicitly calls `api/main.py`'s CORS insertion "the entire footprint of BE-01").
**Pattern extraction date:** 2026-07-16
