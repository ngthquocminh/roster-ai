"""Builds the configured tier-1 claim-support checker, or None (G' phase 3)."""
from __future__ import annotations

import logging
from threading import Lock

from adapters.grounding.jev_checker import (
    OPENROUTER_DECISIONS_ENDPOINT,
    TYPESAFE_ENDPOINT,
    JevClaimSupportChecker,
)
from application.ports.claim_support import ClaimSupportChecker
from settings import Settings

logger = logging.getLogger(__name__)

TYPESAFE_DEFAULT_MODEL = "jev-latest"
OPENROUTER_DEFAULT_MODEL = "typesafe/jev-1.13"

_warned: set[str] = set()
_warned_lock = Lock()


def _warn_once(code: str) -> None:
    with _warned_lock:
        if code in _warned:
            return
        _warned.add(code)
    logger.warning("grounding tier-1 checker disabled: %s", code)


def _openrouter_key(settings: Settings) -> str | None:
    """OPENROUTER_API_KEY, else the agent's own key when the agent itself runs
    through OpenRouter (the live stack passes only AGENT_RUNTIME_API_KEY)."""
    if settings.openrouter_api_key:
        return settings.openrouter_api_key
    if (settings.agent_runtime_model or "").strip().lower().startswith("openrouter:"):
        return settings.agent_runtime_api_key
    return None


def create_claim_support_checker(settings: Settings) -> ClaimSupportChecker | None:
    """`off` -> None. `shadow` -> the provider `grounding_tier1_provider` names:
    `auto` prefers TypeSafe directly when its key is set, else OpenRouter. A
    provider with no key disables the checker with one warning; the turn is
    never affected."""
    if settings.grounding_tier1_mode == "off":
        return None
    provider = settings.grounding_tier1_provider
    if provider == "auto":
        provider = "typesafe" if settings.typesafe_api_key else "openrouter"
    if provider == "typesafe":
        key, endpoint, model = (
            settings.typesafe_api_key, TYPESAFE_ENDPOINT, TYPESAFE_DEFAULT_MODEL)
    else:
        key, endpoint, model = (
            _openrouter_key(settings), OPENROUTER_DECISIONS_ENDPOINT, OPENROUTER_DEFAULT_MODEL)
    if not key:
        _warn_once(f"no API key for provider {provider}")
        return None
    return JevClaimSupportChecker(
        endpoint=endpoint, api_key=key, model=settings.grounding_tier1_model or model,
        timeout_seconds=settings.grounding_tier1_timeout_seconds,
        token_budget=settings.grounding_tier1_token_budget,
    )


__all__ = ["OPENROUTER_DEFAULT_MODEL", "TYPESAFE_DEFAULT_MODEL", "create_claim_support_checker"]
