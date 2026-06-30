# Phase 03: On-Demand Insight Reports - Research

**Researched:** 2026-06-30
**Domain:** FastAPI request handling (sync threadpool), provider-seam extension, SQLite schema evolution, post-hoc text grounding
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** GET lazy-generate + cache on a single endpoint `GET /runs/{run_id}/insights` (mirrors `GET /runs/{run_id}/result`). First GET on a COMPLETED run generates + writes `runs.insight_json`; later GETs return the cache. No separate POST-to-generate step.
- **D-02:** Generation runs **off the event loop on a worker thread, but the GET blocks and returns the report in the same response** (no polling, no 202, no new insight-status field). Do **NOT** reuse the single-worker solve `ThreadPoolExecutor` in `run_service.py` (it serializes work behind CPU-bound solves). Thread path is a research/planner item.
- **D-03:** Report structure = short prose summary (1–2 sentences) + structured metric highlights (labeled lines/bullets). Not free-form prose, not fully-sectioned headings.
- **D-04:** Length/tone = concise operations-brief — a few sentences + a handful of metric highlights.
- **D-05:** Report MUST always cover all four of: (1) Coverage per-function served-vs-required hours + pct (`metrics.coverage_by_function`); (2) Unmet hours + total cost (`metrics.total_unmet_hours`, `metrics.total_cost`); (3) Degenerate-family warnings — narrate `result.warnings[]` honestly (the concrete mechanism behind INS-03's "no generic 'coverage was adequate'" rule); (4) Applied overrides in effect (from the scenario's `overrides` JSON at solve time).
- **D-06:** Post-hoc number-verification guard, provider-agnostic. After generation, extract numerics from the report text and assert each appears in the run's metrics JSON; reject/flag if any number is not found. Guard lives at the seam (protects Phase-4 real Claude too). Failure → treat as generation failure → D-08 5xx path, nothing cached.
- **D-07:** Not-ready (run not COMPLETED) → **200 with a not-ready body** (`ready=false` + reason/current-status). **Deliberate divergence** from `GET /runs/{id}/result` (which returns 409). Downstream MUST NOT "correct" this to 409.
- **D-08:** Provider failure during generation → **5xx (502/503)** with error detail; run stays COMPLETED, `result_json` untouched, **nothing cached** (a later retry can succeed). Insights eligible for **COMPLETED runs only**.
- **D-09:** `LLMProvider` Protocol gains a second operation `generate_insights` alongside `parse_constraints` (LLM-01). `StubLLMProvider` implements it **deterministically, no external I/O** (TEST-01). Reuse the existing `get_llm_provider` dependency seam (LLM-03).
- **D-10:** New `runs.insight_json TEXT` column holds the cached report (INS-04). No migrations framework — planner adds the column to the fresh-DB DDL string AND an `ALTER TABLE … ADD COLUMN` guard for existing DBs. Runs are immutable once COMPLETED, so no cache invalidation.

### Claude's Discretion
- Exact prose wording/phrasing (within D-03 structure + D-04 conciseness).
- `generate_insights` input/return contract shape (raw metrics dict vs prepared summary vs domain `SolveResult`; plain string vs small structured object). Keep provider-neutral.
- Insight-generation thread path (separate executor vs FastAPI `def`-route threadpool) — just NOT the single-worker solve pool.
- Numeric-extraction strategy for the D-06 guard (regex, tolerance for `%`, commas, decimals).

### Deferred Ideas (OUT OF SCOPE)
- Auto-generate insights after every completed run (INS-05) — v2.
- Real Claude `generate_insights` + model config (LLM-02) — Phase 4. Phase 3 wires only the stub.
- Async 202 / polling insight model with an insight-status field — rejected in favor of blocking-GET-on-worker-thread (D-02).
- What-if compare + delta explanation — Phase 5.
- WR-05 (real-engine ENG-05 degeneracy test) and WR-04 (fixture path traversal hardening) — reviewed, not folded.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INS-01 | An endpoint generates a NL insight report from a completed run's metrics | New `GET /runs/{run_id}/insights` sync `def` route (§Pattern 1) over `serialize_result` metrics; `insight_service` orchestrates load→gate→generate→guard→persist. |
| INS-02 | Insights are a separate on-demand step; LLM failure never changes run status or invalidates the schedule | Insight path never writes `result_json`/`status`; on provider/guard failure → 5xx, nothing cached (§D-08 path, §Pitfall 1). Generation is decoupled from the solve worker pool entirely. |
| INS-03 | Report cites specific metric values (no generic "coverage was adequate") | D-05 four-topic coverage + D-06 post-hoc numeric grounding guard (§Pattern 2); `warnings[]` narration forces honest zero-coverage language. |
| INS-04 | Insight result cached in `runs.insight_json` so repeat fetches don't re-call the LLM | New `insight_json TEXT` column + `RunRepo.set_insight`/read; cache-hit short-circuit before provider call (§D-10, §Pattern 3). |
</phase_requirements>

## Summary

