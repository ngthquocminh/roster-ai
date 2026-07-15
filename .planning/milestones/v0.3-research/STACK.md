# Stack Research — Phase 3 LLM Layer

**Domain:** LLM integration layer for Python/FastAPI scheduling backend
**Researched:** 2026-06-28
**Confidence:** MEDIUM (model IDs and SDK API syntax verified via Context7 against official `anthropic-sdk-python` source; Protocol patterns confirmed via stdlib docs; model-selection rationale is well-supported engineering judgment)

> **Scope:** This document covers the NEW additions for Phase 3 only. The existing
> stack (Python 3.10–3.12, OR-Tools CP-SAT 9.11.4210, FastAPI, SQLite WAL, uv)
> is established and unchanged. Every item below is tagged **confirm-baseline** or
> **propose-change**.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Status | Purpose | Rationale |
|------------|---------|--------|---------|-----------|
| `anthropic` Python SDK | latest (`uv add anthropic`) | **confirm-baseline** | HTTP client for Claude API; provides typed `Anthropic` / `AsyncAnthropic` clients, `ToolUseBlock`, `MessageParam` types | Official SDK from Anthropic; correct typed interface for tool_use blocks; no alternative is production-appropriate for Claude |
| Python `typing.Protocol` (stdlib) | Python 3.10+ (already required) | **confirm-baseline** | `LLMProvider` seam; structural subtyping so `ClaudeProvider` and `StubProvider` both satisfy the Protocol without inheritance | Built into the stdlib, matches the pattern already used by `SchedulerEngine`; avoids adding any framework dependency for the seam itself |
| `pydantic` v2 | already in use via FastAPI | **confirm-baseline** | Validate tool-call parameters before applying to the solver (reject unknown member/task IDs, enforce numeric bounds) | Already a dependency via FastAPI; Pydantic v2 models make the 5 tool-call schemas self-documenting and validator-enforced |

### Default Claude Model ID

**Recommended default: `claude-sonnet-4-6`**

| Model | ID | Use case fit | Cost tier | Verdict |
|-------|----|-------------|-----------|---------|
| Claude Opus 4.8 | `claude-opus-4-8` | Maximum reasoning depth | Highest | Reserve for ambiguous/complex constraint NL; overkill for this task set |
| **Claude Sonnet 4.6** | **`claude-sonnet-4-6`** | **Strong tool-use, clear schemas** | **Mid** | **DEFAULT — right balance for NL→5-tool parsing and insight generation** |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | Speed-optimised | Lowest | Acceptable fallback for high-frequency or cost-sensitive deployments; use `claude-haiku-4-5` (alias) |

Rationale for `claude-sonnet-4-6` as default:

- The constraint-parsing task is deterministic-by-design: the model must pick from exactly 5 well-defined tools with a closed set of parameters. This is well within Sonnet's capability — Opus 4.8 would be paying for reasoning depth that the task does not require.
- Insight generation (metrics → natural-language report) is also Sonnet-tier: it is templated narrative over structured data, not open-ended analysis.
- All three IDs are verified in the SDK's `ModelParam` TypeAlias (`src/anthropic/types/model_param.py`). The default **must be config-driven** via an `ANTHROPIC_MODEL` environment variable (or settings object) so operators can override it without code changes.

Model IDs verified from `anthropic-sdk-python` `ModelParam` (MEDIUM confidence, Context7 against official source):

```
claude-opus-4-8       # newest Opus
claude-opus-4-7
claude-opus-4-6
claude-sonnet-4-6     # ← recommended default
claude-haiku-4-5
claude-haiku-4-5-20251001
claude-opus-4-5 / claude-opus-4-5-20251101
claude-sonnet-4-5 / claude-sonnet-4-5-20250929
claude-opus-4-1 / claude-opus-4-1-20250805
claude-opus-4-0 / claude-opus-4-20250514
claude-sonnet-4-0 / claude-sonnet-4-20250514
claude-3-haiku-20240307   # legacy, avoid for new work
```

### `LLMProvider` Protocol Definition

**confirm-baseline** — the design.md Protocol seam pattern is the correct approach. Concrete shape:

