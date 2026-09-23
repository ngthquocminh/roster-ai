"""The configuration a live run was measured under (Story 5.7 AC5).

A run report records WHAT was configured, never a credential: agent and judge
model with their endpoint identity, the reasoning effort, and the sha256 of the
tracked compose override that carries the price rates and the request/tool/
token/deadline limits. `configuration_digest` covers all of it, so two reports
share a digest only if they ran the same configuration.

`behavioral_digest` (Story 5.8) is the narrower companion a regression gate can
actually compare on: the same models and effort, but the override reduced to its
parsed `environment` maps with the per-token PRICE keys excluded, so editing the
file's comment header or correcting a price does not invalidate a comparison.
Prices are behaviourally coupled through the spend limiter, not the model, so a
truncated run is refused separately (`blocking_reasons`, `complete_repetitions`)
rather than by pinning prices here. The rule is an EXCLUSION, never an
allow-list: a newly added environment key is included by default and fails
closed.
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


#: Environment keys excluded from `behavioral_digest`: the per-token prices feed
#: the spend limiter's accounting, not the agent's behaviour.
PRICE_KEY_SUFFIX = '_USD_PER_MTOK'


def _file_digest(path: Path) -> str:
    # Line endings normalised, so the digest does not move with `core.autocrlf`.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def behavioral_environment(override_file: Path) -> dict:
    """The override's `environment` maps, per service, minus the price keys.

    Both the `api` and `worker` service blocks are kept SEPARATELY: they are
    expected to agree, and silently merging them would hide a configuration
    where they do not.

    KNOWN GAP (Story 5.8 review, accepted rather than fixed): `yaml.safe_load`
    never resolves docker-compose `${VAR:-default}` substitution, so a value
    like `DEMONSTRATION_ENABLED: ${DEMONSTRATION_ENABLED:-false}` is captured
    as that literal placeholder string, identical regardless of what
    `stack.py` actually injected at runtime. `reasoning_effort` has the same
    substitution syntax but is safe because `measured_configuration` also
    records it as its own explicit field; `demonstration_enabled` has no such
    field and so is invisible to `behavioral_digest` either way. Accepted
    because it does not affect this suite's authored conversation paths
    today -- revisit if a future scenario becomes sensitive to it.
    """
    import yaml  # dev-group, test-only -- see backend/pyproject.toml

    document = yaml.safe_load(Path(override_file).read_text(encoding='utf-8')) or {}
    services = document.get('services') or {}
    return {
        name: {key: str(value)
               for key, value in (services.get(name, {}).get('environment') or {}).items()
               if not key.endswith(PRICE_KEY_SUFFIX)}
        for name in sorted(services)
    }


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
    return {**body, 'configuration_digest': digest,
            'behavioral_digest': behavioral_digest(
                model=model, judge_model=judge_model,
                reasoning_effort=reasoning_effort, override_file=override)}


def behavioral_digest(*, model: str, judge_model: str, reasoning_effort: str,
                      override_file: Path) -> str:
    """The digest a regression comparison is refused on when it differs.

    Serialised exactly as `configuration_digest` is: `json.dumps(sort_keys=True)`
    over the body, sha256 of its UTF-8 bytes.
    """
    body = {
        'agent_model': model,
        'judge_model': judge_model,
        'reasoning_effort': reasoning_effort,
        'environment': behavioral_environment(Path(override_file)),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode('utf-8')).hexdigest()
