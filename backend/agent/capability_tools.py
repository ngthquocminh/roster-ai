"""Render already-granted application modules through one generic tool path."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from inspect import signature

from pydantic import TypeAdapter
from pydantic_ai import Agent, ApprovalRequired, ModelRetry, RunContext, Tool

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityApprovalRequired


class UnknownCapabilityError(ValueError):
    """The granted set contains the same tool name more than once."""


def _render_result(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        rendered = asdict(value)
        if set(rendered) == {"text", "schema_version"}:
            return rendered["text"]
        return rendered
    return value


def _register_module(
    agent: Agent, module: CapabilityModuleV1, deps: AgentDepsV1 | None
) -> None:
    name = module.manifest.capability_name
    if deps is None:
        raise ValueError(f"{name} requires trusted AgentDepsV1")

    request_adapter = TypeAdapter(module.request_type)
    handler_parameters = tuple(signature(module.handler).parameters)
    request_argument = handler_parameters[1]
    request_schema = request_adapter.json_schema()
    tool_schema = {
        "type": "object",
        "properties": {request_argument: request_schema},
        "required": [request_argument],
        "additionalProperties": False,
    }

    def execute(ctx: RunContext[AgentDepsV1 | None], **kwargs: object) -> object:
        if ctx.deps is None:
            raise RuntimeError("trusted agent dependencies are unavailable")
        request = request_adapter.validate_python(kwargs[request_argument])
        try:
            return _render_result(module.handler(ctx.deps, request, module.manifest))
        except CapabilityApprovalRequired as exc:
            if not ctx.tool_call_approved:
                raise ApprovalRequired from exc
            return _render_result(exc.approved_result)
        except module.error_type as exc:
            if exc.code in module.retryable_error_codes:
                raise ModelRetry(f"{exc.code}: {exc}") from exc
            raise

    tool = Tool.from_schema(
        execute,
        name=name,
        description=f"Governed {name} capability",
        json_schema=tool_schema,
        takes_ctx=True,
    )
    agent._function_toolset.add_tool(tool)


def render_capabilities(
    agent: Agent,
    capabilities: tuple[CapabilityModuleV1, ...],
    deps: AgentDepsV1 | None,
) -> tuple[str, ...]:
    registered: list[str] = []
    for module in capabilities:
        name = module.manifest.capability_name
        if name in registered:
            raise UnknownCapabilityError(f"capability {name!r} was granted more than once")
        _register_module(agent, module, deps)
        registered.append(name)
    return tuple(registered)


__all__ = ["UnknownCapabilityError", "render_capabilities"]
