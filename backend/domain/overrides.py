"""Override domain types — the seam decoupling the engine from the LLM layer.

Pure-domain module: imports only stdlib. No solver, web, or LLM imports.
The engine references OverrideCall; LLM providers produce it — neither imports
the other.

Content-hash ids (override_id) make identical constraints idempotent: re-submitting
the same NL constraint maps to the same key and overwrites in place (D-04/D-05).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OverrideCall:
    """A validated, provider-neutral solver override.

    Fields
    ------
    id   : content-hash identifier (see override_id()); used as the JSON-store key (D-04).
    tool : tool name, e.g. "set_min_workers_per_task" (the only tool in Phase 1, D-01).
    args : tool arguments, e.g. {"task_id": "Pick", "n": 2}. Typed loosely so Phase 2+
           tools can add new arg shapes without touching this class.

    Note: frozen=True with a dict field means instances are not hashable by default —
    that is intentional; the JSON store keys by `id`, not by hashing the object (D-04).
    """

    id: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


def override_id(tool: str, args: dict[str, Any]) -> str:
    """Return a stable content-hash id for a (tool, args) pair (D-05).

    The id is ``"ov_" + sha256(tool + canonical_args)[:8]`` where
    ``canonical_args`` is JSON with sorted keys so key order does not affect
    the hash. Identical constraints therefore map to the same id regardless of
    how the caller ordered the argument dict.

    Example
    -------
    >>> override_id("set_min_workers_per_task", {"n": 2, "task_id": "Pick"})
    >>> # same as override_id(..., {"task_id": "Pick", "n": 2})
    """
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((tool + canonical).encode()).hexdigest()
    return "ov_" + digest[:8]
