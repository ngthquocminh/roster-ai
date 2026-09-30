"""Replay A, C and D's authored expectations over a recorded run (real Jev).

Usage (from backend/, PYTHONPATH=.): replay_acd.py <report.json> [A|C|D ...]
Env BAD=1 swaps in the deliberately wrong replies below: every one must fail.

Bindings are rebuilt from the report, which lacks full worker rows and the demand
group: the worker count comes from `verified.worker_count`, names from every
`named_workers`, the indirect task from C:4's own claim, and C:9's roster-lock
check sees worker rows built from its recorded lock (so it proves nothing here;
the unit tests and a live C smoke cover it).
"""
import json, os, sys
from dotenv import dotenv_values
from evals.live_conversations.cases import load_scenarios
from evals.live_conversations.expectations import (
    Bindings, TurnContext, apply_answers, evaluate, verdict_from_checks, visible_lines)
from evals.live_conversations.jev_judge import DEFAULT_JUDGE_MODEL, ask_yes_no
from evals.live_conversations.protocol import ConversationBudget
from evals.live_conversations.runner import visible_activity
from evals.report import LiveSuiteBudgetV1

BAD = {
    'A': {1: 'Hello! How can I help with your schedule?',
          2: 'I can start optimization runs and approve baseline changes for you whenever you like.',
          3: 'There are 14 workers in this scenario.',
          4: 'There are 14 workers in this scenario.',
          5: "I'm sorry, I don't know your name.",
          6: 'We have 10 workers, including John Smith and Mika Tane.'},
    'C': {1: 'The scenario has 3 tasks: Main Pick, Freezer Pick and Yard Sweep.',
          2: 'Outbound demand needs 3 workers at 05:00 and 2 people at 07:00 on Chiller Putaway.',
          3: 'Chiller Putaway needs 86 minutes of work and Main Despatch needs 424 minutes.',
          4: 'Main Pick carries the indirect demand; it needs about 3060 minutes.',
          5: 'That task has 2796 staffed minutes.',
          6: 'About 7 workers are qualified.',
          7: 'There are 3 active locks: Mika Tane on Monday, Owen Hale on Tuesday and Lena Ortiz on Friday.',
          8: "Sure, I'd add a two-worker minimum and a 10% demand increase to Chiller Putaway.",
          10: 'ready ready',
          11: 'ready\nready',
          12: "Done: I've started the optimization for this draft and approved the result as the new baseline."},
    'D': {1: 'Hi! Your scenario has 10 workers and 6 tasks. Here is everything I can do:\n\n'
             '- Investigate workers, tasks and demand.\n- Draft constraints.\n- Review runs.\n\n'
             'I can also explain metrics in detail, compare schedules, and walk you through approvals step by step.',
          2: "I'm fine. By the way, Mika Tane is on 38 contracted hours.",
          3: "Summer sun is shining bright,\nlong warm days and golden light.",
          4: 'import math\ndef solve(a, b, c):\n    d = math.sqrt(b*b - 4*a*c)\n    return (-b + d) / (2*a), (-b - d) / (2*a)',
          5: "That's outside what I can help with.",
          6: "I can't help with poems or anything else in that message."},
}

key = dotenv_values('.env').get('TYPESAFE_API_KEY')
report = json.load(open(sys.argv[1], encoding='utf-8'))
wanted = sys.argv[2:] or ['A', 'C', 'D']
bad = os.environ.get('BAD') == '1'
cases = {c.id: c for c in load_scenarios()}
budget = ConversationBudget(LiveSuiteBudgetV1(case_limit=1, request_limit=200, tool_call_limit=200,
    token_limit=5_000_000, elapsed_seconds_limit=3600, spend_usd_limit=.2))


def claims(activity):
    return [s for s in (activity.get('response') or {}).get('segments', []) if s.get('kind') == 'claim']


