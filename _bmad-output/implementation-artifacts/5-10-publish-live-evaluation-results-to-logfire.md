---
baseline_commit: 3bf0fb1
---

# Story 5.10: Publish Live-Evaluation Results to Logfire

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an AI engineer comparing models and runs,
I want live-conversation verdicts shown inside each conversation's trace and each suite run shown as
a Logfire experiment,
So that I can open a failing turn's trace from its verdict and compare runs side by side.

**Added 2026-09-24 by `sprint-change-proposal-2026-09-24.md`. Not a Gate B criterion.** It depends on
Story 5.9's conversation-derived trace ID (5.9 Decision 6) and reuses 5.9's export boundary.

**What exists today.** A paid live-suite run (`evals.live_conversations.suite`) writes a raw run
report (git-ignored, e.g. `_bmad-output/test-artifacts/live-matrix-5-7-final3.json`); the evidence
generator reads finished reports and writes `evidence/story-5.7/…`; the 5.8 drop check compares the
evidence with the committed baseline. With `LOGFIRE_TOKEN` set, Story 5.9 made the disposable stack's
API and worker export each conversation as **one trace whose ID is the conversation UUID**. Nothing
puts the *verdicts* anywhere near those traces, and nothing uses `pydantic-evals` (it appears only in
a forbidden-import list).

**What creation measured that nobody had written down.** A throwaway harness ran `logfire==5.1.0` and
`pydantic-evals==2.27.0` in an overlay env over the real Story 5.7 report (90 turns, run
`64ca2862-…`) against a local OTLP capture server and against unreachable, 401 and slow endpoints.
**Nothing reached the hosted Logfire project.** Ten facts changed the design:

1. **`pydantic-evals` must equal `pydantic-ai-slim` exactly** — `pydantic-evals 2.27.0` requires
   `pydantic-ai-slim==2.27.0` (latest is 2.49.0, which would move the agent runtime). `logfire 5.1.0`
   requires `opentelemetry-sdk>=1.39.0,<1.45.0`, so it accepts 5.9's 1.44.0 pin. Adding both to
   the dev group resolves **6 new packages and changes 0 versions** (Decision 2).
2. **Once `logfire` is installed, `logfire_api` IS `logfire`** (`logfire_api.Logfire is
   logfire.Logfire` → `True`). `pydantic_graph/_utils.py:20` builds a `logfire_api.Logfire` at import in
   every process that imports pydantic-ai. So the dev env now carries the real SDK into local API and
   test processes (Decision 2).
3. **…and it stays inert there.** Across 288 tests (agent runtime, conversations API, 5.9's
   end-to-end trace test, content minimization, all architecture guards) with `logfire` importable,
   the Logfire SDK recorded **0 spans, 0 logs, 0 `configure` calls**, never initialized, and set no
   global tracer provider or propagator. The agent graph passes `auto_instrument=False`
   (`pydantic_ai/_agent_graph.py:2480`), which is why (Decision 2).
4. **`logfire` registers two pytest plugins** (`logfire.testing` and
   `logfire._internal.integrations.pytest`). The second auto-enables when `CI` is truthy and
   `LOGFIRE_TOKEN` is set, and then configures with `scrubbing=False` and
   `send_to_logfire='if-token-present'`. Today conftest pops the token before `pytest_configure`, so
   it never fires; `-p no:logfire -p no:pytest_logfire` was measured to disable both, with or without
   `logfire` installed (Decision 2).
5. **The Logfire SDK's own exporter ships the operator's machine.** Its resource carried
   `host.name=ThunderPie`, `os.version`, the full `process.runtime.description`, `process.pid`,
   `service.version=<git HEAD>`. Every pydantic-evals span also carried the publisher's **absolute**
   `code.filepath` (the Windows username included). `AdvancedOptions(resource_detectors=[])` did
   **not** remove the host/OS keys. It also issued a `GET /v1/info` with the token, which reads from
   Logfire (Decision 3).
6. **Logfire's default scrubbing corrupts closed-vocabulary values.** It is a deny-list that matches
   substrings of values as well as keys: a recorded failure code `unauthorized_effect` was exported as
   `"[Scrubbed due to 'auth']"`. No code in today's vocabulary trips it, but `reporting.py`'s own
   comment names "a missing or unauthorized effect" as a category (Decision 3).
7. **The fix works with 5.9's boundary unchanged in kind.** With `send_to_logfire=False` Logfire is
   only the in-process provider. It hands every *final* span, and never a pending span, to
   `additional_span_processors`. Routing those through 5.9's real `SanitizingSpanExporter` → real
   `OTLPSpanExporter` produced one POST of 361 spans (90 verdict + 271 experiment) with the resource
   rebuilt to its allow-list, no `code.*`, no host name, and an unlisted canary key dropped
   (Decisions 3, 4).
8. **`logfire.force_flush()` returns `True` when nothing was delivered.** Unreachable endpoint →
   `True` (4.1 s); **401 → `True`** (0.06 s); slow endpoint → `False` (5.06 s). In all three, the
   recording wrapper saw the one batch return `FAILURE`. A publisher that trusts the flush result
   reports success on a rejected token (Decision 8).
9. **Verdict spans land where the AC wants them.** Created through the OpenTelemetry API inside
   `logfire.propagate.attach_context({'traceparent': …})`, each got `trace_id == conversation UUID`
   and `parent_span_id ==` the UUID's low 64 bits, which is exactly the parent 5.9's boundary
   synthesizes for the conversation's request spans. So they render as siblings of the turn's
   requests, at the turn's recorded `activity.occurred_at` (Decision 5).
10. **`logfire.configure()` sets the process-global tracer provider** (after it,
    `opentelemetry.trace.get_tracer_provider()` is `logfire._internal.tracer.ProxyTracerProvider`),
    and `settings.py` loads `backend/.env` with `override=False`. So a publisher launched from a test
    that does not set `LOGFIRE_TOKEN` itself would load **Minh's real token** and publish. Tests
    therefore run the publisher in a subprocess with both variables set explicitly (Decision 9).

**Scope summary.** Two exact dev-group pins; two pytest plugins disabled; one pure report→publication
planner; one CLI publisher that uses the Logfire SDK only as an in-process provider and exports
through 5.9's sanitizer, publishing each turn's user message, obligation, visible reply and judge
reasons as addendum §6's channel 2 (amended 2026-09-25), with verdict spans kept text-free; two new
policy categories (`live_eval`, `evals`) and a channel-2 resource tag; one stdlib module holding
the conversation trace-ID derivation both sides share; architecture guards; docs; ledger. **No live
run, no provider spend, no migration, no API/route/schema change, no change to the live report
schema, `configuration_digest`, the 5.8 drop check or baseline, no evidence regenerated, zero
frontend diff.**

**Depends on, and consumes:** Story 5.9's `SanitizingSpanExporter`, policy tables, trace-ID rule,
settings (`logfire_token`, `logfire_base_url`), capture helpers (`tests/trace_capture.py`) and failure
servers (`tests/test_trace_export_failure_independence.py::_server`); Story 5.7's run-report format,
`load_scenarios()` and final-attempt rule; Story 5.2's canaries.

**Unblocks:** nothing is waiting on this story; it is additive portfolio observability.

---

## Facts this story depends on — each one written down and citable

Retro action A3 requires this pass before decisions. None of these may be re-derived from code.

