"""Version-bound Story 5.7 evidence from recorded live runs.

Reads finished suite reports (never re-runs anything), derives tool/operation
coverage from what those runs actually observed, and writes one report whose
`live_conversation_journeys` verdict a later Gate B assessment reads.

Coverage sources, each recorded distinctly so a weaker one cannot pass as a
stronger one:

* `capability`  -- the capability was invoked in a live turn (telemetry record).
* `effect`      -- a live, independently read application effect proves the
                   exact operation (a claim's metric/family, a persisted draft's
                   constraint kind).
* `deterministic` -- the operation cannot be addressed by a planner turn (query
                   keys, paging/invalid-query paths, manifest error codes, the
                   compute-risk run tool) and is proved by the offline suite.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.live_conversations.inventory import capability_inventory
from evals.live_conversations.reporting import summarize_runs
from evals.live_conversations.stack import ROOT

#: Named, checkable proof for every chat-reachable operation no authored turn can
#: legitimately exercise. Each entry says WHY a planner turn cannot reach it and
#: where it is proved instead; `require_complete_coverage` refuses a row with no
#: reason, and `missing_declarations` below refuses an operation with no entry.
UNREACHABLE_IN_CHAT = {
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.group=demand':
        'resolve_constraints rejects every draft group except workers and '
        'work-areas-and-tasks; proved by tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.group=locks':
        'resolve_constraints rejects every draft group except workers and '
        'work-areas-and-tasks; proved by tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.group='
    'constraints-and-objectives':
        'resolve_constraints rejects every draft group except workers and '
        'work-areas-and-tasks; proved by tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.group='
    'baseline-assignments':
        'resolve_constraints rejects every draft group except workers and '
        'work-areas-and-tasks; proved by tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.related_group.anyOf.0='
    'demand':
        'related_group is only valid as work-areas-and-tasks (exclude_worker_from_task); '
        'proved by tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.related_group.anyOf.0='
    'locks':
        'related_group is only valid as work-areas-and-tasks; proved by '
        'tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.related_group.anyOf.0='
    'constraints-and-objectives':
        'related_group is only valid as work-areas-and-tasks; proved by '
        'tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.related_group.anyOf.0='
    'baseline-assignments':
        'related_group is only valid as work-areas-and-tasks; proved by '
        'tests/test_scheduling_draft.py.',
    'scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.related_group.anyOf.0='
    'workers':
        'related_group is only valid as work-areas-and-tasks; proved by '
        'tests/test_scheduling_draft.py.',
}


def _observed(runs) -> tuple[dict, set[str]]:
    """Live observations per operation, and every telemetry observation id."""
    coverage: dict[str, dict] = {}
    observation_ids: set[str] = set()

    def record(operation, *, source, state, observation_id, detail):
        seen = coverage.get(operation)
        if seen is None or (seen['state'] != 'success' and state == 'success'):
            coverage[operation] = {'operation': operation, 'source': source, 'state': state,
                                   'observation_id': observation_id, 'detail': detail}

    for run in runs:
        for execution in run.get('prefixes', []):
            where = f"{run.get('run_id')}:{execution.get('scenario')}:rep{execution.get('repetition')}"
            for observation in execution.get('tool_observations', []):
                labels = observation.get('labels') or {}
                name = labels.get('capability_name')
                identifier = ((observation.get('correlation') or {}).get('tool_call_id')
                              or f"{where}:{name}")
                if not name:
                    continue
                observation_ids.add(identifier)
                state = 'failure' if labels.get('failure_reason') else 'success'
                record(f'{name}:invoke', source='capability', state=state,
                       observation_id=identifier, detail=where)
                group = labels.get('fact_group')
                if group:
                    record(f'{name}:request.properties.group={group}', source='capability',
                           state=state, observation_id=identifier, detail=where)
            for turn in execution.get('turns', []):
                activity = turn.get('activity') or {}
                identifier = f"{where}:{turn.get('id')}"
                for segment in (activity.get('response') or {}).get('segments', []):
                    if segment.get('kind') != 'claim' or segment.get('verdict') != 'supported':
                        continue
                    observation_ids.add(identifier)
                    record(f"scheduling_compute:request.properties.metric={segment['metric']}",
                           source='effect', state='success', observation_id=identifier,
                           detail=f'{where} supported claim')
                    family = (segment.get('arguments') or {}).get('family')
                    if family:
                        record('scheduling_compute:request.$defs.ClaimArgumentsV1.properties.'
                               f'family.anyOf.0={family}', source='effect', state='success',
                               observation_id=identifier, detail=f'{where} supported claim')
                draft = (turn.get('verified') or {}).get('persisted_draft') or {}
                for constraint in draft.get('constraints', []):
                    observation_ids.add(identifier)
                    record('scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.'
                           f"kind={constraint['kind']}", source='effect', state='success',
                           observation_id=identifier, detail=f'{where} persisted draft')
                    for entity in constraint.get('resolved_entities', []):
                        record('scheduling_draft:request.$defs.DraftConstraintProposalV1.'
                               f"properties.group={entity['group']}", source='effect',
                               state='success', observation_id=identifier,
                               detail=f'{where} persisted draft')
                        record('scheduling_draft:request.$defs.DraftConstraintProposalV1.'
                               f"properties.related_group.anyOf.0={entity['group']}",
                               source='effect', state='success', observation_id=identifier,
                               detail=f'{where} persisted draft')
    return coverage, observation_ids


def build_coverage(runs, inventory=None) -> dict:
    inventory = inventory or capability_inventory()
    observed, observation_ids = _observed(runs)
    rows = [observed[operation] for operation in sorted(observed)
            if operation in set(inventory['live_required_operations'])]
    covered = {row['operation'] for row in rows}
    for operation in inventory['live_required_operations']:
        if operation in covered:
            continue
        reason = UNREACHABLE_IN_CHAT.get(operation)
        if reason is None:
            rows.append({'operation': operation, 'source': 'capability', 'state': 'gap',
                         'observation_id': next(iter(observation_ids), 'none'),
                         'reason': 'No authored turn exercised this operation.'})
            continue
        rows.append({'operation': operation, 'source': 'deterministic', 'reason': reason})
    for operation in inventory['deterministic_operations']:
        rows.append({'operation': operation, 'source': 'deterministic',
                     'reason': 'Not addressable by a planner turn (query key, paging or '
                               'invalid-query path, manifest error code, or the compute-risk '
                               'run tool); proved by the offline backend suite.'})
    return {'inventory_digest': inventory['digest'], 'tool_coverage': rows}, observation_ids


def generate(run_paths, output: Path, *, allow_dirty: bool = False,
             accepted_findings=()) -> dict:
    from scripts.evidence_binding import resolve_bindings

    runs = [json.loads(Path(path).read_text(encoding='utf-8')) for path in run_paths]
    coverage, observation_ids = build_coverage(runs)
    inventory = capability_inventory()
    models = sorted({run.get('model') for run in runs} | {run.get('judge_model') for run in runs})
    bindings = resolve_bindings(
        {
            'evaluator': ('independent application/fixture reads per turn plus a separately '
                          'configured LLM judge (evals/live_conversations/judge.py RUBRIC); '
                          'a judge pass can never override a fact or effect failure'),
            'model': models,
            'prompt': ('agent/scheduling_instructions.py as built into the measured image; '
                       'authored user turns in evals/live_conversations/scenarios.json'),
            'tool': sorted(module['manifest']['capability_name'] for module in inventory['modules']),
            'policy': ('production grant composition (application/capabilities/registry.py); '
                       'compute-risk modules are withheld from an ordinary planner turn'),
            'application': ('ShiftMind Story 5.7 live conversation suite over the authenticated '
                            'HTTP path against a disposable composed stack'),
            'solver': ('real CP-SAT worker run started through POST /api/v1/schedule-runs in '
                       'Scenario B; no solver participates in Scenarios A and C'),
        },
        repo_root=ROOT,
        dataset_files=[ROOT / 'backend/evals/live_conversations/scenarios.json'],
        allow_dirty=allow_dirty,
    )
    report = summarize_runs(runs, coverage=coverage, observation_ids=observation_ids,
                            version_bindings=bindings, accepted_findings=accepted_findings)
    report['source_runs'] = [str(Path(path).name) for path in run_paths]
    report['images_rebuilt'] = all(run.get('images_rebuilt') for run in runs)
    report['tool_coverage'] = coverage['tool_coverage']
    report['inventory_digest'] = coverage['inventory_digest']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + '\n',
                      encoding='utf-8')
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'evidence/story-5.7/live-conversation-journeys.json')
    parser.add_argument('--allow-dirty', action='store_true')
    parser.add_argument('--accept-finding', action='append', default=[],
                        help='SCENARIO:TURN a reliability failure is accepted for.')
    args = parser.parse_args(argv)
    accepted = [tuple(value.split(':', 1)) for value in args.accept_finding]
    report = generate(args.runs, args.output, allow_dirty=args.allow_dirty,
                      accepted_findings=accepted)
    print(json.dumps({key: report[key] for key in (
        'live_conversation_journeys', 'readiness', 'blocking_reasons',
        'complete_repetitions', 'clean_scenarios')}, indent=2))
    return 0 if report['live_conversation_journeys'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
