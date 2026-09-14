# Story 5.6: Evaluate Real-Provider Multi-Turn History and Tool Continuity

Status: ready-for-dev

## Story

As a portfolio reviewer,
I want opt-in, version-bound live-provider evaluations that exercise multi-turn conversation continuity,
so that real-provider behavior is observable across the history and tool-result paths that deterministic release evidence already protects.

## Origin, outcome, and scope

This corrective Epic 5 story follows Story 5.5. The live suite now proves eligible single-turn routing, but not real-provider behavior across application-owned history, trusted antecedents, durable rehydration, ordered dependent calls, or the owned history window.

Deliver one versioned multi-turn evaluation family with two executions:

- A deterministic-double execution in normal CI. It remains the authoritative safety/correctness evidence.
- An explicit, bounded, version-bound live execution. Every release-eligible case for the pinned release provider/model must pass before the AI feature can ship. Its pass is necessary but never sufficient: it cannot satisfy, weaken, or replace deterministic evidence.

This story supplies evidence for a future Gate B decision. It does not decide the unresolved 50-case dataset floor or create the next release-gate report.

## Facts this story depends on

| Fact | Citable source / anchor | Consequence |
| --- | --- | --- |
| Only the newest 100 owned history messages may reach a provider. | `HISTORY_MESSAGE_BOUND` / `execute_turn`, `backend/application/use_cases/execute_turn.py` | Exercise both activity rehydration and owned-turn replay; never raise or bypass the bound. |
| The runtime accepts only owned history and only registers passed-in modules. | `agent/runtime.py`: `to_framework_messages`, `render_capabilities` | Evaluation uses `AgentTurnV1`, trusted state, and exact per-case grants; never browser history or provider memory. |
| Framework records are edge details. | Architecture spine AD-19; `agent/translate.py` | Do not persist PydanticAI messages/types, hidden reasoning, or raw provider transcripts. |
| Prompts, model output, and tool output are untrusted. | Architecture spine AD-15 | Absent, stale, unauthorized, or truncated antecedents fail closed; no invention, retargeting, or widened authority. |
| CI is deterministic-first; live is explicit, budgeted, and version-bound. | Architecture spine AD-16; `backend/pyproject.toml` | Preserve `@pytest.mark.live`, default `-m "not live"`, and `authoritative=False` for live results. |

## Acceptance Criteria

1. A versioned multi-turn golden scenario has a deterministic equivalent in normal CI. It asserts history-aware routing, prior trusted tool-result use, ordered dependent calls, durable rehydration, and the 100-activity history window. Its deterministic verdict remains the authoritative safety/correctness release evidence.
2. The live counterpart is impossible to run by default and has finite application-owned limits for cases, requests, tool calls, tokens, elapsed time, and spend. It reads neither model credentials nor enables network calls outside the explicit invocation path.
3. Every live turn uses application-owned `AgentTurnV1` history and trusted prior-result state only. Browser transcripts, provider memory, and unbounded durable transcripts are never an authority or history-bound bypass.
4. A scenario whose later request needs a prior result or clarified entity proves the live provider selects only currently granted capabilities and uses that trusted antecedent. Missing, stale, unauthorized, and truncated antecedents fail closed; they are never guessed, silently retargeted, or replaced with new authority.
5. A long-history scenario proves activities older than the application-owned window remain durable but are absent from provider input. Reporting makes no claim that omitted history was retained.
6. Reports contain ordered per-turn calls and outcomes without raw sensitive prompts or tool-result bodies, and bind dataset, evaluator, provider/model, prompts, tools, policy, application, scenario, solver, code, and image versions.
7. Every release-eligible live scenario for the pinned release provider/model passes before the AI feature ships. A live pass is necessary but never sufficient. A failure blocks the feature until fixed and rerun, unless an explicit time-bounded exception records owner, rationale, scope, expiry, and compensating user-facing limitation.
8. An application defect in history, trusted-result propagation, sequencing, persistence, or truncation is fixed at its owning seam and receives a deterministic regression. Prompt ambiguity, unrealistic cases, and provider variability are corrected or classified without mislabelling them as application defects; safe diagnostic evidence is retained.