| Fact | Where it is written |
|---|---|
| **The ACs**, including "nothing is re-executed", "named by report identity and model", and "never read back from Logfire". | `epics.md:1610-1629` |
| **AD-12 (amended 2026-09-24):** "Every exported span passes an export-boundary sanitizer (attribute allow-list, exception type only) … No telemetry system authorizes or blocks product work." This sentence is why the publisher does not use the Logfire exporter (Decision 3). | `ARCHITECTURE-SPINE.md:162` (AD-12 rule, final sentences) |
| **Stack row:** "Logfire SDK + pydantic-evals — pinned at Story 5.10 — dev/eval tooling only; never imported by api, worker, agent, application or domain". | `ARCHITECTURE-SPINE.md:283` |
| **Addendum §2.1:** "ShiftMind exports with the standard OpenTelemetry SDK and its own export-boundary sanitizer rather than the Logfire SDK … the Logfire SDK and Pydantic Evals are used only by evaluation tooling to publish live-evaluation results as Logfire experiments." | `prds/prd-ShiftMind-2026-07-21/addendum.md:60` |
| **Addendum §6 (amended 2026-09-25):** content leaves only through "the two authorized live-evaluation channels, both carrying only conversations run on seeded synthetic fixtures and both tagged `deployment.environment=live-eval`". Channel 2 is this publisher, which "may export each turn's user message, authored obligation, visible reply and judge reasons from that report, nothing else from it". "Credentials and exception text are withheld in every mode and channel." The amendment's trigger and reasoning are in the proposal's *Amendment 2026-09-25* section. | `addendum.md:149`; `sprint-change-proposal-2026-09-24.md` (end) |
| **NFR3** (content excluded from external telemetry by default), **NFR4** (no secrets in traces), **NFR10** (Logfire failure causes zero product-state corruption), **NFR26** (CI deterministic-first, keyless), **NFR30** (minimum explicitly configured content). | `epics.md:79,81,93,125,133` |
| **AR27:** add and lock each planned dependency only at its implementation gate. This story is that gate for the Logfire SDK + pydantic-evals row. | `epics.md:173` |
| **Story 5.8 / sprint-status note for 5.10:** "must not touch the live report schema, `configuration_digest`, the 5.8 drop check, or any evidence." | `sprint-status.yaml` (the `5.9/5.10 added 2026-09-24` comment block) |
| **Story 5.9 Decision 6:** trace ID = conversation UUID; synthesized parent = low 64 bits `or 1`; derived from the path by `api/tracing.py::conversation_traceparent`. | `5-9-…md` Decision 6; `backend/api/tracing.py:36-50` |
| **Story 5.9 Decision 4:** the sanitizer is default-deny by instrumentation-scope category; an unknown scope exports with no attributes; the resource is rebuilt from `RESOURCE_ALLOW`; `deployment.environment=live-eval` is kept only in content mode. | `backend/adapters/telemetry/span_policy.py`, `spans.py:173-243` |
| **Story 5.7 final-attempt rule:** "A retried execution appears more than once; only its final attempt counts." | `backend/evals/live_conversations/reporting.py:54-56` |
| **Turn verdict vocabulary** is `pass`, `fail`, `incomplete`, `needs_review`. | `evals/live_conversations/protocol.py:151-159`; `runner.py:173` |
| **Agent-run status vocabulary** is the seven values of `ck_agent_run_status`. | `backend/adapters/postgres/schema.py:308` |
| **Scenario IDs** are the authored `A`, `B`, `C`, read through `load_scenarios()`. | `backend/evals/live_conversations/scenarios.json`; `cases.py` |
| **Evidence convention:** evidence is generated, never hand-typed; this story produces none. | `docs/EVIDENCE-CONVENTION.md` |
| **The runtime image is built `--no-dev`**, already guarded. | `Dockerfile:13`; `tests/architecture/test_local_composition.py:45` |
| **A demonstrated red comes from mutating already-green code**, recorded in a mutation table before review. | `epic-4-retro-2026-09-02.md` §4, §6 A1; `_bmad/custom/bmad-dev-story.toml` |
| **Domain model.** This story computes no metric, reads no demand row and adds no assignment field. It republishes numbers the suite already recorded (token counts, cost, judge scores); none is a demand or assignment quantity. Cited because the standing rule requires it. | `docs/DOMAIN-MODEL.md` §1–§3, §5 |

---

## Acceptance Criteria

Verbatim from `epics.md:1620-1629`. Frozen.

**AC1.**
**Given** a finished live-suite report (the Story 5.7 format) and `LOGFIRE_TOKEN`
**When** the publisher runs
**Then** one `live_eval.verdict` span per turn is written into that conversation's trace (trace ID
derived from `conversation_id`), carrying turn index, verdict, agent model, `configuration_digest`,
and report identity
**And** the report is replayed into a pydantic-evals `Dataset` — the task returns recorded output and
evaluators return recorded verdicts, nothing is re-executed — so the run appears on Logfire's
Experiments page named by report identity and model.

**AC2.**
**Given** Logfire is unavailable or the token is absent
**When** the publisher runs
**Then** it exits non-zero with a closed-vocabulary reason, and the report file, committed baseline,
Story 5.8 drop check, and all evidence remain untouched and are never read back from Logfire. (AD-12)

**Out of scope, deliberately.** Publishing from inside the suite run, rewriting the live suite on
pydantic-evals, Logfire live evaluations or LLM judges, and publishing deterministic golden-case
results. Also out: any report field beyond addendum §6's four text fields (Decision 6), the Story
5.7 *evidence* document as an input (Decision 6), hosted Logfire datasets, and a paid live run.

**Reading notes.** "The Story 5.7 format" is the **raw run report** that `suite.py --output`
writes (`schema_version: "1-development"`), not the evidence document. Only the run report carries
`conversation_id` and per-turn verdicts (Decision 6). "Report identity" is the report's `run_id`
**and** the sha256 of its bytes, the same pair the evidence generator binds as `source_runs`
(`evidence.py::_source_runs`). "Logfire is unavailable" covers unreachable, slow and rejecting
endpoints (Decision 8).

---

## Measured at creation — `3bf0fb1`, clean tree, Docker PostgreSQL 18 up

### Test baseline

| Suite | Measurement |
|---|---|
| Backend default (`uv run --frozen pytest -q`) | **2367 passed, 1 skipped, 10 deselected**, 404.7 s, the same as Story 5.9's close-out. The skip is `test_scheduling_inspect.py::…[tasks]` (by design) |
| `tests/test_settings.py` | **59 passed** |
| Agent/trace/architecture subset under the `logfire`+`pydantic-evals` overlay (fact 3) | **288 passed**, Logfire SDK calls: 0 |
| Frontend | Not re-measured: zero frontend diff. |

### How the measurement was taken

`uv run --frozen --with logfire==5.1.0 --with pydantic-evals==2.27.0` from `backend/`, the real
report `_bmad-output/test-artifacts/live-matrix-5-7-final3.json` (sha256 `c2e1433a…f2e8`, the one
`evidence/story-5.7/…` binds as its only source run), and a scratch HTTP server decoding every OTLP
body with `ExportTraceServiceRequest`. All `LOGFIRE_*`/`OTEL_*` variables were popped **after**
importing `adapters.telemetry.spans`, because that import loads `backend/.env`. Three pipelines were
compared:

* (a) Logfire SDK exporter (`send_to_logfire=True`, fake `pylf_v1_us_…` token, `base_url` = capture
  server): facts 5, 6, 9.
* (b) Logfire as provider only, an in-memory additional processor: fact 7 (what reaches a processor).
* (c) Logfire as provider only, additional processor = `BatchSpanProcessor(recording
  SanitizingSpanExporter(OTLPSpanExporter))` with two simulated policy categories, then the same
  pipeline against unreachable / 401 / slow (30 s sleep) servers: facts 7, 8.

A scratch pytest plugin counting `Logfire._span`, `Logfire.log` and `LogfireConfig.configure` gave
fact 3. The repository was not modified; `git status` was clean afterwards and no `.logfire/`
directory was created.

### What the experiment spans carry (pipeline (a), final spans; the allow-list source for Decision 4)

| Span name (scope `pydantic-evals`) | Keys observed |
|---|---|
| `evaluate {name}` | `name`, `task_name`, `dataset_name`, `n_cases`, `gen_ai.operation.name` (= `experiment`, what the Experiments page keys on), `metadata`, `assertion_pass_rate`, `logfire.experiment.metadata` (averages), `logfire.msg`, `logfire.msg_template`, `logfire.json_schema`, `logfire.span_type`, `code.filepath`, `code.lineno` |
| `case: {case_name}` | `task_name`, `case_name`, `inputs`, `metadata`, `expected_output`, `output`, `task_duration`, `metrics`, `attributes`, `assertions`, `scores`, `labels`, `logfire.*` as above, `code.filepath`, `code.lineno` |
| `execute {task}` | `task`, `logfire.*`, `code.*` |
| `evaluator: {evaluator_name}` | `evaluator_name`, `logfire.*`, `code.*` |
| *(pending spans; pipeline (a) only)* | the same plus `logfire.pending_parent_id`; never delivered to additional processors (fact 7) |

With the real report, the experiment's `assertion_pass_rate` was **0.9667 = 87/90**, the same total
as the committed 5.7 evidence's `turn_pass_rates`.

---

## Ten decisions were made at story creation — do not re-litigate them

Each states its mechanism **and what it does not cover**.

### Decision 1 — Where the code lives, and what each module may import

