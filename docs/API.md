# ShiftMind API Reference

HTTP API for the ShiftMind backend (Phase 2): create **scenarios** from input
fixtures, trigger solver **runs** that execute off the request thread, and fetch
**results** (coverage, cost, schedule).

This document is the human-readable contract. The live, machine-readable schema
is always available from the running app:

- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI JSON: `GET /openapi.json`

## Running

```bash
cd backend
uv run uvicorn api.main:app --reload      # http://127.0.0.1:8000
```

Base URL in examples: `http://127.0.0.1:8000`.

## Conventions

- **Content type:** requests and responses are `application/json`.
- **IDs** are opaque 32-char hex strings (UUID4 without dashes).
- **Timestamps** are ISO-8601 UTC strings (e.g. `2026-06-07T19:57:46.123456+00:00`).
- **Time is in hours from the scenario horizon start** in schedule rows
  (`start_h`, `end_h`); e.g. day-2 06:00 = `30.0`.
- **Errors** use the standard FastAPI shape:
  ```json
  { "detail": "Scenario not found" }
  ```
  Request-body validation failures return `422` with a structured `detail`
  array (field location, message, type).

---

## The run lifecycle

A run is created immediately and solved asynchronously in a background worker
thread (solves are CPU-heavy and can take seconds to minutes). Poll the run
until it reaches a terminal state.

```
POST /scenarios/{id}/runs
        │  (returns at once)
        ▼
     PENDING ──► RUNNING ──► COMPLETED   → GET /runs/{id}/result
                         └─► FAILED      → see `error`
```

- `status` — the **run** state: `PENDING` | `RUNNING` | `COMPLETED` | `FAILED`.
- `solver_status` — the **solver** outcome, set when a run reaches `COMPLETED`:
  `OPTIMAL` | `FEASIBLE` | `UNKNOWN` | `INFEASIBLE` | `MODEL_INVALID`.

A time-limited solve still ends `COMPLETED`: if the solver hits its limit before
proving cost-optimality it returns the unmet-optimal schedule with
`solver_status = UNKNOWN`. `FAILED` is reserved for unexpected errors (bad input,
exceptions); the reason is in `error`.

---

## Endpoints

### `GET /health`

Liveness probe.

**200**
```json
{ "status": "ok" }
```

---

### `GET /fixtures`

List input files available in the data directory (`*.json`). Use one of these as
a scenario's `fixture`.

**200**
```json
["sample_tiny_input.json"]
```

---

### `POST /scenarios`

Create a scenario bound to a fixture and a solver time limit.

**Request body** — `ScenarioCreate`

| field | type | required | rules | default |
|---|---|---|---|---|
| `name` | string | yes | non-empty | — |
| `fixture` | string | yes | non-empty; must exist in the data dir | — |
| `time_limit_s` | number | no | `> 0` | `60` |

```bash
curl -X POST localhost:8000/scenarios \
  -H 'content-type: application/json' \
  -d '{"name":"week1","fixture":"sample_tiny_input.json","time_limit_s":60}'
```

**201** — `ScenarioOut`
```json
{
  "id": "86a144ec8c1b4a738b3ed5c9155b8752",
  "name": "week1",
  "fixture": "sample_tiny_input.json",
  "time_limit_s": 60.0,
  "created_at": "2026-06-07T19:55:01.000000+00:00"
}
```

**Errors**
- `400` — `fixture` does not exist in the data directory.
- `422` — body fails validation (missing/empty `name`, `time_limit_s <= 0`).

---

### `GET /scenarios`

List all scenarios, newest first.

**200** — array of `ScenarioOut`.

---

### `GET /scenarios/{scenario_id}`

Fetch one scenario.

**200** — `ScenarioOut` · **404** — not found.

---

### `POST /scenarios/{scenario_id}/runs`

Create and start a run for the scenario. Returns immediately with a `PENDING`
run; the solve proceeds in the background.

```bash
curl -X POST localhost:8000/scenarios/86a1.../runs
```

**201** — `RunOut`
```json
{
  "id": "1bb170451f1d427ebbd0154da8ab4c50",
  "scenario_id": "86a144ec8c1b4a738b3ed5c9155b8752",
  "status": "PENDING",
  "created_at": "2026-06-07T19:57:45.000000+00:00",
  "started_at": null,
  "finished_at": null,
  "solver_status": null,
  "error": null
}
```

**404** — scenario not found.

---

### `GET /scenarios/{scenario_id}/runs`

List runs for a scenario, newest first.

**200** — array of `RunOut`.

---

### `GET /runs/{run_id}`

Fetch a run's current state. Poll this until `status` is `COMPLETED` or `FAILED`.

