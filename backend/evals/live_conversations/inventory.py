"""Fresh source-derived tool/operation denominator; availability never removes rows."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from pydantic import TypeAdapter

from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
from application.capabilities.installed import installed_modules


def _enum_rows(value, path='request'):
    if isinstance(value, dict):
        for member in value.get('enum', ()):
            yield path + '=' + str(member)
        for key, child in value.items():
            if key != 'enum':
                yield from _enum_rows(child, path + '.' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _enum_rows(child, path + '.' + str(index))


def capability_inventory():
    modules = []
    operations = []
    reader = PostgresScenarioProjectionReader()
    for module in installed_modules():
        name = module.manifest.capability_name
        schema = TypeAdapter(module.request_type).json_schema()
        descriptor = {
            'manifest': asdict(module.manifest), 'request_schema': schema,
            'required_role': module.required_role, 'feature_policy': module.required_feature_policy,
            'model_description': module.model_description,
        }
        modules.append(descriptor)
        operations.append(name + ':invoke')
        operations.extend(name + ':' + operation for operation in _enum_rows(schema))
        operations.extend(name + ':error=' + code for code in module.manifest.errors)
        if name == 'scheduling_inspect':
            for group in schema['properties']['group']['enum']:
                keys = reader.get_query_keys(group)
                descriptor.setdefault('query_keys', {})[group] = asdict(keys)
                operations.extend(f'{name}:{group}:filter={key}' for key in keys.filter_keys)
                operations.extend(f'{name}:{group}:sort={key}' for key in keys.sort_keys)
                if group != 'overview':
                    operations.extend(f'{name}:{group}:{operation}'
                                      for operation in ('pagination', 'empty', 'invalid_query'))
    operations = sorted(set(operations))
    body = {'schema_version': '2', 'modules': modules, 'operations': operations,
            'live_required_operations': sorted(o for o in operations if _is_chat_reachable(o)),
            'deterministic_operations': sorted(o for o in operations if not _is_chat_reachable(o))}
    body['digest'] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return body


#: Operation shapes a planner conversation cannot address on its own: query keys,
#: paging/empty/invalid-query paths and manifest error codes (several, such as
#: site_mismatch, are unreachable through a legitimate grant by design). They are
#: covered by the deterministic backend suite and recorded as such, per Minh's
#: 2026-09-18 scope decision after the three-scenario right-sizing.
_DETERMINISTIC_MARKERS = (':filter=', ':sort=', ':error=', ':pagination', ':empty',
                          ':invalid_query', ':request.properties.order=')


def chat_grantable_names() -> frozenset[str]:
    """Capabilities a PLANNER TURN can address, from the real grant composition.

    `scheduling_optimize` is compute-risk, so an ordinary turn never receives it
    (registry.py: the module is absent, not present-and-denied). Its operations
    are therefore not chat-reachable however the scenarios are written.
    """
    from uuid import uuid4

    from application.capabilities.registry import (
        CapabilityGrantContextV1, PLANNER_ROLE, compose_granted_capabilities,
    )

    site = uuid4()
    context = CapabilityGrantContextV1(
        role=PLANNER_ROLE, site_id=site,
        feature_policy=frozenset(module.required_feature_policy for module in installed_modules()),
        conversation_id=uuid4(), conversation_site_id=site,
    )
    return frozenset(module.manifest.capability_name
                     for module in compose_granted_capabilities(context))


def _is_chat_reachable(operation: str) -> bool:
    if any(marker in operation for marker in _DETERMINISTIC_MARKERS):
        return False
    return operation.split(':', 1)[0] in chat_grantable_names()


def require_complete_coverage(report: dict, *, observation_ids: set[str]):
    current = capability_inventory()
    if report.get('inventory_digest') != current['digest']:
        raise ValueError('capability inventory changed or is unbound')
    rows = report.get('tool_coverage', [])
    covered = set()
    deterministic = set()
    for row in rows:
        # Application commands and UI actions cannot masquerade as tool executions.
        if row.get('source') == 'deterministic':
            # A chat-unreachable operation proved by the offline suite. It must
            # still name where, so the claim is checkable.
            if not row.get('reason'):
                raise ValueError('a deterministic coverage row must cite its proof')
            deterministic.add(row['operation'])
            continue
        # 'capability' is a telemetry record of the call; 'effect' is an
        # independently read application effect proving the exact operation (a
        # supported claim's metric, a persisted draft's constraint kind). Both
        # are live evidence and must name an observation; anything else is not.
        if row.get('source') not in ('capability', 'effect'):
            continue
        if not row.get('observation_id') or row['observation_id'] not in observation_ids:
            raise ValueError('tool coverage has no recorded observation')
        if row.get('state') not in ('success', 'failure', 'gap'):
            raise ValueError('tool coverage must record a result or explicit gap')
        if row.get('state') == 'gap' and not row.get('reason'):
            raise ValueError('coverage gap requires an explanation')
        covered.add(row['operation'])
    # A chat-reachable operation is normally proved live, but one no authored
    # turn can legitimately reach (a draft group resolve_constraints rejects)
    # may instead cite deterministic proof, exactly like the offline bucket.
    missing = sorted(set(current['live_required_operations']) - covered - deterministic)
    if missing:
        raise ValueError('uncovered operations: ' + ', '.join(missing))
    unproven = sorted(set(current['deterministic_operations']) - deterministic)
    if unproven:
        raise ValueError('operations with neither live nor deterministic coverage: '
                         + ', '.join(unproven))
    return current