| Module | New/changed | May import | Holds |
|---|---|---|---|
| `backend/adapters/telemetry/conversation_trace.py` | new | stdlib only | `conversation_trace_ids(conversation_id: UUID) -> tuple[int, int]` (trace ID = `uuid.int`; parent = low 64 bits `or 1`) and `conversation_traceparent_header(conversation_id: UUID) -> str` (`00-{hex}-{parent:016x}-01`) |
| `backend/api/tracing.py` | changed | as today | `conversation_traceparent(path)` keeps its signature and behaviour and delegates the derivation to the new module |
| `backend/adapters/telemetry/span_policy.py` | changed | stdlib only | two categories and their validators (Decision 4) |
| `backend/adapters/telemetry/spans.py` | changed | as today | `build_live_eval_publication_export(...)` and the shared OTLP-exporter construction (Decision 8) |
| `backend/evals/live_conversations/publication.py` | new | stdlib, `evals.live_conversations.cases`, `evals.live_conversations.runner.visible_activity` (the judge's projection, reused, never copied; importing it loads pydantic-ai, measured 3.3 s, never `logfire`), `adapters.telemetry.conversation_trace`, `adapters.telemetry.span_policy` (stdlib; its vocabularies and validators, so the planner and the sanitizer share one copy) | the pure report→`PublicationPlan` planner and its refusal reasons (Decisions 6, 7). **No** `logfire`, `pydantic_evals` or `opentelemetry` import |
| `backend/evals/live_conversations/logfire_publish.py` | new | `logfire`, `pydantic_evals`, `opentelemetry.trace` (**API facade only**), `settings`, `adapters.telemetry.spans`, `publication` | the CLI: settings → token → plan → configure → verdict spans → experiment → bounded finish → exit code (Decisions 3, 5, 8, 9) |

Guards (Task 7), each with synthetic violating source:

* **Logfire/pydantic-evals in one file.** `logfire` and `pydantic_evals` are imported by
  `evals/live_conversations/logfire_publish.py` and by no other module under `NON_TEST_BACKEND_ROOTS`
  or the backend-root modules. This is stricter than 5.9's `LOGFIRE_BANNED_ROOTS`, which left all of
  `evals/` and `scripts/` open "for Story 5.10". Keep 5.9's test and add the new one.
* **Facade exemption.** `FACADE_ALLOWED` in `test_trace_export_boundaries.py` gains
  `evals/live_conversations/logfire_publish.py` with its reason (verdict spans need an explicit
  `start_time`, which only the OpenTelemetry `Tracer.start_span` API takes; Logfire's `span()` does
  not). `SDK_ALLOWED` does **not** change, so that file importing `opentelemetry.sdk|exporter|
  instrumentation` stays red.
* **Dependencies.** `dependency_pin_violations` also rejects `pydantic-evals` as a runtime dependency,
  and a new check requires the dev group to pin `logfire==5.1.0` and `pydantic-evals==2.27.0`
  exactly.

**What this does not cover.** The guards are AST walks over this repository. Logfire's code reached
transitively through `logfire_api` (fact 2) is invisible to them; its inertness is a measured
property (fact 3), kept by pydantic-ai's `auto_instrument=False`, not by a guard. AD-1's
`FORBIDDEN_ROOT_MODULES` lists `logfire` but not `pydantic_evals`. It is not widened: for
`domain/` and `application/`, the one-file rule already forbids both.

### Decision 2 — Dependencies: dev group only, exact pins, plugins off

`[dependency-groups].dev` gains `logfire==5.1.0` and `pydantic-evals==2.27.0`, each with an
AR27-style comment: why dev-only (Stack row; the image is `--no-dev`), why `pydantic-evals` equals
`pydantic-ai-slim` (fact 1), and that `logfire 5.x` caps `opentelemetry-sdk<1.45`, so the next OTel
bump moves this pin too. Not `logfire 6.0.0b*` (pre-release). Measured delta: `executing 2.2.1`,
`logfire 5.1.0`, `markdown-it-py 4.2.0`, `mdurl 0.1.2`, `pydantic-evals 2.27.0`, `rich 15.0.0`
added; nothing changed or removed; `logfire-api` stays `4.40.0` and is delegated to (fact 2).

`[tool.pytest.ini_options].addopts` becomes `-m "not live" -p no:logfire -p no:pytest_logfire`
(fact 4), so the suite stays keyless by construction even if `CI` and a token were ever both
present. A test asserts neither plugin is registered in the test process.

`Dockerfile`'s `uv sync … --no-dev` comment is stale (it still says the dev group "carries
`opentelemetry-sdk`", which 5.9 moved to runtime). Rewrite it to say what `--no-dev` now keeps out of
the image: pytest, pyyaml, and **the Logfire SDK and pydantic-evals**, whose presence would turn
`logfire_api` into the real SDK inside the runtime (fact 2). The existing
`test_container_builds_use_frozen_dependency_paths` already pins the flag; no new guard.

**What this does not cover.** Local dev processes (`uv run uvicorn …`, `uv run pytest`) now import
the real Logfire SDK through `logfire_api`. It is inert unless something calls it (fact 3). One path
that could call it is Logfire's own pydantic plugin (`pydantic` entry point
`logfire.integrations.pydantic:plugin`), which records only when configured or when
`LOGFIRE_PYDANTIC_PLUGIN_RECORD` is set by hand. An unconfigured Logfire instance would then
lazily configure itself from `LOGFIRE_TOKEN` and export through the Logfire SDK, **bypassing the
sanitizer**. That requires a hand-set Logfire variable on a local dev process; the image cannot
reach it. State it in `docs/CONFIGURATION.md` and the ledger.

### Decision 3 — The publisher exports only through 5.9's sanitizer; Logfire is the in-process provider

`logfire_publish.py` calls, exactly:

```python
logfire.configure(
    send_to_logfire=False,          # fact 5: no Logfire exporter, no GET /v1/info read-back
    additional_span_processors=[export.processor],  # Decision 8: 5.9's sanitizer -> OTLP
    service_name="shiftmind-live-eval-publisher",
    service_version=APP_VERSION,    # not Logfire's git-HEAD default
    console=False, metrics=False, inspect_arguments=False,
    scrubbing=False,                # fact 6: the allow-list is the control; see below
    distributed_tracing=True,       # the one deliberate extraction (Decision 5)
    add_baggage_to_attributes=False,
)
```

Why each non-obvious argument:

* `send_to_logfire=False`: AD-12 says every exported span passes the sanitizer. Logfire's exporter
  would ship fact 5's resource and `code.filepath`, and its deny-list scrubbing is not an allow-list.
* `scrubbing=False`: every *structured* string the publisher emits is a validated identifier, a
  closed-vocabulary member, a digest or a UUID (Decision 6), and the sanitizer re-validates the
  verdict span's keys (Decision 4). The four text fields addendum §6 authorizes are synthetic
  conversation text, and a deny-list would mangle it without protecting anything: any sentence
  containing "session" or "author" would be rewritten. Credentials are handled by an exact-value
  check instead (Decision 6). The 5.9 runtime path does not scrub either.
* The publisher's sanitizer runs with the **agent** content mode **`off`, hard-coded**
  (`span_policy.CONTENT_MODE_OFF`), whatever `AGENT_TRACE_CONTENT_MODE` says in the publisher's shell.
  That mode governs only the `agent` category's content keys, and the publisher emits no agent
  spans. Its resource is tagged `deployment.environment=live-eval` through Decision 4's
  channel-2 flag, because under 5.9's rule that tag marks content-bearing traces, and the
  publisher's now carry content.

**What this does not cover.** `logfire.configure()` sets the process-global tracer provider
(fact 10). That is acceptable in the publisher's own short-lived process and is why every test that
configures Logfire runs it in a subprocess (Decision 9). Values of the allow-listed free-form
experiment keys (`inputs`, `output`, `metadata`, `scores`, `labels`, `metrics`, `assertions`,
`logfire.experiment.metadata`) are bounded by the planner's construction (Decision 6), not by the
sanitizer. This is 5.9 Decision 4's residual, restated for these keys. Since the amendment, that
construction includes free text, so the planner is the only thing standing between a report field
and Logfire. That is why Decision 6's field list is exhaustive and each excluded field has a
canary proof.

### Decision 4 — Two new policy categories, default-deny like the rest

`span_policy.py` gains two categories, keyed by instrumentation scope. Nothing in the API or worker
emits these scopes, so every existing category's behaviour is unchanged (5.9's suites stay green
unmodified).

