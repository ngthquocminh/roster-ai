"""TypeSafe Jev claim-support checker (G' phase 3).

One adapter for two endpoints that take the same body (`model`, `state`,
`questions`) and return `answers[id].noul`: TypeSafe's own System One API and
OpenRouter's Decisions API. Each fact is one `noul` question; its state holds
only the fact's own text and its own verbalised record.

Never raises: a timeout, HTTP error or malformed response becomes a closed
error code on the result, and the caller leaves the grounded response alone.
"""
from __future__ import annotations

import json
from time import perf_counter

import httpx

from application.ports.claim_support import ClaimSupportItemV1, ClaimSupportResultV1

TYPESAFE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
OPENROUTER_DECISIONS_ENDPOINT = "https://openrouter.ai/api/v1/api/alpha/decisions"

#: Estimated tokens for a question's own instructions and criteria.
_QUESTION_OVERHEAD_TOKENS = 80
_CRITERIA = {
    "true": "the record states everything the claim asserts",
    "false": "the record contradicts the claim, or does not state part of it",
}


def _estimated_tokens(item: ClaimSupportItemV1) -> int:
    return (len(item.claim_text) + len(item.evidence_text)) // 4 + _QUESTION_OVERHEAD_TOKENS


def _batches(
    items: tuple[ClaimSupportItemV1, ...], budget: int
) -> tuple[list[list[ClaimSupportItemV1]], int]:
    """Greedy split under the token budget; an item alone over it is skipped."""
    batches: list[list[ClaimSupportItemV1]] = []
    current: list[ClaimSupportItemV1] = []
    used = skipped = 0
    for item in items:
        cost = _estimated_tokens(item)
        if cost > budget:
            skipped += 1
            continue
        if current and used + cost > budget:
            batches.append(current)
            current, used = [], 0
        current.append(item)
        used += cost
    if current:
        batches.append(current)
    return batches, skipped


def _payload(model: str, batch: list[ClaimSupportItemV1]) -> dict:
    questions = {}
    facts = {}
    for index, item in enumerate(batch):
        key = f"f{index}"
        facts[key] = {"claim": item.claim_text, "record": item.evidence_text}
        questions[item.item_id] = {
            "type": "noul",
            "instructions": (
                f"Is the claim in `facts.{key}.claim` fully supported by the record in "
                f"`facts.{key}.record`? Judge only against that record."
            ),
            "criteria": _CRITERIA,
        }
    return {"model": model, "state": {"facts": facts}, "questions": questions}


class JevClaimSupportChecker:
    def __init__(
        self, *, endpoint: str, api_key: str, model: str, timeout_seconds: float,
        token_budget: int, provider: str = "typesafe", client: httpx.Client | None = None,
    ) -> None:
        self.name = f"jev:{model}"
        self.provider = provider
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._budget = token_budget
        self._client = client

    def _post(self, body: dict) -> dict:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._client is not None:
            response = self._client.post(
                self._endpoint, json=body, headers=headers, timeout=self._timeout)
        else:
            response = httpx.post(self._endpoint, json=body, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def _batch(self, batch: list[ClaimSupportItemV1]) -> dict[str, float]:
        """All of a batch's probabilities, or an exception: never a partial batch."""
        answers = self._post(_payload(self._model, batch))["answers"]
        values: dict[str, float] = {}
        for item in batch:
            raw = answers[item.item_id]["noul"]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise TypeError("noul is not a number")
            if not 0.0 <= raw <= 1.0:
                raise ValueError("probability out of range")
            values[item.item_id] = float(raw)
        return values

    def check(self, items: tuple[ClaimSupportItemV1, ...]) -> ClaimSupportResultV1:
        """`timeout_seconds` bounds the whole turn, not each request: once it is
        spent the remaining batches are not sent. The FIRST error is kept."""
        batches, skipped = _batches(items, self._budget)
        probabilities: dict[str, float] = {}
        error: str | None = "all_skipped" if skipped and not batches else None
        deadline = perf_counter() + self._timeout
        for index, batch in enumerate(batches):
            if perf_counter() >= deadline:
                skipped += sum(len(rest) for rest in batches[index:])
                error = error or "timeout"
                break
            try:
                probabilities.update(self._batch(batch))
                continue
            except httpx.TimeoutException:
                code = "timeout"
            except httpx.HTTPStatusError as exc:
                code = f"http_{exc.response.status_code}"
            except httpx.HTTPError:
                code = "transport_error"
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                code = "bad_response"
            except Exception:  # noqa: BLE001 - the port must never raise
                code = "checker_exception"
            error = error or code
        return ClaimSupportResultV1(probabilities=probabilities, skipped=skipped, error=error)


__all__ = ["JevClaimSupportChecker", "OPENROUTER_DECISIONS_ENDPOINT", "TYPESAFE_ENDPOINT"]
