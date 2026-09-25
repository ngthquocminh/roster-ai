# Sprint Change Proposal — Full-stack tracing to Logfire and live-eval results in Logfire

Date: 2026-09-24
Author: Developer agent, with Minh
Mode: Batch
Trigger: stakeholder request (Minh, 2026-09-24). It started as "integrate our agent with Langfuse". After comparing Langfuse, Logfire and LangSmith, Minh chose **Logfire**, with full-stack tracing in one story.
Status: **Approved by Minh 2026-09-24. Artifact edits §4.1–§4.6 applied the same day, with two recorded deviations (see "Application notes" at the end). Stories 5.9 and 5.10 handed to `bmad-create-story`.**

## 1. Issue summary

**Type:** new requirement from the stakeholder. It implements an observability slot the architecture already reserves (AD-12, "sanitized OpenTelemetry/Logfire owns optional AI traces") but no story ever built.

**Today:**
- The agent emits OpenTelemetry GenAI spans. `PydanticAIAgentRuntime` registers PydanticAI's `Instrumentation` with `include_content=False, include_binary_content=False` (`backend/agent/runtime.py:340-348`).
- **Nothing exports them.** `create_agent_runtime` (`agent/runtime.py:1009`, called only from `api/deps.py:123`) passes no `tracer_provider`.
- The API, the database and the worker/solver emit no spans at all.
- The Stack table's `Logfire SDK 4.38.0` row has been `planned` since 2026-07-22. Story 5.1 Decision 10 moved it to 5.2, and 5.2 Decision 11 left it unshipped.

### 1.1 Decisions taken with Minh on 2026-09-24

| # | Decision | Chosen | Why |
|---|---|---|---|
| D1 | Backend | **Logfire** (not Langfuse or LangSmith) | Already the architecture's planned tool, so PRD/architecture churn is minimal. One backend covers agent, API, database and worker. Datasets/Experiments via pydantic-evals, plus annotation queues. Langfuse's native sessions and scores are approximated by F2 (one trace per conversation) and Story 5.10 (verdict spans in that trace, plus experiments). |
| D2 | Content | **Opt-in eval mode.** Content-free by default everywhere. `AGENT_TRACE_CONTENT_MODE=synthetic-eval`, set only by the disposable live-eval stack running seeded synthetic fixtures, exports prompts, completions and tool I/O. | Debugging live conversations needs the text; NFR30 allows "explicitly configured" content. |
| D3 | Story shape | **All full-stack tracing in one story (5.9).** Eval results in a separate small story (5.10). | Every span type passes through one export filter. Deciding its allow-list once is cheaper than widening it later, since each widening means another 5.2-style privacy review and evidence regeneration. |
| — | Prompt management | **Not adopted.** | A runtime prompt fetch would violate AD-12 and decouple agent behavior from `git_commit`, which the evidence convention and the 5.8 baseline rely on. |

### 1.2 Design points settled by analysis (not open decisions)

- **Standard OTel SDK in the server, not the Logfire SDK.** Logfire accepts plain OTLP: `https://logfire-{us|eu}.pydantic.dev/v1/traces`, header `Authorization: <write token>`, `http/protobuf` (Logfire docs via Context7, 2026-09-24). The Logfire SDK's scrubbing is a **deny-list** (`ScrubbingOptions`), but Story 5.2 and addendum §6 require an **allow-list** applied before export. That needs our own sanitizing exporter wrapper, which works only around a standard `OTLPSpanExporter`. Auto-instrumentation uses the standard `opentelemetry-instrumentation-{fastapi,sqlalchemy,httpx}` packages; Logfire's `instrument_*` helpers wrap the same packages. The Logfire SDK and `pydantic-evals` enter only in **eval tooling** (5.10, dev group), where `logfire.configure()` is what makes an experiment appear on Logfire's Experiments page.
- **Keyless by default.** Without `LOGFIRE_TOKEN`, no exporter is constructed. CI stays keyless.

### 1.3 Load-bearing findings, made now rather than at review

