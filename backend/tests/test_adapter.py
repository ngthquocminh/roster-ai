"""Adapter parses the real-schema fixture into a coherent SchedulingProblem."""
from __future__ import annotations

import os

from domain.types import DemandFamily
from ingest.input_adapter import load_problem

_FIXTURE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sample_tiny_input.json")


def test_adapter_loads_fixture():
    p = load_problem(_FIXTURE)
    assert p.horizon_h > 0
    assert len(p.members) > 0
    assert len(p.tasks) > 0
    assert len(p.templates) > 0
    assert len(p.demand) > 0


def test_all_three_demand_families_present():
    p = load_problem(_FIXTURE)
    families = {b.family for b in p.demand}
    assert DemandFamily.OUTBOUND in families
    assert DemandFamily.INBOUND in families
    assert DemandFamily.INDIRECT in families


def test_members_have_windows_and_rates():
    p = load_problem(_FIXTURE)
    for m in p.members:
        assert m.windows, f"{m.contact_id} has no windows"
        assert m.qualifications, f"{m.contact_id} has no qualifications"
        assert m.wage_per_hour > 0
        # every qualification carries a positive production rate
        assert all(q.rate > 0 for q in m.qualifications)
