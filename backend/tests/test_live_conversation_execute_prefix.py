"""The checks that stop the live proof passing on a false baseline, solver or draft
effect (Story 5.7 test-suite review). Each reason code is driven through
`execute_prefix` against a canned application; none of this is live evidence."""
import pytest

from evals.live_conversations import runner
from evals.live_conversations.cases import ConversationScenario, ConversationTurn
from evals.live_conversations.http_client import ApplicationConversation
from evals.live_conversations.protocol import ConversationBudget, IncompleteConversationRun
from evals.live_conversations.runner import execute_prefix
from evals.report import LiveSuiteBudgetV1
from tests.test_live_conversation_protocol import judgment

VERSION = 'ver-1'
CANDIDATE = 'cand-1'
CANDIDATE_ROWS = [
    {'record_id': 'a1', 'worker_id': 'w1', 'task_id': 't1', 'shift_id': None,
     'start_minute': 0, 'end_minute': 60},
]
APPROVAL = {'activity_type': 'approval_request', 'approval_id': 'ap-1',
            'candidate_schedule_version_id': CANDIDATE, 'schedule_run_id': 'sr-1'}
COMPLETED = {'run': {'status': 'solver_completed'},
             'candidate': {'schedule_version_id': CANDIDATE, 'assignments': CANDIDATE_ROWS,
                           'feasible_solver_status': 'OPTIMAL', 'assignment_count': 1}}


class FakeApp:
    """Only what `execute_prefix` touches; every effect is a settable attribute."""

    fixture = {'scenario_id': 'sc-1', 'scenario_version_id': VERSION}

    def __init__(self, *, activity, run_result=COMPLETED):
        self.activity = activity
        self.run_result = run_result
        self.baseline = 'base-0'
        self.baseline_after_decision = CANDIDATE
        self.provenance = {'items': [{'item_type': 'baseline_promotion', 'after_version': CANDIDATE}]}
        self.assignments_after_approval = CANDIDATE_ROWS
        self.groups = {'workers': [], 'work-areas-and-tasks': [], 'demand': [], 'locks': [],
                       'constraints-and-objectives': [], 'baseline-assignments': []}
        self.drift_baseline_after_first_read = False
        self._projection_reads = 0

    def create(self):
        return {'id': 'conv-1'}

    def projection(self, group, *, limit=200, cursor=0):
        items = self.groups[group]
        return {'scenario_version_id': VERSION, 'items': items, 'next_cursor': None,
                'matching_count': len(items)}

    def _request(self, method, path, **_kwargs):
        if path.endswith('/projection'):
            self._projection_reads += 1
            if self.drift_baseline_after_first_read and self._projection_reads > 1:
                return {'baseline_schedule_version': 'drifted'}
            return {'baseline_schedule_version': self.baseline}
        if '/approvals/provenance' in path:
            return self.provenance
        raise AssertionError('unexpected request ' + path)

    def send(self, _user):
        return ({'agent_run_id': 'run-1'},
                {'agent_run_status': 'agent_completed', 'activity': self.activity})

    def latest_draft(self):
        return {'proposal_id': 'p-1'}

    def run_optimization(self):
        return {'schedule_run_id': 'sr-1'}

    def cancel_run(self, run):
        return run

    def wait_for_run(self, _run_id):
        return self.run_result

    def decide(self, _approval_id, *, decision):
        self.baseline = self.baseline_after_decision
        self.groups['baseline-assignments'] = self.assignments_after_approval
        return {'decision': decision}


class Telemetry:
    def read_run(self, _run_id):
        return ({'usage': {'requests': 1, 'input_tokens': 10, 'output_tokens': 5},
                 'estimated_cost_usd': .001}, [])


@pytest.fixture(autouse=True)
def _judge_always_passes(monkeypatch):
    # Isolate the harness's own effect checks: the judge would otherwise be a
    # second reason for a turn to fail, and would need a network.
    monkeypatch.setattr(runner, 'judge_turn', lambda **_kwargs: (judgment(), {'attempts': []}))


def drive(app, *actions, requires_persisted_draft=False):
    case = ConversationScenario(id='X', prefixes=(1,), turns=(ConversationTurn(
        user='go', obligation='Answer', actions_after=tuple(actions),
        requires_persisted_draft=requires_persisted_draft),))
    return execute_prefix(app=app, case=case, endpoint=1, isolation_id='iso', telemetry=Telemetry(),
                          judge_key='k', judge_model='m', budget=ConversationBudget(LiveSuiteBudgetV1(
                              case_limit=1, request_limit=50, tool_call_limit=50, token_limit=1000000,
                              elapsed_seconds_limit=600, spend_usd_limit=5)),
                          save=lambda _report: None)


def failures_of(report):
    return report['turns'][0]['factual_failures']


def test_a_clean_approve_cycle_records_no_failure_and_passes():
    # The control: every negative below differs from this by exactly one effect.
    report = drive(FakeApp(activity=APPROVAL), 'run_optimization', 'approve')
    assert failures_of(report) == [] and report['status'] == 'passed'


@pytest.mark.parametrize('status,action', [('solver_failed', 'run_optimization'),
                                           ('solver_infeasible', 'run_optimization'),
                                           ('solver_completed', 'run_and_cancel')])
def test_a_solver_outcome_other_than_the_required_one_is_a_failure(status, action):
    app = FakeApp(activity={'activity_type': 'agent_response', 'response': {'segments': []}},
                  run_result={'run': {'status': status}, 'candidate': None})
    assert 'required_solver_outcome_missing' in failures_of(drive(app, action))
    assert drive(app, action)['status'] == 'failed'


