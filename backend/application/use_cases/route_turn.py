"""Decide a new planner turn's route; fails open to `scheduling`."""
from __future__ import annotations

from dataclasses import dataclass

from application.contracts.activity import (
    ActivityItemV1,
    AgentResponseActivityV1,
    ApprovalRequestActivityV1,
    ClarificationActivityV1,
    DraftActivityV1,
    PlannerMessageActivityV1,
)
from application.ports.turn_router import TURN_ROUTES, TurnRoute, TurnRouter, TurnRouteStateV1
from application.use_cases.execute_turn import _response_visible_text

#: The latest message keeps more room: a scheduling ask after a long preamble
#: must stay visible, or the whole turn could be refused.
LATEST_MESSAGE_CHAR_LIMIT = 2000
MESSAGE_CHAR_LIMIT = 500
PREVIOUS_MESSAGES = 2


@dataclass(frozen=True)
class TurnRouteDecisionV1:
    route: TurnRoute = "scheduling"
    #: The router's probability for `route`; None when no router answered.
    probability: float | None = None
    error: str | None = None


def _last(texts: list[str]) -> tuple[str, ...]:
    kept = [text.strip()[:MESSAGE_CHAR_LIMIT] for text in texts if text.strip()]
    return tuple(kept[-PREVIOUS_MESSAGES:])


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
        elif isinstance(activity, (DraftActivityV1, ApprovalRequestActivityV1)):
            # "yes, do that" after a draft must still read as scheduling.
            agent.append(activity.consequence_summary)
    return TurnRouteStateV1(
        message=prompt.strip()[:LATEST_MESSAGE_CHAR_LIMIT],
        previous_planner_messages=_last(planner),
        previous_agent_replies=_last(agent),
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
    # Ties resolve in TURN_ROUTES order, so `scheduling` wins any tie.
    top = max(TURN_ROUTES, key=lambda route: result.probabilities.get(route, 0.0))
    probability = result.probabilities.get(top, 0.0)
    if top in ("direct", "out_of_scope") and probability >= threshold:
        return TurnRouteDecisionV1(route=top, probability=probability)
    return TurnRouteDecisionV1(
        probability=result.probabilities.get("scheduling"),
    )


__all__ = ["TurnRouteDecisionV1", "decide_route", "route_state"]