This phase adds a single read endpoint that lazily generates, grounds, caches, and returns a natural-language insight report for a COMPLETED run. Every live code seam the planner needs is already present and was verified in this session: the `LLMProvider` Protocol + `create_provider` factory (`backend/llm/base.py`), the deterministic `StubLLMProvider` (`backend/llm/stub.py`), the `get_llm_provider` dependency (`backend/api/deps.py`), the `RunRepo` + `runs.result_json` read/write pattern (`backend/store/repositories.py`), the embedded `CREATE TABLE IF NOT EXISTS` DDL (`backend/store/db.py`), the `serialize_result` metrics shape (`backend/services/serialize.py`), and the `StubEngine` + `app.dependency_overrides` test seam (`backend/tests/test_api.py`, `test_constraints_api.py`).

The two genuinely open items both resolve cleanly. **D-02 thread path:** the existing `GET /runs/{id}/result` route is declared with plain `def` (sync). FastAPI runs every sync `def` path operation in an external anyio threadpool via `run_in_threadpool` — verified in the FastAPI source — so declaring `GET /runs/{run_id}/insights` as `def` already takes generation off the event loop, in a 40-worker pool that is completely separate from the single-worker solve `ThreadPoolExecutor`. No new executor is needed; adding one would be redundant complexity. **D-06 guard:** a tolerance-based numeric reconciliation over the report text against an "allowed-value set" derived from the same metrics dict the provider was given. The set includes percentage renderings (`pct × 100`) and integer/decimal variants so `%`, thousands-commas, currency and rounding are tolerated, while a fabricated figure has no match and trips the guard.