**`LIVE_EVAL = "live_eval"`, scope `shiftmind.live_eval`** (constant `LIVE_EVAL_SCOPE`, used by the
publisher's tracer):

| Key | Validator |
|---|---|
| `shiftmind.live_eval.turn_index`, `.repetition`, `.attempt` | positive `int` (not `bool`) |
| `shiftmind.live_eval.final_attempt` | `bool` only (new `_flag`) |
| `shiftmind.live_eval.verdict` | closed: `pass`, `fail`, `incomplete`, `needs_review` |
| `shiftmind.live_eval.agent_run_status` | closed: the seven `ck_agent_run_status` values |
| `shiftmind.live_eval.factual_failures` | a non-empty sequence of codes, each `^[a-z][a-z0-9_]{0,63}$`; any bad element drops the whole key |
| `shiftmind.live_eval.scenario` | `^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$` |
| `shiftmind.live_eval.agent_model` | `^[a-z0-9][a-z0-9_-]*:[A-Za-z0-9._/:-]{1,128}$` |
| `shiftmind.live_eval.configuration_digest`, `.report.sha256` | 64 lowercase hex |
| `shiftmind.live_eval.report.run_id`, `shiftmind.conversation.id`, `shiftmind.agent_run.id` | UUID |
| `logfire.msg`, `logfire.span_type` | allow (Logfire adds them; measured `live_eval.verdict` / `span`) |

**`EVALS = "evals"`, scope `pydantic-evals`:** allow exactly the measured non-`code` keys in the table
above (`name`, `task_name`, `dataset_name`, `n_cases`, `gen_ai.operation.name`, `metadata`,
`assertion_pass_rate`, `logfire.experiment.metadata`, `case_name`, `inputs`, `expected_output`,
`output`, `task_duration`, `metrics`, `attributes`, `assertions`, `scores`, `labels`,
`evaluator_name`, `task`, `logfire.msg`, `logfire.msg_template`, `logfire.json_schema`,
`logfire.span_type`); `KNOWN_DROPPED = {code.filepath, code.lineno}`. `logfire.pending_parent_id` is
not listed: pending spans never reach the processor (fact 7).

The validators are pure stdlib functions beside 5.9's `_uuid`/`_number`/`_closed`. The
closed-vocabulary constants live in `span_policy.py`; a test pins them to their sources
(`protocol.turn_verdict`'s outcomes plus `runner.py`'s `incomplete`; `schema.py`'s check
constraint), as 5.9 pinned `SCHEDULE_RUN_STATUSES`.

**Verdict spans stay text-free.** The `live_eval` table has no text key. Addendum §6's text fields
travel only in the experiment's `inputs`, `output` and evaluator reasons (`evals` category).

**The channel-2 resource tag.** `sanitize_resource` gains a keyword `live_eval_channel: bool = False`.
When it is `True`, the rebuilt resource gets `deployment.environment=live-eval` whatever the raw
resource carried. When it is `False`, behaviour is exactly 5.9's: the tag appears only in content
mode and only if the raw resource already carries it. `SanitizingSpanExporter` gains the same
keyword and passes it through; `build_process_tracing` never sets it, so the API and worker are
unchanged. Do **not** pass `environment=` to `logfire.configure`: it produces
`deployment.environment.name`, which `RESOURCE_ALLOW` drops. The tag comes from the sanitizer alone.

**What this does not cover.** Span **names** still pass through: `case: {case_name}` spans are named
by the template, while `logfire.msg` carries `case: A:1:rep1`, bounded by the planner. The `evals`
category bounds keys only (Decision 3's residual). Adding the categories changes the sha256 that
`evidence/story-5.2/content-minimization-report.json` records for `span_policy.py` and `spans.py`.
Those digests are never re-verified (the existing ledger entry after `deferred-work.md:696`). The
C4–C8 verdicts still describe the runtime, because no runtime scope maps to the new categories.
Record it in that entry; do not regenerate the evidence (Decision 10).

### Decision 5 — Verdict spans: the conversation's trace, the synthesized parent, the turn's time

For **every execution attempt** in the report that has a `conversation_id`, and every turn row in it,
the publisher writes one span:

* **name** `live_eval.verdict`; **tracer** `opentelemetry.trace.get_tracer(LIVE_EVAL_SCOPE)` (the
  global provider is Logfire's after `configure`, fact 10); **kind** INTERNAL;
* **context** `with logfire.propagate.attach_context({"traceparent":
  conversation_traceparent_header(conversation_id)}):`. This is the same trace ID and parent as 5.9's
  boundary (fact 9). A test asserts the header equals `api.tracing.conversation_traceparent(
  f"/api/v1/conversations/{id}/messages")` for UUIDs including one whose low 64 bits are zero;
* **time** `start_time = end_time = ` the turn's `activity.occurred_at` in ns; for a turn with no
  activity (it stopped before a reply), the report's `finished_unix`. Zero duration;
* **attributes** exactly the `live_eval` table's keys: `turn_index` (1-based, the row's `turn-N`),
  `verdict`, `agent_model` (report `model`), `configuration_digest` (report
  `configuration.configuration_digest`), `report.run_id`, `report.sha256` (AC1's four named fields
  plus identity), and the join keys `shiftmind.conversation.id`, `shiftmind.agent_run.id` (when
  recorded), `scenario`, `repetition`, `attempt`, `final_attempt`, `agent_run_status` (when recorded),
  and `factual_failures` (only when non-empty).

The joins this makes: a verdict opens its conversation's trace, which since 5.9 holds that turn's
request, agent, model, tool and database spans. `shiftmind.agent_run.id` is the same key 5.9 stamps on
`invoke_agent`.

**What this does not cover.** A report measured **before** Story 5.9, or without `LOGFIRE_TOKEN`
during the suite run (today's only real report, `64ca2862-…`, is both), has no exported conversation
spans. Its verdict spans are the only spans in their traces. A report older than the Logfire
project's retention may publish invisibly, because the spans are backdated to when the turn ran. The
approval-resume half of Scenario B's approval turn lives in the approval request's trace (5.9
Decision 6); its verdict joins it through `shiftmind.agent_run.id`, not the trace ID.

### Decision 6 — What the planner reads from the report, and the content rule

`publication.plan_publication(report_bytes: bytes, *, credential_values: frozenset[str] =
frozenset()) -> PublicationPlan` is pure: bytes and the credential values in, a frozen plan or a
`PublicationRefused(reason)` out. The CLI collects `credential_values`; tests pass canaries. It computes `report_sha256` over the bytes it was given
(the CLI reads the file once, read-only).

**The content rule (addendum §6, channel 2):** the plan is built **only** from the fields listed
below, after validation. Four of them are text, exactly the four the addendum names:
* the turn's `user` message;
* its authored `obligation`;
* its **visible reply**: `evals.live_conversations.runner.visible_activity(activity)`, imported and
  never re-implemented, so the reply is exactly what the judge saw. Measured shapes: prose and claim
  segments, draft/approval summaries, clarifications, terminal outcomes;
* the judge's `judgment.<dim>.reason` strings.

Every other report field is never read into the plan. That includes `verified` (the judge's fact
payload, which carries candidate assignments), `tool_observations`, `command_observations`,
`fixture_setup`, `usage.correlation` (it holds `actor_id`, a person identifier), `judge_usage`,
`judge_unknown_citations`, `incomplete_reason`/`judge_unavailable_reason` strings, the raw `activity`
object beyond `visible_activity`'s projection, and the report's `code`/`images` blocks beyond
`code.git_commit`. So tool arguments/results and schedule payloads cannot leave, and the only
completions that leave are the visible replies the addendum names.

**Two checks on the text** (both refuse the whole report, so a partial publication never happens):
* **Size:** one case's four text fields together must serialize to at most **16 KiB** (measured
  maximum today 3 KB, median 1.2 KB) → else `report_malformed`.
* **Credentials, by exact value (addendum §6: "withheld in every mode and channel"):** after
  settings load, the publisher collects the non-empty values of
  `evals.content_minimization_report.CREDENTIAL_ENV_VARS` (the nine 5.2/5.9 credential variables)
  plus `LIVE_CONVERSATION_JUDGE_API_KEY` from its own environment. If any value of 8 or more
  characters occurs anywhere in the plan's text, it refuses with **`report_contains_credential`**
  and prints no value. The run report never records a key by construction (the suite passes keys to
  the stack only), so this is defence in depth against a model echoing a key it was shown.

| Read | Rule, refusal on failure |
|---|---|
| file bytes | not UTF-8 JSON object → `report_unreadable` |
| `schema_version` | must be `"1-development"` → else `report_schema_unsupported` |
| `finished_unix` | must be an `int`: `suite.py` writes it in its `finally` → else `report_unfinished` |
| `run_id`; `model`, `judge_model`; `configuration.configuration_digest`; `configuration.reasoning_effort`; `code.git_commit`; `started_unix` | UUID; model-ID shape (Decision 4); 64-hex; `none\|low\|medium\|high`; 40-hex; `int` → else `report_malformed` |
| `configuration.behavioral_digest` | optional (reports before 5.8 lack it); 64-hex when present |
| each `prefixes[]`: `scenario`, `repetition`, `attempt`, `conversation_id`, `turns` | scenario ∈ `load_scenarios()` IDs; positive ints; UUID (may be absent only when `turns` is empty, i.e. fixture setup failed); list |
| `conversation_id` across executions | unique (`reporting.py` requires the same) → else `report_malformed` |
| each turn: `id`, `verdict`, `agent_run_id`, `agent_run_status`, `factual_failures`, `activity.occurred_at`, `judgment.<dim>.score`, `usage.usage.{input_tokens,output_tokens,requests,tool_calls}`, `usage.estimated_cost_usd`, `usage.usage_unavailable` | `id == f"turn-{index}"`; verdict closed; UUID if present; status closed if present; list of codes; ISO-8601 if present; score ∈ {0, 1, 2, null} for `relevance`, `continuity`, `completeness`, `clarification_refusal`; non-negative numbers if present |
| each turn's text: `user`, `obligation`, `activity` (only through `visible_activity`), `judgment.<dim>.reason` | `user`/`obligation` strings; `activity` a dict when present (absent → reply `null`); reasons strings or null; the size and credential checks above |

**Final attempts:** the experiment covers, per `(repetition, scenario)`, the **last** execution in
list order, which is `reporting.py:56`'s rule. Verdict spans cover every attempt (each attempt is a
separate conversation with its own trace); `final_attempt` marks which one counts.

**What this does not cover.** The evidence document cannot be published: it carries no
conversation IDs. A report `--resume`d from another copies that report's passed executions, so
publishing both writes two verdict spans into those traces. They are told apart by
`report.run_id`. A syntactically valid report whose values are wrong (a hand-edited verdict) is
published as recorded. The publisher mirrors the report and does not audit it; the evidence chain
does that. The credential check knows only the credentials configured on the publishing machine; a
key that exists only on another machine is invisible to it. Nothing checks that a report's
conversations really ran on seeded fixtures: the addendum's premise is that the live suite only
ever runs on them (`fixtures.py::prepare_initial_baseline`), and the publisher accepts only the
suite's `schema_version`.

### Decision 7 — The experiment: recorded, never re-executed, comparable across runs

* `Dataset(name="live-conversations", cases=…, evaluators=[RecordedVerdict(),
  RecordedJudgeScores(), RecordedOutcome()])`. The constant dataset name groups every run, which is
  what Logfire's "compare against a baseline run" uses (Logfire docs via Context7, 2026-09-24:
  "group runs by dataset … choose a baseline run").