def test_a_cancelled_run_is_the_required_outcome_for_run_and_cancel():
    app = FakeApp(activity={'activity_type': 'agent_response', 'response': {'segments': []}},
                  run_result={'run': {'status': 'solver_cancelled'}, 'candidate': None})
    assert failures_of(drive(app, 'run_and_cancel')) == []


def test_approval_that_leaves_a_different_baseline_than_the_candidate_fails():
    app = FakeApp(activity=APPROVAL)
    app.baseline_after_decision = 'some-other-version'
    assert 'incorrect_baseline_after_decision' in failures_of(drive(app, 'run_optimization', 'approve'))


def test_rejection_that_changes_the_baseline_fails():
    app = FakeApp(activity=APPROVAL)  # decide() promotes the candidate even on reject
    assert 'incorrect_baseline_after_decision' in failures_of(drive(app, 'reject_approval'))


def test_rejection_that_leaves_the_baseline_alone_is_clean():
    app = FakeApp(activity=APPROVAL)
    app.baseline_after_decision = 'base-0'
    assert failures_of(drive(app, 'reject_approval')) == []


@pytest.mark.parametrize('items', [
    [],
    [{'item_type': 'baseline_promotion', 'after_version': CANDIDATE}] * 2,
    [{'item_type': 'baseline_promotion', 'after_version': 'not-the-candidate'}],
    [{'item_type': 'approval_decision', 'after_version': CANDIDATE}],
])
def test_a_promotion_that_is_not_recorded_exactly_once_for_the_candidate_fails(items):
    app = FakeApp(activity=APPROVAL)
    app.provenance = {'items': items}
    assert 'baseline_promotion_provenance_not_exactly_once' in failures_of(
        drive(app, 'run_optimization', 'approve'))


@pytest.mark.parametrize('after', [
    [],
    [{**CANDIDATE_ROWS[0], 'worker_id': 'someone-else'}],
    [{**CANDIDATE_ROWS[0], 'end_minute': 90}],
    CANDIDATE_ROWS * 2,
])
def test_promoted_assignments_that_differ_from_the_candidate_fail(after):
    app = FakeApp(activity=APPROVAL)
    app.assignments_after_approval = after
    assert 'promoted_assignments_do_not_match_candidate' in failures_of(
        drive(app, 'run_optimization', 'approve'))


def test_a_candidate_with_no_assignments_cannot_prove_the_promotion():
    app = FakeApp(activity=APPROVAL,
                  run_result={'run': {'status': 'solver_completed'},
                              'candidate': {'schedule_version_id': CANDIDATE, 'assignments': []}})
    app.assignments_after_approval = []
    assert 'promoted_assignments_do_not_match_candidate' in failures_of(
        drive(app, 'run_optimization', 'approve'))


def test_a_baseline_that_moves_before_approval_is_a_failure():
    app = FakeApp(activity={'activity_type': 'agent_response', 'response': {'segments': []}})
    app.drift_baseline_after_first_read = True
    assert 'baseline_changed_before_approval' in failures_of(drive(app, 'verify_baseline_unchanged'))


def test_approving_with_no_agent_approval_is_incomplete_not_a_pass():
    app = FakeApp(activity={'activity_type': 'agent_response', 'response': {'segments': []}})
    report = drive(app, 'approve')
    assert report['status'] == 'incomplete'
    assert report['incomplete_reason'] == 'required_agent_approval_missing'


def test_a_reply_that_is_not_a_draft_fails_a_turn_that_requires_one():
    app = FakeApp(activity={'activity_type': 'agent_response', 'response': {'segments': []}})
    assert 'required_persisted_draft_missing' in failures_of(
        drive(app, requires_persisted_draft=True))


def test_an_unauthored_action_is_incomplete():
    app = FakeApp(activity={'activity_type': 'agent_response', 'response': {'segments': []}})
    assert drive(app, 'launch_missiles')['incomplete_reason'] == 'unsupported_authored_action'


# --- the client's fail-closed draft and approval reads -------------------------

def client_with(responses):
    app = ApplicationConversation.__new__(ApplicationConversation)
    app.conversation = {'id': 'c-1'}
    app._request = lambda method, path, **_kwargs: responses(path)
    return app


def timeline(*, has_more=False, drafts=1):
    return {'has_more': has_more, 'items': [
        {'activity_type': 'draft', 'proposal_id': f'p-{i}'} for i in range(drafts)]}


def test_a_truncated_timeline_cannot_prove_which_draft_is_latest():
    app = client_with(lambda path: timeline(has_more=True))
    with pytest.raises(IncompleteConversationRun, match='timeline_truncated'):
        app.latest_draft()


@pytest.mark.parametrize('proposal', [{'state': 'rejected', 'stale': False},
                                      {'state': 'active', 'stale': True}])
def test_a_draft_that_is_not_current_cannot_be_optimized(proposal):
    app = client_with(lambda path: proposal if '/proposals/' in path else timeline())
    with pytest.raises(IncompleteConversationRun, match='required_draft_not_current'):
        app.latest_draft()


def test_the_latest_of_several_drafts_is_the_one_resolved():
    seen = []

    def responses(path):
        seen.append(path)
        return {'state': 'active', 'stale': False} if '/proposals/' in path else timeline(drafts=3)

    client_with(responses).latest_draft()
    assert seen[-1].endswith('/proposals/p-2')


def test_a_decision_on_an_approval_that_is_not_pending_is_refused():
    app = client_with(lambda path: {'state': 'approved', 'resource_version': 1})
    with pytest.raises(IncompleteConversationRun, match='required_pending_approval_missing'):
        app.decide('ap-1', decision='approve')


def test_a_decision_must_be_explicit():
    with pytest.raises(ValueError):
        client_with(lambda path: {}).decide('ap-1', decision='maybe')
