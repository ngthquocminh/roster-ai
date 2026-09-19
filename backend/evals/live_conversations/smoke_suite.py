"""CLI for the paid live two-turn capability-routing gate."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

from evals.live_conversations.fixtures import prepare_candidate, prepare_initial_baseline
from evals.live_conversations.facts import read_group
from evals.live_conversations.http_client import ApplicationConversation
from evals.live_conversations.protocol import ConversationBudget, IncompleteConversationRun
from evals.live_conversations.smoke_cases import CONVERSATION_TOOL_SMOKES
from evals.live_conversations.smoke_runner import execute_conversation_smoke
from evals.live_conversations.stack import ROOT, build_live_images, isolated_stack
from evals.live_conversations.telemetry import ContainerTelemetry
from evals.report import LiveSuiteBudgetV1


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def _args(argv=None):
    parser = argparse.ArgumentParser(description='Run Story 5.7 live capability smoke cases.')
    parser.add_argument('--case', choices=[case.id for case in CONVERSATION_TOOL_SMOKES])
    parser.add_argument('--agent-model')
    parser.add_argument('--reasoning-effort', choices=('none', 'low', 'medium', 'high'), default='low')
    parser.add_argument('--spend-limit-usd', type=float, default=10)
    parser.add_argument('--prior-spend-usd', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--override-file', type=Path,
                        default=ROOT / '_bmad-output/test-artifacts/story-5-7.compose.override.yml')
    return parser.parse_args(argv)


def main(argv=None):
    args = _args(argv)
    values = dotenv_values(ROOT / 'backend/.env')
    model = args.agent_model or values.get('AGENT_RUNTIME_MODEL')
    key = values.get('AGENT_RUNTIME_API_KEY')
    if not model or not key:
        raise SystemExit('configured OpenRouter agent model and key are required')
    cases = [case for case in CONVERSATION_TOOL_SMOKES if args.case is None or case.id == args.case]
    budget = ConversationBudget(LiveSuiteBudgetV1(
        case_limit=len(cases), request_limit=max(40, len(cases) * 30),
        tool_call_limit=max(20, len(cases) * 10), token_limit=max(300000, len(cases) * 300000),
        elapsed_seconds_limit=max(1200, len(cases) * 600), spend_usd_limit=args.spend_limit_usd),
        prior_spend_usd=args.prior_spend_usd)
    report = {'schema_version': '1-development', 'run_id': str(uuid4()),
              'agent_model': model, 'cases': [], 'status': 'incomplete'}
    save = lambda: _write(args.output, report)
    build_live_images(model=model, api_key=key, override_file=args.override_file,
        reasoning_effort=args.reasoning_effort, demonstration_enabled=True)
    try:
        for case in cases:
            enabled = case.precondition == 'demonstration_enabled'
            with isolated_stack(model=model, api_key=key, override_file=args.override_file,
                    reasoning_effort=args.reasoning_effort, demonstration_enabled=enabled) as stack:
                app = ApplicationConversation(stack['origin'])
                try:
                    session = app.login()
                    fixture_setup = None
                    if case.precondition in {'baseline', 'candidate'}:
                        fixture_setup = prepare_initial_baseline(
                            app, session=session, database_url=stack['database_url'])
                    resolved_case = case
                    if case.id == 'draft-max-hours':
                        assignments = read_group(app, 'baseline-assignments')
                        workers = {row['record_id']: row['name'] for row in read_group(app, 'workers')}
                        if not assignments or assignments[0]['worker_id'] not in workers:
                            raise IncompleteConversationRun('draft_smoke_worker_unavailable')
                        resolved_case = replace(case, second_turn=(
                            f"Create a draft capping {workers[assignments[0]['worker_id']]} at 40 hours."))
                    holder = {'case': case.id, 'status': 'incomplete', 'fixture_setup': fixture_setup}
                    report['cases'].append(holder)
                    save()

                    def before_second(conversation):
                        if case.precondition != 'candidate':
                            return {'kind': case.precondition}
                        return prepare_candidate(app, session=session, database_url=stack['database_url'],
                                                 conversation_id=conversation['id'])

                    actual = execute_conversation_smoke(
                        app=app, case=resolved_case, telemetry=ContainerTelemetry(stack['container']),
                        budget=budget, before_second=before_second, save=lambda current: (
                            holder.update(current), save()))
                    holder.update(actual)
                finally:
                    app.close()
            save()
        report['status'] = 'passed' if all(row.get('status') == 'passed' for row in report['cases']) else 'failed'
    except IncompleteConversationRun as exc:
        report['incomplete_reason'] = str(exc)
    finally:
        save()
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