**200** — `RunOut` (a completed run)
```json
{
  "id": "1bb170451f1d427ebbd0154da8ab4c50",
  "scenario_id": "86a144ec8c1b4a738b3ed5c9155b8752",
  "status": "COMPLETED",
  "created_at": "2026-06-07T19:57:45.000000+00:00",
  "started_at": "2026-06-07T19:57:46.000000+00:00",
  "finished_at": "2026-06-07T19:57:57.000000+00:00",
  "solver_status": "UNKNOWN",
  "error": null
}
```

**404** — run not found.

---

### `GET /runs/{run_id}/result`

Fetch the solved schedule and metrics. Only available once the run is
`COMPLETED`.

**200** — `RunResult` (see model below).

**Errors**
- `404` — run not found.
- `409` — run is not `COMPLETED` yet (still `PENDING`/`RUNNING`, or `FAILED`).
  `detail` includes the current status.

```json
{
  "status": "UNKNOWN",
  "metrics": {
    "total_cost": 11806.41,
    "total_unmet_hours": 212.13,
    "scheduled_shifts": 40,
    "scheduled_members": 10,
    "coverage_by_function": {
      "Pick":      { "required_h": 265.5, "served_h": 94.1, "pct": 0.354 },
      "Despatch":  { "required_h": 69.4,  "served_h": 44.4, "pct": 0.640 },
      "Putaways":  { "required_h": 54.0,  "served_h": 53.0, "pct": 0.981 },
      "Receiving": { "required_h": 16.5,  "served_h": 1.7,  "pct": 0.104 }
    },
    "coverage_by_day": { "0": 0.61, "1": 0.50, "2": 0.48, "3": 0.46,
                          "4": 0.41, "5": 0.34, "6": 0.63 }
  },
  "stats": {
    "status": "UNKNOWN",
    "wall_time_s": 8.0,
    "unmet_objective_hours": 212.13,
    "cost_objective": 11806.41
  },
  "schedule": [
    {
      "contact_id": "AC0D87",
      "member_name": "Rhiannon Hansen",
      "task_id": "T123",
      "function": "Pick",
      "shift_id": "24_AC0D87_55",
      "start_h": 5.5,
      "end_h": 10.9
    }
  ]
}
```

---

## Data models

### `ScenarioOut`
| field | type | notes |
|---|---|---|
| `id` | string | scenario id |
| `name` | string | |
| `fixture` | string | input file name |
| `time_limit_s` | number | solver time budget per run |
| `created_at` | string | ISO-8601 UTC |

### `RunOut`
| field | type | notes |
|---|---|---|
| `id` | string | run id |
| `scenario_id` | string | parent scenario |
| `status` | string | `PENDING`/`RUNNING`/`COMPLETED`/`FAILED` |
| `created_at` | string | ISO-8601 UTC |
| `started_at` | string \| null | set when `RUNNING` |
| `finished_at` | string \| null | set when terminal |
| `solver_status` | string \| null | set when `COMPLETED` |
| `error` | string \| null | set when `FAILED` |

### `RunResult`
| field | type | notes |
|---|---|---|
| `status` | string | solver status (mirrors `solver_status`) |
| `metrics` | object | see below |
| `stats` | object | `status`, `wall_time_s`, `unmet_objective_hours`, `cost_objective` |
| `schedule` | array | schedule rows |

**`metrics`**
| field | type | notes |
|---|---|---|
| `total_cost` | number \| null | total wage cost; `null` if not computed |
| `total_unmet_hours` | number \| null | unmet labour-hours |
| `scheduled_shifts` | integer | distinct selected shifts |
| `scheduled_members` | integer | distinct members used |
| `coverage_by_function` | object | function → `{ required_h, served_h, pct }` |
| `coverage_by_day` | object | day index (string) → fraction covered (0–1) |

> Numeric fields may be `null`: the solver can report a non-finite cost (e.g.
> when a time-limited solve doesn't minimize cost), which is serialized as `null`
> rather than invalid JSON `NaN`.

**`schedule[]` row**
| field | type | notes |
|---|---|---|
| `contact_id` | string | member id |
| `member_name` | string | |
| `task_id` | string | |
| `function` | string | task's function (e.g. Pick) |
| `shift_id` | string | engine-assigned shift identifier |
| `start_h` | number | hours from horizon start |
| `end_h` | number | hours from horizon start |

---

## Status code summary

| Code | Meaning |
|---|---|
| `200` | OK |
| `201` | Created (scenario, run) |
| `400` | Bad request (unknown fixture) |
| `404` | Resource not found (scenario, run) |
| `409` | Run result requested before completion |
| `422` | Request body failed validation |

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `ROSTERAI_DB` | `backend/var/rosterai.db` | SQLite database file |
| `ROSTERAI_DATA_DIR` | `<repo>/data` | directory scanned by `GET /fixtures` |