```python
# backend/llm/base.py
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass
class ParseResult:
    """Validated output from NL constraint parsing."""
    tool_calls: list[dict]   # [{"name": str, "input": dict}, ...]
    raw_text: str            # for logging / debug

@dataclass
class InsightResult:
    """Structured natural-language insight report."""
    summary: str
    sections: dict[str, str]  # e.g. {"coverage": "...", "cost": "..."}

@runtime_checkable
class LLMProvider(Protocol):
    """Vendor-swap seam for LLM calls. Claude is the default; Gemini is a
    documented future alternative. Implementations must not raise on a missing
    API key when used in test mode — that is the stub's responsibility."""

    def parse_constraints(
        self,
        nl_text: str,
        scenario_context: dict,   # member IDs, task IDs, current overrides
    ) -> ParseResult: ...

    def generate_insights(
        self,
        metrics: dict,
        scenario_name: str,
    ) -> InsightResult: ...
```

Notes on the shape:
- Synchronous interface is preferred here because `parse_constraints` and `generate_insights` are called from the worker thread (same thread that runs the CP-SAT solve), not from the FastAPI event loop. No `async def` needed; avoids a nested event-loop problem.
- `scenario_context` carries the live member/task ID lists so the caller, not the provider, owns validation of the returned tool-call parameters.
- Keep `ParseResult.raw_text` for logging; never store it in the DB — it may contain user input.

### Tool-Use API Pattern (Anthropic SDK)

**confirm-baseline** — the design calls for NL → named tool calls. The SDK supports this natively:

```python
# backend/llm/claude_provider.py
import os
from anthropic import Anthropic
from anthropic.types import ToolUseBlock

CONSTRAINT_TOOLS = [
    {
        "name": "lock_worker_shift",
        "description": "Lock a specific worker to a specific shift slot.",
        "type": "custom",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["member_id", "shift_start_h", "shift_end_h"],
            "properties": {
                "member_id":      {"type": "string"},
                "shift_start_h":  {"type": "number"},
                "shift_end_h":    {"type": "number"},
            },
        },
    },
    # ... set_min_workers_per_task, exclude_worker_from_task,
    #     scale_demand, set_max_hours defined similarly
]

class ClaudeProvider:
    def __init__(self, model: str, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self._model = model   # e.g. "claude-sonnet-4-6"

    def parse_constraints(self, nl_text: str, scenario_context: dict) -> ParseResult:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=self._system_prompt(scenario_context),
            messages=[{"role": "user", "content": nl_text}],
            tools=CONSTRAINT_TOOLS,
            # Do NOT force tool_choice here — let the model decide if the
            # NL actually maps to a tool; if it returns text, treat as
            # "no constraint found" rather than a forced (wrong) call.
        )
        tool_calls = [
            {"name": block.name, "input": block.input}
            for block in msg.content
            if isinstance(block, ToolUseBlock)
        ]
        raw = next((b.text for b in msg.content if hasattr(b, "text")), "")
        return ParseResult(tool_calls=tool_calls, raw_text=raw)
```

Key SDK facts (MEDIUM confidence, verified via Context7):
- `tools` is a list of dicts with `name`, `description`, `type`, `input_schema` (JSON Schema).
- `tool_choice={"type": "tool", "name": "..."}` forces a specific tool — use only when you know exactly which tool must be called; omit it for open-ended parsing.
- `block.type == "tool_use"` or `isinstance(block, ToolUseBlock)` — both work. `ToolUseBlock` is the typed form.
- `block.input` is `Dict[str, object]` — validate with Pydantic before passing to the solver.
- Do NOT use `parse_response()` (the structured-output helper) for tool-use; it is for JSON schema text output, not tool calls. These are two separate paths in the SDK.

### Stubbing the Provider for CI

**confirm-baseline** — the design mandates a stub with no live API calls. The Protocol seam makes this trivial:

```python
# backend/tests/stubs.py
from backend.llm.base import LLMProvider, ParseResult, InsightResult

class StubLLMProvider:
    """Deterministic stub. Satisfies LLMProvider Protocol via structural typing;
    no inheritance or mocking framework required."""

    def __init__(self, tool_calls: list[dict] | None = None, insight: str = "stub insight"):
        self._tool_calls = tool_calls or []
        self._insight = insight

    def parse_constraints(self, nl_text: str, scenario_context: dict) -> ParseResult:
        return ParseResult(tool_calls=self._tool_calls, raw_text="[stub]")

    def generate_insights(self, metrics: dict, scenario_name: str) -> InsightResult:
        return InsightResult(summary=self._insight, sections={})
```

