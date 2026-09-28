"""Decide a new planner turn's route; fails open to `scheduling`."""
from __future__ import annotations

from dataclasses import dataclass

from application.contracts.activity import (
    ActivityItemV1,
    AgentResponseActivityV1,
    ClarificationActivityV1,
    PlannerMessageActivityV1,
)
from application.ports.turn_router import TurnRoute, TurnRouter, TurnRouteStateV1
from application.use_cases.execute_turn import _response_visible_text

MESSAGE_CHAR_LIMIT = 500
PREVIOUS_MESSAGES = 2


@dataclass(frozen=True)
class TurnRouteDecisionV1:
    route: TurnRoute = "scheduling"
    #: The router's probability for `route`; None when no router answered.
    probability: float | None = None
    error: str | None = None


def _truncate(text: str) -> str:
    return text.strip()[:MESSAGE_CHAR_LIMIT]


def route_state(prompt: str, history: tuple[ActivityItemV1, ...]) -> TurnRouteStateV1:
    planner: list[str] = []
    agent: list[str] = []
    for activity in history:
        if isinstance(activity, PlannerMessageActivityV1):
            planner.append(activity.text)
        elif isinstance(activity, AgentResponseActivityV1):
            agent.append(_response_visible_text(activity.response))
        elif isinstance(activity, ClarificationActivityV1):
            agent.append(activity.clarification.question)
    return TurnRouteStateV1(
        message=_truncate(prompt),
        previous_planner_messages=tuple(
            _truncate(text) for text in planner[-PREVIOUS_MESSAGES:] if text.strip()),
        previous_agent_replies=tuple(
            _truncate(text) for text in agent[-PREVIOUS_MESSAGES:] if text.strip()),
    )


def decide_route(
    router: TurnRouter | None,
    *,
    prompt: str,
    history: tuple[ActivityItemV1, ...],
    threshold: float,
) -> TurnRouteDecisionV1:
    """A special route only when the router gives it at least `threshold`."""
    if router is None:
        return TurnRouteDecisionV1()
    try:
        result = router.route(route_state(prompt, history))
    except Exception:  # noqa: BLE001 - routing never fails a turn
        return TurnRouteDecisionV1(error="router_exception")
    if result.error is not None or not result.probabilities:
        return TurnRouteDecisionV1(error=result.error or "bad_response")
    top = max(result.probabilities, key=result.probabilities.__getitem__)
    probability = result.probabilities[top]
    if top in ("direct", "out_of_scope") and probability >= threshold:
        return TurnRouteDecisionV1(route=top, probability=probability)
    return TurnRouteDecisionV1(
        probability=result.probabilities.get("scheduling"),
    )


__all__ = ["TurnRouteDecisionV1", "decide_route", "route_state"]
