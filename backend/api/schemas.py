"""Pydantic request/response models for the API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1)
    fixture: str = Field(min_length=1)
    time_limit_s: float = Field(default=60.0, gt=0)


class ScenarioOut(BaseModel):
    id: str
    name: str
    fixture: str
    time_limit_s: float
    created_at: str


class RunOut(BaseModel):
    id: str
    scenario_id: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    solver_status: Optional[str] = None
    error: Optional[str] = None


class InsightOut(BaseModel):
    ready: bool
    run_id: str
    report: Optional[str] = None    # present when ready=True (INS-01)
    status: Optional[str] = None    # present when ready=False (D-07)
    reason: Optional[str] = None    # present when ready=False (D-07)


class ConstraintParseRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)


class AppliedConstraint(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str


class RejectedConstraint(BaseModel):
    tool: str
    error: str


class ConstraintParseResponse(BaseModel):
    applied: list[AppliedConstraint]
    rejected: list[RejectedConstraint]
    clarification_needed: str | None
    no_constraint_found: bool
