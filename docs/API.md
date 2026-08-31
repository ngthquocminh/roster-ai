<!-- generated-by: gsd-doc-writer -->
# ShiftMind API Reference

HTTP API for the ShiftMind backend: create **scenarios** from input fixtures,
trigger solver **runs** that execute off the request thread, fetch **results**
(coverage, cost, schedule), edit constraints in plain English, and fetch a
plain-language **insight** report for a completed run.

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
- **IDs** are opaque 32-char hex strings (UUID4 without dashes), except
  override ids, which are `ov_` + an 8-char content hash (see `OverrideOut`
  below).
- **Timestamps** are ISO-8601 UTC strings (e.g. `2026-06-07T19:57:46.123456+00:00`).
- **Time is in hours from the scenario horizon start** in schedule rows
  (`start_h`, `end_h`); e.g. day-2 06:00 = `30.0`.
- **Authentication:** none. Every route is unauthenticated; there is no API
  key, session, or bearer-token check anywhere in the request path. This is
  consistent with the CORS posture below (`allow_credentials` is left at its
  default `False` — the app never expects a cookie or `Authorization`
  header). Do not expose this API on an untrusted network without adding an
  auth layer in front of it.
- **CORS:** the FastAPI app in `backend/api/main.py` only allows browser
  requests from the origins listed in `CORS_ORIGINS` (`GET`/`POST` only). See
  [Configuration → CORS configuration](CONFIGURATION.md#cors-configuration)
  for the env var, defaults, and the at-import-time resolution caveat — not
  duplicated here.
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
proving cost-optimality it returns the best schedule found so far, with
`solver_status = UNKNOWN`. `FAILED` is reserved for unexpected errors (bad
input, exceptions); the reason is in `error`.

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
a scenario's `fixture`. Returns `[]` if the configured data directory does not
exist.

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
- `400` — `fixture` is unknown: absent from the data directory, or an
  absolute/traversal path that resolves outside it.
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

### `GET /scenarios/{scenario_id}/overrides`

Fetch a scenario's persisted overrides — every constraint currently applied.
Returned in the stored dict's natural insertion order (first-applied-first,
stable across idempotent re-applies); the server never re-sorts.

**200** — array of `OverrideOut` · **404** — scenario not found.

```json
[
  {
    "id": "ov_1a2b3c4d",
    "tool": "set_min_workers_per_task",
    "args": { "task_id": "T123", "n": 2 },
    "parsed_constraint": "At least 2 workers on Pick (every demanded hour)"
  }
]
```

`parsed_constraint` is nullable: overrides persisted before this field existed
(legacy entries) deserialize with `parsed_constraint: null` rather than
failing — the endpoint never 500s on old data.

---

### `POST /constraints`

Parse a plain-English scheduling constraint against a scenario, validate it,
and persist the entries that pass. This is a **top-level** route (**not**
nested under `/scenarios/{id}`) — `scenario_id` is a body field, not a path
parameter. Does **not** trigger a solve; trigger a run separately via
`POST /scenarios/{id}/runs` to see the effect.

**Request body** — `ConstraintParseRequest`

| field | type | required | rules |
|---|---|---|---|
| `scenario_id` | string | yes | non-empty; must reference an existing scenario |
| `text` | string | yes | 1–2000 chars |

```bash
curl -X POST localhost:8000/constraints \
  -H 'content-type: application/json' \
  -d '{"scenario_id":"86a1...","text":"keep at least 2 workers on Pick at all times"}'
```

**200** — `ConstraintParseResponse`, always `200` regardless of how many (or
how few) constraints were understood. The parser may emit more than one tool
call per request (a sentence can express multiple constraints), and each call
is validated independently — a per-call failure (unknown member/task
reference, out-of-bounds argument, non-positive numeric value) lands in
`rejected[]` rather than failing the whole request. This is a **partial-apply
contract**: only entries in `applied[]` are persisted to the scenario's
`overrides`; `rejected[]` entries and an ambiguous/unparseable
`clarification_needed` question are response-only and never stored.
`no_constraint_found` is `true` only when the model produced no tool call at
all and no clarification question either (e.g. the text wasn't a scheduling
constraint).

