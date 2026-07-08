# Phase 4: Real LLM Provider (free-tier first) + Penalty Calibration - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 10
**Analogs found:** 10 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/llm/gemini.py` | service (provider adapter) | request-response (network) | `backend/llm/stub.py` | role-match (same Protocol, different transport) |
| `backend/llm/translate.py` | utility | transform | `backend/llm/stub.py::_to_override_call` | exact (extraction of existing logic) |
| `backend/llm/base.py` (edit) | service (factory/registry) | request-response | `backend/engine/base.py` (`create_engine` factory) | exact (identical lazy-import registry pattern already in same file) |
| `backend/llm/stub.py` (edit) | service | transform | itself (Phase 2 impl) | exact — minimal edit, last line of `_to_override_call` |
| `backend/api/deps.py` (edit) | provider (FastAPI DI) | request-response | itself (`get_engine`, `get_db`) | exact — same file, same DI idiom |
| `backend/settings.py` (edit) | config | CRUD (env read) | itself (`Settings`/`default_settings`) | exact — same file, same env-override pattern |
| `backend/config/constants.py` (edit) | config | batch (calibration) | itself (existing `*_PENALTY` constants) | exact — value-only edit |
| `backend/scripts/calibrate_penalties.py` | utility (script) | batch | `backend/run.py` (CLI-style sync solve + print) | role-match |
| `backend/tests/test_gemini_provider.py` | test | request-response / event-driven (live) | `backend/tests/test_llm_provider.py` | exact (same provider-seam test shape) + `backend/tests/test_api.py` (dependency_overrides / env fixture idiom for the live/env-gated part) |
| `backend/tests/test_penalty_calibration.py` | test | CRUD (real engine) | `backend/tests/test_engine_overrides.py` | exact (identical real-CP-SAT-engine + hand-built-problem idiom) |
| `backend/pyproject.toml` (edit) | config | — | itself (`[tool.pytest.ini_options]`) | exact |

## Pattern Assignments

### `backend/llm/base.py` (edit — add `"gemini"` branch)

**Analog:** `backend/engine/base.py` (factory pattern already used in this exact file for `"stub"`) and the file's own current content.

**Current factory** (`backend/llm/base.py` lines 23-28):
```python
def create_provider(name: str) -> LLMProvider:
    """Registry of available LLM providers. Add a backend here to make it swappable."""
    if name == "stub":
        from llm.stub import StubLLMProvider
        return StubLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}. Available: ['stub']")
```

**Pattern to copy:** add an `if name == "gemini":` branch with a lazy `from llm.gemini import GeminiLLMProvider` import (mirrors the existing `stub` branch exactly — lazy import keeps `llm/base.py` free of a hard `google-genai` dependency for stub-only CI). Per RESEARCH.md Pattern 3, `create_provider` needs a `settings` kwarg threaded through to construct `GeminiLLMProvider(api_key=..., model=...)`:
```python
def create_provider(name: str, *, settings=None) -> LLMProvider:
    if name == "stub":
        from llm.stub import StubLLMProvider
        return StubLLMProvider()
    if name == "gemini":
        from llm.gemini import GeminiLLMProvider
        return GeminiLLMProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    raise ValueError(f"Unknown LLM provider: {name!r}. Available: ['stub', 'gemini']")
```
Update the module docstring (lines 1-7) — it currently says "The real Claude SDK is Phase 4; only the stub is registered here," which becomes stale.

---

### `backend/llm/translate.py` (new)

**Analog:** `backend/llm/stub.py` lines 105-118 (`_to_override_call`) — this is the function being extracted, not copied wholesale from elsewhere.

**Current logic to extract** (`backend/llm/stub.py` lines 105-118):
```python
def _to_override_call(block: dict) -> OverrideCall:
    """Translate a Claude-faithful tool_use dict to a provider-neutral OverrideCall.
    ...
    """
    tool = block["name"]
    args = block["input"]
    return OverrideCall(
        id=override_id(tool, args),
        tool=tool,
        args=args,
    )
```

**Target shape** (per RESEARCH.md Pattern 1) — same body, generalized signature so both stub and Gemini call it:
```python
from __future__ import annotations
from domain.overrides import OverrideCall, override_id

def to_override_call(tool_name: str, args: dict) -> OverrideCall:
    """Single translation point shared by every LLMProvider implementation."""
    return OverrideCall(id=override_id(tool_name, args), tool=tool_name, args=args)
