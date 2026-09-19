"""`generate` and the CLI's argument handling refuse bad input before any binding is written."""
import pytest

from evals.live_conversations import evidence

CODE = {'git_commit': 'test-only', 'working_tree_dirty': False}
IMAGES = {'api': 'sha256:' + 'a' * 64, 'web': 'sha256:' + 'b' * 64, 'database': 'postgres:18'}
CONFIGURATION = {'agent': {'model': 'openrouter:m', 'endpoint': 'https://openrouter.ai/api/v1'},
                 'judge': {'model': 'openrouter:j', 'endpoint': 'https://judge.example/v1'},
                 'reasoning_effort': 'low', 'override_file': 'compose.override.yml',
                 'override_sha256': '1' * 64, 'configuration_digest': '2' * 64}


@pytest.fixture(autouse=True)
def _code_commit_is_the_recorded_one(monkeypatch):
    # The fake commit ids below name no real commit; the walk back to a code commit has its
    # own tests (test_evidence_binding.py); the test below pins that generate uses it.
    import scripts.evidence_binding as binding
    monkeypatch.setattr(binding, 'nearest_code_commit', lambda root, commit: commit)


def _write_run(tmp_path, name, code=CODE, images=IMAGES, configuration=CONFIGURATION,
               images_rebuilt=True, **extra):
    import json

    path = tmp_path / name
    path.write_text(json.dumps({'run_id': name, 'code': code, 'prefixes': [],
                                'model': 'openrouter:m', 'judge_model': 'openrouter:j',
                                'images': images, 'configuration': configuration,
                                'images_rebuilt': images_rebuilt, **extra}),
                    encoding='utf-8')
    return path


def test_generating_with_no_run_reports_is_refused_not_an_index_error(tmp_path):
    with pytest.raises(ValueError, match='at least one run report'):
        evidence.generate([], tmp_path / 'out.json')


def test_runs_measured_on_different_code_cannot_be_combined(tmp_path):
    runs = [_write_run(tmp_path, 'a.json'),
            _write_run(tmp_path, 'b.json', code={**CODE, 'git_commit': 'another-commit'})]
    with pytest.raises(ValueError, match='same code binding'):
        evidence.generate(runs, tmp_path / 'out.json')


def test_a_run_that_recorded_no_code_binding_is_refused(tmp_path):
    with pytest.raises(ValueError, match='same code binding'):
        evidence.generate([_write_run(tmp_path, 'a.json', code=None)], tmp_path / 'out.json')


def test_a_measurement_taken_on_a_dirty_tree_is_refused_unless_the_override_is_named(tmp_path):
    run = _write_run(tmp_path, 'a.json', code={**CODE, 'working_tree_dirty': True})
    with pytest.raises(ValueError, match='dirty tree'):
        evidence.generate([run], tmp_path / 'out.json')


@pytest.mark.parametrize('value', ['B', 'B4', 'B:', 'B:four', 'B:-1', ':4x'])
def test_a_malformed_accepted_finding_is_a_usage_error(monkeypatch, tmp_path, value):
    monkeypatch.setattr(evidence, 'generate', lambda *_a, **_k: pytest.fail('must not generate'))
    with pytest.raises(SystemExit) as raised:
        evidence.main([str(tmp_path / 'run.json'), '--accept-finding', value])
    assert raised.value.code == 2


def test_well_formed_accepted_findings_reach_the_generator_as_scenario_and_turn(monkeypatch, tmp_path):
    seen = {}

    def fake_generate(runs, output, **kwargs):
        seen.update(kwargs)
        return {'live_conversation_journeys': 'passed', 'readiness': 'ok', 'blocking_reasons': [],
                'complete_repetitions': 3, 'clean_scenarios': ['A', 'B', 'C']}

    monkeypatch.setattr(evidence, 'generate', fake_generate)
    code = evidence.main([str(tmp_path / 'run.json'), '--accept-finding', 'B:4',
                          '--accept-finding', 'C:10'])
    assert code == 0 and seen['accepted_findings'] == [('B', '4'), ('C', '10')]


# --- AC5 provenance and AC8 binding (Story 5.7 docs/evidence review) -------------

