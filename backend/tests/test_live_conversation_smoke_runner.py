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
