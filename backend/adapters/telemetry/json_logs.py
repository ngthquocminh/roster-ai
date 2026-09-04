"""Best-effort JSON-lines sink built only on the Python standard library."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from application.contracts.telemetry import TELEMETRY_LABEL_KEYS, TelemetryRecordV1

TELEMETRY_LOGGER_NAME = "shiftmind.telemetry"
_PAYLOAD_ATTRIBUTE = "shiftmind_telemetry"
_MAX_LABEL_VALUE_CHARS = 128
_APPLICATION_LOGGER_PREFIXES = (
    "api", "worker", "application", "adapters", "agent", "engine",
    "services", "store", "scripts", "shiftmind",
)


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
            owned = any(
                record.name == prefix or record.name.startswith(f"{prefix}.")
                for prefix in _APPLICATION_LOGGER_PREFIXES
            )
            payload = {
                "occurred_at": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat().replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "event": record.msg if owned and isinstance(record.msg, str) else "third_party",
                "call_site": f"{record.module}:{record.lineno}",
            }
            if record.exc_info:
                exception = record.exc_info[1]
                exception_types: list[str] = []
                seen: set[int] = set()
                while exception is not None and id(exception) not in seen:
                    seen.add(id(exception))
                    exception_types.append(type(exception).__qualname__)
                    exception = exception.__cause__ or exception.__context__
                payload["exception_type"] = exception_types
        return json.dumps(payload, default=_json_default, separators=(",", ":"))


class JsonLogTelemetrySink:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(TELEMETRY_LOGGER_NAME)

    def emit(self, record: TelemetryRecordV1) -> None:
        try:
            payload = asdict(record)
            payload["labels"] = {
                key: value[:_MAX_LABEL_VALUE_CHARS]
                for key, value in record.labels.items()
                if key in TELEMETRY_LABEL_KEYS
            }
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
