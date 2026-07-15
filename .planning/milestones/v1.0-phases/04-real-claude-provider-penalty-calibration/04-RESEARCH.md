# Phase 4: Real LLM Provider (free-tier first) + Penalty Calibration - Research

**Researched:** 2026-07-06
**Domain:** Google Gemini function-calling SDK integration behind an existing provider-neutral seam; CP-SAT soft-penalty calibration
**Confidence:** MEDIUM (SDK/model facts CITED against official docs; calibration values are inherently empirical/ASSUMED until run against the fixture; package age signal corrected but registry-tool verdict is SUS)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** First real provider = Google Gemini via the Google AI Studio free-tier
  API key. Registered in `create_provider()` under a new name (e.g. `"gemini"`)
  alongside `"stub"`. Chosen over Anthropic-direct (no free tier) and AWS Bedrock
  (pulls Phase-5 deploy/IAM concerns forward; deferred).
- **D-02:** Gemini's native function calling drives `parse_constraints`; its text
  generation drives `generate_insights`. The vendor's function-call payload is
  translated to provider-neutral `list[OverrideCall]` at the seam — no vendor
  payload crosses `LLMProvider` (upholds Phase 1 D-08/D-09).
- **D-03:** SDK = the current Google GenAI Python SDK (`google-genai`). Researcher
  must confirm the exact current SDK package + function-calling API and the
  current model id via Context7 before the planner commits syntax.
- **D-04:** `get_llm_provider` (currently hardcodes `"stub"`) becomes env-driven —
  e.g. `LLM_PROVIDER` with default `"stub"` so CI stays keyless. Extend the
  `Settings` dataclass (currently filesystem-only) with the provider name, model
  id, and API key (read fresh per call, matching the existing env-override
  pattern).
- **D-05:** Replace the stale default model `claude-sonnet-4-6` (matches no
  current model) with a current Gemini model as the default (a fast/cheap
  Flash-tier model is fine for tool-use parsing + short insights). Exact id →
  researcher confirms. The setting name should read provider-generically rather
  than `ANTHROPIC_MODEL` (e.g. `LLM_MODEL` or `GEMINI_MODEL`).
- **D-06:** Parity no longer means "byte-parity with Claude `tool_use`." It means
  the live Gemini provider's parse path yields the same `OverrideCall` results
  as the stub for the same input text. The neutral `OverrideCall` output is the
  contract, not the vendor payload shape.
- **D-07 (open for planner/researcher):** The Phase-1 `StubLLMProvider` currently
  emits a Claude-shaped `tool_use` payload. Decide whether to (a) re-point the
  stub to Gemini's function-call shape so the same translation function is
  exercised by both stub and live provider (strongest parity signal), or (b) keep
  the stub Claude-shaped and give Gemini its own adapter. Preference: whatever
  makes stub and live share one parse/translation path. Not locked — planner call.
- **D-08:** Calibrate the four weights (`MIN_WORKERS_PENALTY`, `LOCK_SHIFT_PENALTY`,
  `EXCLUDE_WORKER_PENALTY`, `MAX_HOURS_PENALTY`, all currently `100_000`/`50_000`
  placeholders) against the committed full-week fixture via a small calibration
  harness/script that sweeps weights, plus a couple of regression-test
  assertions: a satisfiable override is honored; an unsatisfiable one degrades
  gracefully to baseline coverage (respected, not dominating the round-2 cost
  objective). Calibration uses the real engine + stub LLM → no API key → stays
  in CI.
- **D-09:** Mark the single live test `@pytest.mark.live`, excluded from the
  default run (`-m "not live"`), and env-gated to skip when the Gemini API key
  is absent. It exercises the same parse path as the stub and asserts the D-06
  reframed parity. Only a developer with a key set runs it.
- **Folded WR-05:** Add real-engine test for ENG-05 degeneracy detection against
  the full-week fixture — the same surface the calibration harness (D-08) sets
  up, so it's a natural fit here.

### Claude's Discretion

- Exact calibration weight values and the sweep/search strategy (D-08).
- The precise env var names (`LLM_PROVIDER` / `LLM_MODEL` vs `GEMINI_*`) and
  `Settings` field shapes (D-04/D-05), within the "default stub, keyless CI" rule.
- D-07 stub-shape decision (Gemini-shaped stub vs separate adapter).
- Insight prose wording (already bounded by Phase-3 D-03/D-04 + the D-06 guard).

### Deferred Ideas (OUT OF SCOPE)

- **Provider fallback gateway** — a composite `FallbackProvider([...])` behind the
  same `LLMProvider` seam that rotates to another free provider on rate-limit
  (HTTP 429). Next phase. Build options to evaluate then: hand-rolled
  `FallbackProvider` (no new dep), LiteLLM (open-source gateway, fallback chains
  + unified interface, self-hostable), or OpenRouter (hosted).
- **Per-customer free-trial + quota management** — customers/tenants, auth,
  per-customer key or usage metering. None of this exists in the codebase.
  Future milestone.
- **AWS Bedrock transport** for Claude — same Anthropic Messages/`tool_use`
  format via the `anthropic` SDK's Bedrock client; add when AWS deploy lands
  (Phase 5).
- **Anthropic-direct Claude provider** — trivial future
  `create_provider("claude")` branch once a paid key is in play.
- **WR-04 — Harden scenario fixture path against traversal** — reviewed, not
  folded into this phase; unrelated to provider/calibration work.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LLM-02 | A real, network-backed provider (Google Gemini free tier first) sits behind the `LLMProvider` Protocol with a config-driven provider + model id (default provider `stub` so CI stays keyless; a current Gemini model as the default real provider). Claude and other vendors remain trivial future swaps behind the same seam | Standard Stack (SDK version/install), Architecture Patterns (Gemini adapter + `create_provider` branch + env-driven `get_llm_provider`), Code Examples (client construction, function-calling call, insight text-generation call) |
| ENG-04 | Overrides enter the correct lexicographic round with calibrated penalty weights (respected, but not dominating the cost objective) | Common Pitfalls (penalty-scale reasoning), Code Examples (calibration harness sketch), Validation Architecture (regression assertions), Runtime state N/A (greenfield calibration, not migration) |
| TEST-04 | One live-provider integration test exists but is excluded from the default CI run | Don't Hand-Roll (pytest marker plumbing), Validation Architecture (marker registration + `-m "not live"` default), Code Examples (gated live test skeleton) |

REQUIREMENTS.md and ROADMAP.md text for LLM-02/TEST-04 have **already been
reworded provider-generically** (STATE.md "Roadmap Evolution" log confirms this
happened before this research pass) — the ⚠ flag in CONTEXT.md's canonical_refs
is now resolved; no doc-reconciliation task is needed in the plan.
</phase_requirements>

## Summary

