"""Opt-in real HTTP prefix execution with independent facts and a separate judge."""
from __future__ import annotations

from dataclasses import asdict

from evals.live_conversations.facts import read_group, verify_claim
from evals.live_conversations.http_client import ApplicationConversation
from evals.live_conversations.judge import judge_turn
from evals.live_conversations.protocol import IncompleteConversationRun, turn_verdict


_ASSIGNMENT_FIELDS = ('worker_id', 'task_id', 'shift_id', 'start_minute', 'end_minute')


def _canonical_assignment(row):
    return tuple(row.get(field) for field in _ASSIGNMENT_FIELDS)


def same_assignments(projected, candidate):
    """Compare scheduling substance across projection and candidate transports."""
    return sorted(map(_canonical_assignment, projected)) == sorted(map(_canonical_assignment, candidate))


def compact_reload_effect(timeline):
    """Retain proof of reload continuity without forwarding transcript content."""
    return {
        'has_more': timeline.get('has_more'),
        'visible_activities': [
            {key: item.get(key) for key in ('activity_id', 'activity_type')}
            for item in timeline.get('items', ())
        ],
    }


def relevant_entities(activity, workers, tasks, assignments):
    """Give the judge exact facts only for entities visible in this reply."""
    text = ' '.join(segment.get('text', '') for segment in
                    activity.get('response', {}).get('segments', ())).casefold()
    named_workers = []
    for worker in workers:
        if worker['name'].casefold() in text or worker['record_id'].casefold() in text:
            named_workers.append({
                'record_id': worker['record_id'], 'name': worker['name'],
                'qualified_task_ids': [row['task_id'] for row in worker.get('qualifications', ())],
            })
    named_tasks = []
    for task in tasks:
        if task['name'].casefold() in text or task['record_id'].casefold() in text:
            named_tasks.append({key: task.get(key) for key in
                                ('record_id', 'task_id', 'name', 'function')})
    workers_by_id = {row['record_id']: row['name'] for row in workers}
    tasks_by_id = {row['record_id']: row['name'] for row in tasks}
    named_assignments = []
    for assignment in assignments:
        worker_name = workers_by_id.get(assignment['worker_id'])
        task_name = tasks_by_id.get(assignment['task_id'])
        if ((worker_name and worker_name.casefold() in text)
                or (task_name and task_name.casefold() in text)):
            named_assignments.append({
                'record_id': assignment['record_id'], 'worker_id': assignment['worker_id'],
                'worker_name': worker_name, 'task_id': assignment['task_id'],
                'task_name': task_name,
            })
    return {'named_workers': named_workers, 'named_tasks': named_tasks,
            'named_assignments': named_assignments}


def visible_activity(activity):
    kind = activity['activity_type']
    if kind == 'agent_response':
        return [{'text': s['text']} if s['kind'] == 'prose' else
                {key: s.get(key) for key in ('metric', 'arguments', 'value', 'unit', 'verdict', 'result_id')}
                for s in activity['response']['segments']]
    if kind == 'clarification':
        return activity['clarification']
    if kind == 'terminal_outcome':
        return activity['outcome']
    return {key: activity.get(key) for key in ('activity_type', 'proposal_id',
        'proposal_version_id', 'approval_id', 'approval_state', 'consequence_summary')}


