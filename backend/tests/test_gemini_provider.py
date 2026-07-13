"""Tests for the Gemini-backed LLM provider (LLM-02, TEST-04).

Verifies:
- create_provider("gemini") returns a GeminiLLMProvider named "gemini",
  without requiring a real API key (client construction is deferred to first
  use, keeping the keyless-default-CI invariant intact, D-04).
- parse_constraints translates a fake client's function_calls into
  list[OverrideCall] via the shared to_override_call helper (parity with the
  stub's translation path, D-06/D-07).
- An empty/None function_calls response yields [] (matches the stub's
  "no constraint found" behavior, NLC-03).
- generate_insights returns the fake client's response.text verbatim.
- Exactly one gated @pytest.mark.live test exists, excluded from the default
  suite (addopts = -m "not live") and skipped when GEMINI_API_KEY is absent.

All non-live tests use a hand-rolled fake client (mirroring the StubEngine
idiom in test_api.py) injected onto the provider's `_client` attribute — no
network access, no real API key required.
"""
from __future__ import annotations

import os

import pytest

from domain.overrides import OverrideCall, override_id

_HAS_KEY = bool(os.environ.get("GEMINI_API_KEY"))


# ---------------------------------------------------------------------------
# Fake genai client — mirrors the StubEngine hand-built-fake idiom in
# test_api.py. Exposes only the surface GeminiLLMProvider actually calls:
# `.models.generate_content(...)`.
# ---------------------------------------------------------------------------

class _FakeFunctionCall:
    """Mirrors google.genai.types.FunctionCall's .name/.args surface."""

    def __init__(self, name: str, args: dict) -> None:
        self.name = name
        self.args = args


class _FakeResponse:
    def __init__(self, function_calls=None, text=None) -> None:
        self.function_calls = function_calls
        self.text = text


class _FakeModels:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def generate_content(self, **kwargs):
        return self._response


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.models = _FakeModels(response)


# ---------------------------------------------------------------------------
# create_provider factory — keyless
# ---------------------------------------------------------------------------

def test_create_provider_gemini_returns_gemini_llm_provider():
    from llm.base import create_provider
    from settings import default_settings

    p = create_provider("gemini", settings=default_settings())
    assert p.name == "gemini"


def test_create_provider_gemini_without_settings_raises_value_error():
    """WR-02: gemini branch requires settings; None yields a clear ValueError."""
    from llm.base import create_provider

    with pytest.raises(ValueError, match="requires settings"):
        create_provider("gemini")


# ---------------------------------------------------------------------------
# parse_constraints — fake client, no network
# ---------------------------------------------------------------------------

def test_parse_constraints_translates_one_function_call():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    fake_call = _FakeFunctionCall(name="set_min_workers_per_task", args={"task_id": "Pick", "n": 2})
    provider._client = _FakeClient(_FakeResponse(function_calls=[fake_call]))

    result = provider.parse_constraints("at least 2 on Pick")

    assert isinstance(result, list)
    assert len(result) == 1
    call = result[0]
    assert isinstance(call, OverrideCall)
    assert call.tool == "set_min_workers_per_task"
    assert call.args == {"task_id": "Pick", "n": 2}
    assert call.id == override_id("set_min_workers_per_task", {"task_id": "Pick", "n": 2})


def test_parse_constraints_coerces_float_int_arg_for_stub_parity():
    """WR-03: n returned as 2.0 must coerce to int 2 so override_id matches the stub."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    fake_call = _FakeFunctionCall(name="set_min_workers_per_task", args={"task_id": "Pick", "n": 2.0})
    provider._client = _FakeClient(_FakeResponse(function_calls=[fake_call]))

    result = provider.parse_constraints("at least 2 on Pick")

    call = result[0]
    assert call.args["n"] == 2
    assert isinstance(call.args["n"], int)
    assert call.id == override_id("set_min_workers_per_task", {"task_id": "Pick", "n": 2})


def test_parse_constraints_coerces_float_arg():
    """WR-03: factor/max_hours are floated (e.g. an int 2 -> 2.0) to match the stub."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    fake_call = _FakeFunctionCall(name="scale_demand", args={"task_id": "Pick", "factor": 2})
    provider._client = _FakeClient(_FakeResponse(function_calls=[fake_call]))

    call = provider.parse_constraints("scale Pick demand by 2x")[0]
    assert call.args["factor"] == 2.0
    assert isinstance(call.args["factor"], float)


def test_parse_constraints_none_args_does_not_raise():
    """WR-03: an argument-less function call (fc.args is None) must not raise TypeError."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    fake_call = _FakeFunctionCall(name="set_min_workers_per_task", args=None)
    provider._client = _FakeClient(_FakeResponse(function_calls=[fake_call]))

    result = provider.parse_constraints("do the thing")
    assert len(result) == 1
    assert result[0].args == {}


def test_parse_constraints_empty_function_calls_returns_empty_list():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    provider._client = _FakeClient(_FakeResponse(function_calls=None))

    assert provider.parse_constraints("hello there") == []


def test_parse_constraints_no_function_calls_list_returns_empty_list():
    """response.function_calls == [] (not None) is also treated as no match."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    provider._client = _FakeClient(_FakeResponse(function_calls=[]))

    assert provider.parse_constraints("show me the schedule") == []


# ---------------------------------------------------------------------------
# Vendor API errors -> provider-neutral LLMProviderError (quick-260709-m9m)
# ---------------------------------------------------------------------------