* One `Case` per final-attempt turn: `name = f"{scenario}:{turn}:rep{repetition}"`, stable across
  reports, so the same turn lines up side by side. `inputs = {"scenario", "turn", "repetition",
  "user", "obligation"}`; `metadata = {"conversation_id", "agent_run_id", "trace_id"}` (`trace_id` =
  the 32-hex conversation trace, so a reader can open the trace from the case); `expected_output =
  None`.
* The task is `async def recorded_live_turn(inputs)`. It returns the plan's recorded output for that
  case, `{"reply", "verdict", "agent_run_status", "factual_failures", "judge_scores"}` (`reply` = the
  `visible_activity` projection, or `null`), and when usage was
  recorded it calls `increment_eval_metric` for `input_tokens`, `output_tokens`, `requests`,
  `tool_calls` and `estimated_cost_usd`. It never calls a model, the API, the judge or the fixture.
  The function is named `recorded_live_turn` because the case span's `task_name` is the function's
  name (measured).
* Evaluators read only `ctx.output`: `RecordedVerdict` → `bool` (`verdict == "pass"`),
  `RecordedJudgeScores` → per non-null dimension an `EvaluationReason(value=score, reason=<the
  judge's recorded reason>)`, so the Experiments page shows the judge's reasoning beside each score;
  `RecordedOutcome` → labels `verdict` and `agent_run_status`. Each is a `@dataclass` `Evaluator`
  subclass.
* `dataset.evaluate_sync(recorded_live_turn, name=f"{model} {run_id}",
  task_name="recorded_live_turn", metadata={report_run_id, report_sha256, agent_model, judge_model,
  configuration_digest, behavioral_digest (when present), reasoning_effort, code_commit,
  started_unix, finished_unix}, progress=False)`.

**What this does not cover.** `needs_review` and `incomplete` count as failed assertions, and the
label keeps them distinguishable. The experiment's `assertion_pass_rate` equals the evidence's
per-turn totals only for a report whose repetitions were all complete, because `summarize_runs`
counts complete repetitions only. It is review data, never a gate (AD-12). The case's own trace (the
page's "Open trace") holds only the replay spans, never the agent run, because nothing is
re-executed. The agent run is in the conversation trace named by `metadata.trace_id`.

### Decision 8 — Delivery is proven by recorded export results, never by `force_flush`

`spans.build_live_eval_publication_export(settings, *, session=None) -> LiveEvalPublicationExport |
None`:

* returns `None` when `settings.logfire_token` is falsy, and constructs nothing;
* builds the `OTLPSpanExporter` **exactly** as `build_process_tracing` does (endpoint
  `{base}/v1/traces`, `Authorization` header, 5 s timeout, gzip, `certificate_file=True`, explicit
  `requests.Session`). Extract that construction into one private helper both call, so the two can
  never diverge (5.9 review finding: env must not choose session or CA);
* wraps it as `SanitizingSpanExporter(exporter, content_mode=span_policy.CONTENT_MODE_OFF)`, then a
  recording wrapper that counts spans in `SUCCESS` batches and batches that returned anything else;
* feeds a `BatchSpanProcessor` with explicit bounds (`max_queue_size=16384`, batch 512, 5 s export
  timeout) whose `on_end` also counts spans ended;
* `.processor` is what the publisher passes to Logfire; `.finish() -> PublicationDelivery` runs
  force-flush + shutdown on a daemon thread joined with a hard deadline (5.9's `ProcessTracing.shutdown`
  pattern: SDK 1.44's `force_flush` ignores its timeout) and returns `ended`, `accepted`,
  `failed_batches`, `within_deadline`.

**Delivered** ⇔ `within_deadline and failed_batches == 0 and accepted == ended and ended > 0`.
Anything else → exit **1**, reason `logfire_export_failed`. The failure paths measured at fact 8
(unreachable, 401, slow) each end in 5–10 s wall clock.

**What this does not cover.** A partial delivery (an early batch accepted, a later one refused)
cannot be retracted. Logfire then holds a partial experiment, and the exit code says the
publication failed. Re-running publishes again: there is no idempotency key, and the publisher never
reads Logfire to find an earlier publication (AC2). Publishing a report twice duplicates its verdict
spans and creates a second experiment of the same name. `docs/TESTING.md` says to publish each
report once.

### Decision 9 — Order of operations, exit codes, and a keyless, read-nothing-back process

`main(argv)`: `publish_live_eval <report.json>`

1. `settings.default_settings()`; `InvalidFlagError` → refuse `configuration_invalid`.
2. `settings.logfire_token` absent → refuse `logfire_token_absent`. Nothing is read, constructed or
   sent.
3. Read the report bytes once, then `plan_publication` → refuse with its reason.
4. Build the export (Decision 8), `logfire.configure` (Decision 3), write the verdict spans
   (Decision 5), run the experiment (Decision 7), `export.finish()`.
5. Print **one** JSON line to stdout: `{"outcome": "published"|"refused"|"failed", "reason":
   <code|null>, "report_run_id", "report_sha256", "experiment", "verdict_spans", "cases",
   "spans_exported"}` (identifiers `null` when not yet known). Never the token, the base URL's
   credentials, or a report value outside the plan.

Exit codes: **0** published; **1** `logfire_export_failed`; **2** any refusal. `PUBLISH_REASONS` is a
module constant, the closed vocabulary: `configuration_invalid`, `logfire_token_absent`,
`report_unreadable`, `report_schema_unsupported`, `report_unfinished`, `report_malformed`,
`report_contains_credential`, `logfire_export_failed`. A test pins that every reason the code can
emit is in it.

**Never read back:** the only network call the publisher makes is `POST {base}/v1/traces`. A test
asserts the capture server saw nothing else. That fails if `send_to_logfire=True` sneaks back in
(its `GET /v1/info`, fact 5). The report is opened read-only. The publisher does not import or open
the baseline, the drop check or `evidence/`. A test compares sha256 of the report, the baseline and
every tracked `evidence/**` file before and after a successful and a failed publication.

**Test-process trap (fact 10).** Every subprocess the tests launch gets an environment built by one
helper that **always** sets `LOGFIRE_TOKEN` (a canary, or `""` for the absent case) and
`LOGFIRE_BASE_URL` (a local port), so `load_dotenv(override=False)` can never supply Minh's real
token. A test asserts the helper sets both. Never call `logfire.configure` in the pytest process.

**What this does not cover.** A token set by hand in the operator's shell wins over `backend/.env`,
exactly as for the suite. The publisher cannot tell a wrong-project token from a right one; Logfire
accepts either.

### Decision 10 — Evidence, Gate A, spend, and the one real check

* **No evidence is produced or regenerated.** The publisher is not an evaluation report under NFR27.
  It republishes one, so there is no commit → measure → generate cycle. The registered Gate A files
  (`test_content_minimization_report.py`, `evidence/story-5.2/…`) are not touched, so the readiness
  report is not regenerated. The 5.2 artifact-digest drift is ledgered (Decision 4).
* **No paid run.** Every test uses a synthetic report. The real report at
  `_bmad-output/test-artifacts/live-matrix-5-7-final3.json` is git-ignored and used only by Task 11.
* **Task 11 is the one hosted-Logfire write.** It publishes to Minh's project and **asks Minh first**.

**What this does not cover.** Nothing proves the Experiments page renders the experiment except
Task 11's observation, which is not evidence.

---

## Tasks / Subtasks

- [x] **Task 1 — Start from a clean, re-verified baseline (all ACs)**
  - [x] Create `story/5-10-publish-live-evaluation-results-to-logfire` from `main` (5.9's branch
        naming). Commit the planning edits first if they are still uncommitted, as
        `docs(story-5.10): …`: this story file, its `sprint-status.yaml` row, the addendum §6
        amendment and the proposal's *Amendment 2026-09-25* section.
  - [x] Re-run *Measured at creation*'s suites and record drift. Re-confirm facts 1 and 8 (`uv lock`
        delta; `force_flush` returning `True` on 401) before relying on them.