## Decisions and developer guardrails

1. **Extend the current evaluation authority; do not build another harness.** Reuse `GoldenCase`, `_runtime_for_case`, `_evaluate_case`, `write_evaluation_report`, `resolve_bindings`, `RunSource`, and the existing per-case grants/dependencies/answer-type setup. A narrowly scoped versioned multi-turn case shape may be added, but it must reject unknown fields, consume every declared field, and leave legacy single-turn case semantics intact.

   This does not cover a new durable public conversation contract or a second evaluator. Changes to `AgentTurnV1`, activity contracts, or capability manifests require AD-20 compatibility evidence and are out of scope unless an existing deterministic test proves the contract cannot represent the approved case.

2. **Use the product seam, not an adapter shortcut.** The multi-turn runner must invoke `execute_turn` / `rehydrate_history`. Calling `runtime.run_turn(AgentTurnRequestV1(prompt=...))` directly, the present single-turn helper, cannot establish durable rehydration or the bound.

   Normal persisted rehydration intentionally carries planner-visible activity text rather than raw tool-result bodies. Prove trusted-result use through the owned resume transcript or an existing trusted application result path; do not invent general raw tool-result persistence just for eval coverage. State the chosen supported path in case metadata and its report binding.

3. **Make the dependency real.** Turn one obtains an opaque antecedent via a granted governed capability. A later prompt requires that result or clarified entity, and its expected call proves exact ordered use. The later user prompt must not contain the opaque value. The double must observe/validate history and dependency; a response-index-only double is not evidence.

4. **Fail closed without a provider call.** Test missing, stale, unauthorized, and history-truncated antecedents independently. Each produces a named negative verdict, with no substitute tool, inferred value, widened grant, or new authority. Installed-but-ungranted modules are unavailable.

5. **Bound live execution at the application layer.** The live runner requires an explicit opt-in plus configured model/provider and credential. Validate positive finite ceilings for case count, total requests, total tool calls, total tokens, elapsed time, and spend. Account cumulative actual usage/cost before each next turn; stop fail-closed at exhaustion and persist a safe partial result. No default, `.env` import, or global mutation may permit ordinary tests to call a provider. Keep `models.override_allow_model_requests(True)` scoped to the explicit runner/test.

   `AgentBudgetV1` handles per-turn request/tool/token/deadline limits; it does not replace aggregate suite and spend controls.

6. **Replace unsafe live diagnostics.** `generate_live_diagnostics` currently persists raw tool arguments and `AgentToolResultV1.content`, violating AC6/AD-15. Persist only safe ordered metadata: case/version, model identity, run source, authoritative flag, turn/call order, tool name/count, bounded outcome/reason classification, aggregate budget state, and binding identifiers/digests. Never serialize prompts, keys, raw args, raw result bodies, framework/provider payloads, or chain-of-thought.

   A safe report may show that history was omitted by the owned bound; it must not claim provider memory retained it. Preserve per-case diagnostic durability when serialization/writes fail.

7. **Keep authority split exact.** `ToolRoutingEvaluator` remains exact and ordered. Do not loosen expected routes, deterministic scripts, or evaluator semantics to improve a live result. Live verdicts remain non-authoritative and cannot make an authoritative report green. A readiness artifact may state `blocked`, `eligible`, or a valid exception but cannot replace the later Gate B decision.

8. **No dependency upgrade.** Use the exact `pydantic-ai-slim[anthropic,google,openrouter]==2.27.0` pin and owned `agent/translate.py` boundary. Current message-history guidance supports the established requirement that history and tool-result pairing stay application-owned. [Source: `backend/pyproject.toml`; Pydantic AI message-history documentation]