class _FailingModels:
    """Fake `.models` surface whose generate_content always raises a vendor APIError."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate_content(self, **kwargs):
        raise self._exc


class _FailingClient:
    def __init__(self, exc: Exception) -> None:
        self.models = _FailingModels(exc)


def test_parse_constraints_maps_vendor_api_error_to_llm_provider_error():
    """A vendor google.genai.errors.APIError must never cross the LLMProvider seam (D-02)."""
    from google.genai import errors as genai_errors

    from llm.base import LLMProviderError, create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    vendor_exc = genai_errors.ClientError(
        400, {"error": {"message": "bad key", "status": "INVALID_ARGUMENT"}}
    )
    provider._client = _FailingClient(vendor_exc)

    with pytest.raises(LLMProviderError):
        provider.parse_constraints("at least 2 on Pick")


# ---------------------------------------------------------------------------
# generate_insights — fake client, no network
# ---------------------------------------------------------------------------

def test_generate_insights_returns_fake_text():
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    provider._client = _FakeClient(_FakeResponse(text="Schedule solved with total cost 450."))

    result = provider.generate_insights({"metrics": {"total_cost": 450.0}})

    assert result == "Schedule solved with total cost 450."


def test_generate_insights_none_text_returns_empty_string():
    """WR-01: a safety-blocked/empty response (response.text is None) degrades to ""."""
    from llm.base import create_provider
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())
    provider._client = _FakeClient(_FakeResponse(text=None))

    result = provider.generate_insights({"metrics": {"total_cost": 450.0}})

    assert result == ""
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Live parity test (TEST-04, D-09) — excluded by default, gated on a real key
# ---------------------------------------------------------------------------

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

    # D-06 reframed parity: same neutral OverrideCall shape, not byte-identical
    # vendor payload. task_id token matching is looser (LLM phrasing may vary
    # casing/wording) — constraint_service's substring resolver (VAL-02)
    # handles this either way.
    assert len(gemini_calls) == len(stub_calls) == 1
    assert gemini_calls[0].tool == stub_calls[0].tool == "set_min_workers_per_task"
    assert gemini_calls[0].args["n"] == stub_calls[0].args["n"] == 2


@pytest.mark.live
@pytest.mark.skipif(not _HAS_KEY, reason="GEMINI_API_KEY not set — live test requires a real key")
def test_gemini_generate_insights_passes_grounding_guard():
    """Regression test for insight-api-502-ungrounded: real Gemini prose over
    real run-418577f3-shaped metrics must pass the REAL D-06 grounding guard.

    The bug was whole-number roundings ("98%", "212", "11,550", "61%") emitted
    by genuine model prose being rejected by the guard's rounding ladder — the
    fix was human-verified once against the live endpoint but had no automated
    (opt-in) regression coverage until this test.
    """
    from llm.base import create_provider
    from services.insight_service import _grounding_guard
    from settings import default_settings

    provider = create_provider("gemini", settings=default_settings())

    metrics = {
        "total_cost": 11549.71,
        "total_unmet_hours": 212.127,
        "scheduled_shifts": 42,
        "scheduled_members": 18,
        "coverage_by_function": {
            # 265/270 = 0.9814814814814815 -> whole-number rounding "98%" is the
            # exact case that broke the guard in insight-api-502-ungrounded.
            "Putaways": {"required_h": 270.0, "served_h": 265.0, "pct": 0.9814814814814815},
            "Pick": {"required_h": 300.0, "served_h": 300.0, "pct": 1.0},
        },
        "coverage_by_day": {"0": 0.6122, "1": 0.95},
    }
    summary = {"metrics": metrics, "warnings": [], "overrides": []}

    report = provider.generate_insights(summary)

    # A blank/safety-blocked response would vacuously pass the guard (no numeric
    # tokens to check) and hide the regression — require real prose.
    assert report.strip()

    # We deliberately do not hard-assert a specific token like "98%" here — real
    # Gemini phrasing varies (98%, 98.1%, 98.15%). The guard passing on genuine
    # model output, without raising InsightGenerationError, is the assertion.
    _grounding_guard(report, metrics)


@pytest.mark.live
@pytest.mark.skipif(not _HAS_KEY, reason="GEMINI_API_KEY not set — live test requires a real key")
@pytest.mark.parametrize(
    "text, tool, arg_key, arg_value",
    [
        ("scale Pick demand by 2x", "scale_demand", "factor", 2.0),
        ("cap Alice at 40 hours", "set_max_hours", "max_hours", 40.0),
    ],
)
def test_gemini_parse_constraints_more_phrasings_match_stub(text, tool, arg_key, arg_value):
    """Broadens live parse_constraints parity beyond the single "at least 2 on
    Pick" case (D-06 reframed parity: same neutral OverrideCall shape, not
    byte-identical vendor payload). Only tool name and coerced numeric arg are
    the parity contract — task_id/member_id token matching is deliberately not
    asserted, since constraint_service's substring resolver (VAL-02) handles
    LLM phrasing variance either way.
    """
    from llm.base import create_provider
    from settings import default_settings

    settings = default_settings()
    gemini = create_provider("gemini", settings=settings)
    stub = create_provider("stub")

    gemini_calls = gemini.parse_constraints(text)
    stub_calls = stub.parse_constraints(text)

    assert len(gemini_calls) == len(stub_calls) == 1
    assert gemini_calls[0].tool == stub_calls[0].tool == tool
    assert gemini_calls[0].args[arg_key] == stub_calls[0].args[arg_key] == arg_value
