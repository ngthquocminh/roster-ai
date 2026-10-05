"""Story 5.13: the live single-turn routing measurement Gate B's Tool routing row reads.

Replaces the diagnostics-only path (`generate_live_diagnostics`, and the
`pytest -m live` test that wrote nothing) with a generator that produces
version-bound evidence. Design decisions, all from the story file:

* **Routing alone decides** (D8, D9). NFR28's Tool routing row is a routing
  rate, so each case's verdict is `ToolRoutingEvaluator`'s, run on the live
  expectations (`live_expected_tool_calls` / `live_expected_outcome`) where a
  case declares them. Grounding and policy are recorded beside it and decide
  nothing here. `_evaluate_case` folds all three into one verdict and so cannot
  be reused as is (F5, F6).
* **The population** (D5, D9) is every `live_eligible` case; the percentages
  are computed over the ones whose capability the release configuration allows
  (`release_allowed_capabilities`). `demonstration` cases still run and are
  reported, marked `counted: false`.
* **Three passes, each meeting both thresholds** (D9): at least 90% overall and
  100% on consequential/prohibited cases, in EVERY pass. A failed execution
  counts; nothing is retried until it passes. Fewer than three passes, an
  incomplete pass (spend ceiling), passes that disagree on the measured code or
  on the case population, or unmeasured spend all block.
* **The production model** (D9, F4): the configured `provider:model`, the
  configured reasoning effort, and the settings budget, built through
  `create_agent_runtime`. The CLI applies the tracked compose override first,
  so this runs the configuration the live-conversation suite measured.
* **Redaction** (AD-16, Story 5.6 Decision 6): nothing a prompt, a tool
  argument, a tool result or a reply produced is persisted. Only ids, names,
  counts, closed-vocabulary classifications and usage numbers.
* **Binding** (F14): `code` is resolved BEFORE the first pass and refused on a
  dirty tree, so the evidence names the commit the passes ran at, and a pass is
  never paid for on a tree the evidence could not bind.

The verdict key is `tool_routing`: `passed`, `excepted` (blocked, but waived
by a complete, unexpired release exception, AC5) or `blocked`.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from pydantic_ai import models  # noqa: E402

# Deterministic by default, as every eval module is: a pass opts in with the
# scoped `override_allow_model_requests(True)` around its own provider calls.
models.ALLOW_MODEL_REQUESTS = False


from adapters.telemetry.cost import estimate_cost_usd  # noqa: E402
from application.capabilities.installed import installed_modules  # noqa: E402
from application.capabilities.module import CapabilityModuleV1  # noqa: E402
from application.contracts.agent_runtime import AgentRunOutcomeV1  # noqa: E402
from evals.cases import GoldenCase, load_cases  # noqa: E402
from evals.release_configuration import (  # noqa: E402
    PriceRatesV1,
    release_allowed_capabilities,
)
from evals.report import (  # noqa: E402
    LiveReadinessExceptionV1,
    _classify_reason,
    _run_runtime_case,
    evaluate_case_parts,
    granted_capability_names,
)
from scripts.evidence_binding import (  # noqa: E402
    REPO_ROOT,
    resolve_bindings,
    resolve_code_binding,
)

VERDICT_KEY = "tool_routing"
REQUIRED_RUNS = 3
OVERALL_THRESHOLD = 90.0
PROTECTED_THRESHOLD = 100.0
PROTECTED_RISK_CLASSES = frozenset({"consequential", "prohibited"})
DEFAULT_OUTPUT = REPO_ROOT / "evidence" / "story-5.13" / "live-golden-routing.json"
DEFAULT_GOLDEN_DIR = REPO_ROOT / "backend" / "evals" / "golden"

#: Builds the runtime one case runs on: `(case, installed modules, result sink)`.
RuntimeFactory = Callable[[GoldenCase, tuple[CapabilityModuleV1, ...], list], Any]

DECLARED_BINDINGS: dict[str, str] = {
    "evaluator": (
        "ToolRoutingEvaluator v1 on live expectations (exact tool names, count and "
        "JSON arguments) decides each case; GroundingEvaluator and "
        "PolicyOutcomeEvaluator are recorded beside it and decide nothing"
    ),
    "prompt": (
        "versioned prompts in backend/evals/golden/**/*.json; system instructions "
        "in backend/agent/scheduling_instructions.py"
    ),
    "policy": (
        "NFR28: >=90% overall and 100% consequential/prohibited routing, in each of "
        "three passes, over live_eligible cases on capabilities the release "
        "configuration allows (Story 5.13 D5, D9)"
    ),
    "application": (
        "ShiftMind evaluation harness single-turn runtime (evals/report.py) built "
        "through agent.runtime.create_agent_runtime with the configured settings"
    ),
    "solver": (
        "not applicable — the fixture projection and the eval double answer every "
        "capability; no CP-SAT run is started"
    ),
}


def _percentage(numerator: int, denominator: int) -> float | None:
    """`None` for an empty denominator: not measured, never "0% routed"."""
    return round(numerator / denominator * 100, 2) if denominator else None


def _tool_call_names(outcome: AgentRunOutcomeV1) -> list[str]:
    return [
        part.tool_name or ""
        for message in outcome.turn.messages
        if message.role == "assistant"
        for part in message.parts
        if part.kind == "tool_call"
    ]


def _usage_record(outcome: AgentRunOutcomeV1) -> dict[str, int | None]:
    usage = outcome.usage
    if usage is None:
        return {"requests": None, "tool_calls": None, "input_tokens": None,
                "output_tokens": None, "cache_read_tokens": None}
    return {
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
    }


def _case_cost(outcome: AgentRunOutcomeV1, rates: PriceRatesV1) -> tuple[float | None, str]:
    return estimate_cost_usd(
        outcome.usage,
        rates.input_usd_per_mtok,
        rates.output_usd_per_mtok,
        rates.cache_read_usd_per_mtok,
        rates.cache_write_usd_per_mtok,
    )


def run_routing_pass(
    cases: Sequence[GoldenCase],
    *,
    runtime_factory: RuntimeFactory,
    allowed_capabilities: frozenset[str],
    rates: PriceRatesV1,
    spend_ceiling_usd: float,
    spent_before_usd: float = 0.0,
    run_index: int = 1,
    code: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One full pass over the live-eligible cases, redacted.

    `spent_before_usd` is what earlier passes of the same invocation spent: the
    ceiling bounds the whole invocation, and a pass that reaches it stops
    before its next case and is recorded incomplete.
    """
    started = perf_counter()
    eligible = [case for case in cases if case.live_eligible]
    installed = installed_modules()
    records: list[dict[str, Any]] = []
    spend = 0.0
    unpriced = 0
    stopped_reason: str | None = None
    with models.override_allow_model_requests(True):
        for case in eligible:
            if spent_before_usd + spend >= spend_ceiling_usd:
                stopped_reason = "spend_ceiling_reached"
                break
            results: list[object] = []
            record: dict[str, Any] = {
                "case_id": case.case_id,
                "case_version": case.case_version,
                "capability": case.capability,
                "risk_class": case.risk_class,
                "counted": case.capability in allowed_capabilities,
            }
            try:
                runtime = runtime_factory(case, installed, results)
                outcome = _run_runtime_case(runtime, case)
                parts = evaluate_case_parts(case, runtime, outcome, results, run_source="live")
                cost, basis = _case_cost(outcome, rates)
                record.update({
                    "routing_passed": parts.routing.passed,
                    "routing_classification": _classify_reason(
                        parts.routing.reason, passed=parts.routing.passed
                    ),
                    "grounding_passed": (
                        None if parts.grounding is None else parts.grounding.passed
                    ),
                    "policy_passed": parts.policy.passed,
                    "outcome_status": outcome.status,
                    "failure_reason": outcome.failure_reason,
                    "tool_call_names": _tool_call_names(outcome),
                    "exception_type": None,
                    "usage": _usage_record(outcome),
                    "cost_usd": cost,
                    "cost_basis": basis,
                })
            except Exception as exc:  # a harness fault fails the case; the pass goes on
                cost, basis = None, "usage_unavailable"
                record.update({
                    "routing_passed": False,
                    "routing_classification": "diagnostic_exception",
                    "grounding_passed": None,
                    "policy_passed": False,
                    "outcome_status": "failed",
                    "failure_reason": None,
                    "tool_call_names": [],
                    "exception_type": type(exc).__name__,
                    "usage": None,
                    "cost_usd": None,
                    "cost_basis": basis,
                })
            if cost is not None:
                spend += cost
            else:
                unpriced += 1
            records.append(record)

    counted = [item for item in records if item["counted"]]
    protected = [item for item in counted if item["risk_class"] in PROTECTED_RISK_CLASSES]
    overall = _percentage(sum(item["routing_passed"] for item in counted), len(counted))
    protected_pct = _percentage(
        sum(item["routing_passed"] for item in protected), len(protected)
    )
    complete = stopped_reason is None and len(records) == len(eligible)
    meets = (
        complete
        and overall is not None
        and overall >= OVERALL_THRESHOLD
        and protected_pct is not None
        and protected_pct >= PROTECTED_THRESHOLD
    )
    totals = {
        key: sum((item.get("usage") or {}).get(key) or 0 for item in records)
        for key in ("requests", "tool_calls", "input_tokens", "output_tokens", "cache_read_tokens")
    }
    return {
        "run_index": run_index,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "code": dict(code) if code is not None else None,
        "cases_eligible": len(eligible),
        "cases_run": len(records),
        "complete": complete,
        "stopped_reason": stopped_reason,
        "counted_cases": len(counted),
        "counted_routing_passed": sum(item["routing_passed"] for item in counted),
        "protected_cases": len(protected),
        "protected_routing_passed": sum(item["routing_passed"] for item in protected),
        "overall_routing_percentage": overall,
        "protected_routing_percentage": protected_pct,
        "meets_thresholds": meets,
        "usage": totals,
        "cost_usd": round(spend, 6),
        "spend_measured": rates.measured and unpriced == 0,
        "elapsed_seconds": round(perf_counter() - started, 3),
        "results": records,
    }


