"""Shared owned adapter-status vocabulary without contract import cycles."""
from typing import Literal

AgentRunStatusV1 = Literal[
    "completed",
    "suspended",
    "timed_out",
    "failed",
]

__all__ = ["AgentRunStatusV1"]