```json
{
  "applied": [
    {
      "id": "ov_1a2b3c4d",
      "tool": "set_min_workers_per_task",
      "args": { "task_id": "T123", "n": 2 },
      "parsed_constraint": "At least 2 workers on Pick (every demanded hour)"
    }
  ],
  "rejected": [
    { "tool": "scale_demand", "error": "factor must be positive, got -1. Use a value > 0 (e.g. 1.5 to scale demand up by 50%)." }
  ],
  "clarification_needed": null,
  "no_constraint_found": false
}
```

Five tools are supported: `set_min_workers_per_task`, `scale_demand`,
`lock_worker_shift`, `exclude_worker_from_task`, `set_max_hours`. All resolve
human-readable member/task references (name or id, case-insensitive substring
match) against the scenario's real fixture data, and are applied as **soft**
solver penalties only — never able to make a solve infeasible.

**Errors**
- `404` — scenario not found (or the scenario references a fixture path that
  no longer resolves).
- `503` — LLM provider unavailable (upstream auth/quota/network failure).
- `422` — body fails validation (missing `scenario_id`/`text`, `text` too long).

---

### `POST /scenarios/{scenario_id}/runs`

Create and start a run for the scenario. Returns immediately with a `PENDING`
run; the solve proceeds in the background on a single-worker thread pool
(solves are serialized — at most one in flight at a time).

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

Fetch the solved schedule and metrics.