Google's current Python SDK for Gemini is **`google-genai`** (import as
`from google import genai`), published by the official `googleapis` GitHub org.
`genai.Client(api_key=...)` (or a bare `genai.Client()` picking up
`GEMINI_API_KEY`/`GOOGLE_API_KEY` from the environment) is the entry point.
Function calling is driven by `types.FunctionDeclaration` + `types.Tool`, passed
into `client.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(tools=[tool]))`;
the model's structured call comes back as `response.function_calls[0]` with
`.name` and `.args` (a plain dict) — this is the shape the Gemini provider
translates into a provider-neutral `OverrideCall`, mirroring exactly what
`StubLLMProvider._to_override_call` already does for the Claude-shaped
`tool_use` dict. `generate_insights` is a second, tool-less
`generate_content` call over the run's metrics summary. **`gemini-2.5-flash`**
is the recommended default model id: it is free-tier eligible, stable
(non-preview), and is the model used throughout the SDK's own function-calling
examples — a safer choice than the newer `gemini-3.5-flash` (also free-tier
per the current pricing page, but comparatively unproven in this SDK's
documented tool-use flow at time of writing).

The four penalty constants in `config/constants.py` already flow into
`CpSatBuilder._build_objectives` as terms added **only** to `round2_cost` (never
`round1_unmet`), each behind a bounded-slack variable — this is the mechanism
that guarantees an override can never make the model infeasible, and it is
already correct; ENG-04 is purely about the *magnitude* of the four
`C.*_PENALTY` constants, not the wiring. Calibration should be a small script
that sweeps candidate weight scales against the committed full-week fixture
(`data/sample_tiny_input.json`, loaded via `ingest.input_adapter.load_problem`)
plus two pytest regression assertions exercising the real `CpSatEngine` (not a
hand-built mirror problem) — one proving a satisfiable override is honored, one
proving an unsatisfiable override degrades to bounded slack without doubling
total cost. The same fixture + real-engine setup satisfies the folded WR-05
degeneracy test, which today only unit-tests a *copy* of the detection loop
(`test_engine_degenerate.py`), not `CpSatEngine.solve()` itself.

TEST-04's live/CI split is a standard pytest pattern: register a `live` marker
in `pyproject.toml`, set `addopts = -m "not live"` so a bare `pytest` invocation
excludes it by default, and skip the test at runtime (`pytest.mark.skipif`) when
`GEMINI_API_KEY` is unset — this project has no CI workflow file yet, so the
`addopts` default is the only enforcement point today.

**Primary recommendation:** Add a `GeminiLLMProvider` in `llm/gemini.py` using
`google-genai` v2.10.0+, default model `gemini-2.5-flash`, sharing one
`name → OverrideCall` translation helper with (a refactored) `StubLLMProvider`;
extend `Settings` with `llm_provider` / `llm_model` / `llm_api_key` env fields;
calibrate the four `config/constants.py` penalties with a sweep script +
real-engine regression tests against `data/sample_tiny_input.json`; gate the one
live test behind a registered `live` pytest marker excluded by default.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Provider selection (stub vs gemini) | API / Backend (`api/deps.py` DI seam) | — | `get_llm_provider` is the existing FastAPI dependency seam; provider choice is a backend config concern, never exposed to callers |
| Gemini SDK client + function-call translation | API / Backend (`llm/gemini.py`) | — | Vendor SDK calls are infrastructure; the `LLMProvider` Protocol (also backend-tier) is the only crossing point into services |
| NL → `OverrideCall` translation | API / Backend (`llm/` package) | Domain (`domain/overrides.py` — the neutral type) | Translation logic lives in the vendor adapter; the *type* it produces is domain-owned so engine code has no llm import |
| Penalty weight values | Database / Storage tier equivalent (`config/constants.py`, static config) | Domain (`engine/cpsat/builder.py` consumes them) | Constants are configuration data consumed by the solver; calibration is an offline/DevOps concern, not a runtime service |
| Calibration harness | API / Backend (`backend/` scripts, real engine + stub LLM) | — | Runs entirely server-side against a committed fixture; no browser/CDN tier involved |
| Live test gating | API / Backend (pytest infra) | — | Test-runner configuration; no user-facing tier |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-genai` | 2.10.0 [VERIFIED: PyPI JSON API — `pypi.org/pypi/google-genai/json`, `requires_python: >=3.10`] | Official Python client for the Gemini Developer API (client construction, `generate_content`, function calling) | Official `googleapis` GitHub org package; the SDK named in D-03 and confirmed live via Context7 (`/googleapis/python-genai`, benchmark 78.64, "High" source reputation) [CITED: github.com/googleapis/python-genai] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none new) | — | — | No other new runtime dependency is required — `pytest` (already a dev dependency) covers the calibration regression tests and the gated live test |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `google-genai` | `google-generativeai` (the older, now-legacy Gemini SDK) | Deprecated in favor of `google-genai`; do not use — training-data familiarity with the old package name is a common hallucination trap here [ASSUMED — not directly re-verified this session beyond Context7 resolving only to `google-genai`/`python-genai`] |
| Direct `generate_content` + `types.Tool` (used here) | The newer `client.interactions.create(...)` "Interactions API" shown in some SDK README snippets | Interactions API is a newer, chat-session-oriented surface (`previous_interaction_id` threading); `generate_content` + `FunctionDeclaration` is the longer-established, single-call pattern that matches this project's single-shot `parse_constraints(text) -> list[OverrideCall]` contract — no multi-turn state to manage |
| `gemini-2.5-flash` (recommended default) | `gemini-3.5-flash` | Both are free-tier per the current pricing page [CITED: ai.google.dev/gemini-api/docs/pricing]; `gemini-3.5-flash` is GA and newer but the SDK's own function-calling examples still default to `gemini-2.5-flash`/`gemini-2.5-flash` in most snippets — pick the more-proven one for a Flash-tier tool-use workload and let `LLM_MODEL` make swapping trivial |

**Installation:**
```bash
cd backend
uv add google-genai
```

**Version verification:** confirmed directly against the PyPI JSON API (`https://pypi.org/pypi/google-genai/json`) — `info.version == "2.10.0"`, `info.requires_python == ">=3.10"` (compatible with this project's `>=3.10,<3.13` pin). First release `0.0.1` was `2024-12-10`; 108 releases as of `2026-06-24` — the package is ~19 months old, actively maintained, not a slopsquat despite the legitimacy-check "too-new" flag below (see Package Legitimacy Audit).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|--------------|---------|-------------|
| `google-genai` | PyPI | First release 2024-12-10 (~19 months); latest 2.10.0 published 2026-06-24; 108 total releases [VERIFIED: PyPI JSON API, cross-checked against Context7-resolved `/googleapis/python-genai`] | Not reported by the legitimacy tool (`weeklyDownloads: null`) | `github.com/googleapis/python-genai` (official Google org) | `SUS` (tool signals: `too-new`, `unknown-downloads`) | **Kept — flag for `checkpoint:human-verify` before install, per protocol** |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `google-genai` — the automated legitimacy
check's `too-new` signal is a metadata artifact: it evaluated only the **latest**
release's publish timestamp (`2026-06-24`, i.e. version `2.10.0`'s release date),
not the package's actual first-publish date. Manually checking the full PyPI
release history shows the package has existed since **2024-12-10** with 108
cumulative releases and is maintained under the official `googleapis` GitHub
org — the same package Context7 independently resolved as the current,
documented Gemini Python SDK. This is almost certainly a false positive from
the tool's "newest version age" heuristic rather than a real slopsquat signal,
but per the Package Legitimacy Protocol the verdict must still be surfaced and
the planner **must** insert a `checkpoint:human-verify` task immediately before
the `uv add google-genai` install step so a human confirms the package identity
before it lands in `pyproject.toml`.

