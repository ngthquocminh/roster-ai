"""Tier-1 wording probe (G' phase 3): does Jev catch wrongly worded facts?

Keyless CI cannot answer this -- the stub checker returns a fixed number -- so
this is a small, manual, LIVE probe. Each case pairs one fact's wording with
its own verbalised record and the verdict a correct checker must reach. A
wrongly worded fact here is exactly what tier 0 cannot see: the tag's
attributes would pass, only the wording is false.

    uv run python -m evals.tier1_probe [--provider auto|typesafe|openrouter]

Reads keys from backend/.env WITHOUT importing `settings` (which would load the
real LOGFIRE_TOKEN); prints per-case probabilities, the latency of the one
batched request, and how many cases landed on the right side of 0.5.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values

from adapters.grounding.factory import OPENROUTER_DEFAULT_MODEL, TYPESAFE_DEFAULT_MODEL
from adapters.grounding.jev_checker import (
    OPENROUTER_DECISIONS_ENDPOINT,
    TYPESAFE_ENDPOINT,
    JevClaimSupportChecker,
)
from application.grounding.verbalize import verbalize_record
from application.ports.claim_support import ClaimSupportItemV1

# `adapters.grounding.factory` imports `settings`, which loads backend/.env --
# including the real LOGFIRE_TOKEN. This probe must never export telemetry.
for _name in ("LOGFIRE_TOKEN", "LOGFIRE_BASE_URL"):
    os.environ.pop(_name, None)

THRESHOLD = 0.5

WORKER = verbalize_record("workers", {
    "record_id": "w1", "contact_id": "w1", "name": "Ana Lee", "employment_type": "Casual",
    "grade": "3", "eba": "EBA2020-2023", "contracted_hours": 38.0,
    "qualifications": [{"task_id": "T1", "rate": 1.0}], "availability_windows": [],
})
TASK = verbalize_record("tasks", {
    "record_id": "T1", "task_id": "T1", "name": "C Fork | Grid P 8GR", "function": "Putaways",
    "area_id": "A2", "area_name": "Chiller", "unit_type_id": None,
})
CONSTRAINT = verbalize_record("constraints", {
    "record_id": "c1", "constraint_type": "Maximum Agency Shifts", "value": "6",
    "value_type": "weekly",
})

#: (case id, claim text, record, expected supported?)
CASES: tuple[tuple[str, str, str, bool], ...] = (
    ("qualified", "Ana Lee is qualified for T1", WORKER, True),
    ("qualified-negated", "Ana Lee is not qualified for T1", WORKER, False),
    ("qualified-wrong-task", "Ana Lee is qualified for T2", WORKER, False),
    ("employment", "Ana Lee is a casual worker", WORKER, True),
    ("employment-wrong", "Ana Lee is a full-time worker", WORKER, False),
    ("hours", "Ana Lee is contracted for 38 hours", WORKER, True),
    ("hours-wrong", "Ana Lee is contracted for 40 hours", WORKER, False),
    ("task", "C Fork | Grid P 8GR is a putaway task in the Chiller area", TASK, True),
    ("task-wrong-function", "C Fork | Grid P 8GR is a picking task", TASK, False),
    ("task-wrong-area", "C Fork | Grid P 8GR is in the Ambient area", TASK, False),
    ("constraint", "Agency workers may work at most 6 shifts per week", CONSTRAINT, True),
    ("constraint-inverted", "Agency workers must work at least 6 shifts per week", CONSTRAINT,
     False),
)


def _checker(provider: str) -> JevClaimSupportChecker:
    env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    typesafe, openrouter = env.get("TYPESAFE_API_KEY"), env.get("OPENROUTER_API_KEY")
    if not openrouter and str(env.get("AGENT_RUNTIME_MODEL", "")).startswith("openrouter:"):
        openrouter = env.get("AGENT_RUNTIME_API_KEY")
    if provider == "auto":
        provider = "typesafe" if typesafe else "openrouter"
    key = typesafe if provider == "typesafe" else openrouter
    if not key:
        raise SystemExit(f"no API key for provider {provider} in backend/.env")
    endpoint, model = ((TYPESAFE_ENDPOINT, TYPESAFE_DEFAULT_MODEL) if provider == "typesafe"
                       else (OPENROUTER_DECISIONS_ENDPOINT, OPENROUTER_DEFAULT_MODEL))
    return JevClaimSupportChecker(endpoint=endpoint, api_key=key, model=model,
                                  timeout_seconds=20.0, token_budget=100_000, provider=provider)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=("auto", "typesafe", "openrouter"), default="auto")
    args = parser.parse_args(argv)
    checker = _checker(args.provider)
    items = tuple(ClaimSupportItemV1(case_id, text, record) for case_id, text, record, _ in CASES)
    started = perf_counter()
    result = checker.check(items)
    latency_ms = (perf_counter() - started) * 1_000
    rows = []
    for case_id, text, _record, expected in CASES:
        probability = result.probabilities.get(case_id)
        correct = None if probability is None else (probability >= THRESHOLD) == expected
        rows.append({"case": case_id, "expected_supported": expected,
                     "probability": probability, "correct": correct, "text": text})
    print(json.dumps({
        "provider": checker.provider, "model": checker.name, "error": result.error,
        "latency_ms": round(latency_ms), "correct": sum(1 for r in rows if r["correct"]),
        "cases": len(rows), "rows": rows,
    }, indent=2))
    return 0 if result.error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