**F1 — Eval content is produced inside an API process.** The live-conversation suite (5.7/5.8) drives a **disposable API container** over HTTP (`evals/live_conversations/stack.py:19-45`). "The server can never enable content" and "live-eval traces carry content" therefore contradict each other. The guard has to be:
- **Structural:** an architecture test proves the only tracked file that sets a non-`off` content mode is `evals/live_conversations/compose.override.yml`. The check also covers `docker-compose.yml`, `.env.example`, CI workflows and future IaC.
- **Runtime:** in content mode the resource carries `deployment.environment=live-eval`, so those traces are separable in Logfire.
- **Stated residual:** it's a configuration guard. A person who sets the variable by hand on a real deployment gets content export. That's acceptable only because every environment runs seeded synthetic fixtures, and `docs/CONFIGURATION.md` must say so.

**F2 — "One trace per conversation" must be set at the HTTP boundary, not in the agent runtime.** Agent turns execute **inside** the HTTP request (`POST /conversations/{id}/agent-runs/{id}/execute`, `api/routers/conversations.py:243`). Once FastAPI is instrumented, the `invoke_agent` span is a child of the request span. Re-parenting it onto a conversation trace ID in the runtime would **detach it from its own request**, so the request would show no agent work and the agent span would have no request.
- **Correct placement:** a small ASGI middleware, installed outside the FastAPI instrumentation, runs on routes under `/conversations/{conversation_id}/…`. It **replaces** the incoming trace context with a remote parent whose `trace_id = conversation_uuid.int`. Conversation IDs are UUIDs, exactly 128 bits.
- **Result:** every turn's request, agent, tool, model and database spans, plus the conversation's SSE stream, land in **one trace per conversation**. Logfire's own Codex exporter uses this pattern ("spans for the same conversation share a stable trace ID derived from conversation metadata").
- **Security:** the same middleware discards any client-supplied `traceparent` on **all** routes. An untrusted browser must not choose trace IDs.

**F3 — One continuous API→worker trace needs a migration, so it's out of scope.** Solves run in the worker off the `job_queue` table, which has no trace-context column (`adapters/postgres/schema.py:523`). Continuing the API trace in the worker would need an additive migration plus a new application port, because AD-1 forbids OTel imports in `application/`.
- **Instead:** worker spans (lease, execute, CP-SAT solve) carry `shiftmind.schedule_run.id`, the same attribute the enqueueing request's span carries. You get two traces joined by attribute in Logfire SQL.
- **Deferred trigger recorded** in §4.6.

**F4 — The span allow-list is only a test constant today.** `SPAN_ATTRIBUTE_ALLOW_LIST` lives in `tests/test_content_minimization.py:46`, and 5.2 records "no allow-list is enforced at an export boundary". **Exception text leaks through span events** (`deferred-work.md:696`, whose owner/trigger is "the first real exporter (Logfire/OTLP)"). That is this change, so 5.9 inherits it.

**F5 — Traces carry no agent-run ID.** 5.2's measured key list has `gen_ai.conversation.id` but no run ID, so NFR22's "searchable … across … available traces" is unmet for traces today. 5.9 closes it.

### 1.4 Evidence

| Fact | Where |
|---|---|
| Spans emitted, never exported | `agent/runtime.py:308,340-348,1035-1041` |
| Span content today: structure only (5.2 measurement) | `gen_ai.input.messages = [{"role":"user","parts":[{"type":"text"}]}]`; 23 keys (`5-2-…md:143-144`) |
| Agent turn runs inside the HTTP request | `api/routers/conversations.py:238-260` |
| Four SQLAlchemy engine sites, all `hide_parameters=True` | `worker/composition.py:17`, `adapters/postgres/fixture_history.py:54`, `adapters/postgres/identity.py:35`, plus the API engine (5.2 Decision "four engine sites") |
| `job_queue` has no trace-context column | `adapters/postgres/schema.py:523-560` |
| Live-eval report carries `conversation_id` and per-turn verdicts | `evals/live_conversations/runner.py:153,322` |
| Pydantic Evals is not used anywhere today | `pydantic_evals` appears only in the forbidden-import list (`tests/architecture/test_agent_runtime_boundaries.py`) |
| Logfire Experiments page needs `logfire.configure()` in the eval process | Logfire docs, "evals-in-code" |

