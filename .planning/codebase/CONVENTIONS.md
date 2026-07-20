# Coding Conventions

**Analysis Date:** 2026-07-20

This document covers conventions for both the **backend** (Python, `backend/`) and **frontend** (React + TypeScript, `frontend/`) parts of the RosterAI codebase.

---

## BACKEND (Python)

### Naming Patterns

**Files:**
- `snake_case` for all modules: `run_service.py`, `input_adapter.py`, `scenarios.py`
- Router files grouped in subdirectories: `api/routers/scenarios.py`, `api/routers/runs.py`
- Config and constant files: `settings.py`, `constants.py`

**Functions:**
- `snake_case` for all function names: `create_scenario()`, `load_problem()`, `set_running()`
- Private functions prefixed with underscore: `_now()`, `_rows()`, `_to_float()`, `_dict()`, `_clip()`
- Async context managers use `@asynccontextmanager` decorator and lowercase names: `lifespan()`

**Variables:**
- `snake_case` for all variables and attributes: `scenario_id`, `contact_id`, `time_limit_s`
- Dictionary keys use `snake_case`: `"time_limit_s"`, `"solver_status"`
- Loop variables use short names: `i`, `r`, `s`, `e`, `m` for meaningful context

**Classes:**
- `PascalCase` for all classes: `SchedulingProblem`, `RunOut`, `Member`, `Task`, `Window`
- `PascalCase` for enum types: `WindowKind`, `DemandFamily`

**Constants:**
- `UPPERCASE` with underscores: `DEFAULT_TASK_RATE`, `MAX_ITERATIONS`

**Type Hints:**
- Modern Python 3.10+ syntax with `|` for unions (not `Union[]`): `float | None`, `str | None`, `dict[str, int]`
- Always present on function parameters and return types
- Example from `domain/types.py`:
  ```python
  def rate_for(self, task_id: str) -> float | None:
  ```

### Code Style

**Formatting:**
- No explicit formatter configured; follows PEP 8 implicitly
- 100-character line length observed in multi-line constructs
- Proper spacing around operators (`=`, `==`, `+`) and after commas

**Linting:**
- No explicit linter configured (`.pylintrc`, `ruff.toml` absent)
- Code adheres to PEP 8 via convention

### Import Organization

**Order:**
1. `from __future__ import annotations` (always first)
2. Standard library: `import os`, `import json`, `import sqlite3`
3. Third-party: `from fastapi import`, `from google.genai import`
4. Local absolute imports: `from domain.types import`, `from api.schemas import`

**Pattern:**
- Absolute imports from project root (not relative): `from domain.types import Member` not `from ..domain.types import`
- No path aliases configured; `conftest.py` adds backend directory to `sys.path` so absolute imports resolve
- Example from `api/routers/scenarios.py`:
  ```python
  from domain.types import Member
  from services import scenario_service
  ```

### Error Handling

**API Layer (routers):**
- Raise `HTTPException` with status codes and detail messages
- Example from `api/routers/scenarios.py`:
  ```python
  if s is None:
      raise HTTPException(status_code=404, detail="Scenario not found")
  ```

**Service Layer:**
- Raise domain exceptions; let caller (router/parent) handle with `HTTPException`
- Exceptions propagate upward; caller (API) determines HTTP response

**Background Tasks (worker threads):**
- Catch **all** exceptions: `except Exception as exc: # noqa: BLE001`
- Persist error string to database (`run.error` field), never crash worker
- Example from `services/run_service.py:97`:
  ```python
  except Exception as exc:  # noqa: BLE001 - persist any failure as run state
      repo.set_failed(run_id, f"{type(exc).__name__}: {exc}", _now())
  ```

**Data Validation:**
- Use Pydantic models (FastAPI schemas) for request validation
- FastAPI automatically validates and returns 422 on validation errors
- Example: `ScenarioCreate` schema validates `name`, `fixture`, `time_limit_s`

### Logging

- **CLI operations** (`run.py`): Use `print()` for output
- **API routes**: No logging framework configured; errors persisted to database via service layer
- **Background tasks**: No logging; exceptions caught and stored in `runs.error` column
- **Test setup** (`conftest.py`): Uses `dotenv_values()` to read local `.env` without overriding test defaults

### Comments

**Module-level Docstrings:**
- Always present; explain module purpose, usage, or design decisions
- Example from `run_service.py`:
  ```python
  """Run use-cases: create a run row, then execute the solve in a worker thread.
  
  The solve is CPU-heavy and long (seconds to minutes), so it must never run on
  the event loop. We submit it to a single-worker pool...
  """
  ```

**Function Docstrings:**
- Minimal; rely on type hints and name clarity
- Include if docstring adds value beyond the signature

**Inline Comments:**
- Explain "why", not "what"
- Example from `api/main.py:28-34`:
  ```python
  # NOTE: CORS origins are resolved once here, at process/import time — unlike
  # every other Settings field, which default_settings() re-reads fresh on every
  # call so env overrides apply at request time...
  ```

