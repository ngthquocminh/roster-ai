import pytest

from evals.live_conversations.inventory import capability_inventory, require_complete_coverage


def report():
    inventory = capability_inventory()
    return {'inventory_digest': inventory['digest'], 'tool_coverage': [
        {'source': 'capability', 'operation': operation, 'observation_id': 'observed-1',
         'state': 'gap', 'reason': 'A recorded test attempt found no supported path.'}
        for operation in inventory['live_required_operations']
    ] + [
        {'source': 'deterministic', 'operation': operation,
         'reason': 'Covered by the offline backend suite; unreachable from a planner turn.'}
        for operation in inventory['deterministic_operations']
    ]}


def test_inventory_contains_installed_tools_request_variants_and_actual_query_keys():
    inventory = capability_inventory()
    assert len(inventory['modules']) == 6
    assert 'scheduling_inspect:workers:filter=qualified_task_id' in inventory['operations']
    assert any('qualified_worker_count' in key for key in inventory['operations'])
    assert any('set_max_hours' in key for key in inventory['operations'])
    assert 'shiftmind_demonstration:invoke' in inventory['operations']
    require_complete_coverage(report(), observation_ids={'observed-1'})


def test_chat_unreachable_operations_must_still_cite_deterministic_proof():
    """Minh's 2026-09-18 scope decision: query keys, paging/invalid-query paths
    and manifest error codes are proved offline, but they may not simply vanish
    from the denominator."""
    inventory = capability_inventory()
    assert len(inventory['live_required_operations']) + len(
        inventory['deterministic_operations']) == len(inventory['operations'])
    assert 'scheduling_inspect:workers:filter=qualified_task_id' in inventory[
        'deterministic_operations']
    assert 'scheduling_compute:request.properties.metric=staffed_minutes' in inventory[
        'live_required_operations']

    value = report()
    value['tool_coverage'] = [row for row in value['tool_coverage']
                              if row['source'] != 'deterministic']
    with pytest.raises(ValueError, match='neither live nor deterministic'):
        require_complete_coverage(value, observation_ids={'observed-1'})

    value = report()
    for row in value['tool_coverage']:
        if row['source'] == 'deterministic':
            row.pop('reason')
    with pytest.raises(ValueError, match='cite its proof'):
        require_complete_coverage(value, observation_ids={'observed-1'})


def test_dropping_coverage_of_a_real_operation_fails():
    value = report()
    value['tool_coverage'] = [row for row in value['tool_coverage']
                              if 'qualified_worker_count' not in row['operation']]
    with pytest.raises(ValueError, match='uncovered operations'):
        require_complete_coverage(value, observation_ids={'observed-1'})


def test_api_commands_cannot_replace_llm_tool_coverage():
    value = report()
    value['tool_coverage'][0]['source'] = 'application_command'
    with pytest.raises(ValueError, match='uncovered operations'):
        require_complete_coverage(value, observation_ids={'observed-1'})


def test_stale_inventory_and_fabricated_observation_are_rejected():
    value = report()
    value['inventory_digest'] = 'stale'
    with pytest.raises(ValueError, match='changed or is unbound'):
        require_complete_coverage(value, observation_ids={'observed-1'})
    with pytest.raises(ValueError, match='no recorded observation'):
        require_complete_coverage(report(), observation_ids=set())
