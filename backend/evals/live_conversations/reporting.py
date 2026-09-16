"""Story evidence feeds the existing readiness vocabulary, never a Gate B aggregator."""
from __future__ import annotations

from datetime import datetime, timezone

from evals.live_conversations.cases import load_scenarios, prefix_executions
from evals.live_conversations.inventory import require_complete_coverage
from evals.report import _readiness_verdict


def summarize_runs(runs, *, coverage, observation_ids, version_bindings, browser):
    expected = {(case.id, endpoint): turns for case, endpoint, turns in prefix_executions(load_scenarios())}
    streak = 0
    summaries = []
    seen_runs = set()
    conversations = set()
    isolation_ids = set()
    for run in runs:
        prefixes = run.get('prefixes', [])
        keys = [(prefix.get('scenario'), prefix.get('endpoint')) for prefix in prefixes]
        complete = len(keys) == len(set(keys)) and set(keys) == set(expected)
        passed = complete and run.get('version_bindings') == version_bindings
        if not run.get('run_id') or run['run_id'] in seen_runs:
            passed = False
        seen_runs.add(run.get('run_id'))
        turns_executed = 0
        for prefix in prefixes:
            key = (prefix.get('scenario'), prefix.get('endpoint'))
            turns = prefix.get('turns', [])
            turns_executed += len(turns)
            authored = expected.get(key, ())
            if not authored or [t.get('user') for t in turns] != [t.user for t in authored]:
                passed = False
                complete = False
            conversation_id = prefix.get('conversation_id')
            isolation_id = prefix.get('isolation_id')
            if not conversation_id or conversation_id in conversations or not isolation_id or isolation_id in isolation_ids:
                passed = False
            conversations.add(conversation_id)
            isolation_ids.add(isolation_id)
            if prefix.get('status') != 'passed' or any(turn.get('verdict') != 'pass' for turn in turns):
                passed = False
        if run.get('incomplete_reason'):
            complete = False
            passed = False
        streak = streak + 1 if passed else 0
        summaries.append({'run_id': run.get('run_id'), 'complete': complete,
                          'passed': passed, 'executed_user_turns': turns_executed})
    reasons = []
    try:
        require_complete_coverage(coverage, observation_ids=observation_ids)
    except ValueError:
        reasons.append('tool_operation_coverage_incomplete_or_stale')
    if any(row.get('state') == 'gap' for row in coverage.get('tool_coverage', [])):
        reasons.append('blocking_tool_implementation_gap')
    if streak < 3:
        reasons.append('three_consecutive_complete_passes_missing')
    if not version_bindings or version_bindings.get('code', {}).get('working_tree_dirty', True):
        reasons.append('clean_version_binding_missing')
    if browser.get('status') != 'passed' or browser.get('version_bindings') != version_bindings:
        reasons.append('current_browser_evidence_missing_or_failed')
    eligible = not reasons
    return {
        'schema_version': '1', 'version_bindings': version_bindings,
        'live_conversation_journeys': 'passed' if eligible else 'blocked',
        'readiness': _readiness_verdict(eligible, None if eligible else reasons[0], None,
                                        now=datetime.now(timezone.utc)),
        'blocking_reasons': reasons, 'runs': summaries, 'consecutive_passes': streak,
        'required_prefixes_per_run': len(expected),
        'required_user_turns_per_run': sum(len(turns) for turns in expected.values()),
    }
