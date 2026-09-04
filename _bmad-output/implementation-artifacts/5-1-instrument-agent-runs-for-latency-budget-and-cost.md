---
baseline_commit: 8f25ccb
---

# Story 5.1: Instrument Agent Runs for Latency, Budget, and Cost

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a portfolio operator,
I want product and workflow activity correlated across structured logs and metrics,
So that I can diagnose one run and understand where its latency, budget, and cost went.

**This is the first story of Epic 5's portfolio sequence.** Story 5.0, inserted by
`sprint-change-proposal-2026-09-03.md` as a corrective prerequisite, precedes it in the epic and is
independent of it in both directions — 5.0 touches only the comparison read path and its published
contract; this story declares zero frontend diff and no new API response field. Neither blocks the
other. Every producer it instruments
already exists and already works. What does not exist is **any** operational telemetry: the entire
repository contains exactly two `logging.getLogger` calls
(`backend/api/routers/approvals.py:57`, `backend/api/routers/conversations.py:95`), no formatter, no
logging configuration, no correlation identifier on the request path, no metric of any kind, and no
token or cost figure anywhere — `AgentRunOutcomeV1` has no usage field, and `result.usage` is never
read.

**Scope summary:** one new owned telemetry contract, one new application port, one new
`adapters/telemetry/` package with a stdlib-`logging` JSON sink and a cost estimator, one HTTP
middleware, one `APP_VERSION` constant, usage/budget fields added to the AgentRuntime seam, and
emission calls at eight named producers. **No migration, no new table, no new route, no new API
response field, no new runtime dependency, no evidence file, no Gate A check, no new golden case,
and zero frontend diff.**

**Depends on, and consumes:** Story 2.1's `AgentRuntime` port, its owned contracts, and its
`tests/architecture/test_agent_runtime_boundaries.py` import guard; Story 2.5/2.6's `AgentDepsV1`
and the single capability wrap point in `agent/capability_tools.py`; Story 3.2's
`GovernedSolveResult.wall_time_seconds`; Story 3.3's `JobLeaseV1.created_at`; Story 3.9's
failing-span-exporter test pattern; Story 4.1's `ApprovalBindingV1.created_at`; Story 4.3's
`audit_event` row.

**Unblocks:** Story 5.2 (its allow-list has a typed record to assert against), Story 5.3 (the
one-command run has something to show), Story 5.4 (the walkthrough's "where did the latency go"
claim), and Epic 6's CloudWatch diagnosis surface.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none may be re-derived from code.

| Fact | Where it is written |
|---|---|
| **NFR15's list of what must be recorded is closed and normative:** "API acknowledgement latency, first-persisted-event latency, end-to-end agent duration, model/tool latency, solver duration, queue age, approval age, token use, and cost per completed task." It contains **no database-query latency**, though AC1's *Given* names database execution as a layer. | `epics.md:103` (NFR15); AC1 at `epics.md:1357-1360` |
| **NFR22's cardinality rule, verbatim:** every agent run searchable by one stable run identifier across product records, audit, operational logs, and available traces "without using high-cardinality IDs as metric labels." Restated in the spine's *Correlation* convention, which also lists the identifiers to propagate: request, conversation, agent-run, tool-call, approval, job, solver-run, audit-event, site, actor, and schedule-version. | `epics.md:117` (NFR22); `ARCHITECTURE-SPINE.md` — *Consistency Conventions*, **Correlation** row |
| **Measured fields carry unit suffixes** — `_ms`, `_s`, `_h`, `_bytes`, `_usd`. | `ARCHITECTURE-SPINE.md` — *Consistency Conventions*, **Time and measures** row |
| **AD-12: no telemetry system authorizes or blocks product work.** CloudWatch owns AWS diagnosis; sanitized OpenTelemetry/Logfire owns optional AI traces; PostgreSQL owns product state and append-only business audit. Records of truth stay separate. | `ARCHITECTURE-SPINE.md` — AD-12 |
| **AD-1 / AR1: domain and application code must not import** FastAPI, PydanticAI, SQLAlchemy, Cognito, S3, Logfire, or concrete model providers. Enforced today for `pydantic_ai`, `pydantic_graph` and `logfire` over `backend/domain` and `backend/application` by `FORBIDDEN_ROOT_MODULES`. | `ARCHITECTURE-SPINE.md` — AD-1; `epics.md:147` (AR1); `backend/tests/architecture/test_agent_runtime_boundaries.py:53` |
| **`adapters/` is the declared home for telemetry adapters** — "PostgreSQL, Cognito, S3, telemetry and provider adapters". | `ARCHITECTURE-SPINE.md` — *Structural Seed*; `epics.md:172` (AR26) |
| **AR27: add and lock each planned dependency only at its implementation gate.** The Stack table's `Logfire SDK 4.38.0` is a **planned optional telemetry seed**, not a repository lock. `backend/pyproject.toml:26-28` records that `pydantic-ai-slim`'s two extras were chosen specifically to avoid pulling it. | `ARCHITECTURE-SPINE.md` — *Stack*; `epics.md:173` (AR27); `backend/pyproject.toml:26-28` |
| **Story 5.1 was slimmed at the 2026-08-09 replan:** "metric-label cardinality rules and the standalone `log-metric-contract.json` gate dropped; NFR22 run-ID correlation absorbed from old 5.7-AC3." The **gate artifact** was dropped; NFR22's rule itself was not. | `sprint-change-proposal-2026-08-09-epics-2-5.md:161` |
| **AD-7 / NFR16: budgets are explicit positive application configuration and never chosen by the model.** They already exist and are validated at process start — `AC2_CEILING_FIELDS` in `backend/settings.py:37-46`. This story records their **outcomes**; it does not add, change, or relax a budget. | `ARCHITECTURE-SPINE.md` — AD-7; `epics.md:105` (NFR16); `backend/settings.py:37-46` |
| **The adapter distinguishes wall-clock expiry from budget exhaustion BY TYPE, never by string-matching an error message.** `RunCancelled` maps to `timed_out`; `UsageLimitExceeded` maps to `failed` plus `budget_exhausted`. | `backend/application/contracts/agent_runtime.py:38-52`; `backend/agent/runtime.py:254-263` |
| **NFR35's four internal thresholds are owned by Stories 1.4, 1.5, 2.4 and 3.5 and measured on the CI reference environment under the canonical protocol.** Epic 5's own coverage note says they "do not depend on this epic or Epic 6". This story records the values; it does not own, re-measure, or re-gate a threshold. | `ARCHITECTURE-SPINE.md` — AD-26; `epics.md:1347`; `epics.md:143` (NFR35) |
| **NFR3/NFR4/NFR30 content minimization and its proof are Story 5.2's**, including "any configured trace export" and `evidence/story-5.2/content-minimization-report.json`. | `epics.md:1367-1383` |
| **NFR25's alerting is hosted and Epic 6's.** It appears in no Epic 5 acceptance criterion. | `epics.md:123` (NFR25); `epics.md:1423-1536` |
| `outbound`/`inbound` demand is measured in **volume**, `indirect` in **headcount**; assignments carry worker identity but **no `family`**; a metric reading assignments must not accept a `family` argument. **This story computes no demand metric.** It emits operational measurements only — durations, ages, counts, tokens, money — and must not introduce a telemetry field that looks like, or is derived from, a demand or coverage metric. | `docs/DOMAIN-MODEL.md` §1, §2, §3 |
| **Manual assistive-technology verification is descoped**; accessibility is proven by automated coverage alone. Not exercised here — this story has a zero-line frontend diff. | `EXPERIENCE.md` — Accessibility Floor; `.claude/CLAUDE.md` |
| **Retro action A1 (`epic-4-retro-2026-09-02.md` §6):** a red from incomplete code does not count. The red must come from **mutating code that is already green**, and the Dev Agent Record must carry a mutation table (columns: mutation, guard, before, after) before the story reaches review. A1 had not yet landed as a `bmad-dev-story` fact at `8f25ccb`, so **this story carries the requirement itself** (Task 14). **UPDATED 2026-09-03: it has since landed** — commit `c4f5de1` adds two facts to `_bmad/custom/bmad-dev-story.toml` (the definition of demonstrated red, and the mutation-table requirement) plus a paired fact on `bmad-code-review` requiring the reviewer to independently re-run at least one row rather than only reading the table. Task 14 is now satisfied by the loaded fact rather than duplicating it; the in-story requirement stands as belt and braces and needs no change. | `epic-4-retro-2026-09-02.md` §4, §6 A1; `_bmad/custom/bmad-dev-story.toml`; `_bmad/custom/bmad-code-review.toml` |

---

## Acceptance Criteria

Verbatim from `epics.md:1355-1365`.

**AC1.**
**Given** API, worker, AgentRuntime, database, and solver execution
**When** operational telemetry is emitted
**Then** structured JSON logs and metrics record acknowledgement/first-event/end-to-end/model/tool/solver
timings, queue and approval age, tokens, estimated cost, and budget outcomes
**And** every value is attributable to one agent run. (NFR15)

**AC2.**
**Given** a completed agent run
**When** the operator searches product state, authoritative audit, and structured logs by its stable
run or correlation identifier
**Then** the same lineage is discoverable across all three without exposing sensitive content
**And** authoritative audit remains the business record of truth. (NFR22)

---

## Measured at creation — `8f25ccb`, clean tree

Do not re-derive these from code; re-verify them at Task 1 and record any drift.

