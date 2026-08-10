# Agent Runtime — Seed Replacement Decision

**Status:** ACCEPTED — spike passed 2026-08-10; `2.27.0` locked in `backend/uv.lock`
**Story:** 2.1 — Establish the Owned Agent Runtime Boundary
**Recorded at:** commit `b38500c` (clean tree), 2026-08-10
**Decision owner:** Story 2.1 implementation

---

## The decision

AR19 and AD-19 name **PydanticAI `2.14.1`** as the *seed* version for the agent runtime.
AD-19's closing clause permits substitution:

> *"a different V2 release may replace the seed only with the same evidence."*

**This story replaces the seed with `2.27.0`.**

- `2.14.1` was released 2026-07-21 — one day before the architecture spine was written.
- `2.27.0` is the current release as of 2026-08-09.
- The seven AC1 capabilities were confirmed present at **both** tags before this choice
  was made, so the substitution does not trade away any capability the seed carried.

The phrase *"with the same evidence"* is the binding constraint. It is discharged by
the AC1 capability bar below, proved by a runnable spike rather than asserted.

## The evidence bar

The substitution is only authorized once **all seven** AC1 capabilities are demonstrated
against the *installed* `2.27.0` distribution — not against the documentation site, which
tracks `main`:

| # | Capability |
|---|---|
| 1 | typed tools |
| 2 | deferred calls (suspend, resume with approve **and** deny) |
| 3 | deterministic model doubles |
| 4 | owned-message translation (round-trip through a ShiftMind-owned shape) |
| 5 | bounded execution (wall-time distinguishable from other limit exhaustion) |
| 6 | provider failure mapping |
| 7 | content-disabled instrumentation (asserted on emitted spans) |

**The spike verdict is appended to this file** (see *Spike verdict* below).

If any capability fails, the story halts: the failure is recorded with a reproduction,
`backend/pyproject.toml` and `backend/uv.lock` are left untouched, and the decision is
escalated. A negative result is a valid deliverable — the same posture Story 1.11 held
with `gate_a_passed: false`. No fallback is attempted: no hand-rolled agent loop, no
silent retry at a different version.

## Distribution choice

The dependency under test is **`pydantic-ai-slim[google,openrouter]==2.27.0`**, never the
`pydantic-ai` meta-package.

`pydantic-ai==2.27.0` resolves to
`pydantic-ai-slim[anthropic,cli,evals,google,logfire,mcp,openai,retries,web]`, which would
drag Anthropic, MCP, a CLI, a web-fetch stack, `pydantic-evals`, and the **Logfire SDK**
into a backend that needs none of them. `logfire` is a *planned optional* stack row owned
by Story 5.1; pulling it here would silently claim that gate.

The two extras mirror the two providers the repo already ships:

| Extra | Existing repo module | Underlying SDK |
|---|---|---|
| `google` | `backend/llm/gemini.py` | `google-genai` |
| `openrouter` | `backend/llm/openrouter.py` | `openai` (OpenRouter is OpenAI-compatible) |

A third provider extra would be scope creep.

## Compatibility facts verified before the spike

Verified against the repo at `7f268e0`/`b38500c` so the spike **confirms** rather than
discovers them. Constraints read from the `v2.27.0` tag's `pydantic_ai_slim/pyproject.toml`.

| Constraint (pydantic-ai-slim 2.27.0) | Repo today | Verdict |
|---|---|---|
| `requires-python >=3.10` | venv Python **3.10.9**; `backend/pyproject.toml:5` `>=3.10,<3.13` | compatible |
| `pydantic>=2.12` | locked **2.13.4** | compatible |
| `openai>=2.45.0` (`openai` + `openrouter` extras) | locked **2.45.0** | exact floor — see warning below |
| `google-genai>=1.70.0` (`google` extra) | locked **2.10.0** | compatible |
| `httpx>=0.27` | locked **0.28.1** | compatible |
| `anyio>=4.7.0` | locked **4.14.1** | compatible |
| `opentelemetry-api>=1.28.0` | **absent** | new transitive dependency |
| `exceptiongroup>=1.2.2` (`python_version < "3.11"`) | already locked **1.3.1** | see correction below |

### Corrections to the story's pre-flight table

Two rows in the story's Task 1 table were stated from the spine rather than measured, and
are corrected here:

