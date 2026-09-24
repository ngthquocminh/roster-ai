"""The export-boundary allow-list: what any span may carry out of the process.

Story 5.9, AD-12 (amended 2026-09-24): "Every exported span passes an
export-boundary sanitizer (attribute allow-list, exception type only)". This
module is the policy as production data; `adapters/telemetry/spans.py` applies
it to real OpenTelemetry spans. It imports only the standard library, so the
policy can be read, tested and reviewed without the SDK.

The tables were MEASURED, not written from documentation: a harness drove the
real app, Docker PostgreSQL and the exact dependency pins with Story 5.2's
canaries, and every key observed is classified below. The rule is
default-deny -- a key that is neither allowed nor transformed is dropped, so a
key a future library version adds never leaves the process until a person
decides it should. `KNOWN_DROPPED` records the keys that were seen and
deliberately refused; the drift check in the proof suite fails on any observed
key that is in none of the sets, naming it.

What this does not cover: values of allowed free-form keys
(`gen_ai.tool.definitions`, `db.statement`, `logfire.msg`) are bounded by their
source (application-authored text, placeholder-only SQL, tool names), not by a
schema here. Span names pass through unchanged.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Final
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

HTTP_SERVER: Final = "http_server"
HTTP_CLIENT: Final = "http_client"
DATABASE: Final = "database"
AGENT: Final = "agent"
WORKER: Final = "worker"
OTHER: Final = "other"
CATEGORIES: Final = (HTTP_SERVER, HTTP_CLIENT, DATABASE, AGENT, WORKER, OTHER)

#: Duplicated from `settings.TRACE_CONTENT_SYNTHETIC_EVAL` would break the F1
#: guard's "one literal" rule, so the boundary receives the mode as a value and
#: compares it to the constant passed in by `spans.py`.
CONTENT_MODE_OFF: Final = "off"

#: Instrumentation-scope name -> category. Anything unlisted is `OTHER` and
#: exports with no attributes at all.
SCOPE_CATEGORIES: Final[Mapping[str, str]] = {
    "opentelemetry.instrumentation.fastapi": HTTP_SERVER,
    "opentelemetry.instrumentation.asgi": HTTP_SERVER,
    "opentelemetry.instrumentation.httpx": HTTP_CLIENT,
    "opentelemetry.instrumentation.sqlalchemy": DATABASE,
    "pydantic-ai": AGENT,
    "shiftmind.worker": WORKER,
}

#: Worker span scope name, shared with `spans.py`.
WORKER_SCOPE: Final = "shiftmind.worker"


def categorize(scope_name: str | None) -> str:
    return SCOPE_CATEGORIES.get(scope_name or "", OTHER)


# --- value validators -------------------------------------------------------


def _uuid(value: object) -> object | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _number(value: object) -> object | None:
    # `bool` is an `int` subclass; a flag is not a count.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _closed(vocabulary: frozenset[str]) -> Callable[[object], object | None]:
    def validate(value: object) -> object | None:
        return value if isinstance(value, str) and value in vocabulary else None

    return validate


# --- transforms (value, all raw attributes) -> value | None ----------------

Transform = Callable[[object, Mapping[str, object]], object | None]


def _is_identifier(segment: str) -> bool:
    if segment.isdigit():
        return True
    try:
        UUID(segment)
    except ValueError:
        return False
    return True


def strip_target_query(value: object, attributes: Mapping[str, object]) -> object | None:
    """`http.target`: the path only, and only when it is template + identifiers.

    Cut at the first `?` or `#`, then keep the path only if it lines up with
    `http.route` segment for segment, with every `{param}` filled by a UUID or
    an integer. An unmatched route has no `http.route` (a canary rode its path
    in the measurement), and a MATCHED route is no better on its own: Starlette
    matches `{param}` as `[^/]+` before FastAPI validates the type, so a 401 or
    422 request carries whatever text the client put there (code review
    2026-09-24, observed in hosted Logfire). Anything else drops the key;
    `http.route` still names the template.
    """
    route = attributes.get("http.route")
    if not isinstance(value, str) or not isinstance(route, str) or not route:
        return None
    path = re.split(r"[?#]", value, maxsplit=1)[0]
    template_segments = route.split("/")
    path_segments = path.split("/")
    if len(template_segments) != len(path_segments):
        return None
    for template, segment in zip(template_segments, path_segments):
        if template.startswith("{") and template.endswith("}"):
            if not _is_identifier(segment):
                return None
        elif template != segment:
            return None
    return path


def strip_url_to_origin_and_path(
    value: object, _attributes: Mapping[str, object]
) -> object | None:
    """`http.url` on a client span: `scheme://host[:port]/path` only.

    Query, fragment and userinfo are removed; the host names the provider.
    """
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if not parts.scheme or not host:
        return None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _json(value: object) -> object | None:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


_MESSAGE_PART_KEYS: Final = ("type", "id", "name")


def project_message_structure(
    value: object, _attributes: Mapping[str, object]
) -> object | None:
    """Keep each message's `role` and each part's `type`, `id`, `name` only.

    pydantic-ai promises structure-only messages with content off; this
    projection makes that true by construction. Anything unparseable drops.
    """
    messages = _json(value)
    if not isinstance(messages, list):
        return None
    projected: list[dict[str, object]] = []
    for message in messages:
        if not isinstance(message, dict):
            return None
        item: dict[str, object] = {}
        role = message.get("role")
        if isinstance(role, str):
            item["role"] = role
        parts = message.get("parts")
        if isinstance(parts, list):
            item["parts"] = [
                {
                    key: part[key]
                    for key in _MESSAGE_PART_KEYS
                    if isinstance(part, dict) and isinstance(part.get(key), str)
                }
                for part in parts
            ]
        projected.append(item)
    return json.dumps(projected, separators=(",", ":"))


def remove_instruction_parts(
    value: object, _attributes: Mapping[str, object]
) -> object | None:
    """`model_request_parameters` minus `instruction_parts`.

    Measured: the whole static system prompt rides this key in default mode,
    the one instructions channel pydantic-ai's content switch does not gate.
    """
    parameters = _json(value)
    if not isinstance(parameters, dict):
        return None
    parameters.pop("instruction_parts", None)
    return json.dumps(parameters, separators=(",", ":"))


# --- per-category tables ---------------------------------------------------


class CategoryPolicy:
    """One category's allow-list. Frozen by convention; built once below."""

    def __init__(
        self,
        *,
        allow: frozenset[str] = frozenset(),
        validated: Mapping[str, Callable[[object], object | None]] | None = None,
        validated_prefixes: Mapping[str, Callable[[object], object | None]] | None = None,
        transform: Mapping[str, Transform] | None = None,
        content_mode: frozenset[str] = frozenset(),
        known_dropped: frozenset[str] = frozenset(),
        known_dropped_prefixes: tuple[str, ...] = (),
    ) -> None:
        self.allow = allow
        self.validated = dict(validated or {})
        self.validated_prefixes = dict(validated_prefixes or {})
        self.transform = dict(transform or {})
        self.content_mode = content_mode
        self.known_dropped = known_dropped
        self.known_dropped_prefixes = known_dropped_prefixes

    def classifies(self, key: str) -> bool:
        """True when `key` is decided (allowed, transformed, content or dropped)."""
        return (
            key in self.allow
            or key in self.validated
            or key in self.transform
            or key in self.content_mode
            or key in self.known_dropped
            or key.startswith(tuple(self.validated_prefixes))
            or key.startswith(self.known_dropped_prefixes)
        )


