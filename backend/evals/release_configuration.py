"""The pinned release configuration a Gate B measurement is taken under.

Story 5.13 needs two facts about "the release configuration" in more than one
place, so they are derived once, here, and never hard-coded:

* **Which capabilities the release allows** (D5). A capability is allowed when
  the `Settings` field its module's `required_feature_policy` names defaults to
  True. The policy name and the settings field are the same string by
  construction (`scheduling_baseline_enabled`, ...), so the allowed set follows
  `settings.py` instead of a second list. The dataclass DEFAULT is read, not the
  process environment: a developer's `DEMONSTRATION_ENABLED=true` must not widen
  what the release is said to ship.
* **The measured live configuration** (D3, D9): reasoning effort, per-turn
  budget and per-token prices, read from the tracked compose override that
  Story 5.7 already binds into every live-conversation report. A live Gate B
  run applies that file's `api` environment, so the single-turn and multi-turn
  measurements run the same configuration the live-conversation suite did.
"""
from __future__ import annotations

import os
import re
from dataclasses import MISSING, dataclass, fields
from pathlib import Path
from typing import Mapping

from application.capabilities.installed import installed_modules
from scripts.evidence_binding import REPO_ROOT

OVERRIDE_FILE = REPO_ROOT / "backend" / "evals" / "live_conversations" / "compose.override.yml"

#: docker-compose `${VAR:-default}` / `${VAR}` substitution.
_SUBSTITUTION = re.compile(r"\$\{(?P<name>[A-Z0-9_]+)(?::-(?P<default>[^}]*))?\}")


def release_allowed_capabilities() -> frozenset[str]:
    """Capability names whose feature flag defaults to True in `Settings`."""
    from settings import Settings

    defaults = {
        field.name: field.default
        for field in fields(Settings)
        if field.default is not MISSING
    }
    allowed: set[str] = set()
    for module in installed_modules():
        policy = module.required_feature_policy
        if policy not in defaults:
            # A module gated by a policy no settings field carries cannot be
            # said to be allowed or not; refuse rather than guess.
            raise ValueError(
                f"capability {module.manifest.capability_name!r} is gated by "
                f"{policy!r}, which names no Settings field"
            )
        if defaults[policy] is True:
            allowed.add(module.manifest.capability_name)
    return frozenset(allowed)


def resolve_compose_value(value: str, environ: Mapping[str, str]) -> str:
    """Apply compose's `${VAR:-default}` substitution to one override value."""

    def _substitute(match: re.Match[str]) -> str:
        name = match.group("name")
        default = match.group("default")
        current = environ.get(name)
        if current:
            return current
        return default if default is not None else ""

    return _SUBSTITUTION.sub(_substitute, value)


def override_environment(
    override_file: Path = OVERRIDE_FILE,
    *,
    service: str = "api",
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The override's `environment` for `service`, substitutions resolved."""
    import yaml  # dev-group, test-only -- see backend/pyproject.toml

    document = yaml.safe_load(Path(override_file).read_text(encoding="utf-8")) or {}
    block = ((document.get("services") or {}).get(service) or {}).get("environment") or {}
    source = os.environ if environ is None else environ
    return {key: resolve_compose_value(str(value), source) for key, value in block.items()}


@dataclass(frozen=True)
class PriceRatesV1:
    """Per-million-token prices the spend is measured against."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    cache_read_usd_per_mtok: float = 0.0
    cache_write_usd_per_mtok: float = 0.0

    @property
    def measured(self) -> bool:
        return self.input_usd_per_mtok > 0 or self.output_usd_per_mtok > 0


def override_price_rates(override_file: Path = OVERRIDE_FILE) -> PriceRatesV1:
    """The prices `compose.override.yml` pins for the configured model."""
    environment = override_environment(override_file)

    def _rate(key: str) -> float:
        return float(environment.get(key, "0") or 0)

    return PriceRatesV1(
        input_usd_per_mtok=_rate("AGENT_MODEL_INPUT_USD_PER_MTOK"),
        output_usd_per_mtok=_rate("AGENT_MODEL_OUTPUT_USD_PER_MTOK"),
        cache_read_usd_per_mtok=_rate("AGENT_MODEL_CACHE_READ_USD_PER_MTOK"),
        cache_write_usd_per_mtok=_rate("AGENT_MODEL_CACHE_WRITE_USD_PER_MTOK"),
    )


def apply_override_environment(override_file: Path = OVERRIDE_FILE) -> dict[str, str]:
    """Export the override's `api` environment into this process.

    An explicitly exported variable wins, exactly as compose's own `${VAR:-x}`
    would let it; a key the operator did not export takes the override's value.
    Returns what was applied so the caller can record it.

    The telemetry-only keys (`configuration.TELEMETRY_ONLY_KEYS`) are skipped:
    they change what a trace exporter or the tier-1 shadow scorer receives,
    never what the model sees, and this harness exports no traces.
    """
    from evals.live_conversations.configuration import TELEMETRY_ONLY_KEYS

    applied: dict[str, str] = {}
    for key, value in override_environment(override_file).items():
        if key in TELEMETRY_ONLY_KEYS:
            continue
        if key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


__all__ = [
    "OVERRIDE_FILE",
    "PriceRatesV1",
    "apply_override_environment",
    "override_environment",
    "override_price_rates",
    "release_allowed_capabilities",
    "resolve_compose_value",
]
