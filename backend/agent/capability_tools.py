"""Render application-granted capability declarations into framework tools.

This is the ONLY place a granted declaration becomes a `pydantic_ai` tool. The
authority decision has already been made by `application/capabilities/registry`
before this module runs (AD-2/Decision 4): everything here registers what it is
handed and never decides what may be registered.

`RunContext` and every other framework type stay inside this package —
`application/**` may not import `pydantic_ai` at all, so the wrapper unpacks
`ctx.deps` and calls the application handler with plain typed values.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from pydantic_ai import Agent, ModelRetry, RunContext

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_inspect import (
    CAPABILITY_NAME as SCHEDULING_INSPECT,
    InspectCapabilityManifest,
    SchedulingInspectError,
    SchedulingInspectRequestV1,
    scheduling_inspect as run_scheduling_inspect,
)


class UnknownCapabilityError(ValueError):
    """A granted declaration this adapter has no renderer for.

    Raised rather than skipped: silently dropping a granted capability would
    make `registered_capability_names` over-report, and Story 2.6's add/remove
    conformance proof composes against exactly this seam.
    """


# Model-facing errors the model may usefully retry by correcting its own
# arguments. Everything else is an application failure the model cannot fix.
_RETRYABLE_CODES = frozenset({"invalid_query"})


def _register_scheduling_inspect(
    agent: Agent, manifest: InspectCapabilityManifest
) -> None:
    @agent.tool(name=manifest.capability_name)
    def scheduling_inspect_tool(
        ctx: RunContext[AgentDepsV1 | None],
        request: SchedulingInspectRequestV1,
    ) -> dict[str, object]:
        if ctx.deps is None:
            raise RuntimeError("trusted agent dependencies are unavailable")
        try:
            return asdict(run_scheduling_inspect(ctx.deps, request, manifest))
        except SchedulingInspectError as exc:
            if exc.code in _RETRYABLE_CODES:
                # Hand the model a correctable error so it can fix its own
                # arguments. `ModelRetry` is a framework type and may only be
                # raised here, never in `application/**`.
                raise ModelRetry(f"{exc.code}: {exc}") from exc
            raise


_RENDERERS: dict[str, Callable[[Agent, InspectCapabilityManifest], None]] = {
    SCHEDULING_INSPECT: _register_scheduling_inspect,
}


def render_capabilities(
    agent: Agent,
    capabilities: tuple[InspectCapabilityManifest, ...],
    deps: AgentDepsV1 | None,
) -> tuple[str, ...]:
    """Register every granted capability and report what was actually registered.

    The returned names are collected as each tool is registered, so they reflect
    the agent's real tool set rather than mirroring the input argument.
    """
    registered: list[str] = []
    for capability in capabilities:
        name = capability.capability_name
        renderer = _RENDERERS.get(name)
        if renderer is None:
            raise UnknownCapabilityError(
                f"no tool renderer for granted capability {name!r}; "
                f"known: {', '.join(sorted(_RENDERERS)) or 'none'}"
            )
        if name in registered:
            raise UnknownCapabilityError(
                f"capability {name!r} was granted more than once"
            )
        if deps is None:
            raise ValueError(f"{name} requires trusted AgentDepsV1")
        renderer(agent, capability)
        registered.append(name)
    return tuple(registered)


__all__ = ["UnknownCapabilityError", "render_capabilities"]
