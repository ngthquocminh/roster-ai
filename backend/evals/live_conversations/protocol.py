"""Fail-closed budgets and semantic verdicts for real conversation evaluation."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evals.report import LiveSuiteBudgetV1


class IncompleteConversationRun(RuntimeError):
    """A missing resource or verification is never a passing evaluation."""


@dataclass
class ConversationBudget:
    limits: LiveSuiteBudgetV1
    prior_spend_usd: float = 0.0
    started: float = field(default_factory=monotonic)
    requests: int = 0
    tool_calls: int = 0
    tokens: int = 0
    executions: int = 0
    spend_usd: float = 0.0

    def __post_init__(self):
        if (type(self.prior_spend_usd) not in (int, float)
                or not math.isfinite(self.prior_spend_usd) or self.prior_spend_usd < 0):
            raise ValueError('prior spend must be nonnegative and finite')

    def admit(self, *, reserve_usd: float, requests: int = 1, tokens: int = 0):
        if type(reserve_usd) not in (int, float) or not math.isfinite(reserve_usd) or reserve_usd <= 0:
            raise ValueError('a positive finite per-call cost reservation is required')
        if any(type(value) is not int or value < 0 for value in (requests, tokens)):
            raise ValueError('reservations must be nonnegative integer counters')
        if (
            self.prior_spend_usd + self.spend_usd + reserve_usd > self.limits.spend_usd_limit
            or self.requests + requests > self.limits.request_limit
            or self.tokens + tokens > self.limits.token_limit
            or self.tool_calls >= self.limits.tool_call_limit
            or monotonic() - self.started >= self.limits.elapsed_seconds_limit
        ):
            raise IncompleteConversationRun('aggregate_budget_exhausted')

    def begin_execution(self):
        if self.executions >= self.limits.case_limit:
            raise IncompleteConversationRun('case_budget_exhausted')
        self.executions += 1

    def charge(self, *, requests: int, tool_calls: int, tokens: int, cost_usd: float):
        if any(type(value) is not int or value < 0 for value in (requests, tool_calls, tokens)):
            raise IncompleteConversationRun('usage_unavailable')
        if type(cost_usd) not in (int, float) or not math.isfinite(cost_usd) or cost_usd < 0:
            raise IncompleteConversationRun('cost_unavailable')
        self.requests += requests
        self.tool_calls += tool_calls
        self.tokens += tokens
        self.spend_usd += cost_usd
        self.check_complete()

    def check_complete(self):
        """Check the last call too, retaining actual usage even on exhaustion."""
        if (
            self.prior_spend_usd + self.spend_usd > self.limits.spend_usd_limit
            or self.requests > self.limits.request_limit
            or self.tokens > self.limits.token_limit
            or self.tool_calls > self.limits.tool_call_limit
            or monotonic() - self.started >= self.limits.elapsed_seconds_limit
        ):
            raise IncompleteConversationRun('aggregate_budget_exhausted')


class DimensionGrade(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    score: Literal[0, 1, 2] | None
    evidence_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


class ConversationJudgment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    relevance: DimensionGrade
    continuity: DimensionGrade
    completeness: DimensionGrade
    clarification_refusal: DimensionGrade
    verdict: Literal['pass', 'fail', 'uncertain']

    def passes(self, *, known_ids: set[str], not_applicable: frozenset[str] = frozenset()) -> bool:
        if self.verdict != 'pass':
            return False
        for name in ('relevance', 'continuity', 'completeness', 'clarification_refusal'):
            grade = getattr(self, name)
            if not set(grade.evidence_ids) <= known_ids:
                return False
            if grade.score is None:
                if name not in not_applicable:
                    return False
            elif grade.score != 2:
                return False
        return True


def turn_verdict(*, factual_failures: list[str], judgment: ConversationJudgment | None,
                 known_ids: set[str], not_applicable: frozenset[str] = frozenset()) -> str:
    if factual_failures:
        return 'fail'
    if judgment is None:
        return 'incomplete'
    if judgment.verdict == 'uncertain':
        return 'needs_review'
    return 'pass' if judgment.passes(known_ids=known_ids, not_applicable=not_applicable) else 'fail'