1. **`exceptiongroup` is not absent.** `backend/uv.lock` already resolves
   `exceptiongroup 1.3.1` on the 3.10 environment. It arrives transitively today, so
   pydantic-ai's `python_version < "3.11"` marker adds no new package — only a new
   requirement edge onto one already present.
2. **`logfire-api` arrives as a base dependency**, which the story's table did not
   anticipate. This is *not* the Logfire SDK. `logfire-api` is the upstream no-op shim
   package: it exposes the Logfire API surface and does nothing unless the real `logfire`
   distribution is also installed. It carries no exporter, no network client, and no
   configuration. Installing it does **not** claim Story 5.1's telemetry-export gate.
   The prohibition in this story is on the `logfire` SDK, which is not installed.

### The `openai` floor — the one thing to watch

The repo declares `openai>=1.40` but the lock already resolved **2.45.0**, which is exactly
pydantic-ai 2.27.0's floor. Resolution therefore should **not** move `openai` at all.

If `uv lock` moves `openai`, `google-genai`, `pydantic`, `httpx`, or `anyio`, the diff is
reported before continuing. `backend/llm/openrouter.py:194` calls
`client.chat.completions.create(...)` and `backend/llm/gemini.py` calls the google-genai SDK
directly; a silent major bump under either is a regression this story did not sign up for.

An unconstrained standalone resolution of `pydantic-ai-slim[google,openrouter]==2.27.0`
(no repo floors applied) selects `openai 2.53.0` and `google-genai 2.17.0`. Those are the
*ceilings the package would accept*, not what the repo lock must adopt — the repo lock
preserves its existing pins because they already satisfy every floor.

## Python-version sensitivity of the lock

The local venv is **Python 3.10.9**, not the 3.12 the spine names as the *container target*.
`backend/pyproject.toml:5` allows `>=3.10,<3.13`; pydantic-ai 2.27.0 needs `>=3.10`, so both
ends of the range work.

`exceptiongroup` is gated on `python_version < "3.11"`, so the resolved dependency **graph**
differs between 3.10 and 3.12 even though the lock covers both. `uv.lock` records the
markers rather than a single flattened set, so this is expressed in the lockfile rather than
hidden by it — but it is worth knowing that a 3.12 container installs a strictly smaller set
than the 3.10 dev venv.

## What this decision does not do

- It does not migrate the existing `LLMProvider` seam. `backend/llm/**` and
  `backend/services/**` keep their current ports, error types, and configuration keys.
  The two seams may share a provider client *inside adapters* (AD-19 permits it) but must
  not share a port, an error type, or a configuration key.
- It does not add the Logfire SDK, a CI workflow, a capability registry, or a migration.
- It does not make PydanticAI a product contract. That is the entire point of the story:
  framework messages, deferred calls, tool objects, checkpoints, and event types never
  become domain, persistence, browser, or audit contracts (AD-19).

---

## Spike verdict

**VERDICT: PASS — all seven capabilities demonstrated. The seed replacement is authorized.**

Measured 2026-08-10 against the **installed** `pydantic-ai-slim 2.27.0`
(`pydantic_ai.__version__ == "2.27.0"`), Python 3.10.9, on a clean tree.
Reproduce with:

```
uv run --project backend/spikes/agent_runtime pytest
```

Result: **8 passed** in 1.76s, zero network calls
(`models.ALLOW_MODEL_REQUESTS = False` in both `conftest.py` and at test module scope).

| # | AC1 capability | Verdict | Spike test |
|---|---|---|---|
| 1 | typed tools | **pass** | `test_capability_1_typed_tools` |
| 2 | deferred calls | **pass** | `test_capability_2_deferred_calls_suspend_and_resume`, `test_capability_2_conditional_approval_via_raise` |
| 3 | deterministic model doubles | **pass** | `test_capability_3_deterministic_model_doubles` |
| 4 | owned-message translation | **pass** | `test_capability_4_owned_message_round_trip` |
| 5 | bounded execution | **pass** (with an adapter obligation — see below) | `test_capability_5_bounded_execution_distinguishes_exhaustion_kinds` |
| 6 | provider failure mapping | **pass** | `test_capability_6_provider_failure_maps_to_owned_type` |
| 7 | content-disabled instrumentation | **pass** | `test_capability_7_instrumentation_excludes_content` |

