"""Per-turn draft state shared by `scheduling_draft` and `scheduling_draft_discard`.

Same standing as `EvidenceRegistry`: built fresh with every `AgentDepsV1`, so it
is per-turn by construction. It carries the one fact a draft tool needs from the
Scheduling aggregate -- the conversation's working draft as this turn first saw
it -- without giving a tool a proposal repository (spec 2.1, Story 5.11 C2).
"""
from __future__ import annotations

from typing import Callable

from application.contracts.proposal import WorkingDraftObservationV1


class DraftTurnState:
    def __init__(
        self, read_working: Callable[[], WorkingDraftObservationV1 | None]
    ) -> None:
        self._read_working = read_working
        self._observed = False
        self._observation: WorkingDraftObservationV1 | None = None
        self.drafted = False
        self.discarded: WorkingDraftObservationV1 | None = None

    def observe(self) -> WorkingDraftObservationV1 | None:
        """Read the working draft ONCE per turn and memoize it.

        Every call in a turn resolves against the same pre-turn state and records
        the same observation (spec 2.1); a re-read would let two drafts in one
        turn see different worlds. A change after this read is exactly what the
        finalize guard catches.
        """
        if not self._observed:
            self._observation = self._read_working()
            self._observed = True
        return self._observation

    def note_drafted(self) -> None:
        self.drafted = True

    def record_discard(self, observation: WorkingDraftObservationV1) -> None:
        self.discarded = observation


__all__ = ["DraftTurnState"]