| Fact | Measurement |
|---|---|
| Backend default suite | **1510 passed, 1 skipped, 7 deselected** (`uv run --frozen pytest -q`, 133.9 s) |
| Backend `-m postgres` | **156 passed** (Docker PostgreSQL up) |
| `tests/test_evidence_convention.py` | **87 passed** |
| `tests/architecture/` | **60 passed** across 10 files |
| Existing logging in the whole repository | **two** `logging.getLogger(__name__)` calls — `api/routers/approvals.py:57`, `api/routers/conversations.py:95`. No formatter, no `basicConfig`, no `dictConfig`, no handler, no JSON |
| Existing correlation | **none on the request path.** `accept_turn` mints `request_id=uuid4()` per accepted turn (`application/use_cases/accept_turn.py:32-35`); `execute_agent_turn` mints a **second, unrelated** `uuid4()` for `AgentDepsV1.request_id` (`api/routers/conversations.py:232`). No middleware, no header, no `ProblemDetailsV1` correlation field |
| Existing metrics | **none.** No registry, no counter, no histogram, no `/metrics` route |
| Existing token/cost capture | **none.** `AgentRunOutcomeV1` (`application/contracts/agent_runtime.py:210-262`) has no usage field; `agent/runtime.py` never reads `result.usage` |
| Durations already measured and available for reuse | `GovernedSolveResult.wall_time_seconds` (`engine/governed_adapter.py:174,193-255`, `perf_counter`-based), persisted as `ScheduleVersionV1.wall_time_seconds` (`application/contracts/schedule_version.py:110`) |
| Ages already derivable without a new column | `job_queue.created_at` to `JobLeaseV1.created_at` (`application/contracts/job_lease.py:56`); `approval_request.created_at` to `ApprovalBindingV1.created_at` (`application/contracts/approval_binding.py:52`), read by `adapters/postgres/approval.py:20` |
| Product-state lineage columns that already exist | `persisted_event.request_id`, `.conversation_id`, `.agent_run_id`, `.schedule_run_id` (`adapters/postgres/schema.py:319-323`) |
| Audit lineage columns that already exist | `audit_event.attempt_id`, `.request_id`, `.conversation_id`, `.agent_run_id`, `.approval_id`, `.schedule_run_id`, `.app_version` (`adapters/postgres/schema.py:520`) |
| `app_version` today | the literal `"0.1.0"` in **four** places — `use_cases/decide_approval.py`, `use_cases/promote_baseline.py`, `use_cases/request_approval.py` defaults and `api/routers/approvals.py:395` — plus `FastAPI(version="0.1.0")` in `api/main.py:56` and `version = "0.1.0"` in `backend/pyproject.toml:3`. No shared constant |
| Existing HTTP middleware | two `@app.middleware("http")` decorators (`api/main.py:196`, `:235`) plus `CORSMiddleware` added last at `:305` |
| Dependencies | `opentelemetry-sdk` is **dev-group, test-only** (`backend/pyproject.toml:38-45`); `opentelemetry-api` arrives transitively under `pydantic-ai-slim` and is a no-op without the SDK; **`logfire` is not installed and is a forbidden import in `domain`/`application`** |
| PydanticAI 2.27.0 usage surface | `AgentRunResult.usage` returns `RunUsage` with `requests`, `tool_calls`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `details` (`.venv/.../pydantic_ai/usage.py:338-369`). **Neither `UsageLimitExceeded` nor `RunCancelled` carries usage** (`.venv/.../pydantic_ai/exceptions.py:268,459`) |

**Frontend was deliberately not measured.** This story has a zero-line frontend diff (Decision 11);
the last recorded figures are Story 4.6's Playwright **66** and Story 4.4's Vitest **575 passed**.
CI floors in `.github/workflows/ci.yml:9-13` are floors and ceilings — do not edit them; the backend
default floor there (864) is already far below the measured 1510 and stays as is.

---

## Thirteen decisions were made at story creation — do not re-litigate them

Each decision states its mechanism **and what that mechanism does not cover**. The second half is
load-bearing: Story 4.2's Decision 10 named a goal and a mechanism that blocked only one of two
directions, and the gap shipped.

### Decision 1 — Telemetry crosses an application **port**; application code never imports a logger

New: `application/ports/telemetry.py` defines `TelemetrySink` (a `typing.Protocol` with a single
`emit(record: TelemetryRecordV1) -> None`) and `NullTelemetrySink`. The one concrete implementation
lives in `adapters/telemetry/`, the seed's declared home for telemetry adapters (AR26). Application
code receives a sink; it never constructs one, never imports `logging`, and never imports the
adapter package.

This shape is chosen over "call `logging.getLogger` in the use case" for one reason that is not
style: **the tests must be able to assert on emitted records without touching global logging state
or `caplog`.** A recording fake sink makes every assertion in Tasks 10–13 a direct equality check.

**What this does not cover:** it does not remove the two existing `logging.getLogger` calls in
`api/routers/approvals.py` and `api/routers/conversations.py`, and it does not route their
`logger.exception(...)` tracebacks through the sink. Those are free-text exception records; bringing
them into the typed channel would put uncontrolled provider text into it (Decision 12). They keep
emitting through stdlib logging and become JSON only because Decision 2's formatter is installed
process-wide — their **content** is unchanged and unscrubbed, and scrubbing them is Story 5.2's.

### Decision 2 — "Metrics" are records in the same JSON stream, distinguished by a closed `event` vocabulary

There is no metrics backend in this repository, no hosted one until Epic 6, and NFR25's alerting is
not in any Epic 5 acceptance criterion. AC1 asks that logs and metrics *record* the values, and
`log-metric-contract.json` — the standalone gate that would have demanded a separate metrics
surface — was explicitly dropped at the 2026-08-09 replan.

So: one channel, one JSON object per record, written through stdlib `logging` by
`adapters/telemetry/json_logs.py`. Each record carries a closed `event` name and its measurements.
A downstream metric system (CloudWatch metric filters in Epic 6, an OTel meter later) reads the
stream; nothing in this story aggregates.

**What this does not cover:** there is no counter, no histogram, no aggregation, no `/metrics`
endpoint, no exporter, and no new runtime dependency. A record is emitted per occurrence; nothing
sums, buckets, or samples it. If a later story needs percentiles, it adds an aggregator over this
stream — it does not change these records.

### Decision 3 — NFR22 is enforced **structurally**: IDs are properties, labels are a closed allow-list, and no `*_id` may be a label

`TelemetryRecordV1` has two separate mappings and they are not interchangeable:

* `correlation: CorrelationV1` — a frozen dataclass of optional identifiers, exactly the spine's
  *Correlation* list: `request_id`, `site_id`, `actor_id`, `conversation_id`, `agent_run_id`,
  `tool_call_id`, `approval_id`, `job_id`, `schedule_run_id`, `schedule_version_id`. These are
  **properties**, never dimensions.
* `labels` — a string-to-string mapping, the **only** dimension source, with keys drawn from one
  closed module-level allow-list: `route_template`, `method`, `status_class`, `agent_run_status`,
  `failure_reason`, `capability_name`, `budget_outcome`, `solver_status`, `job_type`,
  `approval_outcome`, `model`, `cost_basis`.

Two guards in `tests/architecture/test_telemetry_boundaries.py`: every emitted label key is in the
allow-list, and **no label key ends in `_id`** — the mechanical form of NFR22's rule.

**What this does not cover:** the allow-list bounds label *keys*, not label *values*. A future
producer could put a UUID in `capability_name` and the key guard would stay green. The value side is
bounded only by the fact that every current label value comes from a closed vocabulary or a config
field, and the story does not add a machine check for it — a value regex would have to admit model
slugs and route templates and would be a proxy. Named here so a later story adding a label from a
free field knows it is unguarded.

### Decision 4 — `emit` never raises, never blocks, and never touches the database