## Tasks / Subtasks

- [ ] Task 1 — Define versioned multi-turn cases and a deterministic oracle (AC: 1, 3, 4, 5)
  - [ ] Extend `backend/evals/cases.py` with the smallest strict multi-turn shape and add versioned cases in `backend/evals/golden/`. Reject unknown keys and prove every new field is consumed.
  - [ ] Add a history-dependent success case; negative missing/stale/unauthorized/truncated antecedent cases; and a long-history case. Bump `case_version` for any semantic case change. Do not edit legacy scripts/expectations merely to suit live behavior.
  - [ ] Update `backend/evals/doubles.py` so history/dependency and call order are observable. A double selecting only by response count must fail the new proof.
  - [ ] Reuse exact per-case capabilities/dependencies. Any live-only expectation must explain why a deterministic security simulation cannot be asked of a real provider; retain Story 5.5's four deterministic-only exclusions.

- [ ] Task 2 — Implement product-shaped multi-turn evaluation (AC: 1, 3, 4, 5)
  - [ ] Extend `backend/evals/report.py` to call `execute_turn` and owned history rehydration instead of only the single-turn direct-runtime helper.
  - [ ] Prove durable rehydration and exactly the newest 100 provider-history messages while older activities remain durable.
  - [ ] Prove a later call uses the trusted antecedent in exact order. Removing/mutating the history, result, grant, or order must make its deterministic check red.
  - [ ] Do not alter `execute_turn.py`, persistence, runtime translation, API, frontend, solver, migrations, or public contracts unless a deterministic regression proves an owning defect. If required, stop and use Correct Course before widening scope.

- [ ] Task 3 — Add explicit bounded live execution and safe reporting (AC: 2, 6, 7)
  - [ ] Build on the existing marked-live configured-model pattern in `backend/tests/test_evaluation_harness.py`; default collection/CI remains network-free.
  - [ ] Implement validated aggregate limits, cumulative accounting, fail-closed stop, safe partial output, and pinned model identity. Do not construct a live model or read credentials before explicit opt-in validation.
  - [ ] Replace raw diagnostic content in `generate_live_diagnostics` with safe ordered metadata; a write/serialization failure must not erase later-case diagnostics.
  - [ ] Generate a binding-resolver-backed live report with all NFR27 dimensions. Mark it live, non-authoritative, opt-in, budgeted, and `blocked`/`eligible`/`excepted`.
  - [ ] Make an exception an explicit validated, time-bounded record with owner, rationale, scope, expiry, and compensating user-facing limitation; incomplete/expired exceptions block readiness.

- [ ] Task 4 — Prove contracts, redaction, and guards (AC: 1–8)
  - [ ] Extend `backend/tests/test_evaluation_harness.py` for schema strictness, field consumption, exact per-turn routing, grant boundary, deterministic authority/live non-authority, opt-in refusal, aggregate budgets, negative antecedents, bindings, readiness classification, and safe diagnostics.
  - [ ] Extend `backend/tests/test_execute_turn_use_case.py` for product-shaped rehydration/window coverage. Reuse current boundary tests; add a regression only where this evaluator's behavior was previously untested.
  - [ ] Put a sensitive sentinel in test inputs and assert it is absent from all persisted diagnostics/reports, including fallback records. Assert prompt, raw arguments, raw tool-result content, and credential values are absent too.
  - [ ] Record a Dev Agent Record mutation table for every new guard: mutate already-green data/code, demonstrate the named failure, restore, and prove green. A first-draft/missing-import failure does not count.

- [ ] Task 5 — Document and verify handoff (AC: 2, 6, 7, 8)
  - [ ] Update `docs/TESTING.md` with exact opt-in invocation/configuration, finite budgets, pinned binding, default no-network rule, diagnostic redaction, deterministic authority, and joint readiness semantics.
  - [ ] Run deterministic multi-turn coverage without a provider, existing evaluation/capability/runtime tests, and the full default backend suite. No live marker may be selected by default.
  - [ ] When a configured provider is available, run the bounded live suite only through the documented explicit command and retain its safe binding report. Classify failures honestly; application defects need an owned-code regression.
  - [ ] Do not change `gate_a_checks.py` or present a live result as standalone release proof. Record the open Gate B data-floor/release-report decision.

