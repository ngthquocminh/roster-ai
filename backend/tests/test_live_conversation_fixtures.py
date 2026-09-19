import pytest

from evals.live_conversations.fixtures import _run_feasible_candidate
from evals.live_conversations.protocol import IncompleteConversationRun


class App:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.requests = []

    def _request(self, method, path, *, command, body):
        self.requests.append((method, path, command, body))
        return {'schedule_run_id': f'run-{len(self.requests)}'}

    def wait_for_run(self, run_id):
        status = next(self.outcomes)
        return {'run': {'schedule_run_id': run_id, 'status': status},
                'candidate': {'schedule_version_id': 'candidate'} if status == 'solver_completed' else None}


def test_fixture_seed_retries_once_and_retains_both_run_outcomes():
    app = App(['solver_failed', 'solver_completed'])
    terminal, attempts = _run_feasible_candidate(app, proposal_id='proposal', resource_version=1)
    assert terminal['candidate']['schedule_version_id'] == 'candidate'
    assert [run['status'] for run in attempts] == ['solver_failed', 'solver_completed']
    assert len(app.requests) == 2


def test_fixture_seed_fails_closed_after_bounded_retry():
    with pytest.raises(IncompleteConversationRun, match='after_retry'):
        _run_feasible_candidate(App(['solver_failed', 'solver_infeasible']),
                                proposal_id='proposal', resource_version=1)
