"""Opt-in real HTTP prefix execution with independent facts and a separate judge."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict

from application.use_cases.conversation_workflow_context import CANDIDATE_ASSIGNMENT_PREVIEW
from evals.live_conversations.facts import read_group, verify_claim
from evals.live_conversations.http_client import ApplicationConversation
from evals.live_conversations.expectations import (
    Bindings, TurnContext, apply_answers, evaluate, mentioned, verdict_from_checks, visible_lines,
    visible_text,
)
from evals.live_conversations.jev_judge import ask_yes_no, is_typesafe_judge, judge_turn_jev
from evals.live_conversations.judge import PAYLOAD_STRUCTURE_KEYS, judge_turn
from evals.live_conversations.protocol import IncompleteConversationRun, turn_verdict
from evals.live_conversations.reporting import tier1_fact_rows


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
    # A multiset comparison, not sorted(): rows whose `shift_id` is None on one
    # side and a string on the other are not orderable, and sorting them raised.
    return (Counter(map(_canonical_assignment, projected))
            == Counter(map(_canonical_assignment, candidate)))


def candidate_assignment_count(candidate):
    """The candidate's assignment count, and whether the assistant saw all of it.

    The result endpoint's candidate (`ScheduleVersionOut`) carries its complete
    assignment list and states the count only at `metrics.assignment_count`;
    `assignment_count`/`assignments_truncated` are the ASSISTANT's snapshot
    keys. Reading them here always gave None, so the judge counted 76 rows
    itself, got 50, and failed a correct reply (live-matrix-5-7-final3, B:8).
    The assistant is shown only a preview, so truncation is judged against it.
    """
    if candidate is None:
        return None, None
    if not isinstance(candidate, dict):
        raise IncompleteConversationRun('candidate_payload_malformed')
    rows = candidate.get('assignments')
    metrics = candidate.get('metrics')
    if (not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows)
            or not isinstance(metrics, dict)):
        raise IncompleteConversationRun('candidate_payload_malformed')
    stated = metrics.get('assignment_count')
    if type(stated) is not int or stated != len(rows):
        raise IncompleteConversationRun('candidate_assignment_count_mismatch')
    return len(rows), len(rows) > CANDIDATE_ASSIGNMENT_PREVIEW


def compact_reload_effect(timeline):
    """Retain proof of reload continuity without forwarding transcript content."""
    return {
        'has_more': timeline.get('has_more'),
        'visible_activities': [
            {key: item.get(key) for key in ('activity_id', 'activity_type')}
            for item in timeline.get('items', ())
        ],
    }


def reply_text(activity):
    """The reply's prose, casefolded: what `relevant_entities` matches names in."""
    return ' '.join(segment.get('text', '') for segment in
                    activity.get('response', {}).get('segments', ())).casefold()


def named_candidate_rows(activity, rows, workers_by_id, tasks_by_id):
    """Candidate rows whose worker or task the reply names, WITH their minutes.

    A truthful reply quoting an assignment's times needs those times in the
    judge's facts (live-suite-evidence B8), but only for the rows it names:
    every row cost ~20k chars on each Scenario B turn. The count and the
    truncation flag stay separate facts, so a "how many" claim is still checked.

    Matched against everything the judge sees of the reply (`visible_activity`),
    so a name only in a claim's arguments or a clarification still counts; and
    as a whole token, so `w1` does not pull in `w12`'s rows.
    """
    text = visible_text(visible_activity(activity))

    def named(record_id, by_id):
        return mentioned(record_id, text) or mentioned(by_id.get(record_id), text)

    return [
        {'record_id': row.get('record_id'), 'worker_id': row.get('worker_id'),
         'worker_name': workers_by_id.get(row.get('worker_id')),
         'task_id': row.get('task_id'), 'task_name': tasks_by_id.get(row.get('task_id')),
         'start_minute': row.get('start_minute'), 'end_minute': row.get('end_minute')}
        for row in rows
        if named(row.get('worker_id'), workers_by_id) or named(row.get('task_id'), tasks_by_id)
    ]


def compact_provenance(provenance):
    """The judge's view of an approval's provenance: the harness checks the full
    payload itself, and its items were ~156k chars on B:9 -- after the reply, so
    never something the reply is graded against."""
    provenance = provenance or {}
    items = provenance.get('items') or []
    promotions = [item for item in items if item.get('item_type') == 'baseline_promotion']
    return {'schedule_run_id': provenance.get('schedule_run_id'), 'item_count': len(items),
            'baseline_promotion_count': len(promotions),
            'promoted_after_version': promotions[0].get('after_version') if promotions else None}


