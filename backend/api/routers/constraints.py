"""Constraint parsing: NL text -> validated override stored on a scenario.

POST /constraints receives a scenario_id and free-text constraint description,
delegates to constraint_service to parse, validate, and persist, then returns
200 echoing the stored override. No solve is triggered here (D-06). The route is
top-level /constraints with scenario_id in the body (D-07).
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_llm_provider, get_settings
from api.schemas import ConstraintParseRequest, ConstraintParseResponse
from llm.base import LLMProvider
from services import constraint_service
from settings import Settings

router = APIRouter(prefix="/constraints", tags=["constraints"])


@router.post(
    "",
    response_model=ConstraintParseResponse,
    responses={
        404: {"description": "Scenario not found"},
        400: {"description": "Constraint validation error (unknown/ambiguous task, n<=0, no match)"},
    },
)
def parse_constraint(
    body: ConstraintParseRequest,
    conn: sqlite3.Connection = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return constraint_service.parse_and_store(
            conn,
            provider,
            body.scenario_id,
            body.text,
            data_dir=settings.data_dir,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