_HEADER_PREFIXES: Final = ("http.request.header.", "http.response.header.")

#: `ScheduleRunStatusV1`, `SolverStatusV1` and `JobTypeV1` as closed
#: vocabularies. Kept stdlib-only here; a test pins them to the contracts.
SCHEDULE_RUN_STATUSES: Final = frozenset({
    "solver_queued", "solver_running", "cancellation_requested", "solver_completed",
    "solver_infeasible", "solver_timed_out", "solver_cancelled", "solver_failed",
})
SOLVER_STATUSES: Final = frozenset({"OPTIMAL", "FEASIBLE", "INFEASIBLE", "MODEL_INVALID", "UNKNOWN"})
JOB_TYPES: Final = frozenset({"schedule_run_execute"})

POLICIES: Final[Mapping[str, CategoryPolicy]] = {
    HTTP_SERVER: CategoryPolicy(
        allow=frozenset({
            "http.method", "http.route", "http.status_code", "http.scheme",
            "http.flavor", "net.host.port",
        }),
        validated={"shiftmind.schedule_run.id": _uuid},
        transform={"http.target": strip_target_query},
        known_dropped=frozenset({
            "http.url", "http.host", "http.server_name", "http.user_agent",
            "net.peer.ip", "net.peer.port", "asgi.event.type",
        }),
        known_dropped_prefixes=_HEADER_PREFIXES,
    ),
    HTTP_CLIENT: CategoryPolicy(
        allow=frozenset({"http.method", "http.status_code"}),
        transform={"http.url": strip_url_to_origin_and_path},
        known_dropped_prefixes=_HEADER_PREFIXES,
    ),
    DATABASE: CategoryPolicy(
        # `db.statement` is placeholder-only by construction; the SQL-literal
        # architecture guard keeps it that way.
        allow=frozenset({"db.system", "db.name", "db.operation", "db.statement"}),
        known_dropped=frozenset({"db.user", "net.peer.name", "net.peer.port"}),
    ),
    AGENT: CategoryPolicy(
        allow=frozenset({
            "gen_ai.operation.name", "gen_ai.agent.name", "agent_name", "model_name",
            "gen_ai.agent.call.id", "gen_ai.conversation.id",
            "gen_ai.provider.name", "gen_ai.system", "gen_ai.request.model",
            "gen_ai.response.model", "gen_ai.response.id", "gen_ai.response.finish_reasons",
            "server.address", "server.port",
            "pydantic_ai.new_message_index", "pydantic_ai.variable_instructions",
            "pydantic_ai.tool.deferral.name",
            "gen_ai.tool.name", "gen_ai.tool.call.id",
            "logfire.msg", "logfire.json_schema", "gen_ai.tool.definitions",
        }),
        validated={
            **{
                f"gen_ai.request.{name}": _number
                for name in (
                    "max_tokens", "top_p", "seed", "temperature",
                    "presence_penalty", "frequency_penalty",
                )
            },
            **{
                f"{family}.{name}": _number
                for family in ("gen_ai.usage", "gen_ai.aggregated_usage")
                for name in (
                    "input_tokens", "output_tokens",
                    "cache_read.input_tokens", "cache_creation.input_tokens",
                )
            },
            "shiftmind.agent_run.id": _uuid,
            "shiftmind.site.id": _uuid,
            "shiftmind.conversation.id": _uuid,
        },
        validated_prefixes={
            "gen_ai.usage.details.": _number,
            "gen_ai.aggregated_usage.details.": _number,
        },
        transform={
            "model_request_parameters": remove_instruction_parts,
            "gen_ai.input.messages": project_message_structure,
            "gen_ai.output.messages": project_message_structure,
            "pydantic_ai.all_messages": project_message_structure,
        },
        content_mode=frozenset({
            "gen_ai.system_instructions", "gen_ai.tool.call.arguments",
            "gen_ai.tool.call.result", "final_result", "pydantic_ai.tool.deferral.metadata",
        }),
        known_dropped=frozenset({
            "gen_ai.agent.description", "metadata", "tool_arguments", "tool_response",
        }),
    ),
    WORKER: CategoryPolicy(
        validated={
            "shiftmind.schedule_run.id": _uuid,
            "shiftmind.job.id": _uuid,
            "shiftmind.site.id": _uuid,
            "shiftmind.job.type": _closed(JOB_TYPES),
            "shiftmind.schedule_run.status": _closed(SCHEDULE_RUN_STATUSES),
            "shiftmind.job.queue_age_s": _number,
            "shiftmind.solver.status": _closed(SOLVER_STATUSES),
            "shiftmind.solver.wall_time_s": _number,
        },
    ),
    OTHER: CategoryPolicy(),
}