def relevant_entities(activity, workers, tasks, assignments, demand=()):
    """Give the judge exact facts only for entities visible in this reply."""
    text = reply_text(activity)
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
    latest_count = (None, None)
    # Per-turn expectations: values bound from application state as they happen,
    # and each reply's visible text for a check that refers back to it.
    bindings = Bindings()
    reply_lines = {}
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
            bindings.turn = index
            if index == 1:
                bindings.capture_start(before, tasks, workers, demand)
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
                bindings.capture_approval_request(activity)
            bindings.capture_claims(activity, tasks)
            assignments = read_group(app, 'baseline-assignments')
            claims = [s for s in activity.get('response', {}).get('segments', []) if s['kind'] == 'claim']
            row['tier1_facts'] = tier1_fact_rows(activity)
            row['tier1'] = usage.pop('tier1', None) if isinstance(usage, dict) else None
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
                bindings.capture_draft(verified['persisted_draft'], workers_by_id, tasks_by_id)
            if turn.requires_persisted_draft and activity['activity_type'] != 'draft':
                failures.append('required_persisted_draft_missing')
            visible = visible_activity(activity)
            reply_lines[index] = visible_lines(visible)
            # Raw fact-tag syntax the planner can see is broken output on any
            # turn, whatever the turn asked (live run ad89854, B:2).
            if '<claim' in visible_text(visible) or '</claim' in visible_text(visible):
                failures.append('raw_claim_markup_shown')
            use_expectations = bool(turn.expect) and is_typesafe_judge(judge_model)
            if use_expectations:
                # Graded as of the reply: before this turn's scripted actions run.
                checks, questions, judge_state = evaluate(turn.expect, TurnContext(
                    activity=activity, visible=visible, draft=verified.get('persisted_draft'),
                    assignments=assignments, locks=locks, workers_by_id=workers_by_id,
                    tasks_by_id=tasks_by_id, reply_lines=reply_lines, turn=index, workers=workers,
                    candidate_rows=named_candidate_rows(
                        activity, ((latest_run or {}).get('candidate') or {}).get('assignments', ()),
                        workers_by_id, tasks_by_id),
                ), bindings, turn.user)
                # On the row now: an action below that aborts the turn must not
                # discard checks already graded against the reply.
                row['checks'] = checks
            for action in turn.actions_after:
                effect = {'action': action, 'id': row['id'] + ':' + action, 'source': 'application_command'}
                if action in {'run_optimization', 'run_and_cancel'}:
                    run = app.run_optimization()
                    if action == 'run_and_cancel':
                        run = app.cancel_run(run)
                    latest_run = app.wait_for_run(run['schedule_run_id'])
                    wanted = 'solver_cancelled' if action == 'run_and_cancel' else 'solver_completed'
                    if latest_run['run']['status'] != wanted:
                        failures.append('required_solver_outcome_missing')
                    # Checked as soon as the result is read, before any action or
                    # fact touches its rows. A payload the harness cannot trust is
                    # an infrastructure fault: keep what this turn already proved,
                    # then stop the report rather than score the model on it.
                    try:
                        latest_count = candidate_assignment_count(latest_run.get('candidate'))
                    except IncompleteConversationRun:
                        # Enough to diagnose the drift: the run and candidate ids.
                        effect['run'] = latest_run.get('run')
                        report['command_observations'].append(effect)
                        verified['effects_after_reply'].append(effect)
                        row.update(factual_failures=failures, verified=verified)
                        save(report)
                        raise
                    effect['run'] = latest_run['run']
                    effect['candidate_schedule_version_id'] = (latest_run.get('candidate') or {}).get('schedule_version_id')
                    bindings.capture_run(latest_run, latest_count[0])
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
                    bindings.capture_decision(pending_approval, approved=action == 'approve',
                                              baseline_now=now['baseline_schedule_version'],
                                              baseline_before=before['baseline_schedule_version'])
                    pending_approval = None
                elif action == 'reload':
                    effect['timeline'] = compact_reload_effect(app.timeline())
                elif action == 'reject_draft':
                    effect['proposal'] = app.reject_draft()
                else:
                    raise IncompleteConversationRun('unsupported_authored_action')
                report['command_observations'].append(effect)
                # The judge gets the compact provenance; the report keeps it whole.
                verified['effects_after_reply'].append(
                    {**effect, 'provenance': compact_provenance(effect['provenance'])}
                    if 'provenance' in effect else effect)
            if latest_run:
                verified['latest_run'] = latest_run['run']
                candidate = latest_run.get('candidate') or {}
                count, truncated = latest_count
                verified['candidate_solver_status'] = candidate.get('feasible_solver_status')
                # The reply-named candidate rows, WITH their minutes (see
                # `named_candidate_rows`). The assistant itself saw only a preview;
                # `candidate_assignments_truncated` says so.
                verified['candidate_assignments'] = named_candidate_rows(
                    activity, candidate.get('assignments', ()), workers_by_id, tasks_by_id)
                verified['candidate_assignment_count'] = count
                verified['candidate_assignments_truncated'] = truncated
            transcript.append({'id': row['id'], 'user': turn.user, 'assistant': visible})
            if use_expectations:
                judge_usage = None
                if questions:
                    try:
                        p_yes, judge_usage = ask_yes_no(api_key=judge_key, model=judge_model,
                                                        state=judge_state, questions=questions,
                                                        budget=budget)
                    except IncompleteConversationRun as exc:
                        row.update(factual_failures=failures, judgment=None, checks=checks,
                                   verified=verified, judge_unavailable_reason=str(exc),
                                   verdict='incomplete')
                        save(report)
                        continue
                    apply_answers(checks, p_yes)
                row.update(factual_failures=failures, judgment=None, checks=checks,
                           judge_usage=judge_usage, verified=verified,
                           verdict=verdict_from_checks(checks, failures))
                save(report)
                continue
            not_applicable = (frozenset({'clarification_refusal'})
                              if activity['activity_type'] == 'agent_response' else frozenset())
            obligation_id = row['id'] + ':obligation'
            known = known_citation_ids(transcript, verified, obligation_id)
            try:
                judge = judge_turn_jev if is_typesafe_judge(judge_model) else judge_turn
                judgment, judge_usage = judge(api_key=judge_key, model=judge_model,
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
