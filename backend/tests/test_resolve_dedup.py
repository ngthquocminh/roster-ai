"""Unit-level coverage for constraint_service's dedupe-by-key resolution
helpers (CR-01/WR-04), independent of the shipped fixture.

Constructs synthetic Member/Task objects directly so the tests cover both:
- Multiple rows for the SAME entity (same contact_id/task_id) must collapse
  to a single candidate — no self-contradictory clarification, no duplicate
  "valid options" listing entries.
- Multiple rows for genuinely DIFFERENT entities must still trigger
  clarification, with each distinct name listed exactly once.
"""
from __future__ import annotations

from types import SimpleNamespace

from domain.types import Member, Task
from services.constraint_service import _resolve_member, _resolve_task


def _member(contact_id: str, name: str) -> Member:
    return Member(
        contact_id=contact_id,
        name=name,
        emp_type="Full Time",
        grade_id="grade-1",
        eba_id="eba-1",
        contracted_hours=38.0,
        wage_per_hour=30.0,
    )


def _task(task_id: str, name: str) -> Task:
    return Task(task_id=task_id, name=name, function="Pick", area_id="area-1")


class _FakeProblem(SimpleNamespace):
    def task(self, task_id: str):
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None


def test_resolve_member_dedupes_multiple_rows_for_same_person():
    """Two Member rows sharing one contact_id (e.g. two roster windows) must
    resolve as a single candidate, not trigger clarification (CR-01)."""
    problem = _FakeProblem(members=[
        _member("c1", "Jae Rerekura"),
        _member("c1", "Jae Rerekura"),
    ])

    result = _resolve_member(problem, "Jae")

    assert result.resolved_id == "c1"
    assert result.clarification is None
    assert result.error is None


def test_resolve_member_still_clarifies_for_genuinely_different_people():
    """Two DIFFERENT people whose names share a substring must still trigger
    clarification, with each name listed exactly once (not per-row)."""
    problem = _FakeProblem(members=[
        _member("c1", "Jae Rerekura"),
        _member("c1", "Jae Rerekura"),   # extra row for the same person
        _member("c2", "Jae Smith"),
    ])

    result = _resolve_member(problem, "Jae")

    assert result.resolved_id is None
    assert result.clarification is not None
    assert result.clarification.count("Jae Rerekura") == 1, (
        "A person with multiple rows must appear once in the clarification list"
    )
    assert "Jae Smith" in result.clarification


def test_resolve_member_zero_match_lists_each_person_once():
    """The zero-match 'Valid members' listing must not repeat a multi-row person."""
    problem = _FakeProblem(members=[
        _member("c1", "Jae Rerekura"),
        _member("c1", "Jae Rerekura"),
        _member("c2", "Gary Lau"),
    ])

    result = _resolve_member(problem, "NoSuchPerson")

    assert result.error is not None
    assert result.error.count("Jae Rerekura") == 1
    assert result.error.count("Gary Lau") == 1


def test_resolve_task_zero_match_lists_each_task_once():
    """WR-04: the 'Valid tasks' listing must not repeat a task_id that appears
    more than once in problem.tasks."""
    problem = _FakeProblem(tasks=[
        _task("t1", "C Pick"),
        _task("t1", "C Pick"),
        _task("t2", "F Pick"),
    ])

    result = _resolve_task(problem, "NoSuchTask")

    assert result.error is not None
    assert result.error.count("'C Pick'") == 1
    assert result.error.count("'F Pick'") == 1