*Every model-id and version claim from WebSearch/WebFetch below without a
Context7/PyPI citation is tagged `[ASSUMED]` per the provenance rule and listed
in the Assumptions Log.*

## Architecture Patterns

### System Architecture Diagram

```
NL text (POST /constraints)
        │
        ▼
constraint_service.parse_and_store(provider, text)
        │
        ├─▶ provider.parse_constraints(text)   ◀── LLMProvider Protocol (unchanged)
        │        │
        │        ├── name == "stub"  → StubLLMProvider: regex match → shared
        │        │                     _translate(name, args) → OverrideCall
        │        │
        │        └── name == "gemini" → GeminiLLMProvider:
        │                 1. genai.Client(api_key=settings.llm_api_key)
        │                 2. client.models.generate_content(
        │                        model=settings.llm_model,
        │                        contents=text,
        │                        config=GenerateContentConfig(
        │                            tools=[FIVE_TOOL_DECLARATIONS],
        │                            tool_config=ToolConfig(mode="ANY"),
        │                            automatic_function_calling=disable(True),
        │                        ))
        │                 3. for fc in response.function_calls:
        │                        shared _translate(fc.name, dict(fc.args))
        │                        → OverrideCall  (SAME helper as stub, D-07/D-06)
        │
        ▼
list[OverrideCall]  (provider-neutral — no vendor payload past this point)
        │
        ▼
constraint_service: resolve human tokens → real ids, validate bounds (VAL-01/02)
        │
        ▼
ScenarioRepo.update_overrides(...)  → persisted; unchanged by this phase
        │
        ▼ (on next run)
run_service → SolverConfig(overrides=[...]) → CpSatBuilder.build()
        │
        ▼
round2_cost += C.MIN_WORKERS_PENALTY * shortfall_terms
            += C.LOCK_SHIFT_PENALTY   * lock_terms
            += C.EXCLUDE_WORKER_PENALTY * excl_terms
            += C.MAX_HOURS_PENALTY   * maxh_terms   ◀── ENG-04 calibration target
        │
        ▼
solve_lexicographic: round1 (unmet) locked → round2 (cost, incl. penalties) minimized
```

Insight generation (unchanged flow, provider swap only):
```
GET /runs/{id}/insights → insight_service.get_or_generate(provider, run)
        │
        ▼
provider.generate_insights(summary: dict) -> str
        │
        ├── stub: deterministic string built from summary["metrics"]
        └── gemini: client.models.generate_content(model=..., contents=<prompt
                     built from summary>, config=GenerateContentConfig())  — NO
                     tools/function-calling; plain text generation
        │
        ▼
_grounding_guard(report, metrics)  ◀── unchanged; still the safety net regardless
        of which provider produced the text (Phase 3 D-06, provider-agnostic)
```

### Recommended Project Structure

```
backend/
├── llm/
│   ├── base.py          # LLMProvider Protocol + create_provider() — add "gemini" branch
│   ├── stub.py          # StubLLMProvider — D-07: re-point to call the shared translate helper
│   ├── translate.py     # NEW — shared `_to_override_call(name: str, args: dict) -> OverrideCall`
│   │                     #        (moved out of stub.py so gemini.py can import it too)
│   └── gemini.py        # NEW — GeminiLLMProvider: client construction, tool declarations,
│                         #        parse_constraints + generate_insights
├── settings.py           # extend Settings: llm_provider, llm_model, llm_api_key
├── api/deps.py           # get_llm_provider() reads settings.llm_provider (env-driven, D-04)
├── config/constants.py   # four *_PENALTY constants — values updated by calibration (D-08)
├── scripts/               # NEW (or backend/calibration/) — calibrate_penalties.py sweep harness
└── tests/
    ├── test_llm_provider.py          # existing — extend for shared translate() helper
    ├── test_gemini_provider.py       # NEW — unit tests for GeminiLLMProvider using a fake
    │                                  #        genai.Client (no network), + one @pytest.mark.live test
    └── test_penalty_calibration.py   # NEW — real CpSatEngine + full-week fixture regression
                                       #        assertions (D-08) + folded WR-05 degeneracy test
```

### Pattern 1: Shared translation helper (D-07 resolution)

**What:** Extract the stub's `_to_override_call(block: dict)` into a shared,
provider-agnostic `translate.py::to_override_call(name: str, args: dict) -> OverrideCall`
that both `StubLLMProvider` and `GeminiLLMProvider` call. The stub still builds
its internal Claude-shaped `tool_use` dict for readability/back-compat with
existing tests (`call.tool`, `call.args`, `call.id` — the *public* `OverrideCall`
fields TEST-01 actually asserts on are unchanged), but the final translation
step becomes `to_override_call(tool_use_block["name"], tool_use_block["input"])`.
Gemini's provider calls the identical `to_override_call(fc.name, dict(fc.args))`
for each `fc` in `response.function_calls`.

**When to use:** Whenever both providers must guarantee they hit *the same
code path* to produce an `OverrideCall` from a `(name, args)` pair — this is
exactly D-06/D-07's "strongest parity signal."

**Example:**
```python
# llm/translate.py
from __future__ import annotations
from domain.overrides import OverrideCall, override_id

def to_override_call(tool_name: str, args: dict) -> OverrideCall:
    """Single translation point shared by every LLMProvider implementation.

    No vendor payload shape (Claude tool_use dict, Gemini FunctionCall object)
    crosses into this function — callers extract (name, args) first, upholding
    D-08/D-09 (Phase 1) and D-02 (Phase 4): only provider-neutral data crosses
    the LLMProvider boundary.
    """
    return OverrideCall(id=override_id(tool_name, args), tool=tool_name, args=args)
```

```python
# llm/stub.py (excerpt) — only the last line of _to_override_call changes
from llm.translate import to_override_call
...
tool_use_block = {"type": "tool_use", "id": ..., "name": "set_min_workers_per_task",
                   "input": {"task_id": task_token, "n": n}}
results.append(to_override_call(tool_use_block["name"], tool_use_block["input"]))
```

### Pattern 2: Gemini provider — forced, non-auto-executing function calling

**What:** Gemini's SDK will *automatically execute* Python callables passed
directly as `tools=[...]`. Because this provider must only classify/extract
arguments (the actual execution is `constraint_service`'s resolve/validate
step, not the LLM's job), declare tools via `types.FunctionDeclaration` (data,
not a callable) and force the model to attempt a call via
`tool_config=ToolConfig(function_calling_config=FunctionCallingConfig(mode="ANY"))`,
with `automatic_function_calling=AutomaticFunctionCallingConfig(disable=True)`
as a defense-in-depth guard against the SDK auto-invoking anything.

