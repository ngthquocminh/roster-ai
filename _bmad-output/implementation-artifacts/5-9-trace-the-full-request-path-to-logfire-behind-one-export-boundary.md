---
baseline_commit: 67584d5
---

# Story 5.9: Trace the Full Request Path to Logfire Behind One Export Boundary

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a portfolio operator,
I want each conversation's HTTP, agent, model, tool, and database work — and each solver job — traced
in Logfire behind an enforced export boundary,
So that I can see where a request spent its time and tokens without widening what leaves the
application.

**Added 2026-09-24 by `sprint-change-proposal-2026-09-24.md`. Not a Gate B criterion.** Findings
F1–F5 in that proposal are binding and are carried into the Decisions below.

**What exists today.** PydanticAI already emits GenAI spans (`agent/runtime.py:340-350`,
`include_content=False, include_binary_content=False`), and nothing exports them:
`create_agent_runtime` (`agent/runtime.py:1009`, called only through `api/deps.py:123`) passes no
tracer provider. The API, the database and the worker emit no spans at all. Story 5.2 proved the
agent spans content-free *through an in-memory exporter* and left three gaps this story inherits:
the allow-list is a test constant (`tests/test_content_minimization.py:46`), no allow-list is
enforced at an export boundary, and exception text leaks through span events
(`deferred-work.md:696`, re-pointed here).

**What creation measured that nobody had written down.** The allow-list below was not written from
documentation. A throwaway harness instrumented the real app against Docker PostgreSQL with the exact
pins in Decision 2 and drove every channel with Story 5.2's canaries. Eleven facts changed the
design; each is load-bearing for a Decision:

1. Exception text reaches the span **status description**, not only events: `RuntimeError: upstream
   rejected CANARY-… CANARY-PROMPT-5-9` on both the `chat` and `invoke_agent` spans (Decision 4).
2. A database span's status description **echoes the bound value**
   (`invalid input syntax for type uuid: "CANARY-DBVALUE-5-9-True"`) **even with
   `hide_parameters=True`** — the value comes from psycopg's own error text (Decision 4).
3. `model_request_parameters` carries `instruction_parts` — the whole 14.6 KB static system prompt —
   **in default mode**, on every `chat` span. Story 5.2's Decision 6 kept the attribute for its tool
   schemas and did not see this (Decision 4).
4. With the default propagator, the outbound provider request carries `traceparent` **and**
   `baggage: gen_ai.agent.name=agent,gen_ai.agent.call.id=…,gen_ai.conversation.id=<uuid>` — trace
   and conversation identifiers sent to the model provider (Decision 6).
5. `http.url` carries the full query string (`?probe=CANARY-QUERY-5-9` observed); an unmatched route
   is named `GET` and carries the client's raw path (a canary) in `http.target`/`http.url`
   (Decision 4).
6. A middleware added with `app.add_middleware` — before *or* after `instrument_app` — runs **inside**
   the OpenTelemetry middleware and adopts the client's `traceparent`; `context.attach` outside it
   loses the conversation-route server spans entirely. Only a header rewrite wrapped **outside** the
   instrumented stack works (Decision 6).
7. Instrumenting FastAPI inside the lifespan records **zero** server spans; Starlette builds the
   middleware stack on the lifespan's own first ASGI message (Decision 11).
8. `SQLAlchemyInstrumentor().instrument()` patches `sqlalchemy.create_engine` **after** `api/deps.py`
   has already bound it as `create_postgres_engine`, so the API's engine gets `connect` spans and no
   statement spans; the instrumentor is also a process singleton (a second `instrument(engine=…)` logs
   "already instrumented" and does nothing) (Decision 8).
9. The worker produced **100 database spans for one job, every one a root span** — a hundred one-span
   traces — and an idle poll costs **4 root spans per second** (Decisions 7 and 10).
10. An open SSE stream costs **~12 spans per second** (42 in 3.5 s: poll statements plus one `http
    send` span per chunk), and the sampler **cannot see `db.*` attributes** when a statement span
    starts — `start_attr_keys: []` (Decision 7).
11. Adding `AGENT_TRACE_CONTENT_MODE` to `compose.override.yml` — which AC4 requires — turns **two
    Story 5.8 tests red** and would make every future live run refuse comparison with the committed
    baseline (Decision 13).

**Scope summary.** Runtime dependencies pinned (OpenTelemetry SDK, OTLP/HTTP exporter, three
instrumentations), three settings, one sanitizing export boundary with its policy as a production
constant, an outermost ASGI trace-context boundary, a sampler, per-engine SQLAlchemy tracing, three
manual worker spans, a run-correlation capability on the agent, content mode behind a config-file
guard, Story 5.8 kept comparable, Story 5.2's evidence regenerated with four new span channels, and a
single-pass Gate A refresh. **No migration, no new table, no new route, no new API field, no change
to the live report schema or `configuration_digest`'s computation, and zero frontend diff.**

**Depends on, and consumes:** Story 5.2's canaries, pinned injection cases, `_span_blob` discipline,
allow-list and evidence generator; Story 5.1's telemetry port, `CorrelationV1` and route-template
middleware; Story 5.3's worker composition; Story 5.8's `behavioral_digest`; Story 1.11's
`evidence_binding.py`, `gate_a_readiness.py` and `--code-from`.

**Unblocks:** Story 5.10 (verdict spans need the conversation-derived trace ID from Decision 6);
Story 6.3's "sanitized hosted Logfire" clause.

---

## Facts this story depends on — each one written down and citable

Retro action A3 requires this pass before decisions. None of these may be re-derived from code.

| Fact | Where it is written |
|---|---|
| **NFR3:** content "must be excluded from external telemetry by default; only explicitly allow-listed sanitized metadata may leave the application boundary." | `epics.md:79` |
| **NFR4:** "Secrets must never appear in … logs, traces, or evaluation fixtures." | `epics.md:81` |
| **NFR10:** "Model-provider or Logfire failure must cause zero product-state corruption and zero authoritative-audit loss." | `epics.md:93` |
| **NFR22:** every agent run searchable by one stable run identifier "across product records, audit, operational logs, and available traces". Story 5.2's measured key list has no run ID, so traces fail it today (F5). | `epics.md:117`; proposal F5 |
| **NFR30:** "external model and telemetry providers receive only the minimum explicitly configured content." This is the sentence that makes the outbound `baggage` header (measured fact 4) a defect and makes content mode legal only because it is *explicitly configured*. | `epics.md:133` |
| **AD-1:** domain and application must not import FastAPI, PydanticAI, SQLAlchemy, Cognito, S3, Logfire. The enforcement list is `FORBIDDEN_ROOT_MODULES`. | `ARCHITECTURE-SPINE.md:52`; `tests/architecture/test_agent_runtime_boundaries.py:53` |
| **AD-12 (amended 2026-09-24):** "Every exported span passes an export-boundary sanitizer (attribute allow-list, exception type only); client trace context is discarded and conversation-scoped requests share one conversation-derived trace. No telemetry system authorizes or blocks product work." | `ARCHITECTURE-SPINE.md:162` |
| **Stack rows** (`pinned at Story 5.9` / `pinned at Story 5.10`); the Logfire SDK is "never imported by api, worker, agent, application or domain". | `ARCHITECTURE-SPINE.md:282-283` |
| **Addendum §6:** the one authorized diagnostic mode is `AGENT_TRACE_CONTENT_MODE=synthetic-eval`, set only by the disposable live-evaluation stack, tagged `deployment.environment=live-eval`; credentials and exception text withheld in every mode; client trace context never trusted. | `prds/prd-ShiftMind-2026-07-21/addendum.md:149` |
| **AR27:** add and lock each planned dependency only at its implementation gate. This story is that gate for the OpenTelemetry runtime rows. | `epics.md:173` |
| **F1–F5** (content inside a real API container; trace ID set at the HTTP boundary; API→worker stays two traces; allow-list is only a test constant; traces carry no run ID). | `sprint-change-proposal-2026-09-24.md` §1.3 |
| **Story 5.2 Decision 7:** assert on OBSERVED spans, never on a settings object. | `5-2-prevent-content-and-secret-leaks.md:325-341` |
| **Story 5.8:** `behavioral_digest` is an EXCLUSION rule — "a newly added environment key is included by default and fails closed". | `backend/evals/live_conversations/configuration.py:9-17` |
| **Evidence convention:** commit code → measure on a clean tree → generate → commit evidence separately; a recorded commit must touch a code file; `--code-from` reuses a code binding "resolved earlier in the same pass, on the clean tree". | `docs/EVIDENCE-CONVENTION.md`; `backend/scripts/evidence_binding.py:529-545`; `backend/scripts/gate_a_readiness.py:581-590` |
| **Gate A regeneration** is three runners on a clean tree with Docker up; a skip is "not proven". | `docs/GATE-A-RUNBOOK.md` §3 |
| **The clean-tree realism test skips on any dirty path except the readiness report's own output** — so a dirty 5.2 evidence file during the three-runner pass records `measurement_integrity` as not proven. | `backend/tests/test_evidence_binding.py:56-63` |
| **CI is keyless** and no provider credential is a repository secret. | `docs/CI-SECRETS-CHECKLIST.md`; `epics.md:125` (NFR26) |
| **A demonstrated red comes from mutating already-green code**, recorded in a mutation table before review. | `epic-4-retro-2026-09-02.md` §4, §6 A1; `_bmad/custom/bmad-dev-story.toml` |
| **Domain model.** This story computes no metric, reads no demand row and adds no assignment field. It is cited because the standing rule requires it; the only numbers this story adds to a span are token counts, a queue age and a solver wall time. | `docs/DOMAIN-MODEL.md` §1–§3 |

---

## Acceptance Criteria

Verbatim from `epics.md:1578-1606`. Frozen.

**AC1.**
**Given** `LOGFIRE_TOKEN` (and region base URL) is configured
**When** the API and worker run
**Then** FastAPI request, SQLAlchemy, outbound httpx, PydanticAI agent/model/tool spans, and worker
lease/execute/solve spans are exported over OTLP to Logfire under `service.name`
`shiftmind-api`/`shiftmind-worker`
**And** with the token absent no exporter is constructed and behavior is identical to today.
(NFR15, AR27)

**AC2.**
**Given** requests under `/conversations/{conversation_id}/…`
**When** they are traced
**Then** every turn's request, agent, and database spans share one trace whose ID is derived from the
conversation UUID, the agent root span carries `shiftmind.agent_run.id`, and worker spans carry
`shiftmind.schedule_run.id` shared with the enqueueing request
**And** client-supplied trace context is discarded on every route. (NFR22)

**AC3.**
**Given** the default content mode
**When** any span leaves the process
**Then** an export-boundary sanitizer forwards only allow-listed keys for every span type, strips URL
query strings, never exports SQL parameter values, and records exception events by type only
**And** Story 5.2's secret, prompt-injection, and adversarial fixtures are absent from what the real
exporter receives, including span events, HTTP, and database spans. (NFR3, NFR4, NFR30, AD-12)

**AC4.**
**Given** `AGENT_TRACE_CONTENT_MODE=synthetic-eval`
**When** the live-evaluation stack runs
**Then** prompts, completions, and tool arguments/results are exported with
`deployment.environment=live-eval`, while credentials and exception text are still withheld
**And** an architecture test proves the only tracked file setting a non-`off` mode is
`evals/live_conversations/compose.override.yml`. (NFR30)

**AC5.**
**Given** Logfire is unreachable, slow, or rejects the token
**When** agent runs, approvals, and solver work proceed
**Then** product state, authoritative audit, and eval verdicts are unchanged and export never blocks a
request or a job. (AD-12, NFR10)

**AC6.**
**Given** the proof suite changes
**When** evidence is regenerated per `docs/EVIDENCE-CONVENTION.md`
**Then** `evidence/story-5.2/content-minimization-report.json` records the export boundary and the
new span channels as tested. (NFR27)

