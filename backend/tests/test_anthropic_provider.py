"""Offline contract tests for the Anthropic-backed task-level LLM provider."""
from __future__ import annotations

import os

import anthropic
import httpx
import pytest

from domain.overrides import OverrideCall, override_id


_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


class _ContentBlock:
    def __init__(self, block_type: str, *, name: str | None = None, input=None, text: str | None = None):
        self.type = block_type
        self.name = name
        self.input = input
        self.text = text


class _Response:
    def __init__(self, content) -> None:
        self.content = content


class _Messages:
    def __init__(self, response=None, exception: Exception | None = None) -> None:
        self._response = response
        self._exception = exception

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._exception:
            raise self._exception
        return self._response


class _FakeClient:
    def __init__(self, response=None, exception: Exception | None = None) -> None:
        self.messages = _Messages(response, exception)


def _provider():
    from llm.base import create_provider
    from settings import default_settings

    return create_provider("anthropic", settings=default_settings())


def test_create_provider_anthropic_is_lazy_and_uses_independent_settings(monkeypatch):
    """Removing lazy creation or accidentally using Gemini settings breaks this contract."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")

    provider = _provider()

    assert provider.name == "anthropic"
    assert provider._client is None
    assert provider._api_key == "test-key"
    assert provider._model == "test-model"


def test_parse_constraints_normalizes_tool_use_blocks():
    """Passing vendor blocks across the seam or skipping numeric normalization breaks this."""
    provider = _provider()
    provider._client = _FakeClient(_Response([
        _ContentBlock("text", text="Working on it"),
        _ContentBlock("tool_use", name="set_min_workers_per_task", input={"task_id": "Pick", "n": 2.0}),
    ]))

    result = provider.parse_constraints("at least 2 on Pick")

    assert result == [OverrideCall(
        id=override_id("set_min_workers_per_task", {"task_id": "Pick", "n": 2}),
        tool="set_min_workers_per_task",
        args={"task_id": "Pick", "n": 2},
    )]


def test_parse_constraints_without_tool_use_returns_empty_list():
    provider = _provider()
    provider._client = _FakeClient(_Response([_ContentBlock("text", text="No constraint")]))

    assert provider.parse_constraints("hello") == []


def test_parse_constraints_leaves_malformed_numeric_arguments_for_service_rejection():
    provider = _provider()
    provider._client = _FakeClient(_Response([
        _ContentBlock("tool_use", name="set_min_workers_per_task", input={"task_id": "Pick", "n": "two"}),
    ]))

    result = provider.parse_constraints("at least two on Pick")

    assert result[0].args == {"task_id": "Pick", "n": "two"}


def test_generate_insights_joins_only_text_blocks():
    """Including tool content or failing to aggregate multiple prose blocks breaks this."""
    provider = _provider()
    provider._client = _FakeClient(_Response([
        _ContentBlock("text", text="Total cost 450."),
        _ContentBlock("tool_use", name="set_max_hours", input={"member_id": "Alice", "max_hours": 40}),
        _ContentBlock("text", text="Coverage is complete."),
    ]))

    assert provider.generate_insights({"metrics": {"total_cost": 450}}) == "Total cost 450.Coverage is complete."


def test_generate_insights_without_text_returns_empty_string():
    provider = _provider()
    provider._client = _FakeClient(_Response([_ContentBlock("tool_use", name="set_max_hours", input={})]))

    assert provider.generate_insights({}) == ""


def test_generate_insights_keeps_the_established_report_categories():
    provider = _provider()
    provider._client = _FakeClient(_Response([]))

    provider.generate_insights({})

    prompt = provider._client.messages.last_kwargs["messages"][0]["content"]
    assert "warnings" in prompt
    assert "constraint overrides applied" in prompt


def test_vendor_errors_are_mapped_to_neutral_error():
    from llm.base import LLMProviderError

    provider = _provider()
    provider._client = _FakeClient(exception=anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    ))

    with pytest.raises(LLMProviderError, match="Anthropic request failed"):
        provider.parse_constraints("at least 2 on Pick")


def test_non_api_sdk_errors_are_mapped_to_neutral_error_for_both_operations():
    from llm.base import LLMProviderError

    provider = _provider()
    provider._client = _FakeClient(exception=TypeError("Could not resolve authentication method"))

    with pytest.raises(LLMProviderError, match="Anthropic request failed"):
        provider.parse_constraints("at least 2 on Pick")
    with pytest.raises(LLMProviderError, match="Anthropic request failed"):
        provider.generate_insights({})


@pytest.mark.live
@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set — live test requires a real key")
def test_anthropic_parse_constraints_matches_stub_parity():
    from llm.base import create_provider
    from settings import default_settings

    anthropic = create_provider("anthropic", settings=default_settings())
    stub = create_provider("stub")
    anthropic_calls = anthropic.parse_constraints("at least 2 on Pick")
    stub_calls = stub.parse_constraints("at least 2 on Pick")

    assert len(anthropic_calls) == len(stub_calls) == 1
    assert anthropic_calls[0].tool == stub_calls[0].tool == "set_min_workers_per_task"
    assert anthropic_calls[0].args["n"] == stub_calls[0].args["n"] == 2


@pytest.mark.live
@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set — live test requires a real key")
def test_anthropic_generate_insights_passes_grounding_guard():
    from llm.base import create_provider
    from services.insight_service import _grounding_guard
    from settings import default_settings

    metrics = {"total_cost": 450.0, "total_unmet_hours": 0.0, "scheduled_shifts": 42}
    report = create_provider("anthropic", settings=default_settings()).generate_insights(
        {"metrics": metrics, "warnings": [], "overrides": []}
    )

    assert report.strip()
    _grounding_guard(report, metrics)