def test_a_run_that_recorded_no_images_cannot_be_bound(tmp_path):
    with pytest.raises(ValueError, match='image digests'):
        evidence.generate([_write_run(tmp_path, 'a.json', images=None)], tmp_path / 'out.json')


def test_a_run_that_recorded_no_configuration_cannot_be_bound(tmp_path):
    with pytest.raises(ValueError, match='measured configuration'):
        evidence.generate([_write_run(tmp_path, 'a.json', configuration=None)],
                          tmp_path / 'out.json')


@pytest.mark.parametrize('field', ['images', 'configuration'])
def test_runs_measured_under_different_images_or_configurations_cannot_be_combined(tmp_path, field):
    other = {'images': {**IMAGES, 'api': 'sha256:' + 'c' * 64},
             'configuration': {**CONFIGURATION, 'configuration_digest': '3' * 64}}[field]
    runs = [_write_run(tmp_path, 'a.json'), _write_run(tmp_path, 'b.json', **{field: other})]
    with pytest.raises(ValueError, match='same'):
        evidence.generate(runs, tmp_path / 'out.json')


def test_a_report_that_stopped_before_recording_images_is_named_with_its_reason(tmp_path):
    early = _write_run(tmp_path, 'early.json', images=None,
                       incomplete_reason='isolated_stack_build_failed')
    with pytest.raises(ValueError, match=r'early\.json records no image digests.*'
                                         r'isolated_stack_build_failed.*left out'):
        evidence.generate([_write_run(tmp_path, 'a.json'), early], tmp_path / 'out.json')


def test_images_that_no_report_built_cannot_be_tied_to_the_measured_code(tmp_path):
    with pytest.raises(ValueError, match='no run report built its images'):
        evidence.generate([_write_run(tmp_path, 'a.json', images_rebuilt=False)],
                          tmp_path / 'out.json')


def test_a_resumed_chain_counts_as_built_when_one_report_built_the_images(tmp_path):
    built = _write_run(tmp_path, 'built.json')
    resumed = _write_run(tmp_path, 'resumed.json', images_rebuilt=False)
    report = evidence.generate([built, resumed], tmp_path / 'out.json')
    assert report['images_rebuilt'] is True


def test_the_evidence_binds_what_the_runs_recorded_and_the_source_reports_by_digest(tmp_path):
    import hashlib
    import json

    run = _write_run(tmp_path, 'a.json')
    report = evidence.generate([run], tmp_path / 'out.json')
    written = json.loads((tmp_path / 'out.json').read_text(encoding='utf-8'))
    assert report['version_bindings']['image'] == IMAGES == written['version_bindings']['image']
    assert written['measured_configuration'] == CONFIGURATION
    assert written['version_bindings']['model'] == ['agent:openrouter:m', 'judge:openrouter:j']
    assert written['source_runs'] == [{'name': 'a.json', 'run_id': 'a.json',
                                       'sha256': hashlib.sha256(run.read_bytes()).hexdigest()}]


def _draft_turn(kind, entities):
    return {'id': 'turn-4', 'verified': {'persisted_draft': {'constraints': [
        {'kind': kind, 'resolved_entities': [{'group': group} for group in entities]}]}}}


RELATED = ('scheduling_draft:request.$defs.DraftConstraintProposalV1.properties.related_group'
           '.anyOf.0=')


def _observed(*turns):
    rows, _ids = evidence._observed([{'run_id': 'r', 'prefixes': [
        {'scenario': 'B', 'repetition': 1, 'turns': list(turns)}]}])
    return rows


def test_related_group_is_proved_live_only_by_a_worker_task_exclusion():
    rows = _observed(_draft_turn('exclude_worker_from_task', ['workers', 'work-areas-and-tasks']))
    assert RELATED + 'work-areas-and-tasks' in rows
    assert RELATED + 'workers' not in rows


def test_a_draft_with_no_related_entity_says_nothing_about_related_group():
    rows = _observed(_draft_turn('set_max_hours', ['workers']),
                     _draft_turn('set_min_workers_per_task', ['work-areas-and-tasks']))
    assert not [operation for operation in rows if operation.startswith(RELATED)]
    assert any('properties.group=workers' in operation for operation in rows)


