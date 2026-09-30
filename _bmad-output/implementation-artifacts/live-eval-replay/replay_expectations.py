"""Replay B's authored expectations over the recorded smoke replies (real Jev)."""
import json, sys
from dotenv import dotenv_values
from evals.live_conversations.cases import load_scenarios
from evals.live_conversations.expectations import (
    Bindings, TurnContext, apply_answers, evaluate, verdict_from_checks, visible_lines)
from evals.live_conversations.jev_judge import DEFAULT_JUDGE_MODEL, ask_yes_no
from evals.live_conversations.protocol import ConversationBudget
from evals.live_conversations.runner import visible_activity
from evals.report import LiveSuiteBudgetV1

key = dotenv_values('.env').get('TYPESAFE_API_KEY')
report = json.load(open(sys.argv[1], encoding='utf-8'))
import os
_rep = int(os.environ.get('REP', '0'))  # 0: the last B prefix
turns = [p for p in report['prefixes'] if p.get('scenario', 'B') == 'B'
         and (not _rep or p.get('repetition') == _rep) and p['turns']][-1]['turns']
B = next(c for c in load_scenarios() if c.id == 'B')
budget = ConversationBudget(LiveSuiteBudgetV1(case_limit=1, request_limit=50, tool_call_limit=50,
    token_limit=2_000_000, elapsed_seconds_limit=1800, spend_usd_limit=.2))
workers_by_id, tasks_by_id = {}, {}
for t in turns:
    v = t['verified']
    for w in v.get('named_workers', []): workers_by_id[w['record_id']] = w['name']
    for x in v.get('named_tasks', []): tasks_by_id[x['record_id']] = x['name']
    for a in v.get('named_assignments', []):
        workers_by_id[a['worker_id']] = a['worker_name']; tasks_by_id[a['task_id']] = a['task_name']
tasks = [{'name': n} for n in tasks_by_id.values()]
bindings, reply_lines = Bindings(), {}
for index, (t, authored) in enumerate(zip(turns, B.turns), 1):
    v, activity = t['verified'], t['activity']
    bindings.turn = index
    if index == 1:
        bindings.capture_start({'baseline_schedule_version': v['baseline_before']}, tasks)
    if activity['activity_type'] == 'approval_request':
        bindings.capture_approval_request(activity)
    draft = v.get('persisted_draft')
    if activity['activity_type'] == 'draft':
        bindings.capture_draft(draft, workers_by_id, tasks_by_id)
    visible = visible_activity(activity)
    reply_lines[index] = visible_lines(visible)
    checks, questions, state = evaluate(authored.expect, TurnContext(
        activity=activity, visible=visible, draft=draft,
        assignments=v.get('named_assignments', []), locks=v.get('locks', []),
        workers_by_id=workers_by_id, tasks_by_id=tasks_by_id, reply_lines=reply_lines, turn=index,
        candidate_rows=v.get('candidate_assignments', [])), bindings, authored.user)
    if questions:
        p_yes, _usage = ask_yes_no(api_key=key, model=DEFAULT_JUDGE_MODEL, state=state,
                                   questions=questions, budget=budget)
        apply_answers(checks, p_yes)
    verdict = verdict_from_checks(checks, t.get('factual_failures') or [])
    print(f"B:{index:<2} {verdict:13} old-Jev={t['verdict']:13}",
          '  '.join(f"{c['id']}={c['outcome']}" + (f"({c['p_wanted']})" if 'p_wanted' in c else '')
                    + (f"[{c['binding']}]" if 'binding' in c else '') for c in checks))
    for effect in v.get('effects_after_reply', []):
        if effect['action'] == 'run_optimization':
            bindings.capture_run({'run': effect['run'], 'candidate': {
                'schedule_version_id': effect['candidate_schedule_version_id'],
                'feasible_solver_status': turns[index]['verified']['candidate_solver_status']}},
                turns[index]['verified']['candidate_assignment_count'])
        if effect['action'] == 'approve':
            bindings.capture_decision(effect['decision'], approved=True,
                                      baseline_now=turns[index]['verified']['baseline_before'],
                                      baseline_before=v['baseline_before'])
print('jev spend $', round(budget.spend_usd, 5))