**When to use:** `parse_constraints(text)` — never for `generate_insights`
(no tools needed there).

**Example:**
```python
# Source: Context7 /googleapis/python-genai — "Declare a Function and Pass as
# a Tool (Python)" + "Disable Automatic Function Calling in ANY Mode (Python)"
from google import genai
from google.genai import types

_TOOL_SCHEMAS = [
    types.FunctionDeclaration(
        name="set_min_workers_per_task",
        description="Require at least N workers on a given task at every demanded hour.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task name or id, e.g. 'Pick'"},
                "n": {"type": "integer", "description": "Minimum worker headcount"},
            },
            "required": ["task_id", "n"],
        },
    ),
    # ... one FunctionDeclaration per remaining tool: scale_demand,
    # lock_worker_shift, exclude_worker_from_task, set_max_hours
]

class GeminiLLMProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def parse_constraints(self, text: str) -> list[OverrideCall]:
        response = self._client.models.generate_content(
            model=self._model,
            contents=text,
            config=types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=_TOOL_SCHEMAS)],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="ANY")
                ),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        calls = response.function_calls or []
        return [to_override_call(fc.name, dict(fc.args)) for fc in calls]

    def generate_insights(self, summary: dict) -> str:
        prompt = _build_insight_prompt(summary)   # plain-text prompt, no tools
        response = self._client.models.generate_content(model=self._model, contents=prompt)
        return response.text
```

### Pattern 3: Env-driven provider selection (D-04/D-05)

**What:** `get_llm_provider()` currently hardcodes `create_provider("stub")`.
Make it read `settings.llm_provider` (fresh per call, matching the existing
`Settings` pattern), defaulting to `"stub"` so CI/tests never require a key.

**Example:**
```python
# settings.py (excerpt)
@dataclass(frozen=True)
class Settings:
    db_path: str
    data_dir: str
    llm_provider: str   # NEW — "stub" (default) | "gemini"
    llm_model: str       # NEW — default "gemini-2.5-flash"
    llm_api_key: str | None  # NEW — from GEMINI_API_KEY; None for stub

def default_settings() -> Settings:
    ...
    return Settings(
        db_path=db_path, data_dir=data_dir,
        llm_provider=os.environ.get("LLM_PROVIDER", "stub"),
        llm_model=os.environ.get("LLM_MODEL", "gemini-2.5-flash"),
        llm_api_key=os.environ.get("GEMINI_API_KEY"),
    )
```
```python
# api/deps.py (excerpt)
def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return create_provider(settings.llm_provider, settings=settings)
```
```python
# llm/base.py (excerpt)
def create_provider(name: str, *, settings=None) -> LLMProvider:
    if name == "stub":
        from llm.stub import StubLLMProvider
        return StubLLMProvider()
    if name == "gemini":
        from llm.gemini import GeminiLLMProvider
        return GeminiLLMProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    raise ValueError(f"Unknown LLM provider: {name!r}. Available: ['stub', 'gemini']")
```

**Env var naming (Claude's discretion, D-04/D-05):** recommend
`LLM_PROVIDER` / `LLM_MODEL` (provider-generic, matches the ask in D-05) plus
`GEMINI_API_KEY` specifically for the key — this matches the SDK's *own*
auto-detected env var name (see Code Examples), so no name-translation layer
is needed and a bare `genai.Client()` would even work without the explicit
`api_key=` kwarg (explicit pass-through via `Settings` is still recommended for
testability — it is what every other seam in this codebase does).

### Anti-Patterns to Avoid

- **Passing Python callables directly as Gemini `tools=[...]`:** the SDK will
  auto-execute them and return only the final text/response, hiding the raw
  function-call arguments this project needs to translate to `OverrideCall`.
  Always pass `types.FunctionDeclaration` (schema, not code) + disable
  automatic function calling.
- **Letting a vendor-shaped object (Claude `tool_use` dict, Gemini `FunctionCall`)
  leak past the provider module:** violates the Phase 1 D-08/D-09 seam
  guarantee this phase is required to uphold (D-02). Always convert to
  `OverrideCall` before returning from `parse_constraints`.
- **Adding overrides to `round1_unmet` instead of `round2_cost`:** would let an
  NL constraint override degrade demand coverage, contradicting ENG-03/ENG-04 and
  this project's explicit "soft, cost-round-only" design. (Already correctly
  avoided in the current `builder.py` — flagged here only as a regression trap
  during calibration edits.)
- **Using an unbounded overflow/shortfall slack variable for a penalty term:**
  the existing code already bounds every override's slack var (`short`, `absent`,
  `over`) — calibration must never remove these bounds even while tuning the
  weight constant, since an unbounded slack with an astronomically large
  coefficient is how a naive "just raise the penalty" fix silently reintroduces
  infeasibility risk or numerical instability in CP-SAT's integer objective.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Gemini function-calling schema/tool-use plumbing | A hand-rolled prompt asking Gemini to emit JSON and manually regex/`json.loads` it out of the text response | `types.FunctionDeclaration` + `types.Tool` + `response.function_calls` | The SDK's native structured function-calling is more reliable than prompting for free-text JSON, and is the officially documented pattern (Context7) |
| Splitting default vs. live test runs | A custom `if os.environ.get("RUN_LIVE_TESTS")` branch inside test bodies, or a separate `test_live/` directory excluded via `testpaths` | pytest's built-in marker system: register `live` in `pyproject.toml`, use `@pytest.mark.live`, set `addopts = -m "not live"` | Standard, well-understood pytest mechanism; composes with `pytest -m live` to opt in explicitly, and with `pytest.mark.skipif` for the env-key gate — no custom test-collection logic needed |
| Weight calibration search | An ad-hoc "try numbers until it looks right" loop with no persisted record | A small, committed sweep script (`backend/scripts/calibrate_penalties.py`) that logs (weight, honored?, cost-delta) rows for a documented candidate set, plus the two regression assertions that lock in the chosen values | Keeps the calibration reproducible and reviewable; the two pytest assertions are the actual CI-enforced contract, the script is documentation of how they were derived |

**Key insight:** Both hand-roll temptations in this phase (parsing raw JSON out
of LLM text, and writing bespoke live/CI test switching) are solved by
features the SDK and pytest already ship — the actual engineering work here is
translation-layer glue and empirical constant-tuning, not new infrastructure.

## Common Pitfalls

### Pitfall 1: Automatic function execution swallows the arguments you need