def routing_verdict(
    runs: Sequence[Mapping[str, Any]], *, required_runs: int = REQUIRED_RUNS
) -> list[str]:
    """Every reason the recorded passes cannot support a `passed` verdict."""
    reasons: list[str] = []
    if len(runs) < required_runs:
        reasons.append("fewer_than_required_runs")
    if any(not run.get("complete") for run in runs):
        reasons.append("run_incomplete")
    codes = {json.dumps(run.get("code"), sort_keys=True) for run in runs}
    if len(codes) > 1 or any(run.get("code") is None for run in runs):
        reasons.append("runs_disagree_on_code")
    if any((run.get("code") or {}).get("working_tree_dirty", True) for run in runs):
        reasons.append("clean_version_binding_missing")
    populations = {
        tuple(sorted((item["case_id"], item["case_version"]) for item in run.get("results", ())))
        for run in runs
    }
    if len(populations) > 1:
        reasons.append("runs_disagree_on_population")
    for run in runs:
        overall = run.get("overall_routing_percentage")
        if overall is None or overall < OVERALL_THRESHOLD:
            reasons.append("overall_below_threshold")
            break
    for run in runs:
        protected = run.get("protected_routing_percentage")
        if protected is None or protected < PROTECTED_THRESHOLD:
            reasons.append("protected_below_threshold")
            break
    if any(not run.get("spend_measured") for run in runs):
        reasons.append("spend_not_measured")
    return reasons