#: The agent category's full exportable key set in default mode, for Story
#: 5.2's proof suite (which used to declare its own copy as a test constant).
AGENT_DEFAULT_ALLOW_LIST: Final = frozenset(
    POLICIES[AGENT].allow | set(POLICIES[AGENT].validated) | set(POLICIES[AGENT].transform)
)
AGENT_CONTENT_MODE_KEYS: Final = POLICIES[AGENT].content_mode


def sanitize_attributes(
    category: str,
    attributes: Mapping[str, object],
    *,
    content_mode: str,
    content_mode_on: str,
) -> dict[str, object]:
    """Default-deny projection of one span's attributes.

    `content_mode_on` is the single literal that enables content keys (passed in
    from `settings.TRACE_CONTENT_SYNTHETIC_EVAL`); any other mode is `off`.
    """
    policy = POLICIES.get(category, POLICIES[OTHER])
    content = content_mode == content_mode_on
    kept: dict[str, object] = {}
    for key, value in attributes.items():
        result: object | None
        if key in policy.allow:
            result = value
        elif key in policy.validated:
            result = policy.validated[key](value)
        elif (prefix := next(
            (p for p in policy.validated_prefixes if key.startswith(p)), None
        )) is not None:
            result = policy.validated_prefixes[prefix](value)
        elif key in policy.transform:
            # Content mode exports the AGENT's messages as emitted; every other
            # category's transforms apply in both modes.
            result = (
                value
                if content and category == AGENT
                else policy.transform[key](value, attributes)
            )
        elif key in policy.content_mode:
            result = value if content else None
        else:
            result = None
        if result is not None:
            kept[key] = result
    return kept


