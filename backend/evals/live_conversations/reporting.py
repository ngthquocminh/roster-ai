"""Story evidence feeds the existing readiness vocabulary, never a Gate B aggregator.

Acceptance (right-sized AC7, sprint-change-proposal-2026-09-17):
- at least one clean passing execution of every scenario on the bound version;
- at least three complete repetitions of the full set, reported as per-turn pass
  rates;
- a false claim, wrong fact, or missing/unauthorized effect in ANY counted
  execution blocks, with no exception;
- a turn that fails without such a failure (model reliability or judge
  semantics) blocks unless the owner explicitly accepted it as a finding.
"""
from __future__ import annotations

from datetime import datetime, timezone

from evals.live_conversations.cases import load_scenarios, prefix_executions
from evals.live_conversations.inventory import require_complete_coverage
from evals.report import _readiness_verdict

REQUIRED_REPETITIONS = 3
# Recorded when the agent run itself did not reach an allowed status. It is a
# reliability outcome (lesson 18's zero-cost transport failures land here), not a
# claim the assistant made, so it cannot be classed as a false claim.
RELIABILITY_FAILURES = frozenset({'unsuccessful_agent_turn'})
#: A claim the gate REFUSED to render (the planner sees "Claim unavailable", not
#: a number). Blocking unless the owner accepts that exact turn explicitly;
#: a wrong rendered value can never be accepted.
ACCEPTABLE_CLAIM_FAILURES = frozenset({'unsupported_claim'})


def summarize_runs(runs, *, coverage, observation_ids, version_bindings, accepted_findings=()):
    expected = {case.id: turns for case, _endpoint, turns in prefix_executions(load_scenarios())}
    accepted = {(scenario, int(turn)) for scenario, turn in accepted_findings}
    summaries = []
    seen_runs, conversations, isolation_ids = set(), set(), set()
    complete_runs = 0
    clean_scenarios = set()
    pass_counts = {}
    false_claims = []
    unaccepted_failures = set()
    for run in runs:
        executions = run.get('prefixes', [])
        scenario_ids = [execution.get('scenario') for execution in executions]
        complete = (len(scenario_ids) == len(set(scenario_ids)) and set(scenario_ids) == set(expected)
                    and not run.get('incomplete_reason')
                    # The suite records the code binding it measured; the
                    # evidence carries the full NFR27 set. Compare the one they
                    # share, or every run looks incomplete.
                    and run.get('code') == (version_bindings or {}).get('code')
                    and bool(run.get('run_id')) and run.get('run_id') not in seen_runs)
        seen_runs.add(run.get('run_id'))
        turns_executed = 0
        for execution in executions:
            authored = expected.get(execution.get('scenario'), ())
            turns = execution.get('turns', [])
            turns_executed += len(turns)
            if not authored or [t.get('user') for t in turns] != [t.user for t in authored]:
                complete = False
            conversation_id = execution.get('conversation_id')
            isolation_id = execution.get('isolation_id')
            if (not conversation_id or conversation_id in conversations
                    or not isolation_id or isolation_id in isolation_ids):
                complete = False
            conversations.add(conversation_id)
            isolation_ids.add(isolation_id)
        if complete:
            complete_runs += 1
            for execution in executions:
                scenario = execution['scenario']
                turns = execution['turns']
                if execution.get('status') == 'passed' and all(t.get('verdict') == 'pass' for t in turns):
                    clean_scenarios.add(scenario)
                for index, turn in enumerate(turns, 1):
                    key = f'{scenario}:{index}'
                    passes, total = pass_counts.get(key, (0, 0))
                    passed = turn.get('verdict') == 'pass'
                    pass_counts[key] = (passes + passed, total + 1)
                    claims = set(turn.get('factual_failures') or ()) - RELIABILITY_FAILURES
                    # A claim whose grounding failed shows the planner "Claim
                    # unavailable", never a wrong number: the gate refused to
                    # render it. That is inspectable and may be accepted
                    # explicitly, exactly like a reliability failure. Everything
                    # else -- a wrong value, unit, entity or version, a missing
                    # required effect, an unauthorized one, or a false success
                    # claim -- can never be accepted and always blocks.
                    unacceptable = claims - ACCEPTABLE_CLAIM_FAILURES
                    if unacceptable or (claims and (scenario, index) not in accepted):
                        false_claims.append({'run_id': run['run_id'], 'turn': key,
                                             'failures': sorted(claims)})
                    elif not passed and (scenario, index) not in accepted:
                        unaccepted_failures.add(key)
        summaries.append({'run_id': run.get('run_id'), 'complete': complete,
                          'executed_user_turns': turns_executed})
    reasons = []
    try:
        require_complete_coverage(coverage, observation_ids=observation_ids)
    except ValueError:
        reasons.append('tool_operation_coverage_incomplete_or_stale')
    if any(row.get('state') == 'gap' for row in coverage.get('tool_coverage', [])):
        reasons.append('blocking_tool_implementation_gap')
    if false_claims:
        reasons.append('false_claim_or_effect_failure')
    if clean_scenarios != set(expected):
        reasons.append('clean_run_missing_for_scenario')
    if complete_runs < REQUIRED_REPETITIONS:
        reasons.append('three_complete_repetitions_missing')
    if unaccepted_failures:
        reasons.append('unaccepted_turn_failure')
    if not version_bindings or version_bindings.get('code', {}).get('working_tree_dirty', True):
        reasons.append('clean_version_binding_missing')
    eligible = not reasons
    return {
        'schema_version': '2', 'version_bindings': version_bindings,
        'live_conversation_journeys': 'passed' if eligible else 'blocked',
        'readiness': _readiness_verdict(eligible, None if eligible else reasons[0], None,
                                        now=datetime.now(timezone.utc)),
        'blocking_reasons': reasons, 'runs': summaries,
        'complete_repetitions': complete_runs,
        'clean_scenarios': sorted(clean_scenarios),
        'turn_pass_rates': {key: {'passed': p, 'executed': n} for key, (p, n) in sorted(pass_counts.items())},
        'false_claims': false_claims,
        'unaccepted_turn_failures': sorted(unaccepted_failures),
        'accepted_findings': sorted(f'{s}:{t}' for s, t in accepted),
        'required_scenarios_per_run': len(expected),
        'required_user_turns_per_run': sum(len(turns) for turns in expected.values()),
    }
