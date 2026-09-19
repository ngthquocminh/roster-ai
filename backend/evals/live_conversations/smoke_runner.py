"""Real two-turn routing checks; semantic matrix execution depends on these."""
from dataclasses import asdict

from evals.live_conversations.protocol import IncompleteConversationRun


def execute_conversation_smoke(*, app, case, telemetry, budget, before_second=None, save):
    budget.begin_execution()
    conversation = app.create()
    report = {'case': asdict(case), 'conversation_id': conversation['id'],
              'turns': [], 'status': 'incomplete'}
    try:
        for number, user in enumerate((case.first_turn, case.second_turn), 1):
            if number == 2 and before_second is not None:
                report['precondition'] = before_second(conversation)
                save(report)
            budget.admit(reserve_usd=.10, tokens=150000)
            row = {'turn': number, 'user': user, 'status': 'incomplete'}
            report['turns'].append(row)
            save(report)
            accepted, executed = app.send(user)
            row.update(agent_run_id=accepted['agent_run_id'],
                       agent_run_status=executed['agent_run_status'],
                       activity_type=executed['activity']['activity_type'])
            usage, tools = telemetry.read_run(accepted['agent_run_id'])
            if usage.get('usage_unavailable'):
                # Unknown real cost: charge the full per-turn reservation so the
                # tracked total errs high, and keep scoring the smoke turn.
                budget.charge(requests=1, tool_calls=len(tools), tokens=0, cost_usd=.10)
            else:
                counters = usage['usage']
                budget.charge(requests=counters['requests'], tool_calls=len(tools),
                              tokens=counters['input_tokens'] + counters['output_tokens'],
                              cost_usd=usage['estimated_cost_usd'])
            names = [tool['labels']['capability_name'] for tool in tools]
            # Keep only the owned closed labels. This makes a failed routing
            # smoke diagnosable without admitting arguments, results, prompts,
            # or provider payloads into the evidence artifact.
            tool_outcomes = [
                {key: tool['labels'][key] for key in ('capability_name', 'failure_reason')
                 if key in tool['labels']}
                for tool in tools
            ]
            row.update(tool_calls=names, tool_outcomes=tool_outcomes, usage=usage)
            if number == 1:
                row['status'] = 'passed' if (executed['agent_run_status'] == 'agent_completed'
                                             and not names) else 'failed'
            else:
                allowed_status = ('approval_required' if case.expected_activity == 'approval_request'
                                  else 'agent_completed')
                row['status'] = 'passed' if (
                    executed['agent_run_status'] == allowed_status
                    and executed['activity']['activity_type'] == case.expected_activity
                    and names == [case.capability]) else 'failed'
            save(report)
        report['status'] = ('passed' if all(row['status'] == 'passed' for row in report['turns'])
                            else 'failed')
    except IncompleteConversationRun as exc:
        report['incomplete_reason'] = str(exc)
    finally:
        report['budget'] = {key: value for key, value in asdict(budget).items() if key != 'started'}
        save(report)
    return report