**What goes wrong:** Passing a real Python function object as a Gemini tool
(rather than a `FunctionDeclaration`) causes the SDK to call it automatically
and return the *result* of your function in the response text, not the raw
`(name, args)` pair — `response.function_calls` may come back empty because
the round-trip already completed.
**Why it happens:** `google-genai`'s automatic function calling is a
convenience feature for agent-style loops (SDK infers you want it invoked and
its result folded back into the conversation), which is the wrong default for
a provider whose whole job is validate-before-execute (VAL-01/02).
**How to avoid:** Always declare tools via `types.FunctionDeclaration` (schema
only, no attached callable) and set
`automatic_function_calling=AutomaticFunctionCallingConfig(disable=True)`
explicitly — belt-and-braces even though declarations without callables
shouldn't auto-execute.
**Warning signs:** `response.function_calls` is empty/`None` for input text
that clearly maps to a tool; `response.text` contains a plausible-looking
answer instead of raising for missing tool call.

### Pitfall 2: Model declines to call any tool for ambiguous/no-match text

**What goes wrong:** Unlike the deterministic regex stub (which always either
matches or returns `[]`/a `_clarification` sentinel per fragment), Gemini in
default `AUTO` tool-calling mode may choose to answer in plain text instead of
calling a function, especially for genuinely ambiguous input (mirroring
NLC-03/NLC-05's "no constraint found" / "clarification needed" paths from
Phase 2). `mode="ANY"` (forcing a call) can actually make this *worse* by
forcing a spurious tool call on truly non-constraint text.
**Why it happens:** `ANY` mode tells the model "you must call one of the
provided functions" — appropriate when you're confident text maps to *a*
tool, but wrong for input the stub would legitimately route to
`no_constraint_found`.
**How to avoid:** Given this phase's `parse_constraints` contract already
tolerates zero-or-more `OverrideCall`s per call (the stub returns `[]` for
`"hello there"`), prefer `mode="AUTO"` over `mode="ANY"` for `parse_constraints`
so the model can legitimately decline, and treat an empty
`response.function_calls` as "no constraint found" (matches NLC-03) rather
than forcing a call — revisit this against D-06's live-test parity assertion
during planning: `mode="ANY"` may still be needed if the specific text used in
the one live/parity test is unambiguous.
**Warning signs:** The live test flakes because the model sometimes answers in
prose instead of calling a tool for the exact fixture-text used in the test.

### Pitfall 3: Grounding guard rejects a real (but poorly-phrased) insight

**What goes wrong:** The D-06 grounding guard (Phase 3, `insight_service.py`,
provider-agnostic, unchanged this phase) rejects any numeric token in the
generated text that isn't traceable to the run's own metrics (within
tolerance). A live LLM is far more likely than the deterministic stub to
introduce a plausible-looking-but-fabricated number (e.g., restating a
percentage with different rounding, or inventing a headcount).
**Why it happens:** `generate_insights` prompts a live model with the summary
dict as context, but nothing in the SDK enforces "only ever cite numbers
present in this dict" — that is prompt-engineering plus the existing guard.
**How to avoid:** Prompt the model explicitly to cite exact figures from the
supplied summary and avoid computing new numbers/percentages itself; rely on
the unchanged `_grounding_guard` as the actual enforcement mechanism (it will
correctly raise `InsightGenerationError` — status 502 — for a fabricated
number without touching run status, per INS-02, which this phase does not
change).
**Warning signs:** The one live/gated insight-adjacent path (if any is
exercised) fails the grounding guard intermittently across runs.

### Pitfall 4: Penalty weight tuned to "always win" defeats the lexicographic guarantee's *spirit*

**What goes wrong:** Simply multiplying the existing `100_000`/`50_000`
placeholders by 10x or 100x "to make sure the override sticks" can make an
override's effective cost so large that *any* schedule satisfying it is chosen
over the genuinely cheapest wage-cost solution by many orders of magnitude —
technically still "soft" (never touches round 1 / never infeasible per
ENG-03), but functionally indistinguishable from a hard constraint in
round-2's cost ranking, which is exactly what ENG-04 says to avoid
("respected, but not dominating the round-2 cost objective").
**Why it happens:** The existing code comments in `constants.py` already
document the intended calibration target — "large enough that assigning one
extra body... beats the marginal wage cost... yet not so large it dominates
the entire round-2 cost objective" — but the actual multiplier was never
empirically checked against the full-week fixture's real wage-cost magnitudes
(`sv.eff_h * wage_per_hour * COST_SCALE`, `COST_SCALE=100`).
**How to avoid:** The calibration harness should compute, for the committed
fixture, the typical *baseline total_cost* (wage-only, no overrides) and size
each `*_PENALTY` constant relative to it (e.g., a single override's maximum
possible penalty contribution should be a small multiple — not two-plus orders
of magnitude — of baseline total_cost) rather than picking a round number in
isolation.
**Warning signs:** The "unsatisfiable override degrades gracefully" regression
assertion (D-08) still passes today's `100_000` constants because the slack
variables are bounded — but a calibration blind to wage-cost magnitude could
still produce a technically-passing-but-absurd result (e.g., total round-2
cost jumping 50x from a single override) that the two required regression
assertions might not catch unless one of them explicitly checks the
cost-delta bound (recommended in Validation Architecture below).

### Pitfall 5: Testing calibration against the wrong fixture size

**What goes wrong:** The hand-built tiny problems in `test_engine_overrides.py`
(2 members, 1 task, 8h horizon) prove *direction* (override honored vs. not)
but their wage-cost magnitudes are nothing like the committed full-week
fixture's (11 members, 6 tasks, 3 families, 168h horizon, `~420KB` JSON). A
calibration derived only from the tiny hand-built problems risks weights that
are miscalibrated at full-week scale (design.md notes the full-week fixture's
round-2 cost-optimal solve takes ~2 minutes — a materially different cost
surface than an 8-hour toy problem).
**Why it happens:** The existing override-honor tests (Phase 2,
`test_engine_overrides.py`) were written to prove *mechanism* correctness
cheaply, not to be reused unmodified as the calibration ground truth.
**How to avoid:** ENG-04/D-08 explicitly names the **committed full-week
fixture** (`data/sample_tiny_input.json`, loaded via
`ingest.input_adapter.load_problem`) as the calibration target — the sweep
script and the two regression assertions must load this real problem, not the
hand-built ones.
**Warning signs:** Regression assertions pass in seconds against a tiny
hand-built problem but the actual production-scale schedule still shows
override penalties dwarfing or being dwarfed by wage costs.

## Runtime State Inventory

> Not applicable — this phase adds a new provider branch and tunes constants;
> it is not a rename/refactor/migration phase. No stored data, live service
> config, OS-registered state, secret renames, or stale build artifacts are in
> scope. **Nothing found in any category** — confirmed by reading
> `llm/base.py`, `api/deps.py`, `settings.py`, and `config/constants.py`
> directly: none of these hold vendor-specific data that would need migrating
> when `"gemini"` is added alongside `"stub"` (additive change only).

## Code Examples

### Client construction (Gemini Developer API, API-key auth)

```python
# Source: Context7 /googleapis/python-genai — "Create a client for Gemini
# Developer API"
from google import genai

client = genai.Client(api_key='GEMINI_API_KEY_VALUE')
```