- [x] **Task 2 — Dependencies and test-process plugins (AC1) — per Decision 2**
  - [x] `pyproject.toml` dev group + `addopts`; `uv lock` (confirm 6 added / 0 changed);
        `uv sync --frozen`. `Dockerfile` comment.
  - [x] Test: neither Logfire pytest plugin is registered in the test process.

- [x] **Task 3 — Shared trace-ID derivation (AC1) — per Decisions 1, 5**
  - [x] `adapters/telemetry/conversation_trace.py`; `api/tracing.py` delegates. 5.9's
        `conversation_traceparent` tests stay green unmodified. Add the parity test, including a UUID
        whose low 64 bits are zero.

- [x] **Task 4 — Policy categories (AC1) — per Decision 4**
  - [x] Constants, validators, the two `CategoryPolicy` entries, `SCOPE_CATEGORIES` entries, and
        the `live_eval_channel` keyword on `sanitize_resource` and `SanitizingSpanExporter`.
  - [x] Unit tests in `tests/test_trace_export_boundary.py` from the measured samples: each validator
        (accept + reject, including a canary string in every string-valued `live_eval` key), the
        vocabulary pins, the resource tag both ways, and the drift check (`unclassified_keys`) run on
        keys observed from a real `Dataset.evaluate` span (captured by Task 8's subprocess, not
        hand-typed).

- [x] **Task 5 — Export builder (AC1, AC2) — per Decision 8**
  - [x] `build_live_eval_publication_export` and the shared exporter helper in `spans.py`. 5.9's
        exporter-construction tests stay green unmodified.

- [x] **Task 6 — Planner and publisher (AC1, AC2) — per Decisions 5–9**
  - [x] `evals/live_conversations/publication.py` (pure) and `logfire_publish.py` (CLI,
        `python -m evals.live_conversations.logfire_publish`).

- [x] **Task 7 — Architecture guards (AC1) — per Decisions 1, 2**
  - [x] In `tests/architecture/test_trace_export_boundaries.py`: the one-file Logfire/pydantic-evals
        rule, the facade exemption, the dev-group pins, each with synthetic violating source.

- [x] **Task 8 — Proof suite (AC1, AC2) — per Decisions 3, 5–9**
  - [x] New `tests/test_live_eval_publication.py`. Reuse `tests/trace_capture.py`'s OTLP decoding
        and `test_trace_export_failure_independence.py::_server`, moving the latter into
        `trace_capture.py` rather than copying it. The minimum proofs are in *Dev Notes → Proof
        suite minimum*.

- [x] **Task 9 — Docs (AC1, AC2) — per Decisions 2, 6, 8, 9**
  - [x] `docs/TESTING.md`: a "Publish a finished live run to Logfire (Story 5.10)" subsection after
        5.9's trace-export one: the command, the raw-report input (not the evidence), exit codes and
        reasons, publish once, what is published (the four text fields of addendum §6 channel 2,
        tagged `live-eval`) and what never is, and where the new tests live.
  - [x] `docs/CONFIGURATION.md`: the `LOGFIRE_TOKEN` row also names the publisher; Decision 2's
        pydantic-plugin residual.
  - [x] Spine Stack row `pinned at Story 5.10` → the two exact versions.

- [x] **Task 10 — Ledger, status, mutation table — per Decisions 2, 4, 8 and retro A1**
  - [x] `deferred-work.md`: new entries for Decision 2's local-dev residual and Decision 8's
        duplicate-on-republish. Append Decision 4's digest note to the existing
        artifact-digest entry. This story's `sprint-status.yaml` row only.
  - [x] Demonstrated-red mutation table (*Dev Notes → Mutation table minimum*), recorded before
        review.

- [ ] **Task 11 — One real publication, at the end, with Minh's go-ahead (AC1)**
  - [ ] Ask Minh before publishing. Then, with the token in `backend/.env`, publish
        `_bmad-output/test-artifacts/live-matrix-5-7-final3.json` once. Confirm in Logfire (MCP SQL
        on `records` is enough): 90 `live_eval.verdict` spans, each `trace_id` equal to its
        conversation UUID hex; the experiment `openrouter:openai/gpt-5.6-luna 64ca2862-…` under
        dataset `live-conversations` on the Experiments page, where an opened case shows the user
        message, the visible reply and the judge's reason per score; every publisher span's resource
        tagged `deployment.environment=live-eval`; no `host.name`, no `code.filepath`, and no
        `verified`/tool-observation content anywhere. Record the observations in the Dev Agent
        Record; they are not evidence.

---

## Dev Notes

### Traps — the quietest first

1. **`logfire.force_flush()` says `True` when a 401 dropped everything** (fact 8). Exit status comes
   from `LiveEvalPublicationExport.finish()`, never from a flush or shutdown return value.
2. **A test subprocess without `LOGFIRE_TOKEN` in its env loads the real one** from `backend/.env`
   (`override=False`, fact 10). Always build the env through the one helper.
3. **Never `logfire.configure()` in the pytest process.** It sets the global tracer provider, which
   5.9's suites (and Story 5.1's failing-exporter test) assume nobody sets.
4. **`send_to_logfire=True` "just works" and leaks the machine** (fact 5). The proof that it is off
   is the capture server seeing only `POST /v1/traces` and a resource whose keys are exactly
   `RESOURCE_ALLOW ∪ {deployment.environment}`.
5. **`resource_detectors=[]` does not strip the resource** (measured). The sanitizer's rebuild does.
6. **Logfire scrubbing would silently rewrite a verdict code** (fact 6), so the fix is not "leave
   scrubbing on for safety".
7. **`pydantic-evals` cannot be bumped alone.** It pins `pydantic-ai-slim` exactly, and `uv lock`
   fails.
8. **The evidence document is not the input** (Decision 6). It has no `conversation_id`.
9. **The case span's `task_name` is the function name.** Name the task `recorded_live_turn`.
10. **Pending spans never reach an additional processor.** Do not allow-list
    `logfire.pending_parent_id` "for completeness"; the drift check would never observe it.
11. **Never write the Windows-CRLF way** (`Path.write_text`) over tracked LF files; edit with the Edit
    tool or `write_bytes`.
12. **Never paste the token anywhere.** Tests use the 5.9 canary style (`CANARY-LOGFIRE-5-10`).
13. **The planner's field list is the whole boundary for text** (Decision 3's residual). The `evals`
    category allows `inputs`/`output` whatever they hold, so reading one more report field
    "for context" publishes it. Add a field only through an addendum §6 change.

### Files being modified — read these before editing

| File | What it does today | What changes | What must be preserved |
|---|---|---|---|
| `backend/pyproject.toml` | runtime OTel pins; dev `pytest`, `pyyaml`; `addopts = -m "not live"` | Decision 2 | every existing pin and comment |
| `backend/uv.lock` | locked | +6 packages, 0 changed | everything else byte-identical in versions |
| `Dockerfile` | `--no-dev` sync with a stale comment | comment only | the command line verbatim (guarded) |
| `backend/api/tracing.py` | derives the conversation traceparent inline | delegates to `conversation_trace.py` | `conversation_traceparent(path)`'s signature and output; `TraceContextBoundary`; everything else |
| `backend/adapters/telemetry/span_policy.py` | six categories; `sanitize_resource(…, content_mode, content_mode_on)` | two more categories, validators; `sanitize_resource` gains `live_eval_channel=False` (Decision 4) | every existing table, validator and function signature |
| `backend/adapters/telemetry/spans.py` | `build_process_tracing` builds its exporter inline | shared exporter helper; publication builder; `SanitizingSpanExporter` gains `live_eval_channel=False` | `build_process_tracing`'s behaviour, the no-global-provider rule, bounded shutdown |
| `backend/tests/architecture/test_trace_export_boundaries.py` | 5.9's four rules | Decision 1's guards | every existing rule and synthetic case |
| `backend/tests/test_trace_export_boundary.py` | 5.9 policy units | Task 4 units | every existing test unmodified |
| `backend/tests/trace_capture.py`, `backend/tests/test_trace_export_failure_independence.py` | capture decoding; `_server` fixture servers | `_server` moves to `trace_capture.py` and is imported back | every 5.9 test's behaviour |
| `docs/TESTING.md`, `docs/CONFIGURATION.md`, spine Stack row, `deferred-work.md`, `sprint-status.yaml` | — | Tasks 9–10 | 5.9's text |

