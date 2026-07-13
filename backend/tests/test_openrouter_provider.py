"""Tests for the OpenRouter-backed LLM provider (quick-260713-pn3).

Verifies:
- create_provider("openrouter") returns an OpenRouterLLMProvider named
  "openrouter", without requiring a real API key (client construction is
  deferred to first use, keeping the keyless-default-CI invariant intact,
  D-04).
- parse_constraints translates a fake client's tool_calls into
  list[OverrideCall] via the shared to_override_call helper (parity with the
  stub's and Gemini's translation path, D-06/D-07).
- Empty/None tool_calls yields [] (matches the stub's "no constraint found"
  behavior, NLC-03).
- generate_insights returns the fake client's response content verbatim.
- An openai SDK error is mapped to the neutral llm.base.LLMProviderError.
- Exactly one (up to two) gated @pytest.mark.live test(s) exist, excluded from
  the default suite (addopts = -m "not live") and skipped when
  OPENROUTER_API_KEY is absent.

All non-live tests use a hand-rolled fake client (mirroring the StubEngine /
test_gemini_provider.py idiom) injected onto the provider's `_client`
attribute — no network access, no real API key required.
"""
from __future__ import annotations

import json
import os

import httpx
import openai
import pytest

from domain.overrides import OverrideCall, override_id

_HAS_KEY = bool(os.environ.get("OPENROUTER_API_KEY"))


# ---------------------------------------------------------------------------
# Fake OpenAI-compatible client — mirrors the openai Chat Completions
# response shape: .choices[0].message.tool_calls / .content, where each tool
# call exposes .function.name / .function.arguments (a JSON STRING).
# ---------------------------------------------------------------------------

class _FakeFunction:
    def __init__(self, name: str, arguments) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name: str, arguments) -> None:
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, tool_calls=None, content=None) -> None:
        self.tool_calls = tool_calls
        self.content = content


class _FakeChoice:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message


class _FakeResponse:
    def __init__(self, choices=None) -> None:
        self.choices = choices if choices is not None else []


class _FakeCompletions:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def create(self, **kwargs):
        return self._response


class _FakeChat:
    def __init__(self, response: _FakeResponse) -> None:
        self.completions = _FakeCompletions(response)


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.chat = _FakeChat(response)


def _response_with_tool_calls(tool_calls) -> _FakeResponse:
    return _FakeResponse(choices=[_FakeChoice(_FakeMessage(tool_calls=tool_calls))])


def _response_with_content(content) -> _FakeResponse:
    return _FakeResponse(choices=[_FakeChoice(_FakeMessage(content=content))])


# ---------------------------------------------------------------------------
# create_provider factory — keyless
# ---------------------------------------------------------------------------

def test_create_provider_openrouter_returns_openrouter_llm_provider():
    from llm.base import create_provider
    from settings import default_settings

    p = create_provider("openrouter", settings=default_settings())
    assert p.name == "openrouter"


def test_create_provider_openrouter_without_settings_raises_value_error():
    from llm.base import create_provider

    with pytest.raises(ValueError, match="requires settings"):
        create_provider("openrouter")


# ---------------------------------------------------------------------------
# parse_constraints — fake client, no network
# ---------------------------------------------------------------------------

def test_parse_constraints_translates_one_tool_call():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    fake_call = _FakeToolCall(
        name="set_min_workers_per_task", arguments='{"task_id":"Pick","n":2}'
    )
    provider._client = _FakeClient(_response_with_tool_calls([fake_call]))

    result = provider.parse_constraints("at least 2 on Pick")

    assert isinstance(result, list)
    assert len(result) == 1
    call = result[0]
    assert isinstance(call, OverrideCall)
    assert call.tool == "set_min_workers_per_task"
    assert call.args == {"task_id": "Pick", "n": 2}
    assert call.id == override_id("set_min_workers_per_task", {"task_id": "Pick", "n": 2})


def test_parse_constraints_coerces_float_int_arg_for_stub_parity():
    """WR-03 parity: n given as 2.0 must coerce to int 2 so override_id matches the stub."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    fake_call = _FakeToolCall(
        name="set_min_workers_per_task", arguments='{"task_id":"Pick","n":2.0}'
    )
    provider._client = _FakeClient(_response_with_tool_calls([fake_call]))

    result = provider.parse_constraints("at least 2 on Pick")

    call = result[0]
    assert call.args["n"] == 2
    assert isinstance(call.args["n"], int)
    assert call.id == override_id("set_min_workers_per_task", {"task_id": "Pick", "n": 2})


def test_parse_constraints_coerces_float_arg():
    """WR-03 parity: factor/max_hours are floated (e.g. an int 2 -> 2.0) to match the stub."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    fake_call = _FakeToolCall(name="scale_demand", arguments='{"task_id":"Pick","factor":2}')
    provider._client = _FakeClient(_response_with_tool_calls([fake_call]))

    call = provider.parse_constraints("scale Pick demand by 2x")[0]
    assert call.args["factor"] == 2.0
    assert isinstance(call.args["factor"], float)


