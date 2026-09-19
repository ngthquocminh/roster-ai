import pytest

from evals.live_conversations.protocol import ConversationBudget
from evals.live_conversations.smoke_cases import ConversationToolSmokeCase
from evals.live_conversations.smoke_runner import execute_conversation_smoke
from evals.report import LiveSuiteBudgetV1


def budget():
    return ConversationBudget(LiveSuiteBudgetV1(
        case_limit=1, request_limit=20, tool_call_limit=20, token_limit=500000,
        elapsed_seconds_limit=60, spend_usd_limit=1))


class App:
    def __init__(self):
        self.count = 0

    def create(self):
        return {'id': 'conversation'}

    def send(self, _user):
        self.count += 1
        return ({'agent_run_id': f'run-{self.count}'},
                {'agent_run_status': 'agent_completed',
                 'activity': {'activity_type': 'agent_response'}})


class Telemetry:
    def __init__(self, tools):
        self.tools = tools

    def read_run(self, run_id):
        number = int(run_id[-1])
        tool_rows = [{'labels': (name if isinstance(name, dict)
                                 else {'capability_name': name})}
                     for name in self.tools[number - 1]]
        return ({'usage': {'requests': 1, 'input_tokens': 10, 'output_tokens': 5},
                 'estimated_cost_usd': .001}, tool_rows)


def test_smoke_passes_only_when_greeting_is_tool_free_and_second_turn_uses_exact_tool_once():
    case = ConversationToolSmokeCase(id='inspect', capability='scheduling_inspect', first_turn='Hi',
        second_turn='Overview please', precondition='baseline', expected_activity='agent_response')
    report = execute_conversation_smoke(app=App(), case=case,
        telemetry=Telemetry([[], ['scheduling_inspect']]), budget=budget(), save=lambda _: None)
    assert report['status'] == 'passed'
    assert report['turns'][1]['tool_outcomes'] == [
        {'capability_name': 'scheduling_inspect'}]


def test_smoke_fails_when_the_agent_uses_a_tool_for_the_greeting_or_extra_tool_for_question():
    case = ConversationToolSmokeCase(id='inspect', capability='scheduling_inspect', first_turn='Hi',
        second_turn='Overview please', precondition='baseline', expected_activity='agent_response')
    report = execute_conversation_smoke(app=App(), case=case,
        telemetry=Telemetry([['scheduling_inspect'], ['scheduling_inspect', 'scheduling_compute']]),
        budget=budget(), save=lambda _: None)
    assert report['status'] == 'failed'
    assert [turn['status'] for turn in report['turns']] == ['failed', 'failed']


def test_smoke_preserves_only_safe_closed_tool_outcome_labels():
    case = ConversationToolSmokeCase(id='draft', capability='scheduling_draft', first_turn='Hi',
        second_turn='Draft it', precondition='baseline', expected_activity='draft')
    report = execute_conversation_smoke(app=App(), case=case,
        telemetry=Telemetry([[], [
            {'capability_name': 'scheduling_draft', 'failure_reason': 'invalid_query',
             'unsafe_detail': 'must not enter evidence'},
            {'capability_name': 'scheduling_draft'},
        ]]), budget=budget(), save=lambda _: None)
    assert report['turns'][1]['tool_outcomes'] == [
        {'capability_name': 'scheduling_draft', 'failure_reason': 'invalid_query'},
        {'capability_name': 'scheduling_draft'},
    ]


class _Turns(App):
    """An application whose second turn ends however the test says."""

    def __init__(self, *, status='agent_completed', activity='agent_response'):
        super().__init__()
        self.second = (status, activity)

    def send(self, _user):
        self.count += 1
        status, activity = ('agent_completed', 'agent_response') if self.count == 1 else self.second
        return ({'agent_run_id': f'run-{self.count}'},
                {'agent_run_status': status, 'activity': {'activity_type': activity}})


def _inspect_case(**changes):
    return ConversationToolSmokeCase(**{**dict(id='inspect', capability='scheduling_inspect',
        first_turn='Hi', second_turn='Overview please', precondition='baseline',
        expected_activity='agent_response'), **changes})


def _smoke(app, telemetry, case=None, spend_limit=1):
    used = ConversationBudget(LiveSuiteBudgetV1(case_limit=1, request_limit=20, tool_call_limit=20,
        token_limit=500000, elapsed_seconds_limit=60, spend_usd_limit=spend_limit))
    return execute_conversation_smoke(app=app, case=case or _inspect_case(), telemetry=telemetry,
                                      budget=used, save=lambda _: None), used


def test_a_second_turn_that_calls_no_tool_fails_the_smoke():
    report, _ = _smoke(App(), Telemetry([[], []]))
    assert report['status'] == 'failed' and report['turns'][1]['status'] == 'failed'


def test_a_second_turn_that_calls_the_wrong_tool_fails_the_smoke():
    report, _ = _smoke(App(), Telemetry([[], ['scheduling_compute']]))
    assert report['turns'][1]['status'] == 'failed'


def test_a_reply_of_the_wrong_kind_fails_even_with_the_right_tool():
    report, _ = _smoke(_Turns(activity='clarification'), Telemetry([[], ['scheduling_inspect']]))
    assert report['turns'][1]['status'] == 'failed'


def test_an_approval_case_needs_the_run_to_suspend_for_approval():
    case = _inspect_case(capability='scheduling_baseline', expected_activity='approval_request')
    telemetry = lambda: Telemetry([[], ['scheduling_baseline']])
    passed, _ = _smoke(_Turns(status='approval_required', activity='approval_request'), telemetry(), case)
    failed, _ = _smoke(_Turns(status='agent_completed', activity='approval_request'), telemetry(), case)
    assert passed['status'] == 'passed' and failed['status'] == 'failed'


class _NoUsageTelemetry(Telemetry):
    def read_run(self, run_id):
        _usage, tools = super().read_run(run_id)
        return {'usage_unavailable': True}, tools


def test_a_turn_with_no_recoverable_usage_is_charged_the_full_reservation_and_still_scored():
    report, used = _smoke(App(), _NoUsageTelemetry([[], ['scheduling_inspect']]))
    assert report['status'] == 'passed'
    assert used.spend_usd == pytest.approx(.20)  # two turns at the .10 reservation, never free


def test_running_out_of_budget_mid_smoke_is_incomplete_not_a_pass():
    report, _ = _smoke(App(), Telemetry([[], ['scheduling_inspect']]), spend_limit=.0005)
    assert report.get('incomplete_reason') == 'aggregate_budget_exhausted'
    assert report['status'] != 'passed'