**Primary recommendation:** Declare `GET /runs/{run_id}/insights` as a sync `def` route (matching `get_run_result`); put orchestration in a new `services/insight_service.py` that (load run → gate COMPLETED → return cache if present → else build grounded metrics dict → call `provider.generate_insights(dict) -> str` → run numeric guard against the same dict → persist `insight_json` → return). On not-ready return 200 `{ready:false,…}` (D-07); on provider error or guard rejection return 5xx and cache nothing (D-08). No new packages; stdlib `re`/`json` only.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Insight HTTP endpoint + status gate + HTTP error mapping | API / Backend (`api/routers/runs.py`) | — | Mirrors existing `get_run_result`; router translates service outcomes to HTTP (established "service raises / router translates" pattern). |
| Orchestration (load→gate→cache→generate→guard→persist) | API / Backend service (`services/insight_service.py`) | — | Business logic belongs in services; routers stay thin. |
| NL text generation | LLM provider seam (`llm/base.py` + `llm/stub.py`) | — | Provider-neutral Protocol op; Phase-4 Claude drops in unchanged. |
| Number-grounding guard (D-06) | API / Backend service | — | Provider-agnostic safety net; must sit at the seam, not in the stub, so it guards real Claude in Phase 4. |
| Cache persistence (`insight_json`) | Database / Storage (`store/db.py`, `store/repositories.py`) | — | Reuses `RunRepo` + `result_json` precedent. |
| Off-event-loop execution | FastAPI anyio threadpool (sync `def` route) | — | Built-in; not the CPU-bound solve pool (D-02). |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.138.1 (installed) | HTTP route + sync-threadpool execution | Already the project's API framework; sync `def` routes give off-event-loop execution for free. [VERIFIED: importlib.metadata] |
| Starlette | 1.3.1 (installed) | `run_in_threadpool` under FastAPI | FastAPI delegates sync routes here. [VERIFIED: importlib.metadata] |
| anyio | 4.14.1 (installed) | Threadpool limiter backing `run_in_threadpool` | Default capacity ~40 worker threads for sync routes. [VERIFIED: importlib.metadata] |
| pytest | (dev, installed) | Stub-driven tests | Existing test runner; 80 tests pass green. [VERIFIED: `uv run pytest` → 80 passed] |
| Python stdlib `re` | 3.10–3.12 | Numeric extraction in D-06 guard | Project already uses stdlib regex in `llm/stub.py`; no new dependency. [VERIFIED: codebase] |
| Python stdlib `json`, `sqlite3` | 3.10–3.12 | Serialization + persistence | Already used throughout `store/` and `services/`. [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic `BaseModel` | (via FastAPI) | Insight response schema (`InsightOut`) | Add alongside `RunOut` in `api/schemas.py`. [VERIFIED: codebase `api/schemas.py`] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sync `def` route in anyio threadpool | A dedicated `ThreadPoolExecutor` for insights | A separate executor is redundant: FastAPI already runs sync routes off the event loop. An executor adds lifecycle/shutdown management and a second blocking hop for no benefit. Only justified if you needed bounded concurrency distinct from the 40-thread default — not the case here. |
| Plain-`str` return from `generate_insights` | Small structured object (e.g. dataclass with `summary` + `highlights`) | A string keeps the Protocol provider-neutral and trivially stub-able; the D-03 structure is encoded in the text. A structured object would push presentation knowledge into the provider. Recommend `str`. |
| Tolerance-based numeric guard | Template-slot-only grounding | Slots guarantee grounding only inside the stub, not at the seam — fails the D-06 requirement to protect the Phase-4 provider. |

**Installation:** No new packages. All dependencies already present in `backend/.venv` (verified via `uv run pytest` → 80 passed).

**Version verification:** `import fastapi → 0.138.1` (also 0.104.1 reported by the bare interpreter — the active `.venv` is 0.138.1; the planner should target the `.venv` version). `starlette 1.3.1`, `anyio 4.14.1`. [VERIFIED: `uv run --directory backend python -c "from importlib.metadata import version; ..."`]

## Package Legitimacy Audit

> No external packages are installed by this phase. All code uses the Python standard library (`re`, `json`, `sqlite3`, `uuid`, `datetime`) plus already-vendored dependencies (FastAPI/Starlette/anyio/pydantic/pytest) introduced and verified in Phases 1–2.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none — no new installs)* | — | — | — | — | OK | N/A |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
            HTTP client
                │  GET /runs/{run_id}/insights
                ▼
   ┌──────────────────────────────┐
   │ runs.py  (sync `def` route)  │   ← runs in anyio threadpool, NOT event loop,
   │  Depends: get_db,            │     NOT the single-worker solve pool
   │           get_llm_provider   │
   └──────────────┬───────────────┘
                  │ delegates
                  ▼
   ┌──────────────────────────────────────────────┐
   │ services/insight_service.get_or_generate()    │
   │                                               │
   │  1. RunRepo.get(run_id) ──► None? → LookupError (router → 404)
   │  2. status != COMPLETED  ──────────────► return {ready:false, status}  (router → 200, D-07)
   │  3. run.insight_json set? ─────────────► return cached report          (INS-04 cache hit)
   │  4. build grounded metrics dict from run.result_json (already serialized)
   │  5. read scenario.overrides via run.scenario_id → overrides summary (D-05 #4)
   │  6. report = provider.generate_insights(insight_input)   ── provider error ─┐
   │  7. _grounding_guard(report, allowed_values)  ── ungrounded number ─────────┤
   │  8. RunRepo.set_insight(run_id, report); conn.commit()                      │
   │  9. return {ready:true, report}                                            │
   └───────────────────────────────────────────────────────────────────────────┘
                                                          │ (6 or 7 fail)
                                                          ▼
                                          raise → router maps to 5xx (D-08)
                                          run.status untouched, nothing cached
```

### Recommended Project Structure (additions only)
```
backend/
├── services/
│   └── insight_service.py    # NEW: orchestration + D-06 guard (or guard in its own module)
├── llm/
│   ├── base.py               # EDIT: add generate_insights to Protocol
│   └── stub.py               # EDIT: add deterministic StubLLMProvider.generate_insights
├── api/
│   ├── routers/runs.py       # EDIT: add GET /runs/{run_id}/insights (sync def)
│   └── schemas.py            # EDIT: add InsightOut response model
├── store/
│   ├── db.py                 # EDIT: insight_json in DDL + ALTER-TABLE guard in init_db
│   └── repositories.py       # EDIT: RunRepo.set_insight (+ read via existing get)
└── tests/
    └── test_insights_api.py  # NEW: generate→cache→provider-failure→not-ready (criteria 1–4)
```

### Pattern 1: Off-event-loop via sync `def` route (resolves D-02)
**What:** Declare the insight route with plain `def`. FastAPI runs every non-coroutine path operation in an external threadpool, so the event loop is never blocked and the route never touches the single-worker solve pool.
**When to use:** Any blocking work (here: provider call + DB I/O) inside an HTTP handler that should not stall the event loop.
**Verification:** FastAPI's `request_response` wraps non-async endpoints in `functools.partial(run_in_threadpool, func)`; the docs state path operations declared with `def` run "in an external threadpool". [VERIFIED: Context7 /fastapi/fastapi — `fastapi/routing.py` request_response + docs/en/docs/async.md]
**Existing precedent:** `get_run_result` (and every other route in `runs.py`) is already declared `def`. [VERIFIED: codebase `backend/api/routers/runs.py:54`]

```python
# backend/api/routers/runs.py  — Source: mirrors existing get_run_result (line 51)
@router.get("/runs/{run_id}/insights",
            responses={404: {"description": "Run not found"},
                       502: {"description": "Insight generation failed"}})
def get_run_insights(
    run_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),   # reuse LLM-03 seam
) -> dict:
    try:
        return insight_service.get_or_generate(conn, provider, run_id)
    except LookupError as exc:                 # unknown run  → 404 (service raises / router translates)
        raise HTTPException(status_code=404, detail=str(exc))
    except InsightGenerationError as exc:      # provider OR guard failure → 5xx, nothing cached (D-08)
        raise HTTPException(status_code=502, detail=str(exc))
