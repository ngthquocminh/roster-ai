"""Render already-granted application modules through one generic tool path.

The authority decision has already been made before anything here runs: this
adapter registers exactly the modules it is handed and never decides what may be
registered (AD-2). Framework types -- `Agent`, `RunContext`, `Tool`,
`ModelRetry`, `ApprovalRequired` -- are confined to this package and must never
appear in `application/**`.

There is ONE registration path for every module. Anything that would need a
per-capability branch here belongs on the module's declaration instead.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace

from pydantic import TypeAdapter
from pydantic_ai import Agent, ApprovalRequired, ModelRetry, RunContext, Tool

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1, validate_module
from application.contracts.capability_manifest import CapabilityApprovalRequired


class UnknownCapabilityError(ValueError):
    """The granted set contains the same tool name more than once."""


def _render_result(value: object, text_field: str | None) -> object:
    """Render a handler result for the model.

    `text_field` is DECLARED by the module. The adapter never inspects the
    result's shape to decide -- guessing by field set would be a per-capability
    branch wearing a structural disguise, and would silently downgrade any
    future module whose result happened to match.
    """
    if not is_dataclass(value) or isinstance(value, type):
        return value
    if text_field is not None:
        return getattr(value, text_field)
    return asdict(value)


def _tool_schema(module: CapabilityModuleV1) -> dict[str, object]:
    """Wrap the request schema, hoisting `$defs` to the document root.

    Pydantic emits `$defs` at the root of the schema it generates and refers to
    them with document-root-relative `$ref`s. Embedding that schema as a
    sub-schema without hoisting leaves every `$ref` of a nested model or enum
    dangling -- which fails at the provider rather than at registration.
    """
    request_schema = dict(TypeAdapter(module.request_type).json_schema())
    definitions = request_schema.pop("$defs", None)
    schema: dict[str, object] = {
        "type": "object",
        "properties": {module.request_argument: request_schema},
        "required": [module.request_argument],
        "additionalProperties": False,
    }
    if definitions:
        schema["$defs"] = definitions
    return schema


def _register_module(
    agent: Agent, module: CapabilityModuleV1, deps: AgentDepsV1 | None
) -> None:
    name = module.manifest.capability_name
    if deps is None:
        raise ValueError(f"{name} requires trusted AgentDepsV1")

    validate_module(module)
    request_adapter = TypeAdapter(module.request_type)
    request_argument = module.request_argument
    declares_approval = module.manifest.approval_policy != "none"

    def execute(ctx: RunContext[AgentDepsV1 | None], **kwargs: object) -> object:
        if ctx.deps is None:
            raise RuntimeError("trusted agent dependencies are unavailable")
        if request_argument not in kwargs:
            # `Tool.from_schema`'s default validator does not enforce the
            # `required` the schema advertises, so a model that flattens the
            # arguments reaches here. That is a mistake the model can correct.
            raise ModelRetry(
                f"missing required argument {request_argument!r} for {name}"
            )
        request = request_adapter.validate_python(kwargs[request_argument])
        # Per-call approval state, so the handler can refuse before acting.
        call_deps = replace(ctx.deps, tool_call_approved=bool(ctx.tool_call_approved))
        try:
            result = module.handler(call_deps, request, module.manifest)
        except CapabilityApprovalRequired as exc:
            if not declares_approval:
                # A module whose manifest declares `approval_policy="none"` must
                # not be able to suspend a run; otherwise the declaration is
                # decorative rather than enforced.
                raise RuntimeError(
                    f"{name} signalled approval but declares approval_policy='none'"
                ) from exc
            raise ApprovalRequired from exc
        except module.error_type as exc:
            if exc.code in module.retryable_error_codes:
                raise ModelRetry(f"{exc.code}: {exc}") from exc
            raise
        return _render_result(result, module.model_facing_text_field)

    tool = Tool.from_schema(
        execute,
        name=name,
        description=f"Governed {name} capability",
        json_schema=_tool_schema(module),
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
