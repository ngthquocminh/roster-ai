---
title: 'Add Anthropic LLM provider'
type: 'feature'
created: '2026-09-09'
status: 'done'
review_loop_iteration: 0
baseline_commit: '72e3c175bee8d5527af2989eb0ce3a2b8e7c4fff'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/prds/prd-ShiftMind-2026-07-21/prd.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The task-level `LLMProvider` can select only stub, Gemini, or OpenRouter. Deployments that use Anthropic cannot route constraint parsing and insight generation through the existing provider-neutral boundary.

**Approach:** Add an `anthropic` `LLM_PROVIDER` implementation backed by Anthropic's Messages API, with an independent `ANTHROPIC_API_KEY` and a default `ANTHROPIC_MODEL=claude-haiku-4-5-20251001`. Preserve the keyless `stub` default and leave the independently configured PydanticAI AgentRuntime out of scope.

## Boundaries & Constraints

**Always:** Keep vendor request/response types and exceptions inside `backend/llm/anthropic.py`; map vendor failures to `LLMProviderError`; use existing tool names and `to_override_call`/`normalize_args` for provider-neutral output; defer SDK-client creation until a real call; retain deterministic, keyless normal CI; never log or expose API keys.

**Ask First:** Do not add Anthropic to `AGENT_RUNTIME_MODEL`, change model budgets/pricing, or make a live provider the default.

**Never:** Do not alter API routes, frontend contracts, domain/application interfaces, grounding behavior, or current Gemini/OpenRouter semantics. Do not call external Anthropic services in ordinary tests.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Selected provider | `LLM_PROVIDER=anthropic`, valid configured key/model | Factory supplies an `AnthropicLLMProvider` for existing API dependencies | Client creation remains lazy |
| Structured constraint | Anthropic response contains `tool_use` blocks | Each block becomes a normalized provider-neutral `OverrideCall` | Empty/no tool-use content returns `[]` |
| Insight generation | Anthropic response contains one or more text blocks | Text is returned for the existing grounding guard | No text blocks returns `""` |
| Provider failure | Anthropic SDK raises an API error | Existing caller receives only `LLMProviderError` | No vendor details or credentials cross the seam |

</frozen-after-approval>

## Code Map

- `backend/llm/base.py` -- task-level provider registry and neutral provider contract.
- `backend/llm/anthropic.py` -- new Anthropic SDK adapter for tools and insight prose.
- `backend/llm/translate.py` -- existing normalized tool-call translation that must remain the sole conversion point.
- `backend/settings.py` -- environment-to-settings mapping with secret-safe fields.
- `backend/pyproject.toml` and `backend/uv.lock` -- locked backend runtime dependencies.
- `backend/tests/test_anthropic_provider.py` -- isolated fake-client and opt-in live-provider coverage.
- `backend/conftest.py` and `backend/tests/test_content_minimization.py` -- live-test key detection and secret-sanitization canary coverage.
- `backend/.env.example`, `docs/CONFIGURATION.md`, `docs/DEVELOPMENT.md`, and `docs/CI-SECRETS-CHECKLIST.md` -- operator configuration and keyless-CI contract.

## Tasks & Acceptance

**Execution:**
- [x] `backend/llm/anthropic.py` -- implement a lazy Anthropic Messages API adapter that declares the five existing client tools with Anthropic `input_schema`, converts only `tool_use` blocks through the shared translator, joins only text blocks for insights, and maps SDK API exceptions -- preserve the seam and neutral behavior.
- [x] `backend/llm/base.py` and `backend/settings.py` -- register `anthropic`, require settings at factory use, and add secret-safe `ANTHROPIC_API_KEY` plus an independent `ANTHROPIC_MODEL` default of `claude-haiku-4-5-20251001` -- make configuration selectable without invalid Gemini defaults.
- [x] `backend/pyproject.toml` and `backend/uv.lock` -- add and lock the official `anthropic` SDK -- make the adapter installable and reproducible without changing AgentRuntime extras.
- [x] `backend/tests/test_anthropic_provider.py`, `backend/conftest.py`, and `backend/tests/test_content_minimization.py` -- cover factory selection, normalization, empty blocks, text aggregation, neutral error mapping, opt-in key-gated live parity/grounding, and the new synthetic credential canary -- prove ordinary tests stay offline and secret-safe.
- [x] `backend/.env.example`, `docs/CONFIGURATION.md`, `docs/DEVELOPMENT.md`, and `docs/CI-SECRETS-CHECKLIST.md` -- document Anthropic selection, separate key/model variables, live-test behavior, and its prohibition from normal CI -- give operators accurate safe setup guidance.

**Acceptance Criteria:**
- Given `LLM_PROVIDER=anthropic`, when API dependencies resolve the task-level provider, then they receive a lazy `AnthropicLLMProvider` using `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`, while an unconfigured process still selects keyless `stub`.
- Given Anthropic produces any supported tool-use calls, when constraints are parsed, then every result is an existing normalized `OverrideCall`; given no tool use, then parsing returns an empty list.
- Given Anthropic returns insight text or an empty/non-text response, when insight generation runs, then it returns concatenated text or an empty string for the existing grounding guard.
- Given an Anthropic request fails, when the adapter handles it, then callers receive `LLMProviderError` without SDK exception types or credentials escaping.
- Given normal CI or the normal pytest suite, when it runs with no Anthropic key, then no Anthropic network call is attempted; live Anthropic tests are explicitly marked and skip without that key.

## Spec Change Log

## Design Notes

Anthropic's Messages API requires `max_tokens` and represents a tool call as a `tool_use` response content block carrying `name` and object-valued `input`; its tool schema is `{name, description, input_schema}`. The adapter must therefore mirror semantic behavior, rather than reuse the Gemini/OpenAI payload shapes. Anthropic's official SDK/API documentation was used as the integration reference.

## Verification

**Commands:**
- `uv run --project backend pytest -q tests/test_anthropic_provider.py` -- expected: all non-live Anthropic adapter tests pass without a key or network access.
- `uv run --project backend pytest -q` -- expected: full default backend suite remains green and excludes live tests.
- `uv run --project backend pytest -q -m live tests/test_anthropic_provider.py` -- expected: Anthropic live tests skip cleanly without `ANTHROPIC_API_KEY`; with an intentionally supplied key, parity and grounding tests execute.

## Suggested Review Order

**Provider boundary**

- Keeps Anthropic SDK details and malformed-model handling at one adapter edge.
  [`anthropic.py:104`](../../backend/llm/anthropic.py#L104)

- Selects the new adapter only through the established neutral registry.
  [`base.py:53`](../../backend/llm/base.py#L53)

**Safe configuration**

- Separates Anthropic credentials and model defaults from other provider settings.
  [`settings.py:29`](../../backend/settings.py#L29)

- Documents the explicit provider selection and keyless default posture.
  [`.env.example:16`](../../backend/.env.example#L16)
  [`CONFIGURATION.md:45`](../../docs/CONFIGURATION.md#L45)

**Regression proof**

- Covers offline translation, failures, malformed input, and opt-in live grounding.
  [`test_anthropic_provider.py:53`](../../backend/tests/test_anthropic_provider.py#L53)

- Adds the Anthropic credential to the existing settings-repr secret canary.
  [`test_content_minimization.py:59`](../../backend/tests/test_content_minimization.py#L59)
