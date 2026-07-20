<!-- generated-by: gsd-doc-writer -->
# ShiftMind

> AI-powered workforce scheduling — natural language constraints + optimization solver + a browser UI

**Repo:** `rosterai` · **Product name:** ShiftMind

ShiftMind is a workforce scheduling assistant for distribution-centre operations.
A constraint solver (the **Scheduling Engine**, Google OR-Tools CP-SAT) produces a
weekly schedule from workforce + demand data. A FastAPI backend serves scenarios
and runs over HTTP. An **LLM layer** lets a user describe a scheduling constraint
change in plain English — it's validated against the real scenario and applied to
the solve as a soft penalty (never able to make a solve infeasible) — and turns
run metrics into a grounded, plain-language insight report on demand. A React
frontend makes the whole thing usable end-to-end from a browser, with no need to
touch curl or raw JSON.

The Scheduling Engine is an open-source-solver (OR-Tools CP-SAT) reimplementation
of the core logic of a production weekly scheduling model. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system design.

## Status

**Scheduling Engine + backend: complete.** Loads a real-schema weekly input,
solves a lexicographic (unmet → cost) model, and serves scenarios/runs over a
FastAPI + SQLite (WAL) backend. Solves run in a worker thread off the event loop.

**LLM layer: complete.** Plain-English constraint editing via five validated
solver-hook tools (`lock_worker_shift`, `set_min_workers_per_task`,
`exclude_worker_from_task`, `scale_demand`, `set_max_hours`) applied as soft
penalties only, plus an on-demand, metric-grounded insight report generated as a
separate post-run step (an LLM failure never invalidates a completed schedule).
Three providers behind an `LLMProvider` Protocol seam: `stub` (default, keyless,
deterministic — drives all default CI), `gemini` (Google Gemini via
`google-genai`), and `openrouter` (OpenAI-compatible SDK).

**Frontend: complete.** A Vite + React 19 + TypeScript SPA under `frontend/`,
typed against `docs/API.md` via OpenAPI codegen: create a scenario from a
fixture, shape it with plain-English constraints, trigger a solve and watch it
run, and read the resulting schedule, coverage, and insight report — all from a
browser.

Active/deferred work (input upload, what-if compare, run cancellation, a known
grounding-guard edge case) is tracked in `.planning/`, not here — see
[`docs/README.md`](docs/README.md) for the doc ownership split.

## Layout

```
backend/      # domain/ engine/ ingest/ config/ fixtures/ run.py tests/
              # api/ services/ store/ settings.py llm/ scripts/
frontend/     # Vite + React + TypeScript SPA (src/api src/hooks src/routes
              # src/components src/lib), typed against the backend's OpenAPI spec
data/         # sample_tiny_input.json  (small coherent fixture, real schema)
docs/         # all project docs:
              #   README.md   — one-owner-per-audience boundary statement
              #   ARCHITECTURE.md — system design (architecture, the model, decisions)
              #   API.md      — HTTP API reference
              #   vision.md   — original project idea, archived for reference
              #   archive/    — superseded Phase 1-2 plan docs (historical)
```

Project/phase status lives in `.planning/`, not `docs/` — see `docs/README.md`
for the ownership split.

## Documentation

- [`docs/README.md`](docs/README.md) — start here: which doc owns what.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design and architecture.
- [`docs/API.md`](docs/API.md) — HTTP API reference.
- [`docs/vision.md`](docs/vision.md) — the original idea, kept for reference (not maintained).

## Quick start

### Backend

Dependencies are managed with [uv](https://docs.astral.sh/uv/). From `backend/`:

```bash
cd backend
uv sync                                       # create .venv + install (uses uv.lock)

uv run python run.py ../data/sample_tiny_input.json   # solve the fixture (CLI)
uv run pytest -q                              # run the tests (stub LLM provider, no network)
```

Regenerate the small fixture from a full weekly input (stdlib only, no solver):

```bash
uv run python fixtures/build_short_input.py
```

Start the API:

```bash
cd backend
uv run uvicorn api.main:app --reload          # http://127.0.0.1:8000  (/docs for Swagger)
```

Lifecycle: list fixtures → create a scenario → trigger a run → poll → get result;
optionally, apply a plain-English constraint before running, and fetch an insight
report afterward.

```bash
curl localhost:8000/fixtures
curl -X POST localhost:8000/scenarios \
  -H 'content-type: application/json' \
  -d '{"name":"week1","fixture":"sample_tiny_input.json","time_limit_s":60}'
curl -X POST localhost:8000/constraints \
  -H 'content-type: application/json' \
  -d '{"scenario_id":"<scenario_id>","text":"give Alice at least 2 workers on packing"}'
curl -X POST localhost:8000/scenarios/<scenario_id>/runs   # -> run (PENDING)
curl localhost:8000/runs/<run_id>                          # poll until COMPLETED
curl localhost:8000/runs/<run_id>/result                   # metrics + schedule
curl localhost:8000/runs/<run_id>/insights                 # on-demand NL insight report
```

The solve runs in a worker thread, so the API stays responsive during a run; a
run finishes `COMPLETED` even if the solver hits its time limit (it reports the
unmet-optimal schedule with `solver_status` `UNKNOWN`). SQLite lives at
`backend/var/rosterai.db` (override with `ROSTERAI_DB`).

By default `LLM_PROVIDER=stub`, so constraint parsing and insight generation work
out of the box with no API key, using a deterministic regex-routed stub. Set
`LLM_PROVIDER=gemini` (with `GEMINI_API_KEY`) or `LLM_PROVIDER=openrouter` (with
`OPENROUTER_API_KEY`) for real NL parsing and generated insight prose.

Full endpoint/model reference: [`docs/API.md`](docs/API.md). Live schema at
`/docs` (Swagger), `/redoc`, and `/openapi.json` when the server is running.

### Frontend

The frontend is a Vite + React + TypeScript SPA under `frontend/` and needs the
backend running (see above) plus its base URL configured. From `frontend/`:

```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=http://127.0.0.1:8000" > .env    # backend origin; fails loudly if unset
npm run dev                                   # http://localhost:5173
```

Other scripts (from `frontend/package.json`):

```bash
npm run build       # tsc -b && vite build -> frontend/dist/
npm run preview      # serve the production build locally
npm run typecheck    # tsc --noEmit
npm test             # vitest run
npm run lint         # oxlint
npm run codegen       # regenerate src/api/schema.d.ts from the backend's OpenAPI spec
```

The backend must allow the frontend's origin via CORS — `CORS_ORIGINS` defaults
to `http://localhost:5173,http://localhost:4173` (Vite dev/preview), so the
default dev setup works without extra configuration.

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
- All NL-derived constraints are applied as **soft** penalties only — they can
  never make a solve infeasible — and are validated against the real scenario's
  member/task IDs before being accepted.
- Insight generation is a separate, on-demand step after a run completes, and is
  cached (`runs.insight_json`); an LLM failure never invalidates a completed
  schedule.
- No auth exists anywhere in the stack; every scenario is globally visible to
  any caller. Out of scope until a public/shared deploy makes it necessary.
- Deployment target is AWS (frontend → S3/CloudFront; backend container →
  ECR + App Runner/ECS/EC2 — container compute, not Lambda). <!-- VERIFY: no deploy config currently exists in-repo; confirm target before acting on it -->
