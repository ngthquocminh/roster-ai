# ShiftMind

> AI-powered workforce scheduling — natural language constraints + optimization solver

**Repo:** `rosterai` · **Product name:** ShiftMind

A workforce scheduling assistant for distribution-centre operations. A constraint
solver (the **Scheduling Engine**) produces a weekly schedule from workforce +
demand data; later phases add a FastAPI backend, natural-language constraint
editing + LLM insights, and a React UI.

The Scheduling Engine is an open-source-solver (OR-Tools CP-SAT) reimplementation
of the core logic of a production weekly scheduling model. See [`design.md`](design.md)
for the full system design and phase plan.

## Status

**Phase 1 — Scheduling Engine + data spine: complete.** Loads a real-schema
weekly input, solves a lexicographic (unmet → cost) model, and reports coverage,
cost, and a schedule. Backend API, LLM, and frontend are future phases.

## Layout

```
backend/      # Phase 1 engine: domain/ engine/ ingest/ config/ fixtures/ run.py tests/
data/         # sample_tiny_input.json  (small coherent fixture, real schema)
design.md     # full system design + phase plan
```

## Quick start

Dependencies are managed with [uv](https://docs.astral.sh/uv/). From `backend/`:

```bash
cd backend
uv sync                                       # create .venv + install (uses uv.lock)

uv run python run.py ../data/sample_tiny_input.json   # solve the fixture
uv run pytest -q                              # run the tests
```

Regenerate the small fixture from a full weekly input (stdlib only, no solver):

```bash
uv run python fixtures/build_short_input.py
```

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
