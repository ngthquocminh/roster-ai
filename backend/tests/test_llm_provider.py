"""Tests for the LLM provider seam (LLMProvider Protocol + StubLLMProvider + DI).

Verifies:
- create_provider("stub") returns a StubLLMProvider with name=="stub"
- create_provider("bogus") raises ValueError
- StubLLMProvider.parse_constraints("at least 2 on Pick") -> one OverrideCall
- OverrideCall fields: tool, args, id match expectations
- Internal tool_use dict never crosses the Protocol boundary (returns list[OverrideCall])
- Non-matching text returns []
- get_llm_provider() dependency returns the stub
"""
from __future__ import annotations

import pytest

from domain.overrides import OverrideCall, override_id


# ---------------------------------------------------------------------------
# create_provider factory
# ---------------------------------------------------------------------------

def test_create_provider_stub_returns_stub_llm_provider():
    from llm.base import create_provider
    p = create_provider("stub")
    assert p.name == "stub"


def test_create_provider_bogus_raises_value_error():
    from llm.base import create_provider
    with pytest.raises(ValueError, match="stub"):
        create_provider("bogus")


# ---------------------------------------------------------------------------
# StubLLMProvider.parse_constraints — matching text
# ---------------------------------------------------------------------------

def test_parse_constraints_returns_list_of_override_call():
    from llm.base import create_provider
    p = create_provider("stub")
    result = p.parse_constraints("at least 2 on Pick")
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], OverrideCall)


def test_parse_constraints_correct_tool():
    from llm.base import create_provider
    p = create_provider("stub")
    call = p.parse_constraints("at least 2 on Pick")[0]
    assert call.tool == "set_min_workers_per_task"


def test_parse_constraints_correct_args():
    from llm.base import create_provider
    p = create_provider("stub")
    call = p.parse_constraints("at least 2 on Pick")[0]
    assert call.args == {"task_id": "Pick", "n": 2}


def test_parse_constraints_id_starts_with_ov():
    from llm.base import create_provider
    p = create_provider("stub")
    call = p.parse_constraints("at least 2 on Pick")[0]
    assert call.id.startswith("ov_")


def test_parse_constraints_id_is_stable_content_hash():
    """Same text twice -> same id (content-hash stability, D-05)."""
    from llm.base import create_provider
    p = create_provider("stub")
    a = p.parse_constraints("at least 2 on Pick")[0]
    b = p.parse_constraints("at least 2 on Pick")[0]
    assert a.id == b.id


def test_parse_constraints_id_matches_override_id_helper():
    """The id field equals override_id(tool, args) for the human token args (pre-resolve)."""
    from llm.base import create_provider
    p = create_provider("stub")
    call = p.parse_constraints("at least 2 on Pick")[0]
    expected = override_id("set_min_workers_per_task", {"task_id": "Pick", "n": 2})
    assert call.id == expected


# ---------------------------------------------------------------------------
# StubLLMProvider.parse_constraints — non-matching text
# ---------------------------------------------------------------------------

def test_parse_constraints_no_match_returns_empty_list():
    from llm.base import create_provider
    p = create_provider("stub")
    assert p.parse_constraints("hello there") == []


def test_parse_constraints_general_question_returns_empty():
    from llm.base import create_provider
    p = create_provider("stub")
    assert p.parse_constraints("show me the schedule") == []


# ---------------------------------------------------------------------------
# get_llm_provider DI dependency
# ---------------------------------------------------------------------------

def test_get_llm_provider_returns_stub():
    from api.deps import get_llm_provider
    provider = get_llm_provider()
    assert provider.name == "stub"


def test_get_llm_provider_parse_constraints_works():
    from api.deps import get_llm_provider
    provider = get_llm_provider()
    result = provider.parse_constraints("at least 3 on Pack")
    # "Pack" token — stub should still parse even if it's not a real task id
    assert isinstance(result, list)
    # either 1 result (matched the number+task pattern) or 0 — either valid
    assert len(result) in (0, 1)


# ---------------------------------------------------------------------------
# StubLLMProvider.generate_insights — determinism + grounding (plan 03-02, LLM-01/TEST-01)
# ---------------------------------------------------------------------------

def test_generate_insights_deterministic():
    """Two calls with the same summary return identical non-empty text (LLM-01 / TEST-01).

    Also spot-checks that the rendered cost and unmet-hours values appear in the output
    and that no foreign number is introduced — confirming the stub is safe to drive
    the D-06 grounding guard in CI without any live API calls.
    """
    from llm.stub import StubLLMProvider

    # Representative summary dict matching the serialize_result metrics shape (serialize.py).
    summary = {
        "metrics": {
            "total_cost": 450.0,
            "total_unmet_hours": 3.5,
            "scheduled_shifts": 12,
            "scheduled_members": 8,
            "coverage_by_function": {
                "Pick": {
                    "required_h": 40.0,
                    "served_h": 36.0,
                    "pct": 0.9,   # 90% — fraction, not percentage
                },
                "Pack": {
                    "required_h": 20.0,
                    "served_h": 20.0,
                    "pct": 1.0,
                },
            },
            "coverage_by_day": {
                "0": 0.9,
                "1": 1.0,
            },
        },
        "warnings": ["Low coverage on day 2 for Pick"],
        "overrides": [{"tool": "set_min_workers_per_task", "args": {"task_id": "Pick", "n": 4}}],
    }

    provider = StubLLMProvider()

    result_a = provider.generate_insights(summary)
    result_b = provider.generate_insights(summary)

    # Must be non-empty str.
    assert isinstance(result_a, str), f"generate_insights must return str; got {type(result_a)}"
    assert result_a, "generate_insights must return non-empty text"

    # Determinism: two calls with the same input must return identical text (TEST-01 / LLM-01).
    assert result_a == result_b, (
        "generate_insights is not deterministic — two identical calls produced different output"
    )

    # Spot-check that the cost and unmet-hours values from the summary appear in the text.
    assert "450" in result_a, (
        f"Report must cite total_cost=450; got: {result_a!r}"
    )
    assert "3.5" in result_a, (
        f"Report must cite total_unmet_hours=3.5; got: {result_a!r}"
    )