> **Contract: strict — 409 before completion.** This endpoint raises `409`
> for any non-`COMPLETED` status (`PENDING`, `RUNNING`, or `FAILED`). Contrast
> this with `GET /runs/{id}/insights` immediately below, which returns `200`
> in the equivalent "not ready yet" case. The two endpoints use **different**
> not-ready conventions on purpose — clients must not assume they behave the
> same way.

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
  ],
  "warnings": []
}
```

---

### `GET /runs/{run_id}/insights`

Fetch (or, on first call, generate) a plain-language insight report for a
run. Runs synchronously on FastAPI's own thread pool — a separate pool from
the single-worker solve pool, so an insight request never competes with, or
blocks, an in-flight solve. The generated report is cached on the run
(`runs.insight_json`); a second call for the same run returns the cached
report without calling the LLM provider again (at most one generation per
run).

```bash
curl localhost:8000/runs/1bb1.../insights
```

**200** — `InsightOut`, **always `200`, never `409`**. This is the opposite
convention from `GET /runs/{id}/result` above: clients must branch on the
`ready` field in the body, **never** on the HTTP status code. Two distinct
body shapes share this one status code:

- **Ready** (`ready: true`) — the run is `COMPLETED` and a report is
  available (freshly generated or returned from cache):
  ```json
  { "ready": true, "run_id": "1bb1...", "report": "Overall, coverage reached 68%..." }
  ```
- **Not ready** (`ready: false`) — the run has not reached `COMPLETED` yet.
  This is a **deliberate `200`, not a `409`**:
  ```json
  { "ready": false, "run_id": "1bb1...", "status": "RUNNING", "reason": "Insights available only for COMPLETED runs (status: RUNNING)" }
  ```

Every number the report cites is checked against the run's own metrics (a
numeric-grounding guard, with a small rounding tolerance): any token that
isn't a real, run-derived value is treated as a fabrication and the request
fails with `502` rather than returning an untrustworthy report. A report is
only cached once it passes this check — a rejected report is never persisted
and never returned again on a later call (the next call regenerates from
scratch).

**Errors**
- `404` — run not found.
- `502` — the LLM provider failed, or the grounding guard rejected the
  generated report as containing an ungrounded number. Nothing is cached in
  either case, and the run's status/result are untouched — an insight
  failure can never invalidate a completed schedule.

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
| `warnings` | array of string | degenerate-solve caveats (e.g. a family with real demand but zero served hours); always present, `[]` when there are none |

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

### `ConstraintParseResponse`
| field | type | notes |
|---|---|---|
| `applied` | array of `AppliedConstraint` | validated and persisted to the scenario |
| `rejected` | array of `RejectedConstraint` | failed validation; not persisted |
| `clarification_needed` | string \| null | a question, if the text was ambiguous |
| `no_constraint_found` | boolean | true if no tool call and no clarification signal |

**`AppliedConstraint`**
| field | type | notes |
|---|---|---|
| `id` | string | content-hash override id (`ov_` + 8-char sha256 prefix of `tool` + canonical args); stable across re-submissions of the same constraint |
| `tool` | string | one of the five solver-hook tool names |
| `args` | object | resolved, validated tool arguments (real task/member ids) |
| `parsed_constraint` | string | human-readable echo of what was understood |

### `OverrideOut`
| field | type | notes |
|---|---|---|
| `id` | string | content-hash override id (`ov_...`), same id space as `AppliedConstraint.id` |
| `tool` | string | one of the five solver-hook tool names |
| `args` | object | resolved, validated tool arguments (real task/member ids) |
| `parsed_constraint` | string \| null | human-readable echo; `null` for overrides persisted before this field existed (legacy entries) |

**`RejectedConstraint`**
| field | type | notes |
|---|---|---|
| `tool` | string | tool name the call would have used |
| `error` | string | plain-English reason, naming the offending reference/argument |

### `InsightOut`
| field | type | notes |
|---|---|---|
| `ready` | boolean | whether a report is available — branch on this, not on status code |
| `run_id` | string | |
| `report` | string \| null | present when `ready` is true |
| `status` | string \| null | present when `ready` is false — the run's current status |
| `reason` | string \| null | present when `ready` is false |

---

## Status code summary

| Code | Meaning |
|---|---|
| `200` | OK, including `GET /runs/{id}/insights` when the body carries `ready: false` |
| `201` | Created (scenario, run) |
| `400` | Bad request (unknown or path-escaping `fixture`) |
| `404` | Resource not found (scenario, run) |
| `409` | `GET /runs/{id}/result` requested before the run reached `COMPLETED` — **not** used by `GET /runs/{id}/insights`, which uses `200` + `ready: false` for the same "not there yet" case |
| `422` | Request body failed validation |
| `502` | Insight generation failed (LLM provider failure or grounding-guard rejection) |
| `503` | LLM provider unavailable (constraint parsing) |

## Approval requests

- `POST /api/v1/approvals` creates a pending approval for one feasible candidate. It requires an `Idempotency-Key` header and returns the existing binding on a replay.
- `GET /api/v1/approvals/{approval_id}` reads one visible binding.
- `GET /api/v1/approvals?schedule_run_id={id}` lists bindings for a run.
- `GET /api/v1/approvals/provenance?schedule_run_id={id}` reads the complete, site-scoped
  decision path for a run. It replays committed run, conversation, approval, audit, and current
  baseline records without writing or recomputing any figure. This is the authoritative reader
  for the audit `parameter_hash` and `consequence_hash` named below; protected missing and
  cross-site runs both return the same `schedule_run_not_found` response.
- `POST /api/v1/approvals/{approval_id}/decision` accepts `{ "decision": "approve" | "reject", "expected_resource_version": number }` with an `Idempotency-Key`. A valid approval atomically returns `200 consumed`, moves the baseline pointer once, records `approval_consumed`, and resumes an approval-backed agent run after commit. Rejection commits `200`; stale and expired terminalizations commit then return `409`.

Problem bodies on the decision route carry AD-13's literal `expected` and
`current` objects **when there is context to carry** — a version, state, or
policy the caller can compare. Codes describing a condition with nothing to
compare (`approval_not_found`, `approval_not_granted`)
omit both keys rather than publishing an empty object; both fields are declared
optional on `ProblemDetailsV1` and generated into the client types.

`ApprovalOut` publishes the identifiers, versions, consequence summary,
`created_at` and `expires_at` that the review surface renders. It deliberately
does **not** publish `parameter_hash` / `consequence_hash`: AC1 asks for the
material parameters themselves, which the run, candidate and baseline versions
already are, and provenance reads the digests from `audit_event`, which carries
both.

The POST can return RFC 7807 problem codes with these statuses (AD-13 keeps
denied, stale, missing, and invalid distinct):

| Code | Status | Meaning |
|---|---|---|
| `approval_not_granted` | 403 | Policy does not grant baseline approval |
| `candidate_not_found` | 404 | No candidate is visible in this site |
| `candidate_not_promotable` | 409 | The run is not `solver_completed`, or has no feasible candidate |
| `stale_resource_version` | 409 | The run changed since the version you pinned |
| `stale_baseline_version` | 409 | The current baseline is not the one you expected |
| `approval_already_pending` | 409 | A pending binding already exists for this candidate |
| `approval_not_found` | 404 | No approval binding is visible in this site |
| `approval_not_pending` | 409 | The binding already reached a terminal state |
| `approval_expired` | 409 | The decision attempt committed expiry terminalization |
| `approval_stale` | 409 | The decision attempt committed stale terminalization |
| `agent_run_not_cancellable` | 409 | The agent run awaiting this approval left `approval_required`; nothing was written |
| `stale_baseline_version` | 409 | The site baseline moved while the approval was being consumed; the whole promotion bundle rolled back and the binding stays `pending` |
| `approval_payload_unreadable` | 500 | An agent-backed binding's stored `pending_payload` is absent or does not carry exactly one pending call, so the resumed turn cannot be driven; the promotion rolled back |
| `idempotency_key_conflict` | 409 | The key was reused with a different body |
| `invalid_approval_command` | 422 | The command is otherwise unusable |

Pre-write `approval_not_pending` and `stale_resource_version` refusals against a
binding resolved in the current site append an authoritative `approval_denied`
row (`success=false`) keyed independently by `(site_id, attempt_id)`. Missing or
cross-site bindings and the feature-policy pre-check write no denial row.

Creating a request writes governance and audit records but never promotes the
candidate or changes the baseline pointer.

The provenance GET has one RFC 7807 problem code:

| Code | Status | Meaning |
|---|---|---|
| `schedule_run_not_found` | 404 | No schedule run with that identifier is visible in the current site |

Approving one **does** move the pointer, and that has a documented effect on run
results. A completed run's result freezes the baseline pointer that was live when
it was snapshotted, and the authoritative baseline **assignment** supply is not
wired yet, so from the first promotion onward the baseline half of the comparison
cannot be computed. The result endpoint does **not** fail for this: it returns
`200` with `comparison: null` and a literal `comparison_unavailable_reason`, so
the run, the candidate schedule, and any pending approval on it stay readable and
actionable. `current_baseline_schedule_version` is carried on the result itself
(not only on the comparison) so a new approval can still be requested while the
comparison is unavailable. An unreadable baseline is never rendered as an empty
one — the comparison is withheld, not fabricated.

A binding whose `expires_at` has passed is PRESENTED as `expired` by every read
path, while the stored row stays `pending`; the terminal `expired` state is
materialised only inside a decision transaction (Story 4.2). Reads never write.

## Configuration

Every backend environment variable that affects this API (`ROSTERAI_DB`,
`ROSTERAI_DATA_DIR`, `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY`,
`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `CORS_ORIGINS`) is documented in
[Configuration](CONFIGURATION.md), including defaults, required-vs-optional
status, and the CORS at-import-time resolution caveat. That table is the
source of truth — it is not duplicated here.