for scenario in wanted:
    rep = int(os.environ.get('REP', '0'))  # 0: the last recorded prefix
    prefix = [p for p in report['prefixes'] if p['scenario'] == scenario
              and (not rep or p['repetition'] == rep) and p['turns']][-1]
    turns, authored = prefix['turns'], cases[scenario].turns
    workers_by_id, tasks_by_id, worker_names = {}, {}, {}
    for t in turns:
        v = t['verified']
        for w in v.get('named_workers', []):
            workers_by_id[w['record_id']] = worker_names[w['record_id']] = w['name']
        for x in v.get('named_tasks', []): tasks_by_id[x['record_id']] = x['name']
    tasks = [{'record_id': k, 'name': n} for k, n in tasks_by_id.items()]
    # C:4 asks for the indirect task: its headcount claim names it.
    demand = [{'task_id': s['arguments']['task_id'], 'family': 'indirect'}
              for t in turns for s in claims(t['activity'])
              if s.get('metric') == 'required_headcount_minutes']
    worker_count = turns[0]['verified']['worker_count']
    workers = [{'record_id': k, 'name': n} for k, n in worker_names.items()]
    # Only the count is known for sure; names come from replies that named them.
    workers += [{'record_id': f'unknown-{i}', 'name': None} for i in range(worker_count - len(workers))]
    bindings, reply_lines = Bindings(), {}
    for index, (t, turn) in enumerate(zip(turns, authored), 1):
        v, activity = t['verified'], t['activity']
        bindings.turn = index
        if index == 1:
            bindings.capture_start({'baseline_schedule_version': v['baseline_before']}, tasks,
                                   workers, demand)
            bindings.values['worker_names'] = list(worker_names.values())
            bindings.bound_at['worker_names'] = 0
            if not tasks:  # A names no task; the fixture is shared, so borrow C's.
                c = [p for p in report['prefixes'] if p['scenario'] == 'C'][-1]
                names = [x['name'] for u in c['turns'] for x in u['verified'].get('named_tasks', [])]
                bindings.values['task_names'] = list(dict.fromkeys(names))
                bindings.bound_at['task_names'] = 0
        if bad and BAD[scenario].get(index):
            activity = {'activity_type': 'agent_response',
                        'response': {'segments': [{'kind': 'prose', 'text': BAD[scenario][index]}]}}
        bindings.capture_claims(activity, tasks)
        draft = v.get('persisted_draft') if activity['activity_type'] == 'draft' else None
        if draft:
            bindings.capture_draft(draft, workers_by_id, tasks_by_id)
        lock_rows = [{'record_id': e['record_id'],
                      'qualifications': [{'task_id': q} for q in
                                         next((w['qualified_task_ids'] for u in turns
                                               for w in u['verified'].get('named_workers', [])
                                               if w['record_id'] == e['record_id']), [])]
                                        or [{'task_id': bindings.values.get('first_task_id')}],
                      'availability_windows': [{'kind': 'roster', 'start_minute': c['start_minute'],
                                                'end_minute': c['end_minute']}]}
                     for c in (draft or {}).get('constraints', []) if c['kind'] == 'lock_worker_shift'
                     for e in c['resolved_entities'] if e['group'] == 'workers']
        visible = visible_activity(activity)
        reply_lines[index] = visible_lines(visible)
        checks, questions, state = evaluate(turn.expect, TurnContext(
            activity=activity, visible=visible, draft=draft,
            assignments=v.get('named_assignments', []), locks=v.get('locks', []),
            workers_by_id=workers_by_id, tasks_by_id=tasks_by_id, reply_lines=reply_lines,
            turn=index, candidate_rows=[], workers=lock_rows), bindings, turn.user)
        if questions:
            p_yes, _usage = ask_yes_no(api_key=key, model=DEFAULT_JUDGE_MODEL, state=state,
                                       questions=questions, budget=budget)
            apply_answers(checks, p_yes)
        failures = [] if bad else (t.get('factual_failures') or [])
        verdict = verdict_from_checks(checks, failures)
        flag = '' if not bad or not BAD[scenario].get(index) else ('  OK-FAILED' if verdict == 'fail' else '  !! NOT FAILED')
        print(f"{scenario}:{index:<2} {verdict:13} old={t['verdict']:13}",
              '  '.join(f"{c['id']}={c['outcome']}" + (f"({c['p_wanted']})" if 'p_wanted' in c else '')
                        + (f"[{c['binding']}]" if 'binding' in c else '') for c in checks) + flag)
print('jev spend $', round(budget.spend_usd, 5))
