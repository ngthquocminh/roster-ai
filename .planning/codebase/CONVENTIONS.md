# Coding Conventions

**Analysis Date:** 2026-06-26

## Naming Patterns

**Files:**
- Snake_case for all Python modules: `input_adapter.py`, `run_service.py`, `scenarios.py`
- Router files grouped in subdirectories: `api/routers/scenarios.py`, `api/routers/runs.py`
- Config files and settings: `settings.py`, `constants.py`

**Functions:**
- Snake_case for all functions: `create_scenario()`, `load_problem()`, `set_running()`
- Private functions prefixed with underscore: `_now()`, `_rows()`, `_to_float()`, `_dict()`, `_clip()`
- Async context managers: `lifespan()` defined with `@asynccontextmanager` decorator

**Variables:**
- Snake_case for all variables: `scenario_id`, `contact_id`, `time_limit_s`
- Dictionary keys use snake_case: `"time_limit_s"`, `"solver_status"`
- Constants use UPPERCASE: `DEFAULT_TASK_RATE` (in `config/constants.py`)
- Loop variables use short names: `i`, `r`, `s`, `e`, `m` for meaningful context

**Types:**
- PascalCase for all classes: `ScenarioCreate`, `RunOut`, `SchedulingProblem`, `Member`
- Enums use PascalCase: `WindowKind`, `DemandFamily`
- Type hints use modern Python 3.10+ syntax with `|` for unions: `float | None`, `str | None`

## Code Style

**Formatting:**
- No explicit formatter configured (likely PEP 8 default)
- 100-character line length observed in multi-line constructs
- Proper spacing around operators and after commas
- Example from `api/schemas.py`:
  ```python
  class ScenarioCreate(BaseModel):
      name: str = Field(min_length=1)
      fixture: str = Field(min_length=1)
      time_limit_s: float = Field(default=60.0, gt=0)
  ```

**Linting:**
- No explicit linter configured (.eslintrc, .pylintrc, ruff.toml, etc. absent)
- Code follows PEP 8 implicitly via conventions observed:
  - Two blank lines between top-level definitions
  - One blank line between methods
  - Imports properly organized

## Import Organization

**Order:**
1. Future imports: `from __future__ import annotations` (used in every file)
2. Standard library: `import os`, `import sqlite3`, `import json`, `from datetime import datetime`
3. Third-party: `from fastapi import FastAPI`, `from pydantic import BaseModel`, `from ortools.sat.python import cp_model`
4. Local project: `from domain.types import Member`, `from api.deps import get_db`

**Example from `api/routers/scenarios.py`:**
```python
from __future__ import annotations

import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_settings
from api.schemas import ScenarioCreate, ScenarioOut
```

**Path Aliases:**
- No path aliases configured; absolute imports from project root (`from domain.types import...` not relative `from ..domain.types import...`)
- Imports work because `conftest.py` adds backend directory to sys.path

## Error Handling

**Patterns:**
- **API endpoints:** Use `HTTPException` with status codes and detail messages
  ```python
  # from api/routers/scenarios.py
  if not os.path.isfile(os.path.join(settings.data_dir, body.fixture)):
      raise HTTPException(status_code=400, detail=f"Unknown fixture: {body.fixture!r}")
  ```
  
- **Services:** Raise exceptions; let caller (router/parent) handle with HTTPException
  
- **Background tasks:** Catch all exceptions (`except Exception as exc: # noqa: BLE001`) and persist to database
  ```python
  # from services/run_service.py
  except Exception as exc:  # noqa: BLE001 - persist any failure as run state
      repo.set_failed(run_id, f"{type(exc).__name__}: {exc}", _now())
  ```

- **Data validation:** Use Pydantic models (FastAPI schemas) for request validation
  - `ScenarioCreate`, `RunOut` in `api/schemas.py`

## Logging

**Framework:** None explicitly configured (print statements only for CLI)

**Patterns:**
- **CLI:** Use `print()` for output (see `run.py`)
  ```python
  print(f"Loading {path} ...")
  print(f"Solved with '{engine.name}' in {time.time() - t:.1f}s  -> status={result.status}")
  ```
  
- **API:** No logging; errors persisted to database via service layer
- **Background tasks:** No logging; exceptions caught and stored in `runs.error` column

## Comments

**When to Comment:**
- Module-level docstrings always present: explain module purpose, usage, or design decisions
  ```python
  """ShiftMind backend API.
  
  Run from backend/:
      uv run uvicorn api.main:app --reload
  """
  ```
  
- Function docstrings: minimal; rely on type hints and name clarity
- Inline comments: explain "why", not "what"
  ```python
  # WAL mode so a background solve thread can write run status while request threads read
  ```

**JSDoc/TSDoc:**
- Not used; this is Python, not TypeScript

## Function Design

**Size:** Most functions 10-30 lines; larger functions broken into logical blocks

**Parameters:**
- Type hints on all parameters: `def create_scenario(conn: sqlite3.Connection, name: str, fixture: str, ...)`
- Default values at the end: `time_limit_s: float = 60.0`
- Use keyword-only arguments after `*` when appropriate (not common in this codebase)

**Return Values:**
- Always annotated: `-> dict`, `-> Optional[dict]`, `-> SolveResult`
- Return early for error cases
- Example from `domain/types.py`:
  ```python
  def rate_for(self, task_id: str) -> float | None:
      for q in self.qualifications:
          if q.task_id == task_id:
              return q.rate
      return None
  ```

## Module Design

**Exports:**
- Modules export classes, functions, and constants used by other modules
- No explicit `__all__` lists (all public names exported)
- Example: `engine/base.py` exports `SchedulerEngine`, `SolverConfig`, `create_engine()`

**Barrel Files:**
- Minimal use; most `__init__.py` files empty or minimal
- `api/__init__.py`, `domain/__init__.py` are empty
- `engine/__init__.py` is empty

**Common Patterns:**
- **Dataclasses:** Use `@dataclass` or `@dataclass(frozen=True)` for immutable types
  ```python
  @dataclass(frozen=True)
  class Window:
      id: str
      start_h: float
      end_h: float
      kind: WindowKind
  ```

- **Protocols:** Use `typing.Protocol` for engine abstraction
  ```python
  class SchedulerEngine(Protocol):
      def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult: ...
      @property
      def name(self) -> str: ...
  ```

- **Pydantic models:** Use for API request/response validation
  ```python
  class ScenarioCreate(BaseModel):
      name: str = Field(min_length=1)
  ```

- **Repository pattern:** Thin data-access layer wrapping SQLite
  ```python
  class ScenarioRepo:
      def __init__(self, conn: sqlite3.Connection):
          self.conn = conn
      def get(self, scenario_id: str) -> Optional[dict]:
          return _dict(self.conn.execute(...).fetchone())
  ```

- **Service layer:** Business logic; operates on repos
  ```python
  def create_scenario(conn: sqlite3.Connection, name: str, ...) -> dict:
      sid = uuid.uuid4().hex
      repo = ScenarioRepo(conn)
      repo.insert({...})
      conn.commit()
      return repo.get(sid)
  ```

- **Router layer:** FastAPI endpoints; use dependency injection
  ```python
  @router.post("", response_model=ScenarioOut, status_code=201)
  def create_scenario(
      body: ScenarioCreate,
      conn: sqlite3.Connection = Depends(get_db),
      settings: Settings = Depends(get_settings),
  ) -> dict:
  ```

---

*Convention analysis: 2026-06-26*