### Function Design

**Signatures:**
- Type hints on all parameters: `def create_scenario(conn: sqlite3.Connection, name: str, fixture: str)`
- Default values at the end: `time_limit_s: float = 60.0`
- Return type always annotated: `-> dict`, `-> Optional[dict]`, `-> SolveResult`

**Body:**
- Return early for error cases
- Single exit path preferred but not enforced

### Module Design

**Exports:**
- All public names exported (no explicit `__all__` lists)
- Example: `engine/base.py` exports `SchedulerEngine`, `SolverConfig`, `create_engine()`

**Dataclasses:**
- Immutable types use `@dataclass(frozen=True)` (hashable, thread-safe)
- Mutable types use `@dataclass` with `field(default_factory=list)` for mutable defaults
- Example from `domain/types.py`:
  ```python
  @dataclass(frozen=True)
  class Window:
      id: str
      start_h: float
      end_h: float
      kind: WindowKind
  ```

**Protocols:**
- Use `typing.Protocol` for abstract interfaces (pluggable backends)
- Example: `engine/base.py:18` defines `SchedulerEngine` protocol; `engine/cpsat/engine.py:22` implements

**Repository Pattern:**
- Thin data-access layer wrapping SQLite queries
- Returns `sqlite3.Row` objects (dict-like)
- Example: `store/repositories.py:ScenarioRepo.get(scenario_id)`

**Service Layer:**
- Orchestrates business logic; operates on repos
- Example: `services/scenario_service.py` manages scenario CRUD and fixture loading

**Router Layer:**
- FastAPI endpoints; use dependency injection for DB connections and engine
- Example: `api/routers/scenarios.py:create_scenario()` uses `Depends(get_db)`, `Depends(get_settings)`

---

## FRONTEND (React + TypeScript)

### Naming Patterns

**Files:**
- React components: `PascalCase.tsx` (e.g., `ScenarioHeader.tsx`, `ConstraintInput.tsx`)
- Hooks: `camelCase`, prefixed `use`: `useScenarios.ts`, `useApplyConstraint.ts`
- Utilities/libraries: `camelCase.ts` (e.g., `errors.ts`, `formatShiftWindow.ts`)
- Test files: co-located with implementation: `Component.test.tsx`, `lib.test.ts`

**Functions and Variables:**
- `camelCase` for all function names and variables: `getErrorStatus()`, `scenarioId`, `isLoading`
- Abbreviated loop variables: `r` for row, `i` for index

**React Components:**
- `PascalCase` component names: `ScenarioHeader`, `ConstraintInput`
- Export as named exports: `export function ScenarioHeader({ ... })`
- Props as destructured object parameter with inline type annotation

**Hooks:**
- `camelCase`, prefixed `use`: `useScenarios()`, `useApplyConstraint()`
- Thin TanStack Query wrappers: `useScenarios()` wraps `listScenarios()`

**Constants:**
- `UPPERCASE` or `camelCase` depending on scope
- Example: `MAX_LENGTH = 2000`, `COUNTER_THRESHOLD = 1800`

**Type Hints:**
- TypeScript strict mode enabled (`noUnusedLocals`, `noUnusedParameters`)
- Union types with `|`: `string | null`, `number | undefined`
- Derived types from generated OpenAPI schema preferred over hand-authored interfaces
- Example from `src/api/scenarios.ts`:
  ```typescript
  type CreateScenarioBody = paths["/scenarios"]["post"]["requestBody"]["content"]["application/json"];
  ```

### Code Style

**Formatting:**
- No explicit formatter configured (likely Prettier defaults); follows eslint/oxlint rules
- Consistent spacing around operators and after commas
- Multi-line JSX fragments use readable indentation

**Linting:**
- `oxlint` (Rust-based linter)
- Config: `.oxlintrc.json` enables React and TypeScript plugins
- Rules enforced:
  - `react/rules-of-hooks`: error (enforce Hook rules)
  - `react/only-export-components`: warn (components should be default/named exports)

**Strict Compiler Flags:**
- `noUnusedLocals`: true — unused variables error
- `noUnusedParameters`: true — unused parameters error
- `noFallthroughCasesInSwitch`: true — enforce default case

### Import Organization

**Order:**
1. React and core libraries: `import * as React from "react"`
2. Third-party UI/utility: `import { Button } from "@shadcn/ui"`, `import { useQuery } from "@tanstack/react-query"`
3. Project code: `import { useScenario } from "@/hooks"`
4. Types: `import type { ComponentProps }` or co-located with imports

**Path Aliases:**
- `@/*` resolves to `./src/*` (configured in `vite.config.ts` and `tsconfig.json`)
- All imports use absolute `@` alias: `@/api/scenarios`, `@/hooks/useScenarios`, `@/components/ui/button`

**Imports from Generated Types:**
- OpenAPI schema imported as: `import type { paths, components } from "@/api/schema"`
- Derived types: `type CreateScenarioBody = paths["/scenarios"]["post"]["requestBody"]["content"]["application/json"]`

