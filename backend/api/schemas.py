"""Pydantic request/response models for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="after")
    def check_ready_fields(self) -> "InsightOut":
        if self.ready and self.report is None:
            raise ValueError("report must be set when ready=True")
        if not self.ready and self.status is None:
            raise ValueError("status must be set when ready=False")
        return self


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


class OverrideOut(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str | None = None  # None for pre-D-02 legacy entries


class ProblemDetailsV1(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str


class AuthSessionOut(BaseModel):
    app_user_id: UUID
    site_id: UUID
    csrf_token: str
    expires_at: datetime


class FixtureCatalogueEntryOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    fixture_id: str
    scenario_name: str
    scenario_version_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    imported_at: datetime
    site_id: UUID


class ScenarioContextOut(BaseModel):
    schema_version: str = "v1"
    scenario_name: str
    scenario_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    site_id: UUID
    baseline_schedule_version: str | None
