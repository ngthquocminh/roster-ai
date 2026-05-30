# NL Workforce Scheduling Assistant

A workforce scheduling assistant for distribution-centre operations. A constraint
solver (the **Scheduling Engine**) produces a weekly schedule from workforce +
demand data; later phases add a FastAPI backend, natural-language constraint
editing + LLM insights, and a React UI.

The Scheduling Engine is an open-source-solver (OR-Tools CP-SAT) reimplementation
of the core logic of a production weekly model. See [`design.md`](design.md)
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

- The fixture horizon is 2 days (`HORIZON_DAYS` in `build_short_input.py`);
  raise it toward 7 for a full week.
- Deployment target is AWS (frontend → S3/CloudFront; backend container →
  ECR + App Runner/ECS/EC2 — container compute, not Lambda).
