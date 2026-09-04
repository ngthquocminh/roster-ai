"""Deterministic configured-price estimate for one agent run."""
from __future__ import annotations

from typing import Literal

from application.contracts.telemetry import AgentUsageV1

CostBasis = Literal["configured", "unpriced", "usage_unavailable"]


def estimate_cost_usd(
    usage: AgentUsageV1 | None,
    input_rate_usd_per_mtok: float,
    output_rate_usd_per_mtok: float,
    cache_read_rate_usd_per_mtok: float = 0.0,
    cache_write_rate_usd_per_mtok: float = 0.0,
) -> tuple[float | None, CostBasis]:
    if usage is None or usage.input_tokens is None or usage.output_tokens is None:
        return None, "usage_unavailable"
    if input_rate_usd_per_mtok == 0.0 and output_rate_usd_per_mtok == 0.0:
        return None, "unpriced"
    # `input_tokens` is a parent bucket that already includes cache tokens
    # (pydantic-ai's `UsageBase` docstring), so pricing the full figure at
    # `input_rate_usd_per_mtok` double-bills cache tokens at the full input
    # price. Price the non-cache remainder at the input rate and the cache
    # portions at their own (optionally zero) rates instead.
    cache_read_tokens = usage.cache_read_tokens or 0
    cache_write_tokens = usage.cache_write_tokens or 0
    non_cache_input_tokens = max(
        0, usage.input_tokens - cache_read_tokens - cache_write_tokens
    )
    value = (
        non_cache_input_tokens * input_rate_usd_per_mtok
        + usage.output_tokens * output_rate_usd_per_mtok
        + cache_read_tokens * cache_read_rate_usd_per_mtok
        + cache_write_tokens * cache_write_rate_usd_per_mtok
    ) / 1_000_000
    return value, "configured"


__all__ = ["CostBasis", "estimate_cost_usd"]
