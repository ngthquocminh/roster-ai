"""`generate` and the CLI's argument handling refuse bad input before any binding is written."""
import pytest

from evals.live_conversations import evidence

CODE = {'git_commit': 'test-only', 'working_tree_dirty': False}


def _write_run(tmp_path, name, code=CODE):
    import json

    path = tmp_path / name
    path.write_text(json.dumps({'run_id': name, 'code': code, 'prefixes': [], 'model': 'm',
                                'judge_model': 'j'}), encoding='utf-8')
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
