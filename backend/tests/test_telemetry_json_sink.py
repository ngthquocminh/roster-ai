import json
import logging
from datetime import datetime, timezone
from io import StringIO
from uuid import UUID

import pytest

from adapters.telemetry.cost import estimate_cost_usd
from adapters.telemetry.json_logs import (
    JsonLogFormatter,
    JsonLogTelemetrySink,
    configure_json_logging,
)
from application.contracts.telemetry import (
    AgentUsageV1,
    CorrelationV1,
    TelemetryRecordV1,
)
from application.app_version import APP_VERSION


def _handler(stream: StringIO) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    return handler


def test_json_sink_preserves_nulls_and_owned_scalar_shapes() -> None:
    stream = StringIO()
    logger = logging.Logger("test.telemetry")
    logger.addHandler(_handler(stream))
    sink = JsonLogTelemetrySink(logger=logger)
    sink.emit(
        TelemetryRecordV1(
            event="agent.run.completed",
            occurred_at=datetime(2026, 9, 3, 4, 5, tzinfo=timezone.utc),
            app_version=APP_VERSION,
            correlation=CorrelationV1(
                agent_run_id=UUID("00000000-0000-0000-0000-000000000001")
            ),
            labels={"budget_outcome": "budget_exhausted"},
            usage=None,
            estimated_cost_usd=None,
        )
    )
    payload = json.loads(stream.getvalue())
    assert payload["occurred_at"] == "2026-09-03T04:05:00Z"
    assert payload["correlation"]["agent_run_id"].endswith("0001")
    assert payload["usage"] is None
    assert payload["estimated_cost_usd"] is None


def test_cost_estimator_covers_configured_unpriced_and_missing_usage() -> None:
    usage = AgentUsageV1(input_tokens=2_000_000, output_tokens=500_000)
    assert estimate_cost_usd(usage, 1.0, 4.0) == (4.0, "configured")
    assert estimate_cost_usd(usage, 0.0, 0.0) == (None, "unpriced")
    assert estimate_cost_usd(None, 1.0, 4.0) == (None, "usage_unavailable")
    assert estimate_cost_usd(AgentUsageV1(), 1.0, 4.0) == (
        None,
        "usage_unavailable",
    )


def test_cost_estimator_prices_cache_tokens_separately_from_full_input_rate() -> None:
    # `input_tokens` is a parent bucket that already includes the 900_000
    # cache-read tokens (pydantic-ai convention) -- pricing the whole bucket
    # at the input rate would double-bill them (code review of story-5.1,
    # decision 4).
    usage = AgentUsageV1(
        input_tokens=1_000_000, output_tokens=0, cache_read_tokens=900_000
    )
    # No cache rate configured: cache tokens contribute nothing, only the
    # 100_000 non-cache remainder is priced at the input rate -- not the
    # full 1_000_000 at the input rate (which would be 1.0).
    assert estimate_cost_usd(usage, 1.0, 4.0) == (0.1, "configured")
    # Cache rate configured: the non-cache remainder prices at the input
    # rate and the cache tokens price at their own, cheaper rate.
    value, basis = estimate_cost_usd(
        usage, 1.0, 4.0, cache_read_rate_usd_per_mtok=0.1
    )
    assert basis == "configured"
    assert value == pytest.approx(0.19)


def test_json_sink_swallows_serialization_and_handler_failures() -> None:
    class RaisingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            raise RuntimeError("handler failed")

    logger = logging.Logger("test.telemetry.failure")
    logger.addHandler(RaisingHandler())
    sink = JsonLogTelemetrySink(logger=logger)
    sink.emit(TelemetryRecordV1())
    sink.emit(TelemetryRecordV1(labels={"bad": object()}))  # type: ignore[dict-item]


def test_configure_json_logging_is_idempotent() -> None:
    logger = logging.getLogger("test.telemetry.configure")
    configure_json_logging(logger=logger)
    configure_json_logging(logger=logger)
    configured = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_shiftmind_json_handler", False)
    ]
    assert len(configured) == 1