**Not modified, by rule:** `evals/live_conversations/{suite,runner,reporting,evidence,configuration}.py`,
`compose.override.yml`, `scripts/live_conversation_drop_check.py`,
`scripts/derive_live_conversation_baseline.py`, `evals/baselines/live-conversations.json`,
`evidence/**`, `backend/tests/test_content_minimization*.py`, `backend/conftest.py` (5.9's pops
already cover the publisher's variables).

New files: `backend/adapters/telemetry/conversation_trace.py`,
`backend/evals/live_conversations/publication.py`,
`backend/evals/live_conversations/logfire_publish.py`, `backend/tests/test_live_eval_publication.py`.

### Proof suite minimum (Task 8)

A synthetic report builder in the test module produces a small valid report: two scenarios, one
repetition with a retried (non-final) attempt, a turn with no activity, a `needs_review` turn and a
turn with `factual_failures`. Two kinds of canary go in:
* **Excluded fields** (`verified`, `tool_observations`, `command_observations`, `fixture_setup`,
  `usage.correlation`, `judge_usage`, the raw `activity` object outside `visible_activity`'s
  projection, `incomplete_reason`) carry Story 5.2's secret, prompt-injection and adversarial
  canaries. None may reach the payload.
* **Included text fields** (`user`, `obligation`, a prose segment, a judge reason) carry distinct
  **marker** strings, which must arrive verbatim. The prompt-injection text is planted here too:
  channel 2 publishes it, and the proof is that it arrives as inert data.

| Proof | How |
|---|---|
| AC1 verdict spans | subprocess vs capture server: one `live_eval.verdict` per turn of every attempt; `trace_id == conversation_id.hex`; parent = low 64 bits; `start == end ==` `occurred_at` (or `finished_unix`); exact key set; values equal the report's |
| AC1 experiment | the `evaluate {name}` span: `name == f"{model} {run_id}"`, `dataset_name == "live-conversations"`, `gen_ai.operation.name == "experiment"`, `n_cases` = final-attempt turns only; `assertion_pass_rate` = the fixture's pass fraction; case names and scores as recorded |
| AC1 nothing re-executed | the planner's task and evaluators run with the model, API and judge unavailable (no network but the capture server) and the result equals the recording |
| content rule: excluded | no excluded-field canary in the raw OTLP bytes or decoded payload; no `code.*` key; verdict spans carry no text key |
| content rule: included | each marker appears verbatim in its case's `inputs`, `output.reply` or score `reason`, and nowhere else (not in verdict spans) |
| resource | every exported span's resource keys `== RESOURCE_ALLOW ∪ {deployment.environment}` with value `live-eval`; a Task 4 unit shows `live_eval_channel=False` leaves 5.9's resource rule unchanged |
| credentials | a `CREDENTIAL_ENV_VARS` value set in the subprocess env and planted in a reply → exit 2, `report_contains_credential`, nothing sent, the value absent from stdout/stderr; a 7-character value is not matched |
| size | a case whose text exceeds 16 KiB → `report_malformed` |
| trace-ID parity | `conversation_traceparent_header(id)` equals 5.9's path-derived header, zero-low-bits case included |
| AC2 token absent | `LOGFIRE_TOKEN=""` → exit 2, `logfire_token_absent`, capture server saw zero requests |
| AC2 unavailable | unreachable, 401, slow → exit 1, `logfire_export_failed`, each within a bound (≤ 20 s); stderr and stdout carry no token canary |
| AC2 refusals | each of `report_unreadable`, `report_schema_unsupported`, `report_unfinished`, `report_malformed` (including a canary in a factual-failure code and a duplicate `conversation_id`) → exit 2, nothing sent. Planner-level cases in-process; one subprocess case |
| AC2 untouched, never read back | digests of report, baseline and tracked `evidence/**` unchanged across a published and a failed run; the capture server saw only `POST /v1/traces` |
| closed vocabulary | `PUBLISH_REASONS` covers every reason the code emits (AST or exhaustive-branch test) |
| scrubbing off | a fixture code `unauthorized_effect` and a reply sentence containing "session" arrive verbatim |
| env helper | the subprocess env always sets both Logfire variables |

### Mutation table minimum (Task 10)

Each row: mutate already-green code, run the named guard, record before/after, restore the exact
bytes.

| Mutation | Guard that must redden |
|---|---|
| exit status from `logfire.force_flush()` instead of `finish()` | 401 and unreachable subprocess cases |
| `send_to_logfire=True` | read-nothing-back and resource tests |
| drop `additional_span_processors` (export through nothing) | AC1 verdict-span case (nothing captured → exit 1) |
| `scrubbing` left at default | `unauthorized_effect` case |
| planner copies `turn["verified"]` into case `output` | content-rule (excluded) case |
| planner re-implements the reply projection and passes the raw `activity` | content-rule (excluded) case, via the raw-activity canary |
| planner drops `user` from `inputs` | content-rule (included) case |
| credential check removed | credentials case |
| `live_eval_channel` not passed by the publication builder | resource case |
| `live_eval` verdict validator → identity | Task 4 canary-verdict unit |
| `code.filepath` moved to the `evals` allow-list | content-rule (`code.*`) case |
| random trace ID instead of `conversation_trace_ids` | parity + AC1 trace-ID case |
| experiment includes non-final attempts | `n_cases` case |
| token check skipped | token-absent case |
| `report_unfinished` check removed | refusal case |
| `-p no:pytest_logfire` removed from `addopts` | plugin-registration test |
| `import logfire` in `evals/live_conversations/evidence.py` | one-file guard |
| `logfire` moved to runtime deps | dependency guard |
| subprocess env helper stops setting `LOGFIRE_TOKEN` | env-helper test |

### Testing requirements

* Run from `backend/`: `uv run --frozen pytest -q`; the new tests are in the default suite (no
  `postgres` marker needed, no Docker).
* Subprocess via `sys.executable -m evals.live_conversations.logfire_publish`, `cwd=backend/`, env
  from the one helper. Bound every subprocess with `timeout=`.
* No live provider, no real token, no hosted Logfire in any test. Zero frontend tests change.
* New guards each carry a synthetic violating case (`test_each_guard_detects_synthetic_violating_source`
  pattern).

### Project structure notes

The publisher sits beside `evidence.py`, the other post-hoc CLI that reads finished run reports.
`adapters/telemetry/` keeps the only OTel SDK code (`spans.py`); the new `conversation_trace.py` is
stdlib and exists so the API boundary and the publisher cannot disagree on the trace ID.
`application/` and `domain/` gain nothing.

### Previous-story intelligence (5.9)

* Measure against the real OTLP payload, never a settings object; 5.9's review found a HIGH leak
  (`http.target` free text on matched routes) only in hosted Logfire.
* Bounded shutdown needs its own deadline thread (SDK 1.44 `force_flush` ignores its timeout).
* `backend/.env` holds a real `LOGFIRE_TOKEN`. One review probe reached the hosted project by
  importing `settings` in an ad-hoc script. Pop the tracing vars after importing `settings` in any
  probe.
* Vacuous canary cells were a review finding. Each content-rule assertion must be shown red by a
  mutation.

### Git intelligence

Last five commits are Story 5.9's review close-out (`3bf0fb1` merge, `42131b0` docs, `9623e6c` /
`ae9ea0f` evidence, `edb2efe` review fixes to `spans.py`, `span_policy.py`, `api/tracing.py`,
`settings.py`, `trace_capture.py`). Every file this story extends was last shaped there. Read
`edb2efe`'s diff of `spans.py` (bounded shutdown, exporter session/CA) before extracting the shared
exporter helper.

### References