**Out of scope, deliberately.** One continuous API→worker trace, browser/frontend tracing, OTel metrics
or log export (`deferred-work.md:663` stays with Epic 6), the Logfire SDK in any runtime process,
prompt management, and anything from Story 5.10 (verdict spans, pydantic-evals).

**Path note.** The API mounts every conversation route under `/api/v1`, so AC2's
`/conversations/{conversation_id}/…` is `/api/v1/conversations/{conversation_id}/…` on the wire.
AC4's file is `backend/evals/live_conversations/compose.override.yml` from the repository root.

---

## Measured at creation — `67584d5`, Docker PostgreSQL 18 up

`67584d5` with the 2026-09-24 planning edits uncommitted (the proposal, `epics.md`, the spine, the
addendum, `deferred-work.md`, `sprint-status.yaml`). Re-verify at Task 1 and record any drift.

### Test baseline

| Suite | Measurement |
|---|---|
| Backend default (`uv run --frozen pytest -q`) | **2240 passed, 2 skipped, 10 deselected**, 227.6 s. One skip is `test_evidence_binding.py::test_bindings_on_a_clean_tree_name_a_reproducible_commit` ("needs a clean tree" — the planning edits); expect **2241 passed, 1 skipped** on a clean tree. The other is `test_scheduling_inspect.py::…[tasks]` (by design). |
| `tests/architecture/` | **79 passed**, 12 files |
| `tests/test_content_minimization.py` | **16 passed** |
| `tests/test_content_minimization_report.py` | **4 passed** |
| `tests/test_evidence_convention.py` | **105 passed** |
| `tests/test_gate_a_readiness.py` | **44 passed** |
| `tests/test_live_conversation_drop_check.py` | **42 passed** |
| `tests/test_live_conversation_configuration.py` | **9 passed** |
| `tests/test_conversations_api.py` / `test_agent_runtime_adapter.py` / `test_settings.py` | **32 / 85 / 37 passed** |
| Frontend Vitest (`npx vitest run`) | **648 passed, 85 files**, 108 s. This story has a zero-line frontend diff. |
| Playwright | Not re-measured (zero frontend diff). Last recorded: **80 tests, 10 files** (Story 5.2). Needed only for Task 16's Gate A pass. |

### Dependency resolution (scratch copy of `pyproject.toml`/`uv.lock`; the repo's files were not touched)

Adding the five packages resolves **12 new packages and changes 0 existing versions**:
`opentelemetry-exporter-otlp-proto-common 1.44.0`, `-exporter-otlp-proto-http 1.44.0`,
`-instrumentation 0.65b0`, `-instrumentation-asgi 0.65b0`, `-instrumentation-fastapi 0.65b0`,
`-instrumentation-httpx 0.65b0`, `-instrumentation-sqlalchemy 0.65b0`, `opentelemetry-proto 1.44.0`,
`opentelemetry-util-http 0.65b0`, `asgiref 3.12.1`, `googleapis-common-protos 1.75.0`,
`wrapt 2.4.1`. `protobuf` stays at the ortools-compatible **5.26.1** (`opentelemetry-proto` requires
`protobuf>=5.0,<8.0`). `opentelemetry-api` stays at the locked **1.44.0** (`pydantic-ai-slim 2.27.0`
requires `>=1.28.0`; `opentelemetry-sdk 1.44.0` requires `==1.44.0`). PyPI, 2026-09-24: 1.44.0 /
0.65b0 (2026-07-16) are the latest releases. Moving `httpx` into runtime dependencies at `==0.28.1`
changes no locked version.

### How the span measurement was taken

`uv run --frozen --with opentelemetry-sdk==1.44.0 --with opentelemetry-exporter-otlp-proto-http==1.44.0
--with opentelemetry-instrumentation-{fastapi,sqlalchemy,httpx}==0.65b0`, a `TracerProvider` +
`InMemorySpanExporter`, a throwaway database bootstrapped with `scripts.bootstrap_local`, and the real
`api.main.app` driven through `TestClient` with `evals.live_conversations.http_client.ApplicationConversation`
(fake OIDC, CSRF). Every credential env var was preset to a 5.2 canary before `settings` was imported.
Channels: (a) one deterministic-model turn; (b) query strings with a canary; (c) an SSE replay driven
at the ASGI boundary; (d) the provider-error path through the execute route, an unhandled route
exception, and a DB error echoing a bound value; (e) outbound httpx to a local OpenAI-shaped stub;
(f) hostile `traceparent`/`tracestate`/`baggage` on a conversation route, a non-conversation route and
`/health`; (g) `POST /api/v1/schedule-runs` then the real `worker.composition.create_runtime()` →
`run_once` (a 10 s CP-SAT solve, `solver_completed`) plus idle polls; (h) (a) repeated with
`include_content=True`; plus four middleware placements, a sampler prototype, a worker manual-span
prototype and a lifespan-instrumentation check. **Semconv emitted:** the *old* HTTP and DB conventions
(`http.method`, `http.url`, `http.target`, `db.statement`, `db.system`) — `OTEL_SEMCONV_STABILITY_OPT_IN`
unset.

---

## The export-boundary allow-list — decided, per span type

This is the story's central deliverable. Every key observed in the measurement is listed with its
decision. **The rule is default-deny: a key not marked allow or transform is dropped**, so a key a
future library version adds never leaves the process until a person decides it should. Each table is
the source for `adapters/telemetry/span_policy.py` (Decision 4). "Category" is chosen by the span's
instrumentation-scope name.

### HTTP server — scope `opentelemetry.instrumentation.fastapi`, kind SERVER

| Key | Measured sample | Decision | Reason |
|---|---|---|---|
| `http.method` | `POST` | allow | closed vocabulary |
| `http.route` | `/api/v1/conversations/{conversation_id}/agent-runs/{agent_run_id}/execute` | allow | template; no identifiers |
| `http.status_code` | `200` | allow | |
| `http.scheme` | `http` | allow | |
| `http.flavor` | `1.1` | allow | |
| `net.host.port` | `80` | allow | the server's own port |
| `http.target` | `/api/v1/conversations/3b52…/messages` | **transform** — cut at the first `?` or `#`; **drop when the span has no `http.route`** | path IDs are identifiers, not content; an unmatched route's path is client free text (fact 5) |
| `http.url` | `http://shiftmind.test/api/v1/conversations?scenario_id=…&probe=CANARY-QUERY-5-9` | **drop** | carries the query (fact 5) and the client-controlled Host; `http.target` + `http.route` suffice |
| `http.host`, `http.server_name` | `shiftmind.test` | drop | client-controlled `Host` header |
| `http.user_agent` | `testclient` | drop | client fingerprint |
| `net.peer.ip` | `198.51.100.7` | drop | client IP address — personal data |
| `net.peer.port` | `50000` | drop | client's ephemeral port |
| `http.request.header.*`, `http.response.header.*` | not emitted (only when `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_*` is set) | drop | would carry `Cookie`/`X-CSRF-Token` |
| `shiftmind.schedule_run.id` | new; `POST /api/v1/schedule-runs` only (Decision 9) | allow, UUID-validated | F3's attribute join |
| `… http send` / `… http receive` child spans (`asgi.event.type`, `http.status_code`) | 3 per JSON request, 7 per 3.5 s of SSE | **not emitted** — `exclude_spans=["receive", "send"]` at the source (Decision 7) | one span per ASGI message is noise |

### HTTP client — scope `opentelemetry.instrumentation.httpx`, kind CLIENT

| Key | Measured sample | Decision | Reason |
|---|---|---|---|
| `http.method` | `POST` | allow | |
| `http.url` | `http://127.0.0.1:58645/v1?probe=CANARY-QUERY-5-9/chat/completions` | **transform** — `scheme://host[:port]/path`; query, fragment and userinfo removed | the host names the provider; the query carried a canary (fact 5) |
| `http.status_code` | `200` | allow | |
| request/response headers | **never recorded** (measured: no `Authorization`, no key) | — | |
| outbound `traceparent`/`baggage` headers | sent by the default propagator (fact 4) | **not sent** — extract-only propagator (Decision 6) | NFR30 |

### Database — scope `opentelemetry.instrumentation.sqlalchemy`, kind CLIENT

| Key | Measured sample | Decision | Reason |
|---|---|---|---|
| `db.system` | `postgresql` | allow | Logfire honors the old key |
| `db.name` | `rosterai` | allow | |
| `db.operation` | `SELECT rosterai` | allow | |
| `db.statement` | `SELECT set_config('app.site_id', %(site_id)s, true)` | **allow** | **Verified placeholders only:** 27 distinct statements across a full turn, a query, an SSE replay and an enqueue; the only literals are the application constants `'app.site_id'` and `''`; even `LIMIT %(param_1)s::INTEGER` is bound. No `literal_binds` and no string-built SQL in any runtime root (the one f-string, `store/db.py:42`, is the legacy SQLite `PRAGMA` path SQLAlchemy never sees). Kept that way by Decision 4's AST guard. |
| `db.user` | `shiftmind_login` | drop | the identity half of a credential |
| `net.peer.name`, `net.peer.port` | `localhost`, `5432` | drop | infrastructure topology; nothing to diagnose in a single-database system |
| status description | `invalid input syntax for type uuid: "CANARY-DBVALUE-5-9-True"` | **dropped (every span, Decision 4)** | echoes bound values despite `hide_parameters` (fact 2) |
| `connect` spans | produced only by the global instrumentor's `Engine.connect` wrap | **not emitted** — per-engine tracing (Decision 8) | |

### Agent — scope `pydantic-ai` (`invoke_agent agent`, `chat <model>`, `execute_tool <tool>`, `running output function`)

**Default mode (`off`).** All keys below measured on a deterministic turn and on an OpenAI-shaped
stub call, or read from pydantic-ai 2.27.0's emitters (marked *code*).

