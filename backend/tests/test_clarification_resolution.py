from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from application.capabilities.deps import AgentDepsV1
from application.clarification.resolve import resolve_clarification
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.dialogue import (
    ClarificationV1,
    EntityCandidateProposalV1,
)
from application.contracts.scenario_projection import TaskV1, WorkerV1


class RecordingProjectionReader:
    def __init__(self, outcomes: dict[tuple[str, str], object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, UUID, UUID, str]] = []

    def _resolve(
        self, resolver: str, _connection: object, scenario_id: UUID,
        scenario_version_id: UUID, record_id: str,
    ) -> object:
        self.calls.append((resolver, scenario_id, scenario_version_id, record_id))
        return self.outcomes[(resolver, record_id)]

    def resolve_task(self, *args):
        return self._resolve("resolve_task", *args)

    def resolve_worker(self, *args):
        return self._resolve("resolve_worker", *args)


def _deps(reader: RecordingProjectionReader, version_id: UUID) -> AgentDepsV1:
    return AgentDepsV1(
        actor_id=UUID(int=1),
        site_id=UUID(int=2),
        membership_id=UUID(int=3),
        request_id=UUID(int=4),
        agent_run_id=UUID(int=5),
        conversation_id=UUID(int=6),
        scenario_id=UUID(int=7),
        scenario_version_id=version_id,
        policy_version="one-user-mvp-v1",
        clock=lambda: datetime.now(timezone.utc),
        projection_reader=reader,
        connection=object(),
        remaining_budget=AgentBudgetV1(),
    )


def test_resolves_all_candidates_with_application_owned_grid_labels() -> None:
    version_id = uuid4()
    task = TaskV1("task-record", "TASK-7", "Pick", "Pick", "A", "Area", None)
    worker = WorkerV1(
        "worker-record", "CONTACT-9", "Taylor", "casual", "1", "EBA", 8.0, (), ()
    )
    reader = RecordingProjectionReader(
        {
            ("resolve_task", "task-record"): SimpleNamespace(
                outcome="resolved", current_scenario_version_id=version_id, item=task
            ),
            ("resolve_worker", "worker-record"): SimpleNamespace(
                outcome="resolved", current_scenario_version_id=version_id, item=worker
            ),
        }
    )
    clarification = ClarificationV1(
        question="Which record?",
        candidates=(
            EntityCandidateProposalV1(group="work-areas-and-tasks", record_id="task-record"),
            EntityCandidateProposalV1(group="workers", record_id="worker-record"),
        ),
    )

    resolved = resolve_clarification(clarification, _deps(reader, version_id))

    assert [candidate.label for candidate in resolved.candidates] == ["TASK-7", "CONTACT-9"]
    assert resolved.scenario_version_id == version_id
    assert resolved.dropped_candidate_count == 0


def test_missing_candidate_is_dropped_after_exactly_one_cited_lookup() -> None:
    version_id = uuid4()
    reader = RecordingProjectionReader(
        {
            ("resolve_worker", "plausible-wrong-label"): SimpleNamespace(
                outcome="not_found", current_scenario_version_id=version_id, item=None
            )
        }
    )
    clarification = ClarificationV1(
        question="Did you mean plausible-wrong-label?",
        candidates=(
            EntityCandidateProposalV1(
                group="workers", record_id="plausible-wrong-label"
            ),
        ),
    )

    resolved = resolve_clarification(clarification, _deps(reader, version_id))

    assert resolved.candidates == ()
    assert resolved.dropped_candidate_count == 1
    assert reader.calls == [
        ("resolve_worker", UUID(int=7), version_id, "plausible-wrong-label")
    ]
    assert not any(
        candidate.label == "plausible-wrong-label"
        for candidate in resolved.candidates
    )


def test_zero_candidates_is_a_valid_persistable_clarification() -> None:
    version_id = uuid4()
    reader = RecordingProjectionReader({})

    resolved = resolve_clarification(
        ClarificationV1(question="Which time window?"),
        _deps(reader, version_id),
    )

    assert asdict(resolved) == {
        "question": "Which time window?",
        "candidates": (),
        "scenario_version_id": version_id,
        "dropped_candidate_count": 0,
        "schema_version": "1",
    }
    assert reader.calls == []


def test_version_mismatch_is_dropped_without_retargeting() -> None:
    version_id = uuid4()
    other_version = uuid4()
    worker = WorkerV1(
        "worker-record", "CONTACT-9", "Taylor", "casual", "1", "EBA", 8.0, (), ()
    )
    reader = RecordingProjectionReader(
        {
            ("resolve_worker", "worker-record"): SimpleNamespace(
                outcome="resolved", current_scenario_version_id=other_version, item=worker
            )
        }
    )

    resolved = resolve_clarification(
        ClarificationV1(
            question="Which worker?",
            candidates=(EntityCandidateProposalV1(group="workers", record_id="worker-record"),),
        ),
        _deps(reader, version_id),
    )

    assert resolved.candidates == ()
    assert resolved.dropped_candidate_count == 1
    assert len(reader.calls) == 1
