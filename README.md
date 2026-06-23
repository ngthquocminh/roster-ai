# ShiftMind

> AI-powered workforce scheduling — natural language constraints + optimization solver

**Repo:** `rosterai` · **Product name:** ShiftMind

A workforce scheduling assistant for distribution-centre operations. A constraint
solver (the **Scheduling Engine**) produces a weekly schedule from workforce +
demand data; later phases add a FastAPI backend, natural-language constraint
editing + LLM insights, and a React UI.

The Scheduling Engine is an open-source-solver (OR-Tools CP-SAT) reimplementation
of the core logic of a production weekly scheduling model. See
[`docs/design.md`](docs/design.md) for the full system design and phase plan.

## Status

**Phase 1 — Scheduling Engine + data spine: complete.** Loads a real-schema
weekly input, solves a lexicographic (unmet → cost) model, and reports coverage,
cost, and a schedule.

**Phase 2 — Backend skeleton: complete.** A FastAPI app over SQLite: create
scenarios from a fixture, trigger runs that solve in a worker thread (off the
event loop), poll status, and fetch results. LLM and frontend are future phases.

## Layout

```
backend/      # domain/ engine/ ingest/ config/ fixtures/ run.py tests/
              # api/ services/ store/ settings.py   (Phase 2 backend)
data/         # sample_tiny_input.json  (small coherent fixture, real schema)
docs/         # all project docs:
              #   design.md   — system design (architecture, the model, decisions)
              #   PLAN.md     — build plan + phase status tracker
              #   API.md      — HTTP API reference
              #   vision.md   — original project idea, archived for reference
```

## Documentation

- [`docs/design.md`](docs/design.md) — system design and architecture (start here).
- [`docs/API.md`](docs/API.md) — HTTP API reference.
- [`docs/PLAN.md`](docs/PLAN.md) — phase plan and status.
- [`docs/vision.md`](docs/vision.md) — the original idea, kept for reference (not maintained).

## Quick start

Dependencies are managed with [uv](https://docs.astral.sh/uv/). From `backend/`:

```bash
cd backend
uv sync                                       # create .venv + install (uses uv.lock)

uv run python run.py ../data/sample_tiny_input.json   # solve the fixture (CLI)
uv run pytest -q                              # run the tests
```

Regenerate the small fixture from a full weekly input (stdlib only, no solver):

```bash
uv run python fixtures/build_short_input.py
```

### Backend API (Phase 2)

```bash
cd backend
uv run uvicorn api.main:app --reload          # http://127.0.0.1:8000  (/docs for Swagger)
```

Lifecycle: list fixtures → create a scenario → trigger a run → poll → get result.

```bash
curl localhost:8000/fixtures
curl -X POST localhost:8000/scenarios \
  -H 'content-type: application/json' \
  -d '{"name":"week1","fixture":"sample_tiny_input.json","time_limit_s":60}'
curl -X POST localhost:8000/scenarios/<scenario_id>/runs   # -> run (PENDING)
curl localhost:8000/runs/<run_id>                          # poll until COMPLETED
curl localhost:8000/runs/<run_id>/result                   # metrics + schedule
```

The solve runs in a worker thread, so the API stays responsive during a run; a
run finishes `COMPLETED` even if the solver hits its time limit (it reports the
unmet-optimal schedule with `solver_status` `UNKNOWN`). SQLite lives at
`backend/var/rosterai.db` (override with `ROSTERAI_DB`).

Full endpoint/model reference: [`docs/API.md`](docs/API.md). Live schema at
`/docs` (Swagger), `/redoc`, and `/openapi.json` when the server is running.

## Notes

- ortools is pinned to `9.11.4210`: the 9.15 wheel segfaults on the dev machine.
- The fixture covers the **full scenario week**. It is shrunk *vertically*
  (fewer tasks/members + demand scaling), not by truncating days, so coverage
  reports span all seven days. `build_short_input.py` exposes `HORIZON_DAYS`
  (`None` = full week; set an int only to truncate for a quick probe).
- The full-week instance solves the primary objective (unmet labour-hours) in
  ~20s; proving cost-optimality takes longer (~2 min). With a short time limit
  the engine returns the unmet-optimal schedule (cost not yet minimized) rather
  than failing. Pass a time limit to the CLI: `run.py <input> cpsat <seconds>`.
- Deployment target is AWS (frontend → S3/CloudFront; backend container →
  ECR + App Runner/ECS/EC2 — container compute, not Lambda).