```

> Note: the not-ready case (D-07) returns a normal dict `{ready: False, ...}` with HTTP 200 — it is *not* an exception. Only unknown-run (404) and generation failure (5xx) raise.

### Pattern 2: Provider-agnostic numeric grounding guard (resolves D-06)
**What:** After generation, extract every number from the report text, normalize formatting, and require each to match a value derived from the run's metrics within tolerance. Build the **allowed-value set** from the *same* metrics dict handed to the provider.
**When to use:** Immediately after `generate_insights`, before persisting. Any unmatched number → raise `InsightGenerationError` (→ D-08 5xx, nothing cached).

```python
# Source: new backend/services/insight_service.py (illustrative)
import re

_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")   # 1,234  12.5  80  123.00

def _allowed_values(metrics: dict) -> set[float]:
    """All defensible numeric renderings of the run's real metrics (D-06).

    For each metric value v we admit: v itself, round(v,1), round(v,2),
    and — for fraction-style coverage pcts — v*100 with the same rounding,
    so "0.8" in metrics matches "80%" / "80.0%" in prose. None (NaN-coerced)
    values contribute NOTHING, so any number printed for a null metric is caught.
    """
    vals: set[float] = set()
    def admit(x):
        if x is None or not isinstance(x, (int, float)):
            return
        for y in (x, round(x, 1), round(x, 2)):
            vals.add(float(y))
    m = metrics
    admit(m.get("total_cost")); admit(m.get("total_unmet_hours"))
    admit(m.get("scheduled_shifts")); admit(m.get("scheduled_members"))
    for cov in (m.get("coverage_by_function") or {}).values():
        admit(cov.get("required_h")); admit(cov.get("served_h"))
        admit(cov.get("pct"))
        if isinstance(cov.get("pct"), (int, float)):     # 0.8 → 80
            for y in (cov["pct"]*100, round(cov["pct"]*100, 1)):
                vals.add(float(y))
    for p in (m.get("coverage_by_day") or {}).values():
        admit(p)
        if isinstance(p, (int, float)):
            vals.add(float(p*100))
    return vals

def _grounding_guard(report: str, metrics: dict, *, tol: float = 0.05) -> None:
    allowed = _allowed_values(metrics)
    for tok in _NUM_RE.findall(report):
        v = float(tok.replace(",", ""))
        if not any(abs(v - a) <= tol for a in allowed):
            raise InsightGenerationError(
                f"Ungrounded number {tok!r} not found in run metrics")
```

**Design notes / pitfalls baked in:**
- `serialize_result` already coerces NaN/inf → `None` (round-2 timeout case). Null metrics are excluded from `allowed`, so the report must *not* print a figure for a null metric — if it does, the guard catches it. The stub report should say e.g. "cost not available" rather than emit a number. [VERIFIED: codebase `backend/services/serialize.py:14`]
- Tolerance `tol` covers display rounding (8.0 → "8"); commas stripped before parse; trailing `%` is captured by the day/pct ×100 renderings. The planner may widen the regex to consume a trailing `%` explicitly.
- **False-positive risk:** structural integers the prose might use ("all 4 functions", "day 1") may not be in `allowed`. Because *we author the stub report*, keep it to grounded numbers only (and spell small structural counts as words, or include `len(coverage_by_function)` in the allowed set). Flagged in Assumptions (A2).

### Pattern 3: Cache-hit short-circuit (INS-04 / criterion 4)
**What:** Before calling the provider, return `run["insight_json"]` if non-null. `RunRepo.get` already does `SELECT *`, so the new column is returned automatically once added.
```python
# Source: new insight_service.get_or_generate (illustrative)
run = RunRepo(conn).get(run_id)
if run is None:
    raise LookupError(f"Run {run_id} not found")
if run["status"] != "COMPLETED" or not run["result_json"]:
    return {"ready": False, "run_id": run_id, "status": run["status"],
            "reason": f"Insights available only for COMPLETED runs (status: {run['status']})"}
if run["insight_json"]:                                  # cache hit — no provider call (INS-04)
    return {"ready": True, "run_id": run_id, "report": run["insight_json"]}
# … cache miss: generate, guard, persist …
```

### Pattern 4: Idempotent column add with no migration framework (D-10)
**What:** SQLite has no `ADD COLUMN IF NOT EXISTS`; guard with `PRAGMA table_info`.
```python
# backend/store/db.py — add to _SCHEMA runs table:  insight_json TEXT   -- cached NL report (INS-04)
def _has_column(conn, table, col) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})"))

def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(_SCHEMA)                       # fresh DBs get the column from DDL
        if not _has_column(conn, "runs", "insight_json"): # existing DBs: additive migration
            conn.execute("ALTER TABLE runs ADD COLUMN insight_json TEXT")
        conn.commit()
    finally:
        conn.close()
```
`RunRepo` addition:
```python
def set_insight(self, run_id: str, insight_json: str) -> None:
    self.conn.execute("UPDATE runs SET insight_json=? WHERE id=?", (insight_json, run_id))