### Error Handling

**API Layer (`src/api/*.ts`):**
- Throw error objects with HTTP status attached: `throw { status: response.status, ...error }`
- Example from `src/api/scenarios.ts:48`:
  ```typescript
  if (error) {
    throw { status: response.status, ...error };
  }
  ```

**Components and Hooks:**
- TanStack Query surfaces thrown errors as `query.error`/`mutation.error` (typed `unknown`)
- Use `getErrorStatus(error)` helper to safely extract status: `const status = getErrorStatus(error)`
- Status discrimination drives branching (404 → terminal view, 503 → provider-down banner)

**Helper Functions:**
- Example `src/lib/errors.ts`: Centralized `getErrorStatus()` prevents repeated type casts
  ```typescript
  export function getErrorStatus(error: unknown): number | undefined {
    if (typeof error !== "object" || error === null) return undefined;
    const status = (error as { status?: unknown }).status;
    return typeof status === "number" ? status : undefined;
  }
  ```

### Comments

**Module-level Docstrings:**
- Always present; explain purpose and reference design docs or tickets
- Example from `src/components/editor/ConstraintInput.tsx:1-22`:
  ```typescript
  /**
   * CONS-01 constraint input box (UI-SPEC E4) — Textarea + "Apply Constraint",
   * status-branching for CONS-05 (503-vs-422, keyed strictly off
   * `response.status`, never error message text)...
   */
  ```

**Inline Comments:**
- Explain "why", cite relevant design tickets
- Example from `src/components/editor/ConstraintInput.tsx:72-76`:
  ```typescript
  // Input-preservation rule (generalizes CONS-04): clear ONLY on a
  // genuine full apply with nothing rejected and no pending
  // clarification...
  ```

### React Patterns

**Controlled Components:**
- State-driven forms with `useState`, clear on success conditions (not always on HTTP 200)
- Example from `src/components/editor/ConstraintInput.tsx:70-75`:
  ```typescript
  applyConstraint.mutate(text, {
    onSuccess: (data) => {
      // Only clear if the response indicates full success (no rejects/clarifications)
      if (data.applied.length > 0 && data.rejected.length === 0 && data.clarifications.length === 0) {
        setText("");
      }
    },
  });
  ```

**Custom Hooks:**
- Thin TanStack Query wrappers; business logic belongs in components
- Example `src/hooks/useScenarios.ts`:
  ```typescript
  export function useScenarios() {
    return useQuery({
      queryKey: ["scenarios"],
      queryFn: listScenarios,
    });
  }
  ```

**Dependencies and Injection:**
- TanStack Query `enabled` gates conditional queries
- Props passed to components for flexibility; dependency overrides in tests

**Router Integration:**
- Use `react-router` for navigation; real route tests use `createMemoryRouter`
- Example from `src/components/editor/ScenarioHeader.test.tsx:35-45`:
  ```typescript
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId", Component: () => <ScenarioHeader ... /> }],
    { initialEntries: ["/scenarios/abc"] },
  );
  ```

### Module Design

**API Layer (`src/api/`):**
- Thin typed wrappers over `openapi-fetch` client
- No hand-authored interfaces; derive from generated OpenAPI schema
- Every endpoint request/response shape comes from `./schema.d.ts`

**Hooks (`src/hooks/`):**
- TanStack Query wrappers; no business logic
- Thin pass-through of query configuration
- Query keys are cross-plan contracts (e.g., `["scenarios"]` invalidated on creation)

**Utilities (`src/lib/`):**
- Pure functions: `getErrorStatus()`, `formatTimestamp()`, `formatShiftWindow()`
- Type safety via TypeScript; centralize repeated type casts

**Components (`src/components/`):**
- Organize by feature/domain: `layout/`, `editor/`, `results/`
- Props interface inline or as dedicated type
- Export as named exports (not default)

---

## Cross-Codebase Patterns

### Type Safety Philosophy

**Backend (Python):**
- Static type hints on all functions (PEP 484)
- Pydantic models for validation
- Strict-by-design (exceptions throw, don't return error codes)

**Frontend (TypeScript):**
- Strict TypeScript compiler flags
- Types derived from generated OpenAPI schema (source of truth)
- Hand-authored types only when schema generation cannot provide them

### Error Handling Philosophy

**Backend:** Exceptions propagate; caller decides HTTP response
**Frontend:** Errors thrown with status attached; components discriminate on status codes

### Documentation Style

**Both:** Module-level docstrings explain "why", not "what". Reference design docs and tickets.

Example (backend):
```python
"""Run use-cases: create a run row, then execute the solve in a worker thread.

The solve is CPU-heavy and long (seconds to minutes), so it must never run on
the event loop...
"""
```

Example (frontend):
```typescript
/**
 * CONS-01 constraint input box (UI-SPEC E4) — Textarea + "Apply Constraint",
 * status-branching for CONS-05 (503-vs-422, keyed strictly off
 * `response.status`, never error message text)...
 */
```

---

*Convention analysis: 2026-07-20*
