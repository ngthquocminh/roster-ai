"""Builds the configured tier-1 claim-support checker and turn router, or None."""
from __future__ import annotations

import logging
from threading import Lock

from adapters.grounding.jev_checker import (
    OPENROUTER_DECISIONS_ENDPOINT,
    TYPESAFE_ENDPOINT,
    JevClaimSupportChecker,
)
from adapters.grounding.jev_router import JevTurnRouter
from application.ports.claim_support import ClaimSupportChecker
from application.ports.turn_router import TurnRouter
from settings import Settings

logger = logging.getLogger(__name__)

TYPESAFE_DEFAULT_MODEL = "jev-latest"
OPENROUTER_DEFAULT_MODEL = "typesafe/jev-1.13"

_warned: set[tuple[str, str]] = set()
_warned_lock = Lock()


def _warn_once(code: str, component: str = "grounding tier-1 checker") -> None:
    with _warned_lock:
        if (component, code) in _warned:
            return
        _warned.add((component, code))
    logger.warning("%s disabled: %s", component, code)


def _openrouter_key(settings: Settings) -> str | None:
    """OPENROUTER_API_KEY, else the agent's own key when the agent itself runs
    through OpenRouter (the live stack passes only AGENT_RUNTIME_API_KEY)."""
    if settings.openrouter_api_key:
        return settings.openrouter_api_key
    if (settings.agent_runtime_model or "").strip().lower().startswith("openrouter:"):
        return settings.agent_runtime_api_key
    return None


def _jev_target(settings: Settings) -> tuple[str, str | None, str, str]:
    """(provider, key, endpoint, default model) per `grounding_tier1_provider`:
    `auto` prefers TypeSafe directly when its key is set, else OpenRouter."""
    provider = settings.grounding_tier1_provider
    if provider == "auto":
        provider = "typesafe" if settings.typesafe_api_key else "openrouter"
    if provider == "typesafe":
        return provider, settings.typesafe_api_key, TYPESAFE_ENDPOINT, TYPESAFE_DEFAULT_MODEL
    return (provider, _openrouter_key(settings), OPENROUTER_DECISIONS_ENDPOINT,
            OPENROUTER_DEFAULT_MODEL)


def create_claim_support_checker(settings: Settings) -> ClaimSupportChecker | None:
    """`off` -> None. Otherwise the Jev provider `_jev_target` resolves. A
    provider with no key disables the checker with one warning; the turn is
    never affected."""
    if settings.grounding_tier1_mode == "off":
        return None
    provider, key, endpoint, model = _jev_target(settings)
    if not key:
        _warn_once(f"no API key for provider {provider}")
        return None
    return JevClaimSupportChecker(
        endpoint=endpoint, api_key=key, model=settings.grounding_tier1_model or model,
        timeout_seconds=settings.grounding_tier1_timeout_seconds,
        token_budget=settings.grounding_tier1_token_budget,
        provider=provider,
    )


def create_turn_router(settings: Settings) -> TurnRouter | None:
    """`off` -> None. Otherwise the tier-1 checker's Jev provider, key and
    model; with no key the router is disabled with one warning, and every turn
    takes the scheduling path."""
    if settings.agent_router_mode == "off":
        return None
    provider, key, endpoint, model = _jev_target(settings)
    if not key:
        _warn_once(f"no API key for provider {provider}", component="agent turn router")
        return None
    return JevTurnRouter(
        endpoint=endpoint, api_key=key, model=settings.grounding_tier1_model or model,
        timeout_seconds=settings.agent_router_timeout_seconds, provider=provider,
    )

__all__ = [
    "OPENROUTER_DEFAULT_MODEL", "TYPESAFE_DEFAULT_MODEL", "create_claim_support_checker",
    "create_turn_router",
]
