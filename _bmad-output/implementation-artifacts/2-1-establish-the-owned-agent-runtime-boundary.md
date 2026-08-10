---
baseline_commit: 7f268e042977222709c72cc06eee767f9d42b9fd
---

# Story 2.1: Establish the Owned Agent Runtime Boundary

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a product engineer,
I want a validated ShiftMind-owned agent runtime port,
So that conversational behavior can evolve without making a model framework part of product authority or persisted contracts.

**This is the Epic 2 enabler.** It ships no planner-visible feature. It answers one question — *can a framework carry our agent loop without becoming a product contract?* — and then builds the seam that keeps the answer true.

**Gate A is clear.** `evidence/story-1.11/gate-a-readiness-report.json` records `gate_a_passed: true` as of `ae19f58`. AR28's "before AgentRuntime or agent tools" ordering constraint is satisfied; this story is unblocked.

**Unblocks:** Story 2.2 (which formalizes the model doubles this spike proves), Story 2.3, and every conversational story.

**Sizing note from `epics.md`:** high implementation breadth — framework spike, owned port, dependency boundaries, brownfield seams, and hidden-reasoning discard. The ten tasks below each carry exactly one acceptance boundary; do not merge them.

### Two decisions were made at story creation — do not re-litigate them

**1. The pinned seed moves from PydanticAI 2.14.1 to 2.27.0.** AR19 and AD-19 name `2.14.1` as the *seed*; AD-19's own closing clause permits replacement: *"a different V2 release may replace the seed only with the same evidence."* 2.14.1 shipped 2026-07-21, one day before the spine was written; 2.27.0 is current as of 2026-08-09. Task 1 records the substitution with evidence. **The spike targets 2.27.0.** The seven capabilities in AC1 were confirmed present at both tags before this choice was made.

**2. A failed spike halts the story. It does not trigger a fallback.** AC1 says the dependency enters manifests only after the spike passes; it does not say what happens if it fails. It is now specified: on any failed capability, stop, record which one failed with a reproduction, add nothing to `backend/pyproject.toml` or `backend/uv.lock`, and escalate. **Do not hand-roll an agent loop. Do not silently try a different version.** A negative spike result is a valid deliverable — the same posture Story 1.11 held with `gate_a_passed: false`.

## Acceptance Criteria

1. **Given** the repository's supported Python, Pydantic, provider, and test environments **when** the pinned PydanticAI compatibility spike runs **then** it proves typed tools, deferred calls, deterministic model doubles, owned-message translation, bounded execution, provider failure mapping, and content-disabled instrumentation **and** the tested version is added to manifests/lockfiles only after the spike passes. *(AR19, AR27)*

2. **Given** the `AgentRuntime` port and adapter **when** domain or application modules are inspected **then** they contain no PydanticAI, provider-message, deferred-call, framework-tool, checkpoint, or telemetry event type **and** the existing provider-neutral constraint parsing and cached-insight operations remain behind their own ports until deliberately migrated. *(AR1, AR19)*

3. **Given** new runtime work is added **when** its module location and dependency direction are reviewed **then** it converges on the architecture structural seed under backend API/worker/application/domain/agent/engine/adapters/migrations/evals and frontend API/features/routes boundaries **and** compatibility adapters permit incremental brownfield migration without an all-at-once rename. *(AR26)*

4. **Given** a provider response containing hidden reasoning or thinking parts **when** the adapter translates the response **then** hidden reasoning is discarded and only planner-visible content, typed recovery data, concise application-owned summaries, and evidence references may persist **and** no private chain-of-thought appears in product records or telemetry. *(AR15, FR20 precursor)*

## Tasks / Subtasks