```

**Import convention:** `from domain.overrides import OverrideCall, override_id` — matches the absolute-import-from-project-root convention already used throughout `llm/stub.py` line 31 (no relative imports in this codebase; confirmed by `conftest.py` sys.path injection).

---

### `backend/llm/stub.py` (edit — D-07 shared-helper refactor)

**Analog:** itself.

**What changes:** only the import (add `from llm.translate import to_override_call`) and the last line of `_to_override_call` (or remove `_to_override_call` entirely and call `to_override_call(tool_use_block["name"], tool_use_block["input"])` at each of the 5 call sites, lines 153, 167, 189, 203, 217). The Claude-shaped `tool_use_block` dict construction (lines 147-152, 161-166, 183-188, 197-202, 211-216) stays exactly as-is — it is internal/local to the stub, never crossing the Protocol boundary, and existing tests (`test_llm_provider.py`) only assert on the resulting `OverrideCall`'s public fields (`tool`, `args`, `id`), never on the internal dict shape. Confirmed no test imports `_to_override_call` directly (checked `test_llm_provider.py` and `test_engine_overrides.py` — RESEARCH.md Open Question 3 already flagged this; grep below confirms no other reference).

```bash
grep -rn "_to_override_call" backend/tests/
# (no hits found — safe to refactor)
```

The `_clarification` sentinel branch (lines 220-230) does **not** go through `_to_override_call`/`to_override_call` today (it builds an `OverrideCall` directly) — leave that branch untouched.

---

### `backend/llm/gemini.py` (new)

**Analog:** `backend/llm/stub.py` for the `LLMProvider` shape (class with `name` attr + two methods), and RESEARCH.md Pattern 2/Code Examples for the SDK-specific body (already vetted against Context7 docs — use verbatim as the base implementation).

**Protocol shape to match** (from `backend/llm/base.py` lines 15-20):
```python
class LLMProvider(Protocol):
    def parse_constraints(self, text: str) -> list[OverrideCall]: ...
    def generate_insights(self, summary: dict) -> str: ...

    @property
    def name(self) -> str: ...
```

**Stub's `name` convention** (`backend/llm/stub.py` line 124): `name = "stub"` — a plain class attribute (not a `@property`), since Protocol's `@property` is structurally satisfied by a class attribute too. Gemini should use `name = "gemini"` identically.

**Core pattern** — copy RESEARCH.md's Pattern 2 code block verbatim as the starting implementation (client construction, `_TOOL_SCHEMAS` as `types.FunctionDeclaration` list, forced/`AUTO`-mode `generate_content` call, `to_override_call(fc.name, dict(fc.args))` translation loop, plain-text `generate_content` for `generate_insights`). Import `to_override_call` from the new `llm/translate.py`, not a locally-duplicated helper.

**Error handling analog:** no existing LLM-layer example (stub has no I/O to fail); follow the project's general convention from `backend/services/insight_service.py`'s provider-exception wrapping style noted in RESEARCH.md's Security Domain section — wrap SDK exceptions generically without interpolating the API key into any message.

---

### `backend/api/deps.py` (edit — env-driven provider selection, D-04)

**Analog:** itself — `get_engine` (lines 31-32) and `get_settings`/`get_db` (lines 18-28) are the exact DI idioms to mirror.

**Current** (`backend/api/deps.py` lines 35-36):
```python
def get_llm_provider() -> LLMProvider:
    return create_provider("stub")
```

**Pattern to copy** (mirrors `get_engine`'s `Depends`-free simplicity is broken here since Gemini needs settings — instead mirror `get_db`'s `Depends(get_settings)` injection, lines 22-23):
```python
def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return create_provider(settings.llm_provider, settings=settings)
```
This requires `Settings` already imported at line 14 (`from settings import Settings, default_settings`) — no new import needed beyond what's already at the top of the file.

---

### `backend/settings.py` (edit — extend `Settings`, D-04/D-05)

**Analog:** itself — the existing `db_path`/`data_dir` fields and `default_settings()` are the exact pattern to replicate for the three new fields.

**Current** (`backend/settings.py` full file, lines 16-26):
```python
@dataclass(frozen=True)
class Settings:
    db_path: str       # SQLite file
    data_dir: str      # directory holding input fixtures (*.json)


def default_settings() -> Settings:
    """Read settings fresh each call so env overrides apply at request time."""
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    return Settings(db_path=db_path, data_dir=data_dir)
```

**Pattern to copy** — identical `os.environ.get(NAME, default)` idiom, three more fields added to the frozen dataclass and the same constructor call:
```python
@dataclass(frozen=True)
class Settings:
    db_path: str
    data_dir: str
    llm_provider: str        # NEW — "stub" (default) | "gemini"
    llm_model: str           # NEW — default "gemini-2.5-flash"
    llm_api_key: str | None  # NEW — from GEMINI_API_KEY; None for stub


def default_settings() -> Settings:
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    llm_provider = os.environ.get("LLM_PROVIDER", "stub")
    llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    llm_api_key = os.environ.get("GEMINI_API_KEY")
    return Settings(db_path=db_path, data_dir=data_dir,
                     llm_provider=llm_provider, llm_model=llm_model, llm_api_key=llm_api_key)
