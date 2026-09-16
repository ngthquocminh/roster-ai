import pytest

from evals.live_conversations.facts import expected_metric, verify_claim


def test_volume_is_prorated_while_headcount_is_integrated():
    demand = [dict(task_id='t', family='outbound', unit='volume', amount=120,
                   start_minute=0, end_minute=60),
              dict(task_id='t', family='indirect', unit='headcount', amount=2,
                   start_minute=0, end_minute=60)]
    arguments = dict(task_id='t', start_minute=15, end_minute=45)
    assert expected_metric('required_demand_volume', {**arguments, 'family': 'outbound'}, demand=demand) == (60, 'units')
    assert expected_metric('required_headcount_minutes', {**arguments, 'family': 'indirect'}, demand=demand) == (60, 'minutes')
    with pytest.raises(ValueError, match='dimension mismatch'):
        expected_metric('required_headcount_minutes', {**arguments, 'family': 'outbound'}, demand=demand)


def test_assignment_or_qualification_cannot_be_scoped_by_demand_family():
    for metric in ('qualified_worker_count', 'staffed_minutes'):
        with pytest.raises(ValueError, match='family'):
            expected_metric(metric, dict(task_id='t', family='inbound'))


def test_independent_oracle_rejects_plausible_but_wrong_grounded_claim():
    workers = [dict(qualifications=[dict(task_id='t')]), dict(qualifications=[])]
    claim = dict(metric='qualified_worker_count', arguments=dict(task_id='t'),
                 verdict='supported', value=2, unit='workers')
    assert verify_claim(claim, workers=workers) == ['incorrect_claim_value_or_unit']
    assert verify_claim({**claim, 'value': 1}, workers=workers) == []
