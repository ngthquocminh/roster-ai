# ShiftMind — Original Idea (archived)

> **This is the initial product/technical spec the project started from**, kept
> in the repo so we don't need to reference anything outside it. It is a snapshot
> of the original idea — **not** a description of the current system, and it is
> **not maintained**. For how the project actually works, see
> [`../README.md`](../README.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and [`API.md`](API.md).

> **Repo name:** `rosterai` · **Product / brand name:** ShiftMind

**Portfolio project:** AI/ML Engineer. Demonstrates OR + LLM engineering in a single pipeline.

**Elevator pitch:** Upload workforce & demand data → describe constraint tweaks in plain English → CP-SAT solver generates a weekly schedule → Claude explains insights and flags issues.

**Stack:** React (TypeScript) + FastAPI (Python) + OR-Tools CP-SAT + Claude API + SQLite + Docker

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
2. [Architecture Overview](#2-architecture-overview)
3. [Module Design](#3-module-design)
4. [Data Models — SQLite](#4-data-models--sqlite)
5. [CSV Input Schemas](#5-csv-input-schemas)
6. [API Design](#6-api-design)
7. [Solver Formulation](#7-solver-formulation)
8. [LLM Integration](#8-llm-integration)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Async Run Execution](#10-async-run-execution)
11. [Summary Metrics Schema](#11-summary-metrics-schema)
12. [Deploy](#12-deploy)
13. [Project File Structure](#13-project-file-structure)
14. [Build Order](#14-build-order)

---

## 1. Core Concepts

| Concept | Description |
|---|---|
| **Session** | Lightweight browser session (UUID stored in localStorage). No auth in v1. All data on backend is scoped to a session. |
| **Scenario** | A named workspace: uploaded CSV data + active constraint overrides + metadata. A session can have multiple scenarios. |
| **Run** | One solver execution against a frozen snapshot of a scenario. Immutable once completed. Re-running creates a new Run. |
| **Insight** | LLM-generated analysis of a completed Run's summary metrics. Attached to a Run, generated asynchronously after solve. |

### Run Status Lifecycle

```
PENDING → RUNNING → COMPLETED
                 ↘ FAILED
```

---

## 2. Architecture Overview

The system follows **Clean Architecture** (Hexagonal / Ports & Adapters). Dependency direction is strictly inward:

```
API Layer
    ↓
Service Layer        ← orchestrates use cases
    ↓
Domain Layer         ← pure Python, zero external deps
    ↑
Infrastructure Layer ← solver engines, LLM providers, DB, storage
```

**Key rule:** Domain never imports from infrastructure. Infrastructure depends on domain types. Services depend on domain types + infrastructure interfaces (Protocols), never on concrete implementations.

This means swapping the solver engine (CP-SAT → CPLEX) or LLM provider (Claude → Gemini → Bedrock) requires zero changes to domain or service layers.

---

## 3. Module Design

### 3.1 Solver — SchedulerEngine Protocol

All solver implementations satisfy one Protocol. Services call `engine.solve()` and receive a `SolveResult` — they never import OR-Tools or CPLEX directly.

```python
# infrastructure/solver/base.py

from typing import Protocol
from dataclasses import dataclass, field
from app.domain.problem import SchedulingProblem
from app.domain.result import SolveResult

@dataclass
class SolverConfig:
    time_limit_s: int = 60
    mip_gap: float = 0.01
    num_threads: int = 4
    extra: dict = field(default_factory=dict)   # engine-specific knobs

class SchedulerEngine(Protocol):
    def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult: ...

    @property
    def name(self) -> str: ...

    @property
    def supports_warm_start(self) -> bool: ...
```

```python
# infrastructure/solver/factory.py

from app.infrastructure.solver.cpsat.engine import CpSatEngine
from app.infrastructure.solver.greedy.engine import GreedyEngine

REGISTRY: dict[str, type] = {
    "cpsat":  CpSatEngine,
    "greedy": GreedyEngine,   # fast heuristic fallback / CI tests
    # "cplex": CplexEngine,   # add when CPLEX license available
}

def create_engine(name: str) -> "SchedulerEngine":
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown solver engine: {name!r}. Available: {list(REGISTRY)}")
    return cls()
```

**Switching engines:** set `SOLVER_ENGINE=cplex` in `.env`. No service code changes.

### 3.2 LLM — LLMProvider Protocol + Adapter per Provider

Each LLM provider (Claude, Gemini, Bedrock) has a different API format for tool/function calling. The adapter layer normalizes this into a single `LLMProvider` interface that services use.

```python
# infrastructure/llm/base.py

from typing import Protocol, Literal
from dataclasses import dataclass

@dataclass
class Message:
    role: Literal["user", "assistant", "system"]
    content: str

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema — provider-agnostic

@dataclass
class ToolCall:
    tool_name: str
    arguments: dict

class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> tuple[str | None, list[ToolCall]]:
        """
        Returns (text_response, tool_calls).
        If tools were provided and the model called one, tool_calls is non-empty.
        text_response and tool_calls are mutually exclusive (one is None/empty).
        """
        ...
```

Each provider has a `provider.py` (wraps SDK) and an `adapter.py` (translates Tool/Message/ToolCall ↔ native format):

```python
# infrastructure/llm/claude/adapter.py

from app.infrastructure.llm.base import Tool, ToolCall

def to_anthropic_tools(tools: list[Tool]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]

def from_anthropic_tool_use(block) -> ToolCall:
    return ToolCall(tool_name=block.name, arguments=block.input)
```

```python
# infrastructure/llm/gemini/adapter.py

def to_gemini_tools(tools: list[Tool]) -> list[dict]:
    return [{
        "function_declarations": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ]
    }]

def from_gemini_function_call(call) -> ToolCall:
    return ToolCall(tool_name=call.name, arguments=dict(call.args))
```

```python
# infrastructure/llm/factory.py

from app.infrastructure.llm.claude.provider import ClaudeProvider
from app.infrastructure.llm.gemini.provider import GeminiProvider
from app.infrastructure.llm.bedrock.provider import BedrockProvider

REGISTRY = {
    "claude":  ClaudeProvider,
    "gemini":  GeminiProvider,
    "bedrock": BedrockProvider,   # wraps Claude/Titan/Llama via AWS SDK
}

def create_provider(name: str, **kwargs) -> "LLMProvider":
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {name!r}. Available: {list(REGISTRY)}")
    return cls(**kwargs)
```

**Switching providers:** set `LLM_PROVIDER=gemini` in `.env`. Operations layer (`constraint_parser.py`, `insight_generator.py`, `delta_explainer.py`) are untouched.

**Note on Bedrock:** AWS Bedrock exposes multiple model families (Claude, Titan, Llama) through one endpoint but with different per-model request formats. `BedrockProvider` takes a `model_id` parameter and the adapter handles the per-model format differences internally.

### 3.3 LLM Operations Layer

High-level LLM tasks live in `infrastructure/llm/operations/`. They depend on `LLMProvider` (the Protocol), not on any concrete provider. This is where prompts and structured output parsing live.

```python
# infrastructure/llm/operations/constraint_parser.py

class ConstraintParser:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def parse(self, nl_text: str, context: ScenarioContext) -> ConstraintOverride:
        _, tool_calls = await self.provider.complete(
            messages=[Message(role="user", content=nl_text)],
            tools=CONSTRAINT_TOOLS,           # list[Tool] defined below
            system=CONSTRAINT_SYSTEM_PROMPT,
        )
        if not tool_calls:
            raise ParseError("Model did not call a constraint tool")
        tc = tool_calls[0]
        return ConstraintOverride(
            parsed_tool=tc.tool_name,
            parsed_args=tc.arguments,
            display_label=_human_label(tc),
        )
```

### 3.4 Config (Environment-Driven)

```python
# app/config.py  (pydantic-settings)

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Solver
    solver_engine: str = "cpsat"         # "cpsat" | "cplex" | "greedy"
    solver_time_limit_s: int = 60
    solver_mip_gap: float = 0.01

    # LLM
    llm_provider: str = "claude"         # "claude" | "gemini" | "bedrock"
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""
    google_api_key: str = ""
    aws_region: str = "us-east-1"        # for Bedrock

    # App
    database_url: str = "sqlite:///./data/app.db"
    data_dir: str = "./data"

    class Config:
        env_file = ".env"
```

---

## 4. Data Models — SQLite

```sql
-- Sessions
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,   -- UUID v4
    created_at  DATETIME NOT NULL,
    last_seen   DATETIME NOT NULL
);

-- Scenarios
CREATE TABLE scenarios (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    site_name       TEXT DEFAULT 'Demo DC',
    horizon_start   DATE,               -- Monday of the planning week
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
);

-- Uploaded data files (3 types per scenario, stored as JSON)
CREATE TABLE scenario_files (
    id          TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    file_type   TEXT NOT NULL CHECK(file_type IN ('workers','demand','qualifications')),
    content     JSON NOT NULL,          -- parsed CSV as array of row objects
    row_count   INTEGER,
    uploaded_at DATETIME NOT NULL,
    UNIQUE(scenario_id, file_type)      -- one active file per type per scenario
);

-- NL constraint overrides
CREATE TABLE constraint_overrides (
    id              TEXT PRIMARY KEY,
    scenario_id     TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    nl_text         TEXT NOT NULL,      -- raw user input
    parsed_tool     TEXT NOT NULL,      -- function name the LLM called
    parsed_args     JSON NOT NULL,      -- function arguments
    display_label   TEXT,               -- human-readable summary for UI
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME NOT NULL
);

-- Runs
CREATE TABLE runs (
    id              TEXT PRIMARY KEY,
    scenario_id     TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    input_snapshot  JSON NOT NULL,      -- full copy of scenario data at trigger time
    created_at      DATETIME NOT NULL,
    started_at      DATETIME,
    completed_at    DATETIME,
    error_message   TEXT
);

-- Run Results
CREATE TABLE run_results (
    run_id          TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    summary_metrics JSON NOT NULL,      -- coverage, cost, utilization
    solver_stats    JSON NOT NULL,      -- solve_time_s, objective, gap_pct, status
    schedule_json   JSON NOT NULL,      -- full schedule rows
    insights_json   JSON,               -- LLM InsightReport (nullable, generated async)
    created_at      DATETIME NOT NULL
);
```

---

## 5. CSV Input Schemas

Three CSV files are uploaded per scenario. Templates are downloadable from the app.

### workers.csv

| Column | Type | Description |
|---|---|---|
| `worker_id` | str | Unique identifier |
| `name` | str | Display name |
| `employment_type` | str | `full_time` \| `part_time` \| `casual` |
| `contracted_hours_per_week` | float | Weekly contracted hours |
| `availability_days` | str | Comma-separated: `Mon,Tue,Wed,Thu,Fri` |
| `availability_start` | str | Earliest start time, e.g. `06:00` |
| `availability_end` | str | Latest end time, e.g. `22:00` |
| `preferred_area` | str | Optional: `Outbound` \| `Inbound` \| `Indirect` |

### demand.csv

| Column | Type | Description |
|---|---|---|
| `task_id` | str | Unique identifier |
| `task_name` | str | Display name, e.g. `Pick`, `Receiving` |
| `family` | str | `outbound` \| `inbound` \| `indirect` |
| `day` | str | `Monday` .. `Sunday` |
| `window_start` | str | Start of demand window, e.g. `06:00` |
| `window_end` | str | End of demand window, e.g. `14:00` |
| `volume` | float | Person-hours of demand (or units for outbound) |
| `unit` | str | `hours` \| `cases` \| `pallets` |

### qualifications.csv

| Column | Type | Description |
|---|---|---|
| `worker_id` | str | References workers.csv |
| `task_id` | str | References demand.csv |
| `preference_level` | str | `preferred` \| `qualified` \| `unqualified` |
| `productivity_rate` | float | Relative to default, e.g. `1.0`, `0.8` |

---

## 6. API Design

All endpoints: `Content-Type: application/json`. Session ID passed via `X-Session-ID` header.

### Sessions
```
POST   /api/sessions                           → create session, return {session_id}
GET    /api/sessions/{id}                      → validate + refresh last_seen
```

### Scenarios
```
GET    /api/scenarios                          → list scenarios for session
POST   /api/scenarios                          → create {name, description, site_name, horizon_start}
GET    /api/scenarios/{id}                     → scenario detail + file upload status
PATCH  /api/scenarios/{id}                     → update name / description
DELETE /api/scenarios/{id}                     → delete (cascades runs + files)
```

### Scenario Files
```
POST   /api/scenarios/{id}/files/{type}        → upload CSV → parse → store
                                               type: workers | demand | qualifications
GET    /api/scenarios/{id}/files/{type}        → paginated rows {data, total, page}
GET    /api/scenarios/{id}/files/templates     → download CSV templates as zip
DELETE /api/scenarios/{id}/files/{type}        → remove uploaded file
```

### Constraint Overrides
```
POST   /api/scenarios/{id}/constraints/preview → NL text → LLM parse → return parsed (NOT saved)
POST   /api/scenarios/{id}/constraints         → save a previewed constraint
GET    /api/scenarios/{id}/constraints         → list active constraints
PATCH  /api/scenarios/{id}/constraints/{cid}   → toggle is_active
DELETE /api/scenarios/{id}/constraints/{cid}   → remove
```

### Runs
```
POST   /api/scenarios/{id}/runs                → trigger run → {run_id, status: "PENDING"}
GET    /api/scenarios/{id}/runs                → list runs (desc order) with status
GET    /api/runs/{run_id}                      → status + metadata
GET    /api/runs/{run_id}/results              → full results (COMPLETED only)
GET    /api/runs/{run_id}/schedule             → paginated schedule rows
POST   /api/runs/{run_id}/insights             → (re-)trigger LLM insight generation
```

### What-if
```
POST   /api/scenarios/{id}/whatif              → body: {base_run_id, overrides: {...}}
                                               → snapshots scenario + applies overrides → new Run
GET    /api/runs/compare?a={run_id}&b={run_id} → delta summary between two COMPLETED runs
```

---

## 7. Solver Formulation

The solver receives a `SchedulingProblem` (pure domain type) and returns a `SolveResult`. The CP-SAT implementation lives in `infrastructure/solver/cpsat/`.

### Scale (demo)
- ~30 workers, 5–10 task types, 1 distribution centre, 1 week

### Shift Templates (hardcoded for demo)

```python
SHIFT_TEMPLATES = [
    {"id": "S6",  "length_h": 6,  "break_paid_h": 0.0, "break_unpaid_h": 0.5},
    {"id": "S8",  "length_h": 8,  "break_paid_h": 0.5, "break_unpaid_h": 0.5},
    {"id": "S10", "length_h": 10, "break_paid_h": 0.5, "break_unpaid_h": 1.0},
]
```

Eligible templates per worker are filtered by availability window length.

### Decision Variables

```python
# Binary: does worker w work a shift of template t starting at hour h on day d?
shift_selected[(w, d, h, t)] ∈ {0, 1}

# Binary: is worker w assigned to task k during slot s of their shift on day d?
task_assigned[(w, d, slot, task_id)] ∈ {0, 1}

# Integer (scaled): demand volume served for task k in hour h
demand_served[(task_id, h)] ∈ [0, MAX_VOLUME]

# Integer: unmet demand
unmet[(task_id, h)] ∈ [0, MAX_VOLUME]
```

### Constraints

1. **Qualification gate** — `task_assigned[(w,d,s,k)]` = 0 if worker not qualified for task k
2. **Availability** — shift window must be within worker's availability for that day
3. **Break exclusion** — task slots cannot overlap break windows (paid or unpaid)
4. **One shift per worker per day** — `sum(shift_selected[(w,d,*,*)]) ≤ 1`
5. **Weekly hours cap** — `sum(selected shift hours) ≤ contracted_hours × 1.2` (20% OT ceiling)
6. **Task slot mutex** — worker can only do one task per time slot
7. **Demand balance** — `demand_served[k,h] + unmet[k,h] = total_demand[k,h]`
8. **Supply coupling** — `demand_served[k,h] ≤ Σ (task_assigned × effective_hours × productivity_rate)`
9. **Indirect headcount** — `Σ(assigned workers for task k in hour h) ≥ required_headcount[k,h]`

### Objective (single minimization)

```python
model.Minimize(
    W1 * sum(unmet.values())        +   # dominant: demand coverage
    W2 * sum(labor_cost.values())   +   # cost
    W3 * sum(no_preference_penalty)     # preference violations
)
# W1 = 1000, W2 = 1, W3 = 10
```

### NL Constraint Overrides → Solver Hooks

When the user adds an NL constraint, the LLM calls one of these tools. The solver builder reads active `ConstraintOverride` rows and applies the corresponding modification before solving.

| Tool name | Args | Solver effect |
|---|---|---|
| `lock_worker_shift` | worker_id, day, start_hour, end_hour | Force shift_selected = 1 for that window |
| `set_min_workers_per_task` | task_id, day, hour_start, hour_end, min_count | Add: Σ(assigned) ≥ min_count |
| `exclude_worker_from_task` | worker_id, task_id | Set all task_assigned[(w,*,*,task_id)] = 0 |
| `scale_demand` | task_id, day, factor | Multiply demand[task_id, h] for that day by factor |
| `set_max_hours_per_day` | worker_id, max_hours | Tighten daily hour cap for that worker |

---

## 8. LLM Integration

### 8.1 Constraint Parsing

```python
# infrastructure/llm/operations/constraint_parser.py

CONSTRAINT_SYSTEM_PROMPT = """
You are a workforce scheduling constraint parser.
Given a plain-English constraint, call the appropriate tool to encode it.
Available workers and tasks are provided in context.
If the constraint is ambiguous or cannot be encoded, return a text explanation instead of a tool call.
"""

CONSTRAINT_TOOLS: list[Tool] = [
    Tool(
        name="lock_worker_shift",
        description="Force a specific worker to work a fixed shift on a given day.",
        parameters={
            "type": "object",
            "properties": {
                "worker_id":   {"type": "string"},
                "day":         {"type": "string", "enum": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]},
                "start_hour":  {"type": "number", "description": "24h float, e.g. 6.0"},
                "end_hour":    {"type": "number"},
            },
            "required": ["worker_id", "day", "start_hour", "end_hour"]
        }
    ),
    Tool(
        name="set_min_workers_per_task",
        description="Enforce a minimum headcount for a task during a time window.",
        parameters={
            "type": "object",
            "properties": {
                "task_id":    {"type": "string"},
                "day":        {"type": "string"},
                "hour_start": {"type": "number"},
                "hour_end":   {"type": "number"},
                "min_count":  {"type": "integer"},
            },
            "required": ["task_id", "day", "hour_start", "hour_end", "min_count"]
        }
    ),
    Tool(
        name="exclude_worker_from_task",
        description="Prevent a worker from being assigned to a specific task all week.",
        parameters={
            "type": "object",
            "properties": {
                "worker_id": {"type": "string"},
                "task_id":   {"type": "string"},
            },
            "required": ["worker_id", "task_id"]
        }
    ),
    Tool(
        name="scale_demand",
        description="Increase or decrease demand for a task on a specific day.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "day":     {"type": "string"},
                "factor":  {"type": "number", "description": "e.g. 1.2 for +20%, 0.8 for -20%"},
            },
            "required": ["task_id", "day", "factor"]
        }
    ),
    Tool(
        name="set_max_hours_per_day",
        description="Cap a worker's hours on any single day.",
        parameters={
            "type": "object",
            "properties": {
                "worker_id": {"type": "string"},
                "max_hours": {"type": "number"},
            },
            "required": ["worker_id", "max_hours"]
        }
    ),
]
```

### 8.2 Insight Generation

Input: `summary_metrics` JSON (~500 tokens). Output: structured `InsightReport`.

```python
# infrastructure/llm/operations/insight_generator.py

INSIGHT_SYSTEM_PROMPT = """
You are a workforce scheduling analyst.
Given solver summary metrics for a weekly schedule, identify the top 3 most important issues
and provide specific, actionable recommendations.
Output JSON matching the InsightReport schema exactly.
Be specific: name the task, day, and magnitude of each problem.
"""

# Output schema passed as a tool (forces structured output)
INSIGHT_TOOL = Tool(
    name="report_insights",
    description="Report structured insights about the schedule.",
    parameters={
        "type": "object",
        "properties": {
            "overall_assessment": {
                "type": "string",
                "description": "2-3 sentence summary of the schedule quality."
            },
            "insights": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "severity":   {"type": "string", "enum": ["high", "medium", "low"]},
                        "area":       {"type": "string", "description": "e.g. 'Receiving coverage — Monday–Thursday'"},
                        "finding":    {"type": "string", "description": "What is wrong, with numbers."},
                        "root_cause": {"type": "string", "description": "Likely reason."},
                        "action":     {"type": "string", "description": "Concrete recommendation."}
                    },
                    "required": ["severity", "area", "finding", "root_cause", "action"]
                }
            }
        },
        "required": ["overall_assessment", "insights"]
    }
)
```

**Example LLM output:**
```json
{
  "overall_assessment": "The schedule covers 84% of total demand. Receiving is the main risk, with consistent shortfalls Monday–Thursday that could delay inbound processing.",
  "insights": [
    {
      "severity": "high",
      "area": "Receiving coverage — Monday to Thursday",
      "finding": "Receiving demand is 30% unmet (18 person-hours) across Mon–Thu, concentrated in the 6am–10am window.",
      "root_cause": "Only 2 Receiving-qualified workers have morning availability; demand requires at least 4.",
      "action": "Add 2 workers with Receiving qualification and morning availability, or shift the Receiving demand window to start at 10am when more qualified workers are available."
    }
  ]
}
```

### 8.3 What-if Delta Explanation

```python
# infrastructure/llm/operations/delta_explainer.py

DELTA_SYSTEM_PROMPT = """
You are a workforce scheduling analyst.
Given two schedule summaries (base and modified) and a description of the change applied,
write a 2–3 sentence plain-English explanation of the impact.
Be specific about numbers: coverage percentages, hours, cost delta.
"""

# Input to model:
# {
#   "change_applied": "Added 3 Receiving-qualified workers with morning availability",
#   "base": { ...summary_metrics... },
#   "modified": { ...summary_metrics... }
# }
```

---

## 9. Frontend Architecture

### Tech Stack
- React 18 + TypeScript
- Vite (build tool)
- shadcn/ui + Tailwind CSS (components + styling)
- Recharts (charts)
- React Query / TanStack Query (server state + polling)
- React Router v6 (routing)
- Zustand (client state: session_id)
- Axios (HTTP client)

### Pages & Routes

| Route | Page | Description |
|---|---|---|
| `/` | `Home` | Scenario list + create button |
| `/scenarios/:id` | `ScenarioEditor` | Tabs: Data upload, Constraints, Settings |
| `/scenarios/:id/runs` | `RunHistory` | List of runs with status |
| `/runs/:runId` | `ResultsView` | Summary metrics + insights + schedule table |
| `/runs/:runId/whatif` | `WhatIfView` | Parameter sliders + compare panel |

### Component Structure

```
src/
  pages/
    Home.tsx
    ScenarioEditor.tsx
    RunHistory.tsx
    ResultsView.tsx
    WhatIfView.tsx

  components/
    layout/
      AppShell.tsx          -- sidebar nav + header
      Breadcrumb.tsx
    scenarios/
      ScenarioCard.tsx
      ScenarioForm.tsx
    upload/
      FileUpload.tsx         -- drag-drop CSV + client-side header validation
      DataPreview.tsx        -- table preview (first 10 rows)
      UploadStatusBadge.tsx  -- uploaded | missing | error
    constraints/
      ConstraintInput.tsx    -- NL textarea + "Preview" button
      ConstraintPreview.tsx  -- parsed constraint card (confirm / discard)
      ConstraintList.tsx     -- active constraints with toggle + delete
    runs/
      RunCard.tsx            -- status chip + timestamps + "View Results" link
      RunStatusBadge.tsx     -- PENDING | RUNNING (spinner) | COMPLETED | FAILED
      TriggerRunButton.tsx   -- disabled if files missing
    results/
      SummaryMetrics.tsx     -- coverage % cards per task family
      CoverageChart.tsx      -- Recharts BarChart: demand vs served by day
      InsightsPanel.tsx      -- insight cards, color-coded by severity
      ScheduleTable.tsx      -- paginated worker × shift × task table
    whatif/
      ParameterPanel.tsx     -- sliders: add N workers, shift demand window, scale demand
      ComparisonTable.tsx    -- side-by-side metrics: base vs modified

  api/
    client.ts                -- axios instance + X-Session-ID header injection
    sessions.ts
    scenarios.ts
    files.ts
    constraints.ts
    runs.ts
    whatif.ts

  hooks/
    useSession.ts            -- init session_id in localStorage on first load
    useRunPoller.ts          -- polls GET /api/runs/:id every 2s until COMPLETED | FAILED
    useScenario.ts           -- scenario detail + file status

  store/
    sessionStore.ts          -- Zustand: { session_id, setSessionId }
```

### Key UX Flows

**Upload flow:** User drops CSV → `FileUpload` validates headers client-side → POST to backend → `DataPreview` shows first 10 rows → `UploadStatusBadge` turns green.

**Constraint flow:** User types NL in `ConstraintInput` → "Preview" → POST `/constraints/preview` → `ConstraintPreview` shows parsed card ("Lock Alice to Tuesday 6am–2pm") → "Confirm" → POST `/constraints` → appears in `ConstraintList`.

**Run flow:** "Run Solver" button → POST `/runs` → `RunStatusBadge` shows PENDING → RUNNING (spinner) → COMPLETED → auto-navigate to `ResultsView`.

**What-if flow:** From `ResultsView` → "Try What-if" → `ParameterPanel` sliders → "Run" → new Run in background → `ComparisonTable` shows delta vs base run.

---

## 10. Async Run Execution

Uses **FastAPI BackgroundTasks** (no Celery — sufficient for demo, simpler deploy).

```python
# routers/runs.py

@router.post("/scenarios/{scenario_id}/runs")
async def trigger_run(
    scenario_id: str,
    background_tasks: BackgroundTasks,
    session_id: str = Header(alias="X-Session-ID"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    scenario = get_scenario_or_404(db, scenario_id, session_id)
    validate_files_uploaded(db, scenario_id)         # all 3 CSVs must exist
    run = create_run(db, scenario)                   # status=PENDING, snapshot input
    background_tasks.add_task(execute_run, run.id, settings)
    return {"run_id": run.id, "status": "PENDING"}


async def execute_run(run_id: str, settings: Settings):
    db = next(get_db())
    update_run_status(db, run_id, "RUNNING")
    try:
        snapshot = load_snapshot(db, run_id)
        problem = build_problem(snapshot)                     # domain type

        engine = create_engine(settings.solver_engine)
        config = SolverConfig(time_limit_s=settings.solver_time_limit_s)
        result = engine.solve(problem, config)                # SolveResult

        metrics = extract_summary_metrics(result)

        provider = create_provider(settings.llm_provider, ...)
        generator = InsightGenerator(provider)
        insights = await generator.generate(metrics)

        save_results(db, run_id, metrics, result, insights)
        update_run_status(db, run_id, "COMPLETED")
    except Exception as e:
        update_run_status(db, run_id, "FAILED", error=str(e))
```

**Frontend polling:** `useRunPoller` calls `GET /api/runs/{run_id}` every 2 seconds until status is `COMPLETED` or `FAILED`, then invalidates the results query.

---

## 11. Summary Metrics Schema

Extracted from solver results. Stored in `run_results.summary_metrics`. Input to LLM insight generation.

```json
{
  "demand_coverage": {
    "Pick":      { "required_h": 120, "served_h": 98,  "pct": 0.82 },
    "Despatch":  { "required_h": 40,  "served_h": 38,  "pct": 0.95 },
    "Receiving": { "required_h": 60,  "served_h": 42,  "pct": 0.70 },
    "Putaway":   { "required_h": 30,  "served_h": 28,  "pct": 0.93 },
    "Indirect":  { "required_h": 80,  "served_h": 75,  "pct": 0.94 }
  },
  "coverage_by_day": {
    "Monday": 0.91, "Tuesday": 0.88, "Wednesday": 0.65,
    "Thursday": 0.72, "Friday": 0.90, "Saturday": 0.83, "Sunday": 0.78
  },
  "workforce": {
    "total_workers": 30,
    "scheduled": 28,
    "unscheduled": 2,
    "over_contracted_hours": [
      { "worker_id": "W01", "name": "Bob", "scheduled_h": 48, "contracted_h": 40 }
    ]
  },
  "cost": {
    "total": 42000,
    "regular_component": 38800,
    "overtime_component": 3200
  },
  "solver": {
    "solve_time_s": 12.3,
    "objective_value": 245.6,
    "mip_gap_pct": 0.01,
    "status": "OPTIMAL"
  }
}
```

---

## 12. Deploy

### Docker Compose (local + production)

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data       # SQLite file + uploaded files persist here
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LLM_PROVIDER=claude
      - SOLVER_ENGINE=cpsat
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://backend:8000
    depends_on:
      - backend
```

### Render (free tier)

- **Backend:** Python web service. Add a persistent disk (1 GB) mounted at `/app/data` for SQLite.
- **Frontend:** Static site. Point build command to `cd frontend && npm run build`, publish dir to `frontend/dist`.
- **Env vars on Render:** `ANTHROPIC_API_KEY`, `LLM_PROVIDER`, `SOLVER_ENGINE`.

### .env template

```bash
# Solver
SOLVER_ENGINE=cpsat
SOLVER_TIME_LIMIT_S=60
SOLVER_MIP_GAP=0.01

# LLM
LLM_PROVIDER=claude
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...

# (optional — only if switching provider)
# LLM_PROVIDER=gemini
# GOOGLE_API_KEY=...

# (optional — Bedrock)
# LLM_PROVIDER=bedrock
# LLM_MODEL=anthropic.claude-sonnet-4-6
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...

# App
DATABASE_URL=sqlite:///./data/app.db
DATA_DIR=./data
```

---

## 13. Project File Structure

```
nl-scheduling-assistant/
│
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app init + router registration
│   │   ├── config.py                        # Settings (pydantic-settings, reads .env)
│   │   ├── database.py                      # SQLAlchemy engine + session + Base
│   │   │
│   │   ├── domain/                          # Pure Python — zero external deps
│   │   │   ├── models.py                    # Worker, Task, Demand, Qualification, Shift
│   │   │   ├── problem.py                   # SchedulingProblem
│   │   │   ├── result.py                    # SolveResult, ScheduleRow, SummaryMetrics
│   │   │   ├── insight.py                   # InsightReport, Insight, Severity
│   │   │   └── constraints.py               # ConstraintOverride domain types
│   │   │
│   │   ├── services/                        # Use-case orchestration
│   │   │   ├── scheduling_service.py        # build problem → engine.solve() → metrics
│   │   │   ├── constraint_service.py        # NL → parse → store overrides
│   │   │   ├── insight_service.py           # metrics → LLM → InsightReport
│   │   │   ├── run_service.py               # run lifecycle + snapshot
│   │   │   ├── scenario_service.py          # scenario CRUD
│   │   │   └── session_service.py           # session init + validation
│   │   │
│   │   ├── infrastructure/
│   │   │   │
│   │   │   ├── solver/
│   │   │   │   ├── base.py                  # SchedulerEngine Protocol + SolverConfig
│   │   │   │   ├── factory.py               # create_engine(name) from REGISTRY
│   │   │   │   ├── cpsat/
│   │   │   │   │   ├── engine.py            # CpSatEngine implements SchedulerEngine
│   │   │   │   │   ├── builder.py           # SchedulingProblem → CP-SAT model + vars
│   │   │   │   │   └── extractor.py         # CP-SAT solution → SolveResult
│   │   │   │   └── greedy/
│   │   │   │       └── engine.py            # GreedyEngine (fast fallback / CI)
│   │   │   │
│   │   │   ├── llm/
│   │   │   │   ├── base.py                  # LLMProvider Protocol, Message, Tool, ToolCall
│   │   │   │   ├── factory.py               # create_provider(name, **kwargs) from REGISTRY
│   │   │   │   ├── claude/
│   │   │   │   │   ├── provider.py          # ClaudeProvider — wraps anthropic SDK
│   │   │   │   │   └── adapter.py           # Tool ↔ Anthropic format conversions
│   │   │   │   ├── gemini/
│   │   │   │   │   ├── provider.py
│   │   │   │   │   └── adapter.py
│   │   │   │   ├── bedrock/
│   │   │   │   │   ├── provider.py          # BedrockProvider — wraps boto3
│   │   │   │   │   └── adapter.py           # per-model format (Claude/Titan/Llama)
│   │   │   │   └── operations/              # LLM tasks; depend on LLMProvider only
│   │   │   │       ├── constraint_parser.py # NL → ConstraintOverride
│   │   │   │       ├── insight_generator.py # SummaryMetrics → InsightReport
│   │   │   │       └── delta_explainer.py   # metrics_a + metrics_b → str
│   │   │   │
│   │   │   └── db/
│   │   │       ├── models.py                # SQLAlchemy ORM models
│   │   │       └── repositories/
│   │   │           ├── session_repo.py
│   │   │           ├── scenario_repo.py
│   │   │           └── run_repo.py
│   │   │
│   │   ├── routers/
│   │   │   ├── sessions.py
│   │   │   ├── scenarios.py
│   │   │   ├── files.py
│   │   │   ├── constraints.py
│   │   │   ├── runs.py
│   │   │   └── whatif.py
│   │   │
│   │   └── schemas/                         # Pydantic request/response models
│   │       ├── sessions.py
│   │       ├── scenarios.py
│   │       ├── files.py
│   │       ├── constraints.py
│   │       ├── runs.py
│   │       └── insights.py
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── pages/ ...
│   │   ├── components/ ...
│   │   ├── api/ ...
│   │   ├── hooks/ ...
│   │   └── store/ ...
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── Dockerfile
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 14. Build Order

### Week 1 — End-to-end skeleton

- [ ] Repo init: monorepo, `.env.example`, `docker-compose.yml` skeleton
- [ ] Backend: FastAPI app + SQLAlchemy + SQLite + Alembic migrations
- [ ] Domain types: `Worker`, `Task`, `Demand`, `SchedulingProblem`, `SolveResult`
- [ ] Session + Scenario CRUD (API + DB)
- [ ] CSV upload → parse → store + download templates
- [ ] CP-SAT solver: `CpSatEngine` — shift generation, basic constraints, solve, extract metrics
- [ ] Run trigger + `execute_run` background task + status polling endpoint
- [ ] Frontend: Vite + React TS + shadcn/ui + Tailwind scaffold
- [ ] Frontend: session init + Home page + ScenarioEditor (upload tab only)
- [ ] Frontend: TriggerRunButton + RunStatusBadge polling

### Week 2 — LLM + Results UI

- [ ] `ClaudeProvider` + adapter (function calling)
- [ ] `ConstraintParser` operation — CONSTRAINT_TOOLS + system prompt
- [ ] Constraint preview/confirm API + ConstraintInput UI flow
- [ ] `InsightGenerator` operation — INSIGHT_TOOL + system prompt
- [ ] Insight generation wired into `execute_run`
- [ ] ResultsView: SummaryMetrics cards + CoverageChart (Recharts)
- [ ] InsightsPanel: severity-coded insight cards
- [ ] ScheduleTable: paginated worker × shift × task
- [ ] RunHistory page

### Week 3 — What-if + Polish + Deploy

- [ ] `DeltaExplainer` operation
- [ ] What-if API: `/whatif` endpoint + `/runs/compare`
- [ ] WhatIfView: ParameterPanel sliders + ComparisonTable
- [ ] Error states, loading skeletons, empty states across all pages
- [ ] Docker Compose full integration test (backend + frontend)
- [ ] Deploy to Render (backend persistent disk + frontend static)
- [ ] README: architecture diagram + demo GIF + local setup instructions
- [ ] **Freeze** — no new features after end of week 3