def test_no_operation_is_both_proved_live_and_excused_as_unreachable():
    rows = _observed(_draft_turn('exclude_worker_from_task', ['workers', 'work-areas-and-tasks']))
    assert not set(rows) & set(evidence.UNREACHABLE_IN_CHAT)


def test_the_demonstration_approval_gap_is_stated_not_filed_as_unaddressable():
    coverage, _ids = evidence.build_coverage([])
    row = next(r for r in coverage['tool_coverage']
               if r['operation'] == 'shiftmind_demonstration:error=approval_required')
    assert row['source'] == 'deterministic' and 'Decision 1' in row['reason']
    assert 'Not addressable' not in row['reason']


def _failed_turn(status, failures):
    return {'id': 'turn-5', 'user': 'q', 'verdict': 'fail', 'agent_run_status': status,
            'factual_failures': failures}


def test_an_accepted_finding_states_its_pass_rate_and_why_each_execution_failed():
    passed = {'verdict': 'pass', 'agent_run_status': 'agent_completed', 'factual_failures': []}
    runs = [{'prefixes': [
        {'scenario': 'B', 'repetition': 1, 'attempt': 1, 'turns': [{}] * 4 + [
            _failed_turn('agent_failed', ['unsuccessful_agent_turn'])]},
        {'scenario': 'B', 'repetition': 2, 'attempt': 1, 'turns': [{}] * 4 + [passed]},
        {'scenario': 'B', 'repetition': 3, 'attempt': 1, 'turns': [{}] * 4 + [
            _failed_turn('agent_failed', [])]},
    ]}]
    details = evidence._accepted_finding_details(
        runs, [('B', '5')], {'B:5': {'passed': 1, 'executed': 3}})
    assert details == [{'turn': 'B:5', 'passed': 1, 'executed': 3, 'failures': [
        {'repetition': 1, 'agent_run_status': 'agent_failed',
         'factual_failures': ['unsuccessful_agent_turn']},
        {'repetition': 3, 'agent_run_status': 'agent_failed', 'factual_failures': []}]}]


def test_a_retried_execution_is_read_by_its_final_attempt_only():
    runs = [{'prefixes': [
        {'scenario': 'B', 'repetition': 1, 'attempt': 1,
         'turns': [{}] * 4 + [_failed_turn('agent_failed', ['unsuccessful_agent_turn'])]},
        {'scenario': 'B', 'repetition': 1, 'attempt': 2, 'turns': [{}] * 4 + [
            {'verdict': 'pass', 'factual_failures': []}]},
    ]}]
    assert evidence._accepted_finding_details(runs, [('B', '5')], {})[0]['failures'] == []


def test_a_run_started_at_a_docs_only_head_is_bound_to_the_code_commit_it_measured(
        tmp_path, monkeypatch):
    import json

    import scripts.evidence_binding as binding
    monkeypatch.setattr(binding, 'nearest_code_commit',
                        lambda root, commit: 'code-commit' if commit == 'test-only' else commit)
    report = evidence.generate([_write_run(tmp_path, 'a.json')], tmp_path / 'out.json')
    written = json.loads((tmp_path / 'out.json').read_text(encoding='utf-8'))
    assert report['version_bindings']['code']['git_commit'] == 'code-commit'
    assert written['measured_at_commit'] == 'test-only'


def test_the_runs_stay_bound_when_the_binding_names_the_code_commit_not_the_start_commit(
        tmp_path, monkeypatch):
    import scripts.evidence_binding as binding
    monkeypatch.setattr(binding, 'nearest_code_commit', lambda root, commit: 'code-commit')
    seen = {}

    def fake_summarize(runs, **kwargs):
        seen['codes'] = [run['code'] for run in runs]
        seen['binding'] = kwargs['version_bindings']['code']
        return {'turn_pass_rates': {}}

    monkeypatch.setattr(evidence, 'summarize_runs', fake_summarize)
    evidence.generate([_write_run(tmp_path, 'a.json')], tmp_path / 'out.json')
    assert seen['codes'] == [seen['binding']] and seen['binding']['git_commit'] == 'code-commit'