def test_parse_constraints_empty_arguments_does_not_raise():
    """WR-03 parity: an argument-less tool call (empty/None arguments string) must not raise."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    fake_call = _FakeToolCall(name="set_min_workers_per_task", arguments="")
    provider._client = _FakeClient(_response_with_tool_calls([fake_call]))

    result = provider.parse_constraints("do the thing")
    assert len(result) == 1
    assert result[0].args == {}


def test_parse_constraints_none_arguments_does_not_raise():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    fake_call = _FakeToolCall(name="set_min_workers_per_task", arguments=None)
    provider._client = _FakeClient(_response_with_tool_calls([fake_call]))

    result = provider.parse_constraints("do the thing")
    assert len(result) == 1
    assert result[0].args == {}


def test_parse_constraints_none_tool_calls_returns_empty_list():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    provider._client = _FakeClient(_response_with_tool_calls(None))

    assert provider.parse_constraints("hello there") == []


def test_parse_constraints_empty_tool_calls_list_returns_empty_list():
    """response.choices[0].message.tool_calls == [] (not None) is also treated as no match."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    provider._client = _FakeClient(_response_with_tool_calls([]))

    assert provider.parse_constraints("show me the schedule") == []


def test_parse_constraints_no_choices_returns_empty_list():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    provider._client = _FakeClient(_FakeResponse(choices=[]))

    assert provider.parse_constraints("hello there") == []


# ---------------------------------------------------------------------------
# Vendor API errors -> provider-neutral LLMProviderError
# ---------------------------------------------------------------------------

class _FailingCompletions:
    """Fake `.chat.completions` surface whose create always raises a vendor error."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def create(self, **kwargs):
        raise self._exc


class _FailingChat:
    def __init__(self, exc: Exception) -> None:
        self.completions = _FailingCompletions(exc)


class _FailingClient:
    def __init__(self, exc: Exception) -> None:
        self.chat = _FailingChat(exc)


def test_parse_constraints_maps_vendor_api_error_to_llm_provider_error():
    """A vendor openai.OpenAIError must never cross the LLMProvider seam (D-02)."""
    from llm.base import LLMProviderError, create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    vendor_exc = openai.APIConnectionError(
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    )
    provider._client = _FailingClient(vendor_exc)

    with pytest.raises(LLMProviderError):
        provider.parse_constraints("at least 2 on Pick")


def test_generate_insights_maps_vendor_api_error_to_llm_provider_error():
    from llm.base import LLMProviderError, create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    vendor_exc = openai.APIConnectionError(
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    )
    provider._client = _FailingClient(vendor_exc)

    with pytest.raises(LLMProviderError):
        provider.generate_insights({"metrics": {"total_cost": 450.0}})


# ---------------------------------------------------------------------------
# generate_insights — fake client, no network
# ---------------------------------------------------------------------------

def test_generate_insights_returns_fake_content():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    provider._client = _FakeClient(
        _response_with_content("Schedule solved with total cost 450.")
    )

    result = provider.generate_insights({"metrics": {"total_cost": 450.0}})

    assert result == "Schedule solved with total cost 450."


def test_generate_insights_none_content_returns_empty_string():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    provider._client = _FakeClient(_response_with_content(None))

    result = provider.generate_insights({"metrics": {"total_cost": 450.0}})

    assert result == ""
    assert isinstance(result, str)


def test_generate_insights_no_choices_returns_empty_string():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())
    provider._client = _FakeClient(_FakeResponse(choices=[]))

    result = provider.generate_insights({"metrics": {"total_cost": 450.0}})

    assert result == ""


# ---------------------------------------------------------------------------
# Live parity test (D-09) — excluded by default, gated on a real key
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.skipif(not _HAS_KEY, reason="OPENROUTER_API_KEY not set — live test requires a real key")
def test_openrouter_parse_constraints_matches_stub_parity():
    from llm.base import create_provider
    from settings import default_settings

    settings = default_settings()  # picks up OPENROUTER_MODEL / OPENROUTER_API_KEY from env
    openrouter = create_provider("openrouter", settings=settings)
    stub = create_provider("stub")

    text = "at least 2 on Pick"
    openrouter_calls = openrouter.parse_constraints(text)
    stub_calls = stub.parse_constraints(text)

    # D-06 reframed parity: same neutral OverrideCall shape, not byte-identical
    # vendor payload. task_id token matching is looser (LLM phrasing may vary
    # casing/wording) — constraint_service's substring resolver (VAL-02)
    # handles this either way.
    assert len(openrouter_calls) == len(stub_calls) == 1
    assert openrouter_calls[0].tool == stub_calls[0].tool == "set_min_workers_per_task"
    assert openrouter_calls[0].args["n"] == stub_calls[0].args["n"] == 2


@pytest.mark.live
@pytest.mark.skipif(not _HAS_KEY, reason="OPENROUTER_API_KEY not set — live test requires a real key")
def test_openrouter_generate_insights_passes_grounding_guard():
    """Real OpenRouter prose over real run-shaped metrics must pass the REAL
    D-06 grounding guard (mirrors the Gemini live regression test)."""
    from llm.base import create_provider
    from services.insight_service import _grounding_guard
    from settings import default_settings

    provider = create_provider("openrouter", settings=default_settings())

    metrics = {
        "total_cost": 11549.71,
        "total_unmet_hours": 212.127,
        "scheduled_shifts": 42,
        "scheduled_members": 18,
        "coverage_by_function": {
            "Putaways": {"required_h": 270.0, "served_h": 265.0, "pct": 0.9814814814814815},
            "Pick": {"required_h": 300.0, "served_h": 300.0, "pct": 1.0},
        },
        "coverage_by_day": {"0": 0.6122, "1": 0.95},
    }
    summary = {"metrics": metrics, "warnings": [], "overrides": []}

    report = provider.generate_insights(summary)

    # A blank/safety-blocked response would vacuously pass the guard (no numeric
    # tokens to check) and hide a regression — require real prose.
    assert report.strip()

    _grounding_guard(report, metrics)