## 2. Impact analysis

### 2.1 Checklist results

| Item | Status | Finding |
|---|---|---|
| 1.1 Trigger | [x] | Stakeholder request; no story is blocked. |
| 1.2 Problem | [x] | New requirement: export sanitized full-stack traces to Logfire and give live-eval results a browsable home. |
| 1.3 Evidence | [x] | §1.4 |
| 2.1 Current epic (5) | [x] | Epic 5 is `in-progress` (Gate B re-opened 2026-09-10). This is **not** a Gate B obligation and changes no Gate B criterion. |
| 2.2 Epic-level change | [x] | Add Stories 5.9 and 5.10. No existing story's acceptance changes. |
| 2.3 Future epics | [!] | Story 6.3 gains one clause (hosted = content-free, token from Secrets Manager). Epic 6's "sanitized hosted Logfire" wording becomes true instead of aspirational. |
| 2.4 Obsolete / new epics | [N/A] | None. |
| 2.5 Order | [x] | 5.9 → 5.10. Independent of the Gate B dataset-floor decision and of Epic 6. |
| 3.1 PRD | [!] | Small: addendum §2 caveat, §6 authorizes the diagnostic mode, §2.1 names pydantic-evals as the eval path. NFR3/NFR4/NFR30 are unchanged; NFR30's "explicitly configured" already allows D2. |
| 3.2 Architecture | [!] | Small: AD-12 gains the export-boundary sentence; AD-1 enforcement list grows; Stack row changes from `planned` to its real shape. No invariant weakens. |
| 3.3 UX | [N/A] | Zero frontend diff. Browser-side tracing is explicitly out of scope. |
| 3.4 Other artifacts | [!] | `pyproject.toml`, `settings.py`, `api/main.py` (middleware and instrumentation), `worker/composition.py`, `docs/CONFIGURATION.md`, `docs/TESTING.md`, `.env.example`, `compose.override.yml`, 5.2's evidence file (regenerated), `deferred-work.md:696` (closed by 5.9). |

### 2.2 Technical impact

- **Dependencies (AR27, and 5.9 is the implementation gate):**
  - **Runtime:** promote `opentelemetry-sdk` from dev to runtime; add `opentelemetry-exporter-otlp-proto-http` and `opentelemetry-instrumentation-{fastapi,sqlalchemy,httpx}`.
  - **Eval-only (dev group, 5.10):** `logfire` and `pydantic-evals`.
  - Exact pins are decided at story creation, checked against PyPI and the `opentelemetry-api` that `pydantic-ai-slim==2.27.0` resolves.
- **Composition:** one tracer provider per process (`service.name` = `shiftmind-api` / `shiftmind-worker`), built in a new `adapters/telemetry/spans.py` and passed into `create_agent_runtime`. It is force-flushed on API lifespan shutdown and on worker exit. A disposable live-eval container is torn down after every conversation, so a missing flush loses its traces silently.
- **Export filter, the core of 5.9 (AD-12, F4).** A sanitizing wrapper around the exporter, applied to **every** span type:
  - forwards only allow-listed attribute keys. The allow-list becomes a production constant covering agent, `http.*`, `db.*` and worker keys; 5.2's test imports it.
  - strips URL query strings;
  - handles `db.statement` explicitly (SQL text with placeholders, never parameter values);
  - records `exception` events by type only, in **both** content modes.

  Content mode widens only the named `gen_ai` content keys. Credentials and exception text are never exported.
