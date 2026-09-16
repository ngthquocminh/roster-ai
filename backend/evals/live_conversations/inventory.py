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
    body = {'schema_version': '1', 'modules': modules, 'operations': operations}
    body['digest'] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return body


def require_complete_coverage(report: dict, *, observation_ids: set[str]):
    current = capability_inventory()
    if report.get('inventory_digest') != current['digest']:
        raise ValueError('capability inventory changed or is unbound')
    rows = report.get('tool_coverage', [])
    covered = set()
    for row in rows:
        # Application commands and UI actions cannot masquerade as tool executions.
        if row.get('source') != 'capability':
            continue
        if not row.get('observation_id') or row['observation_id'] not in observation_ids:
            raise ValueError('tool coverage has no recorded observation')
        if row.get('state') not in ('success', 'failure', 'gap'):
            raise ValueError('tool coverage must record a result or explicit gap')
        if row.get('state') == 'gap' and not row.get('reason'):
            raise ValueError('coverage gap requires an explanation')
        covered.add(row['operation'])
    missing = sorted(set(current['operations']) - covered)
    if missing:
        raise ValueError('uncovered operations: ' + ', '.join(missing))
    return current
