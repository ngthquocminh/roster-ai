"""Report whether AgentRuntime is constructable without probing its provider."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal
from uuid import UUID

from application.contracts.activity import TerminalOutcomeActivityV1
from application.ports.conversation import ConversationRepository

AgentAvailabilityReasonV1 = Literal["not_configured", "provider_error"]

# Story 3.9 proves product state, agent-originated activity, deterministic run
# behavior, saved results, and evidence remain independent of optional trace
# export. These two authoritative systems do not exist yet, so claiming them as
# covered would be circular rather than a proof (AD-12/NFR10).
SCOPE_CONTROLS = (
    "COVERS: telemetry:optional_and_non_authoritative; "
    "NOT COVERED: audit:owned_by_epic_4; "
    "NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6"
)


@dataclass(frozen=True)
class AgentAvailabilityV1:
    available: bool
    reason: AgentAvailabilityReasonV1 | None
    observed_at: datetime | None


def get_agent_availability(
    runtime_factory: Callable[[], object],
    repository: ConversationRepository,
    connection: Any,
    *,
    site_id: UUID,
    recency_seconds: float,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> AgentAvailabilityV1:
    """Use trusted configuration and recent durable evidence only.

    Constructing the runtime validates deployment configuration without model
    spend. Deliberately never call ``run_turn`` here: availability reads must
    not become unbudgeted provider probes.
    """

    now = clock()
    try:
        runtime_factory()
    except Exception:
        return AgentAvailabilityV1(
            available=False,
            reason="not_configured",
            observed_at=now,
        )

    event = repository.latest_terminal_outcome_for_site(
        connection,
        site_id=site_id,
    )
    if (
        event is not None
        and isinstance(event.payload, TerminalOutcomeActivityV1)
        and event.payload.outcome.reason == "provider_error"
        and event.occurred_at > now - timedelta(seconds=recency_seconds)
    ):
        return AgentAvailabilityV1(
            available=False,
            reason="provider_error",
            observed_at=event.occurred_at,
        )

    return AgentAvailabilityV1(available=True, reason=None, observed_at=None)


__all__ = [
    "AgentAvailabilityReasonV1",
    "AgentAvailabilityV1",
    "SCOPE_CONTROLS",
    "get_agent_availability",
]