```
`get` needs no change (`SELECT *`). [VERIFIED: codebase `backend/store/repositories.py:55`]

### Pattern 5: `generate_insights` Protocol contract (D-09 discretion → recommendation)
**Recommended input:** a plain JSON-safe dict (provider-neutral, no domain object crosses the seam), assembled by `insight_service` from the run's already-serialized metrics + warnings + an overrides summary. **Recommended return:** plain `str` (the D-03-structured report text).

```python
# backend/llm/base.py
class LLMProvider(Protocol):
    def parse_constraints(self, text: str) -> list[OverrideCall]: ...
    def generate_insights(self, summary: dict) -> str: ...          # NEW (LLM-01 second op)
    @property
    def name(self) -> str: ...
```
`summary` shape (built by the service, so the guard reconciles against the same numbers):
```python
{
  "metrics": { ...serialize_result()["metrics"]... },   # total_cost, total_unmet_hours, coverage_by_function, coverage_by_day
  "warnings": [ ...result["warnings"]... ],             # D-05 #3 degenerate-family narration
  "overrides": [ {"tool": "...", "args": {...}}, ... ], # D-05 #4 applied overrides
}
```
**Why dict-in/str-out:** mirrors how `result_json` already flows as plain dicts; keeps the stub trivially deterministic (TEST-01); avoids the provider importing/depending on `SolveResult` internals; and the service owns both the prompt input and the guard's allowed-value set, guaranteeing they reference identical numbers. The Phase-4 Claude provider turns the same dict into a prompt with no contract change. [VERIFIED: codebase — `parse_constraints(text)->list[OverrideCall]` is the sibling shape to mirror, `backend/llm/base.py:16`]

### Anti-Patterns to Avoid
- **Reusing the solve pool for insights:** `run_service._get_pool()` is `ThreadPoolExecutor(max_workers=1)` and serializes — an insight would queue behind a running solve. Explicitly forbidden by D-02. [VERIFIED: codebase `backend/services/run_service.py:38`]
- **`async def` route that calls the blocking provider directly:** would block the event loop. Use sync `def` (Pattern 1).
- **Caching a report that failed the guard:** a fabricated number must never be persisted or returned (D-06/D-08). Guard runs *before* `set_insight`.
- **Putting the guard inside the stub:** it must live at the service/seam so it also protects Phase-4 Claude.
- **Echoing a metric the serializer nulled:** printing a number where `serialize_result` produced `None` trips the guard (and is misleading).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Off-event-loop execution | A custom `ThreadPoolExecutor` + lifecycle/shutdown for insights | FastAPI sync `def` route (`run_in_threadpool`) | Framework already does exactly this for sync routes; a second pool is dead weight and another shutdown hook to manage. |
| Metrics serialization for the report/guard | A new metrics-to-dict function | `serialize_result` (already in `run.result_json`) | It is the canonical shape, already NaN/inf-safe; reusing it keeps prompt input and guard reconciliation identical. |
| Run/scenario persistence | New DAO methods beyond `set_insight` | `RunRepo` + `ScenarioRepo` | `get`/`SELECT *` already returns the new column; only an `UPDATE … set_insight` is new. |
| Schema migration tooling | Adopting Alembic/migration framework | `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` guard | Project deliberately has no migration framework (D-10); one additive column doesn't justify one. |
| NL number extraction | An NLP/number-words parser | stdlib `re` digit regex + normalization | The report is machine-authored (stub now, prompt-constrained Claude later); a simple digit regex with tolerance is sufficient and deterministic. |

**Key insight:** Phase 3 is almost entirely *composition of existing seams*. The only genuinely new logic is (a) the `generate_insights` stub body and (b) the grounding guard. Everything else is a thin reuse of `result_json`/`RunRepo`/the sync-route pattern.

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `runs.result_json` already holds serialized metrics for every COMPLETED run; new `runs.insight_json` will hold the cached report. Existing dev DB at `backend/var/rosterai.db` (if present) predates the column. | Additive `ALTER TABLE runs ADD COLUMN insight_json` guard in `init_db` so existing DBs gain the column on next startup (Pattern 4). No data migration — column is nullable, populated lazily on first GET. |
| Live service config | None — no external services hold insight state. | None. |
| OS-registered state | None — no schedulers/daemons reference insights. | None — verified: no cron/Task Scheduler entries in repo. |
| Secrets/env vars | `ROSTERAI_DB`, `ROSTERAI_DATA_DIR` only (unchanged). No LLM API key in Phase 3 (stub-only; real key is Phase 4 LLM-02). | None. |
| Build artifacts | None — no compiled artifacts embed run/insight state. | None. |

**Canonical question (post-rename equivalent):** after the column is added, the only runtime state is the SQLite `runs` table; a pre-existing dev DB is reconciled by the `init_db` ALTER guard on startup.

## Common Pitfalls

### Pitfall 1: Insight failure leaks into run status (violates INS-02 / criterion 3)
**What goes wrong:** A provider exception or guard rejection accidentally marks the run FAILED or overwrites `result_json`.
**Why it happens:** Copy-pasting `run_service._execute`'s `set_failed`/`set_completed` writes into the insight path.
**How to avoid:** The insight path must call **only** `RunRepo.set_insight` (and only on success). On any failure, raise → router maps to 5xx; never touch `status`/`result_json`/`error`. Criterion 3 test forces this.
**Warning signs:** A test that injects a failing provider sees the run flip out of COMPLETED, or sees `result_json` change.

### Pitfall 2: Caching an ungrounded report
**What goes wrong:** `set_insight` runs before the guard, so a fabricated number gets persisted and is then served forever from cache.
**Why it happens:** Wrong ordering of generate → persist → guard.
**How to avoid:** Strict order: generate → guard → (only if clean) persist → return.
**Warning signs:** A later GET returns a report the guard would now reject.

### Pitfall 3: pct-format mismatch defeats the guard
**What goes wrong:** Metrics store coverage `pct` as a fraction (`0.8`) but the report prints `80%`; a naive guard rejects the *real* number as ungrounded.
**Why it happens:** Forgetting the fraction↔percentage rendering.
**How to avoid:** Include `pct × 100` in the allowed-value set (Pattern 2). `CoverageStat.pct` is `served_h/required_h` (a fraction). [VERIFIED: codebase `backend/domain/result.py:24`]
**Warning signs:** Guard fails on a hand-checked-correct report.

### Pitfall 4: Concurrent first-GET double-generates
**What goes wrong:** Two simultaneous first GETs on the same run both miss the cache and both call the provider; last write wins.
**Why it happens:** No lock between read-cache and write-cache.
**How to avoid:** Acceptable for MVP — content is deterministic (stub) and idempotent; the wasted second call is harmless. If undesired later, gate with a conditional `UPDATE … WHERE insight_json IS NULL`. Flagged as Open Question 1.
**Warning signs:** Provider call-count assertions flake under concurrency (avoid asserting exact provider call counts across parallel requests).

### Pitfall 5: Overrides summary reads *current* scenario, not solve-time snapshot
**What goes wrong:** D-05 #4 says "overrides that shaped this run," but the run does not snapshot overrides — `_execute` reads `scenario["overrides"]` at solve time and stores only `result_json`. The insight service can only read the scenario's *current* `overrides` via `run.scenario_id`, which may have changed since the solve.
**Why it happens:** No overrides snapshot on the run row.
**How to avoid (MVP):** Read `scenario.overrides` via `run.scenario_id` and narrate it; document the caveat. For exact fidelity, a future enhancement snapshots overrides onto the run at solve time. Note: the stored override JSON shape is `{id: {tool, args}}` — `parsed_constraint` human phrasing is **not** persisted, so the report/service reconstructs a phrase from `tool`+`args`. [VERIFIED: codebase `backend/services/constraint_service.py:371`, `backend/services/run_service.py:89`] Flagged in Assumptions (A1) and Open Question 2.
**Warning signs:** Report lists an override that was added after the run, or omits one that was later removed.

## Code Examples

### Deterministic stub `generate_insights` (TEST-01)
```python
# backend/llm/stub.py — add to StubLLMProvider (illustrative; prose wording is Claude's discretion)
def generate_insights(self, summary: dict) -> str:
    m = summary["metrics"]
    lines = []
    # D-03: 1–2 sentence narrative + structured metric highlights
    cost = m.get("total_cost"); unmet = m.get("total_unmet_hours")
    cost_s = f"{cost:g}" if cost is not None else "not available"
    unmet_s = f"{unmet:g}" if unmet is not None else "not available"
    lines.append(f"Schedule solved with total cost {cost_s} and {unmet_s} unmet hours.")
    for fn, c in (m.get("coverage_by_function") or {}).items():
        if c.get("pct") is not None:
            pct = c["pct"] * 100
            lines.append(f"- {fn}: served {c['served_h']:g}/{c['required_h']:g} h ({pct:g}%)")
    for w in summary.get("warnings", []):          # D-05 #3 — honest degenerate-family narration
        lines.append(f"- WARNING: {w}")
    for ov in summary.get("overrides", []):        # D-05 #4 — applied overrides in effect
        lines.append(f"- override applied: {ov['tool']} {ov['args']}")
    return "\n".join(lines)
