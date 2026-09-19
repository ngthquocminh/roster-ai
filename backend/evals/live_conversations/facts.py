"""Independent arithmetic oracles over fresh, authenticated projection reads."""
from __future__ import annotations

import math

from evals.live_conversations.protocol import IncompleteConversationRun


def read_group(app, group, *, max_rows=10000):
    rows = []
    cursor = 0
    seen = set()
    while len(rows) <= max_rows:
        if cursor in seen:
            raise IncompleteConversationRun('projection_cursor_cycle')
        seen.add(cursor)
        page = app.projection(group, limit=200, cursor=cursor)
        if page['scenario_version_id'] != app.fixture['scenario_version_id']:
            raise IncompleteConversationRun('projection_version_mismatch')
        rows.extend(page['items'])
        if len(rows) > max_rows:
            break
        cursor = page['next_cursor']
        if cursor is None:
            if len(rows) != page['matching_count']:
                raise IncompleteConversationRun('projection_count_mismatch')
            return rows
    raise IncompleteConversationRun('projection_row_budget_exhausted')


def expected_metric(metric, arguments, *, workers=(), demand=(), assignments=()):
    task = arguments.get('task_id')
    family = arguments.get('family')
    if metric == 'worker_count':
        if any(arguments.get(key) is not None for key in ('task_id', 'family', 'start_minute', 'end_minute')):
            raise ValueError('scenario worker count is unscoped')
        return len(workers), 'workers'
    if not task:
        raise ValueError('task required')
    if metric in {'qualified_worker_count', 'staffed_minutes'} and family is not None:
        raise ValueError('family does not apply to workers or assignments')
    if metric == 'qualified_worker_count':
        if arguments.get('start_minute') is not None or arguments.get('end_minute') is not None:
            raise ValueError('qualification count has no time window')
        return sum(any(q['task_id'] == task for q in w['qualifications']) for w in workers), 'workers'
    start, end = arguments.get('start_minute'), arguments.get('end_minute')
    if type(start) is not int or type(end) is not int or end <= start:
        raise ValueError('valid time window required')
    def overlap(row):
        return max(0, min(end, row['end_minute']) - max(start, row['start_minute']))
    if metric == 'staffed_minutes':
        return sum(overlap(row) for row in assignments if row['task_id'] == task), 'minutes'
    if metric not in {'required_headcount_minutes', 'required_demand_volume'}:
        raise ValueError('unknown metric')
    matching = [r for r in demand if r['task_id'] == task and
                (family is None or r['family'] == family) and overlap(r)]
    wanted = 'volume' if metric == 'required_demand_volume' else 'headcount'
    selected = [r for r in matching if r['unit'] == wanted]
    if matching and not selected:
        raise ValueError('dimension mismatch')
    if wanted == 'headcount':
        return sum(r['amount'] * overlap(r) for r in selected), 'minutes'
    return sum(r['amount'] * overlap(r) / (r['end_minute'] - r['start_minute']) for r in selected), 'units'


def verify_claim(claim, **facts):
    if claim.get('verdict') != 'supported':
        return ['unsupported_claim']
    try:
        value, unit = expected_metric(claim['metric'], claim['arguments'], **facts)
    except (KeyError, TypeError, ValueError):
        return ['invalid_claim_dimensions']
    observed = claim.get('value')
    if type(observed) not in (int, float) or not math.isfinite(observed):
        return ['missing_claim_value']
    if unit != claim.get('unit') or not math.isclose(value, observed, rel_tol=1e-9, abs_tol=1e-9):
        return ['incorrect_claim_value_or_unit']
    return []