AD-12: "No telemetry system authorizes or blocks product work." NFR10 requires zero product-state
corruption on a telemetry failure. Two of the emission sites — `decide_approval` and the worker's
finalize path — run **inside** a transaction whose exception rolls the transaction back
(`api/main.py:58-75`, `api/deps.py`'s `get_site_context`). A raising sink there would roll back a
baseline promotion.

So `JsonLogTelemetrySink.emit` catches every exception from serialization and from the handler and
discards it, and the `TelemetrySink` Protocol docstring states the obligation for any
implementation. The correctness proof is a **mutation**: replace the injected sink with one that
raises on every `emit`, run the approval-decision path, and assert the promotion still commits and
the audit row still exists — the same shape as Story 3.9's
`test_manual_run_result_and_evidence_survive_a_failing_span_exporter`
(`tests/architecture/test_model_outage_boundaries.py:550`), which is the pattern to copy.

Emission also performs **no query**. A record carries only identifiers already in hand at the call
site (Decision 8's second half).

**What this does not cover:** a synchronous handler still costs wall time on the request path. This
story writes through stdlib `logging` with no queue and no thread, so a slow or blocked stream slows
the request. That is accepted for a local portfolio deployment and is not measured; an asynchronous
handler is Epic 6's if hosted throughput ever makes it matter.

### Decision 5 — Unknown is `null`, never `0`

Every measurement field is optional, and a producer that could not observe a value emits `None`.
Reporting `0` tokens for a run that exhausted a 32,768-token ceiling, or `0.0 USD` for an unpriced
model, is a wrong number wearing a valid-looking field — the same defect class
`docs/DOMAIN-MODEL.md` §3 describes for a dimension miss returning zero, restated for operational
values. (That section is normative for demand metrics; it is cited here as the repo's own precedent
for the shape of the mistake, not as a rule about telemetry.)

This is not hypothetical. `run_sync` **raises** on the `timed_out` and `budget_exhausted` paths, and
neither `RunCancelled` nor `UsageLimitExceeded` carries usage (measured — see the table above), so
on exactly the two runs an operator most wants to inspect, token counts are genuinely unavailable.
They are emitted as `null` with `budget_outcome` still populated.

**What this does not cover:** it does not recover the missing usage. `Agent.iter()` exposes a
running `AgentRun.usage()` that would survive the exception (`.venv/.../pydantic_ai/run.py:487`),
but adopting it turns `run_turn`'s synchronous `run_sync` into an async iteration and rewrites the
`CancellationToken` plus `threading.Timer` deadline mechanism that AD-7's
`timed_out`/`budget_exhausted` distinction depends on. Out of scope; ledgered by Task 13.

### Decision 6 — `budget_outcome` is exactly what type-discrimination can produce

Closed vocabulary: `within_budget`, `budget_exhausted`, `deadline_expired`, `unknown`. Nothing
finer. `UsageLimitExceeded` does not say **which** ceiling was hit except in its message text, and
`contracts/agent_runtime.py:38-52` states the rule that governs this seam — the adapter maps by
type, "never by string-matching an error message." A `tokens_exhausted` / `requests_exhausted` /
`tool_calls_exhausted` vocabulary would be unimplementable without breaking that rule.

`deadline_expired` maps from `RunCancelled`; `budget_exhausted` from `UsageLimitExceeded`;
`within_budget` from a normal return; `unknown` from every other failure path (provider error,
invalid output, capability error), where no budget verdict was reached.

**What this does not cover:** an operator sees that *a* ceiling was hit, not *which*. The configured
ceilings are visible in settings, and `usage` — when available — shows how close the run got; when
usage is `null` (Decision 5) neither is available and the record says so.

### Decision 7 — Cost is estimated from application-configured prices; unpriced is `null`, not zero

New settings, both defaulting to `0.0` and both parsed with a **non-negative** parser (not
`_positive_float` — a genuinely free model has a real price of zero):
`AGENT_MODEL_INPUT_USD_PER_MTOK`, `AGENT_MODEL_OUTPUT_USD_PER_MTOK`.

`adapters/telemetry/cost.py` computes
`(input_tokens * in_rate + output_tokens * out_rate) / 1_000_000` and returns:

* a float with label `cost_basis="configured"` when **either** rate is explicitly configured;
* `None` with `cost_basis="unpriced"` when neither is configured;
* `None` with `cost_basis="usage_unavailable"` when tokens are `null`.

**Known gap (code review, 2026-09-04 — accepted for this MVP, not fixed):** `Settings` stores each
rate as a plain float with no sentinel distinguishing "explicitly configured to 0" from "left at the
default 0.0". Consequently a **half-configured** price — one rate set, the other left at its 0.0
default — is reported as fully `cost_basis="configured"`, with the unset rate silently contributing
$0 to that side of the estimate and no signal that it was never priced. No settings-level validation
was added to reject this (that would require every deployment to set both rates or neither,
changing today's accepted single-rate configurations into a startup failure). Ledgered instead of
enforced — see `deferred-work.md`, "Deferred from: code review of story-5.1".

These are **not** budgets and are deliberately outside `AC2_CEILING_FIELDS` — NFR16's positive-value
rule governs ceilings that bound a run, and a price rate bounds nothing.

The default local model is `agent_runtime_model="test"` (`settings.py:87`), so the default local
posture is `unpriced` — which is the honest answer, and is why the distinction from `0.0` had to be
made rather than assumed away.

**Corrected at code review (2026-09-04) — this paragraph originally claimed the opposite of the
verified behavior.** It read: "the estimate ignores `cache_read_tokens` and `cache_write_tokens`…
the estimate is therefore a floor." That was wrong: `pydantic-ai`'s `UsageBase.input_tokens` is a
parent bucket that **already includes** cache tokens (confirmed against the installed 2.27.0
source), so pricing the full `input_tokens` figure at the input rate — with no cache-specific
rate — double-billed cache tokens at full input price, making the original estimate a **ceiling**
(an overcount) for any cache-using provider, not a floor. Fixed: two new optional settings,
`AGENT_MODEL_CACHE_READ_USD_PER_MTOK` / `AGENT_MODEL_CACHE_WRITE_USD_PER_MTOK` (default `0.0`,
meaning "contributes nothing," not "caching is free"), and `estimate_cost_usd` now prices the
non-cache remainder of `input_tokens` at the input rate and the cache portions separately
(`backend/adapters/telemetry/cost.py`). It is still per-run, not per-request: a run making several
model requests gets one summed figure.

### Decision 8 — The stable identifier is `agent_run_id`, falling back to `schedule_run_id`; AC2's three surfaces are `persisted_event`, `audit_event`, and the log stream

AC1 says "every value is attributable to one agent run", but **a schedule run can exist with no
agent run**: `schedule_run` has no `agent_run_id` column (`adapters/postgres/schema.py:439-452`),
`approval_request.agent_run_id` is nullable (`:511`), and Story 3.6 lets a planner start an
optimization from the UI. Reading AC1 literally would either drop the solver and queue records or
force a fabricated agent run.

Resolution: **every telemetry record carries at least one durable run identifier** — `agent_run_id`
where one exists, `schedule_run_id` otherwise — and AC2's "stable run or correlation identifier" is
satisfied against whichever the record carries. AC2's three surfaces are concrete:
`persisted_event` (product state, columns at `schema.py:319-323`), `audit_event` (authoritative
audit, `schema.py:520`), and this story's log stream. Task 12 proves one real run is findable by
`agent_run_id` in all three.

**What this does not cover:** records that legitimately have neither. An `api.request.completed`
record for a 401, a 404, or a health check carries `request_id` alone and is **deliberately not
run-attributable**; the guard in Task 11 asserts the run-identifier rule over the seven run-scoped
events and exempts `api.request.completed` by name, rather than being weakened to "usually". It also
does not add a join: correlation carries only identifiers already present at the call site, so a
solver record does not gain a `conversation_id` it would have to query for (Decision 4's no-query
rule).

### Decision 9 — One `APP_VERSION` constant, read by both audit and telemetry

AC2 requires "the same lineage" across audit and logs. `audit_event.app_version` is written from a
hard-coded `"0.1.0"` in four places today. If telemetry hard-codes a fifth copy, the two surfaces
can silently disagree about which build produced a run — which is precisely the lineage AC2 asks to
be discoverable.

New `backend/application/app_version.py` exporting `APP_VERSION = "0.1.0"`. The four existing
default arguments and `api/main.py:56`'s `FastAPI(version=...)` are repointed at it. Value
unchanged; no behaviour change; the string exists once.

**What this does not cover:** it does not derive the version from `pyproject.toml`, a git SHA, or a
build stamp, and it does not make the constant and `pyproject.toml:3` verify each other — they stay
two literals that happen to agree. Binding a real build identity is Story 5.3's image-digest work
(AR27), and doing it here would produce a second, competing definition of "the application version"
before that story chooses one.

### Decision 10 — No exporter, no Logfire SDK, no CloudWatch, no OTel span

None of the three appears in AC1 or AC2. AR27 forbids adding a planned dependency before its
implementation gate, and `backend/pyproject.toml:26-28` records the deliberate work already done to
keep the Logfire SDK out of the tree. Story 5.2's acceptance criteria own "any configured trace
export" and its default-off posture; AD-12 gives CloudWatch to the hosted epic, and the ledger
already records `diagnosis:cloudwatch_owned_by_epic_6` (`deferred-work.md:508,639`).

**Ownership of the Stack table's `Logfire SDK 4.38.0` row therefore moves to Story 5.2**, and the
row stays `planned` after this story. Say so in Completion Notes rather than leaving a reader to
infer that "the telemetry story" satisfied it.

**What this does not cover:** the existing OpenTelemetry surface is untouched and stays exactly as
Story 2.1 left it — `InstrumentationSettings(include_content=False)` in `agent/runtime.py:129-134`,
with `opentelemetry-sdk` dev-only. This story emits no span, adds no span attribute, and does not
change what PydanticAI's own instrumentation records.

### Decision 11 — No evidence file, no Gate A check, no golden case, zero frontend diff

Story 5.1's acceptance criteria name no artifact. The one artifact this story might have produced —
`log-metric-contract.json` — was explicitly dropped
(`sprint-change-proposal-2026-08-09-epics-2-5.md:161`). `docs/EVIDENCE-CONVENTION.md` governs any
story that **produces** an `evidence/**/*.json`; this story produces none, so it registers no
`GateACheck`, adds no `NFR29_GATES` invariant, adds no path to the exact registered-evidence set in
`tests/test_gate_a_readiness.py:267-284`, and regenerates nothing under `evidence/`.

**What this does not cover:** it means nothing release-blocking guards this instrumentation. If a
producer stops emitting, the guards in Tasks 10–13 go red in CI, but no Gate A row and no NFR29
invariant does. That is the accepted consequence of the replan's decision, restated here so it is
not rediscovered later as a gap.

### Decision 12 — No free text enters a telemetry record

`TelemetryRecordV1` has **no** message, detail, summary, or error-text field. Specifically excluded:
`AgentRunOutcomeV1.summary` (which is `str(exc)[:200]` on every adapter failure path —
`agent/runtime.py:257,264,301`), exception messages, prompts, model output, tool arguments, tool
results, workforce rows, schedule payloads, and approval evidence. The only string-valued fields are
the closed `event` name, the allow-listed labels, stringified UUIDs in `correlation`, and
`APP_VERSION`.

`failure_reason` is admitted as a label because it is a closed vocabulary plus manifest-declared
capability codes, and `agent/runtime.py:286-291` already **refuses** any code no granted manifest
declares — the value set is bounded by the registry, not by a model.

**What this does not cover:** this constrains the typed channel only. It does not scrub the two
pre-existing `logger.exception(...)` calls (Decision 1), and it is **not** a content-minimization
proof — no allow-list is enforced at an export boundary, no adversarial or secret fixture is run,
and no scrubber exists. NFR3/NFR4/NFR5/NFR27/NFR29/NFR30 and
`evidence/story-5.2/content-minimization-report.json` are Story 5.2's entirely. What this story
delivers to 5.2 is a **typed record with a closed field set to assert against**, instead of
free-form log lines.

### Decision 13 — Ledger disposition: one re-points, five stay open and untouched

* `deferred-work.md:585` — "The agent's complete tool transcript is not persisted. **Owner/revisit
  trigger: Epic 5 (Story 5.1)**, where tool execution becomes a governed persisted capability."
  **RE-POINT, do not close.** The trigger's premise is false for this story: 5.1 makes tool
  execution *observable* (name, duration, outcome — Decision 12 forbids arguments and results), not
  *persisted*. Nothing here writes a tool transcript to PostgreSQL, and Story 5.2 forbids logging
  tool arguments and results outright, so no Epic 5 story can be its owner. Re-point to **open**,
  triggered by the first story that requires replaying a tool call's inputs.
* `deferred-work.md:465`, `:467`, `:494` — no production worker composition (`--runtime-factory` has
  no non-test factory), `cancellation_requested` with no worker, and the Runs list's polling-vs-SSE
  decision. All three say **"Owner: Epic 5/6"**, and all three are blocked on a *runnable production
  worker*, which is Story 5.3's one-command run. Leave open and untouched; do not fix them here and
  do not re-point them.
* `deferred-work.md:50` (a second SIGTERM cannot abort an in-flight `run_once`) and `:193` (the Gate
  A readiness gate cannot be run twice) both name Epic 5. `:50` is Story 5.3's process-supervision
  work; `:193` is retro action **A5**, owned by Murat and Amelia and gating Story 5.4. Neither is
  this story's. Leave untouched.

**What this does not cover:** Task 13 edits `deferred-work.md` for the one re-point above and adds
this story's own new entries. It reconciles nothing else, and it does not touch `sprint-status.yaml`
beyond this story's own row.

---

## Tasks / Subtasks

- [x] **Task 1 — Re-derive every baseline before writing anything** (Decisions 1–13)
  - [x] From `backend/`: `uv run --frozen pytest -q`, `uv run --frozen pytest -m postgres -q`,
        `uv run --frozen pytest tests/test_evidence_convention.py -q`,
        `uv run --frozen pytest tests/architecture -q`.
  - [x] Record all counts in Debug Log References, with **totals** alongside any pass/skip split —
        Story 3.12's review established that the split is environment-conditional while the total is
        the stable invariant.
  - [x] Do **not** run the frontend suites: this story has a zero-line frontend diff (Decision 11).
        If a frontend file changes, stop and re-read Decision 11.
  - Acceptance boundary: no code is written until the numbers are in the Debug Log. Any later
    failure is attributed against these numbers, never against Story 4.6's.

- [x] **Task 2 — Read the files this story modifies, before editing any of them**
  - [x] `backend/agent/runtime.py` (the deadline/cancellation mechanism at `:229-310` and the
        instrumentation construction at `:120-134`), `backend/agent/capability_tools.py`
        (`_register_module.execute`, `:81-118`).
  - [x] `backend/application/contracts/agent_runtime.py` (`AgentBudgetV1`, `AgentRunOutcomeV1`),
        `backend/application/ports/agent_runtime.py`, `backend/application/capabilities/deps.py`.
  - [x] `backend/api/main.py` (both existing middlewares and the CORS registration, `:196-310`),
        `backend/api/routers/conversations.py` (`send_message` `:176-182`, `execute_agent_turn`
        `:189-411`), `backend/api/deps.py`.
  - [x] `backend/application/use_cases/lease_and_execute_schedule_run.py`,
        `backend/application/use_cases/execute_schedule_run.py`,
        `backend/application/use_cases/decide_approval.py`, `backend/worker/main.py`,
        `backend/settings.py`.
  - [x] `backend/tests/architecture/test_agent_runtime_boundaries.py` (the guard shape to copy) and
        `backend/tests/architecture/test_model_outage_boundaries.py:550` (the never-blocks proof
        shape to copy).
  - Acceptance boundary: the File List records which of these were read, not merely opened.

- [x] **Task 3 — Write the owned contract `backend/application/contracts/telemetry.py`** (AC1, AC2;
      Decisions 3, 5, 12)
  - [x] `SCHEMA_VERSION = "1"` and the `V1` naming, matching every sibling in `contracts/`.
  - [x] `TelemetryEventV1` — a `Literal` of exactly eight names:
        `api.request.completed`, `agent.run.completed`, `agent.model.calls.completed`
        (renamed from `agent.model.call.completed` at code review — see Review Findings),
        `agent.tool.call.completed`, `solver.run.completed`, `job.leased`,
        `run.first_event.persisted`, `approval.decided`.
  - [x] `TELEMETRY_LABEL_KEYS` — a module-level `frozenset` of the twelve keys named in Decision 3,
        closed.
  - [x] `CorrelationV1` — frozen dataclass, all ten identifiers optional and defaulting to `None`.
  - [x] `AgentUsageV1` — `requests`, `tool_calls`, `input_tokens`, `output_tokens`,
        `cache_read_tokens`, `cache_write_tokens`, each optional and defaulting to `None`.
  - [x] `BudgetOutcomeV1` — a `Literal` of `within_budget`, `budget_exhausted`, `deadline_expired`,
        `unknown` (Decision 6). Write the reason it is this coarse into the module docstring, citing
        `contracts/agent_runtime.py`'s map-by-type rule, so a later editor does not "improve" it.
  - [x] `TelemetryRecordV1` — `schema_version`, `event`, `occurred_at`, `app_version`,
        `correlation`, `labels`, and the measurement fields, every one optional (Decision 5), each
        name carrying a spine unit suffix: `duration_ms`, `queue_age_s`, `approval_age_s`,
        `estimated_cost_usd`, plus optional `usage` and `budget_outcome`.
  - Acceptance boundary: **no** message, detail, summary, error-text, or free-string field exists on
    any type in this module (Decision 12).

- [x] **Task 4 — Write the port `backend/application/ports/telemetry.py`** (Decisions 1, 4)
  - [x] `TelemetrySink` Protocol: `emit(self, record: TelemetryRecordV1) -> None`. The docstring
        states the two obligations any implementation must honour — **never raise**, and **never
        perform I/O against the product database** — citing AD-12.
  - [x] `NullTelemetrySink` — the safe default for every existing call site and test that does not
        care.
  - Acceptance boundary: this module imports nothing outside `typing` and
    `application.contracts.telemetry`. Mirror the shape of `application/ports/agent_runtime.py`.

- [x] **Task 5 — Write `backend/adapters/telemetry/`** (AC1; Decisions 2, 4, 7)
  - [x] `json_logs.py` — `JsonLogTelemetrySink` serialising one record to one JSON object
        (UUID to string, datetime to RFC 3339 UTC, `None` preserved as JSON `null` and never
        dropped) and writing it through a named stdlib logger. `emit` wraps serialization **and**
        the log call in one `except Exception: return` (Decision 4).
  - [x] `configure_json_logging()` — idempotent process-start configuration installing the JSON
        formatter. Called from `api/main.py`'s `lifespan` and `worker/main.py`'s entry only; **never
        at import time** in any library module, or importing `settings` would reconfigure logging in
        every test process.
  - [x] `cost.py` — `estimate_cost_usd(usage, input_rate, output_rate)` returning the value and the
        `cost_basis` label, exactly per Decision 7's three cases.
  - Acceptance boundary: `adapters/telemetry/` imports no framework — no FastAPI, no SQLAlchemy, no
    PydanticAI, no Logfire, no OpenTelemetry (Decision 10).

- [x] **Task 6 — Add `APP_VERSION` and repoint its five existing copies** (AC2; Decision 9)
  - [x] New `backend/application/app_version.py` with `APP_VERSION = "0.1.0"`.
  - [x] Repoint the `app_version` defaults in `use_cases/decide_approval.py`,
        `use_cases/promote_baseline.py`, `use_cases/request_approval.py`, the literal at
        `api/routers/approvals.py:395`, and `FastAPI(version=...)` at `api/main.py:56`.
  - Acceptance boundary: the value is unchanged and no test changes. Afterwards the literal
    `"0.1.0"` survives in `backend/` in exactly three places — `application/app_version.py`,
    `pyproject.toml:3`, and the fixture value at
    `tests/test_approval_governance_postgres.py:347`. The test literal stays: it is a fixture's
    expected value, not a production source of the version.

- [x] **Task 7 — Carry usage and budget outcome across the AgentRuntime seam** (AC1; Decisions 5, 6)
  - [x] Add optional `usage` and `budget_outcome` fields to `AgentRunOutcomeV1`, both defaulting to
        `None` so every existing construction stays valid.
  - [x] In `agent/runtime.py`, translate `result.usage` into `AgentUsageV1` on the success path.
        **Translate field by field; never store the framework object** — `RunUsage` is a PydanticAI
        type and `find_framework_typed_contract_fields` exists to catch exactly that.
  - [x] Set `budget_outcome` on all four arms: `within_budget` on normal return, `deadline_expired`
        in the `RunCancelled` handler (`:254`), `budget_exhausted` in the `UsageLimitExceeded`
        handler (`:258`), `unknown` on every other failure path.
  - [x] Leave `usage` as `None` on every raising path — do not synthesise zeros (Decision 5).
  - [x] Measure model-call latency around `self._agent.run_sync` with `time.perf_counter()` and emit
        `agent.model.calls.completed` (renamed at code review), including on the exception paths
        (`try`/`finally`).
  - Acceptance boundary: `tests/architecture/test_agent_runtime_boundaries.py` stays green with no
    edit to `FRAMEWORK_TYPE_NAMES` or `FORBIDDEN_ROOT_MODULES`. If it goes red, the translation
    leaked a framework type — fix the translation, never the guard.

- [x] **Task 8 — Instrument the request path** (AC1, AC2; Decisions 3, 8)
  - [x] Add an optional `telemetry` sink field to `AgentDepsV1`
        (`application/capabilities/deps.py`), defaulting to `None`, after `tool_result_sink`.
  - [x] Add `get_telemetry_sink()` to `api/deps.py`, returning a process-singleton
        `JsonLogTelemetrySink` — overridable in tests exactly like the other dependencies.
  - [x] New `@app.middleware("http")` in `api/main.py` emitting `api.request.completed`:
        server-side `duration_ms`, `request_id` (minted here and stashed on `request.state`),
        `route_template`, `method`, `status_class`.
  - [x] **Read `request.scope.get("route")` AFTER `await call_next(...)` returns, never before** —
        see Trap 1. Use `route.path_format`, never `request.url.path`. When no route matched, label
        `route_template` as the literal `"unmatched"`.
  - [x] **Skip the two SSE routes** (`/conversations/{id}/events`, `/schedule-runs/{id}/events`) —
        see Trap 2.
  - [x] Call `configure_json_logging()` from the `lifespan` startup half.
  - [x] In `execute_agent_turn` (`routers/conversations.py`), measure claim-to-finalize with
        `perf_counter()` and emit `agent.run.completed` after `_finish()` with the end-to-end
        `duration_ms`, the outcome's `usage`, `budget_outcome`, `estimated_cost_usd` and
        `cost_basis`, and labels `agent_run_status`, `failure_reason`, `model`. Emit on **every**
        exit path, including the `except Exception` arm at `:290-297` that finalizes a terminal
        outcome.
  - Acceptance boundary: the middleware is registered **after** the `CORSMiddleware` call at
    `api/main.py:305` so it is outermost and measures total server-side handling; record in a
    comment that this ordering is deliberate.

- [x] **Task 9 — Instrument the capability, worker, solver, and approval producers** (AC1;
      Decisions 3, 4, 8)
  - [x] `agent/capability_tools.py` — wrap `_register_module.execute` in `try`/`finally`, emitting
        `agent.tool.call.completed` with `duration_ms`, label `capability_name`, label
        `failure_reason` (the manifest code) or absent on success, and `ctx.deps`' correlation.
        Emit on the `ApprovalRequired`, `ModelRetry` and error arms too — a suspended or retried
        tool call is exactly the one an operator is diagnosing.
  - [x] `application/use_cases/lease_and_execute_schedule_run.py` — after a successful
        `lease_next_job`, emit `job.leased` with `queue_age_s` computed from `lease.created_at`
        (`JobLeaseV1.created_at`; do not add a column) and label `job_type`.
  - [x] Emit `solver.run.completed` at the point the solve result is available, taking
        `duration_ms` from the **already measured** `wall_time_seconds`
        (`engine/governed_adapter.py:174`), converted to milliseconds. Do not start a second timer
        around the solve. Label `solver_status`; correlate on `schedule_run_id` and
        `schedule_version_id`.
  - [x] Emit `run.first_event.persisted` for the **schedule-run** path only, computed from
        `job_queue.created_at` to the first persisted event's `occurred_at` for that
        `schedule_run_id` — both server clock, one clock. See Trap 5 for why the agent-run path gets
        no separate number.
  - [x] `application/use_cases/decide_approval.py` — add an optional `telemetry` keyword and emit
        `approval.decided` with `approval_age_s` computed from `binding.created_at`
        (`ApprovalBindingV1.created_at`, already read by `adapters/postgres/approval.py:20`) and
        label `approval_outcome`.
  - [x] `worker/main.py` — call `configure_json_logging()` at process start and compose the sink
        into the worker's runtime, mirroring how the API composes it.
  - Acceptance boundary: **no new database query is added for telemetry** and **no new column or
    migration is created**. Every value above comes from a field already in hand at its call site.

- [x] **Task 10 — `backend/tests/test_telemetry_contracts.py` and `test_telemetry_json_sink.py`**
      (AC1; Decisions 2, 4, 5, 7)
  - [x] The eight-name `TelemetryEventV1` vocabulary and the twelve-key label allow-list are
        asserted as **exact sets**, so adding a ninth name or a thirteenth key is a deliberate edit.
  - [x] `None` survives serialization as JSON `null` and is never dropped or coerced to `0`
        (Decision 5) — assert on the parsed JSON, not on the record object.
  - [x] `estimate_cost_usd` returns all three Decision 7 cases, each with its `cost_basis`, and the
        unpriced case returns `None` rather than `0.0`.
  - [x] `emit` swallows a serialization failure and a handler failure without raising.
  - [x] `configure_json_logging()` is idempotent across repeated calls.

- [x] **Task 11 — `backend/tests/architecture/test_telemetry_boundaries.py`** (AC2; Decisions 1, 3,
      4, 8, 10, 12)
  - [x] **NFR22 label guard**: every label key emitted by every producer is in
        `TELEMETRY_LABEL_KEYS`, and **no label key ends in `_id`**.
  - [x] **Route-template guard**: drive a real request against a parameterised route through the
        `TestClient` and assert the `route_template` label is the literal
        `/api/v1/conversations/{conversation_id}/messages` — that is, that the recorded value
        contains no UUID. This is what makes Trap 1 mechanically impossible to reintroduce.
  - [x] **Run-attribution guard** (Decision 8): each of the seven run-scoped events carries
        `agent_run_id` or `schedule_run_id`; `api.request.completed` is exempted **by name** in an
        explicit set, never by weakening the rule.
  - [x] **AD-1 import guard**: extend the existing AST helpers' pattern — `backend/domain/**` and
        `backend/application/**` import neither `adapters.telemetry` nor `logging`.
  - [x] **Free-text guard** (Decision 12): no field on any type in `contracts/telemetry.py` is named
        `message`, `detail`, `summary`, `error`, `text`, `prompt`, `args`, `arguments`, `result`, or
        `content`.
  - [x] **Never-blocks guard** (Decision 4): with a sink that raises on every `emit`, the approval
        decision still commits, the baseline still moves, and the audit row still exists. Copy the
        shape of `test_model_outage_boundaries.py:550`.
  - [x] Every guard above is also run against **synthetic violating source**, the way
        `test_agent_runtime_boundaries.py:334-360` does — a guard nobody has seen go red is a guard
        nobody has tested.

- [x] **Task 12 — `backend/tests/test_telemetry_correlation.py` — AC2's lineage proof**
      (`@pytest.mark.postgres`)
  - [x] Drive one real agent run end to end. Capture emitted records with a recording sink.
  - [x] Assert the same `agent_run_id` is findable in **all three**: `persisted_event` rows
        (product state), the `audit_event` row (authoritative audit), and the emitted records.
  - [x] Assert `app_version` on the telemetry records equals `audit_event.app_version` (Decision 9).
  - [x] Assert no emitted record contains the planner's message text, the model's output text, any
        tool argument, or any tool result (Decision 12) — assert on the serialized JSON string, not
        on the record objects, so a field added later that stringifies content is caught.
  - [x] Assert the audit row is unchanged by this story: telemetry adds no audit write and removes
        none (AC2's "authoritative audit remains the business record of truth").

- [x] **Task 13 — Configuration, documentation, and ledger** (Decisions 7, 10, 13)
  - [x] `backend/settings.py`: add the two price fields with a **non-negative** parser. Do **not**
        add them to `AC2_CEILING_FIELDS` (Decision 7).
  - [x] `backend/.env.example` and `docs/CONFIGURATION.md` (sections *Backend environment variables*
        and *Defaults*): document both variables and state that unset means `unpriced`, not free.
  - [x] `_bmad-output/implementation-artifacts/deferred-work.md`: re-point `:585` exactly as
        Decision 13 states; add this story's own new entries (at minimum: the unrecoverable usage on
        the two raising paths from Decision 5, and the unguarded label-**value** cardinality from
        Decision 3).
  - Acceptance boundary: `:465`, `:467`, `:494`, `:50` and `:193` are **not** edited.

- [x] **Task 14 — Demonstrated-red mutation table** (retro action A1)
  - [x] For every guard added in Tasks 10–12, produce a red by **mutating code that is already
        green** — never by an unresolved import, a missing symbol, or a first draft.
  - [x] Record a table in the Dev Agent Record with the four columns retro A1 names: the mutation
        applied to real code, the guard that should redden, the before state, and the after state.
  - [x] Suggested mutations, each targeting a real defect this story exists to prevent: label the
        route with `request.url.path` instead of `path_format`; return `0` instead of `None` from
        `estimate_cost_usd` when unpriced; synthesise a zero-token `AgentUsageV1` on the
        `UsageLimitExceeded` arm; add a `summary` field to `TelemetryRecordV1`; add `agent_run_id`
        to `TELEMETRY_LABEL_KEYS`; import `logging` in an `application/use_cases/` module; make the
        raising sink's exception escape `emit`.
  - Acceptance boundary: a guard that cannot be made to fail by a relevant mutation does not count
    and must be replaced, not documented away.

- [x] **Task 15 — Re-run every Task 1 suite and compare**
  - [x] All four backend suites green, with counts **at or above** Task 1's, and any delta explained
        per test in the Debug Log.
  - [x] `git diff --stat` shows **zero** frontend files, **zero** files under `evidence/`, **zero**
        files under `backend/migrations/`, and no change to `.github/workflows/ci.yml`.

---

### Review Findings

Code review of story-5.1 (2026-09-04). Three parallel layers (Blind Hunter, Edge Case Hunter,
Acceptance Auditor) plus independent verification: full default suite re-run (1555 passed / 2
skipped / 7 deselected — matches the Debug Log exactly), three mutation-table rows independently
re-run and confirmed red for the stated reason, and every high/decision-grade finding below was
confirmed by reading the actual call site (and, where a library's behavior was load-bearing, by
importing it) before being recorded.

- [x] [Review][Decision→Patch, fixed] `configure_json_logging()` raised the process root logger from
      WARNING to INFO, so every third-party logger (sqlalchemy, httpx, etc.) flowed free-text
      through the same JSON formatter this story installs — verified with a live repro showing an
      emitted SQL statement with a literal email address, and full request URLs from `httpx`'s own
      logger. **Resolved: option (a).** Fixed to set the level on the dedicated
      `shiftmind.telemetry` logger instead of `target` (which defaults to root); the handler is
      still installed on `target` so propagated telemetry records reach it. Root logger now stays
      at its prior level (verified: root level 30/WARNING, `shiftmind.telemetry` level 20/INFO; a
      third-party `.info()` call with a seeded secret now produces zero output, a telemetry `emit`
      still produces its one JSON line). `tests/test_telemetry_contracts.py`,
      `tests/test_telemetry_json_sink.py`, `tests/test_telemetry_request_path.py`,
      `tests/test_telemetry_correlation.py`, `tests/architecture` — 77 passed, no regression. [backend/adapters/telemetry/json_logs.py:63-77; backend/api/main.py:58; backend/worker/main.py:143]
- [x] [Review][Decision→Patch, fixed] `agent.model.call.completed` was emitted from a single
      `finally` around the *entire* `run_sync` call, so its `duration_ms` and `usage` cover every
      model request **and** every tool execution in the run, not one model call — tool time is
      double-counted against what NFR15 calls "model … latency" (tool latency is also reported
      separately as `agent.tool.call.completed`). No pydantic-ai hook exists today for per-model-
      request timing without deeper framework work. **Resolved: option (a).** Renamed the event to
      `agent.model.calls.completed` (plural) in `TelemetryEventV1`, with a caveat comment on the
      Literal explaining the run-level (not per-call) semantics and pointing back to this finding.
      Updated every reference: `agent/runtime.py`, `tests/architecture/test_telemetry_boundaries.py`,
      `tests/test_agent_runtime_adapter.py`, `tests/test_telemetry_contracts.py`, and this story's
      own Task 3/Task 9 text. `tests/test_telemetry_contracts.py`, `tests/test_telemetry_json_sink.py`,
      `tests/test_telemetry_request_path.py`, `tests/test_telemetry_correlation.py`,
      `tests/test_agent_runtime_adapter.py`, `tests/architecture` — 102 passed, no regression. [backend/application/contracts/telemetry.py:21-31; backend/agent/runtime.py:263-345]
- [x] [Review][Decision→Defer, resolved] Decision 7's three-`cost_basis` design does not fully hold
      against the actual settings model. **Re-examined during resolution: only one of the two
      originally-raised sub-issues is a real gap.** `pydantic_ai.usage.RunUsage` does default every
      token field to `0`, never `None` — but `estimate_cost_usd`'s `usage is None` check (not
      `usage.input_tokens is None`) is what actually reaches `"usage_unavailable"` in practice, via
      the raising paths (`RunCancelled`/`UsageLimitExceeded`) where `outcome.usage` stays `None`
      entirely; that call site is exercised on every run regardless of outcome
      (`backend/api/routers/conversations.py`). So `usage_unavailable` is reachable and correct for
      its intended case — the field-level null check is redundant defensive code, not a defect.
      **The real, remaining gap:** `Settings` stores each price as a plain float with no sentinel
      for "explicitly configured to 0" vs. "left at the 0.0 default", so a half-configured price
      (one rate set, the other left at default) is reported as fully `cost_basis="configured"` — a
      silent undercount with no signal distinguishing it from an honest answer. **Resolved: option
      (2) from the follow-up discussion** — no settings-level validation added (would turn today's
      accepted single-rate configurations into a startup failure); documented instead in Decision 7
      and ledgered in `deferred-work.md`. [backend/adapters/telemetry/cost.py:16-24; backend/settings.py:88-90; story Decision 7]
- [x] [Review][Decision→Patch, fixed] The story's own Decision 7 text said the cost estimate
      "ignores `cache_read_tokens` and `cache_write_tokens`… and the estimate is therefore **a
      floor** for any cache-using provider." Verified against the installed `pydantic-ai` 2.27.0
      source (`UsageBase.input_tokens` docstring): `input_tokens` is a parent bucket that
      **already includes** `cache_read_tokens`/`cache_write_tokens` — providers that report them
      separately are normalized so the convention holds everywhere. `cost.py` priced the full
      `input_tokens` figure at the input rate with no cache-specific rate, so cache tokens were
      billed at full input price — the estimate was a **ceiling** that overcharged cache-heavy
      runs, the opposite of what the story documented. **Resolved: option (a).** Added
      `AGENT_MODEL_CACHE_READ_USD_PER_MTOK` / `AGENT_MODEL_CACHE_WRITE_USD_PER_MTOK` (both
      optional, default `0.0` = "contributes nothing," not "free") to `Settings`, parsed with the
      existing `_non_negative_float`; `estimate_cost_usd` now takes two additional optional rate
      parameters and prices `max(0, input_tokens - cache_read_tokens - cache_write_tokens)` at the
      input rate plus each cache bucket at its own rate. Wired through the one call site
      (`api/routers/conversations.py`), documented in `.env.example` and
      `docs/CONFIGURATION.md`, and Decision 7's "What this does not cover" paragraph corrected in
      place. New test `test_cost_estimator_prices_cache_tokens_separately_from_full_input_rate`
      covers both the no-cache-rate-configured case (cache tokens contribute $0, not full input
      price) and the cache-rate-configured case. `tests/test_telemetry_json_sink.py`,
      `tests/test_telemetry_contracts.py`, `tests/test_telemetry_request_path.py`,
      `tests/test_telemetry_correlation.py`, `tests/test_settings.py`,
      `tests/test_conversations_api.py`, `tests/architecture` — 143 passed, no regression. [backend/adapters/telemetry/cost.py:11-38; backend/settings.py:88-97,299-311,451-452; backend/api/routers/conversations.py:413-419]
- [x] [Review][Patch, fixed] AD-12 guard gap: the middleware resolved the route template and the
      telemetry sink **before** the `try:` that was supposed to make emission safe. Fixed:
      extracted `_emit_api_request_telemetry`, which puts route-template resolution and sink
      lookup entirely inside its own guarded body — nothing outside that function's `try` can
      turn a completed response into a 500. [backend/api/main.py]
- [x] [Review][Patch, fixed] No telemetry was emitted for any 5xx / unhandled-exception response.
      Fixed: `emit_request_telemetry` now wraps `call_next` in `try`/`except BaseException`,
      emitting with `status_class="5xx"` before re-raising, so an unhandled exception (which
      Starlette re-raises after building its response, per `versioned_unhandled_problem`'s own
      docstring) still produces a record. [backend/api/main.py]
- [x] [Review][Patch, fixed] `_declared_route_template`'s fallback rebuilds the entire OpenAPI
      schema per request, and that cost was included inside the reported `duration_ms`. Fixed:
      `_emit_api_request_telemetry` captures `duration_ms` as its first statement, before calling
      `_declared_route_template` at all. [backend/api/main.py]
- [x] [Review][Patch, fixed] Resumed-turn agent runs were entirely uninstrumented (`AgentDepsV1`
      for the resume path omitted `telemetry=`). Fixed: `_drive_resumed_turn` now takes
      `telemetry`/`request_id` parameters, wires `telemetry=telemetry` into `AgentDepsV1`, and
      (new) emits its own `agent.run.completed` unconditionally at the end — even when
      finalization itself failed, unlike the first-turn route before its own fix below. [backend/api/routers/approvals.py]
- [x] [Review][Patch, fixed] NFR22 correlation was broken for every agent-triggering HTTP request.
      Fixed: both `execute_agent_turn` (conversations.py) and the resumed-turn route
      (approvals.py) now read `request.state.telemetry_request_id` (falling back to a fresh
      `uuid4()` only if absent) instead of minting an unrelated second id, so `api.request.completed`
      and the agent-side records for the same request now share one request id. [backend/api/routers/conversations.py; backend/api/routers/approvals.py]
- [x] [Review][Patch, fixed] Two `execute_agent_turn` exit paths (`AgentRunNotQueuedError`,
      `RuntimeError` from `finish_agent_run`) returned before `agent.run.completed` was emitted.
      Fixed: extracted `_emit_agent_run_completed` and called it from both exception arms (with
      `agent_run_status="agent_run_not_queued"` / `"finalize_failed"`) as well as the success path,
      so a run that consumed tokens before either race still produces a record. [backend/api/routers/conversations.py]
- [x] [Review][Patch, fixed] `agent.tool.call.completed` mislabelled a normal, designed approval
      suspension with `failure_reason=exc.code`, and left a genuinely malformed call's
      `failure_reason` at `None`. Fixed: the `CapabilityApprovalRequired` branch no longer sets
      `failure_reason` (a suspend, not a failure); the missing-argument `ModelRetry` branch now
      sets `failure_reason="missing_argument"`. [backend/agent/capability_tools.py]
- [x] [Review][Patch, fixed] Admission-check approval denials (`ApprovalNotPendingError`,
      `StaleResourceVersionError`) emitted no telemetry at all. Fixed: both raise sites now call
      `_emit_approval_telemetry` first, with `outcome="approval_not_pending"` /
      `"stale_resource_version"`; `_emit_approval_telemetry` was refactored to take `outcome: str`
      directly (the two existing call sites already had the string on hand) instead of a
      `DecisionResultV1`, since only `result.outcome` was ever read from it. [backend/application/use_cases/decide_approval.py]
- [x] [Review][Patch, fixed] `run.first_event.persisted` was emitted inside Transaction A's `with`
      block, before that block committed. Fixed: the record is now built into a
      `pending_first_event_telemetry` local and the actual `_emit(...)` call moved to after the
      `with` block exits (commits), right before Transaction B begins. [backend/application/use_cases/lease_and_execute_schedule_run.py]
- [x] [Review][Patch, fixed] Task 12's real-agent-run correlation/content-minimization test never
      drove an actual agent run, so its "no leaked secret" assertions passed trivially. Fixed:
      the test now also drives a real `PydanticAIAgentRuntime` (a `FunctionModel` double, no
      network) with the real `demonstration` capability, using the run's real `agent_run_id` and
      the same recording sink used for `decide_approval`, so `agent.model.calls.completed` and
      `agent.tool.call.completed` records genuinely produced by code that saw `model_text`/
      `tool_argument` are now in the checked set. **Independently verified as non-vacuous**: a
      deliberate mutation making `agent.tool.call.completed` leak the raw tool-call `kwargs`
      reddened this test with the secret string in the assertion failure; reverting restored
      green. [backend/tests/test_telemetry_correlation.py]
- [x] [Review][Patch, fixed] The AD-1 boundary architecture guard scanned only
      `application`/`domain`; nothing guarded `adapters/telemetry/` itself against a later
      framework import. Fixed: added `forbidden_framework_imports_in_telemetry_adapter` and
      `test_telemetry_adapter_imports_no_framework`, scanning `adapters/telemetry/` for
      `fastapi`/`sqlalchemy`/`pydantic_ai`/`pydantic_graph`/`logfire`/`opentelemetry` imports, plus
      a synthetic-violation assertion in the existing guard-redness test. [backend/tests/architecture/test_telemetry_boundaries.py]
- [x] [Review][Patch, fixed] The Debug Log's test-count reconciliation claimed the +33 delta was
      "offset by removal of 1 redundant APP_VERSION literal assertion" — verified false. Fixed:
      corrected the Debug Log entry in place; see the note there for what was and wasn't
      re-verified. [story Debug Log; backend/tests/test_approval_governance_postgres.py:380]
- [x] [Review][Defer] `TELEMETRY_LABEL_KEYS`'s architecture guard is AST-based and only catches
      literal dict-key labels; a future runtime-computed label key would bypass it and reach the
      log with unbounded cardinality. No live producer trips this today. [backend/tests/architecture/test_telemetry_boundaries.py] — deferred, guard-completeness gap, no current bug
- [x] [Review][Defer] `tool_call_id` in `CorrelationV1` is a model-controlled, unbounded string
      with no truncation or validation — the one non-closed-vocabulary field in an otherwise
      closed-label contract. [backend/application/contracts/telemetry.py:78; backend/agent/capability_tools.py:137] — deferred, no current exploit path, worth a length cap before any real provider is wired in
- [x] [Review][Defer] Lower-confidence, cosmetic notes not independently re-verified in full depth:
      CORS preflight `OPTIONS` requests bucket into `route_template="unmatched"` alongside genuine
      404s; each telemetry record is JSON-serialized twice (once to validate, once to format); a
      re-leased job may report total time-since-first-enqueue as this lease attempt's own queue
      wait. [backend/api/main.py; backend/adapters/telemetry/json_logs.py:54-60; backend/application/use_cases/lease_and_execute_schedule_run.py] — deferred, low severity

**Dismissed as noise:** Blind Hunter's claim that `job.leased`'s `(now - lease.created_at)`
subtraction can raise `TypeError` on a tz-naive `created_at` — disproven: `JobLeaseV1.__post_init__`
(`backend/application/contracts/job_lease.py:95-100`) already rejects any non-UTC-aware
`created_at` at construction, so the record built in `lease_and_execute_schedule_run.py:120-134`
can never receive one.

---

## Dev Notes

### Traps — the quietest first

1. **`request.scope["route"]` is `None` before `call_next` and populated after it.**
   `@app.middleware("http")` (Starlette's `BaseHTTPMiddleware`) runs before routing. Routing happens
   downstream and mutates the *same* scope dict via `scope.update(child_scope)`
   (`starlette/routing.py:192,679`), with FastAPI setting `child_scope["route"] = self`
   (`fastapi/routing.py:823`). So reading the route before `await call_next(request)` yields `None`,
   and the obvious fallback — `request.url.path` — puts UUIDs into a metric label and violates NFR22
   directly. Read it **after**, use `route.path_format`, and label unmatched requests `"unmatched"`.

2. **The two SSE endpoints will report minutes of "API latency".**
   `GET /conversations/{id}/events` and `GET /schedule-runs/{id}/events` stream with 15-second
   heartbeats (`api/routers/conversations.py:463-537`). A duration middleware records the whole
   stream lifetime as request latency — an unbounded number that is not acknowledgement latency and
   would poison any percentile computed over the stream. Skip them by route template, and say in a
   comment that the exclusion is deliberate.

3. **There are already two unrelated `request_id`s per turn, and neither is a request correlation
   ID.** `accept_turn` mints one for the persisted event (`use_cases/accept_turn.py:32-35`);
   `execute_agent_turn` mints another for `AgentDepsV1` (`routers/conversations.py:232`). Do **not**
   unify them and do not repoint either at the middleware's new ID — they are persisted correlation
   values that Story 4.4's provenance reader and the `persisted_event` / `audit_event` rows already
   depend on. The middleware's `request_id` is a **third**, transport-scoped value that appears only
   on `api.request.completed`. AC2's stable identifier is `agent_run_id` (Decision 8), not any of
   the three.

4. **Two emission sites run inside a transaction that rolls back on exception.**
   `decide_approval` is inside TX2, and `api/main.py:58-75`'s handlers exist precisely so those
   exceptions escape the endpoint and unwind `get_site_context`. A sink that raises there rolls back
   a baseline promotion. Decision 4's swallow is not defensive style; it is the thing that keeps
   AD-12 true.

5. **The agent run's "first persisted event" is written inside the acknowledgement transaction.**
   `accept_turn` calls `repository.accept_turn`, which persists the message event in the same
   transaction that answers `POST /messages`, so a separate agent-side first-event latency would be
   a second name for a number `api.request.completed` already carries. Emit
   `run.first_event.persisted` for the **schedule-run** path only (job enqueue to first
   `RunProgress` event), which is AD-6's and AD-26's actual subject. Do not invent an agent-side
   value, and do not touch Story 3.5's NFR35 measurement or its
   `evidence/story-3.5/nfr35-first-run-event.json` — AD-26 allocates that threshold elsewhere and
   Gate B measures it.

6. **`str(exc)[:200]` is on every adapter failure path.** `agent/runtime.py:257,264,301` puts
   provider text into `AgentRunOutcomeV1.summary`. It is a legitimate product field. It must not
   reach a telemetry record (Decision 12). When emitting `agent.run.completed`, take `status`,
   `failure_reason` and `usage` from the outcome — never `summary`.

7. **`RunUsage` is a PydanticAI type.** Storing it on `AgentRunOutcomeV1` — even typed as `object` —
   makes the framework a persisted contract and is what `find_framework_typed_contract_fields`
   (`tests/architecture/test_agent_runtime_boundaries.py:170`) exists to catch. Translate field by
   field into `AgentUsageV1` inside `backend/agent/`, which is the one package allowed to see the
   framework.

8. **`configure_json_logging()` at import time will reconfigure logging for the whole test session.**
   Call it only from the API `lifespan` and the worker entry point. `settings.py` is imported by
   almost everything (`load_dotenv` runs at import), so a logging side effect placed near it becomes
   global and unremovable.

9. **`_positive_float` is the wrong parser for a price.** `settings.py`'s `_positive_float` rejects
   `0`, and a free model has a real rate of zero. Use a non-negative parser, and keep the price
   fields out of `AC2_CEILING_FIELDS` — that tuple exists to make an *unvalidated ceiling*
   detectable, and a price is not a ceiling.

10. **A telemetry field must not look like a scheduling metric.** `docs/DOMAIN-MODEL.md` §1 governs
    demand families and units; this story emits none. Do not add a "coverage", "shortfall", "unmet",
    "headcount" or "volume" field to a telemetry record — that would create a second, ungoverned
    producer of numbers the grounding layer is built to control.

### Files being modified — read these before editing

| File | What it does today | What this story changes | What must not break |
|---|---|---|---|
| `agent/runtime.py` | Owns the wall-clock deadline (`threading.Timer` plus `CancellationToken`, `:234-241`) and maps four framework exceptions to owned outcomes by type (`:254-310`) | Adds usage translation, `budget_outcome`, and model-latency emission | The map-by-type discipline and the `timed_out`/`budget_exhausted` distinction. Never string-match an exception message |
| `agent/capability_tools.py` | The single wrap point for every governed capability call (`_register_module.execute`, `:81-118`); raises `ApprovalRequired`, `ModelRetry`, or the module's error type | Adds `try`/`finally` timing and emission | Argument validation, the `approval_policy="none"` refusal at `:97-103`, the retryable-code mapping, and `tool_result_sink` ordering |
| `api/main.py` | Two `@app.middleware("http")` decorators plus CORS added last (`:196-310`) | Adds a third middleware, registered after CORS; `configure_json_logging()` in `lifespan`; `APP_VERSION` on the `FastAPI(...)` call | The Gate A legacy-route refusal and the session/CSRF enforcement, both of which return responses **without** calling `call_next` — the new middleware must record those too |
| `api/routers/conversations.py` | Claims, executes, and finalizes outside a transaction (`:189-411`); `except Exception` at `:290-297` finalizes a terminal outcome rather than surfacing an error | Adds end-to-end timing and `agent.run.completed` on every exit path | The "reaching a terminal status wins" invariant at `:288-297`. Emission must never turn a finalized failure into an unfinalized one |
| `application/use_cases/decide_approval.py` | TX2's decision, revalidation, terminalize, audit append, activity append — all in one transaction (`:97-146`) | Adds a `telemetry` keyword and one `approval.decided` emission | Atomicity. Emit **after** the writes are staged, and never let emission raise (Trap 4) |
| `application/use_cases/lease_and_execute_schedule_run.py` | Leases, executes, classifies fatal versus transient failure (`:97-140`); a transient failure must re-raise so the lease lapses | Adds `job.leased`, `solver.run.completed`, `run.first_event.persisted` | The fatal/transient classification. An emission inside the `except` arms must not change which exception propagates |
| `application/capabilities/deps.py` | The trusted, server-owned dependency bundle handed to every capability handler | Adds an optional `telemetry` sink field | Field ordering — every field after `tool_call_approved` has a default; the new one must too |
| `settings.py` | Frozen `Settings`, validated at process start; `AC2_CEILING_FIELDS` at `:37-46` | Adds two price fields | `AC2_CEILING_FIELDS` membership and `tests/test_settings.py` |

### Testing requirements

* **Where tests live:** unit and integration under `backend/tests/`, boundary guards under
  `backend/tests/architecture/`. pytest runs from `backend/` with `testpaths = ["tests"]`
  (`backend/pyproject.toml:48-49`); `backend/conftest.py` makes backend modules importable. Do not
  add a second rootdir.
* **Postgres-touching tests carry `@pytest.mark.postgres`.** They live inside the default suite and
  `pytest.skip()` when the service is absent — that is why CI runs the marked selection separately
  (`.github/workflows/ci.yml:236-248`).
* **No live provider.** `addopts = -m "not live"` (`backend/pyproject.toml:54`). This story adds no
  `@pytest.mark.live` test; the deterministic model double is the only model it needs (NFR26).
* **Every new guard is demonstrated red by mutating already-green code**, and the mutation table
  goes in the Dev Agent Record before review (Task 14, retro action A1). A missing-import red does
  not count.
* **Assert on serialized JSON, not on record objects**, wherever the claim is about what leaves the
  application — a field added later that stringifies content is only caught at the JSON boundary.

### Project structure notes

* `backend/adapters/telemetry/` is the spine's own declared location (*Structural Seed*: "adapters/
  — PostgreSQL, Cognito, S3, telemetry and provider adapters"). No variance.
* `backend/application/contracts/telemetry.py` and `backend/application/ports/telemetry.py` mirror
  the established pairing of `contracts/agent_runtime.py` with `ports/agent_runtime.py`. No
  variance.
* `backend/application/app_version.py` is a new single-constant module. The nearest precedent is
  `POLICY_GENERATION` in `application/capabilities/registry.py`; `config/constants.py` is
  deliberately not used — it holds solver-domain scaling knobs and nothing application-layer.
* `tests/architecture/` stays under `backend/tests/`, per the variance Story 2.1 already recorded
  and justified (`test_agent_runtime_boundaries.py:29-36`).

### Open questions — neither blocks this story

* ~~**Retro action A1 has not landed as a `bmad-dev-story` fact.**~~ **CLOSED 2026-09-03 — it
  landed, before this story reached implementation, which is what the retrospective asked for.**
  Commit `c4f5de1` adds the definition of demonstrated red (the red must come from mutating code
  that is already green; a red from an unresolved import or a first draft proves only that the test
  file loads) and the mutation-table requirement to `_bmad/custom/bmad-dev-story.toml`, plus a
  paired fact on `bmad-code-review`: the table must cover every new guard in the diff, a missing
  table is itself a finding, and the reviewer independently re-runs at least **one** row rather than
  only reading it — because checking the table alone would trade detection for paperwork. Task 14 is
  satisfied by the loaded fact rather than duplicating it.
* **`AGENT_RUNTIME_*` is absent from `backend/.env.example`.** Every Story 2.1 setting
  (`AGENT_RUNTIME_MODEL`, `AGENT_RUNTIME_API_KEY`, and the five budget ceilings) is documented in
  `settings.py` but missing from the example file. Pre-existing and not this story's; it becomes
  Story 5.3's, whose acceptance criteria require a clean clone to come up from a documented
  prerequisite set. Recorded here so 5.3 does not rediscover it.

### References

- `epics.md:1341-1348` — Epic 5 statement and coverage note; `:1349-1365` — Story 5.1 verbatim
- `epics.md:103` (NFR15), `:105` (NFR16), `:117` (NFR22), `:123` (NFR25), `:143` (NFR35),
  `:147` (AR1), `:172` (AR26), `:173` (AR27)
- `epics.md:1367-1383` — Story 5.2, which owns content minimization and any trace export
- `epics.md:1538-1556` — Release Gate; Gate B rows and their owners
- `ARCHITECTURE-SPINE.md` — AD-1, AD-7, AD-12, AD-19, AD-26; *Consistency Conventions*
  (**Correlation**, **Time and measures**); *Stack*; *Structural Seed*
- `sprint-change-proposal-2026-08-09-epics-2-5.md:161` — Story 5.1's slimming
- `epic-4-retro-2026-09-02.md` §4, §5, §6 — the demonstrated-red failure mode, Epic 5 preparation,
  action items A1, A3 and A5
- `docs/DOMAIN-MODEL.md` §1, §2, §3 — demand family/unit rule; the fail-closed-not-zero precedent
- `docs/EVIDENCE-CONVENTION.md` — not exercised; this story produces no evidence file (Decision 11)
- `deferred-work.md:50`, `:193`, `:465`, `:467`, `:494`, `:585` — the six ledger entries naming
  Epic 5 or Story 5.1, dispositioned in Decision 13

---

## Dev Agent Record

### Agent Model Used

Codex (GPT-5)

### Implementation Plan

1. Establish the owned telemetry contract, port, JSON/cost adapters, and shared application version behind focused unit tests.
2. Extend the runtime seam with owned usage/budget data, then instrument request, capability, worker, solver, persistence, and approval producers using injected non-blocking sinks.
3. Add boundary, correlation, configuration, and failure-isolation coverage; demonstrate every new guard red by mutating finished green code and restoring it.
4. Re-run all four baselines, verify zero frontend/evidence/migration/CI diff, reconcile the ledger, and move the story to review only after every gate is green.

### Debug Log References

- 2026-09-03 Task 1 baseline, `uv run --frozen pytest -q`: 1,522 passed + 2 skipped = 1,524 executed; 7 deselected. Green.
- 2026-09-03 Task 1 baseline, `uv run --frozen pytest -m postgres -q`: the first concurrent run produced 156 passed + 1 failed = 157 executed (NFR35 live-worker latency exceeded 5 seconds under contention); the required isolated rerun produced 157 passed = 157 executed, 1,374 deselected. Green baseline is the isolated run.
- 2026-09-03 Task 1 baseline, `uv run --frozen pytest tests/test_evidence_convention.py -q`: 87 passed = 87 executed. Green.
- 2026-09-03 Task 1 baseline, `uv run --frozen pytest tests/architecture -q`: 60 passed = 60 executed. Green.
- Frontend suites deliberately not run per Decision 11; no frontend file had changed at this boundary.
- 2026-09-04 Task 14: every mutation below started from green product code, reddened the named guard, and was restored; the consolidated telemetry selection then passed 17 tests.
- 2026-09-04 first Task 15 default rerun: 1,555 passed + 2 skipped = 1,557 executed; 7 deselected; one worker-process test failed because the new JSON records filled its undrained Windows stderr pipe. The test harness was corrected to capture subprocess output in temporary files, retaining diagnostics without applying pipe backpressure.
- 2026-09-04 final Task 15, `uv run --frozen pytest -q`: 1,555 passed + 2 skipped = 1,557 executed; 7 deselected. Green; +33 executed versus Task 1 comprises 25 new telemetry/config/unit cases, 8 new architecture cases, and 1 new PostgreSQL correlation case. **Corrected at code review (2026-09-04):** the original line claimed this was "offset by removal of 1 redundant APP_VERSION literal assertion" — verified false: no test assertion is removed anywhere in the tracked diff, and the literal fixture at `tests/test_approval_governance_postgres.py:380` is unchanged. The 25/8/1 breakdown itself was not re-audited case-by-case at review; only the removal claim is corrected here.
- 2026-09-04 final Task 15, `uv run --frozen pytest -m postgres -q`: 158 passed = 158 executed; 1,407 deselected. Green; +1 is `test_telemetry_correlation.py`.
- 2026-09-04 final Task 15, `uv run --frozen pytest tests/test_evidence_convention.py -q`: 87 passed = 87 executed. Green; unchanged.
- 2026-09-04 final Task 15, `uv run --frozen pytest tests/architecture -q`: 68 passed = 68 executed. Green; +8 are `test_telemetry_boundaries.py`.
- 2026-09-04 fences: zero changed files under `frontend/`, `evidence/`, `backend/migrations/`, or `.github/workflows/ci.yml`. `git diff --check` passed; Ruff is not installed in the backend environment, so no Ruff result is claimed.

### Demonstrated-red mutation table (retro A1 — required before review)

| Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|
| Used `request.url.path` as the emitted route label in `api/main.py` | Parameterized route-template request guard | Green | Red with the concrete conversation UUID; restored green |
| Returned `0.0` for an unpriced model in `adapters/telemetry/cost.py` | Three-case cost estimator guard | Green | Red on `None` vs `0.0`; restored green |
| Synthesized zero-token usage on `UsageLimitExceeded` in `agent/runtime.py` | Raising-path unknown-usage guard | Green | Red because usage was not `None`; restored green |
| Added `summary` to `TelemetryRecordV1` | Free-text contract-field guard | Green | Red naming `summary`; restored green |
| Added `agent_run_id` to `TELEMETRY_LABEL_KEYS` | Exact twelve-key vocabulary guard | Green | Red on the thirteenth key; restored green |
| Imported `logging` in `application/use_cases/decide_approval.py` | AD-1 import boundary guard | Green | Red naming the application-layer import; restored green |
| Re-raised the approval telemetry sink exception | Approval promotion/audit never-blocks guard | Green | Red with `RuntimeError`; restored green |
| Removed `agent_run_id` from model-call correlation | Seven-event run-attribution guard | Green | Red naming `agent.model.call.completed`; restored green (event later renamed to `agent.model.calls.completed` at code review — same guard, same row) |
| Dropped top-level `None` values during JSON serialization | JSON-null preservation guard | Green | Red because `usage` was absent; restored green |
| Re-raised JSON sink serialization/handler failures | Sink isolation guard | Green | Red with the handler failure; restored green |
| Allowed repeated `configure_json_logging()` calls to add handlers | Idempotent process configuration guard | Green | Red with two configured handlers; restored green |
| Added a ninth `telemetry.unbounded` event | Exact eight-event vocabulary guard | Green | Red on the extra event; restored green |
| Removed approval `agent_run_id` correlation | PostgreSQL three-surface lineage guard | Green | Red with telemetry `{None}` vs persisted/audit run ID; restored green |
| Hard-coded a divergent approval telemetry app version | PostgreSQL audit/log version-lineage guard | Green | Red on `telemetry-version-drift`; restored green |
| Added a free-text field carrying the seeded tool result | PostgreSQL serialized content-minimization guard | Green | Red on `TOOL_RESULT_SECRET_5_1`; restored green |

### Completion Notes List

- Added the owned eight-event telemetry contract, non-blocking port, JSON-lines sink, deterministic cost estimator, and shared `APP_VERSION`.
- Instrumented API acknowledgement, agent/model/tool execution, durable job lease and first event, solver completion, and approval decisions with bounded labels and run correlation.
- Preserved unknown usage/cost as JSON `null`; budget outcomes are mapped by exception type, and exporter failures cannot change product or audit outcomes.
- Added exact-vocabulary, architecture, mutation, and real PostgreSQL lineage proofs. The authoritative audit remains unchanged at two rows for the exercised agent-backed approval lifecycle.
- Added non-negative model-price configuration and documentation. Re-pointed the tool-transcript ledger item and recorded unknown raising-path usage plus unguarded label-value cardinality.
- Logfire SDK ownership remains planned for Story 5.2; this story adds no exporter, OTel span, CloudWatch integration, dependency, migration, frontend change, or evidence artifact.

### File List

- Read before modification: `backend/agent/runtime.py`, `backend/agent/capability_tools.py`, `backend/application/contracts/agent_runtime.py`, `backend/application/ports/agent_runtime.py`, `backend/application/capabilities/deps.py`, `backend/api/main.py`, `backend/api/routers/conversations.py`, `backend/api/deps.py`, `backend/application/use_cases/lease_and_execute_schedule_run.py`, `backend/application/use_cases/execute_schedule_run.py`, `backend/application/use_cases/decide_approval.py`, `backend/worker/main.py`, `backend/settings.py`, `backend/tests/architecture/test_agent_runtime_boundaries.py`, `backend/tests/architecture/test_model_outage_boundaries.py`.
- Added: `backend/application/app_version.py`, `backend/application/contracts/telemetry.py`, `backend/application/ports/telemetry.py`, `backend/adapters/telemetry/__init__.py`, `backend/adapters/telemetry/cost.py`, `backend/adapters/telemetry/json_logs.py`, `backend/tests/architecture/test_telemetry_boundaries.py`, `backend/tests/test_telemetry_contracts.py`, `backend/tests/test_telemetry_correlation.py`, `backend/tests/test_telemetry_json_sink.py`, `backend/tests/test_telemetry_request_path.py`.
- Modified application/runtime: `backend/agent/capability_tools.py`, `backend/agent/runtime.py`, `backend/api/deps.py`, `backend/api/main.py`, `backend/api/routers/approvals.py`, `backend/api/routers/conversations.py`, `backend/application/capabilities/deps.py`, `backend/application/contracts/agent_runtime.py`, `backend/application/ports/schedule_run.py`, `backend/application/use_cases/decide_approval.py`, `backend/application/use_cases/execute_schedule_run.py`, `backend/application/use_cases/lease_and_execute_schedule_run.py`, `backend/application/use_cases/promote_baseline.py`, `backend/application/use_cases/request_approval.py`, `backend/adapters/postgres/schedule_run.py`, `backend/settings.py`, `backend/worker/lease_worker.py`, `backend/worker/main.py`.
- Modified tests/docs/ledger: `backend/tests/test_agent_runtime_adapter.py`, `backend/tests/test_conversations_api.py`, `backend/tests/test_decide_approval.py`, `backend/tests/test_lease_next_job.py`, `backend/tests/test_settings.py`, `backend/tests/test_worker_process_recovery_postgres.py`, `backend/.env.example`, `docs/CONFIGURATION.md`, `_bmad-output/implementation-artifacts/deferred-work.md`, `_bmad-output/implementation-artifacts/sprint-status.yaml`, and this story file.

## Change Log

- 2026-09-04 — Implemented Story 5.1 operational telemetry, correlation, cost/budget reporting, configuration, architecture and PostgreSQL guards; completed demonstrated-red verification and moved the story to review.