```
Note module docstring line 1 ("Runtime settings — filesystem paths...") will need a light rewording since `Settings` is no longer filesystem-only.

---

### `backend/config/constants.py` (edit — calibrated penalty values, D-08)

**Analog:** itself — the four constants already exist with full derivation comments (lines 34-58); only the integer literals change, comments should be updated to state the empirically-derived value replaced the placeholder (referencing the calibration script).

**Current values to replace** (lines 41, 46, 52, 58):
```python
MIN_WORKERS_PENALTY: int = 100_000
LOCK_SHIFT_PENALTY: int = 100_000
EXCLUDE_WORKER_PENALTY: int = 50_000
MAX_HOURS_PENALTY: int = 100_000
```
Keep the exact same comment style (explain *why* the magnitude was chosen relative to wage-cost order of magnitude, per the existing convention) — this project's "Comments" convention (CLAUDE.md) requires explaining "why," which these constants already model well; extend rather than replace that pattern.

---

### `backend/scripts/calibrate_penalties.py` (new)

**Analog:** `backend/run.py` (CLI-style script — sync solve, `print()` output, no logging framework per CLAUDE.md "Logging" convention: "CLI: Use `print()` for output").

**Pattern to copy:** RESEARCH.md's "Calibration harness skeleton" code block (already written against this project's real `load_problem` / `create_engine` / `SolverConfig` / `config.constants` surface) — use verbatim as the starting script. Follow `run.py`'s `if __name__ == "__main__":` entry-point convention and its `print()`-based reporting (no logger).

---

### `backend/tests/test_gemini_provider.py` (new)

**Analog:** `backend/tests/test_llm_provider.py` (unit-test shape/assertions for the non-live parts) + `backend/tests/test_api.py` (env-var + fixture-scoped setup idiom for the live/gated part).

**Non-live unit test pattern** (mirror `test_llm_provider.py` lines 23-32 style — `from llm.base import create_provider` inline import inside each test function, matching this file's convention throughout):
```python
def test_create_provider_gemini_returns_gemini_llm_provider():
    from llm.base import create_provider
    from settings import default_settings
    p = create_provider("gemini", settings=default_settings())
    assert p.name == "gemini"
```
For a network-free unit test of `parse_constraints`/`generate_insights`, fake `genai.Client` (e.g. monkeypatch `GeminiLLMProvider._client` or inject a stub client) — no existing analog for mocking a vendor SDK client in this codebase (new pattern); keep it minimal and consistent with `StubEngine` in `test_api.py` (lines 27-43) as the nearest "hand-built fake replacing a real dependency" idiom.

**Live/gated test pattern** — copy RESEARCH.md's "Registering the `live` pytest marker" code block verbatim (lines showing `_HAS_KEY`, `@pytest.mark.live`, `@pytest.mark.skipif`), and mirror `test_api.py`'s `monkeypatch.setenv(...)` fixture style (lines 47-49) if the live test needs env manipulation beyond reading `GEMINI_API_KEY` directly.

---

### `backend/tests/test_penalty_calibration.py` (new)

**Analog:** `backend/tests/test_engine_overrides.py` — identical idiom: real `create_engine("cpsat")`, `SolverConfig(time_limit_s=..., overrides=[...])`, assertions on `result.status in ("OPTIMAL", "FEASIBLE")` and metric deltas vs. a baseline solve. Difference: this file must load the **committed full-week fixture** (`data/sample_tiny_input.json` via `ingest.input_adapter.load_problem`) instead of the hand-built tiny problems in `test_engine_overrides.py` (RESEARCH.md Pitfall 5 — do not reuse the tiny hand-built problems for calibration ground truth).

**Baseline + override comparison pattern** (`backend/tests/test_engine_overrides.py` lines 108-120, `test_no_regression_empty_overrides`):
```python
def test_no_regression_empty_overrides():
    problem = _make_problem(n_members=2, demand_volume=10.0)
    engine = create_engine("cpsat")
    baseline = engine.solve(problem, SolverConfig(time_limit_s=10))
    result = engine.solve(problem, SolverConfig(time_limit_s=10, overrides=[]))
    assert result.status == baseline.status
    assert abs((result.metrics.total_cost or 0.0) - (baseline.metrics.total_cost or 0.0)) < 0.01
