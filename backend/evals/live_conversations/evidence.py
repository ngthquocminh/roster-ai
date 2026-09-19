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
import hashlib
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
    'scheduling_inspect:request.properties.group=assignments':
        'A planner turn reads assignments from the workflow snapshot, which carries them for '
        'the baseline and any candidate, so no authored turn addresses the projection group '
        'itself; the group is proved by tests/test_scheduling_inspect.py.',
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

#: Operations outside the live denominator that need a reason more specific than the
#: generic one below -- a known product gap must be stated, not filed under "not
#: addressable".
DETERMINISTIC_REASONS = {
    'shiftmind_demonstration:error=approval_required':
        'A suspended demonstration call has no approval path over the authenticated HTTP '
        'conversation route: it finalizes the run as cancelled (api/routers/conversations.py) '
        'instead of raising an approval request, so no live turn can complete this branch. '
        'Story 5.7 Decision 1 reports it as a gap rather than widening the schedule-run-shaped '
        'approval contract; the approval branch of the capability itself is proved by '
        'tests/test_demonstration_capability.py.',
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
                        # The persisted constraint keeps only resolved entities, not the
                        # proposal's `related_group` field. Only exclude_worker_from_task
                        # carries one, and only as work-areas-and-tasks
                        # (application/drafting/resolve.py), so that is the single
                        # live-provable value; every other resolved entity says nothing
                        # about `related_group`.
                        if (constraint['kind'] == 'exclude_worker_from_task'
                                and entity['group'] == 'work-areas-and-tasks'):
                            record('scheduling_draft:request.$defs.DraftConstraintProposalV1.'
                                   'properties.related_group.anyOf.0=work-areas-and-tasks',
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
            # A sentinel guaranteed absent from `observation_ids`, never a real,
            # unrelated observation borrowed just to satisfy the membership check
            # in `require_complete_coverage` -- a gap row proves nothing live.
            rows.append({'operation': operation, 'source': 'capability', 'state': 'gap',
                         'observation_id': 'gap:' + operation,
                         'reason': 'No authored turn exercised this operation.'})
            continue
        rows.append({'operation': operation, 'source': 'deterministic', 'reason': reason})
    for operation in inventory['deterministic_operations']:
        rows.append({'operation': operation, 'source': 'deterministic',
                     'reason': DETERMINISTIC_REASONS.get(
                         operation,
                         'Not addressable by a planner turn (query key, paging or '
                         'invalid-query path, manifest error code, or the compute-risk '
                         'run tool); proved by the offline backend suite.')})
    return {'inventory_digest': inventory['digest'], 'tool_coverage': rows}, observation_ids


def _agreed(run_paths, runs, key: str, what: str):
    """The one value every run report records for `key`, or a refusal.

    Runs measured under different images or configurations cannot be combined into
    one bound report, and a report that recorded neither cannot be bound at all.
    """
    for path, run in zip(run_paths, runs):
        if run.get(key) is None:
            reason = run.get('incomplete_reason')
            raise ValueError(
                f'{Path(path).name} records no {what}'
                + (f' (it stopped early: {reason}; a report with no executions can be left '
                   'out)' if reason else '; it was measured by an older suite and must be '
                   'measured again'))
    if len({json.dumps(run[key], sort_keys=True) for run in runs}) != 1:
        raise ValueError(f'every run must record the same {what}; these reports were '
                         'measured under different ones and cannot be combined')
    return runs[0][key]


def _source_runs(run_paths, runs) -> list[dict]:
    """Each source report by name, run id and sha256, so the (git-ignored) transcripts
    the verdict rests on are bound by digest even though they are not committed."""
    return [{'name': Path(path).name, 'run_id': run.get('run_id'),
             'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            for path, run in zip(run_paths, runs)]


def _accepted_finding_details(runs, accepted, pass_rates) -> list[dict]:
    """Why each accepted turn was accepted: its pass rate and what its failures were.

    Read from each execution's FINAL attempt, the same rule the readiness summary
    counts by, so the file states the failure the owner accepted rather than only
    naming the turn.
    """
    details = []
    for scenario, turn in sorted((s, int(t)) for s, t in accepted):
        key = f'{scenario}:{turn}'
        failures = []
        for run in runs:
            final = {}
            for execution in run.get('prefixes', []):
                final[(execution.get('repetition'), execution.get('scenario'))] = execution
            for (repetition, name), execution in sorted(final.items(), key=lambda i: (i[0][0] or 0, i[0][1] or '')):
                turns = execution.get('turns', [])
                if name != scenario or len(turns) < turn or turns[turn - 1].get('verdict') == 'pass':
                    continue
                failed = turns[turn - 1]
                failures.append({'repetition': repetition,
                                 'agent_run_status': failed.get('agent_run_status'),
                                 'factual_failures': sorted(failed.get('factual_failures') or ())})
        details.append({'turn': key, **pass_rates.get(key, {}), 'failures': failures})
    return details


def generate(run_paths, output: Path, *, allow_dirty: bool = False,
             accepted_findings=(), ignore_paths=()) -> dict:
    from scripts.evidence_binding import nearest_code_commit, resolve_bindings

    if not run_paths:
        raise ValueError('at least one run report is required')
    runs = [json.loads(Path(path).read_text(encoding='utf-8')) for path in run_paths]
    coverage, observation_ids = build_coverage(runs)
    inventory = capability_inventory()
    # Bind to the commit the MEASUREMENT ran at, which every run report records,
    # not to whatever HEAD is when the report is written. Otherwise fixing the
    # generator moves HEAD and invalidates the measurement that exposed the fix.
    measured = {json.dumps(run.get('code'), sort_keys=True) for run in runs}
    if len(measured) != 1 or runs[0].get('code') is None:
        raise ValueError('every run must record the same code binding')
    code_binding = runs[0]['code']
    # A run started right after a docs-only commit measured the code of the closest earlier
    # commit that touched code; the binding names that one (checked to be the same code),
    # and `measured_at_commit` keeps the commit the run actually started from.
    measured_at_commit = code_binding['git_commit']
    code_binding = {**code_binding, 'git_commit': nearest_code_commit(ROOT, measured_at_commit)}
    if code_binding.get('working_tree_dirty') and not (allow_dirty or ignore_paths):
        # `resolve_bindings` enforces the same rule and records the override, so
        # this guard only fails fast; it must not be stricter than the binder.
        raise ValueError('the measurement ran on a dirty tree; pass --allow-dirty to record '
                         'the override, or measure again on a clean tree')
    # Both come from what the suite recorded it RAN, never from a manifest another build
    # wrote: the api/web digests are the live-eval images' content ids, and the
    # configuration is the measured models, endpoints, effort and override-file digest.
    image_binding = _agreed(run_paths, runs, 'images', 'image digests')
    configuration = _agreed(run_paths, runs, 'configuration', 'measured configuration')
    # `_agreed` makes every report name the same image ids, so it is enough that ONE report
    # built them (a resume reuses them with --skip-image-build). None built them: the ids
    # are whatever was lying around, and binding them to the measured commit would claim an
    # image nobody built from this code.
    if not any(run.get('images_rebuilt') for run in runs):
        raise ValueError('no run report built its images (every one used --skip-image-build); '
                         'the image ids cannot be tied to the measured code')
    models = sorted({f"agent:{run.get('model')}" for run in runs}
                    | {f"judge:{run.get('judge_model')}" for run in runs})
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
        # The report being written, and artifacts outside the measured backend,
        # cannot change what was measured. Each one is named here and recorded
        # below, never waved through with allow_dirty.
        ignore_paths=frozenset(ignore_paths),
        code_binding=code_binding,
        image_binding=image_binding,
    )
    report = summarize_runs(runs, coverage=coverage, observation_ids=observation_ids,
                            version_bindings=bindings, accepted_findings=accepted_findings)
    report['source_runs'] = _source_runs(run_paths, runs)
    report['measured_configuration'] = configuration
    report['accepted_finding_details'] = _accepted_finding_details(
        runs, accepted_findings, report['turn_pass_rates'])
    report['ignored_dirty_paths'] = sorted(ignore_paths)
    # Stated, never implied: the tree carried uncommitted paths while the
    # measurement ran. They are named above and lie outside the measured
    # backend, but a reader must be able to see the condition.
    report['measured_at_commit'] = measured_at_commit
    report['measurement_tree_dirty'] = bool(code_binding.get('working_tree_dirty'))
    report['images_rebuilt'] = any(run.get('images_rebuilt') for run in runs)
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
    parser.add_argument('--ignore-path', action='append', default=[],
                        help='A repo-relative path that cannot affect the measurement (the '
                             'report itself, artifacts outside the measured backend). Recorded '
                             'in the report.')
    parser.add_argument('--accept-finding', action='append', default=[],
                        help='SCENARIO:TURN a reliability failure is accepted for.')
    args = parser.parse_args(argv)
    accepted = []
    for value in args.accept_finding:
        scenario, sep, turn = value.partition(':')
        if not sep or not turn.isdigit():
            parser.error(f'--accept-finding must be SCENARIO:TURN (an integer), got {value!r}')
        accepted.append((scenario, turn))
    report = generate(args.runs, args.output, allow_dirty=args.allow_dirty,
                      accepted_findings=accepted, ignore_paths=args.ignore_path)
    print(json.dumps({key: report[key] for key in (
        'live_conversation_journeys', 'readiness', 'blocking_reasons',
        'complete_repetitions', 'clean_scenarios')}, indent=2))
    return 0 if report['live_conversation_journeys'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