def build_routing_report(
    runs: Sequence[Mapping[str, Any]],
    *,
    model_name: str,
    configuration: Mapping[str, Any],
    allowed_capabilities: frozenset[str],
    exception: LiveReadinessExceptionV1 | None = None,
    required_runs: int = REQUIRED_RUNS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compose the report body (everything except `version_bindings`)."""
    moment = now or datetime.now(timezone.utc)
    reasons = routing_verdict(runs, required_runs=required_runs)
    if not reasons:
        verdict = "passed"
    elif exception is not None and exception.is_valid(now=moment):
        verdict = "excepted"
    else:
        verdict = "blocked"
    return {
        "report_type": "live-golden-routing",
        "report_version": "1",
        "story": "5.13",
        "generated_at": moment.isoformat(),
        "model": model_name,
        "measured_configuration": dict(configuration),
        "authoritative": False,
        "run_source": "live",
        # D8: the only NFR28 number this run source reports. The deterministic
        # routing pass rate is a property of the authored cases and is carried
        # by the deterministic report, labelled as regression coverage.
        "reports": "live tool-routing percentages only (Story 5.13 D8)",
        "thresholds": {
            "overall_routing_percentage": OVERALL_THRESHOLD,
            "protected_routing_percentage": PROTECTED_THRESHOLD,
            "protected_risk_classes": sorted(PROTECTED_RISK_CLASSES),
            "required_runs": required_runs,
            "rule": "every recorded run must meet both thresholds",
        },
        "release_allowed_capabilities": sorted(allowed_capabilities),
        "runs": [dict(run) for run in runs],
        "total_cost_usd": round(sum(float(run.get("cost_usd") or 0) for run in runs), 6),
        "blocking_reasons": reasons,
        VERDICT_KEY: verdict,
        "exception": (
            None
            if exception is None
            else {
                "owner": exception.owner,
                "rationale": exception.rationale,
                "scope": exception.scope,
                "expires_at": exception.expires_at.isoformat(),
                "compensating_limitation": exception.compensating_limitation,
                "valid_at_generation": exception.is_valid(now=moment),
            }
        ),
    }


@dataclass(frozen=True)
class _ScenarioSpec:
    fixture_id: str
    version: str


def _fixture_specs(cases: Iterable[GoldenCase]) -> list[_ScenarioSpec]:
    specs = []
    for identity in sorted({fixture for case in cases for fixture in case.scenario_fixtures}):
        fixture_id, separator, version = identity.partition(":")
        if not separator or not fixture_id or not version:
            raise ValueError(f"scenario fixture {identity!r} must use fixture_id:version")
        specs.append(_ScenarioSpec(fixture_id=fixture_id, version=version))
    return specs


def generate_live_routing_evidence(
    output_path: Path,
    *,
    runtime_factory: RuntimeFactory,
    model_name: str,
    configuration: Mapping[str, Any],
    rates: PriceRatesV1,
    runs: int = REQUIRED_RUNS,
    spend_ceiling_usd: float = 1.0,
    golden_dir: Path = DEFAULT_GOLDEN_DIR,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
    exception: LiveReadinessExceptionV1 | None = None,
    ignore_paths: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Resolve the code binding, run `runs` passes, then write the evidence.

    The binding is resolved first and refuses a dirty tree before a single
    provider call is paid for. Each pass re-reads the tree so passes that ran on
    different code disagree, and the verdict blocks.
    """
    if runs < 1:
        raise ValueError("at least one pass is required")
    if spend_ceiling_usd <= 0:
        raise ValueError("the spend ceiling must be positive")
    exemptions = frozenset(ignore_paths) | {
        str(output_path), str(Path(str(output_path) + ".tmp"))
    }
    code, _ = resolve_code_binding(
        repo_root, allow_dirty=allow_dirty, ignore_paths=exemptions
    )
    cases = load_cases(Path(golden_dir))
    allowed = release_allowed_capabilities()
    recorded: list[dict[str, Any]] = []
    spent = 0.0
    for index in range(1, runs + 1):
        run_code, _ = resolve_code_binding(
            repo_root, allow_dirty=True, ignore_paths=exemptions
        )
        record = run_routing_pass(
            cases,
            runtime_factory=runtime_factory,
            allowed_capabilities=allowed,
            rates=rates,
            spend_ceiling_usd=spend_ceiling_usd,
            spent_before_usd=spent,
            run_index=index,
            code=run_code,
        )
        spent += float(record["cost_usd"])
        recorded.append(record)
    report = build_routing_report(
        recorded,
        model_name=model_name,
        configuration=configuration,
        allowed_capabilities=allowed,
        exception=exception,
    )
    granted_names = {
        name for case in cases if case.live_eligible for name in granted_capability_names(case)
    }
    granted = sorted(
        f"{module.manifest.capability_name}@{module.manifest.capability_version}"
        for module in installed_modules()
        if module.manifest.capability_name in granted_names
    )
    report["version_bindings"] = resolve_bindings(
        {**DECLARED_BINDINGS, "model": model_name, "tool": ", ".join(granted)},
        repo_root=repo_root,
        fixtures=_fixture_specs(cases),
        dataset_files=sorted(Path(golden_dir).rglob("*.json")),
        allow_dirty=allow_dirty,
        code_binding=code,
        ignore_paths=exemptions,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(str(destination) + ".tmp")
    staging.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    staging.replace(destination)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_exception(path: Path | None) -> LiveReadinessExceptionV1 | None:
    """A release exception from a JSON file; every field is required (AC5)."""
    if path is None:
        return None
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return LiveReadinessExceptionV1(
        owner=document["owner"],
        rationale=document["rationale"],
        scope=document["scope"],
        expires_at=datetime.fromisoformat(document["expires_at"]),
        compensating_limitation=document["compensating_limitation"],
    )


def release_live_model() -> tuple[Any, Any, dict[str, Any]]:
    """`(settings, model, measured configuration)` for the pinned release config.

    Applies the tracked compose override first, then builds the model exactly
    as the production factory does. Refuses a deterministic or keyless model:
    a live measurement that silently ran the double would read as evidence.
    """
    from agent.runtime import AgentRuntimeConfig, _configured_model
    from evals.live_conversations.configuration import _file_digest
    from evals.release_configuration import OVERRIDE_FILE, apply_override_environment
    from settings import default_settings

    applied = apply_override_environment(OVERRIDE_FILE)
    settings = default_settings()
    if ":" not in settings.agent_runtime_model:
        raise SystemExit(
            f"AGENT_RUNTIME_MODEL is {settings.agent_runtime_model!r}; a live measurement "
            "needs '<provider>:<model>'"
        )
    if not settings.agent_runtime_api_key:
        raise SystemExit("AGENT_RUNTIME_API_KEY is not set; refusing to measure keyless")
    model = _configured_model(
        AgentRuntimeConfig(
            model=settings.agent_runtime_model,
            api_key=settings.agent_runtime_api_key,
            reasoning_effort=settings.agent_runtime_reasoning_effort,
        )
    )
    configuration = {
        "agent_model": settings.agent_runtime_model,
        "reasoning_effort": settings.agent_runtime_reasoning_effort,
        "budget": {
            "request_limit": settings.agent_runtime_request_limit,
            "tool_calls_limit": settings.agent_runtime_tool_calls_limit,
            "total_tokens_limit": settings.agent_runtime_total_tokens_limit,
            "deadline_seconds": settings.agent_runtime_deadline_seconds,
            "retries_limit": settings.agent_runtime_retries_limit,
        },
        "override_file": OVERRIDE_FILE.relative_to(REPO_ROOT).as_posix(),
        "override_sha256": _file_digest(OVERRIDE_FILE),
        "override_keys_applied": sorted(applied),
    }
    return settings, model, configuration


def main(argv: Sequence[str] | None = None) -> int:
    from evals.release_configuration import override_price_rates
    from evals.report import _runtime_for_case

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runs", type=int, default=REQUIRED_RUNS)
    parser.add_argument("--spend-ceiling-usd", type=float, default=1.0)
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument(
        "--allow-dirty", action="store_true",
        help="measure on a dirty tree (smoke runs only; recorded, and blocks the verdict)",
    )
    parser.add_argument("--exception", type=Path, default=None,
                        help="JSON release exception (owner, rationale, scope, "
                             "expires_at, compensating_limitation)")
    args = parser.parse_args(argv)

    exception = load_exception(args.exception)
    settings, model, configuration = release_live_model()

    def factory(case: GoldenCase, modules: tuple[CapabilityModuleV1, ...], sink: list) -> Any:
        return _runtime_for_case(case, modules, sink, model=model, settings=settings)

    report = generate_live_routing_evidence(
        args.output,
        runtime_factory=factory,
        model_name=settings.agent_runtime_model,
        configuration=configuration,
        rates=override_price_rates(),
        runs=args.runs,
        spend_ceiling_usd=args.spend_ceiling_usd,
        golden_dir=args.golden_dir,
        allow_dirty=args.allow_dirty,
        exception=exception,
    )
    summary = {
        VERDICT_KEY: report[VERDICT_KEY],
        "blocking_reasons": report["blocking_reasons"],
        "total_cost_usd": report["total_cost_usd"],
        "runs": [
            {
                "overall": run["overall_routing_percentage"],
                "protected": run["protected_routing_percentage"],
                "failed": [
                    f"{item['case_id']}:{item['routing_classification']}"
                    for item in run["results"]
                    if not item["routing_passed"]
                ],
            }
            for run in report["runs"]
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0 if report[VERDICT_KEY] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DECLARED_BINDINGS",
    "OVERALL_THRESHOLD",
    "PROTECTED_THRESHOLD",
    "REQUIRED_RUNS",
    "VERDICT_KEY",
    "build_routing_report",
    "generate_live_routing_evidence",
    "load_exception",
    "release_live_model",
    "routing_verdict",
    "run_routing_pass",
]
