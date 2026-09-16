"""Regression for the live scenario-wide worker question; not a task qualification count."""
import pytest
from pydantic import TypeAdapter

from application.capabilities.scheduling_compute import SchedulingComputeRequestV1
from application.contracts.grounding import ClaimArgumentsV1
from application.grounding.calculators import CalculationArgumentsError, calculate_metric
from tests.test_scheduling_compute import ProjectionStub, SCENARIO, VERSION, SITE


def test_scenario_count_has_a_valid_citable_tool_request_and_counts_unqualified_workers():
    request = TypeAdapter(SchedulingComputeRequestV1).validate_python({'metric': 'worker_count', 'arguments': {}})
    result = calculate_metric(ProjectionStub(), None, scenario_id=SCENARIO,
        scenario_version_id=VERSION, site_id=SITE, metric=request.metric, arguments=request.arguments,
        page_size=1)
    assert result.value == 3 and result.unit == 'workers'
    assert result.consumed_row_count == 3
    assert {ref.record_id for ref in result.evidence_refs} == {'w1', 'w2', 'w3'}


@pytest.mark.parametrize('arguments', [ClaimArgumentsV1(task_id='pick'),
    ClaimArgumentsV1(family='outbound'), ClaimArgumentsV1(start_minute=0, end_minute=60)])
def test_scenario_count_rejects_arguments_that_would_misrepresent_its_scope(arguments):
    with pytest.raises(CalculationArgumentsError):
        calculate_metric(ProjectionStub(), None, scenario_id=SCENARIO,
            scenario_version_id=VERSION, site_id=SITE, metric='worker_count', arguments=arguments)