- **AD-12 failure independence:** exporter failure, timeout or a 401 changes no product outcome, audit row, eval verdict or gate. Extend `…survives_a_failing_span_exporter` to the real exporter class pointed at an unreachable endpoint.
- **Eval results stay outside the evidence chain (5.10):** post-hoc tooling reads a *finished* report. The report schema, `configuration_digest`, the 5.8 drop check and all evidence files are untouched and never read back from Logfire.

## 3. Recommended approach

**Direct Adjustment:** two additive stories in Epic 5, plus small PRD/architecture text edits and one Epic 6 clause.

| | 5.9 Full-stack tracing | 5.10 Eval results |
|---|---|---|
| Effort | **Large but one coherent boundary.** Exporter and filter, content mode and guard, F2 middleware, auto-instrumentation (API/DB/httpx), worker spans, 5.2 evidence regeneration | Low to medium. Verdict spans plus a pydantic-evals replay script |
| Risk | **Medium-high.** First data leaving the machine; widens 5.2's proven boundary to new span types | Low. Post-hoc, eval-only dependencies, no product path |
| Mitigation | Settle the full allow-list (every new key, per span type) **at story creation** by measuring real spans, so it isn't discovered at code review | — |

Rollback and MVP review: N/A. Gate B is unaffected.

## 4. Detailed change proposals

### 4.1 PRD addendum — `prds/prd-ShiftMind-2026-07-21/addendum.md`

**§2 table row "Agent observability"**
```
OLD: | Agent observability | Hosted Logfire Personal through OpenTelemetry | Optional for correctness; disable prompt/tool content capture by default |
NEW: | Agent observability | Hosted Logfire through standard OpenTelemetry (OTLP), full request path: API, database, agent, worker | Optional for correctness; content-free by default behind an export-boundary allow-list; content only in the authorized synthetic-eval mode (§6) |
```

**§2.1, append one sentence:** `ShiftMind exports with the standard OpenTelemetry SDK and its own export-boundary sanitizer rather than the Logfire SDK, so the allow-list is enforced before data leaves the process; the Logfire SDK and Pydantic Evals are used only by evaluation tooling to publish live-evaluation results as Logfire experiments.`

**§6 paragraph (line 149)**
```
OLD: Logfire must use PydanticAI instrumentation with content and binary capture disabled by default. Export only allow-listed attributes and scrub as defense in depth. Never export credentials, raw workforce data, full prompts/completions, schedule payloads, tool arguments/results, or approval evidence unless a specific safe diagnostic mode is authorized.
NEW: Logfire export must use PydanticAI instrumentation with content and binary capture disabled by default, and an export-boundary sanitizer that forwards only allow-listed attributes for every span type (agent, HTTP, database, worker), strips URL query strings, never exports SQL parameter values, and records exceptions by type only. Never export credentials, raw workforce data, full prompts/completions, schedule payloads, tool arguments/results, or approval evidence, except in the one authorized diagnostic mode: `AGENT_TRACE_CONTENT_MODE=synthetic-eval`, set only by the disposable live-evaluation stack running seeded synthetic fixtures and tagged `deployment.environment=live-eval`. Credentials and exception text are withheld in every mode. Client-supplied trace context is never trusted.
```

*PRD body (`prd.md`) is unchanged. NFR3/NFR4/NFR30 are unchanged.*

### 4.2 Architecture spine — `architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`

**AD-1 enforcement (not rule text):** add `opentelemetry.sdk`, `opentelemetry.exporter` and `opentelemetry.instrumentation` to `FORBIDDEN_ROOT_MODULES` (`tests/architecture/test_agent_runtime_boundaries.py:53`). `logfire` is already listed. The rule text already names Logfire, so no text edit is needed.

**AD-12 Rule (line 162), final sentences**
```
OLD: CloudWatch owns AWS diagnosis; sanitized OpenTelemetry/Logfire owns optional AI traces; version-controlled datasets/reports own evaluation. No telemetry system authorizes or blocks product work.
NEW: CloudWatch owns AWS diagnosis; sanitized OpenTelemetry exported to Logfire owns optional request-path and AI traces and non-authoritative live-evaluation experiment review; version-controlled datasets/reports and the committed evaluation baseline own evaluation. Every exported span passes an export-boundary sanitizer (attribute allow-list, exception type only); client trace context is discarded and conversation-scoped requests share one conversation-derived trace. No telemetry system authorizes or blocks product work.
```

