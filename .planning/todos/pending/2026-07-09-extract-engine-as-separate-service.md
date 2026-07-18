---
created: 2026-07-09T00:00:00.000Z
title: Extract solver engine into a separate service with a master run-manager
area: architecture
severity: future / post-POC
files:
  - backend/engine/
  - backend/services/run_service.py
  - backend/api/main.py
---

## Context

This is a planned post-POC system refactoring, not a fix. The current architecture
runs the CP-SAT solver in-process inside the FastAPI backend via a single-worker
`ThreadPoolExecutor` (`services/run_service.py`). This is intentional for the POC
but will not scale in production.

## Target Architecture

- **Engine service** — a standalone process (or container) that owns the solver.
  Accepts a solve job (problem payload + solver config + overrides), runs CP-SAT,
  and returns the result. Horizontally scalable; one instance per CPU-heavy worker.

- **Master service** — a coordinator that accepts run requests from the API, queues
  them, dispatches to available engine instances, and polls/streams status back.
  Owns the run lifecycle (PENDING → RUNNING → COMPLETED/FAILED) currently managed
  by `run_service._execute`.

- **FastAPI backend** — becomes a thin API + LLM layer only. Submits jobs to the
  master service; no longer hosts the solver thread pool.

## Design Considerations

- The `SchedulerEngine` Protocol (`engine/base.py`) is already a clean seam — the
  engine service can implement the same interface over a network transport (gRPC,
  HTTP, or a task queue like Celery/RQ) without touching domain or service code.
- Run state persistence (SQLite `runs` table) either stays in the API service or
  moves to the master service; decide based on who owns the run record lifecycle.
- LLM constraint parsing and insight generation stay in the API/LLM layer — they
  are not CPU-bound and should not move to the engine service.
- The `SolverConfig.overrides` field travels with the job payload — no schema change
  needed at the protocol level.

## When to Revisit

After POC is validated with real users and throughput requirements become clearer.
Trigger: concurrent solve requests start queuing visibly, or multi-tenant isolation
becomes a requirement.
