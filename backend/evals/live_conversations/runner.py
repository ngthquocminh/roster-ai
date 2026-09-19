"""Opt-in real HTTP prefix execution with independent facts and a separate judge."""
from __future__ import annotations

from dataclasses import asdict

from evals.live_conversations.facts import read_group, verify_claim
from evals.live_conversations.http_client import ApplicationConversation
from evals.live_conversations.judge import PAYLOAD_STRUCTURE_KEYS, judge_turn
from evals.live_conversations.protocol import IncompleteConversationRun, turn_verdict


_ASSIGNMENT_FIELDS = ('worker_id', 'task_id', 'shift_id', 'start_minute', 'end_minute')


def supplied_citation_ids(value):
    """Collect explicit IDs the judge actually received in sanitized input."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if (key == 'id' or key == 'result_id' or key.endswith('_id')) and isinstance(item, str):
                found.add(item)
            found.update(supplied_citation_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(supplied_citation_ids(item))
    return found


def known_citation_ids(transcript, verified, obligation_id):
    """Every ID the judge may legitimately cite: explicit IDs, the name of a
    supplied fact group itself for a scalar fact with no ID of its own (e.g.
    candidate_solver_status), the judge payload's own top-level wrapper keys
    (e.g. "current_obligation", the literal key the obligation is nested under),
    and the obligation's own ID."""
    return (supplied_citation_ids(transcript) | supplied_citation_ids(verified)
            | set(verified.keys()) | PAYLOAD_STRUCTURE_KEYS | {obligation_id})


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