* ACs — `_bmad-output/planning-artifacts/epics.md:1610-1629`
* Proposal §1.2, §2.2, §4.3 — `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-24.md`
* AD-12, Stack — `…/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:162,283`
* Addendum §2.1, §6 — `…/prds/prd-ShiftMind-2026-07-21/addendum.md:60,149`
* Story 5.9 Decisions 3, 4, 6, 8, 12 and review findings — `_bmad-output/implementation-artifacts/5-9-trace-the-full-request-path-to-logfire-behind-one-export-boundary.md`
* Report format — `backend/evals/live_conversations/suite.py:109-113,149-150,199`, `runner.py:153-328`; final-attempt rule `reporting.py:54-56`; identity `evidence.py::_source_runs`
* Logfire `configure`, `AdvancedOptions`, `propagate.attach_context`, Experiments page — logfire 5.1.0 source and Logfire docs via Context7 (`/websites/pydantic_dev_logfire`), 2026-09-24
* pydantic-evals `Dataset.evaluate`, `increment_eval_metric` — pydantic-evals 2.27.0 source
* Domain model (cited per the standing rule; no metric touched) — `docs/DOMAIN-MODEL.md` §1–§3, §5

---

## Dev Agent Record

### Agent Model Used

Claude Opus 5.5 (`claude-opus-5-5`), Claude Code, 2026-09-25.

### Debug Log References

- **Task 1 re-verification.** `uv lock` delta confirmed: `executing 2.2.1`, `logfire 5.1.0`, `markdown-it-py 4.2.0`, `mdurl 0.1.2`, `pydantic-evals 2.27.0`, `rich 15.0.0` added, 0 changed. Fact 8 re-confirmed through mutation row 1: with exit status taken from `logfire.force_flush()`, the 401 case exits 0.
- **Smoke run on the real report** (`live-matrix-5-7-final3.json`, local capture server only, canary token): exit 0, 90 verdict spans, 90 cases, **541** spans exported. Creation measured 361 with fewer evaluators; the three recorded evaluators add 270 `evaluator:` spans. Only `POST /v1/traces` was seen. Resource keys were exactly `RESOURCE_ALLOW ∪ {deployment.environment}`.
- **Drift check caught an unmeasured key.** pydantic-evals 2.27.0 also emits `code.function` on its spans; creation's table listed only `code.filepath`/`code.lineno`. Added to the `evals` category's `KNOWN_DROPPED`.
- **Shape validators bound shape, not content.** `CANARY-DB-5-2` is a valid `scenario` shape. The `live_eval` canary unit therefore uses free-text canaries. The planner additionally admits only `load_scenarios()` IDs.
- **Full regression:** `uv run --frozen pytest -q` → **2432 passed, 2 skipped, 10 deselected, 1 failed** (399 s). The failure is Story 5.9's `test_turn_and_solver_outcomes_are_unchanged_by_a_failing_exporter`: `[slow]` in one full run, `[unreachable]` in the next. In both, the tracing-off and tracing-on runs reached different solver terminals (`solver_timed_out` vs `solver_failed`) under the test's 5 s solver budget. Run alone: 3/3 passed, twice. It is load-dependent: CPU contention in the full suite pushes the 5 s solve over its budget. This story does not change the worker or solver path; it only extracts `_otlp_exporter`, which constructs the same exporter. Not fixed here; flagged for review.
- **Four mutation rows first stayed green and were fixed before review.** (1) Deciding with `logfire.force_flush()` *after* `finish()` was equivalent, so the mutation now replaces `finish()` itself. (13) The parity test compared the shared function with itself, so it now asserts an independently written derivation. (17) pytest's `-p no:logfire` also blocks `pytest_logfire`, so removing only the second flag was equivalent; the row removes both. (20) The env-helper test used an empty token, which the credential-blanking loop also produces; it now uses a canary.

### Completion Notes List

- Tasks 1–10 complete; **Task 11 (the one hosted-Logfire publication) waits for Minh's go-ahead**, per Decision 10.
- AC1: verdict spans land in the conversation's trace with the synthesized parent and the turn's time. The experiment is named `{model} {run_id}` under `live-conversations`, with final attempts only, and replays the recording.
- AC2: the publisher refuses with a closed vocabulary, exits 1 on an unavailable Logfire within the bound, and never touches the report, baseline or `evidence/**` (sha256 before/after). It sends only `POST /v1/traces`.
- No evidence regenerated, no live run, zero frontend diff.

#### Mutation table (demonstrated red; every mutation reverted, tree left as before)

| # | Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|---|
| 1 | `finish()` replaced by `logfire.force_flush()` as the delivery verdict | `test_an_unavailable_logfire_exits_1_within_a_bound` | green 3/3 | RED `[rejected]` (401 → exit 0); `[unreachable]`,`[slow]` stayed exit 1 because the flush itself returned `False` there |
| 2 | `send_to_logfire=True` | read-nothing-back + resource tests | green | RED 2/2 |
| 3 | `additional_span_processors=[]` | AC1 verdict-span test | green | RED (fixture: exit 1) |
| 4 | `scrubbing=False` removed | scrubbing-off test | green | RED |
| 5 | planner copies `turn["verified"]` into output | excluded-fields test | green | RED |
| 6 | planner passes raw `activity` as reply | excluded-fields test (raw-activity canary) | green | RED |
| 7 | `user` dropped from `inputs` | included-text test | green | RED |
| 8 | credential check removed | both credential tests | green | RED 2/2 |
| 9 | `live_eval_channel=True` removed from the builder | resource test | green | RED |
| 10 | verdict validator → identity | canary unit `[verdict]` | green | RED |
| 11 | `code.filepath` added to `evals` allow-list | excluded-fields (`code.*`) test | green | RED |
| 12 | random UUID for the verdict traceparent | AC1 verdict-span test | green | RED |
| 13 | parent from the high 64 bits in `conversation_trace_ids` | parity + AC1 tests | green | RED 3/5 |
| 14 | non-final attempts become cases | experiment test | green | RED |
| 15 | token check removed | token-absent test | green | RED |
| 16 | `report_unfinished` raise → `finished_unix = 0` | refusal subprocess + planner case | green | RED 2 |
| 17 | both `-p no:` flags removed from `addopts` | plugin-registration test | green | RED |
| 18 | `import logfire` in `evidence.py` | one-file guard | green | RED |
| 19 | `logfire==5.1.0` added to runtime deps | dependency guard | green | RED |
| 20 | env helper stops setting `LOGFIRE_TOKEN` | env-helper test | green | RED |

### File List

- `Dockerfile` (comment only)
- `backend/pyproject.toml`, `backend/uv.lock`
- `backend/adapters/telemetry/conversation_trace.py` (new)
- `backend/adapters/telemetry/span_policy.py`, `backend/adapters/telemetry/spans.py`
- `backend/api/tracing.py`
- `backend/evals/live_conversations/publication.py` (new), `backend/evals/live_conversations/logfire_publish.py` (new)
- `backend/tests/test_live_eval_publication.py` (new)
- `backend/tests/test_trace_export_boundary.py`, `backend/tests/architecture/test_trace_export_boundaries.py`
- `backend/tests/trace_capture.py`, `backend/tests/test_trace_export_failure_independence.py`
- `docs/TESTING.md`, `docs/CONFIGURATION.md`
- `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` (Stack row)
- `_bmad-output/implementation-artifacts/deferred-work.md`, `_bmad-output/implementation-artifacts/sprint-status.yaml`, this story file

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-24 | Story created at `3bf0fb1` (clean). Design measured, not written from docs: an overlay env with the exact pins drove the real Story 5.7 report through three export pipelines and three failure endpoints, all local. Ten facts shaped ten decisions. The main ones: the Logfire SDK exporter leaks host, OS, git HEAD and absolute paths and reads back from Logfire, so the publisher exports through 5.9's sanitizer instead; Logfire scrubbing corrupts closed-vocabulary codes; `force_flush()` reports success on a 401; and a test subprocess would load the real token. Ultimate context engine analysis completed - comprehensive developer guide created. |
| 2026-09-25 | Minh approved publishing conversation text. Addendum §6 amended to name two synthetic-only content channels, the stack and this publisher (recorded as *Amendment 2026-09-25* in sprint-change-proposal-2026-09-24). Decisions 3, 4, 6, 7 and 9, the proof table, mutation table, Tasks 4/9/11 and trap 13 updated. Cases now carry the user message and obligation (`inputs`), the visible reply (`output.reply`, via `runner.visible_activity`) and the judge's reasons (per-score `EvaluationReason`, measured to export). Verdict spans stay text-free. New `live_eval_channel` resource tag. New refusals `report_contains_credential` (exact-value credential check) and a 16 KiB per-case text bound (measured maximum 3 KB). Scrubbing stays off. |
| 2026-09-25 | Implemented Tasks 1–10 on `story/5-10-publish-live-evaluation-results-to-logfire`. Mutation table: 20/20 red. Full regression 2432 passed, 1 load-dependent 5.9 failure (Debug Log). Task 11 awaits Minh. |