```
Every number emitted (`cost`, `unmet`, `served_h`, `required_h`, `pct×100`) is in the metrics dict → passes the guard by construction. [Pattern derived from VERIFIED metrics shape in `serialize.py`]

### Insight response schema
```python
# backend/api/schemas.py — add alongside RunOut
class InsightOut(BaseModel):
    ready: bool
    run_id: str
    report: Optional[str] = None     # present when ready
    status: Optional[str] = None     # present when not ready (D-07)
    reason: Optional[str] = None     # present when not ready (D-07)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Block event loop / manual thread for blocking handler work | Declare route `def`; FastAPI/Starlette run it via `run_in_threadpool` (anyio limiter) | Standard since Starlette adopted anyio | No custom executor needed for D-02; matches existing `runs.py` routes. [VERIFIED: Context7 /fastapi/fastapi] |

**Deprecated/outdated:** None relevant. (Note: a Starlette deprecation warning appears in tests — "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2`" — cosmetic, does not affect this phase. [VERIFIED: test output])

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | D-05 #4 overrides are read from the scenario's *current* `overrides` via `run.scenario_id` (no solve-time snapshot exists on the run). | Pitfall 5 / Pattern 5 | Report may show overrides that differ from those that actually shaped the run if the scenario was re-constrained after solving. Low for MVP (runs typically fetched before further edits); planner should confirm whether a snapshot is required. |
| A2 | The machine-authored report emits only grounded metric numbers; small structural counts (function count, day index) are spelled as words or added to the allowed set, so the guard yields no false positives. | Pattern 2 / Pitfall 3 | If the stub prose emits a structural integer not in `allowed`, the guard rejects a correct report. Mitigated by authoring the stub carefully; planner sets guard tolerance/word-spelling policy. |
| A3 | anyio's default sync-route threadpool (~40 workers) is ample for on-demand insight concurrency. | Standard Stack | If many concurrent insight GETs + a long Phase-4 Claude call saturate the pool, latency rises. Negligible at MVP scale; revisit in Phase 4. |

