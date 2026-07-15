---
created: 2026-07-15T15:32:34.487Z
title: Add run cancellation and concurrency limits
area: api
files:
  - backend/services/run_service.py:30
  - backend/services/run_service.py:34
  - backend/services/run_service.py:38
---

## Problem

Solves run on a module-level single-worker `ThreadPoolExecutor`
(`run_service.py:38`, `max_workers=1`, guarded by `_pool_lock` at
`run_service.py:31`). Two consequences:

1. **No cancellation.** Once a run is submitted there is no way to stop it. A user
   who triggers a 2-minute full-week solve by mistake must wait it out; the run
   holds the single worker for its whole duration.
2. **No concurrency control beyond the hard serial limit.** `max_workers=1` means
   every solve queues behind every other solve, with no queue visibility, no
   per-scenario fairness, and no way to raise the limit for a bigger host.

Nothing is broken — this is a deliberate v0.2 simplification (documented as an
architectural constraint: solves are CPU-bound, so serialising them keeps the
event loop free). It becomes user-visible with a frontend, where a queued or
runaway run is something a person watches rather than a script tolerates.

Note the interaction with the deferred "extract engine as separate service" todo
— if the engine moves behind its own service with a master run-manager, that
component is where cancellation and queueing would naturally live. Worth deciding
which lands first rather than building cancellation twice.

Carried over from `docs/PLAN.md` Phase 2 follow-ups (marked deferred/optional),
migrated into GSD when that hand-written tracker was retired at the v0.3/v0.4
boundary.

## Solution

TBD. CP-SAT cancellation is not a simple thread kill — it needs a
`SolutionCallback` polling a stop flag, or `solver.StopSearch()` from another
thread, so the engine seam (`SchedulerEngine.solve()`) would need a cancellation
token in its contract. That's a Protocol change, so it deserves a design pass, not
a patch. Concurrency limits are cheaper: make `max_workers` configurable via
settings and add a `CANCELLED` state to the run lifecycle
(`PENDING → RUNNING → COMPLETED/FAILED/CANCELLED`).
