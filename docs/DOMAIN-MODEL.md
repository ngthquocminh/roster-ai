# Domain Model — demand families, units, and assignments

The dimensional model every metric in this repository is built on: which unit
each demand family is measured in, what an assignment can and cannot be scoped
by, and which planner questions each side can answer.

**Read this before creating or reviewing any story that touches a metric.**
This document exists because the rule was stable and true but written down
nowhere, so five of Story 2.7's nine decision-grade review findings were the
same rule re-derived wrongly from adapter code
(`_bmad-output/implementation-artifacts/epic-1-2-retro-2026-08-16.md` §3.2,
action A1). Cite it; do not re-derive it.

Sits beside [`EVIDENCE-CONVENTION.md`](EVIDENCE-CONVENTION.md) and
[`GATE-A-RUNBOOK.md`](GATE-A-RUNBOOK.md).

Anchors below name a file and a symbol rather than a line, so they survive the
code moving. Ledger references are `deferred-work.md:<line>`, matching that
file's own convention.

---

## 1. Family determines unit

**Rule: `unit` is a property of the source table the row came from, not a
choice a metric may make.** The adapter hardcodes it per family; no code
downstream may reinterpret it.

| Family | Source table | Amount field | `unit` | Means |
|---|---|---|---|---|
| `outbound` | `Outbound Workload` | `Volume` | `volume` | a **quantity** of output over the interval (cartons, pieces — as the source states it) |
| `inbound` | `Inbound Workload` → `Tasks[]` | `Volume` | `volume` | same, one row per task nested under a shared window |
| `indirect` | `Indirect Workforce Requirement` | `RequiredHeadcount` | `headcount` | a **rate**: persons held for the whole interval |

**Enforced in:** `backend/adapters/postgres/scenario_projection.py` —
`_normalize_demand`. Three separate loops, each emitting a literal `unit=` for
its family. There is no path that produces any other pairing.

**Typed in:** `backend/application/contracts/scenario_projection.py` —
`DemandIntervalV1` (`family: outbound|inbound|indirect`, `unit:
volume|headcount`). Family vocabulary: `backend/domain/types.py` —
`DemandFamily`. The solver-side domain states the same rule in
`DemandBand`'s docstring.

Consequences that follow from the table and MUST NOT be worked around:

* **`volume` and `headcount` are not interconvertible in the read model.** The
  only rate in the projection is `QualificationRefV1.rate`, which is *per
  worker, per task*. Volume → minutes therefore depends on **who performs the
  work** — an assignment, and so a solver question owned by Epic 3.
* **A `volume` row multiplied into "minutes" is a wrong number wearing a valid
  evidence locator.** This is the defect the fail-closed guard exists for.
* **Restricting a `volume` row to a window pro-rates it** across the row's own
  interval — an assumption declared in
  `backend/application/capabilities/scheduling_compute.py` — `SCOPE_CONTROLS`
  under `volume:uniform_within_interval`, not left implicit. A `headcount` row
  needs no such assumption: overlap × amount is exact worker-minutes.

**Time:** all projection intervals are integer minutes from horizon start,
half-open. Overlap is `interval_overlap_minutes`
(`backend/application/grounding/calculators.py`) — never containment. Site
timezone is `Australia/Sydney`, applied once at the adapter boundary.

---

## 2. What an assignment carries — and what it does not

| Record | Carries | Does **not** carry |
|---|---|---|
| `AssignmentV1` | `worker_id`, `task_id`, `shift_id`, `start_minute`, `end_minute` | **`family`**, `unit`, `amount` |
| `WorkerV1` | identity, employment, `qualifications` (per-task rate), availability | **`family`** |
| `DemandIntervalV1` | `family`, `unit`, `amount`, `task_id`, `area_id`, window | worker identity |

**Rule: `family` is a property of a demand row alone. It is not a function of
`task_id` and it cannot be derived for any other record.** One task carries
demand rows in several families — measured on `sample_tiny_input`, task
`1E5596F1` has 197 `inbound`, 53 `outbound`, and 6 `indirect` rows.

**Enforced in:** `backend/application/contracts/grounding.py` —
`FAMILY_AWARE_METRICS` (exactly the two demand-reading metrics), and
`backend/application/grounding/calculators.py` —
`_check_family_is_meaningful`, which raises `CalculationArgumentsError` →
`invalid_query` when `family` is passed to a metric that reads assignments or
workers. Passing it is a caller error, not a silently ignored hint.

### What this makes unanswerable

Any question requiring demand and assignments to be **scoped to the same
dimension**. Specifically, today:

| Unanswerable | Why |
|---|---|
| Required work in **minutes** for `outbound`/`inbound` | that demand is `volume`; conversion needs a per-worker rate |
| Demand **volume** for `indirect` | a workforce requirement has no output quantity |
| Any **family-scoped** staffing or worker question | assignments and workers carry no family and it cannot be derived |
| **Shortfall** (required − staffed) for any family | see §4 |
| Any **non-zero** `staffed_minutes` against the real projection | `PostgresScenarioProjectionReader.get_baseline_assignments` returns `()`; `baseline_assignment_count` is `0`. The only populated assignment source is the eval double (`backend/evals/fixture_projection.py` — `ASSIGNMENTS`). Epic 3 supplies the real one. |

