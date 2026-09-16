"""Command-line orchestration for opt-in, paid live conversation evaluation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import time
from uuid import uuid4

from dotenv import dotenv_values

from evals.live_conversations.cases import load_scenarios
from evals.live_conversations.fixtures import prepare_initial_baseline
from evals.live_conversations.http_client import ApplicationConversation
from evals.live_conversations.protocol import ConversationBudget, IncompleteConversationRun
from evals.live_conversations.runner import execute_prefix
from evals.live_conversations.stack import ROOT, build_live_images, isolated_stack
from evals.live_conversations.telemetry import ContainerTelemetry
from evals.report import LiveSuiteBudgetV1


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def _arguments(argv=None):
    parser = argparse.ArgumentParser(description='Run paid, isolated Story 5.7 live prefixes.')
    parser.add_argument('--scenario', help='Run one authored scenario during development.')
    parser.add_argument('--endpoint', type=int, help='Run one authored endpoint during development.')
    parser.add_argument('--agent-model', help='Override only the application agent model for this run.')
    parser.add_argument('--reasoning-effort', choices=('none', 'low', 'medium', 'high'), default='low')
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--spend-limit-usd', type=float, default=7.0)
    parser.add_argument('--prior-spend-usd', type=float, default=.5,
                        help='Conservative amount already spent on story probes/browser runs.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--override-file', type=Path,
                        default=ROOT / '_bmad-output/test-artifacts/story-5-7.compose.override.yml')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _arguments(argv)
    if args.repetitions < 1 or args.repetitions > 3:
        raise SystemExit('--repetitions must be between 1 and 3')
    values = dotenv_values(ROOT / 'backend/.env')
    model = (args.agent_model or values.get('AGENT_RUNTIME_MODEL')
             or os.environ.get('AGENT_RUNTIME_MODEL'))
    key = values.get('AGENT_RUNTIME_API_KEY') or os.environ.get('AGENT_RUNTIME_API_KEY')
    judge_model = values.get('LIVE_CONVERSATION_JUDGE_MODEL') or os.environ.get('LIVE_CONVERSATION_JUDGE_MODEL')
    judge_key = values.get('LIVE_CONVERSATION_JUDGE_API_KEY') or key
    if not all(isinstance(value, str) and value.strip() for value in (model, key, judge_model, judge_key)):
        raise SystemExit('agent and separate judge model/key configuration is required')
    scenarios = load_scenarios()
    selected = [(case, endpoint) for case in scenarios for endpoint in case.prefixes
                if (args.scenario is None or case.id == args.scenario)
                and (args.endpoint is None or endpoint == args.endpoint)]
    if not selected:
        raise SystemExit('the requested authored prefix does not exist')
    if args.endpoint is not None and args.scenario is None:
        raise SystemExit('--endpoint requires --scenario')
    executions = len(selected) * args.repetitions
    authored_turns = sum(endpoint for _case, endpoint in selected) * args.repetitions
    budget = ConversationBudget(LiveSuiteBudgetV1(
        case_limit=executions, request_limit=max(100, authored_turns * 20),
        tool_call_limit=max(100, authored_turns * 20),
        token_limit=max(150_000, authored_turns * 175_000),
        elapsed_seconds_limit=max(1800, executions * 600), spend_usd_limit=args.spend_limit_usd,
    ), prior_spend_usd=args.prior_spend_usd)
    report = {'schema_version': '1-development', 'run_id': str(uuid4()),
              'started_unix': int(time()), 'model': model, 'judge_model': judge_model,
              'prefixes': [], 'incomplete_reason': None}
    save = lambda _prefix=None: _atomic_json(args.output, report)
    build_live_images(model=model, api_key=key, override_file=args.override_file,
                      reasoning_effort=args.reasoning_effort)
    try:
        for repetition in range(1, args.repetitions + 1):
            for case, endpoint in selected:
                prefix = {'scenario': case.id, 'endpoint': endpoint, 'repetition': repetition,
                          'status': 'incomplete', 'turns': []}
                report['prefixes'].append(prefix)
                save()
                with isolated_stack(model=model, api_key=key, override_file=args.override_file,
                                    reasoning_effort=args.reasoning_effort) as stack:
                    app = ApplicationConversation(stack['origin'])
                    try:
                        session = app.login()
                        prefix['fixture_setup'] = prepare_initial_baseline(
                            app, session=session, database_url=stack['database_url'])
                        actual = execute_prefix(
                            app=app, case=case, endpoint=endpoint,
                            isolation_id=stack['isolation_id'], telemetry=ContainerTelemetry(stack['container']),
                            judge_key=judge_key, judge_model=judge_model, budget=budget,
                            save=lambda current: (prefix.update(current), save()),
                        )
                        prefix.update(actual)
                    finally:
                        app.close()
                save()
    except IncompleteConversationRun as exc:
        report['incomplete_reason'] = str(exc)
        save()
        return 2
    finally:
        report['finished_unix'] = int(time())
        save()
    return 0 if all(prefix.get('status') == 'passed' for prefix in report['prefixes']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
