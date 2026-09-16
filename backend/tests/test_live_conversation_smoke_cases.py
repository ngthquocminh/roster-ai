from application.capabilities.installed import installed_modules
from evals.live_conversations.smoke_cases import COMMAND_TOOL_SMOKES, CONVERSATION_TOOL_SMOKES


def test_every_agent_invocable_capability_has_a_two_turn_smoke_case():
    assert all(case.first_turn == 'Hi' and case.second_turn for case in CONVERSATION_TOOL_SMOKES)
    assert len({case.id for case in CONVERSATION_TOOL_SMOKES}) == len(CONVERSATION_TOOL_SMOKES)
    assert {case.capability for case in CONVERSATION_TOOL_SMOKES} == {
        'scheduling_inspect', 'scheduling_compute', 'scheduling_draft',
        'scheduling_baseline', 'shiftmind_demonstration',
    }


def test_every_installed_capability_has_exactly_one_smoke_plane():
    conversational = {case.capability for case in CONVERSATION_TOOL_SMOKES}
    commanded = {case.capability for case in COMMAND_TOOL_SMOKES}
    installed = {module.manifest.capability_name for module in installed_modules()}
    assert conversational.isdisjoint(commanded)
    assert conversational | commanded == installed


def test_optimization_smoke_cannot_masquerade_as_an_llm_tool_call():
    assert [(case.capability, case.command) for case in COMMAND_TOOL_SMOKES] == [
        ('scheduling_optimize', 'POST /api/v1/schedule-runs')]
