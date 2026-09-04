"""Best-effort JSON-lines sink built only on the Python standard library."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from application.contracts.telemetry import TelemetryRecordV1

TELEMETRY_LOGGER_NAME = "shiftmind.telemetry"
_PAYLOAD_ATTRIBUTE = "shiftmind_telemetry"


def _json_default(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc)
        return normalized.isoformat().replace("+00:00", "Z")
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


class JsonLogFormatter(logging.Formatter):
    """Render telemetry and ordinary stdlib records as one JSON object each."""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, _PAYLOAD_ATTRIBUTE, None)
        if payload is None:
            payload = {
                "occurred_at": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat().replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=_json_default, separators=(",", ":"))


class JsonLogTelemetrySink:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(TELEMETRY_LOGGER_NAME)

    def emit(self, record: TelemetryRecordV1) -> None:
        try:
            payload = asdict(record)
            # Validate serialization inside this catch as well as in the
            # formatter so malformed records cannot escape through logging.
            json.dumps(payload, default=_json_default)
            self._logger.info("telemetry", extra={_PAYLOAD_ATTRIBUTE: payload})
        except Exception:  # noqa: BLE001 - AD-12 requires telemetry to disappear
            return None


def configure_json_logging(*, logger: logging.Logger | None = None) -> None:
    """Install one process handler; repeated startup calls are harmless."""
    target = logger or logging.getLogger()
    if any(
        getattr(handler, "_shiftmind_json_handler", False)
        for handler in target.handlers
    ):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    setattr(handler, "_shiftmind_json_handler", True)
    target.addHandler(handler)
    # Enable only the telemetry logger at INFO, never `target`'s own level:
    # `target` defaults to the process root, and every other logger in the
    # process (SQLAlchemy, httpx, ...) inherits its effective level from
    # root. Raising root to INFO would flow their free-text INFO records
    # through this same JSON formatter -- exactly what Decision 12 keeps out
    # of TelemetryRecordV1 itself.
    telemetry_logger = logging.getLogger(TELEMETRY_LOGGER_NAME)
    if telemetry_logger.level == logging.NOTSET or telemetry_logger.level > logging.INFO:
        telemetry_logger.setLevel(logging.INFO)


__all__ = [
    "JsonLogFormatter",
    "JsonLogTelemetrySink",
    "TELEMETRY_LOGGER_NAME",
    "configure_json_logging",
]
