# Phase 3: On-Demand Insight Reports - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-30
**Phase:** 3-On-Demand Insight Reports
**Areas discussed:** Endpoint & generation flow, Report content & structure, Grounding enforcement, Failure & not-ready responses

---

## Endpoint & generation flow

### Generation + caching trigger

| Option | Description | Selected |
|--------|-------------|----------|
| GET lazy-generate + cache | First GET generates + writes insight_json; later GETs return cache. One endpoint, mirrors GET /runs/{id}/result. | ✓ |
| POST generate, GET fetch | Explicit two-step; POST triggers generation, GET returns stored. More REST-explicit, extra endpoint + state. | |

**User's choice:** GET lazy-generate + cache

### Execution location

| Option | Description | Selected |
|--------|-------------|----------|
| Synchronous in request handler | One LLM call is quick; FastAPI runs sync def routes in a threadpool. Simplest. (Claude's recommendation.) | |
| Offload to worker pool / background | Generate on a background worker, decoupled from request. | ✓ |

**User's choice:** Offload to worker pool / background — deviated from the recommendation.
**Notes:** Created tension with criterion 1 ("a GET returns a report"), so a follow-up clarified the async model (see below).

### Async model (clarifying follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Blocking GET on a worker thread | First GET runs generation off the event loop and waits, returning the report in that response; caches; later GETs return cache. No polling, no new status field. | ✓ |
| Async + poll (202 generating) | First GET enqueues background generation, returns 202; client polls; later GET returns cache. Needs insight_status field. | |

**User's choice:** Blocking GET on a worker thread
**Notes:** Claude flagged that the existing solve pool is `max_workers=1` and would serialize insight calls behind solves — recorded as a research item (use a separate path or FastAPI's def-route threadpool, not the solve pool).

---

## Report content & structure

### Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Prose summary + structured highlights | 1-2 sentence narrative + labeled metric lines/bullets. Readable, easy to ground. | ✓ |
| Fully structured sections | Headed sections (Coverage / Unmet / Cost / Warnings / Overrides). Most scannable. | |
| Free-form prose paragraph | Single narrative. Most natural-language, hardest to ground/test. | |

**User's choice:** Prose summary + structured highlights

### Mandatory content (multi-select)

| Option | Description | Selected |
|--------|-------------|----------|
| Coverage (served vs required + pct) | Per-function/family coverage from coverage_by_function. | ✓ |
| Unmet hours + total cost | total_unmet_hours and total_cost — top-line objective outcomes. | ✓ |
| Degenerate-family warnings | Narrate result.warnings[] honestly (serves INS-03 no-generic-language). | ✓ |
| Applied overrides in effect | Which NL constraints/overrides were active for the run. | ✓ |

**User's choice:** All four selected.

### Length/tone

| Option | Description | Selected |
|--------|-------------|----------|
| Concise operations-brief | A few sentences + a handful of metric highlights. | ✓ |
| Detailed multi-paragraph | Fuller narrative covering each section in prose. | |
| You decide | Leave length/tone to planner discretion. | |

**User's choice:** Concise operations-brief

---

## Grounding enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Post-hoc number-verification guard | Extract numerics from the report, assert each appears in metrics JSON; reject otherwise. Provider-agnostic, testable, guards Phase-4 Claude. | ✓ |
| Template slots only | Stub fills numbers into fixed templates; verbatim by construction. Guarantee lives in the stub only. | |
| Trust the prompt | Instruct the model to use only given numbers. Lightest, weakest, hardest to test. | |

**User's choice:** Post-hoc number-verification guard
**Notes:** Guard failure on an ungrounded number should route to the 5xx failure path so a fabricated report is never cached or returned.

---

## Failure & not-ready responses

### Not-ready (run not COMPLETED)

| Option | Description | Selected |
|--------|-------------|----------|
| 409 Conflict | Mirror GET /runs/{id}/result; body names current run status. (Claude's recommendation.) | |
| 200 with not-ready body | Always 200, body carries ready=false + reason. Friendlier for polling clients. | ✓ |

**User's choice:** 200 with not-ready body — deviated from the recommendation.
**Notes:** Deliberate divergence from the existing result endpoint's 409; downstream agents must not "correct" it to 409.

### Provider failure during generation

| Option | Description | Selected |
|--------|-------------|----------|
| 5xx error, run untouched | 502/503 + error detail; run stays COMPLETED, result_json untouched, nothing cached (retry-able). COMPLETED runs only. | ✓ |
| 200 with error payload | 200 carrying an error field / insight=null; run untouched. | |

**User's choice:** 5xx error, run untouched

---

## Claude's Discretion

- Exact prose wording of the report (within the prose-summary + highlights structure, concise).
- `generate_insights` input/return contract shape (provider-neutral).
- Insight-generation thread path (separate executor vs FastAPI def-route threadpool — not the solve pool).
- Numeric-extraction strategy for the grounding guard.

## Deferred Ideas

- Auto-generate insights after every run (INS-05, v2).
- Real Claude `generate_insights` + model config (LLM-02, Phase 4).
- Async 202 / polling insight model (considered, rejected for blocking-GET).
- What-if compare + delta explanation (Phase 5).

## Reviewed Todos (not folded)

- WR-05 — Add real-engine test for ENG-05 degeneracy detection (testing): Phase-2 testing gap, not insight work.
- WR-04 — Harden scenario fixture path against traversal (api): Phase-4/security item, unrelated to insights.