This stub is injected via the same FastAPI dependency-injection seam already used for `get_engine` — no `monkeypatch` required. Tests that need a bad-parse scenario instantiate `StubLLMProvider(tool_calls=[{"name": "...", "input": {"bad_id": "UNKNOWN"}}])` and verify that the service rejects it at the validation layer.

**Do NOT** use `respx_mock` or `httpx` HTTP mocking for the provider in unit tests — that mocks the HTTP layer, which means the test is tightly coupled to the SDK's internal transport. The Protocol stub approach is more stable and portable.

---

## Supporting Libraries

| Library | Version | Purpose | When to Use | Status |
|---------|---------|---------|-------------|--------|
| `pydantic` v2 | already installed (FastAPI dep) | Validate tool-call parameter structs (member IDs, numeric bounds) | Always — every `ParseResult.tool_calls` entry passes through a Pydantic model before reaching the solver | **confirm-baseline** |
| `pytest` + `pytest-anyio` | already installed (dev dep) | Async test support if async provider variant needed | Only if async provider is added; current design is sync | **confirm-baseline** (no change needed for sync path) |

### Libraries Explicitly NOT Added

| Package | Why Not | Alternative |
|---------|---------|-------------|
| `langchain` / `llama-index` | Abstraction layer for Claude tool-use adds complexity with no benefit for a fixed-5-tool schema. SDK is already the right level of abstraction. | `anthropic` SDK directly |
| `openai` SDK | Wrong vendor for this project. Only add if a second provider (e.g., OpenAI GPT) is added behind the Protocol seam. | N/A |
| `instructor` | Useful for multi-field structured output via function calling; over-engineered for a deterministic 5-tool schema. | `anthropic` SDK tool_use directly |
| `respx` (for CI) | HTTP-layer mock is brittle across SDK versions. Protocol stub is more maintainable. | `StubLLMProvider` via dependency injection |

---

## Installation

```bash
# From backend/ directory (uv project root)
uv add anthropic

# anthropic adds no transitive deps that conflict with existing ortools/fastapi/pydantic pins
# Verify after: uv run python -c "import anthropic; print(anthropic.__version__)"
```

No `ANTHROPIC_API_KEY` is needed in CI — the stub is injected and the real provider is never instantiated. Set the key only in local dev and production environments.

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| `anthropic` SDK directly | LangChain / LlamaIndex tool abstraction | 5 fixed tool schemas do not justify the abstraction tax; SDK is typed and stable |
| `claude-sonnet-4-6` default | `claude-opus-4-8` default | Opus 4.8 is the right choice for complex multi-step reasoning; NL→5-tool parsing is not that task; use Opus only if Sonnet consistently misparses ambiguous inputs in testing |
| `claude-sonnet-4-6` default | `claude-haiku-4-5` default | Haiku 4.5 is appropriate for high-volume / low-cost scenarios; accept it as a user-configurable override via `ANTHROPIC_MODEL` env var; not recommended as the out-of-box default for quality |
| Sync `LLMProvider` interface | Async `LLMProvider` | Both the CP-SAT solve and LLM calls run in the worker thread, not the event loop; sync avoids nested-event-loop complexity. If a future FastAPI background-task integration is added, wrap in `asyncio.run_in_executor`. |
| Structural-subtyping `Protocol` stub | `unittest.mock.MagicMock` | Mock objects have no type safety and don't enforce the interface; a real stub class gives mypy and the CI the same contract as the production implementation |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `anthropic` (latest) | Python 3.10–3.12, pydantic v2, fastapi 0.x | Anthropic SDK uses `httpx` internally; no known conflicts with existing deps |
| `anthropic` (latest) | `ortools==9.11.4210` | No overlap; completely separate import trees |

---

## Sources

- `/anthropics/anthropic-sdk-python` (Context7, MEDIUM confidence) — SDK installation, `Anthropic` client constructor, `ModelParam` TypeAlias with all current model IDs, `ToolUseBlock` structure, `tool_choice` syntax, test mock patterns
- Python `typing` stdlib documentation — `Protocol`, `@runtime_checkable`, structural subtyping, PEP 544
- `design.md §4` (this repo) — `LLMProvider` Protocol shape, 5 tool names, soft-constraint mandate, insights-as-separate-step architecture

---

*Stack research for: ShiftMind Phase 3 LLM Layer (NL constraint parsing + insight generation)*
*Researched: 2026-06-28*