**Stack table (line 282)**
```
OLD: | Logfire SDK | 4.38.0 | planned optional telemetry seed |
NEW: | OpenTelemetry SDK + OTLP/HTTP exporter + FastAPI/SQLAlchemy/httpx instrumentation → hosted Logfire | pinned at Story 5.9 | runtime trace export behind the ShiftMind sanitizer |
     | Logfire SDK + pydantic-evals | pinned at Story 5.10 | dev/eval tooling only; never imported by api, worker, agent, application or domain |
```

Deployment rule (line 194) and container diagram (line 383) already say "hosted Logfire" / "sanitized OTLP": **no edit.**

### 4.3 Epics — `epics.md`

**Insert after Story 5.7:**

> ### Story 5.9: Trace the Full Request Path to Logfire Behind One Export Boundary
>
> As a portfolio operator,
> I want each conversation's HTTP, agent, model, tool, and database work — and each solver job — traced in Logfire behind an enforced export boundary,
> So that I can see where a request spent its time and tokens without widening what leaves the application.
>
> **Acceptance Criteria:**
>
> **Given** `LOGFIRE_TOKEN` (and region base URL) is configured
> **When** the API and worker run
> **Then** FastAPI request, SQLAlchemy, outbound httpx, PydanticAI agent/model/tool spans, and worker lease/execute/solve spans are exported over OTLP to Logfire under `service.name` `shiftmind-api`/`shiftmind-worker`
> **And** with the token absent no exporter is constructed and behavior is identical to today. (NFR15, AR27)
>
> **Given** requests under `/conversations/{conversation_id}/…`
> **When** they are traced
> **Then** every turn's request, agent, and database spans share one trace whose ID is derived from the conversation UUID, the agent root span carries `shiftmind.agent_run.id`, and worker spans carry `shiftmind.schedule_run.id` shared with the enqueueing request
> **And** client-supplied trace context is discarded on every route. (NFR22)
>
> **Given** the default content mode
> **When** any span leaves the process
> **Then** an export-boundary sanitizer forwards only allow-listed keys for every span type, strips URL query strings, never exports SQL parameter values, and records exception events by type only
> **And** 5.2's secret, prompt-injection, and adversarial fixtures are absent from what the real exporter receives, including span events, HTTP, and database spans (closes `deferred-work.md:696`). (NFR3, NFR4, NFR30, AD-12)
>
> **Given** `AGENT_TRACE_CONTENT_MODE=synthetic-eval`
> **When** the live-evaluation stack runs
> **Then** prompts, completions, and tool arguments/results are exported with `deployment.environment=live-eval`, while credentials and exception text are still withheld
> **And** an architecture test proves the only tracked file setting a non-`off` mode is `evals/live_conversations/compose.override.yml`. (NFR30)
>
> **Given** Logfire is unreachable, slow, or rejects the token
> **When** agent runs, approvals, and solver work proceed
> **Then** product state, authoritative audit, and eval verdicts are unchanged and export never blocks a request or a job. (AD-12, NFR10)
>
> **Given** the proof suite changes
> **When** evidence is regenerated per `docs/EVIDENCE-CONVENTION.md`
> **Then** `evidence/story-5.2/content-minimization-report.json` records the export boundary and the new span channels as tested. (NFR27)
>
> **Out of scope, deliberately.** One continuous API→worker trace (needs a `job_queue` migration and an application port; deferred trigger in §4.6), browser/frontend tracing, OTel metrics or log export (`deferred-work.md:663` stays with Epic 6), the Logfire SDK in any runtime process, and prompt management.