## File plan

| Area | Action | Constraint |
| --- | --- | --- |
| `backend/evals/cases.py` | Update | Strict versioned multi-turn schema; no silent defaults. |
| `backend/evals/doubles.py` | Update | History/dependency-aware oracle, not response-index-only. |
| `backend/evals/report.py` | Update | Product-shaped runner, existing bindings, redacted diagnostics. |
| `backend/evals/evaluators.py` | Preserve / narrow update | Exact ordered comparisons and live non-authority remain. |
| `backend/evals/golden/**` | Add | Versioned cases; no raw secrets. |
| `backend/tests/test_evaluation_harness.py` | Update | Contract, budgets, reports, redaction, demonstrated-red tests. |
| `backend/tests/test_execute_turn_use_case.py` | Update | Owned rehydration/window proof. |
| `backend/tests/test_agent_runtime_adapter.py` | Inspect/update as needed | Owned transcript/tool-result translation only. |
| `docs/TESTING.md` | Update | Explicit live execution and safe readiness semantics. |

No migration, frontend, API, solver, capability-grant, credential, `gate_a_checks.py`, or durable-public-contract change is expected.

## Previous-story intelligence

- Story 5.5 already made live routing functional. Reuse `_evaluate_case`, `runtime_for_modules` / `_runtime_for_case`, scoped model-request override, per-capability descriptions, and exact live-aware evaluation; do not rebuild it.
- A real provider needs literal prompt values and clear tool descriptions. The old double does not read prompt/history unless this story makes the oracle do so. Never weaken exact expected calls or deterministic scripts to raise a live pass rate.
- The current diagnostics survive serialization/write errors but leak raw tool args/results. Preserve durability while removing content.
- Unrelated deferred items remain deferred: local environment-model leakage, no committed diagnostics CLI, mistagged `grounding-supported` fixture, and the Gate B 50-case decision.

## Verification commands

Run from `backend/` (use any new focused target added during implementation):

```bash
uv run pytest tests/test_evaluation_harness.py tests/test_execute_turn_use_case.py tests/test_agent_runtime_adapter.py
uv run pytest
uv run pytest -m live tests/test_evaluation_harness.py
```

The last command is opt-in only and needs documented live configuration; it must never be selected by the default-suite command.

## References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 5.6 / Epic 5 release gate]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-14.md` — approved corrective scope]
- [Source: `architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-15, AD-16, AD-19, AD-20]
- [Source: `_bmad-output/implementation-artifacts/5-5-make-the-live-agent-route-the-golden-dataset.md`]
- [Source: `backend/application/use_cases/execute_turn.py`; `backend/agent/translate.py`; `backend/agent/runtime.py`]
- [Source: `backend/evals/report.py`; `backend/evals/cases.py`; `backend/evals/doubles.py`; `backend/evals/evaluators.py`]
- [Source: `docs/TESTING.md`; `backend/pyproject.toml`]

## Dev Agent Record

### Agent Model Used

To be completed during implementation.

### Debug Log References

To be completed during implementation.

### Completion Notes List

- Ultimate context-engine analysis completed — comprehensive developer guide created.
- Facts, decisions, and self-consistency passes completed. Tasks cite the governing facts/decisions rather than re-arguing them.
- Out of scope: changing the 100-message bound; general raw tool-result persistence; widened authority; durable public-contract changes; default network access; or live evidence presented as deterministic proof.

### File List

- `_bmad-output/implementation-artifacts/5-6-evaluate-real-provider-multi-turn-history-and-tool-continuity.md`