| Key | Spans | Measured sample | Decision | Reason |
|---|---|---|---|---|
| `gen_ai.operation.name`, `gen_ai.agent.name`, `agent_name`, `model_name` | all / invoke_agent | `invoke_agent`, `agent`, `function:respond:` | allow | |
| `gen_ai.agent.call.id`, `gen_ai.conversation.id` | all | `01a0d287-5c97-…` | allow | **pydantic-ai's own per-run UUID7s, not ShiftMind's IDs** — see Decision 9 |
| `gen_ai.provider.name`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model` | chat | `openai`, `stub-model` | allow | |
| `gen_ai.response.id`, `gen_ai.response.finish_reasons` | chat | `chatcmpl-1`, `['stop']` | allow | provider bookkeeping, no content |
| `server.address`, `server.port` | chat | `127.0.0.1`, `58645` | allow | the provider host |
| `gen_ai.request.{max_tokens,top_p,seed,temperature,presence_penalty,frequency_penalty}` | chat (*code*, only when set) | numeric | allow, numeric-validated | |
| `gen_ai.usage.input_tokens`, `.output_tokens`, `.cache_read.input_tokens`, `.cache_creation.input_tokens`; prefix `gen_ai.usage.details.` | chat | `133`, `7` | allow, numeric-validated | NFR15 |
| `gen_ai.aggregated_usage.*` (same shapes) | invoke_agent | `337`, `32` | allow, numeric-validated | |
| `pydantic_ai.new_message_index` / `pydantic_ai.variable_instructions` | invoke_agent | `1` / *code* bool | allow | |
| `pydantic_ai.tool.deferral.name` | execute_tool | *code* (5.2 measured) | allow | |
| `gen_ai.tool.name`, `gen_ai.tool.call.id` | execute_tool | `scheduling_inspect`, `deterministic-inspection` | allow | |
| `logfire.msg` | invoke_agent, execute_tool | `agent run`, `running tool: scheduling_inspect` | allow | content-free: fixed text + tool name |
| `logfire.json_schema` | all | `{"type":"object","properties":{"gen_ai.input.messages":{"type":"array"},…}}` | allow | attribute names and types only |
| `gen_ai.tool.definitions` | chat | 12.2 KB of tool name/description/JSON schema | allow | application-authored from `CapabilityManifestV1` (5.2 Decision 6) |
| `model_request_parameters` | chat | 29.8 KB; keys `function_tools, output_tools, output_mode, tool_visibility, instruction_parts, …` | **transform — remove `instruction_parts`** | fact 3: the one instructions channel pydantic-ai's content switch does not gate; any future dynamic instruction built from deps would ride it |
| `gen_ai.input.messages`, `gen_ai.output.messages` | chat | `[{"role":"user","parts":[{"type":"text"}]}]` | **transform — structure-only projection**: keep `role` and per part `type`, `id`, `name`; drop every other field; unparseable → drop key | structure-only today by pydantic-ai's promise; the projection makes it true by construction |
| `pydantic_ai.all_messages` | invoke_agent | structure-only | **transform** — same projection | |
| `shiftmind.agent_run.id`, `shiftmind.site.id`, `shiftmind.conversation.id` | invoke_agent | new (Decision 9) | allow, UUID-validated | F5 / NFR22 |
| `gen_ai.agent.description`, `metadata` | invoke_agent (*code*; not emitted — no description, no run metadata) | — | drop | rendered from deps / run metadata if ever set |
| `tool_arguments`, `tool_response` | (*code*; legacy names for instrumentation versions < 3) | — | drop | |

**Content mode (`synthetic-eval`) — the exact additional key set**, measured with
`include_content=True`: `gen_ai.system_instructions` (chat, invoke_agent), `gen_ai.tool.call.arguments`
and `gen_ai.tool.call.result` (execute_tool), `final_result` (invoke_agent), and
`pydantic_ai.tool.deferral.metadata` (execute_tool, *code*). In content mode the four transforms above
are **not applied** (messages, `all_messages` and `model_request_parameters` pass as emitted). Nothing
else widens: every non-agent category, every event rule, the status rule and the resource rule are
identical in both modes.

### Worker — scope `shiftmind.worker` (manual, Decision 10; prototype measured)

| Span | Keys | Decision |
|---|---|---|
| `shiftmind.worker.execute` (root) | `shiftmind.schedule_run.id`, `shiftmind.job.id`, `shiftmind.site.id` (UUIDs); `shiftmind.job.type` (`schedule_run_execute`); `shiftmind.schedule_run.status` (e.g. `solver_completed`); `shiftmind.job.queue_age_s` (float) | allow, UUID/numeric-validated; the two strings are closed `Literal` vocabularies |
| `shiftmind.worker.lease` (retroactive child) | `shiftmind.schedule_run.id`, `shiftmind.job.id`, `shiftmind.site.id` | allow |
| `shiftmind.worker.solve` | `shiftmind.schedule_run.id`; `shiftmind.solver.status` (`FEASIBLE`); `shiftmind.solver.wall_time_s` (`10.08`) | allow |
| the job's statement spans | database rules above | — |

### Every span type — the rules that are not per-key

| Surface | Decision | Measured reason |
|---|---|---|
| Events | `exception` → **`exception.type` only**; `exception.message`, `exception.stacktrace`, `exception.escaped` dropped. Any other event name → dropped. **Both modes.** | `exception.message` carried the provider-error canary on `chat` and `invoke_agent`, and `route exploded CANARY-ROUTE-ERROR-5-9` on the HTTP server span |
| Status | code kept; **description never exported, both modes** | facts 1 and 2 |
| Links | dropped | none measured; a link can carry attributes |
| Resource | exactly `service.name`, `service.version`, `service.instance.id`, `telemetry.sdk.language`, `telemetry.sdk.name`, `telemetry.sdk.version`, and — content mode only — `deployment.environment=live-eval`. Built explicitly, never merged from `OTEL_RESOURCE_ATTRIBUTES`/`OTEL_SERVICE_NAME`; filtered again at export | Logfire reads `service.version`, `telemetry.sdk.language`, and honors `deployment.environment` as the fallback of `deployment.environment.name` (Logfire docs via Context7) |
| Span name, kind, IDs, times, instrumentation scope | pass through | names are route templates, `GET` for unmatched routes, `<OP> <db>`, fixed agent/worker names, tool names |
| Unknown instrumentation scope | span exported with **no attributes** | default-deny |

---

## Fifteen decisions were made at story creation — do not re-litigate them

Each states its mechanism **and what it does not cover**. Items 1–9 of the proposal's "already
decided" list are not repeated as decisions; they are applied.

### Decision 1 — One export boundary: where OpenTelemetry code may live

| Module | May import | Holds |
|---|---|---|
| `backend/adapters/telemetry/span_policy.py` (new) | stdlib only | the allow-list tables above as constants, the category/transform/event/resource rules as pure functions over plain mappings, `KNOWN_DROPPED` per category |
| `backend/adapters/telemetry/spans.py` (new) | `opentelemetry.*` (SDK, exporter, `opentelemetry.instrumentation.sqlalchemy`) | `ProcessTracing`, `build_process_tracing`, the sanitizing exporter, the sampler, the extract-only propagator, `trace_engine`, `annotate_enqueued_schedule_run`, the worker job scope and `traced_scheduler` |
| `backend/api/tracing.py` (new) | `opentelemetry.instrumentation.fastapi`, `opentelemetry.instrumentation.httpx` | `install_api_tracing` and the outermost ASGI `TraceContextBoundary` |
| `backend/agent/runtime.py` | `opentelemetry.trace` (API only) | the run-correlation capability (Decision 9) |

Everything else — including `adapters/telemetry/json_logs.py`, `adapters/telemetry/__init__.py`, every
router, `application/` and `domain/` — imports no `opentelemetry` module and no `logfire` module.

Enforced by three guards (Task 10): a new one-boundary guard over the non-test backend roots
(`opentelemetry.sdk|exporter|instrumentation` only in `spans.py` and `api/tracing.py`; any
`opentelemetry.*` additionally only in `agent/runtime.py`; `logfire` in none of `api, worker, agent,
application, domain, adapters, engine, services, store, ingest, llm, config` nor backend-root modules);
the amended `test_telemetry_adapter_imports_no_framework` (exempts `spans.py` from the `opentelemetry`
root **only** — `fastapi`, `sqlalchemy`, `pydantic_ai`, `pydantic_graph`, `logfire` stay forbidden
there); and AD-1's `FORBIDDEN_ROOT_MODULES` gaining `opentelemetry.sdk`, `opentelemetry.exporter`,
`opentelemetry.instrumentation`.

**The AD-1 edit as literally specified would be a guard that cannot go red.**
`find_forbidden_imports` compares `_root_of(module)` — the first dotted segment — against the tuple
(`test_agent_runtime_boundaries.py:140-154`), so `"opentelemetry.sdk"` in the tuple never matches
anything. The matcher must become prefix-aware (`module == entry or module.startswith(entry + ".")`),
with synthetic cases proving `import opentelemetry.sdk.trace`, `from
opentelemetry.exporter.otlp.proto.http.trace_exporter import X` and `from
opentelemetry.instrumentation.fastapi import Y` are flagged and `from opentelemetry import trace` is not.

**What this does not cover.** AD-1's list names the SDK, exporter and instrumentation packages, not the
API facade: `application/` importing `opentelemetry.trace` would pass AD-1 and is caught only by the
one-boundary guard. Both guards are AST walks over this repository's roots; a third-party package that
itself builds an exporter is invisible to them (none does today — `logfire-api 4.40.0`, locked under
`pydantic-ai-slim`, is a no-op shim that exports nothing without `logfire`).

### Decision 2 — Dependencies: exact pins, and `httpx` becomes a declared runtime dependency

`[project].dependencies` gains `opentelemetry-sdk==1.44.0`, `opentelemetry-exporter-otlp-proto-http==1.44.0`,
`opentelemetry-instrumentation-fastapi==0.65b0`, `opentelemetry-instrumentation-sqlalchemy==0.65b0`,
`opentelemetry-instrumentation-httpx==0.65b0` and `httpx==0.28.1`, each commented in the file's AR27
style. The dev-group `opentelemetry-sdk` and `httpx` entries are removed (their comments move to the
runtime entries). Exact pins, not floors: `EngineTracer` (Decision 8) is a module-level class of
the instrumentation package, and an unpinned upgrade could change its constructor.

`httpx` moves because this story makes it a runtime-instrumented library, which fires
`deferred-work.md:717`'s trigger ("the first story permitted to change `backend/pyproject.toml`'s
dependency list"). Measured lock-neutral.

**What this does not cover.** `logfire` and `pydantic-evals` are Story 5.10's (dev group). The
OTLP exporter posts through `requests` (already locked), which is not instrumented, so export traffic
never creates spans of its own. The Stack table rows are updated to the pins by Task 13.

### Decision 3 — Settings, keyless default, and a keyless test process

Three settings in `backend/settings.py`, parsed in `default_settings()`:

| Setting | Env var | Default | Rule |
|---|---|---|---|
| `logfire_token: str \| None = field(repr=False, default=None)` | `LOGFIRE_TOKEN` | `None` | empty or whitespace → `None`; tagged T-04-01 like the other credentials |
| `logfire_base_url: str` | `LOGFIRE_BASE_URL` | `https://logfire-us.pydantic.dev` | scheme `http`/`https`, no path/query/fragment, trailing `/` stripped; otherwise `InvalidFlagError`. EU users set `https://logfire-eu.pydantic.dev` |
| `agent_trace_content_mode: Literal["off", "synthetic-eval"]` | `AGENT_TRACE_CONTENT_MODE` | `"off"` | anything else → `InvalidFlagError` at process start (fail closed). The string `"synthetic-eval"` is defined once, as `TRACE_CONTENT_SYNTHETIC_EVAL` in `settings.py`, and imported everywhere else |

`build_process_tracing(settings, *, service_name, quiet_parent_span_names=frozenset(), session=None)`
returns `None` when `logfire_token` is `None` — **no exporter, provider, propagator change or
instrumentation is constructed**. Otherwise it constructs `OTLPSpanExporter(endpoint=f"{base}/v1/traces",
headers={"Authorization": token}, timeout=5, session=session)` explicitly — never from `OTEL_EXPORTER_OTLP_*`
env vars — per Logfire's documented contract (`https://logfire-{us|eu}.pydantic.dev/v1/traces`,
`Authorization: <write token>`, http/protobuf; confirmed via Context7 2026-09-24). `session` is a
test seam (a `requests.Session`) and is `None` in production.

**`backend/conftest.py` must pop `LOGFIRE_TOKEN`, `LOGFIRE_BASE_URL` and `AGENT_TRACE_CONTENT_MODE`**
after importing `settings`, exactly as it already pops `LLM_PROVIDER`/`LLM_MODEL`. `settings.py` runs
`load_dotenv(backend/.env)` at import; the moment Minh puts the token in `backend/.env` for the smoke
check, every local pytest run would otherwise configure real export at `api.main` import and ship test
spans to Logfire. A test asserts the test process has no process tracing.