## Open Questions

1. **Concurrent first-GET double-generation.**
   - What we know: deterministic stub → harmless; last write wins.
   - What's unclear: whether the planner wants strict single-generation.
   - Recommendation: accept for MVP; optionally a `WHERE insight_json IS NULL` conditional write. Do **not** assert exact provider call-counts under parallel requests in tests.
2. **Overrides fidelity (snapshot vs live read).**
   - What we know: run stores no overrides snapshot; `_execute` reads scenario overrides at solve time.
   - What's unclear: whether D-05 #4 requires exact solve-time fidelity.
   - Recommendation: MVP reads current `scenario.overrides`; document caveat; defer snapshot to a later slice if needed.
3. **5xx status code choice (502 vs 503).**
   - What we know: D-08 says "5xx (502/503)".
   - Recommendation: use **502 Bad Gateway** for provider/guard failure (an upstream-generation failure), reserving 503 for explicit unavailability. Planner's call.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All backend code | ✓ | 3.10–3.12 (project pin) | — |
| FastAPI | Insight route | ✓ | 0.138.1 (.venv) | — |
| Starlette/anyio | sync-route threadpool | ✓ | 1.3.1 / 4.14.1 | — |
| pytest + httpx | Stub-driven tests | ✓ | installed (dev group) | — |
| SQLite (stdlib) | `insight_json` persistence | ✓ | stdlib | — |
| Live LLM API | (NOT used in Phase 3) | ✗ (by design) | — | Stub provider drives all paths (TEST-01) — this is the intended state, not a gap. |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Live LLM API is intentionally absent in Phase 3 (stub-only CI). No action.

## Validation Architecture

