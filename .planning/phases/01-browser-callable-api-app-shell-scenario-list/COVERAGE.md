# API Coverage — ShiftMind backend HTTP API (consumed by `frontend/src/api/`)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
>
> **Detector fired** (`api-coverage.cjs --json` → `detected: true`, signal `noun: api`).
> This phase integrates an API: the frontend's typed client (SHELL-02) wraps the
> ShiftMind backend's own HTTP API. The capability surface below is the endpoint
> list from `docs/API.md` (authoritative as of commit `93ca4e0`).

## What "INTEGRATE" means here, and why the opt-outs are cheap

The typed client has **two layers**, and they have different coverage profiles:

1. **Generated types (`frontend/src/api/schema.d.ts`)** — produced by
   `openapi-typescript` from the backend's *whole* `app.openapi()` schema.
   **Every endpoint below is already fully typed**, including the OPT-OUT rows.
   There is no per-endpoint decision at this layer and no way to partially
   generate it.
2. **Hand-written thin wrapper functions (`frontend/src/api/scenarios.ts`)** —
   one small function per endpoint the UI actually calls. **This is the layer the
   matrix below decides.**

Consequently every OPT-OUT is reversible by writing a ~4-line wrapper against
types that already exist — it is not a missing integration, it is an unwritten
call site. This is exactly SHELL-02's wording: *"a typed API client wraps every
endpoint **the UI uses**"*.

## Matrix

| capability | decision | reason |
|---|---|---|
| `GET /fixtures` | INTEGRATE | SCEN-02 — populates the create-scenario fixture picker |
| `GET /scenarios` | INTEGRATE | SCEN-01 — the Home list |
| `POST /scenarios` | INTEGRATE | SCEN-02 — scenario creation |
| `GET /health` | OPT-OUT | not needed — no UI surface consumes liveness; reachability is already observable through the real data calls (see note A below) |
| `GET /scenarios/{scenario_id}` | OPT-OUT | not needed yet — SCEN-03 (scenario detail) is Phase 2; Phase 1 mounts `/scenarios/:scenarioId` as a placeholder that fetches nothing (see note B below) |
| `POST /constraints` | OPT-OUT | not needed yet — CONS-01..05 are **Phase 2** |
| `POST /scenarios/{scenario_id}/runs` | OPT-OUT | not needed yet — RUN-01 is **Phase 3** |
| `GET /scenarios/{scenario_id}/runs` | OPT-OUT | not needed yet — RUN-04 is **Phase 3** |
| `GET /runs/{run_id}` | OPT-OUT | not needed yet — RUN-02 (poll to terminal) is **Phase 3** |
| `GET /runs/{run_id}/result` | OPT-OUT | not needed yet — RES-01..03 are **Phase 4** |
| `GET /runs/{run_id}/insights` | OPT-OUT | not needed yet — RES-04/05 are **Phase 4** |

**Coverage:** 3 INTEGRATE · 8 OPT-OUT · 0 undecided.

## Notes on two opt-outs whose reasoning does not fit a table cell

**A — `GET /health`.** This is the one OPT-OUT that is *architectural* rather than schedule-based, so
it does not expire when Phase 2 arrives. A health poll would introduce a second, independent "is the
backend up?" signal alongside the one already produced by the real data queries — and two signals can
disagree. A green health check next to a "Can't reach the ShiftMind API" banner (or the inverse) is
strictly worse than one honest signal, and SHELL-04's whole point is that the failure surface tells
the truth. The data calls already answer the reachability question as a side effect of doing real work.

**B — `GET /scenarios/{scenario_id}`.** Worth flagging because it is load-bearing for a known gap:
UI-SPEC's backstop **E5/error** (deep-linking to a nonexistent `:scenarioId` renders the placeholder
as though the scenario were valid — no 404, no error) exists *precisely because* this endpoint is not
yet wrapped. Phase 1 has no scenario fetch on which to hang a 404. Phase 2 must close both together:
wrapping this endpoint is what makes "Scenario not found" renderable. The two are one decision, not two.

## Re-decision baseline for later phases

Phases 2-4 each wrap a further slice of this same surface. Per the coverage
protocol, each of those phases starts from the **same full-coverage baseline** —
the OPT-OUT rows above are decided *for Phase 1 only* and must be re-decided, not
inherited. The one row that never becomes an INTEGRATE by default is `GET /health`,
whose reason is architectural (redundant signal), not schedule-based; a later phase
that wants it must overturn that reason explicitly.

*Decided: 2026-07-16 at plan time (not deferred to seal time).*
