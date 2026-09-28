"""TypeSafe Jev turn router: one `choice` question per new planner message.

Same endpoints, auth and closed error codes as the tier-1 claim checker. The
state holds message text only. Never raises.
"""
from __future__ import annotations

import json

import httpx

from application.ports.turn_router import TURN_ROUTES, TurnRouteResultV1, TurnRouteStateV1

_INSTRUCTIONS = (
    "Route the planner's latest message (`state.message`) to a workforce scheduling "
    "assistant. `state.previous_planner_messages` and `state.previous_agent_replies` are "
    "the earlier conversation, for context only."
)
_CRITERIA = {
    "scheduling": (
        "asks about, or to change, the schedule, workers, tasks, demand, drafts, runs or "
        "baseline; or refers back to earlier conversation; or mixes any of that with "
        "something else"
    ),
    "direct": (
        "only a greeting, thanks, small talk, or a question about what the assistant can do "
        "or how the workflow works"
    ),
    "out_of_scope": (
        "clearly unrelated to workforce scheduling or this app, with no scheduling request "
        "in it"
    ),
}


def _payload(model: str, state: TurnRouteStateV1) -> dict:
    return {
        "model": model,
        "state": {
            "message": state.message,
            "previous_planner_messages": list(state.previous_planner_messages),
            "previous_agent_replies": list(state.previous_agent_replies),
        },
        "questions": {
            "route": {"type": "choice", "instructions": _INSTRUCTIONS, "criteria": _CRITERIA},
        },
    }


def _probabilities(response: dict) -> dict[str, float]:
    raw = response["answers"]["route"]["probabilities"]
    values: dict[str, float] = {}
    for route in TURN_ROUTES:
        value = raw[route]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("probability is not a number")
        if not 0.0 <= value <= 1.0:
            raise ValueError("probability out of range")
        values[route] = float(value)
    if abs(sum(values.values()) - 1.0) > 0.05:
        raise ValueError("probabilities do not sum to 1")
    return values


class JevTurnRouter:
    def __init__(
        self, *, endpoint: str, api_key: str, model: str, timeout_seconds: float,
        provider: str = "typesafe", client: httpx.Client | None = None,
    ) -> None:
        self.name = f"jev:{model}"
        self.provider = provider
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._client = client

    def _post(self, body: dict) -> dict:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        post = self._client.post if self._client is not None else httpx.post
        response = post(self._endpoint, json=body, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def route(self, state: TurnRouteStateV1) -> TurnRouteResultV1:
        try:
            return TurnRouteResultV1(
                probabilities=_probabilities(self._post(_payload(self._model, state))))
        except httpx.TimeoutException:
            code = "timeout"
        except httpx.HTTPStatusError as exc:
            code = f"http_{exc.response.status_code}"
        except httpx.HTTPError:
            code = "transport_error"
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            code = "bad_response"
        except Exception:  # noqa: BLE001 - the port must never raise
            code = "router_exception"
        return TurnRouteResultV1(error=code)


__all__ = ["JevTurnRouter"]