### Handling the function-call response and (optionally) round-tripping a result

```python
# Source: Context7 /googleapis/python-genai — "Handle Model Function Call and
# Pass Response Back (Python)" — NOTE: this project does not need the
# round-trip (it never calls generate_content a second time with a
# function_response); parse_constraints only needs step 1, reading
# response.function_calls directly. Included here to show the full SDK
# contract in case a future multi-turn clarification flow (NLC-08, v2 scope,
# out of scope for Phase 4) revisits this.
from google.genai import types

function_call_part = response.function_calls[0]
print(function_call_part.name, function_call_part.args)
```

### Env-var auto-detection (documents why explicit pass-through is still preferred)

```python
# Source: Context7 /googleapis/python-genai — "Create a client using
# environment variables"
from google import genai
client = genai.Client()   # auto-reads GEMINI_API_KEY or GOOGLE_API_KEY
                           # (GOOGLE_API_KEY wins if both set)
```

### Registering the `live` pytest marker and default exclusion

```toml
# backend/pyproject.toml — ADD to [tool.pytest.ini_options]
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "live: exercises a real network-backed LLM provider; excluded by default (run with `pytest -m live`)",
]
addopts = "-m \"not live\""
```

```python
# backend/tests/test_gemini_provider.py (skeleton)
import os
import pytest

_HAS_KEY = bool(os.environ.get("GEMINI_API_KEY"))

@pytest.mark.live
@pytest.mark.skipif(not _HAS_KEY, reason="GEMINI_API_KEY not set — live test requires a real key")
def test_gemini_parse_constraints_matches_stub_parity():
    from llm.base import create_provider
    from settings import default_settings

    settings = default_settings()  # picks up LLM_MODEL / GEMINI_API_KEY from env
    gemini = create_provider("gemini", settings=settings)
    stub = create_provider("stub")

    text = "at least 2 on Pick"
    gemini_calls = gemini.parse_constraints(text)
    stub_calls = stub.parse_constraints(text)

    # D-06 parity: same neutral OverrideCall shape, not byte-identical vendor payload
    assert len(gemini_calls) == len(stub_calls) == 1
    assert gemini_calls[0].tool == stub_calls[0].tool == "set_min_workers_per_task"
    assert gemini_calls[0].args["n"] == stub_calls[0].args["n"] == 2
    # task_id token matching is looser (LLM phrasing may vary casing/wording) —
    # constraint_service's substring resolver (VAL-02) handles this either way
```

### Calibration harness skeleton (D-08)

```python
# backend/scripts/calibrate_penalties.py (sketch — not a test; a documentation/
# derivation script the two regression assertions in test_penalty_calibration.py
# encode the conclusions of)
from ingest.input_adapter import load_problem
from domain.overrides import OverrideCall, override_id
from engine.base import SolverConfig, create_engine

FIXTURE = "data/sample_tiny_input.json"

def run_case(problem, overrides, penalty_overrides: dict[str, int]):
    import config.constants as C
    saved = {k: getattr(C, k) for k in penalty_overrides}
    for k, v in penalty_overrides.items():
        setattr(C, k, v)
    try:
        engine = create_engine("cpsat")
        return engine.solve(problem, SolverConfig(time_limit_s=60, overrides=overrides))
    finally:
        for k, v in saved.items():
            setattr(C, k, v)

if __name__ == "__main__":
    problem = load_problem(FIXTURE)
    baseline = run_case(problem, [], {})
    print("baseline total_cost:", baseline.metrics.total_cost)
    for scale in (10_000, 50_000, 100_000, 250_000, 500_000):
        args = {"task_id": "<a real demanded task id from the fixture>", "n": 3}
        ov = OverrideCall(id=override_id("set_min_workers_per_task", args),
                           tool="set_min_workers_per_task", args=args)
        r = run_case(problem, [ov], {"MIN_WORKERS_PENALTY": scale})
        delta = (r.metrics.total_cost or 0) - (baseline.metrics.total_cost or 0)
        print(f"scale={scale:>8}  total_cost_delta={delta:.2f}  status={r.status}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `google-generativeai` (legacy Gemini SDK) | `google-genai` (unified Gemini Developer API + Vertex AI SDK) | Google's stated migration direction ahead of this session; `google-generativeai` is the deprecated package name most likely to appear in stale training data | Any generated code importing `google.generativeai` instead of `from google import genai` is using the wrong, deprecated package — a documented hallucination/staleness trap for this exact SDK [ASSUMED — not independently re-verified via a dedicated deprecation-notice fetch this session; inferred from Context7 resolving cleanly only to `google-genai`/`python-genai` and no lingering official docs surfaced for the old package name] |
| `gemini-2.0-flash` | `gemini-2.5-flash` / `gemini-3.5-flash` | `gemini-2.0-flash` and `gemini-2.0-flash-lite` shut down 2026-06-01 [CITED: WebSearch summary of ai.google.dev models page, dated within this session] | The stale `claude-sonnet-4-6` default this phase replaces would have needed updating again soon even if it *had* been a real Gemini id — always read the model id from config (`LLM_MODEL`), never hardcode one past this phase's default |

**Deprecated/outdated:**
- `google-generativeai`: superseded by `google-genai`; do not install or import.
- `gemini-2.0-flash`, `gemini-2.0-flash-lite`: shut down 2026-06-01; do not default to these even if seen in older examples/training data.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `google-generativeai` is deprecated in favor of `google-genai` | State of the Art | Low — Context7 only resolved the new package; if wrong, worst case is a redundant note, not a broken plan (the plan already targets `google-genai` regardless) |
| A2 | Free-tier numeric rate limits for `gemini-2.5-flash` (≈10 RPM / 250K TPM / 1,500 RPD) | Standard Stack / Summary | Low-Medium — sourced from third-party aggregator blogs, not the official numeric rate-limit page (Google's own page defers to the AI Studio dashboard); if these numbers are stale, the live test (single call, gated, developer-run only) is unaffected either way — only matters if the planner adds a higher-volume live smoke test |
| A3 | `gemini-3.5-flash`'s function-calling behavior is "comparatively unproven" relative to `gemini-2.5-flash` in this SDK version | Standard Stack (Alternatives Considered) | Low — this is a qualitative risk-aversion judgment, not a factual claim; if wrong, the only cost is picking the second-best free, valid default (either model is confirmed free-tier and confirmed to exist) |
| A4 | `mode="AUTO"` (rather than `mode="ANY"`) is the right default for `parse_constraints` to preserve NLC-03/NLC-05-style "no constraint found" behavior | Common Pitfalls #2 | Medium — this is a design recommendation for the planner to validate against the one live test's exact input text; if `AUTO` causes the live parity test to flake (model answers in prose instead of calling a tool), the planner should switch that specific call to `mode="ANY"` and treat empty-response-text-with-no-tool-call as an explicit non-match instead |

**If empty:** N/A — see table above; four assumptions logged, none blocking, all
flagged for planner confirmation as noted.

## Open Questions

1. **Should `mode="ANY"` or `mode="AUTO"` drive `parse_constraints`?**
   - What we know: `ANY` guarantees a function-call response (good for the
     D-06 live-parity test's simple honored case) but forces a call even on
     genuinely non-constraint text (bad for NLC-03 parity, which this phase
     does not explicitly require Gemini to replicate but shouldn't obviously
     regress either).
   - What's unclear: whether TEST-04's single live test only needs to cover the
     "honored" case (in which case `ANY` is simplest and sufficient) or should
     also probe a no-match case (in which case `AUTO` is needed).
   - Recommendation: default to `AUTO` for production `parse_constraints`
     (safer, avoids forcing spurious calls); if the planner's single live test
     only exercises unambiguous constraint text, either mode works for passing
     that specific test — pick `AUTO` for production correctness regardless.

2. **Exact calibration weight values.**
   - What we know: the mechanism (bounded slack vars, cost-round-only
     placement) is already correct; only magnitudes are unset. The fixture,
     load path, and rough wage-cost order of magnitude (`eff_h * wage_per_hour
     * COST_SCALE=100`, wages observed in `test_engine_overrides.py` fixtures
     around $35–45/h) are known.
   - What's unclear: the exact final integer constants — genuinely an
     empirical output of running the sweep script against the real fixture,
     not something researchable in advance.
   - Recommendation: planner creates the sweep script + two regression
     assertions as executable tasks; the actual chosen constants are a plan
     *output*, not a plan *input*.

3. **Does the stub-shape refactor (D-07 Pattern 1) risk breaking any currently
   passing Phase 1–3 test?**
   - What we know: `test_llm_provider.py` and `test_engine_overrides.py` assert
     only on the public `OverrideCall` fields (`tool`, `args`, `id`) and on
     `StubLLMProvider.name`/`parse_constraints` behavior — none inspect the
     internal `tool_use` dict shape directly.
   - What's unclear: whether any other test (not read in full this session)
     imports `llm.stub._to_override_call` directly by name.
   - Recommendation: planner should `grep -rn "_to_override_call"
     backend/tests/` before refactoring to confirm no test imports the private
     helper directly; this research did not find such a reference in the two
     test files read (`test_llm_provider.py`, `test_engine_overrides.py`), but
     did not exhaustively grep every test file.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| `google-genai` (Python package) | `GeminiLLMProvider` (LLM-02) | ✗ (not yet installed in `backend/.venv`) | — (target: 2.10.0) | `uv add google-genai` — planner task, gated behind the `checkpoint:human-verify` from the Package Legitimacy Audit |
| `GEMINI_API_KEY` (env var / secret) | Live provider construction + the one `@pytest.mark.live` test | Unknown — not checked this session (would require reading a real secret) | — | Default CI/dev path (`LLM_PROVIDER=stub`) requires no key at all; the live test self-skips via `pytest.mark.skipif` when absent (D-09) — no blocking dependency |
| `uv` (package manager) | Installing `google-genai` | ✓ (project already uv-managed per `backend/pyproject.toml` + `uv.lock`) | — | — |
| Network access to `generativelanguage.googleapis.com` | Only the one live test + real ad-hoc manual runs | Unknown — not checked this session | — | Stub provider requires none; live test self-skips without a key, which typically also means no network attempt is made |

**Missing dependencies with no fallback:** none — every dependency above either
has a documented fallback (stub provider, self-skipping live test) or is a
one-line `uv add` the planner schedules as a task.

**Missing dependencies with fallback:**
- `google-genai` not yet installed — fallback is simply: add it (task), default
  CI (`LLM_PROVIDER=stub`) is entirely unaffected either way.
- `GEMINI_API_KEY` presence unknown — fallback is the existing stub default;
  the live test is explicitly designed to be the *only* thing that needs it.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already a dev dependency, `backend/pyproject.toml`) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` — needs a new `markers` list + `addopts = "-m \"not live\""` (Wave 0 gap) |