---

## 3. Which questions come from demand, and which from assignments

**Rule: route by the *unit the answer is measured in*, never by the family the
question mentions.** A metric is dimension-bound; a planner's question is not.

| Planner question | Read from | Metric | Family argument |
|---|---|---|---|
| "How much work is required here?" (`outbound`/`inbound`) | demand | `required_demand_volume` → `units` | optional |
| "How many people are required here?" (`indirect`) | demand | `required_headcount_minutes` → `minutes` | optional |
| "How much staffed time is on this task?" | assignments | `staffed_minutes` → `minutes` | **MUST be omitted** |
| "Who can do this task?" | workers | `qualified_worker_count` → `workers` (horizon-wide, takes **no** window) | **MUST be omitted** |
| "How many *people* are working?" (headcount, not minutes) | assignments | **none today** — computable, deliberately not added (`deferred-work.md:196`) | — |
| "Are we short?" | — | **none** — see §4 (`deferred-work.md:198`) | — |

### The rule story authors get wrong

> **A headcount or staffing question on an `outbound` or `inbound` task is a
> VALID planner question.** It is answered from **assignments**, which are
> family-agnostic. Only *required demand in minutes* is unanswerable for those
> families.

Never guard a question by family, and never phrase a dimension miss as "that
question is invalid" — the question is usually fine; it is the *metric* that
cannot express it. This wording is normative and is already carried in
`backend/application/grounding/calculators.py` —
`CalculationDimensionError`'s docstring.

**Fail-closed, not zero:** when demand rows exist for the task and window but
none carry the metric's unit, the calculator **raises** rather than returning
`0`. A dimension miss returning zero is indistinguishable from a proven-empty
set and renders as a supported zero carrying no locator. Anchors:
`calculate_metric`'s `window_demand` / `matched_demand` split and
`_dimension_message`; `SCOPE_CONTROLS` under
`dimension:fail_closed_on_unit_miss`. The resulting
`metric_dimension_mismatch` is deliberately **retryable** — the message names
the metric that *can* answer, and the rows are already drained.

---

## 4. Why required-in-minutes exists only for `indirect`

`required_headcount_minutes` is the only "required minutes" metric because
`headcount` is the only demand unit that already *is* a rate: overlap ×
persons is exact worker-minutes with no distributional assumption. And
`headcount` is emitted only for family `indirect` (§1).

`shortfall_minutes` was specified, implemented, and **removed at review**. It
cannot be made sound at this layer: required minutes exist only for
`indirect`, staffed minutes come from `AssignmentV1`, which carries no family
and cannot be scoped to match — so the subtraction always took all-family
staffing away from indirect-only demand. The "compute it only for
single-dimension tasks" rescue does not exist either: measured on
`sample_tiny_input`, **0 of 6 tasks carry demand in a single family**, so the
branch would refuse on every task and ship as dead code.

The absence is recorded in code, not only here:
`backend/application/contracts/grounding.py` — the `NOTE on what is
deliberately ABSENT` comment inside `MetricV1`. Ledger: `deferred-work.md:198`.

### Before `shortfall_minutes` can return, all four must hold

1. **A per-worker rate from the solver**, so `volume` → minutes is defined and
   required minutes exist for *every* family — not just `indirect`.
2. **A required side and a staffed side scoped to the same dimension** —
   either assignments gain family, or required minutes become family-complete
   so the family-agnostic staffed side legitimately matches.
3. **A real assignment supply in the projection.** `get_baseline_assignments`
   returns `()` today, so the staffed side is structurally zero (§2).
4. **A test that drives it against a task carrying mixed-family demand.** A
   test using a single-family task would pass without exercising the
   subtraction that was wrong.

Owner: **Epic 3**, once CP-SAT supplies the per-worker rate.

---

## 5. Checklist for a story touching a metric

1. Name the **unit** the answer is measured in before naming the metric.
2. If the answer is measured in `minutes` and the demand is `outbound` or
   `inbound`, stop — that is Epic 3's, or the question routes to assignments
   (§3).
3. Pass `family` **only** to `required_headcount_minutes` or
   `required_demand_volume`.
4. Do not compare a demand-side value with an assignment-side value (§4).
5. Windows are half-open minute intervals compared by **overlap**. Do not push
   a window into the projection — `DEMAND_FILTERS` publishes only containment
   keys and would silently drop partially-overlapping rows
   (`deferred-work.md:186`).
6. `MetricV1` is a **closed vocabulary persisted inside conversation
   payloads**. Adding, renaming, or removing a member is a contract change,
   not a refactor (`deferred-work.md:194`).
7. State in the story which rule above the work relies on. If a rule you need
   is not written here, it is not written anywhere — record it before
   implementing against it.