> ### Story 5.10: Publish Live-Evaluation Results to Logfire
>
> As an AI engineer comparing models and runs,
> I want live-conversation verdicts shown inside each conversation's trace and each suite run shown as a Logfire experiment,
> So that I can open a failing turn's trace from its verdict and compare runs side by side.
>
> **Acceptance Criteria:**
>
> **Given** a finished live-suite report (the Story 5.7 format) and `LOGFIRE_TOKEN`
> **When** the publisher runs
> **Then** one `live_eval.verdict` span per turn is written into that conversation's trace (trace ID derived from `conversation_id`), carrying turn index, verdict, agent model, `configuration_digest`, and report identity
> **And** the report is replayed into a pydantic-evals `Dataset`, where the task returns recorded output and evaluators return recorded verdicts with nothing re-executed, so the run appears on Logfire's Experiments page named by report identity and model.
>
> **Given** Logfire is unavailable or the token is absent
> **When** the publisher runs
> **Then** it exits non-zero with a closed-vocabulary reason, and the report file, committed baseline, 5.8 drop check, and all evidence remain untouched and are never read back from Logfire. (AD-12)
>
> **Out of scope, deliberately.** Publishing from inside the suite run, rewriting the live suite on pydantic-evals, Logfire live evaluations or LLM judges, and publishing deterministic golden-case results.

**Epic 5 implementation notes (line 333), append:** `Stories 5.9–5.10 (added 2026-09-24, sprint-change-proposal-2026-09-24) export sanitized full-request-path traces and live-evaluation results to Logfire; neither is a Gate B criterion.`

**Story Map, Epic 5 row, append:** ` - 5.9 Full-stack Logfire tracing - 5.10 Live-eval results in Logfire`. Count `47 stories` → `49 stories`.

### 4.4 Epic 6 — Story 6.3 (one clause)

> **And** the hosted runtime exports traces to Logfire only in the default content-free mode; `AGENT_TRACE_CONTENT_MODE` is absent from all IaC and task definitions, and `LOGFIRE_TOKEN` comes from Secrets Manager. (NFR30, AD-12)

### 4.5 Sprint status — `sprint-status.yaml`

Under `epic-5`, after `5-8-…: done`:
```yaml
  # 5.9/5.10 added 2026-09-24 by sprint-change-proposal-2026-09-24.md (Logfire). Additive,
  # NOT Gate B criteria. 5.9 = full request-path tracing behind ONE export boundary; owns
  # deferred-work.md:696; settle the full allow-list at creation. 5.10 = post-hoc eval results;
  # must not touch the report schema or evidence.
  5-9-trace-the-full-request-path-to-logfire-behind-one-export-boundary: backlog
  5-10-publish-live-evaluation-results-to-logfire: backlog
```

### 4.6 Deferred-work ledger

- `:696` (span events carry exception text): **re-point owner** from "Epic 6 wiring the first real exporter" to **Story 5.9**. It closes when the sanitizer lands and the residual assertion in `test_c4_spans_withhold_exception_content_on_the_provider_error_path` is deleted.
- `:663` (label-value cardinality): **unchanged.** Its trigger is a *metrics* exporter.
- **New entry — one continuous API→worker trace.** Origin: this proposal, F3. **Trigger:** the first diagnosis that needs one waterfall across the job queue, which attribute-joined traces can't answer. **Needs:** an additive nullable `job_queue.trace_context` column, a trace-context port in `application/` (AD-1), and the worker resuming that context.

### 4.7 Docs (done inside the stories)

- `docs/CONFIGURATION.md`: `LOGFIRE_TOKEN`, the region base URL and `AGENT_TRACE_CONTENT_MODE`, with F1's residual stated plainly (5.9).
- `.env.example`: token and region commented out; content mode **not** listed (enforced by the guard test) (5.9).
- `docs/TESTING.md`: the publisher command (5.10).

## 5. Implementation handoff

**Scope classification: Moderate.** Two new backlog stories plus small PRD/architecture text edits. No replan and no change to an existing story's acceptance.