> nyquist_validation is enabled (config.json `workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (dev dependency); FastAPI `TestClient` |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` `testpaths=["tests"]` |
| Quick run command | `uv run --directory backend pytest tests/test_insights_api.py -x` |
| Full suite command | `uv run --directory backend pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INS-01 / criterion 1 | GET insights for a COMPLETED run returns a NL report (`ready=true`, `report` non-empty) | integration | `pytest tests/test_insights_api.py::test_insights_returns_report_for_completed_run -x` | ❌ Wave 0 |
| INS-01 / criterion 1 | GET insights for a not-yet-completed run → 200 `{ready:false, status}` (D-07, NOT 409) | integration | `pytest tests/test_insights_api.py::test_insights_not_ready_returns_200_body -x` | ❌ Wave 0 |
| INS-03 / criterion 2 | Every number in the report appears in metrics; a stub emitting a fabricated number → guard → 5xx, nothing cached | integration | `pytest tests/test_insights_api.py::test_grounding_guard_rejects_fabricated_number -x` | ❌ Wave 0 |
| INS-03 | Report narrates `warnings[]` honestly (no generic "coverage was adequate" when a family has zero served hours) | integration | `pytest tests/test_insights_api.py::test_report_narrates_degenerate_warnings -x` | ❌ Wave 0 |
| INS-02 / criterion 3 | Forcing provider failure leaves run COMPLETED + `result_json` untouched; only the insight call errors (5xx) | integration | `pytest tests/test_insights_api.py::test_provider_failure_leaves_run_completed -x` | ❌ Wave 0 |
| INS-04 / criterion 4 | Second fetch returns cached `insight_json` without re-calling the provider (assert provider call-count == 1 for *sequential* fetches) | integration | `pytest tests/test_insights_api.py::test_second_fetch_uses_cache -x` | ❌ Wave 0 |
| INS-04 | Unknown run → 404; FAILED run → 200 not-ready (no metrics to ground) | integration | `pytest tests/test_insights_api.py::test_unknown_and_failed_run -x` | ❌ Wave 0 |
| LLM-01 | `StubLLMProvider.generate_insights` is deterministic, no I/O, returns str | unit | `pytest tests/test_llm_provider.py::test_generate_insights_deterministic -x` | ❌ Wave 0 (extend existing file) |

### Stub-driven test approach (TEST-01 / criterion 3)
- Extend the existing fixture pattern: `app.dependency_overrides[get_engine] = lambda: StubEngine()` and `app.dependency_overrides[get_llm_provider] = lambda: <stub>` (real `StubLLMProvider` for happy path; a purpose-built failing/fabricating stub for guard + failure tests). [VERIFIED: codebase `backend/tests/test_constraints_api.py:93`]
- **Failure injection (criterion 3):** override `get_llm_provider` with a stub whose `generate_insights` raises; assert GET → 5xx, then GET `/runs/{id}` still shows `COMPLETED` and GET `/runs/{id}/result` unchanged, and a subsequent GET `/runs/{id}/insights` with a *working* provider succeeds (proving nothing was cached on failure).
- **Fabrication injection (criterion 2):** override with a stub returning a report containing a number absent from metrics; assert 5xx and nothing cached.
- **Cache (criterion 4):** use a counting stub; first GET generates (count 1), second sequential GET returns identical body with count still 1. Do not assert counts under parallel load (Open Question 1).
- Reuse `_wait_terminal` helper to reach COMPLETED before fetching insights. [VERIFIED: codebase `backend/tests/test_api.py:61`]

### Sampling Rate
- **Per task commit:** `uv run --directory backend pytest tests/test_insights_api.py -x`
- **Per wave merge:** `uv run --directory backend pytest`
- **Phase gate:** Full suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/test_insights_api.py` — covers INS-01..04 + criteria 1–4 (new file).
- [ ] Extend `backend/tests/test_llm_provider.py` — `generate_insights` determinism (LLM-01).
- [ ] Shared failing/counting/fabricating stub providers — define inline in the new test file (mirror `StubEngine` pattern); no new conftest fixtures required.
- Framework install: none — pytest + httpx already in the dev group and passing (80 tests green).

## Security Domain

> `security_enforcement: true`, ASVS level 1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in this API milestone (pre-existing posture; unchanged). |
| V3 Session Management | no | Stateless HTTP; no sessions. |
| V4 Access Control | no | No per-user authorization in scope; run/scenario ids are opaque uuids. |
| V5 Input Validation | yes | `run_id` is a path param used only in parameterized SQL (`RunRepo.get` uses `?` placeholders — no string interpolation). No user-supplied free text reaches the insight path (input is the run's own metrics). [VERIFIED: codebase `backend/store/repositories.py`] |
| V6 Cryptography | no | No crypto introduced. |
| V5 Output handling | yes | Report text is machine-generated from the run's own metrics and returned as a JSON string (FastAPI/pydantic encodes it) — no template/HTML injection surface (API-only, no UI until Phase 4). |

### Known Threat Patterns for FastAPI + SQLite + LLM-seam

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `run_id` | Tampering | Parameterized queries only (`WHERE id = ?`) — already the codebase norm; the new `set_insight` MUST use placeholders. [VERIFIED: `repositories.py`] |
| Prompt-injection into the report | Tampering / Info disclosure | Phase 3 input is the run's *own* numeric metrics + tool/args (no untrusted free text), and the D-06 guard rejects any number not in metrics — limiting fabricated/exfiltrated figures. Real-Claude prompt hardening is Phase 4. |
| DoS via repeated generation | DoS | Cache short-circuit (INS-04) means at most one generation per run; sync-route threadpool bounds concurrency (~40). |
| Insight failure corrupting run state | Tampering | D-08: failures never write `status`/`result_json`; insight write is isolated to `insight_json` (Pitfall 1). |

## Sources

### Primary (HIGH confidence)
- Codebase (verified this session via `Read`): `backend/llm/base.py`, `backend/llm/stub.py`, `backend/api/deps.py`, `backend/api/routers/runs.py`, `backend/api/routers/constraints.py`, `backend/api/schemas.py`, `backend/api/main.py`, `backend/store/db.py`, `backend/store/repositories.py`, `backend/services/run_service.py`, `backend/services/serialize.py`, `backend/services/scenario_service.py`, `backend/services/constraint_service.py`, `backend/domain/result.py`, `backend/domain/overrides.py`, `backend/settings.py`, `backend/tests/test_api.py`, `backend/tests/test_constraints_api.py`, `backend/conftest.py`, `backend/pyproject.toml`.
- Context7 `/fastapi/fastapi` — sync `def` path operations run via `run_in_threadpool` (external threadpool, event loop unblocked); `fastapi/routing.py request_response`, `docs/en/docs/async.md`.
- `uv run --directory backend pytest` → 80 passed (baseline green); `importlib.metadata.version` for fastapi/starlette/anyio.

### Secondary (MEDIUM confidence)
- None required — all claims grounded in codebase or Context7.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified in the active `.venv`; no new packages.
- Architecture: HIGH — every seam read directly; D-02 resolved against verified FastAPI behavior + existing `def` routes.
- Pitfalls: HIGH — derived from verified code (serializer NaN-coercion, single-worker pool, override storage shape).
- Grounding guard: MEDIUM-HIGH — strategy is sound and testable; exact tolerance/word-spelling policy is the planner's tuning call (A2).

**Research date:** 2026-06-30
**Valid until:** 2026-07-30 (stable; codebase + pinned deps unlikely to shift within the milestone)
