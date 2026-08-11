"""Authoritative AD-5 capability risk vocabulary."""
from typing import Literal

RiskClassV1 = Literal[
    "inspect", "draft", "compute", "consequential", "prohibited"
]

__all__ = ["RiskClassV1"]