EXCEPTION_EVENT: Final = "exception"
EXCEPTION_TYPE_KEY: Final = "exception.type"


def sanitize_event(
    name: str, attributes: Mapping[str, object]
) -> tuple[str, dict[str, object]] | None:
    """`exception` keeps `exception.type` only; every other event is dropped.

    Both content modes: `exception.message` carried the provider-error canary
    on agent spans and route exception text on the HTTP server span.
    """
    if name != EXCEPTION_EVENT:
        return None
    exception_type = attributes.get(EXCEPTION_TYPE_KEY)
    kept = {EXCEPTION_TYPE_KEY: exception_type} if isinstance(exception_type, str) else {}
    return EXCEPTION_EVENT, kept


RESOURCE_ALLOW: Final = frozenset({
    "service.name", "service.version", "service.instance.id",
    "telemetry.sdk.language", "telemetry.sdk.name", "telemetry.sdk.version",
})
DEPLOYMENT_ENVIRONMENT_KEY: Final = "deployment.environment"
LIVE_EVAL_ENVIRONMENT: Final = "live-eval"


def sanitize_resource(
    attributes: Mapping[str, object], *, content_mode: str, content_mode_on: str
) -> dict[str, object]:
    kept = {key: value for key, value in attributes.items() if key in RESOURCE_ALLOW}
    if (
        content_mode == content_mode_on
        and attributes.get(DEPLOYMENT_ENVIRONMENT_KEY) == LIVE_EVAL_ENVIRONMENT
    ):
        kept[DEPLOYMENT_ENVIRONMENT_KEY] = LIVE_EVAL_ENVIRONMENT
    return kept


def unclassified_keys(category: str, keys: object) -> set[str]:
    """Observed raw keys that no table decides -- the drift check's input."""
    policy = POLICIES.get(category, POLICIES[OTHER])
    return {key for key in keys if isinstance(key, str) and not policy.classifies(key)}  # type: ignore[union-attr]


__all__ = [
    "AGENT",
    "AGENT_CONTENT_MODE_KEYS",
    "AGENT_DEFAULT_ALLOW_LIST",
    "CATEGORIES",
    "CONTENT_MODE_OFF",
    "DATABASE",
    "HTTP_CLIENT",
    "HTTP_SERVER",
    "OTHER",
    "POLICIES",
    "RESOURCE_ALLOW",
    "WORKER",
    "WORKER_SCOPE",
    "categorize",
    "project_message_structure",
    "remove_instruction_parts",
    "sanitize_attributes",
    "sanitize_event",
    "sanitize_resource",
    "strip_target_query",
    "strip_url_to_origin_and_path",
    "unclassified_keys",
]