### Negative controls — the two load-bearing assertions were made to go red

All eight tests passed on their first execution, which is exactly the condition under
which a proof deserves to be distrusted. The two assertions that carry the story's
architectural weight were therefore inverted and confirmed to fail:

**Capability 7 — is the assertion actually sensitive to `include_content`?**

| `include_content` | spans emitted | prompt leaked | tool args leaked |
|---|---|---|---|
| `False` | 4 | no | no |
| `True` | 4 | **yes** | **yes** |

The span *count* is identical either way, so the test is not passing merely because
instrumentation stayed silent. Content genuinely disappears from emitted span attributes
and events when `include_content=False`, and genuinely appears when it is `True`.

**Capability 4 — would the framework-native form actually violate AD-19?**

| Durable form | Framework markers found in JSON |
|---|---|
| `to_jsonable_python(result.all_messages())` — *the shape the docs teach* | `part_kind` |
| `OwnedTurnV1.to_json()` — *the shape we own* | *(none)* |

`part_kind` is PydanticAI's own discriminated-union tag. Persisting that JSON persists a
PydanticAI contract, which is precisely what AD-19 prohibits. The owned form carries no
framework type name, no discriminator, and no import-path string.

### Capability 5 — ownership split, recorded as the story requires

`UsageLimits` at 2.27.0 carries **no deadline or wall-time field**. Its fields are
`request_limit`, `tool_calls_limit`, `input_tokens_limit`, `output_tokens_limit`,
`per_request_input_tokens_limit`, `total_tokens_limit`, `cost_limit`, and
`count_tokens_before_request`.

The framework therefore cannot, by itself, distinguish wall-time exhaustion from budget
exhaustion. Per the story's instruction — *"if the framework cannot distinguish them, that
is an adapter obligation, not a spike failure — record which side owns it"* — the split is:

| AD-7 outcome | Trigger | Framework exception | Owner |
|---|---|---|---|
| `failed` + `budget_exhausted` | token / request / tool-call ceiling | `UsageLimitExceeded` | **framework** |
| `timed_out` | wall-clock deadline elapsed | `RunCancelled` | **adapter** owns the deadline; framework supplies the mechanism |

`Agent.run_sync(..., cancellation_token=CancellationToken())` is the mechanism, and
`RunCancelled` is a distinct exception type from `UsageLimitExceeded` (neither is a
subclass of the other — asserted in the spike). So the adapter can map the two to
different owned outcomes **by type**, never by string-matching an error message.

This is a real obligation on Task 6, not a framework gap that blocks the story.

### Notes carried forward to the adapter

- `InstrumentationSettings` is exported from the package root (`pydantic_ai`) at 2.27.0,
  not only from `pydantic_ai.models.instrumented`. Instrumentation is attached via
  `Agent(..., capabilities=[Instrumentation(settings=...)])` from `pydantic_ai.capabilities`.
- `ModelResponse.parts` can already carry at least eleven part kinds at 2.27.0 —
  `TextPart`, `ThinkingPart`, `ToolCallPart`, `FilePart`, `NativeToolCallPart`,
  `NativeToolReturnPart`, `ToolSearchCallPart`, `ToolSearchReturnPart`,
  `LoadCapabilityCallPart`, `LoadCapabilityReturnPart`, `CompactionPart`. This is the
  concrete argument for whitelist translation: a blacklist naming `ThinkingPart` alone
  would admit the next reasoning-bearing kind the framework adds.
- `ModelResponse` carries `finish_reason` and `state` — useful raw material for the owned
  outcome contract, and both must be *translated*, never stored.
- Approval resumes via
  `run_sync(message_history=..., deferred_tool_results=DeferredToolResults(approvals={call_id: True | ToolDenied(...)}))`.
  The suspend-and-resume form is used, not the in-run `HandleDeferredToolCalls` capability,
  because ShiftMind's approval is a persisted one-time state machine (AD-10).

### Spike directory disposition

`backend/spikes/agent_runtime/` is **committed, not deleted**. It is the reproducible
evidence behind this decision, and this document is worth materially less without a
runnable proof beside it. It carries its own `pyproject.toml` and its own `uv.lock`, sits
outside `backend/pyproject.toml`'s `testpaths = ["tests"]`, and is never imported by
backend code — so it cannot contaminate the backend resolution or the backend test run.