```
Adapt this shape for: (1) satisfiable-override-honored assertion (mirror `test_scale_demand_honored`, lines 127-150 — compare bodies/hours before vs. after), (2) unsatisfiable-override-degrades-gracefully assertion (new — assert `result.status in ("OPTIMAL","FEASIBLE")` AND a bounded cost-delta check per Pitfall 4, e.g. `total_cost` doesn't jump more than some small multiple of baseline), (3) folded WR-05 real-engine degeneracy test — use the same fixture-load + `create_engine("cpsat").solve(...)` pattern, then assert `result.warnings` (or equivalent field on `SolveResult`) is non-empty, contrasting with the existing mirrored-loop-only unit test in `test_engine_degenerate.py`.

Use a bounded `time_limit_s` (30-60s per RESEARCH.md's Timing note) given the full-week fixture's ~2min round-2-optimal solve time.

---

### `backend/pyproject.toml` (edit — register `live` marker)

**Analog:** itself, `[tool.pytest.ini_options]` (lines 20-21).

**Current:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Pattern to copy** — copy RESEARCH.md's exact TOML block:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "live: exercises a real network-backed LLM provider; excluded by default (run with `pytest -m live`)",
]
addopts = "-m \"not live\""
```

Also add the new runtime dependency to `[project] dependencies` (line 6-11 currently lists `ortools`, `pandas`, `fastapi`, `uvicorn[standard]`):
```toml
dependencies = [
    "ortools==9.11.4210",
    "pandas",
    "fastapi",
    "uvicorn[standard]",
    "google-genai",
]
```
(Per RESEARCH.md Package Legitimacy Audit — insert a `checkpoint:human-verify` task immediately before `uv add google-genai` in the plan; the package is flagged `SUS` by the automated legitimacy tool despite being confirmed legitimate.)

## Shared Patterns

### Lazy-import provider registry
**Source:** `backend/llm/base.py` lines 23-28 (existing), mirrored from `backend/engine/base.py`'s `create_engine`
**Apply to:** `llm/base.py`'s new `"gemini"` branch — keeps `google-genai` import out of the module import graph for stub-only CI runs.

### Fresh-per-call `Settings` from env
**Source:** `backend/settings.py` lines 22-26 (`default_settings()`)
**Apply to:** the three new `Settings` fields (`llm_provider`, `llm_model`, `llm_api_key`) and `api/deps.py`'s `get_settings()` — no caching, so `monkeypatch.setenv` in tests (as `test_api.py` already does at lines 47-49) works without app-restart tricks.

### Provider-neutral translation boundary (D-08/D-09 upheld)
**Source:** `backend/llm/stub.py` lines 8-12 (module docstring) + `_to_override_call` (lines 105-118), now generalized to `llm/translate.py::to_override_call`
**Apply to:** both `StubLLMProvider` and `GeminiLLMProvider` — no vendor payload (Claude-shaped `tool_use` dict, Gemini `FunctionCall` object) may cross `LLMProvider`; only `list[OverrideCall]` may be returned from `parse_constraints`.

### Real-engine + fixture-driven regression test idiom
**Source:** `backend/tests/test_engine_overrides.py` (whole file — `create_engine("cpsat")`, `SolverConfig(overrides=[...])`, baseline-vs-override comparison)
**Apply to:** `test_penalty_calibration.py` — same idiom, but loading the full-week fixture via `ingest.input_adapter.load_problem("data/sample_tiny_input.json")` instead of hand-built problems.

### pytest marker + env-gated skip for network-dependent tests
**Source:** RESEARCH.md Code Examples ("Registering the `live` pytest marker") — no existing analog in this codebase (first live/network test introduced this phase)
**Apply to:** `test_gemini_provider.py`'s one `@pytest.mark.live` test + `pyproject.toml`'s `addopts`.

### DI dependency mirroring `get_db`/`get_engine`
**Source:** `backend/api/deps.py` lines 18-32 (whole file)
**Apply to:** `get_llm_provider`'s new `Depends(get_settings)` signature.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/llm/gemini.py` (SDK client + function-calling body specifically) | service | request-response (network) | No existing code in this repo calls any external network API/SDK — RESEARCH.md's Context7-sourced Code Examples are the primary source for this file's SDK-specific body, not a codebase analog |
| Fake/mock `genai.Client` for unit-testing `GeminiLLMProvider` without network | test helper | request-response (mocked) | No prior pattern for mocking a vendor SDK client in this codebase; nearest conceptual analog is `StubEngine` in `test_api.py` (hand-built fake standing in for a real dependency via DI override), reused as inspiration only |

## Metadata

**Analog search scope:** `backend/llm/`, `backend/api/`, `backend/engine/`, `backend/config/`, `backend/tests/`, `backend/settings.py`, `backend/run.py`, `backend/pyproject.toml`
**Files scanned:** `llm/base.py`, `llm/stub.py`, `api/deps.py`, `settings.py`, `config/constants.py`, `engine/cpsat/builder.py` (grep only), `tests/test_api.py`, `tests/test_llm_provider.py`, `tests/test_engine_overrides.py`, `pyproject.toml`
**Pattern extraction date:** 2026-07-06