| Recipient | Responsibility |
|---|---|
| Developer agent (this session, on approval) | Apply §4.1–§4.6 artifact edits exactly as written |
| `bmad-create-story` → 5.9 | Pin OTel versions (PyPI-verified). **Measure real spans** from FastAPI, SQLAlchemy, httpx, agent and worker, and settle the complete allow-list per span type before dev. Carry F1–F5 verbatim. |
| `bmad-dev-story` → 5.9, then 5.10 | Code commit → measure → `evidence_binding.py` → separate evidence commit (EVIDENCE-CONVENTION). |
| Minh | Create a Logfire project (choose US or EU region) and a **write token**, and put it in `backend/.env` as `LOGFIRE_TOKEN` yourself (never in chat). **Needed first at the end of 5.9 development**, for the real-export smoke check. CI never needs it. |

**Success criteria:**
1. One Logfire trace per conversation contains each turn's request → agent → model/tool → database spans. No content in default mode; searchable by `shiftmind.agent_run.id`.
2. A solver job's worker spans are findable by `shiftmind.schedule_run.id` from the enqueueing request.
3. A live-eval conversation shows readable prompts and completions under `deployment.environment=live-eval`. After the publisher runs, its verdict spans sit in the same trace and the suite run appears on the Experiments page.
4. Breaking Logfire connectivity changes no test outcome, audit row, verdict or gate. Default CI stays keyless and green. 5.2's regenerated evidence lists the export boundary and new channels.

## Application notes (2026-09-24)

Applied: §4.1 addendum (§2 row, §2.1 sentence, §6 paragraph); §4.2 AD-12 and Stack table; §4.3 Stories 5.9/5.10, Epic 5 implementation note and Story Map row; §4.4 Story 6.3 clause; §4.5 sprint-status entries; §4.6 ledger re-point of `:696` and the new F3 entry.

Two deviations from the text above:

1. **Story count not changed (§4.3 said `47 → 49`).** The "47 stories" sentence in `epics.md` was already stale. The Story Map lists 52 stories before this change, and Story 5.8 was never added to `epics.md` at all. Writing 49 would have repeated a wrong number, so the sentence is left as it was and the discrepancy is recorded here for a future epics tidy-up.
2. **AD-1 enforcement is carried by Story 5.9, not applied now (§4.2).** Adding `opentelemetry.sdk`, `.exporter` and `.instrumentation` to `FORBIDDEN_ROOT_MODULES` is a test-code change and ships with the code it guards. It is recorded in the sprint-status note for 5.9.

## Amendment 2026-09-25 — the publisher is a second content channel (approved by Minh)

**Trigger.** Story 5.10's creation found that addendum §6 authorized content by *process* ("set only by the disposable live-evaluation stack"), not by *data*. The 5.10 publisher replays the same seeded synthetic conversations, but as a separate process it fell outside the wording. The only compliant experiment was text-free: a pass/fail grid with no input, output or judge reason. Logfire's review flow is built around reading exactly those three (Input → Output → evaluator reason → trace).

**Why the original rule does not apply here.** The rule (PRD §6.1, NFR3, NFR30) protects real workforce data: in a scheduling assistant the conversation text names employees, their availability and assignments. A finished live-suite report contains only conversations run on seeded synthetic fixtures. For runs measured after Story 5.9 with a token, the same text is already in Logfire in the stack's `live-eval` traces.

**Change.** Addendum §6 now names two authorized channels, both synthetic-only and both tagged `deployment.environment=live-eval`: (1) the stack's `AGENT_TRACE_CONTENT_MODE=synthetic-eval`; (2) the live-evaluation publisher, which may export each turn's user message, authored obligation, visible reply and judge reasons from a finished report, and nothing else from it. The channels are listed by name rather than by data class so that a future tool does not inherit the permission without a decision. Credentials and exception text stay withheld in every channel. The runtime (default mode, hosted Epic 6) is unchanged and content-free. Epic ACs, NFRs, the spine and Story 6.3's clause are unchanged. The design lives in Story 5.10 Decisions 3, 4, 6 and 7.