- [x] **Task 1: Record the seed-replacement decision before touching any manifest** (AC: #1)
  - [x] Write `docs/AGENT-RUNTIME-DECISION.md` (flat, uppercase — `docs/` has no topic subdirectories; matches `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md`).
  - [x] It must state: AD-19 names 2.14.1 as a seed and permits replacement "only with the same evidence"; 2.27.0 is the release under test; the seven AC1 capabilities are the evidence bar; and the spike verdict will be appended to this file.
  - [x] Record the compatibility facts already verified at `7f268e0` so the spike confirms rather than discovers them:

    | Constraint (pydantic-ai-slim 2.27.0) | Repo today | Verdict |
    |---|---|---|
    | `requires-python >=3.10` | venv Python **3.10.9**; `backend/pyproject.toml:5` `>=3.10,<3.13` | compatible |
    | `pydantic>=2.12` | locked **2.13.4** | compatible |
    | `openai>=2.45.0` (`openai` + `openrouter` extras) | locked **2.45.0** | exact floor — see Task 4's warning |
    | `google-genai>=1.70.0` (`google` extra) | locked **2.10.0** | compatible |
    | `httpx>=0.27` | locked **0.28.1** | compatible |
    | `anyio>=4.7.0` | locked **4.14.1** | compatible |
    | `opentelemetry-api>=1.28.0` | **absent** | new transitive dependency |
    | `exceptiongroup>=1.2.2` (`python_version < "3.11"`) | **absent** | new transitive dependency on the 3.10 venv |

  - [x] **Acceptance boundary:** the file exists and names 2.27.0 as the version under test, and `git diff` shows no change to `backend/pyproject.toml` or `backend/uv.lock`.

- [x] **Task 2: Build the spike so it cannot contaminate the repository manifest** (AC: #1)
  - [x] Spike code lives at `backend/spikes/agent_runtime/` with its **own** `pyproject.toml` declaring `pydantic-ai-slim[google,openrouter]==2.27.0` plus `pytest`. Run it with `uv run --project backend/spikes/agent_runtime pytest`.
  - [x] **Use `pydantic-ai-slim`, never the `pydantic-ai` meta-package.** `pydantic-ai==2.27.0` resolves to `pydantic-ai-slim[anthropic,cli,evals,google,logfire,mcp,openai,retries,web]` — it would drag Anthropic, MCP, a CLI, a web-fetch stack, `pydantic-evals`, and the Logfire SDK into a portfolio backend that needs none of them today. `logfire` in particular is a *planned optional* stack row owned by Story 5.1; pulling it here would silently claim that gate.
  - [x] The two extras chosen mirror the two providers the repo already ships (`backend/llm/gemini.py` → `google-genai`, `backend/llm/openrouter.py` → `openai`). Adding a third provider extra is scope creep.
  - [x] **Acceptance boundary:** the spike suite runs to completion and `git status --porcelain` shows changes only under `backend/spikes/` and `docs/`.

- [x] **Task 3: Prove all seven AC1 capabilities, or halt** (AC: #1)
  - [x] One test per capability, each producing a named pass/fail line. All seven must pass. `models.ALLOW_MODEL_REQUESTS = False` at module scope in every spike test — no network call in this task, ever.

    | # | AC1 capability | What must be demonstrated | Confirmed API at v2.27.0 |
    |---|---|---|---|
    | 1 | typed tools | a Pydantic-typed tool signature is exposed to the model and its arguments arrive validated | `@agent.tool` / `@agent.tool_plain` |
    | 2 | deferred calls | a tool marked for approval **suspends the run**, returns the pending call, and the run **resumes** from that suspension with an approve *and* a deny | `output_type=[str, DeferredToolRequests]`, `@agent.tool_plain(requires_approval=True)`, `raise ApprovalRequired`, `DeferredToolResults(approvals={tool_call_id: True \| ToolDenied(...)})`, `agent.run_sync(message_history=..., deferred_tool_results=...)` |
    | 3 | deterministic model doubles | a scripted multi-step tool loop (call → result → text) runs identically twice with no network | `TestModel`, `FunctionModel(fn)` + `AgentInfo`, `agent.override(model=...)` |
    | 4 | owned-message translation | a run's messages **round-trip through a ShiftMind-owned shape** and a second run continues from the rehydrated history — see the hard rule below | `capture_run_messages()`, `result.all_messages()`, `message_history=` |
    | 5 | bounded execution | an application-set limit terminates the run, and wall-time exhaustion is distinguishable from other limit exhaustion | `UsageLimits(...)`, `UsageLimitExceeded` |
    | 6 | provider failure mapping | a provider error surfaces as an identifiable framework exception that an adapter can catch and re-raise as an owned type | raise from inside `FunctionModel`; `UnexpectedModelBehavior`, `ModelHTTPError` |
    | 7 | content-disabled instrumentation | instrumentation can be enabled with prompt/tool content excluded, and the emitted spans carry no prompt or tool payload | `Agent(..., capabilities=[Instrumentation(settings=InstrumentationSettings(include_content=False))])`; also `Agent.instrument_all(settings)` |

  - [x] **Hard rule for capability 4 — this is the most likely place to get it wrong.** AD-19 states framework messages "never become domain, persistence, browser, or audit contracts." Therefore the round-trip must go `ModelMessage[] → owned dataclass → JSON → owned dataclass → ModelMessage[]`. **Serializing `to_jsonable_python(result.all_messages())` and calling that the durable form fails this capability**, even though `ModelMessagesTypeAdapter` makes it trivially easy — that JSON *is* a PydanticAI contract, and persisting it makes the framework a persisted contract by definition. The point of the spike is to prove translation is possible, not that serialization exists.
  - [x] Capability 7 must assert on **observed span attributes**, not on the settings object. Use an in-memory OTel span exporter (`opentelemetry-sdk` — a spike-only dependency, not a repo one) and assert no span attribute contains the prompt text or the tool arguments. Reading `settings.include_content is False` proves nothing about what is emitted.
  - [x] Capability 5 must show the *distinction* AD-7 requires: wall-time exhaustion → `timed_out`, other limit exhaustion → `failed` with a stable `budget_exhausted` reason. If the framework cannot distinguish them, that is an adapter obligation, not a spike failure — record which side owns it.
  - [x] **Acceptance boundary:** append a verdict table to `docs/AGENT-RUNTIME-DECISION.md` — one row per capability, `pass`/`fail`, with the spike test name. **If any row is `fail`: stop the story here.** Record the failure with a reproduction, leave `backend/pyproject.toml` and `backend/uv.lock` untouched, set the story status to blocked, and escalate. Do not proceed to Task 4. Do not hand-roll a loop. Do not try a different version.

- [x] **Task 4: Lock the dependency — only now** (AC: #1)
  - [x] Add `pydantic-ai-slim[google,openrouter]==2.27.0` to `backend/pyproject.toml` `[project].dependencies` and refresh `backend/uv.lock`. Exact pin, not a floor — AR27 requires each planned dependency be *locked* at its implementation gate.
  - [x] **Watch the `openai` floor.** The repo declares `openai>=1.40` but the lock already resolved **2.45.0**, which is exactly pydantic-ai's floor. The resolution therefore should not move `openai` at all. **If `uv lock` moves `openai`, `google-genai`, `pydantic`, `httpx`, or `anyio`, stop and report the diff before continuing** — `backend/llm/openrouter.py:194` calls `client.chat.completions.create(...)` and `backend/llm/gemini.py` calls the google-genai SDK directly; a silent bump under either is a regression this story did not sign up for.
  - [x] Update the architecture spine's Stack table row: `PydanticAI | 2.27.0 | repository lock` (was `2.14.1 | planned seed; compatibility spike and lock required before agent slice`). Cite `docs/AGENT-RUNTIME-DECISION.md`. This is the one spec edit this story is authorized to make.
  - [x] **Acceptance boundary:** `uv run --frozen pytest` passes from `backend/` with the new dependency installed, and `git diff backend/uv.lock` shows no version change to `openai`, `google-genai`, `pydantic`, `httpx`, or `anyio`.

- [x] **Task 5: Define the owned `AgentRuntime` port and its contracts** (AC: #2)
  - [x] `backend/application/ports/agent_runtime.py` — a `typing.Protocol`, matching the shape of `application/ports/scenario_projection.py` (frozen dataclasses for inputs/outputs, `Protocol` for the port, absolute imports).
  - [x] `backend/application/contracts/agent_runtime.py` — the owned types that cross the seam. Every contract carries `schema_version` per the spine's *Normative contract minimums*.
  - [x] **Own these, name them ourselves:** the turn request, the owned message/turn record, the typed tool-call proposal, the tool result, the suspension-for-approval marker, the run outcome (including the `timed_out` / `failed`+`budget_exhausted` distinction from AD-7), and the budget. Model naming on the existing `V1` convention (`EvidenceRefV1`, `ScenarioProjectionV1`).
  - [x] **Do not name these `ActivityItemV1`, `PersistedEventV1`, `CapabilityManifestV1`, or `JobLeaseV1`.** Those four are cross-epic contracts owned by Stories 2.3, 2.4, 2.6, and Epic 3 respectively (AD-20). Defining a partial version here would force a rename later or, worse, be quietly extended into a contract this story never validated.
  - [x] The port takes trusted server-owned inputs only. It must not accept a model-supplied capability name, a browser value, or an authority flag (AD-2, AD-15).
  - [x] **Acceptance boundary:** `backend/application/**` imports nothing from `pydantic_ai`, and the port is exercised by at least one test through a fake implementation that never imports the framework.

- [x] **Task 6: Implement the adapter in `backend/agent/`** (AC: #2, #4)
  - [x] New package `backend/agent/` — AR26's structural seed names it `# AgentRuntime and capability-module adapters`. This is the **only** new top-level backend package this story creates.
  - [x] The adapter implements the Task 5 port over PydanticAI: owned request → framework call → owned outcome. All seven spike capabilities become real adapter behavior; the spike proved they are possible, the adapter makes them ours.
  - [x] **Owned error type.** Define `AgentRuntimeError` in the application layer, mirroring `llm/base.py:LLMProviderError`'s established pattern — provider-neutral, so no vendor or framework exception type crosses the seam. Catch `UnexpectedModelBehavior`, `ModelHTTPError`, `UsageLimitExceeded` and anything else PydanticAI raises; re-raise as owned. A bare `except Exception` that swallows the cause is not acceptable — preserve it with `raise ... from exc`.
  - [x] Instrumentation is constructed **content-disabled by default** (`InstrumentationSettings(include_content=False)`). Per AD-12/AD-15 external telemetry excludes prompt, tool, workforce, and schedule content by default. **Do not add the Logfire SDK** — Story 5.1 owns telemetry export; `opentelemetry-api` arriving transitively is sufficient here.
  - [x] Budgets, limits, and timeouts come from application configuration, never from the model (AD-7). Wire them through the port's budget contract; do not read env vars inside the adapter.
  - [x] **Ship exactly one throwaway demonstration tool**, exercised only by deterministic doubles, purely to prove the typed-tool and deferred-call seams end to end. It must not read scenario data, touch a repository, or resemble a real capability.
  - [x] **Acceptance boundary:** an adapter test drives a full multi-step turn — tool call, suspension for approval, resume, terminal outcome — against `FunctionModel`, with `models.ALLOW_MODEL_REQUESTS = False`, and asserts on owned types only.

- [x] **Task 7: Prove hidden reasoning is discarded** (AC: #4)
  - [x] `ModelResponse` exposes `.thinking` and carries `ThinkingPart` entries in `.parts` (confirmed at v2.27.0). Construct a `FunctionModel` that returns a response containing a `ThinkingPart` with a recognisable sentinel string alongside a `TextPart`.
  - [x] Assert the sentinel appears in **no** owned output: not in the visible content, not in the owned message record, not in the summary, not in any typed recovery payload, not in the JSON round-trip from Task 5's contracts, and not in an emitted span attribute.
  - [x] Assert the **positive** half too: planner-visible content, typed recovery data, and the application-owned summary survive translation. A test that only proves absence would also pass if the adapter discarded everything.
  - [x] The discard is a **whitelist**, not a blacklist: translate the part kinds we recognise and drop the rest. A `isinstance(part, ThinkingPart): continue` blacklist silently admits the next reasoning-part type the framework introduces — and AD-15 says "discard provider hidden-reasoning parts", not "discard the one class named ThinkingPart".
  - [x] **Acceptance boundary:** a sentinel-string test that fails loudly if the sentinel reaches any persisted or emitted surface.

- [x] **Task 8: Leave the existing LLM seams alone, and prove it** (AC: #2)
  - [x] AC2's second clause and AD-19 both require the existing provider-neutral constraint-parsing and cached-insight operations to stay behind their own ports "until deliberately migrated." **This story does not migrate them.**
  - [x] `backend/llm/{base,stub,gemini,openrouter,translate}.py` and `backend/services/{constraint_service,insight_service}.py` are **not modified**. `LLMProvider`, `LLMProviderError`, `create_provider()`, and `to_override_call()` keep their current signatures. The `stub` default and the keyless-CI invariant (`backend/conftest.py` pops `LLM_PROVIDER`/`LLM_MODEL`) are untouched.
  - [x] The two seams may share a provider client *inside adapters* (AD-19 permits it) but must not share a port, an error type, or a configuration key. `AgentRuntime` gets its own settings fields; do not overload `llm_provider`/`llm_model`.
  - [x] **Acceptance boundary:** `git diff --stat` shows zero lines changed under `backend/llm/` and `backend/services/`, and the existing `test_llm_provider.py`, `test_gemini_provider.py`, `test_openrouter_provider.py`, `test_constraints_api.py`, and `test_insights_api.py` pass unchanged.

- [x] **Task 9: Make the boundary executable** (AC: #3)
  - [x] `backend/tests/architecture/test_agent_runtime_boundaries.py` — an AST or import-graph walk asserting that no module under `backend/domain/**` or `backend/application/**` imports `pydantic_ai` (any submodule), and that no framework message, deferred-call, tool, checkpoint, or telemetry type name appears in their source.
  - [x] Assert the dependency **direction** too, not just the absence of one package: `backend/agent/**` may import `application` and `domain`; the reverse must fail the test. `backend/domain/**` continues to import nothing outside itself (AD-1).
  - [x] Add the same guard for the persisted shape: assert no `application/contracts/**` dataclass field is typed as, or defaults to, a framework object. This is the executable form of the Task 3 capability-4 hard rule.
  - [x] **Acceptance boundary:** the test **fails** when temporarily given a violating import, and passes on the shipped tree. Demonstrate both — a guard nobody has seen go red is a guard nobody has tested.

- [x] **Task 10: Full regression gate** (AC: #1, #2, #3, #4)
  - [x] Backend: `uv run --frozen pytest`; `uv run --frozen pytest -m postgres` (needs Docker PostgreSQL 18 up via `docker-compose.yml`); `alembic check` must show zero diff — **this story adds no migration**.
  - [x] Frontend: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run test:e2e`. This story changes no frontend file; the suites must stay green regardless.
  - [x] **Re-run Gate A explicitly and report by name.** AR28's "no later gate may weaken an earlier gate's invariants" binds this story: regenerate `evidence/story-1.11/gate-a-readiness-report.json` and confirm it still reads `gate_a_passed: true`. Adding a dependency changes the environment the gate was measured in.
  - [x] **Re-derive the baselines at the start rather than trusting these.** Recorded at `7488fc8` / `sprint-status.yaml`: backend **452 passed / 0 skipped / 6 deselected**; postgres **27**; frontend **50 files / 287 tests**; e2e **46**; alembic zero diff.
  - [x] **Acceptance boundary:** every suite green at its re-derived baseline plus this story's new tests, and Gate A still `true`.

## Dev Notes

### What this story is, and the six things it is not

It is: a port, an adapter, a spike that justifies the dependency, and executable proof the boundary holds.

It is **not**:

| Not this | Owned by |
|---|---|
| Conversation persistence, messages, accept-turn bundle | Story 2.3 |
| SSE, `PersistedEventV1`, `Last-Event-ID` replay | Story 2.4 |
| The application-owned capability registry | Story 2.5 |
| `CapabilityManifestV1` and add/remove conformance | Story 2.6 |
| The deterministic evaluation harness and golden dataset | Story 2.2 |
| Any chat UI, route, or frontend change | Stories 2.3–2.8 |

Story 2.2 "formalizes the model doubles this spike proves" — so the spike's doubles are throwaway proof, not the harness. Resist building `backend/evals/` here.

### The framework-as-persisted-contract trap

This is the single failure mode that would make the whole story worthless, and PydanticAI makes it *easy* to fall into:

```python
# WRONG — this is the shape the framework docs teach, and it makes
# PydanticAI a persisted product contract in violation of AD-19.
from pydantic_core import to_jsonable_python
row.messages_json = to_jsonable_python(result.all_messages())

# RIGHT — translate at the adapter edge into a shape we own and version.
row.turn = AgentTurnV1.from_framework(result.all_messages())   # in backend/agent/
```

AD-19: *"messages, deferred calls, tool objects, checkpoints, and framework event types never become domain, persistence, browser, or audit contracts."* `ModelMessagesTypeAdapter` exists and works; using it as the durable format is precisely the thing being prohibited. Task 9's contract-field guard is the mechanical defence.

### Verified environment facts (at `7f268e0`, clean tree)

- Local venv is **Python 3.10.9** — not the 3.12 the spine names as the *container target*. `backend/pyproject.toml:5` allows `>=3.10,<3.13`; pydantic-ai 2.27.0 needs `>=3.10`. It works, but `exceptiongroup` will be pulled in on 3.10 and not on 3.12, so the lock is Python-version-sensitive. Note it in the decision doc.
- Locked today: `pydantic 2.13.4`, `fastapi 0.138.1`, `openai 2.45.0`, `google-genai 2.10.0`, `httpx 0.28.1`, `anyio 4.14.1`, `sqlalchemy 2.0.51`, `psycopg 3.3.4`, `alembic 1.18.5`, `ortools 9.11.4210`.
- `opentelemetry-api` is **not** currently in `backend/uv.lock`. It arrives as a base dependency of `pydantic-ai-slim`. This is expected and acceptable; the Logfire SDK is not.
- pytest runs **from `backend/`**. `backend/pyproject.toml:28` sets `testpaths = ["tests"]`; `backend/conftest.py:32` does `sys.path.insert(0, os.path.dirname(__file__))`. A repo-root `tests/architecture/` directory **would not be collected** — hence Task 9's `backend/tests/architecture/`. See Project Structure Notes.
- Markers: `live` (excluded by default via `addopts = -m "not live"`) and `postgres` (skips cleanly with no database). Story 1.11 established that **a skipped test is not a passed test** — do not mark any new test `postgres` or `live` unless it genuinely needs them.
- No `.github/`, no root `package.json`, no Makefile. All scripts live in `backend/scripts/`. Gate commands are local.
- `backend/agent/`, `backend/worker/`, `backend/evals/`, and `tests/architecture/` do **not** exist yet. Create only `backend/agent/`. Do not scaffold empty packages for the others — `worker/` is Epic 3's and `evals/` is Story 2.2's, and an empty package that nobody owns rots.

### Existing conventions to match, not reinvent

| Need | Copy the pattern from |
|---|---|
| Port as `Protocol` + frozen dataclass DTOs | `backend/application/ports/scenario_projection.py` |
| Versioned contract dataclasses, `V1` suffix | `backend/application/contracts/evidence_ref.py` |
| Provider-neutral error type at a seam | `backend/llm/base.py:LLMProviderError` |
| Factory with lazy imports behind a registry | `backend/llm/base.py:create_provider` |
| Secret-bearing settings field kept out of `__repr__` | `backend/settings.py` — `field(repr=False, ...)` on both API keys (T-04-01) |
| Vendor payload unpacked to a neutral pair before crossing | `backend/llm/translate.py` module docstring |
| Absolute imports from the backend root | every module — `from application.contracts... import ...`, never relative |

If `AgentRuntime` needs a model/API-key setting, follow the existing `settings.py` shape exactly: an env-read in `default_settings()`, a frozen field, `repr=False` if it carries a secret.

### Anti-patterns for this story

- **Do not persist `result.all_messages()` in any framework-native form.** The whole story exists to prevent this.
- **Do not proceed past a failed spike capability.** The escalation is the deliverable.
- **Do not install `pydantic-ai`** (the meta-package). Use `pydantic-ai-slim[google,openrouter]`.
- **Do not add the Logfire SDK.** `opentelemetry-api` transitively is fine; telemetry export is Story 5.1.
- **Do not build a capability registry or a `CapabilityManifestV1`.** Stories 2.5 and 2.6 own those and depend on nothing here.
- **Do not touch `backend/llm/**` or `backend/services/**`.** AC2 requires those seams preserved; Task 8's boundary is a zero-line diff.
- **Do not overload `llm_provider` / `llm_model`.** Two seams, two configurations.
- **Do not let a model-supplied string reach an authority decision.** AD-2 and AD-15: capability names, permissions, budgets, and approval never come from model output.
- **Do not blacklist `ThinkingPart`.** Whitelist the parts we translate; drop everything else.
- **Do not add a CI workflow.** `.github/` does not exist and pipeline ownership is out of scope (established in Stories 1.10, 1.11).
- **Do not weaken Gate A.** If a change breaks `ScenarioDataParity.test.tsx`, `scenarioDataBoundaries.test.ts`, or `legacyReachability.test.ts`, fix the change.
- **Do not hand-type an evidence file.** This story is not expected to produce one — but if it does, `docs/EVIDENCE-CONVENTION.md` governs: commit code → measure on a clean tree → generate via `backend/scripts/evidence_binding.py` → commit evidence separately.

### Latest technical information (verified 2026-08-09)

PydanticAI **2.27.0** is the current release (2.14.1 shipped 2026-07-21). All seven AC1 capabilities were confirmed against the v2.27.0 tag's own documentation, not the general docs site:

- Deferred/approval flow: `output_type=[str, DeferredToolRequests]`; `@agent.tool_plain(requires_approval=True)`; `raise ApprovalRequired(metadata={...})` for conditional approval driven by `ctx.tool_call_approved`; resume via `agent.run_sync(message_history=messages, deferred_tool_results=DeferredToolResults(approvals={tool_call_id: True | ToolDenied('…')}))`. There is also an in-run `HandleDeferredToolCalls` capability — **prefer the suspend-and-resume form**, because ShiftMind's approval is a persisted one-time state machine (AD-10), not an in-process callback.
- Testing: `from pydantic_ai import models; models.ALLOW_MODEL_REQUESTS = False`; `from pydantic_ai.models.test import TestModel`; `from pydantic_ai.models.function import AgentInfo, FunctionModel`; `agent.override(model=...)`; `capture_run_messages()`.
- Messages: `ModelMessagesTypeAdapter`, `ModelRequest`/`ModelResponse`, parts `TextPart`/`ToolCallPart`/`ThinkingPart`. `ModelResponse` carries `finish_reason` (`stop|length|content_filter|tool_call|error`) and `state` (`complete|incomplete|suspended|interrupted`) — both are useful raw material for the owned outcome contract, and both must be *translated*, not stored.
- Instrumentation: `from pydantic_ai.capabilities import Instrumentation`; `from pydantic_ai.models.instrumented import InstrumentationSettings`; `Agent(..., capabilities=[Instrumentation(settings=InstrumentationSettings(include_content=False))])` or `Agent.instrument_all(settings)`.
- Note the API moved into `pydantic_ai.capabilities` in the 2.x line. Confirm every import against the **installed** version, not against the docs site — the site tracks `main`.

### Project Structure Notes

- **New:** `backend/agent/` (adapter), `backend/application/ports/agent_runtime.py`, `backend/application/contracts/agent_runtime.py`, `backend/tests/architecture/` (+ `__init__.py`), `backend/tests/test_agent_runtime_adapter.py`, `backend/spikes/agent_runtime/` (own `pyproject.toml`, deleted or kept — decide and record), `docs/AGENT-RUNTIME-DECISION.md`.
- **Modified:** `backend/pyproject.toml` and `backend/uv.lock` (Task 4 only), the architecture spine's Stack table row for PydanticAI.
- **Not modified:** `backend/llm/**`, `backend/services/**`, `backend/domain/**`, any frontend file, any migration.
- **Variance from AR26, recorded deliberately:** the spine's structural seed lists `tests/architecture/` as a repo-root sibling of `backend/`. Placing it there today would not be collected — pytest runs from `backend/` with `testpaths = ["tests"]`, and `backend/conftest.py` is what makes backend modules importable. A root-level suite would need its own `conftest.py`, a `testpaths` change, and a second rootdir convention: unowned churn inside an enabler story. **AC3's own list does not include `tests/architecture`** — it names `backend/{api,worker,application,domain,agent,engine,adapters,migrations,evals}` and `frontend/{api,features,routes}`. So `backend/tests/architecture/` satisfies AC3 while keeping one rootdir. Record this variance in completion notes so a later story can promote it if it ever adds a root-level suite.
- **Spike directory disposition:** decide explicitly whether `backend/spikes/agent_runtime/` is committed or removed after Task 4, and say which in completion notes. Recommended: **commit it** — it is the reproducible evidence behind the seed-replacement decision, and `docs/AGENT-RUNTIME-DECISION.md` is worth less without a runnable proof beside it. Ensure it is excluded from the backend test run (it has its own project and is outside `testpaths`).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1, lines 606-636] — story statement, sizing note, and all four acceptance criteria, verbatim
- [Source: _bmad-output/planning-artifacts/epics.md, lines 147, 165, 172, 173] — AR1 (hexagonal boundary; the explicit "cannot import … PydanticAI …" list), AR19 (owned `AgentRuntime` port, preserved existing ports, pinned spike), AR26 (structural seed), AR27 (lock each planned dependency at its implementation gate)
- [Source: _bmad-output/planning-artifacts/epics.md, lines 161, 174] — AR15 (untrusted content, discard hidden reasoning) and AR28 (Gate A precedes AgentRuntime; no later gate weakens an earlier one)
- [Source: _bmad-output/planning-artifacts/epics.md, lines 709-717, 739-747] — Stories 2.5 and 2.6's explicit ownership of the registry and `CapabilityManifestV1`; the boundary this story must not cross
- [Source: .../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md, lines 198-202] — AD-19 verbatim: the owned `AgentRuntime` port, the preserved task-specific ports, "never become domain, persistence, browser, or audit contracts", and the "a different V2 release may replace the seed only with the same evidence" clause this story invokes
- [Source: ARCHITECTURE-SPINE.md, lines 48-52, 54-58] — AD-1 hexagonal module boundary and the "existing `services`, `store`, and `llm` seams may remain behind compatibility adapters" allowance; AD-2 three-way authority partition
- [Source: ARCHITECTURE-SPINE.md, lines 84-92] — AD-7 closed state machines: application configuration (not the model) sets budgets; wall-time → `timed_out`, other exhaustion → `failed` with stable `budget_exhausted`
- [Source: ARCHITECTURE-SPINE.md, lines 174-178] — AD-15: prompts/model output/tool output are untrusted; adapters discard hidden-reasoning parts and persist only visible messages, owned summaries, typed recovery data, and evidence links
- [Source: ARCHITECTURE-SPINE.md, lines 204-208, 312-331] — AD-20 canonical contract set (the sixteen `V1` names this story must not partially define) and the *Normative contract minimums* `schema_version` rule
- [Source: ARCHITECTURE-SPINE.md, lines 262-283] — the Stack table: `PydanticAI 2.14.1 | planned seed; compatibility spike and lock required before agent slice`, the row Task 4 updates
- [Source: ARCHITECTURE-SPINE.md, lines 287-303] — the Structural Seed tree naming `backend/agent/`, `backend/evals/`, `backend/worker/`, and root `tests/architecture/`
- [Source: evidence/story-1.11/gate-a-readiness-report.json; git ae19f58] — `gate_a_passed: true`, the AR28 precondition for this story
- [Source: _bmad-output/implementation-artifacts/1-11-confirm-gate-a-readiness.md, lines 30-34, 285-296] — the "verdict is not completion" posture Task 3's halt rule copies, and the anti-pattern list style
- [Source: docs/EVIDENCE-CONVENTION.md; .claude/CLAUDE.md] — commit → measure → generate → commit-separately, if this story produces evidence at all
- [Source: backend/pyproject.toml, lines 5, 6-20, 28-33] — `requires-python >=3.10,<3.13`, the current dependency set, `testpaths = ["tests"]`, and the `live`/`postgres` markers with `addopts = -m "not live"`
- [Source: backend/uv.lock] — locked `openai 2.45.0`, `google-genai 2.10.0`, `pydantic 2.13.4`, `httpx 0.28.1`, `anyio 4.14.1`; `requires-python = ">=3.10, <3.13"`
- [Source: backend/conftest.py, lines 18-45] — the keyless-CI invariant (`LLM_PROVIDER`/`LLM_MODEL` popped at lines 44-45) and the `sys.path.insert` at line 32 that fixes the pytest rootdir
- [Source: backend/llm/base.py; backend/llm/translate.py] — the `LLMProvider` Protocol, `LLMProviderError`, `create_provider()` registry, and the provider-neutral translation point Task 8 must leave untouched
- [Source: backend/application/ports/scenario_projection.py; backend/application/contracts/evidence_ref.py] — the port and contract conventions Task 5 mirrors
- [Source: backend/settings.py] — `default_settings()`, the frozen `Settings` dataclass, and the `field(repr=False, ...)` treatment for secrets
- [Source: https://pypi.org/pypi/pydantic-ai/2.14.1/json; .../2.27.0] — 2.14.1 released 2026-07-21; 2.27.0 current at 2026-08-09
- [Source: github.com/pydantic/pydantic-ai @ v2.27.0 — pydantic_ai_slim/pyproject.toml] — `requires-python >=3.10`, `pydantic>=2.12`, `anyio>=4.7.0`, `httpx>=0.27`, `opentelemetry-api>=1.28.0`, `exceptiongroup>=1.2.2; python_version < "3.11"`; extras `google → google-genai>=1.70.0`, `openai`/`openrouter → openai>=2.45.0`, `logfire → logfire[httpx]>=4.16.0`
- [Source: github.com/pydantic/pydantic-ai @ v2.27.0 — docs/deferred-tools.md, docs/testing.md, docs/logfire.md, docs/message-history.md, pydantic_ai_slim/pydantic_ai/messages.py] — the exact API surface quoted in *Latest technical information*

## Dev Agent Record

### Agent Model Used

claude-opus-5 (Amelia / bmad-dev-story)

### Debug Log References

**Spike verdict (Task 3 gate):** `uv run --project backend/spikes/agent_runtime pytest`
→ **8 passed** in 1.76s, zero network. All seven AC1 capabilities `pass`. Full
verdict table, negative controls and the capability-5 ownership split are in
`docs/AGENT-RUNTIME-DECISION.md`.

**Negative controls run because all eight spike tests passed first try.** A proof
that has never failed has not been tested:

| Control | Result |
|---|---|
| Capability 7 with `include_content=True` | 4 spans either way; prompt + tool args **leak** when `True`, absent when `False` — the assertion is sensitive to the setting, not to span silence |
| Capability 4 via `to_jsonable_python(all_messages())` | leaks `part_kind`, PydanticAI's own discriminator; `OwnedTurnV1.to_json()` leaks nothing |
| Task 7 whitelist → blacklist mutation | `CompactionPart` sentinel survives; the whitelist guard goes **red**, the other four hidden-reasoning tests stay green — exactly the blind spot a blacklist has |
| Task 9 guard given a real `from pydantic_ai.messages import ModelResponse` in `application/ports/` | **3 tests fail**; reverted, 14 pass on the shipped tree |

**Two defects found and fixed during implementation, both mine, not the framework's:**

1. The demonstration tool was first written `@tool_plain(requires_approval=True)`
   — unconditional approval. That made every budget test suspend on the first
   tool call instead of looping, so budget exhaustion was never reachable.
   Changed to conditional approval (`raise ApprovalRequired` when `repeat > 1`),
   which lets one tool prove both the bounded-loop and deferred-call seams and is
   closer to AD-10's persisted state machine anyway.
2. `test_instrumentation_...` initially used a stray `pytest.importorskip`
   expression statement. Replaced with a hard import — Story 1.11's "a skipped
   test is not a passed test" applies to the guard itself.

**Baseline re-derivation caught a false alarm.** The first post-lock run read
424 passed / 28 skipped against a recorded 425 / 27. The delta was **not** the
new dependency: `test_evidence_binding.py:350` self-skips with "binding realism
check needs a clean tree", and the tree was dirty. Confirmed by the final clean
-tree run.

### Completion Notes List

**Verdict: the framework can carry our agent loop without becoming a product
contract.** All seven capabilities cleared at 2.27.0; the seed replacement is
authorized and locked; the boundary that keeps the answer true is executable.

**AC coverage**

- **AC1** — spike proved all seven capabilities before anything entered a
  manifest (Tasks 1–3), then `pydantic-ai-slim[google,openrouter]==2.27.0` was
  pinned exactly (Task 4). `git diff backend/uv.lock` contains **zero removed
  lines** — a pure addition. `openai` 2.45.0, `google-genai` 2.10.0, `pydantic`
  2.13.4, `httpx` 0.28.1 and `anyio` 4.14.1 all unmoved, as the decision doc
  predicted from the `openai>=2.45.0` exact-floor analysis.
- **AC2** — `AgentRuntime` port + owned contracts contain no framework type;
  `backend/llm/**` and `backend/services/**` show a **zero-line diff** and their
  five named test files pass unchanged (91 passed).
- **AC3** — `backend/tests/architecture/test_agent_runtime_boundaries.py`
  enforces framework-freedom, one-way dependency direction, domain purity, and
  the contract-field rule. Demonstrated red **and** green.
- **AC4** — hidden reasoning discarded by whitelist; sentinel absent from all
  six surfaces the story enumerates, and the positive half asserted so
  "discarded everything" cannot pass.

**Capability 5 is an adapter obligation, and that is recorded rather than
hidden.** PydanticAI's `UsageLimits` has no deadline field, so the framework
cannot distinguish wall-time from budget exhaustion on its own. The adapter owns
the deadline via `CancellationToken`; `RunCancelled` → `timed_out` and
`UsageLimitExceeded` → `failed` + `budget_exhausted`, mapped **by exception
type**, never by string-matching a message. The story anticipated this case and
asked which side owns it — the answer is the adapter.

**One dependency added beyond the story's list, with approval:**
`opentelemetry-sdk` in `backend/pyproject.toml` `[dependency-groups] dev`. Task 7
requires asserting the sentinel reaches no *emitted span attribute*, but only the
no-op `opentelemetry-api` arrives transitively — without the SDK nothing is
recorded and the guard could only read the settings object, which proves nothing.
Test-tier only, never `[project].dependencies`, and not the Logfire SDK (Story 5.1).

**Two corrections to the story's Task 1 pre-flight table**, both recorded in the
decision doc: `exceptiongroup` was already locked at 1.3.1 (not absent), and
`logfire-api` arrives as a base dependency. `logfire-api` is the upstream **no-op
shim**, not the Logfire SDK — no exporter, no client, no config — so it does not
claim Story 5.1's gate. The `logfire` SDK itself is absent from the lock, verified.

**Variance from AR26, deliberate and recorded** (as the story instructs): the
architecture suite lives at `backend/tests/architecture/`, not the spine's
root-level `tests/architecture/`. pytest runs from `backend/` with
`testpaths = ["tests"]`, and `backend/conftest.py` is what makes backend modules
importable; a root-level suite would need its own conftest, a `testpaths` change,
and a second rootdir convention. AC3's own list does not name `tests/architecture`.
A later story adding a root-level suite may promote it.

**Spike directory disposition: committed, not deleted.** It is the reproducible
evidence behind the seed-replacement decision, and the decision doc is worth less
without a runnable proof beside it. It carries its own `pyproject.toml` and
`uv.lock`, sits outside `testpaths`, and is never imported by backend code.

**Scope held.** No capability registry, no `CapabilityManifestV1`, no
`ActivityItemV1`/`PersistedEventV1`/`JobLeaseV1`, no `backend/evals/` or
`backend/worker/` scaffolding, no migration, no CI workflow, no frontend change,
no Logfire SDK. `settings.py` gained `agent_runtime_*` fields — its own seam's
configuration, with `llm_provider`/`llm_model` untouched.

### File List

**New**

- `docs/AGENT-RUNTIME-DECISION.md`
- `backend/spikes/agent_runtime/pyproject.toml`
- `backend/spikes/agent_runtime/uv.lock`
- `backend/spikes/agent_runtime/conftest.py`
- `backend/spikes/agent_runtime/owned.py`
- `backend/spikes/agent_runtime/tests/test_capabilities.py`
- `backend/application/contracts/agent_runtime.py`
- `backend/application/ports/agent_runtime.py`
- `backend/agent/__init__.py`
- `backend/agent/runtime.py`
- `backend/agent/translate.py`
- `backend/tests/architecture/__init__.py`
- `backend/tests/architecture/test_agent_runtime_boundaries.py`
- `backend/tests/test_agent_runtime_port.py`
- `backend/tests/test_agent_runtime_adapter.py`
- `backend/tests/test_agent_runtime_hidden_reasoning.py`

**Modified**

- `backend/pyproject.toml` — pinned `pydantic-ai-slim[google,openrouter]==2.27.0`; `opentelemetry-sdk` in the dev group
- `backend/uv.lock` — pure addition, no version moved
- `backend/settings.py` — `agent_runtime_*` fields + `_optional_int`/`_optional_float` helpers
- `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md` — Stack table PydanticAI row
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status tracking
- `_bmad-output/implementation-artifacts/2-1-establish-the-owned-agent-runtime-boundary.md` — this file

**Not modified (verified zero-line diff):** `backend/llm/**`, `backend/services/**`,
`backend/domain/**`, every frontend file, every migration.

## Change Log

| Date | Change |
|---|---|
| 2026-08-09 | Story created. Two creation-time decisions recorded: spike targets PydanticAI **2.27.0** rather than the 2.14.1 seed (under AD-19's replacement clause), and a failed spike **halts and escalates** rather than triggering a fallback. |
| 2026-08-10 | Spike passed all seven AC1 capabilities (8 tests, no network); seed replacement authorized and `pydantic-ai-slim[google,openrouter]==2.27.0` locked with no other version moved. Added the owned `AgentRuntime` port + contracts, the `backend/agent/` adapter, whitelist hidden-reasoning discard, and an executable boundary suite demonstrated both red and green. `backend/llm/**` and `backend/services/**` unchanged (zero-line diff). One approved extra dev dependency: `opentelemetry-sdk`, test-tier only, so the telemetry guard can assert on emitted spans. Status → review. |
