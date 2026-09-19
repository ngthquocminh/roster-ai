"""The configuration a live run was measured under (Story 5.7 AC5).

A run report records WHAT was configured, never a credential: agent and judge
model with their endpoint identity, the reasoning effort, and the sha256 of the
tracked compose override that carries the price rates and the request/tool/
token/deadline limits. `configuration_digest` covers all of it, so two reports
share a digest only if they ran the same configuration.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evals.live_conversations.judge import JUDGE_ENDPOINT
from evals.live_conversations.stack import ROOT

#: Agent endpoint identity by provider prefix of `--agent-model`. A provider with
#: no entry is refused rather than recorded without an endpoint.
AGENT_ENDPOINTS = {'openrouter': 'https://openrouter.ai/api/v1'}

DEFAULT_OVERRIDE_FILE = ROOT / 'backend/evals/live_conversations/compose.override.yml'


def _file_digest(path: Path) -> str:
    # Line endings normalised, so the digest does not move with `core.autocrlf`.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def measured_configuration(*, model: str, judge_model: str, reasoning_effort: str,
                           override_file: Path) -> dict:
    provider = model.partition(':')[0]
    if provider not in AGENT_ENDPOINTS:
        raise ValueError(f'no known endpoint identity for agent provider {provider!r}')
    override = Path(override_file)
    if not override.is_file():
        raise ValueError(f'the compose override {override} does not exist')
    try:
        recorded_path = override.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        recorded_path = override.name
    body = {
        'agent': {'model': model, 'endpoint': AGENT_ENDPOINTS[provider]},
        'judge': {'model': judge_model, 'endpoint': JUDGE_ENDPOINT},
        'reasoning_effort': reasoning_effort,
        'override_file': recorded_path,
        'override_sha256': _file_digest(override),
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode('utf-8')).hexdigest()
    return {**body, 'configuration_digest': digest}
