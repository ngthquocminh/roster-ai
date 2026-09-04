"""Concrete operational telemetry adapters."""

from adapters.telemetry.json_logs import (
    JsonLogTelemetrySink,
    configure_json_logging,
)

__all__ = ["JsonLogTelemetrySink", "configure_json_logging"]
