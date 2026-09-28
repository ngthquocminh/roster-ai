"""Turn router port: which path a new planner message takes.

Only message text crosses this port -- never scenario records, tool results or
the workflow snapshot. Implementations never raise; a failure is a closed
`error` code and the caller falls back to `scheduling`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol

TurnRoute = Literal["scheduling", "direct", "out_of_scope"]
TURN_ROUTES: tuple[TurnRoute, ...] = ("scheduling", "direct", "out_of_scope")


@dataclass(frozen=True)
class TurnRouteStateV1:
    message: str
    previous_planner_messages: tuple[str, ...] = ()
    previous_agent_replies: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnRouteResultV1:
    """Probability per route. `error` is a closed code, never provider text."""

    probabilities: Mapping[str, float] = field(default_factory=dict)
    error: str | None = None


class TurnRouter(Protocol):
    name: str
    #: Closed label for telemetry: "typesafe" or "openrouter".
    provider: str

    def route(self, state: TurnRouteStateV1) -> TurnRouteResultV1: ...


__all__ = [
    "TURN_ROUTES", "TurnRoute", "TurnRouteResultV1", "TurnRouteStateV1", "TurnRouter",
]
