"""Minimal live routing gate before any paid multi-turn conversation matrix."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ConversationToolSmokeCase:
    id: str
    capability: str
    second_turn: str
    precondition: Literal['baseline', 'candidate', 'demonstration_enabled']
    expected_activity: Literal['agent_response', 'draft', 'approval_request']
    first_turn: str = 'Hi'


CONVERSATION_TOOL_SMOKES = (
    ConversationToolSmokeCase(
        id='inspect-constraints', capability='scheduling_inspect', precondition='baseline',
        second_turn='Show me the current scheduling constraints.',
        expected_activity='agent_response'),
    ConversationToolSmokeCase(
        id='compute-worker-count', capability='scheduling_compute', precondition='baseline',
        second_turn='How many workers are in this scenario?', expected_activity='agent_response'),
    ConversationToolSmokeCase(
        id='draft-max-hours', capability='scheduling_draft', precondition='baseline',
        second_turn='Create a draft capping Mika Tane at 40 hours.', expected_activity='draft'),
    ConversationToolSmokeCase(
        id='baseline-proposal', capability='scheduling_baseline', precondition='candidate',
        second_turn='Propose the completed candidate as the new baseline for my approval.',
        expected_activity='approval_request'),
    ConversationToolSmokeCase(
        id='demonstration-once', capability='shiftmind_demonstration',
        precondition='demonstration_enabled',
        second_turn='Use the demonstration feature to repeat “ready” once.',
        expected_activity='agent_response'),
)


@dataclass(frozen=True)
class CommandToolSmokeCase:
    id: str
    capability: str
    precondition: str
    command: str


# AD-5 deliberately withholds this compute-risk capability from ordinary chat.
# It is exercised through the authenticated command plane after draft review.
COMMAND_TOOL_SMOKES = (
    CommandToolSmokeCase(
        id='optimize-reviewed-draft', capability='scheduling_optimize',
        precondition='active_reviewed_draft', command='POST /api/v1/schedule-runs'),
)
