"""RFC 8785 JSON Canonicalization Scheme (JCS) serialization."""
from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


def _quote_string(value: str) -> str:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError("RFC 8785 does not permit lone Unicode surrogates")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _serialize_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("RFC 8785 numbers must be finite")
    if value == 0:
        return "0"

    representation = repr(value).lower()
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        if "e" in representation:
            representation = format(Decimal(representation), "f")
        if "." in representation:
            representation = representation.rstrip("0").rstrip(".")
        return representation

    if "e" not in representation:
        representation = format(Decimal(representation).normalize(), "e")
    mantissa, exponent = representation.split("e", 1)
    mantissa = mantissa.rstrip("0").rstrip(".")
    exponent_value = int(exponent)
    exponent_sign = "+" if exponent_value >= 0 else ""
    return f"{mantissa}e{exponent_sign}{exponent_value}"


def _serialize_number(value: int | float) -> str:
    if isinstance(value, int):
        if -(2**53) <= value <= 2**53:
            return str(value)
        try:
            as_float = float(value)
        except OverflowError as exc:
            raise ValueError(
                "RFC 8785 integers must be expressible as IEEE 754 doubles"
            ) from exc
        if int(as_float) != value:
            raise ValueError(
                "RFC 8785 integers must be exactly representable as IEEE 754 "
                "doubles — this value would silently lose precision"
            )
        return _serialize_float(as_float)
    return _serialize_float(value)


def _utf16_sort_key(value: str) -> bytes:
    _quote_string(value)
    return value.encode("utf-16-be")


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quote_string(value)
    if isinstance(value, (int, float)):
        return _serialize_number(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("RFC 8785 object property names must be strings")
        members = (
            f"{_quote_string(key)}:{_serialize(value[key])}"
            for key in sorted(value, key=_utf16_sort_key)
        )
        return "{" + ",".join(members) + "}"
    raise ValueError(f"Value is not an I-JSON data type: {type(value).__name__}")


def canonicalize_json(value: Any) -> bytes:
    """Return the RFC 8785 canonical UTF-8 representation of ``value``."""
    return _serialize(value).encode("utf-8")