| Quick run command | `cd backend && uv run pytest -q` (already excludes `live` once `addopts` is added) |
| Full suite command | `cd backend && uv run pytest -q` (same — this project has no separate "full" tier; the calibration regression tests run in the default suite since they use only the real engine + stub LLM, no network) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|--------------|
| LLM-02 | `create_provider("gemini", settings=...)` returns a `GeminiLLMProvider`; `get_llm_provider()` reads `settings.llm_provider` (default `"stub"`, keyless) | unit | `pytest tests/test_gemini_provider.py -k "not live" -x` | ❌ Wave 0 (new file) |
| LLM-02 | Switching `LLM_PROVIDER=gemini` requires no service/route code change (seam holds) | integration | `pytest tests/test_api.py -x` (existing dependency-override pattern proves route/service code is provider-agnostic already; extend with an explicit `LLM_PROVIDER` env-swap assertion) | ✅ existing, extend |
| ENG-04 | A satisfiable override (e.g. reachable `set_min_workers_per_task`) is honored against the full-week fixture | integration (real engine) | `pytest tests/test_penalty_calibration.py::test_satisfiable_override_honored -x` | ❌ Wave 0 (new file) |
| ENG-04 | An unsatisfiable override degrades to bounded baseline coverage without dominating round-2 cost | integration (real engine) | `pytest tests/test_penalty_calibration.py::test_unsatisfiable_override_degrades_gracefully -x` | ❌ Wave 0 (new file) |
| ENG-05 (folded WR-05) | Real `CpSatEngine.solve()` against the full-week fixture (with a deliberately starved task) produces a populated `warnings` list — not just the mirrored detection-loop unit test | integration (real engine) | `pytest tests/test_penalty_calibration.py::test_real_engine_degeneracy_detected -x` | ❌ Wave 0 (new file) |
| TEST-04 | One live-provider test exercises the real Gemini parse path and confirms `OverrideCall` parity with the stub for the same text | live (excluded by default) | `pytest tests/test_gemini_provider.py -m live` (requires `GEMINI_API_KEY`) | ❌ Wave 0 (new file) |

### Sampling Rate

- **Per task commit:** `cd backend && uv run pytest -q -k "not live"` (fast:
  excludes the full-week-fixture calibration tests too if they're slow — see
  note below on time-limiting them)
- **Per wave merge:** `cd backend && uv run pytest -q` (full default suite,
  still excludes `live` via `addopts`)
- **Phase gate:** `cd backend && uv run pytest -q` green (no key needed);
  developer optionally runs `pytest -m live` locally with `GEMINI_API_KEY` set
  before considering TEST-04 fully exercised end-to-end

**Timing note:** design.md documents the full-week fixture taking ~20s for
round-1-optimal and ~2 min for round-2-cost-optimal at full precision. The
calibration/degeneracy regression tests should use a bounded `time_limit_s`
(e.g. 30–60s) — per `objective.py`'s solve-and-lock design, a round-2 timeout
still returns the round-1-locked snapshot with *a* cost value (not the
provably optimal one), which is sufficient to assert direction/bounds
(honored vs. not, cost-delta below a threshold) without needing full
optimality every CI run.