def execute_prefix(*, app: ApplicationConversation, case, endpoint, isolation_id,
                   telemetry, judge_key, judge_model, budget, save):
    """Caller must create a disposable fixture/stack before entering this seam."""
    budget.begin_execution()
    conversation = app.create()
    report = {'scenario': case.id, 'endpoint': endpoint, 'conversation_id': conversation['id'],
              'isolation_id': isolation_id, 'turns': [], 'tool_observations': [],
              'command_observations': [], 'status': 'incomplete'}
    transcript = []
    pending_approval = None
    latest_run = None
    try:
        workers = read_group(app, 'workers')
        tasks = read_group(app, 'work-areas-and-tasks')
        demand = None
        projection_path = '/api/v1/scenarios/' + app.fixture['scenario_id'] + '/projection'
        for index, turn in enumerate(case.turns[:endpoint], 1):
            budget.admit(reserve_usd=.05, tokens=150000)
            before = app._request('GET', projection_path)
            row = {'id': f'{isolation_id}:turn:{index}', 'user': turn.user,
                   'obligation': turn.obligation, 'verdict': 'incomplete'}
            report['turns'].append(row)
            save(report)
            accepted, executed = app.send(turn.user)
            row.update(agent_run_id=accepted['agent_run_id'], activity=executed['activity'],
                       agent_run_status=executed['agent_run_status'])
            save(report)
            usage, tools = telemetry.read_run(accepted['agent_run_id'])
            counters = usage['usage']
            budget.charge(requests=counters['requests'], tool_calls=len(tools),
                          tokens=counters['input_tokens'] + counters['output_tokens'],
                          cost_usd=usage['estimated_cost_usd'])
            row['usage'] = usage
            report['tool_observations'].extend(tools)
            failures = []
            if executed['agent_run_status'] not in {'agent_completed', 'approval_required'}:
                failures.append('unsuccessful_agent_turn')
            activity = executed['activity']
            if activity['activity_type'] == 'approval_request':
                pending_approval = activity
            assignments = read_group(app, 'baseline-assignments')
            claims = [s for s in activity.get('response', {}).get('segments', []) if s['kind'] == 'claim']
            for claim in claims:
                if claim['metric'].startswith('required_') and demand is None:
                    demand = read_group(app, 'demand')
                failures.extend(verify_claim(claim, workers=workers, assignments=assignments, demand=demand or ()))
            verified = {'id': row['id'] + ':facts', 'worker_count': len(workers),
                **relevant_entities(activity, workers, tasks, assignments),
                'baseline_before': before['baseline_schedule_version'],
                'baseline_assignment_count': len(assignments),
                'independent_claim_failures': failures.copy(), 'effects_after_reply': []}
            if activity['activity_type'] == 'draft':
                verified['persisted_draft'] = app.latest_draft()
            if turn.obligation.startswith('Persist') and activity['activity_type'] != 'draft':
                failures.append('required_persisted_draft_missing')
            for action in turn.actions_after:
                effect = {'action': action, 'id': row['id'] + ':' + action, 'source': 'application_command'}
                if action in {'run_optimization', 'run_and_cancel'}:
                    run = app.run_optimization()
                    if action == 'run_and_cancel':
                        run = app.cancel_run(run)
                    latest_run = app.wait_for_run(run['schedule_run_id'])
                    effect['run'] = latest_run['run']
                    effect['candidate_schedule_version_id'] = (latest_run.get('candidate') or {}).get('schedule_version_id')
                    wanted = 'solver_cancelled' if action == 'run_and_cancel' else 'solver_completed'
                    if latest_run['run']['status'] != wanted:
                        failures.append('required_solver_outcome_missing')
                elif action == 'verify_baseline_unchanged':
                    now = app._request('GET', projection_path)
                    if now['baseline_schedule_version'] != before['baseline_schedule_version']:
                        failures.append('baseline_changed_before_approval')
                    effect['baseline_schedule_version'] = now['baseline_schedule_version']
                elif action in {'approve', 'reject_approval'}:
                    if pending_approval is None:
                        raise IncompleteConversationRun('required_agent_approval_missing')
                    decision = app.decide(pending_approval['approval_id'],
                                          decision='approve' if action == 'approve' else 'reject')
                    effect['decision'] = decision
                    now = app._request('GET', projection_path)
                    expected = pending_approval['candidate_schedule_version_id'] if action == 'approve' else before['baseline_schedule_version']
                    if now['baseline_schedule_version'] != expected:
                        failures.append('incorrect_baseline_after_decision')
                    provenance = app._request('GET', '/api/v1/approvals/provenance?schedule_run_id=' + pending_approval['schedule_run_id'])
                    effect['provenance'] = provenance
                    if action == 'approve':
                        promotions = [p for p in provenance['items'] if p['item_type'] == 'baseline_promotion']
                        if len(promotions) != 1 or promotions[0]['after_version'] != expected:
                            failures.append('baseline_promotion_provenance_not_exactly_once')
                        after_assignments = read_group(app, 'baseline-assignments')
                        if latest_run is None or not same_assignments(
                                after_assignments, latest_run['candidate']['assignments']):
                            failures.append('promoted_assignments_do_not_match_candidate')
                    pending_approval = None
                elif action == 'reload':
                    effect['timeline'] = compact_reload_effect(app.timeline())
                elif action == 'reject_draft':
                    effect['proposal'] = app.reject_draft()
                else:
                    raise IncompleteConversationRun('unsupported_authored_action')
                report['command_observations'].append(effect)
                verified['effects_after_reply'].append(effect)
            if latest_run:
                verified['latest_run'] = latest_run['run']
                verified['candidate_solver_status'] = (latest_run.get('candidate') or {}).get('feasible_solver_status')
            transcript.append({'id': row['id'], 'user': turn.user, 'assistant': visible_activity(activity)})
            judgment, judge_usage = judge_turn(api_key=judge_key, model=judge_model,
                transcript=transcript, obligation=turn.obligation, verified=verified, budget=budget)
            known = {item['id'] for item in transcript} | {verified['id']} | {e['id'] for e in verified['effects_after_reply']}
            row.update(factual_failures=failures, judgment=judgment.model_dump(), judge_usage=judge_usage,
                       verified=verified, verdict=turn_verdict(factual_failures=failures,
                       judgment=judgment, known_ids=known))
            save(report)
        report['status'] = 'passed' if all(row['verdict'] == 'pass' for row in report['turns']) else 'failed'
    except IncompleteConversationRun as exc:
        report['incomplete_reason'] = str(exc)
    finally:
        report['budget'] = {key: value for key, value in asdict(budget).items() if key != 'started'}
        save(report)
    return report
