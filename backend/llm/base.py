"""LLMProvider seam — the swap point for language-model backends.

Mirror of engine/base.py: Protocol + factory with lazy imports. The Protocol
returns provider-neutral list[OverrideCall]; no vendor-specific payload crosses
this boundary (D-08). A real (network-backed) provider is registered behind
this factory in a later plan; only the stub is registered here so far.
"""
from __future__ import annotations

from typing import Protocol

from domain.overrides import OverrideCall


class LLMProvider(Protocol):
    def parse_constraints(self, text: str) -> list[OverrideCall]: ...
    def generate_insights(self, summary: dict) -> str: ...   # D-09 second operation

    @property
    def name(self) -> str: ...


def create_provider(name: str, *, settings=None) -> LLMProvider:
    """Registry of available LLM providers. Add a backend here to make it swappable."""
    if name == "stub":
        from llm.stub import StubLLMProvider
        return StubLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}. Available: ['stub']")
