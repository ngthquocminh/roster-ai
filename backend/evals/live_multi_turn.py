"""Story 5.13 D3: CLI for the recorded live multi-turn measurement.

Runs `generate_live_multi_turn_evidence` (evals/report.py) on the pinned
release configuration: the tracked compose override is applied, the model is
built the way the production factory builds it (configured reasoning effort and
settings budget), and the override's per-token prices are passed so
`spend_measured` is true. Default output is
`evidence/story-5.13/live-multi-turn-evaluation.json`; the Story 5.6 file stays
as history.

    uv run --frozen python -m evals.live_multi_turn                 # 3 recorded runs
    uv run --frozen python -m evals.live_multi_turn --runs 1 --allow-dirty \\
        --output ../_bmad-output/test-artifacts/gate-b/multi-turn-smoke.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evals.live_golden_routing import load_exception, release_live_model  # noqa: E402
from evals.release_configuration import override_price_rates  # noqa: E402
from evals.report import (  # noqa: E402
    MULTI_TURN_REQUIRED_RUNS,
    MULTI_TURN_VERDICT_KEY,
    LiveSuiteBudgetV1,
    generate_live_multi_turn_evidence,
)
from scripts.evidence_binding import REPO_ROOT  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "evidence" / "story-5.13" / "live-multi-turn-evaluation.json"

#: Aggregate ceilings for ONE run of the six-case suite. Per-turn limits come
#: from the settings budget; these bound the run as a whole (Story 5.6 D5).
DEFAULT_BUDGET = LiveSuiteBudgetV1(
    case_limit=20, request_limit=300, tool_call_limit=300,
    token_limit=3_000_000, elapsed_seconds_limit=1800.0, spend_usd_limit=1.0,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runs", type=int, default=MULTI_TURN_REQUIRED_RUNS)
    parser.add_argument("--allow-dirty", action="store_true",
                        help="measure on a dirty tree (smoke runs only; blocks the verdict)")
    parser.add_argument("--exception", type=Path, default=None,
                        help="JSON release exception (owner, rationale, scope, "
                             "expires_at, compensating_limitation)")
    args = parser.parse_args(argv)

    exception = load_exception(args.exception)
    settings, model, configuration = release_live_model()
    rates = override_price_rates()
    report = generate_live_multi_turn_evidence(
        args.output,
        model=model,
        model_name=settings.agent_runtime_model,
        budget=DEFAULT_BUDGET,
        configuration=configuration,
        runs=args.runs,
        settings=settings,
        input_usd_per_mtok=rates.input_usd_per_mtok,
        output_usd_per_mtok=rates.output_usd_per_mtok,
        cache_read_usd_per_mtok=rates.cache_read_usd_per_mtok,
        cache_write_usd_per_mtok=rates.cache_write_usd_per_mtok,
        allow_dirty=args.allow_dirty,
        exception=exception,
    )
    print(json.dumps({
        MULTI_TURN_VERDICT_KEY: report[MULTI_TURN_VERDICT_KEY],
        "blocking_reasons": report["blocking_reasons"],
        "total_spend_usd": report["total_spend_usd"],
        "runs": [
            {
                "stopped_reason": run["stopped_reason"],
                "failed": [
                    f"{item['case_id']}:" + ",".join(
                        f"t{turn['turn_index']}={turn['reason_classification']}"
                        for turn in item.get("turns", []) if not turn["passed"]
                    )
                    for item in run["results"] if not item["passed"]
                ],
            }
            for run in report["runs"]
        ],
    }, indent=2))
    return 0 if report[MULTI_TURN_VERDICT_KEY] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