def relevant_entities(activity, workers, tasks, assignments, demand=()):
    """Give the judge exact facts only for entities visible in this reply."""
    text = ' '.join(segment.get('text', '') for segment in
                    activity.get('response', {}).get('segments', ())).casefold()
    named_workers = []
    for worker in workers:
        if worker['name'].casefold() in text or worker['record_id'].casefold() in text:
            windows = worker.get('availability_windows', ())
            named_workers.append({
                'record_id': worker['record_id'], 'name': worker['name'],
                'employment_type': worker.get('employment_type'),
                'grade': worker.get('grade'), 'eba': worker.get('eba'),
                'contracted_hours': worker.get('contracted_hours'),
                'qualified_task_ids': [row['task_id'] for row in worker.get('qualifications', ())],
                'roster_window_count': sum(row.get('kind') == 'roster' for row in windows),
                'extra_availability_window_count': sum(
                    row.get('kind') == 'availability' for row in windows),
            })
    demand_families_by_task = {}
    for row in demand:
        demand_families_by_task.setdefault(row['task_id'], set()).add(row['family'])
    named_tasks = []
    for task in tasks:
        if task['name'].casefold() in text or task['record_id'].casefold() in text:
            entry = {key: task.get(key) for key in
                     ('record_id', 'task_id', 'name', 'function')}
            entry['demand_families'] = sorted(demand_families_by_task.get(task['task_id'], ()))
            named_tasks.append(entry)
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
        workers_by_id = {row['record_id']: row['name'] for row in workers}
        tasks = read_group(app, 'work-areas-and-tasks')
        tasks_by_id = {row['record_id']: row['name'] for row in tasks}
        demand = read_group(app, 'demand')
        locks = read_group(app, 'locks')
        constraints = read_group(app, 'constraints-and-objectives')
        projection_path = '/api/v1/scenarios/' + app.fixture['scenario_id'] + '/projection'
        for index, turn in enumerate(case.turns[:endpoint], 1):
            budget.admit(reserve_usd=.05, tokens=150000)
            before = app._request('GET', projection_path)
            row = {'id': f'turn-{index}', 'user': turn.user,
                   'obligation': turn.obligation, 'verdict': 'incomplete'}
            report['turns'].append(row)
            save(report)
            accepted, executed = app.send(turn.user)
            row.update(agent_run_id=accepted['agent_run_id'], activity=executed['activity'],
                       agent_run_status=executed['agent_run_status'])
            if accepted.get('execute_retried_after_404'):
                row['execute_retried_after_404'] = True
            save(report)
            usage, tools = telemetry.read_run(accepted['agent_run_id'])
            if usage.get('usage_unavailable'):
                # Unknown real cost: charge the full per-turn reservation so the
                # tracked total errs high, and keep scoring the conversation.
                budget.charge(requests=1, tool_calls=len(tools), tokens=0, cost_usd=.05)
            else:
                counters = usage['usage']
                budget.charge(requests=counters['requests'], tool_calls=len(tools),
                              tokens=counters['input_tokens'] + counters['output_tokens'],
                              cost_usd=usage['estimated_cost_usd'])
            row['usage'] = usage
            report['tool_observations'].extend(tools)
            failures = []
            if executed['agent_run_status'] not in turn.allowed_run_statuses:
                failures.append('unsuccessful_agent_turn')
            if usage.get('usage_unavailable') and 'unsuccessful_agent_turn' not in failures:
                failures.append('unsuccessful_agent_turn')
            activity = executed['activity']
            if activity['activity_type'] == 'approval_request':
                pending_approval = activity
            assignments = read_group(app, 'baseline-assignments')
            claims = [s for s in activity.get('response', {}).get('segments', []) if s['kind'] == 'claim']
            for claim in claims:
                failures.extend(verify_claim(claim, workers=workers, assignments=assignments, demand=demand))
            verified = {'id': row['id'] + ':facts', 'worker_count': len(workers),
                # Independently read so a reply about locks or constraints is
                # judgeable at all: without them the judge could only return
                # uncertain (live-suite-v2-C-x2, C7 rep2).
                'locks': locks, 'lock_count': len(locks),
                'constraints': constraints, 'constraint_count': len(constraints),
                **relevant_entities(activity, workers, tasks, assignments, demand),
                'baseline_before': before['baseline_schedule_version'],
                'baseline_assignment_count': len(assignments),
                'independent_claim_failures': failures.copy(), 'effects_after_reply': []}
            if activity['activity_type'] == 'draft':
                verified['persisted_draft'] = app.latest_draft()
            if turn.requires_persisted_draft and activity['activity_type'] != 'draft':
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
                        candidate_assignments = (latest_run or {}).get('candidate') or {}
                        if not candidate_assignments.get('assignments') or not same_assignments(
                                after_assignments, candidate_assignments['assignments']):
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
                candidate = latest_run.get('candidate') or {}
                verified['candidate_solver_status'] = candidate.get('feasible_solver_status')
                # The rows the assistant can actually see, WITH their minutes: the
                # judge scored a truthful reply 0 for "inventing" times that were
                # in the snapshot but absent from its facts (live-suite-evidence
                # B8).
                verified['candidate_assignments'] = [
                    {'record_id': row.get('record_id'), 'worker_id': row.get('worker_id'),
                     'worker_name': workers_by_id.get(row.get('worker_id')),
                     'task_id': row.get('task_id'),
                     'task_name': tasks_by_id.get(row.get('task_id')),
                     'start_minute': row.get('start_minute'), 'end_minute': row.get('end_minute')}
                    for row in candidate.get('assignments', ())
                ]
                verified['candidate_assignment_count'] = candidate.get('assignment_count')
                verified['candidate_assignments_truncated'] = candidate.get('assignments_truncated')
            transcript.append({'id': row['id'], 'user': turn.user, 'assistant': visible_activity(activity)})
            not_applicable = (frozenset({'clarification_refusal'})
                              if activity['activity_type'] == 'agent_response' else frozenset())
            obligation_id = row['id'] + ':obligation'
            known = known_citation_ids(transcript, verified, obligation_id)
            try:
                judgment, judge_usage = judge_turn(api_key=judge_key, model=judge_model,
                    transcript=transcript, obligation=turn.obligation, obligation_id=obligation_id,
                    verified=verified, budget=budget, not_applicable=not_applicable)
            except IncompleteConversationRun as exc:
                # A judge outage leaves THIS turn unjudged (AC6: not a pass), but
                # the remaining turns and scenarios still carry information.
                row.update(factual_failures=failures, judgment=None, verified=verified,
                           judge_unavailable_reason=str(exc), verdict='incomplete')
                save(report)
                continue
            row.update(factual_failures=failures, judgment=judgment.model_dump(), judge_usage=judge_usage,
                       verified=verified,
                       judge_unknown_citations=judgment.unknown_citations(known_ids=known),
                       verdict=turn_verdict(factual_failures=failures,
                       judgment=judgment, known_ids=known, not_applicable=not_applicable))
            save(report)
        report['status'] = 'passed' if all(row['verdict'] == 'pass' for row in report['turns']) else 'failed'
    except IncompleteConversationRun as exc:
        report['incomplete_reason'] = str(exc)
    finally:
        report['budget'] = {key: value for key, value in asdict(budget).items() if key != 'started'}
        save(report)
    return report