### Wave 0 Gaps

- [ ] `backend/pyproject.toml` — register the `live` marker + `addopts = "-m \"not live\""`
- [ ] `backend/llm/translate.py` — shared `to_override_call(name, args)` helper (D-07)
- [ ] `backend/llm/gemini.py` — `GeminiLLMProvider` implementation
- [ ] `backend/tests/test_gemini_provider.py` — unit tests (fake client, no
      network) + the one `@pytest.mark.live` test
- [ ] `backend/tests/test_penalty_calibration.py` — real-engine regression
      assertions against `data/sample_tiny_input.json` (D-08 + folded WR-05)
- [ ] `backend/scripts/calibrate_penalties.py` (or equivalent) — sweep harness
      documenting how the final constants in `config/constants.py` were chosen

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | no | This phase adds a server-to-vendor API key, not end-user authentication (single-tenant, no sessions — unchanged design.md §3.7 constraint) |
| V3 Session Management | no | No session state introduced |
| V4 Access Control | no | No new access-control surface; `get_llm_provider` selection is server config, not user-controllable |
| V5 Input Validation | yes | NL text still flows through the **unchanged** `constraint_service` VAL-01/VAL-02 validation (bounds + real-id resolution) regardless of which provider produced the `OverrideCall` — Gemini's output gets exactly the same scrutiny the stub's output always has |
| V6 Cryptography | no (secrets-handling, adjacent) | The Gemini API key is a bearer secret read from an env var (`GEMINI_API_KEY`), never logged, never persisted to SQLite/JSON, and never returned in any API response — same pattern this project already uses for no other secret today (first one introduced this phase) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| Prompt injection via NL constraint text causing Gemini to emit an out-of-schema tool call or wildly out-of-bounds argument (e.g., negative `n`, absurd `max_hours`) | Tampering | Already fully mitigated by the existing, provider-agnostic `constraint_service` validation (VAL-01: bounds checks on `n`, `factor`, `max_hours`, `day`; VAL-02: real-id resolution) — this phase adds no new validation gap because the seam is unchanged; Gemini output is just another `list[OverrideCall]` subjected to the same checks |
| API key leakage via logs, error messages, or exception text | Information Disclosure | Read the key only into `Settings.llm_api_key` (never interpolated into f-strings that could land in a log or an `InsightGenerationError`/`HTTPException` message); the existing error-handling convention already wraps provider exceptions generically (`except Exception as exc: raise InsightGenerationError(f"Provider failed: {exc}")` in `insight_service.py`) — verify the Gemini SDK's own exception `__str__` never embeds the API key (standard for well-behaved SDKs; not independently verified this session — flag as a code-review check, not a blocking research gap) |
| Denial of wallet / free-tier quota exhaustion via repeated live calls in CI | Denial of Service (cost-shaped, not availability-shaped) | TEST-04's marker-gating (`live` excluded by default) is itself the mitigation — default CI makes zero network calls to Gemini; only a developer explicitly running `pytest -m live` with a key present incurs any quota usage |
| Fabricated/ungrounded numeric content in LLM-authored insight text reaching an end user as if it were real run data | Tampering (of trust in output, not of data) | Already mitigated, unchanged, by the Phase 3 `_grounding_guard` (D-06) — provider-agnostic and re-verified as unchanged by this phase (Pitfall 3 above) |

## Sources

### Primary (HIGH confidence)
- PyPI JSON API (`https://pypi.org/pypi/google-genai/json`) — package version
  `2.10.0`, `requires_python`, full release history (108 releases,
  `2024-12-10` → `2026-06-24`) [VERIFIED: npm/PyPI-equivalent registry query,
  run directly this session]
- `gsd-tools query package-legitimacy check --ecosystem pypi google-genai` —
  verdict `SUS` with signals `too-new`/`unknown-downloads`, repo
  `github.com/googleapis/python-genai` [VERIFIED: tool output, this session]

### Secondary (MEDIUM confidence)
- Context7 `/googleapis/python-genai` (resolved via `resolve-library-id`,
  benchmark 78.64, "High" source reputation) — client construction, env-var
  auto-detection (`GEMINI_API_KEY`/`GOOGLE_API_KEY`), `FunctionDeclaration` +
  `Tool` + `GenerateContentConfig` function-calling pattern, `ToolConfig`
  `mode="ANY"` + `AutomaticFunctionCallingConfig(disable=True)` [CITED:
  github.com/googleapis/python-genai README/docs, fetched via Context7 this
  session]
- `https://ai.google.dev/gemini-api/docs/pricing` (via WebFetch) — confirms
  `gemini-2.5-flash` and `gemini-3.5-flash` both list a Free tier
  [CITED: ai.google.dev/gemini-api/docs/pricing]

### Tertiary (LOW confidence)
- `https://ai.google.dev/gemini-api/docs/models` (via WebFetch, summarized) —
  current model roster, `gemini-2.0-flash`/`gemini-2.0-flash-lite` shutdown
  date `2026-06-01` [ASSUMED — WebFetch summary of an official page, not a
  direct quote verified against raw HTML this session]
- WebSearch aggregator results (pecollective.com, aifreeapi.com, tokenmix.ai,
  laozhang.ai blog posts) — free-tier numeric rate limits (~10 RPM / 250K TPM
  / 1,500 RPD for Flash models) [ASSUMED — third-party blogs, not Google's own
  numeric rate-limit page, which explicitly defers to the AI Studio dashboard]

## Metadata

**Confidence breakdown:**
- Standard stack (SDK package/version): HIGH — directly verified against PyPI's
  JSON API and cross-confirmed via Context7's independent resolution to the
  same package
- Architecture (function-calling pattern, client construction): MEDIUM — CITED
  against official Context7-fetched docs, but this project's exact prompt/tool
  schema wording is new code, not something the docs specify
- Model id choice (`gemini-2.5-flash`): MEDIUM — free-tier status is CITED
  against the official pricing page; the "prefer 2.5 over 3.5" judgment itself
  is a risk-aversion recommendation (A3), not a hard fact
- Pitfalls (auto-execution, AUTO vs ANY mode, grounding guard): MEDIUM-HIGH —
  the SDK mechanics (Pitfall 1) are CITED docs; the AUTO/ANY tradeoff
  (Pitfall 2) is reasoned from the docs plus this project's existing NLC-03/05
  contract, not independently tested against a live model this session
- Calibration approach (ENG-04): MEDIUM — the *mechanism* (bounded slack,
  cost-round-only placement) is VERIFIED by reading `builder.py`/`objective.py`
  directly; the *specific weight values* are inherently unresearchable in
  advance (Open Question 2) — this is expected and correctly deferred to a
  plan-time executable task, not a research gap

**Research date:** 2026-07-06
**Valid until:** 30 days (2026-08-05) — Gemini model availability/free-tier
terms and SDK versions move fast; re-verify model id and SDK version via
Context7/PyPI if planning is delayed materially past this window
