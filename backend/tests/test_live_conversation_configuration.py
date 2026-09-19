"""The measured configuration a live run records (Story 5.7 AC5): no credential, and a
digest that moves whenever any part of it does."""
import json

import pytest

from evals.live_conversations.configuration import (
    DEFAULT_OVERRIDE_FILE, measured_configuration,
)
from evals.live_conversations.judge import JUDGE_ENDPOINT

OVERRIDE = 'services:\n  api:\n    environment:\n      AGENT_RUNTIME_REQUEST_LIMIT: "12"\n'


def _configuration(override, **extra):
    arguments = {'model': 'openrouter:vendor/agent', 'judge_model': 'openrouter:vendor/judge',
                 'reasoning_effort': 'low', 'override_file': override, **extra}
    return measured_configuration(**arguments)


@pytest.fixture
def override(tmp_path):
    path = tmp_path / 'override.yml'
    path.write_bytes(OVERRIDE.encode('utf-8'))
    return path


def test_the_default_override_is_a_tracked_file_the_suite_can_always_find():
    assert DEFAULT_OVERRIDE_FILE.is_file()
    assert 'evals/live_conversations/' in DEFAULT_OVERRIDE_FILE.as_posix()
    assert '_bmad-output' not in DEFAULT_OVERRIDE_FILE.as_posix()


def test_it_records_model_endpoint_effort_and_override_identity(override):
    configuration = _configuration(override)
    assert configuration['agent'] == {'model': 'openrouter:vendor/agent',
                                      'endpoint': 'https://openrouter.ai/api/v1'}
    assert configuration['judge'] == {'model': 'openrouter:vendor/judge',
                                      'endpoint': JUDGE_ENDPOINT}
    assert configuration['reasoning_effort'] == 'low'
    assert len(configuration['override_sha256']) == 64
    assert len(configuration['configuration_digest']) == 64


@pytest.mark.parametrize('change', [
    {'model': 'openrouter:vendor/other'}, {'judge_model': 'openrouter:vendor/other'},
    {'reasoning_effort': 'high'},
])
def test_the_digest_moves_with_every_recorded_field(override, change):
    assert (_configuration(override)['configuration_digest']
            != _configuration(override, **change)['configuration_digest'])


def test_the_digest_moves_with_the_override_file_but_not_with_its_line_endings(tmp_path, override):
    # Same file NAME in each directory: the recorded name is part of the digest body, so
    # differently named files would differ whatever the content hashing does.
    def variant(directory, content):
        (tmp_path / directory).mkdir()
        path = tmp_path / directory / override.name
        path.write_bytes(content.encode('utf-8'))
        return path

    base = _configuration(override)
    crlf = _configuration(variant('crlf', OVERRIDE.replace('\n', '\r\n')))
    edited = _configuration(variant('edited', OVERRIDE.replace('"12"', '"13"')))
    assert crlf['override_sha256'] == base['override_sha256']
    assert crlf['configuration_digest'] == base['configuration_digest']
    assert edited['override_sha256'] != base['override_sha256']
    assert edited['configuration_digest'] != base['configuration_digest']


def test_the_record_holds_no_credential_field(override):
    configuration = _configuration(override)
    assert set(configuration) == {
        'agent', 'judge', 'reasoning_effort', 'override_file', 'override_sha256',
        'configuration_digest'}
    assert 'api_key' not in json.dumps(configuration).lower()


def test_an_agent_provider_with_no_known_endpoint_is_refused(override):
    with pytest.raises(ValueError, match='no known endpoint identity'):
        _configuration(override, model='unknown:vendor/agent')


def test_a_missing_override_file_is_refused_before_any_spend(tmp_path):
    with pytest.raises(ValueError, match='does not exist'):
        _configuration(tmp_path / 'absent.yml')
