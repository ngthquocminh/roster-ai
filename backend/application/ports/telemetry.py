"""Application port for best-effort operational telemetry."""
from __future__ import annotations

from typing import Protocol

from application.contracts.telemetry import TelemetryRecordV1


class TelemetrySink(Protocol):
    """Emit one record without influencing product work (AD-12).

    Implementations must never raise and must never perform I/O against the
    product database. Telemetry is diagnostic, never an authority or commit
    dependency.
    """

    def emit(self, record: TelemetryRecordV1) -> None: ...


class NullTelemetrySink:
    """Safe default used by call sites that do not compose telemetry."""

    def emit(self, record: TelemetryRecordV1) -> None:
        return None


__all__ = ["NullTelemetrySink", "TelemetrySink"]