**What this does not cover.** A token set by hand in the shell of a test run is still popped (the
suite is keyless by construction). The token is stored in the exporter's `requests` session headers;
nothing in this repository logs those headers (the exporter's own failure log names status and reason
only, and passes through 5.2's `third_party` sanitization). `LOGFIRE_TOKEN` joins 5.2's credential
repr sweep (`CREDENTIAL_CANARIES`).

### Decision 4 — The sanitizer: one exporter wrapper, default-deny, policy as production data

`SanitizingSpanExporter(inner: OTLPSpanExporter, *, content_mode)` in `spans.py` builds a sanitized
copy of every `ReadableSpan` and hands only copies to the inner exporter. Rules, in full, are the
tables above; mechanically:

* **Category** from the instrumentation scope name: `…fastapi`/`…asgi` → http_server, `…httpx` →
  http_client, `…sqlalchemy` → database, `pydantic-ai` → agent, `shiftmind.worker` → worker, anything
  else → other (no attributes).
* **Attributes**: allow-listed keys pass; transform keys pass through their transform (a transform
  returning `None` drops the key); `shiftmind.*.id` values must parse as UUIDs; usage/numeric keys
  must be `int`/`float` (not `bool`); everything else is dropped. Content-mode keys pass only when
  `content_mode == "synthetic-eval"`, and the four agent transforms are skipped in that mode.
* **Events, status, links, resource** as in "the rules that are not per-key". The sanitizer rebuilds
  the resource from the allow-list even though `build_process_tracing` builds it explicitly — defence
  in depth against a future resource detector.
* `export()` never raises: any sanitization error returns `SpanExportResult.FAILURE` for the batch
  (AD-12). It never returns an unsanitized span on error.

The allow-list **moves into production** (`span_policy.py`); `tests/test_content_minimization.py`
**imports** the agent category's allow-list instead of declaring `SPAN_ATTRIBUTE_ALLOW_LIST`. Story
5.2's "a new key names itself" property is preserved by a **drift check**: every raw key an observed
span emits (pre-sanitizer) must be in its category's `ALLOW ∪ TRANSFORM ∪ CONTENT_MODE ∪
KNOWN_DROPPED`; an unclassified key reddens naming the key, while the runtime independently drops it.

The **SQL guard** that keeps `db.statement` placeholder-only: an AST test over the non-test backend
roots asserting every `sqlalchemy.text(...)` and `.exec_driver_sql(...)` argument is a string literal
(or implicit concatenation of literals) — no f-string, `%`, `+`, `.format`, or name. Resolve the
`text` binding through imports as 5.2's engine guard resolves `create_engine`
(`test_telemetry_boundaries.py`); `store/db.py`'s SQLite `conn.execute(f"PRAGMA…")` is not
`text()`/`exec_driver_sql` and is out of the rule's reach by construction — say so in the docstring.

**What this does not cover.** The allow-list bounds keys and validates a few value shapes; values of
allowed free-form keys (`gen_ai.tool.definitions`, `db.statement`, `logfire.msg`, span names) are
bounded by their source (application-authored text, placeholder SQL, tool names), not by a schema — a
library that starts writing content into an already-allowed key is caught only if a canary reaches it,
exactly 5.2 Decision 7's residual. Span **names** pass through; an `execute_tool <name>` span for a
model-invented tool name would carry that name (pydantic-ai only opens tool spans for registered tools
today). A second SQL construct outside `text()`/`exec_driver_sql` that builds strings (e.g. a future
raw DBAPI cursor) is not guarded.

### Decision 5 — Content mode: two levers, one config file, one stated residual

`AGENT_TRACE_CONTENT_MODE=synthetic-eval` flips exactly two things, both read from the same setting:
the agent's `InstrumentationSettings(include_content=True)` (binary stays `False` in both arms —
5.2's `test_both_instrumentation_constructors_disable_binary_capture` stays green unchanged) and the
sanitizer's content mode; the process resource gains `deployment.environment=live-eval`. The sanitizer
is authoritative: if the two ever disagree, `off` at the sanitizer drops the content keys regardless.

`backend/evals/live_conversations/compose.override.yml` sets `AGENT_TRACE_CONTENT_MODE: synthetic-eval`
in **both** the `api` and `worker` environment blocks (the worker emits no content; the tag separates
live-eval worker traces in Logfire). `docker-compose.yml` and `.env.example` never mention the variable.

**F1 guard** (architecture test, `git ls-files`, excluding `docs/**`, `_bmad-output/**`, `**/*.md`,
`backend/tests/**`): (1) the only tracked files containing the token `AGENT_TRACE_CONTENT_MODE` are a
declared set, each with its reason — `backend/settings.py` (reads it), `backend/conftest.py` (pops it,
Decision 3), `backend/evals/live_conversations/configuration.py` (excludes it from the digest,
Decision 13) and the override (sets it); (2) the only tracked files containing `synthetic-eval` are
`backend/settings.py` (the constant) and the override — this is the rule that actually guards the
value; (3) positively, the override's `services.api.environment` and `services.worker.environment`
set it to `synthetic-eval` (so the guard cannot pass on an empty world). Repo-wide scanning is what
covers `docker-compose.yml`, `.env.example`, `.github/workflows/*` and any future IaC without naming
them. Synthetic violating cases: a compose snippet, a `.env` line, a workflow `env:` block, and an ECS
task-definition JSON `{"name": "AGENT_TRACE_CONTENT_MODE", "value": "synthetic-eval"}`.

**What this does not cover (F1's residual — state it in `docs/CONFIGURATION.md`).** It is a
configuration guard. A person who sets the variable by hand on a real deployment — a shell export, a
`docker run -e`, an untracked `backend/.env`, a console-edited task definition — gets content export.
That is acceptable only because every ShiftMind environment runs seeded synthetic fixtures; the
hosted runtime is content-free by Story 6.3's clause.

### Decision 6 — The conversation-derived trace is set at the HTTP boundary, outside instrumentation (F2)

`api/tracing.py::TraceContextBoundary` is a plain ASGI wrapper installed **around the instrumented
middleware stack** (measured fact 6 — the only placement that works): after
`FastAPIInstrumentor.instrument_app(...)`, `install_api_tracing` replaces `app.build_middleware_stack`
with one returning `TraceContextBoundary(instrumented_stack)`. For every `http`/`websocket` scope it
removes `traceparent`, `tracestate` and `baggage`; for a path matching
`^/api/v1/conversations/(<uuid>)(/|$)` it appends `traceparent: 00-{uuid.hex}-{parent:016x}-01`, where
`parent` is the conversation UUID's low 64 bits (`or 1` if zero); a 36-character segment that does not
parse as a UUID gets no synthesized parent (an ordinary root trace). Measured with the prototype: the
`messages` request, the `execute` request, its `invoke_agent`/`chat`/`execute_tool` spans and the SSE
stream all share `trace_id == conversation_uuid.hex`; a hostile `traceparent` on
`/api/v1/scenarios` and `/health` produced fresh root traces.

The API's global propagator becomes **extract-only W3C trace context** (`inject` is a no-op, `fields`
empty, no baggage propagator). Measured fact 4: the default propagator sent `traceparent` and
pydantic-ai's `baggage` (including the conversation UUID) to the model provider; extract-only sent
neither. Set by `build_process_tracing` only when tracing is enabled.

**What this does not cover.** The derived parent span ID is never exported, so each request span has
a parent Logfire has not seen; the Task 17 smoke check confirms how Logfire renders it. The approval
decision route (`POST /api/v1/approvals/{approval_id}/decision`) resumes a paused agent run but is not
under `/conversations/…`, so the resumed run's spans land in the approval request's own trace —
joined back by `shiftmind.agent_run.id` and `shiftmind.conversation.id` (Decision 9), not by trace ID.
`POST /api/v1/conversations` (no ID yet) and `GET /api/v1/conversations?scenario_id=…` are ordinary
root traces.

### Decision 7 — Sampling and noise: roots, SSE polls, health checks, ASGI messages

`ShiftMindSampler` (in `spans.py`):

* **Root span** (no valid parent): sampled iff `kind == SERVER` or the name starts with `shiftmind.`;
  otherwise dropped. This is what removes the worker's idle-poll spans (fact 9: 0 exported, measured
  with the prototype), heartbeat-thread renewals, and any stray startup query.
* **Local parent**: a `CLIENT` span whose parent span's **name** is in `quiet_parent_span_names` is
  dropped — the API passes `{f"GET {t}" for t in _SSE_ROUTE_TEMPLATES}` (the two SSE routes). The
  predicate uses kind + parent name because the sampler sees **no** `db.*` attribute at statement-span
  start (fact 10). Otherwise the parent's sampled flag is followed.
* **Remote parent** (only ever the boundary's synthesized one): its sampled flag (`01`).

`install_api_tracing` also passes `exclude_spans=["receive", "send"]` and `excluded_urls="/health$"`
(the compose healthcheck calls `/health` every 2 s — 43,200 one-span traces a day otherwise).

Result for an SSE connection: **one** server span whose duration is the connection's lifetime (it ends
on the send after disconnect — up to the 15 s heartbeat), in the conversation trace, with no children.

**What this does not cover.** The SSE route's connection-setup work outside the poll (the `_head`
pre-flight) is also a `CLIENT` child of the SSE span and is dropped with the polls. A sampled-out span
is not recorded at all, so its duration is not visible anywhere. Heartbeat renewals during a long
solve are never traced (a `threading.Thread` inherits no context; propagating it would need an OTel
import in `application/`) — ledgered.

### Decision 8 — SQLAlchemy engines are traced per instance, at their three runtime construction sites

The global instrumentor cannot be used: it misses engines built through names bound before it runs
(fact 8 — `api/deps.py`'s alias) and it is a process singleton. `spans.trace_engine(engine, tracing)`
attaches `opentelemetry.instrumentation.sqlalchemy.engine.EngineTracer(tracer, engine,
connections_usage)` to one engine instance (tracer from the process provider under the scope name
`opentelemetry.instrumentation.sqlalchemy`; `connections_usage` from a `NoOpMeterProvider` — metrics
are out of scope), is idempotent per engine (a `WeakSet`), and is a no-op when `tracing is None`.
Measured with the prototype: statement spans appear, `connect` spans do not.

Call sites: `api/deps.py::_site_context_engine`; `api/deps.py::_identity_store`, which now builds the
engine itself (`create_postgres_engine(url, hide_parameters=True)`, traced) and injects it through
`PostgresIdentitySessionStore`'s existing `engine=` parameter — so `adapters/postgres/identity.py` is
**not** modified; and `worker/composition.py:17`. Each passes the process tracing it already holds
(`get_process_tracing()` in the API); none imports OpenTelemetry. `fixture_history.py`,
`seed_planner.py`, `bootstrap_local.py` and `migrations/env.py` are operator/bootstrap paths and are
not traced.

**What this does not cover.** An engine built anywhere else is untraced (none exists in a runtime
root). Both API engines are `lru_cache`d by URL, so an engine first built before tracing was installed
stays untraced — production installs at import, before any request; a test installing tracing on the
shared `app` must use its own throwaway database URL (the `postgres` fixtures already do). Per-row `INSERT` statements each become a span — **79 for one `sample_tiny_input` job** — which
is span volume, not a leak.

### Decision 9 — Correlation keys, and why `session.id` is not one of them

* **`shiftmind.agent_run.id`, `shiftmind.site.id`, `shiftmind.conversation.id` on `invoke_agent`**,
  set by a small pydantic-ai capability in `agent/runtime.py` whose `wrap_run` calls
  `opentelemetry.trace.get_current_span().set_attribute(...)` from the runtime's `AgentDepsV1` before
  `await handler()` — the pattern pydantic-ai's `Instrumentation` documents. Measured: the attribute
  lands on `invoke_agent` whichever list order the capabilities have. Added **only when a tracer
  provider is injected**, so the keyless agent is unchanged. It covers the execute route and the
  approval-resume route alike (both build the runtime from `deps`).
* **`shiftmind.schedule_run.id` on the enqueueing request** — `POST /api/v1/schedule-runs` is the only
  enqueue path (the agent's `scheduling_optimize` capability validates and never enqueues;
  `scheduling_optimize.py:34-38`). `api/routers/schedule_runs.py::start_schedule_run` calls
  `spans.annotate_enqueued_schedule_run(result.schedule_run_id)` after `enqueue_compute` returns, on
  the create and the idempotent-replay paths alike. It is not added to other run routes (their path
  already names the run).
* **`session.id` — not emitted.** ShiftMind's only session is the authentication session; any
  identifier of it links traces to a bearer credential's lifetime. No Logfire feature consumes it
  (Context7, 2026-09-24); conversation grouping is the trace ID.
* **`gen_ai.conversation.id` / `gen_ai.agent.call.id` stay pydantic-ai's per-run UUID7s** (measured).
  Passing ShiftMind's IDs into `run_sync(conversation_id=…, run_id=…)` was rejected: both are stamped
  onto the messages the run returns, `conversation_id` also selects OpenAI server-side conversation
  state (`models/openai.py`, `openai_conversation_id`), and pydantic-ai documents a `UserError` for a
  `run_id` already present on the history — changing how the agent is *called* is a behaviour change a
  tracing story has no reason to make. `shiftmind.conversation.id` is the key to search on.

**What this does not cover.** No actor/user identifier is exported (a person identifier, not needed
to diagnose timing). `shiftmind.site.id` is not put on HTTP spans (the session resolves after the
server span starts). Logfire views keyed on `gen_ai.conversation.id` show one value per run.

### Decision 10 — Worker spans live in adapters/worker only; API→worker stays two traces (F3)

`spans.py` provides a job scope used by `worker/lease_worker.py::run_once` and a scheduler wrapper used
by `worker/composition.py`; `application/use_cases/lease_and_execute_schedule_run.py` is unchanged.

* The scope's repository proxy delegates everything; its `lease_next_job` times the call and, **only
  when a lease is returned**, starts root `shiftmind.worker.execute` with `start_time` = the lease
  call's start, creates `shiftmind.worker.lease` retroactively as its child (`start_time`/`end_time` =
  the call), and attaches the execute span's context. `run_once` ends the span (setting
  `shiftmind.schedule_run.status` from the returned `LeaseOutcomeV1`) and detaches in a `finally`,
  exception or not.
* `traced_scheduler(factory, tracing)` returns a factory whose `solve(snapshot)` runs inside
  `shiftmind.worker.solve` and sets `shiftmind.solver.status` and `shiftmind.solver.wall_time_s` from
  the `SolverOutcomeV1`.

Measured with the prototype: **one trace per job**; execute root → lease (7.3 ms) and solve
(10.9 s) children; all 96 statement spans children of execute (the solver-input read under solve);
`shiftmind.schedule_run.id` identical to the enqueue span's. With `tracing is None` both helpers
return their inputs unchanged.

**What this does not cover.** The lease SQL itself is dropped as a root span (it runs before the root
exists); the retroactive lease span stands in for its timing. One continuous API→worker trace needs a
`job_queue.trace_context` migration and an application port — `deferred-work.md`'s F3 entry, unchanged.

### Decision 11 — Where each process builds, injects and flushes its tracing

* **API** — at **import**, at the end of `api/main.py` after `app.include_router(...)`:
  `build_process_tracing(get_settings(), service_name="shiftmind-api",
  quiet_parent_span_names=…)`; if not `None`, `install_api_tracing(app, tracing)` (FastAPI
  instrumentation, the outermost boundary, `HTTPXClientInstrumentor().instrument(tracer_provider=…)`),
  and `api.deps.set_process_tracing(tracing)`. Import time, not lifespan: measured fact 7. The
  lifespan's shutdown branch calls `tracing.shutdown()` (force-flush then provider shutdown) after
  `run_service.shutdown()`.
* **Agent runtime** — `api/deps.py` gains `get_process_tracing()` (process singleton, overridable);
  `get_agent_runtime_factory(tracing = Depends(get_process_tracing))` returns plain
  `create_agent_runtime` when tracing is `None`, else `functools.partial(create_agent_runtime,
  tracer_provider=tracing.provider)`. Both router call sites stay unchanged. `create_agent_runtime`
  gains `tracer_provider: object | None = None` and passes it with `trace_content =
  settings.agent_trace_content_mode == TRACE_CONTENT_SYNTHETIC_EVAL` to `PydanticAIAgentRuntime`,
  whose new keyword-only `trace_content: bool = False` feeds `include_content`. The global tracer
  provider is **never** set — every instrumentation receives the provider explicitly, so an
  un-wired library records nothing.
* **Worker** — `worker/composition.py::create_runtime()` builds `service_name="shiftmind-worker"`
  tracing, traces its engine, wraps the scheduler, and returns it on `WorkerRuntimeV1.tracing`
  (new, default `None`). `worker/main.py::main()` passes it through `run_worker_loop(…, tracing=…)` →
  `run_once(…, tracing=…)` and calls `tracing.shutdown()` in the existing `finally`, before
  `dispose()`. Compose's worker `stop_grace_period: 60s` and the API's default 10 s both exceed the
  5 s flush. The worker installs no httpx instrumentation: it makes no outbound HTTP call (the solve
  is in-process).

**What this does not cover.** `uvicorn --reload` and multi-worker servers build one provider per
process, which is correct. Tests that need an instrumented app call `install_api_tracing` on the
shared `app` and must call the returned undo (uninstrument FastAPI, restore `build_middleware_stack`,
reset `app.middleware_stack`, uninstrument httpx, restore the global textmap) in a `finally`.

### Decision 12 — Export can never block a request or a job

`BatchSpanProcessor(sanitizing_exporter, max_queue_size=2048, schedule_delay_millis=5000,
max_export_batch_size=512, export_timeout_millis=5000)`, explicit so `OTEL_BSP_*` cannot change them;
`OTLPSpanExporter(timeout=5)` (its retry loop stops at that deadline); `ProcessTracing.shutdown()` =
`force_flush(5000)` + `shutdown()`. `on_end` only enqueues; a full queue drops. Failures log through
the exporter's own `logging` calls, which 5.2's formatter renders as `third_party`.

Proof (AC5), each against the **real** `OTLPSpanExporter` class, three fixtures: **unreachable**
(`http://127.0.0.1:<port>` where the port was bound and closed), **slow** (a local server that sleeps
30 s), **rejected** (a local server answering 401). For each: a deterministic agent turn through the
API, an approval decision with its audit rows, and a worker job produce the same product outcome as
with tracing off; every request returns in under 2 s while the slow server holds the exporter
(synchronous export would take ≥ 5 s); `shutdown()` returns within 12 s (the 5 s force-flush wait plus
at most one in-flight export's 5 s deadline, plus margin); ending 5,000 spans against
the slow server takes under 1 s (queue drop, not block); the 401 path's captured JSON log stream holds
an ERROR line from the exporter's logger rendered as `"event": "third_party"` (5.2 Decision 4 drops
its message) and **not** the token canary. `test_authoritative_audit_survives_a_failing_span_exporter`
is extended to use this real pipeline (installed on the app, unreachable endpoint, non-vacuity via a
counting `requests.Session` passed as `session=`). Eval verdicts: the four pinned injection golden
cases and one grounding case evaluated through `evals.report._evaluate_case` with and without the
failing pipeline's provider on the runtime produce identical verdicts.

**What this does not cover.** Spans dropped on a full queue or a failed export are lost, not retried
later; the exporter's error log line every 5 s while Logfire is down is accepted noise.

### Decision 13 — Story 5.8's baseline stays comparable after the override edit

Measured fact 11. Adding the key changes `behavioral_digest` (5.8's rule includes a new key "by
default") and the override's sha256, which turns red
`test_committed_baseline_is_exactly_what_the_script_derives` (`derive_baseline` raises because the
working tree no longer matches the 5.7 `override_sha256`) and
`test_adding_behavioral_digest_left_configuration_digest_untouched` (an equality against a moving file
— a non-monotone rule per `EVIDENCE-CONVENTION.md`).

* `behavioral_environment` excludes a declared `TELEMETRY_ONLY_KEYS = frozenset({"AGENT_TRACE_CONTENT_MODE"})`
  beside the price-key suffix. Justification in the docstring: under AD-12 the key changes what the
  exporter receives, never what the model receives or the application does. So the current override's
  `behavioral_digest` equals the committed baseline's **by construction**, and every future live run
  still compares.
* `derive_live_conversation_baseline._baseline_behavioral_digest` reads the override **as measured**
  — `git show <measured_at_commit>:backend/evals/live_conversations/compose.override.yml` — verifies
  its LF-normalized sha256 equals the recorded `override_sha256`, and computes from that text
  (refactor `behavioral_environment` to accept text; keep the path form). Monotone: a committed blob
  never changes. Verify at Task 9 that the blob at `db0a5dd0` reproduces the recorded digest.
* `test_adding_behavioral_digest_left_configuration_digest_untouched` is retargeted to its monotone
  form: the blob at `measured_at_commit` reproduces `override_sha256` and `configuration_digest`; the
  current override's `behavioral_digest` equals the baseline's. `test_behavioral_digest_excludes_only_the_price_keys`
  asserts price keys **and** `TELEMETRY_ONLY_KEYS` are excluded; a new test proves adding/removing
  the content-mode key does not move the digest; `test_a_newly_added_environment_key_is_included_by_default`
  is unchanged.
* The live suite passes `LOGFIRE_TOKEN`/`LOGFIRE_BASE_URL` into the disposable stack: `suite.py` reads
  them from `backend/.env` with the existing `dotenv_values` pattern (`suite.py:69`) or the shell, and
  `stack.py::isolated_stack` merges them into the compose environment **only when given**;
  `docker-compose.yml`'s backend anchor gains `LOGFIRE_TOKEN: ${LOGFIRE_TOKEN:-}` and
  `LOGFIRE_BASE_URL: ${LOGFIRE_BASE_URL:-https://logfire-us.pydantic.dev}`. Neither value ever enters
  `measured_configuration`, a report or a log (test: canary absent from the report dict).

**What this does not cover.** Future live reports carry a different `configuration_digest` (the file
changed) — recorded, never compared (the drop check compares `behavioral_digest`). Story 5.10's "must
not touch the drop check" constraint binds 5.10, not this change, which alters only the exclusion set
and the source of one digest computation.

### Decision 14 — Evidence: what changes in 5.2's report, and a single-pass Gate A refresh

`backend/evals/content_minimization_report.py` changes:

* `channels`: C4 becomes "C4 exported agent spans"; add "C5 exported HTTP server spans", "C6 exported
  HTTP client spans", "C7 exported database spans", "C8 exported worker spans".
* `MATRIX_NODES`: 8 channels × 3 fixture classes = **24 distinct tests**; the machinery test's
  `len == 12` and channel tuple become 24 and c1–c8.
* `SURFACE_NODES` add: `export_content_mode_key_set`, `export_keyless_constructs_no_exporter`,
  `export_client_trace_context_discarded`, `export_agent_raw_key_drift`.
* new top-level `export_boundary` block: policy and boundary module paths, `content_modes`, default
  mode, `exception_events: "exception.type only"`, `status_description: "never exported"`,
  `url_query: "stripped"`, `sql_parameters: "placeholders only; status description dropped"`,
  `client_trace_context: "discarded on every route"`, `observed_at: "OTLP protobuf payload captured
  at the real OTLPSpanExporter"`.
* `artifact_versions` adds `span_export_policy` (`span_policy.py`) and `span_export_boundary`
  (`spans.py`), version `"1"`.
* `fixtures.secrets` lists the credential env var names from a generator constant
  `CREDENTIAL_ENV_VARS` (nine, including `LOGFIRE_TOKEN`) instead of the hard-coded "seven synthetic
  configuration canaries", which was already wrong (eight). The machinery test pins
  `set(CREDENTIAL_ENV_VARS) == set(CREDENTIAL_CANARIES)` from the suite, so the generator never
  imports a test module and the two cannot drift.

C4–C8 cells assert on **what the real exporter receives**: a `requests.Session` test double passed as
`session=` captures the OTLP request body; the cell decodes it with
`opentelemetry.proto.collector.trace.v1.trace_service_pb2.ExportTraceServiceRequest` and searches both
the raw bytes and the decoded names/attributes/events/status messages/resource. The C4 adversarial
cell's residual block (`test_content_minimization.py:444-460`) and its stale "Epic 6's exporter work"
comment are deleted; the cell now asserts the canary is absent from the **whole** exported payload.

Gate A: the registry does not change (still `content_minimization_evidence` +
`content_minimization_report_machinery`), but the registered machinery test file and the registered
evidence change, so the readiness report is regenerated **once** (Story 5.2's review precedent,
`5caad99`). Trap B's second pass arises only when the registry changes; it does not here.

**What this does not cover.** `artifact_versions` digests are still never re-verified
(`deferred-work.md` entry after `:696`, unchanged). The only other evidence binding a file this story
edits is `evidence/story-5.7/live-conversation-journeys.json` (`measured_configuration.override_sha256`
of the override) — deliberately left as the measured value; Decision 13 is what keeps it usable.

### Decision 15 — Ledger and docs

* `deferred-work.md:696` → **CLOSE** (events type-only, status description dropped, residual
  assertion deleted). `:717` → **CLOSE** (Decision 2). The F3 entry and `:663` → unchanged.
* New entries: (a) **pre-existing Story 5.1 defect, measured here**: for every routed request
  `route_template` lacks the `/api/v1` prefix (FastAPI 0.138's `scope["route"].path_format` is
  router-relative: observed `"/conversations/{conversation_id}/events"`), so `_SSE_ROUTE_TEMPLATES`
  never matches and SSE streams emit `api.request.completed`; no leak (still a template); owner open;
  (b) heartbeat renewals untraced (Decision 7); (c) `gen_ai.conversation.id` is pydantic-ai's per-run
  ID (Decision 9); (d) `OTEL_SEMCONV_STABILITY_OPT_IN` set to `http`/`database` would switch to
  stable-semconv keys that the allow-list default-denies — data loss, not a leak.
* Docs per Task 13. Do not touch `:669`, `:508`, `:639`.

---

## Tasks / Subtasks

- [x] **Task 1 — Start from a clean, re-verified baseline (all ACs)**
  - [x] If the 2026-09-24 planning edits (proposal, `epics.md`, spine, addendum, `deferred-work.md`,
        `sprint-status.yaml`) and this story are uncommitted, commit them as `docs(story-5.9): …`
        first — the evidence steps need a clean tree.
  - [x] Re-run the *Measured at creation* suites; record drift. Re-confirm the three facts most
        likely to move with a version bump: the old-semconv HTTP/DB keys (fact 5), the status
        description leaks (facts 1–2), and `instruction_parts` in `model_request_parameters` (fact 3).

- [x] **Task 2 — Dependencies (AC1) — per Decision 2**
  - [x] Edit `backend/pyproject.toml`; `uv lock`; confirm the 12-added/0-changed delta; `uv sync --frozen`.

- [x] **Task 3 — Settings and a keyless test process (AC1) — per Decision 3**
  - [x] `settings.py` fields, parsing and `TRACE_CONTENT_SYNTHETIC_EVAL`; tests in `test_settings.py`
        for defaults, empty token → `None`, invalid base URL / mode → `InvalidFlagError`.
  - [x] `conftest.py` pops the three variables; add `LOGFIRE_TOKEN` to `CREDENTIAL_CANARIES`.

- [x] **Task 4 — `adapters/telemetry/span_policy.py` (AC3, AC4) — per Decision 4 and the allow-list tables**
  - [x] Constants per category (`ALLOW`, `TRANSFORM`, `CONTENT_MODE`, `KNOWN_DROPPED`,
        `RESOURCE_ALLOW`, numeric/UUID key families) and pure functions (`categorize`,
        `sanitize_attributes`, `sanitize_event`, `sanitize_resource`, the four transforms).
  - [x] Unit tests in `tests/test_trace_export_boundary.py` built from the measured samples in the
        tables — one per transform, per event rule, per category's drop set.

- [x] **Task 5 — `adapters/telemetry/spans.py` (AC1, AC3, AC5) — per Decisions 3, 4, 6, 7, 8, 10, 12**
  - [x] `ProcessTracing`, `build_process_tracing`, `SanitizingSpanExporter`, `ShiftMindSampler`,
        extract-only propagator, explicit `Resource`, BSP bounds, `trace_engine`,
        `annotate_enqueued_schedule_run`, the worker job scope, `traced_scheduler`.

- [x] **Task 6 — API wiring (AC1, AC2) — per Decisions 6, 7, 8, 9, 11**
  - [x] `api/tracing.py` (`install_api_tracing` with undo, `TraceContextBoundary`).
  - [x] `api/main.py` import-time install + lifespan shutdown flush.
  - [x] `api/deps.py`: `get_process_tracing`, `set_process_tracing`, the factory partial, and
        `trace_engine` at `_site_context_engine` and at `_identity_store` (engine built and injected
        there; `adapters/postgres/identity.py` untouched — Decision 8).
  - [x] `api/routers/schedule_runs.py`: `annotate_enqueued_schedule_run` after `enqueue_compute`.

- [x] **Task 7 — Agent runtime (AC2, AC4) — per Decisions 5, 9, 11**
  - [x] `trace_content` keyword and the correlation capability (added only with a provider);
        `create_agent_runtime(tracer_provider=…)`. Update the comment at `agent/runtime.py:331-339`
        — it still says content export is "a deliberate future decision" and names Story 5.1.

- [x] **Task 8 — Worker (AC1, AC2, AC5) — per Decisions 8, 10, 11**
  - [x] `worker/composition.py`, `worker/main.py` (`WorkerRuntimeV1.tracing`, pass-through, flush in
        `finally`), `worker/lease_worker.py::run_once(…, tracing=None)`.

- [x] **Task 9 — Content mode config and Story 5.8 compatibility (AC4) — per Decisions 5 and 13**
  - [x] `compose.override.yml` (both services), `docker-compose.yml` passthrough, `.env.example`
        (commented `# LOGFIRE_TOKEN=` and `# LOGFIRE_BASE_URL=…`; content mode absent).
  - [x] `configuration.py` exclusion, `derive_live_conversation_baseline.py` blob read, the drop-check
        test edits, `suite.py`/`stack.py` token passthrough. Run `tests/test_live_conversation_*`.

- [x] **Task 10 — Architecture guards (AC1, AC3, AC4) — per Decisions 1, 4, 5**
  - [x] New `tests/architecture/test_trace_export_boundaries.py`: one-boundary import guard, `logfire`
        runtime ban plus a `pyproject.toml` check that `logfire` is not a runtime dependency and the
        five OTel pins are exact, the F1 content-mode guard, the SQL-literal guard — each with its
        synthetic violating cases.
  - [x] `test_agent_runtime_boundaries.py`: the three entries and the prefix-aware matcher (Decision 1).
  - [x] `test_telemetry_boundaries.py::test_telemetry_adapter_imports_no_framework`: the `spans.py`
        exemption, `opentelemetry` root only.

- [x] **Task 11 — Proof suites (AC2, AC3, AC4, AC5) — per Decisions 4, 6, 7, 9, 10, 12, 14**
  - [x] `tests/test_content_minimization.py`: import the allow-list; re-point C4 through the real
        exporter capture, including an off-mode case with a canary in `AgentRuntimeConfig.instructions`
        (proves `instruction_parts` never leaves); delete the C4 residual block and its stale comment;
        add C5–C8 × 3 cells. C5 may use dependency-overridden fakes; C6 a local stub server, and its
        cells also assert the stub received no `traceparent`/`baggage`; C7 a real engine (`postgres`
        marker); C8 fake repository/scheduler through the real job scope.
  - [x] The four surface nodes live in the same file — the machinery test requires every proof node to
        be a test declared there: `export_content_mode_key_set` (AC4: the content keys present, the
        credential canaries and exception text absent, `deployment.environment=live-eval`),
        `export_keyless_constructs_no_exporter` (AC1: no token → `build_process_tracing` returns `None`,
        `OTLPSpanExporter.__init__` is never called, `get_agent_runtime_factory()` is plain
        `create_agent_runtime`, `create_runtime().tracing is None`), `export_client_trace_context_discarded`
        (fake-backed app), `export_agent_raw_key_drift`.
  - [x] `tests/test_trace_request_path.py` (`postgres`): AC2 end to end — conversation trace ID on
        messages/execute/agent/SSE; hostile `traceparent` discarded on three route kinds;
        `invoke_agent` carries the three correlation keys; enqueue span and the worker job's spans
        share `shiftmind.schedule_run.id`; the SSE connection exports exactly one span; `/health`
        exports none; an idle `run_once` exports none.
  - [x] `tests/test_trace_export_failure_independence.py` and the extended approval-audit test (AC5).

- [x] **Task 12 — Evidence generator (AC6) — per Decision 14**
  - [x] `content_minimization_report.py` and `test_content_minimization_report.py` (24 cells,
        distinctness, existence, derived `fixtures.secrets`).

- [x] **Task 13 — Docs (AC1, AC4) — per Decisions 2, 3, 5, 13, 15**
  - [x] `docs/CONFIGURATION.md`: three rows, the region note, F1's residual verbatim in spirit.
  - [x] `docs/CI-SECRETS-CHECKLIST.md`: `LOGFIRE_TOKEN` under "must NOT be added"; a checklist line.
  - [x] `docs/TESTING.md`: live-suite trace export (token in `backend/.env`; what content mode
        exports) and where the new proof suites live.
  - [x] Spine Stack row: "pinned at Story 5.9" → the exact versions.

- [x] **Task 14 — Ledger and status — per Decision 15**
  - [x] Two closes, four new entries; this story's row in `sprint-status.yaml` only.

- [x] **Task 15 — Demonstrated-red mutation table (retro A1)** — minimum rows in *Dev Notes → Mutation
      table minimum*. Every new canary test must be shown red by removing the sanitizer rule it relies on.

- [ ] **Task 16 — Commit, measure, generate, commit — in this order (AC6) — per Decision 14**
  - [ ] Follow *Dev Notes → The commit plan* literally.

- [ ] **Task 17 — One real Logfire smoke check, at the end (AC1, AC2, AC4)**
  - [ ] Minh puts `LOGFIRE_TOKEN` (and `LOGFIRE_BASE_URL` if EU) in `backend/.env` himself — never in
        chat. Run API + worker locally (`uvicorn api.main:app`, `python -m worker.main`), one
        deterministic conversation turn, one optimization run, one SSE session. In Logfire confirm: one
        trace per conversation; `invoke_agent` searchable by `shiftmind.agent_run.id`; the enqueue span
        and the worker trace joined by `shiftmind.schedule_run.id`; no query strings, no exception
        text, no `db.user`/`net.peer.ip`; how the synthesized parent renders (Decision 6).
  - [ ] Then set `AGENT_TRACE_CONTENT_MODE=synthetic-eval` by hand for one turn (deterministic model —
        no provider spend) and confirm the content keys and `deployment.environment=live-eval`. Record
        observations in the Dev Agent Record; this is not evidence.

---

## Dev Notes

### Traps — the quietest first

1. **Adding a dotted name to `FORBIDDEN_ROOT_MODULES` changes nothing** unless the matcher changes
   (Decision 1). Prove it red with a synthetic `import opentelemetry.sdk`.
2. **Do not instrument in the lifespan** and do not add the boundary with `add_middleware` — both
   measured to silently fail (facts 6, 7).
3. **Do not call `SQLAlchemyInstrumentor().instrument()`** — global patch misses `api/deps.py`'s alias
   and is a singleton (fact 8). Use `trace_engine`.
4. **Do not set the global tracer provider.** Pass the provider explicitly (Decision 11). Story 5.1's
   failing-exporter test already warns that OTel allows one global per process.
5. **Assert on events and status, not attributes.** `span.attributes`-only checks passed while
   `exception.message` leaked (F4), and the status description is a third surface 5.2 never read.
   Assert on the captured OTLP payload.
6. **The sampler cannot see `db.*` at span start** (fact 10); an attribute predicate for the SSE rule
   passes review and drops nothing.
7. **Pop the token in `conftest.py` before anything imports `api.main`** — Task 17 puts a real token
   in `backend/.env`.
8. **Editing `compose.override.yml` without Decision 13 reddens two 5.8 tests** and breaks the live
   gate's comparability; do both in the same commit.
9. **Content mode is not "the server can never enable content"** (F1). The guard is the config-file
   test; the residual is documented, not engineered away.
10. **The 5.2 evidence must be committed before the Gate A three-runner pass** — a dirty 5.2 file
    skips the realism test and Gate A records "not proven".
11. **`logfire_api` is not `logfire`.** The locked `logfire-api` shim is pydantic-ai's no-op; the ban
    is on the `logfire` package.
12. **Never paste the token anywhere** — not in chat, a test, a fixture, a log assertion or a report.
    Tests use `CANARY-LOGFIRE-5-9`.

### Files being modified — read these before editing

| File | What it does today | What changes | What must be preserved |
|---|---|---|---|
| `backend/pyproject.toml` | `opentelemetry-sdk` and `httpx` dev-only | Decision 2 | every existing pin and the AR27 comments' intent |
| `backend/settings.py` | frozen `Settings`, `default_settings()` re-reads env per call | three fields (Decision 3) | every default; `InvalidFlagError` style; `repr=False` on all credentials |
| `backend/conftest.py` | pops `LLM_PROVIDER`/`LLM_MODEL` after importing `settings` | pops the three tracing vars | the live-key surfacing for `@pytest.mark.live` |
| `backend/agent/runtime.py` | two-arm `InstrumentationSettings(include_content=False, include_binary_content=False[, tracer_provider])` | `trace_content` feeds `include_content`; correlation capability with a provider | both arms and `include_binary_content=False` literal in both (5.2's AST test); `create_agent_runtime`'s existing kwargs |
| `backend/api/main.py` | lifespan (`configure_json_logging`, `db.init_db`, `run_service.shutdown`), three `@app.middleware`, CORS, `_SSE_ROUTE_TEMPLATES`, router includes | import-time install at the end; shutdown flush | middleware order and the 5.1 request-telemetry middleware; exception handlers |
| `backend/api/deps.py` | `get_agent_runtime_factory() -> create_agent_runtime`; `_site_context_engine` and `_identity_store` lru-cached per URL | tracing dependency, factory partial, `trace_engine` at both engines; `_identity_store` builds and injects its engine | `hide_parameters=True` at both (5.2's AST guard); the `site_context` transaction contract; every override seam |
| `backend/adapters/postgres/identity.py` | `engine or create_engine(url, hide_parameters=True)` | **nothing** — it already accepts `engine=` | — |
| `backend/api/routers/schedule_runs.py` | `start_schedule_run` enqueues, re-reads the view | one annotation call | problem mapping, idempotent replay semantics |
| `backend/worker/composition.py`, `worker/main.py`, `worker/lease_worker.py` | composition; loop with backoff; `run_once` | tracing field, pass-through, flush, job scope | backoff, `on_error` seam, signal-handler ordering, `dispose()` in `finally`, lease semantics |
| `backend/tests/test_content_minimization.py` | 16 tests, local allow-list, C4 residual block `:444-460` | Decision 14 | C1–C3 cells verbatim; `_sanitized_stream`; the settings repr sweep |
| `backend/evals/content_minimization_report.py` + its test | 12 cells, 4 surface nodes | Decision 14 | `_junit_outcome`, fail-closed timeout, no child output in failures, own-output exemption |
| `backend/tests/architecture/test_agent_runtime_boundaries.py`, `test_telemetry_boundaries.py` | AD-1 and adapter-framework guards | Decision 1 | every existing guard and synthetic case |
| `backend/evals/live_conversations/{configuration,suite,stack}.py`, `compose.override.yml`, `scripts/derive_live_conversation_baseline.py`, `tests/test_live_conversation_drop_check.py` | 5.8 digests and baseline | Decision 13 | the drop check's comparison logic; price-key exclusion; `configuration_digest`'s computation |
| `backend/tests/test_approval_governance_postgres.py` | `test_authoritative_audit_survives_a_failing_span_exporter` with a standalone raising provider | Decision 12 | every audit assertion |
| `docker-compose.yml`, `backend/.env.example` | backend env anchor | passthrough / commented lines | the `postgres` healthcheck verbatim (`ci.yml` depends on it) |

New files: `backend/adapters/telemetry/span_policy.py`, `backend/adapters/telemetry/spans.py`,
`backend/api/tracing.py`, `backend/tests/test_trace_export_boundary.py`,
`backend/tests/test_trace_request_path.py`, `backend/tests/test_trace_export_failure_independence.py`,
`backend/tests/architecture/test_trace_export_boundaries.py`.

### The commit plan — Task 16, in order

| # | Commit | Contents | State after |
|---|---|---|---|
| 0 | `docs(story-5.9): …` (only if Task 1 found them uncommitted) | the planning edits and this story | clean |
| 1 | `feat(story-5.9): trace the full request path behind one export boundary` | all code, tests, docs, compose files, ledger, `sprint-status.yaml` row | clean; suite green |
| — | *(measure)* on clean commit 1 | `uv run --frozen python -m evals.content_minimization_report` (Docker up — C7 is `postgres`-marked, and `skipped == 0` is required) | dirty by the 5.2 report only |
| 2 | `evidence(story-5.2): record the story 5.9 export boundary` | the 5.2 report only | clean |
| — | *(measure)* on clean commit 2 | `GATE-A-RUNBOOK.md` §3 three runners (streaming Playwright reporter on Windows), then `gate_a_readiness.py … --code-from ../evidence/story-5.2/content-minimization-report.json` | dirty by the readiness report only |
| 3 | `evidence(gate-a): refresh after story 5.9` | the readiness report only | clean; `gate_a_passed: true` |

Why this order: `--code-from` binds the readiness report to commit 1 — the code measured — because
commit 2 touches no code file and binding it would violate the convention; commit 2 must precede the
three-runner pass or the realism test skips (trap 10). Never `--allow-dirty`. One pass suffices
because the registry is unchanged.

### Mutation table minimum (Task 15)

Each row: mutate already-green code, run the named guard, record before/after, revert.

| Mutation | Guard that must redden |
|---|---|
| stop cutting `http.target` at `?` / keep `http.url` | C5 prompt-injection and adversarial cells |
| keep `exception.message` in events | C4/C7/C8 adversarial cells |
| keep the status description | C4 adversarial and C7 secrets cells |
| drop the `instruction_parts` transform | an off-mode test using a canary in the runtime's `instructions` |
| drop the message structure projection + force `include_content=True` in off mode | C4 prompt-injection cell |
| default propagator instead of extract-only | C6 outbound-header test |
| boundary via `add_middleware` | AC2 conversation-trace and hostile-`traceparent` tests |
| remove the SSE quiet-parent rule | SSE one-span test |
| remove the root rule | idle-`run_once` exports-nothing test |
| `SimpleSpanProcessor` instead of batch | AC5 slow-server latency test |
| remove the correlation capability | AC2 `shiftmind.agent_run.id` test |
| remove the enqueue annotation | AC2 schedule-run join test |
| construct the exporter without a token | AC1 keyless test |
| revert `FORBIDDEN_ROOT_MODULES` matcher to root-only | synthetic `import opentelemetry.sdk` case |
| remove `TELEMETRY_ONLY_KEYS` | drop-check digest-compatibility test |
| remove the `conftest.py` pop with a token set | keyless-test-process test |
| an f-string passed to `text()` (synthetic) | SQL-literal guard |
| two matrix cells on one test | machinery distinctness test |

### Testing requirements

* Run from `backend/`: `uv run --frozen pytest -q`; `addopts = -m "not live"` stays.
* Docker PostgreSQL 18 up; `postgres`-marked tests skip cleanly without it, which Gate A treats as not
  proven.
* Import `opentelemetry.sdk` hard, never `importorskip` (`test_agent_runtime_adapter.py:682`
  precedent).
* Every instrumented-app test restores global state in `finally` (Decision 11's undo; httpx
  uninstrument; textmap).
* `TestClient` is an `httpx.Client`: with httpx instrumented, each test request makes a root `CLIENT`
  span, which the root rule drops, and the extract-only propagator injects nothing — so test requests
  neither pollute the export nor set the trace ID. Do not "fix" this by excluding TestClient.
* No live provider, no real token, no Logfire subject in any test. Zero frontend tests change.
* New guards each carry a synthetic violating case, following `test_each_guard_detects_synthetic_violating_source`.

### Project structure notes

`adapters/telemetry/` is the declared home for telemetry adapters (AR26); this story is the first to
put OpenTelemetry there and does so in one module (`spans.py`), keeping `json_logs.py` framework-free.
`api/tracing.py` holds the only HTTP-specific tracing code. `application/` and `domain/` gain nothing.
`backend/evals/` keeps the report generator.

### References

* ACs, NFR3/4/10/15/22/26/27/30, AR1/AR26/AR27 — `_bmad-output/planning-artifacts/epics.md:79,81,93,103,117,125,127,133,1570-1608`
* F1–F5, §2.2, application notes — `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-24.md`
* AD-1, AD-12, Stack — `…/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:52,162,282-283`
* Addendum §2, §2.1, §6 — `…/prds/prd-ShiftMind-2026-07-21/addendum.md:53,60,149`
* Story 5.2 Decisions 6, 7, 9, 10 and its review findings — `_bmad-output/implementation-artifacts/5-2-prevent-content-and-secret-leaks.md`
* Story 5.1 Decisions 3, 4, 10 — `_bmad-output/implementation-artifacts/5-1-instrument-agent-runs-for-latency-budget-and-cost.md`
* Ledger — `_bmad-output/implementation-artifacts/deferred-work.md:663,696,701,717` and the F3 entry at the end
* Evidence rules, `--code-from`, realism test — `docs/EVIDENCE-CONVENTION.md`; `backend/scripts/gate_a_readiness.py:581-635`; `backend/tests/test_evidence_binding.py:56-63`
* Gate A regeneration — `docs/GATE-A-RUNBOOK.md` §3
* 5.8 digests — `backend/evals/live_conversations/configuration.py`; `backend/scripts/derive_live_conversation_baseline.py:136-151`; `backend/tests/test_live_conversation_drop_check.py:97-99,595-677`
* Logfire OTLP contract, environments, service attributes — Logfire docs via Context7 (`/websites/pydantic_dev_logfire`), 2026-09-24
* Domain model (cited per the standing rule; no metric touched) — `docs/DOMAIN-MODEL.md` §1–§3

---

## Dev Agent Record

### Agent Model Used

Claude Opus 5.5 (`claude-opus-5-5`), Claude Code, 2026-09-24.

### Debug Log References

- **Task 1 baseline, re-verified on 2960de0** (planning edits already committed): backend `2240 passed, 2 skipped, 10 deselected` with only the story/sprint-status status edits dirty (the second skip is the clean-tree realism test, as the story predicts). No drift. Facts 1-3 and 5 (status-description leaks, `instruction_parts`, old-semconv `http.url`/`http.target`) re-confirmed by demonstrated red: removing each sanitizer rule turns its canary cell red (mutations m01, m03, m04 below).
- **Task 2:** `uv lock` added exactly the 12 measured packages and changed 0 existing versions; `uv sync --frozen` clean.
- **Stop 1, resolved by Minh (option 1):** `tests/architecture/test_model_outage_boundaries.py::test_manual_solver_path_imports_no_telemetry_at_all` (Story 3.9, outside the file table) went red. The worker and the enqueue route necessarily reach `adapters/telemetry/spans.py` (AC1, Decisions 8-10). Amended to exempt that ONE module for the `opentelemetry` root only (never `logfire`), extracted `telemetry_imports_outside_boundary` with synthetic cases, and added a non-vacuity assertion that the boundary is reached. The "export cannot affect the path" property is now proven behaviourally by the AC5 suite.
- **Stop 2, resolved by Minh (option 1):** Decision 14's report records `content_modes: ["off", "synthetic-eval"]`, which the F1 guard (Decision 5) would flag once the evidence is committed. `evidence/**` added to F1's exclusions with its reason (generated measurement records, never configuration); the generator imports `TRACE_CONTENT_SYNTHETIC_EVAL` rather than spelling the literal.
- **Two bugs found by the new unit tests, fixed:** (1) the SDK builds a span's attributes FROM the `SamplingResult`, so a custom sampler returning `None` attributes silently dropped every start-time attribute -- `ShiftMindSampler` now hands them back; (2) content mode skipped the transforms of every category -- now only the agent's four, as specified.
- **Live-provider calls in my own tests, found and fixed before commit:** `backend/.env` selects a live `AGENT_RUNTIME_MODEL`, conftest does not pop it, and the two PostgreSQL end-to-end tests lift `ALLOW_MODEL_REQUESTS` for the deterministic model. Their first runs therefore made a handful of real OpenRouter calls. Both tests now pin `AGENT_RUNTIME_MODEL=deterministic`, drop `AGENT_RUNTIME_API_KEY`, and assert the setting before any request.
- **Regression outside the file table, fixed in product code:** `tests/test_worker_composition.py` builds the worker from a narrow `SimpleNamespace` settings stub; `build_process_tracing` reads the token with `getattr(..., None)` (the worker's existing narrow-stub convention, cf. `default_lease_seconds`). That test file is unchanged.
- **Measurement differs from the story in one place:** on a failing statement the SQLAlchemy engine tracer records the failure as a STATUS (description echoing the bound value) with no `exception` event. The C7 adversarial cell asserts the status is exported empty and that any event is type-only; m02 (keep `exception.message`) leaves C7 green for that reason, and m03 (keep the status description) turns it red.
- **Suite duration:** backend default suite 204 s -> about 424 s. Most of the added time is AC5's bounded-shutdown and slow-server cases (each waits up to the 5 s flush plus 5 s export deadline, by design) and three bootstrapped PostgreSQL end-to-end runs.

### Demonstrated-red mutation table

Each row mutated already-green code through a harness that ran the named guard before and after, then restored the original bytes. The tree's `git diff` hash was `515a2f9a...c6af` before and after the whole run: the tree was left exactly as found.

| # | Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|---|
| m01 | `strip_target_query` returns the value uncut; `http.url` added to the server allow-list | C5 prompt-injection + C5 adversarial | 2 passed | 2 failed |
| m02 | `sanitize_event` keeps every exception attribute | C4, C7 and C8 adversarial | 3 passed | 2 failed, 1 passed (C7: DB spans carry the failure in the status, not an event -- see m03) |
| m03 | exported status keeps its description (`status=span.status`) | C4 adversarial + C7 secrets | 2 passed | 2 failed |
| m04 | `remove_instruction_parts` no longer pops `instruction_parts` | `test_c4_off_mode_never_exports_the_runtime_instructions` | 1 passed | 1 failed |
| m05 | message projection returns the raw value AND `include_content=True` forced in off mode | C4 prompt-injection | 1 passed | 1 failed |
| m06 | extract-only propagator not installed (default W3C + baggage) | C6 secrets (stub must receive no `traceparent`/`baggage`) | 1 passed | 1 failed |
| m07 | boundary added with `app.add_middleware(TraceContextBoundary)` | `test_export_client_trace_context_discarded` + `test_trace_request_path.py` | 2 passed | 2 failed |
| m08 | SSE quiet-parent sampler rule disabled | `test_trace_request_path.py` (SSE exports one span) | 1 passed | 1 failed |
| m09 | sampler root rule removed (`sampled = True`) | `test_trace_request_path.py` (idle `run_once` exports nothing) | 1 passed | 1 failed |
| m10 | `SimpleSpanProcessor` instead of `BatchSpanProcessor` | `test_requests_never_wait_for_the_exporter[slow]` | 1 passed | 1 failed |
| m11 | run-correlation capability removed | `test_trace_request_path.py` (`shiftmind.agent_run.id`) | 1 passed | 1 failed |
| m12 | enqueue annotation removed | `test_trace_request_path.py` (schedule-run join) | 1 passed | 1 failed |
| m13 | exporter constructed without a token | `test_export_keyless_constructs_no_exporter` + `test_keyless_settings_construct_nothing` | 2 passed | 2 failed |
| m14 | AD-1 matcher reverted to root-only | `test_import_guard_actually_fails_on_a_violating_import` (synthetic `import opentelemetry.sdk.trace`) | 1 passed | 1 failed |
| m15 | `TELEMETRY_ONLY_KEYS = frozenset()` | drop-check digest-compatibility test (+ baseline derivation) | 2 passed | 1 failed, 1 passed (derivation reads the committed blob, which never had the key -- by design) |
| m16 | conftest's three pops removed, run with `LOGFIRE_TOKEN` set (base URL a closed local port, so nothing left the machine) | `test_the_test_process_has_no_process_tracing` | 1 passed | 1 failed |
| m17 | `text(f"...")` in `worker/lease_worker.py` | `test_sql_passed_to_sqlalchemy_is_always_a_literal` | 1 passed | 1 failed |
| m18 | two matrix cells pointed at one test | `test_proof_matrix_is_attributable_to_channel_and_fixture_class` | 1 passed | 1 failed |
| m19 | `from opentelemetry import trace` in `worker/lease_worker.py` | one-boundary guard + amended Story 3.9 manual-path guard | 2 passed | 2 failed |
| m20 | `AGENT_TRACE_CONTENT_MODE: synthetic-eval` added to `docker-compose.yml` | F1 content-mode guard | 1 passed | 1 failed |
| m21 | `logfire.msg` removed from the agent table | `test_export_agent_raw_key_drift` | 1 passed | 1 failed |
| m22 | OpenTelemetry imported by `adapters/telemetry/json_logs.py` | `test_telemetry_adapter_imports_no_framework` (exemption is `spans.py` only) | 1 passed | 1 failed |

### Completion Notes List

- One export boundary: the policy is production data in `adapters/telemetry/span_policy.py` (stdlib only, default-deny, per-category tables as measured), applied by `SanitizingSpanExporter` in `adapters/telemetry/spans.py`, the only SDK/exporter importer besides `api/tracing.py`. Events keep `exception.type` only; status descriptions, links and scope attributes never leave; the resource is rebuilt from its allow-list. A sanitization error fails the batch; it never raises or exports unsanitized.
- Keyless is literal: no token -> `build_process_tracing` returns `None` and constructs nothing; the global tracer provider is never set; the test process pops all three variables.
- API: instrumented at import (not in the lifespan) with `exclude_spans=["receive","send"]` and `/health` excluded; `TraceContextBoundary` wraps the instrumented stack, drops client `traceparent`/`tracestate`/`baggage` on every route and synthesizes the conversation-derived parent; extract-only propagator, so nothing is injected into provider requests. Engines are traced per instance at the three runtime sites; `adapters/postgres/identity.py` is untouched.
- Agent: `trace_content` feeds `include_content`; the `_RunCorrelation` capability (only with a provider) stamps `shiftmind.agent_run.id`/`site.id`/`conversation.id` on `invoke_agent`.
- Worker: one trace per leased job (`shiftmind.worker.execute` -> retroactive `lease`, `solve`); idle polls export nothing; flush in `main()`'s `finally` before `dispose()`.
- Story 5.8 kept comparable: `TELEMETRY_ONLY_KEYS`, blob-based baseline digest (the blob at `db0a5dd0` reproduces the recorded `override_sha256`), monotone retargeted test; the live suite passes the token into the disposable stack only when given.
- Proofs: a 24-cell matrix (C1-C8 x 3), four export surface nodes, the AC2 end-to-end test on bootstrapped PostgreSQL, the AC5 suite against unreachable/slow/401 exporters (plus the approval-audit test now on the real pipeline), and new architecture guards with synthetic cases. Backend default suite before commit: **2339 passed, 2 skipped, 10 deselected**. Zero frontend diff, so Vitest was not re-run.
- Ledger: `:696` and `:717` closed; four entries added (route_template prefix defect, heartbeat untraced, per-run `gen_ai.conversation.id`, stable-semconv opt-in).

### File List

New: `backend/adapters/telemetry/span_policy.py`, `backend/adapters/telemetry/spans.py`, `backend/api/tracing.py`, `backend/tests/trace_capture.py`, `backend/tests/test_trace_export_boundary.py`, `backend/tests/test_trace_request_path.py`, `backend/tests/test_trace_export_failure_independence.py`, `backend/tests/architecture/test_trace_export_boundaries.py`.

Modified: `backend/pyproject.toml`, `backend/uv.lock`, `backend/settings.py`, `backend/conftest.py`, `backend/.env.example`, `backend/agent/runtime.py`, `backend/api/main.py`, `backend/api/deps.py`, `backend/api/routers/schedule_runs.py`, `backend/worker/composition.py`, `backend/worker/main.py`, `backend/worker/lease_worker.py`, `backend/evals/content_minimization_report.py`, `backend/evals/live_conversations/compose.override.yml`, `backend/evals/live_conversations/configuration.py`, `backend/evals/live_conversations/stack.py`, `backend/evals/live_conversations/suite.py`, `backend/scripts/derive_live_conversation_baseline.py`, `backend/tests/test_content_minimization.py`, `backend/tests/test_content_minimization_report.py`, `backend/tests/test_settings.py`, `backend/tests/test_live_conversation_drop_check.py`, `backend/tests/test_live_conversation_stack.py`, `backend/tests/test_approval_governance_postgres.py`, `backend/tests/test_agent_runtime_adapter.py` (comment), `backend/tests/architecture/test_agent_runtime_boundaries.py`, `backend/tests/architecture/test_telemetry_boundaries.py`, `backend/tests/architecture/test_model_outage_boundaries.py` (Stop 1), `backend/tests/architecture/test_local_composition.py` (comment), `docker-compose.yml`, `docs/CONFIGURATION.md`, `docs/CI-SECRETS-CHECKLIST.md`, `docs/TESTING.md`, `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`, `_bmad-output/implementation-artifacts/deferred-work.md`, `_bmad-output/implementation-artifacts/sprint-status.yaml`, this story file.

Evidence (separate commits, Task 16): `evidence/story-5.2/content-minimization-report.json`, `evidence/story-1.11/gate-a-readiness-report.json`.

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-24 | Story created at `67584d5`. Allow-list measured, not written from docs: a throwaway harness drove eight channels against the real app and Docker PostgreSQL with the exact pins. Eleven measured facts shaped fifteen decisions, including three leak channels Story 5.2 never read (status descriptions on agent and DB spans; `instruction_parts` in default mode; outbound `baggage`), four placements that silently fail (lifespan instrumentation, `add_middleware`, `context.attach`, the global SQLAlchemy instrumentor), and a collision with Story 5.8's baseline that the AC4 file choice causes. Baseline: backend 2240 passed / 2 skipped / 10 deselected; Vitest 648 / 85 files. |
| 2026-09-24 | Implemented (dev-story). Two stops resolved with Minh: Story 3.9 manual-path telemetry guard exempts only the export boundary; F1 excludes evidence/. 22-row demonstrated-red mutation table; backend 2339 passed / 2 skipped pre-commit. |
