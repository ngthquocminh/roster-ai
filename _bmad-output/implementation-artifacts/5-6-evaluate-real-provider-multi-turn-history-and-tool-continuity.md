# Story 5.6: Evaluate Real-Provider Multi-Turn History and Tool Continuity
---
baseline_commit: 3171ec6b6a8cb13c1c2f427a449a002287a10192
---

Status: review

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

- [x] Task 1 — Define versioned multi-turn cases and a deterministic oracle (AC: 1, 3, 4, 5)
  - [x] Extend `backend/evals/cases.py` with the smallest strict multi-turn shape and add versioned cases in `backend/evals/golden/`. Reject unknown keys and prove every new field is consumed. **Deviation (recorded, not asked):** cases live in a new `backend/evals/golden_multi_turn/` directory, not inside `backend/evals/golden/`. `load_cases()` recursively parses every `.json` under `golden/` as a single-turn `GoldenCase` and raises on any unrecognized top-level field (by design — the same strictness this task requires); co-locating the fundamentally different multi-turn shape (`turns` instead of `scripted_turns`, etc.) there would break that loader on every multi-turn file. A sibling directory with its own loader (`load_multi_turn_cases`) satisfies the same intent (versioned, strict, "no raw secrets") without weakening either schema's strictness.
  - [x] Add a history-dependent success case; negative missing/stale/unauthorized/truncated antecedent cases; and a long-history case. Bump `case_version` for any semantic case change. Do not edit legacy scripts/expectations merely to suit live behavior. Six cases in `backend/evals/golden_multi_turn/history_and_tools/`, all `case_version: "1"` (new dataset). `backend/evals/golden/**` untouched.
  - [x] Update `backend/evals/doubles.py` so history/dependency and call order are observable. A double selecting only by response count must fail the new proof. `history_response_offset_for` + `HistoryLookupV1`/`_resolve_history_lookup` — see mutation table.
  - [x] Reuse exact per-case capabilities/dependencies. Any live-only expectation must explain why a deterministic security simulation cannot be asked of a real provider; retain Story 5.5's four deterministic-only exclusions. No live-only expectations were needed: every 5.6 case (including `unauthorized-antecedent`, which tests the app's OWN capability-grant boundary) is equally answerable by a real provider. Story 5.5's exclusions are untouched.

- [x] Task 2 — Implement product-shaped multi-turn evaluation (AC: 1, 3, 4, 5)
  - [x] Extend `backend/evals/report.py` to call `execute_turn` and owned history rehydration instead of only the single-turn direct-runtime helper. `run_multi_turn_case` calls `execute_turn` per turn; `raw_turn` mode replays the exact "owned resume transcript" mechanism `api/routers/approvals.py` already uses; `rehydrated_activities` mode drives `execute_turn`'s own `rehydrate_history()` call.
  - [x] Prove durable rehydration and exactly the newest 100 provider-history messages while older activities remain durable. `long-history-window.json` (105 filler activities) through the full harness, plus a new focused unit test in `test_execute_turn_use_case.py` for the previously-untested raw-`AgentTurnV1` truncation branch.
  - [x] Prove a later call uses the trusted antecedent in exact order. Removing/mutating the history, result, grant, or order must make its deterministic check red. Proven — see Dev Agent Record mutation table.
  - [x] Do not alter `execute_turn.py`, persistence, runtime translation, API, frontend, solver, migrations, or public contracts unless a deterministic regression proves an owning defect. Confirmed unaltered (`git status` / file list below); no owning defect was found, so no Correct Course was needed.

- [x] Task 3 — Add explicit bounded live execution and safe reporting (AC: 2, 6, 7)
  - [x] Build on the existing marked-live configured-model pattern in `backend/tests/test_evaluation_harness.py`; default collection/CI remains network-free. New `test_live_multi_turn_suite_is_bounded_and_non_authoritative`, same `@pytest.mark.live` + `_HAS_LIVE_AGENT` skipif guard as the Story 5.5 single-turn test; `addopts = "-m \"not live\""` unchanged.
  - [x] Implement validated aggregate limits, cumulative accounting, fail-closed stop, safe partial output, and pinned model identity. Do not construct a live model or read credentials before explicit opt-in validation. `LiveSuiteBudgetV1` (six required positive-finite ceilings) + `run_bounded_live_multi_turn_suite`; model/credential construction happens only inside the live-marked test, never in the suite functions themselves.
  - [x] Replace raw diagnostic content in `generate_live_diagnostics` with safe ordered metadata; a write/serialization failure must not erase later-case diagnostics. `_safe_diagnostic_record` + `_classify_reason`; both failure paths proven in `TestLiveDiagnosticsRedaction`.
  - [x] Generate a binding-resolver-backed live report with all NFR27 dimensions. Mark it live, non-authoritative, opt-in, budgeted, and `blocked`/`eligible`/`excepted`. `generate_bounded_live_multi_turn_report`.
  - [x] Make an exception an explicit validated, time-bounded record with owner, rationale, scope, expiry, and compensating user-facing limitation; incomplete/expired exceptions block readiness. `LiveReadinessExceptionV1` + `_readiness_verdict`.

- [x] Task 4 — Prove contracts, redaction, and guards (AC: 1–8)
  - [x] Extend `backend/tests/test_evaluation_harness.py` for schema strictness, field consumption, exact per-turn routing, grant boundary, deterministic authority/live non-authority, opt-in refusal, aggregate budgets, negative antecedents, bindings, readiness classification, and safe diagnostics. ~65 new tests/parametrizations added.
  - [x] Extend `backend/tests/test_execute_turn_use_case.py` for product-shaped rehydration/window coverage. Reuse current boundary tests; add a regression only where this evaluator's behavior was previously untested. One new test (the raw-`AgentTurnV1` truncation branch); `test_agent_runtime_adapter.py` inspected — no change needed, since `agent/runtime.py`/`agent/translate.py` were not touched.
  - [x] Put a sensitive sentinel in test inputs and assert it is absent from all persisted diagnostics/reports, including fallback records. Assert prompt, raw arguments, raw tool-result content, and credential values are absent too. Two sentinel tests: one through a REAL captured tool-result body (`shiftmind_demonstration`'s `text=label`), one through the write-failure fallback branch.
  - [x] Record a Dev Agent Record mutation table for every new guard: mutate already-green data/code, demonstrate the named failure, restore, and prove green. A first-draft/missing-import failure does not count. See below.

- [x] Task 5 — Document and verify handoff (AC: 2, 6, 7, 8)
  - [x] Update `docs/TESTING.md` with exact opt-in invocation/configuration, finite budgets, pinned binding, default no-network rule, diagnostic redaction, deterministic authority, and joint readiness semantics.
  - [x] Run deterministic multi-turn coverage without a provider, existing evaluation/capability/runtime tests, and the full default backend suite. No live marker may be selected by default. Full suite: 1584 passed, 161 skipped (no local Postgres), 11 deselected (`live` marker), 0 regressions.
  - [x] When a configured provider is available, run the bounded live suite only through the documented explicit command and retain its safe binding report. Classify failures honestly; application defects need an owned-code regression. Run for real this session (by explicit user instruction) against the pinned `anthropic:claude-haiku-4-5-20251001`, key mirrored from `.env` into the test subprocess only (never read or printed by the agent). Found and fixed one real classification bug and one real prompt-ambiguity issue (now passing live); the remaining 4/6 cases show honestly-classified provider variability, not an application defect — see Dev Agent Record.
  - [x] Do not change `gate_a_checks.py` or present a live result as standalone release proof. Record the open Gate B data-floor/release-report decision. Confirmed unaltered. Both deterministic and live multi-turn reports carry `release_gate_eligible: false` / `"Gate B ... remains open"` — the Gate B 50-case floor and release-report decision remain open, unchanged by this story.

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

Claude Sonnet 5 (claude-sonnet-5), via Claude Code.

### Debug Log References

- One-off scratchpad scripts (not committed, session-local): a live-suite runner that mirrors `ANTHROPIC_API_KEY` into `AGENT_RUNTIME_API_KEY` for a single subprocess (never printed; redacted defensively before any output left the process) and a per-case tool-call/result inspector, both used only to diagnose the live-tuning findings below.
- `git stash` / re-run confirmed `tests/test_conversations_api.py::test_execute_turn_emits_claim_to_finalize_telemetry` fails identically on the pre-story baseline commit (`3171ec6`) — a local `AGENT_RUNTIME_MODEL` environment leak (`anthropic:claude-haiku-4-5-20251001` vs. the test's expected `"deterministic"`), the SAME issue Story 5.5's Dev Agent Record already recorded as deferred and unrelated. Deselected from the final full-suite run below; not caused by, or fixed by, this story.

### Completion Notes List

- Ultimate context-engine analysis completed — comprehensive developer guide created.
- Facts, decisions, and self-consistency passes completed. Tasks cite the governing facts/decisions rather than re-arguing them.
- Out of scope: changing the 100-message bound; general raw tool-result persistence; widened authority; durable public-contract changes; default network access; or live evidence presented as deterministic proof.

**Deviation from the File plan's literal path (recorded, not asked — see Task 1):** new multi-turn cases live in `backend/evals/golden_multi_turn/`, a new sibling directory, not inside `backend/evals/golden/`. `evals/cases.py::load_cases()` recursively parses every `.json` under `golden/` as a strict single-turn `GoldenCase` and raises on any field it does not recognize; the multi-turn shape's top-level `turns` field (and per-turn `capabilities`/`history_mode`/etc.) would make every multi-turn file an immediate load error if it lived there. A sibling directory with its own strict loader (`load_multi_turn_case(s)`) keeps both schemas' "reject unknown fields" guarantee intact rather than weakening either one to let them coexist.

**Design summary — how the mechanism actually works:**
- `GoldenTurn`/`MultiTurnGoldenCase` (`evals/cases.py`) extend the schema additively; `ScriptedModelTurn` gained one new optional field (`history_lookup`), so every existing single-turn case file and test is untouched (proven by the full suite below).
- `history_mode: "raw_turn"` reuses the EXACT "owned resume transcript" mechanism `api/routers/approvals.py` already uses to resume a suspended turn after approval — a prior turn's raw `AgentTurnV1` (tool-call/tool-result content preserved verbatim) fed back in as the next turn's `history`. This is what makes a genuine trusted-antecedent proof possible without inventing a second raw-persistence mechanism (Decision 2).
- `history_mode: "rehydrated_activities"` builds real `ActivityItemV1` tuples and drives `execute_turn`'s own `rehydrate_history()` — the ordinary conversational path every other multi-turn production request takes, proving `HISTORY_MESSAGE_BOUND` (durable-but-absent, AC5).
- `evals/doubles.py`'s `HistoryLookupV1`/`_resolve_history_lookup` makes the deterministic double OBSERVE the injected history rather than replay a hardcoded literal: it scans the accumulated framework messages for a prior tool result, `ast.literal_eval`s its stringified content (a resumed transcript stores tool-result content as text), and deep-sets the extracted value into the next scripted call's arguments — raising `UnexpectedModelBehavior` (fail-closed) when the antecedent is absent or an optional consistency check (`require_field`) fails. `history_response_offset_for` fixes the "response-index-only double" defect the story named: without it, a double indexing by `ModelResponse` count across the FULL message list (injected history included) misindexes from a multi-turn case's very first response.
- `evals/report.py::run_multi_turn_case` drives every turn through `execute_turn` (never the single-turn `runtime.run_turn` shortcut), then SCOPES each turn's outcome to only the messages that turn itself added before evaluating (`_trim_outcome_to_current_turn`) — `AgentTurnV1` is explicitly "one or more agent turns," so a raw-resume-transcript turn's outcome legitimately carries every earlier turn's messages too, and evaluating it unscoped would double-count an earlier turn's tool call or misreport an already-granted-then-later-narrowed capability as "unregistered."
- `ToolRoutingEvaluator`/`PolicyOutcomeEvaluator` (Story 2.2/2.9) are reused completely UNCHANGED, via duck typing on `GoldenTurn`'s identically-named fields (Decision 1). One genuinely new check was needed and added as `GoldenTurn.expected_tool_result_names` + a check in `_evaluate_turn`: `ToolRoutingEvaluator` judges only ATTEMPTED tool calls, so an `unauthorized`-antecedent case (whose model still attempts the call, matching `injection-chat-text.json`'s existing precedent) needed a way to prove the attempt was actually REJECTED, not executed — found only by mutation-testing the case (see table).
- Live scoring (`run_source="live"`) excludes exact visible-text/state matching from `_evaluate_turn`'s pass/fail gate, matching the untouched single-turn precedent (`_evaluate_case`/`test_golden_cases_against_live_agent_are_non_authoritative` never calls `_visible_judgement` either) — a real model's prose never reproduces a scripted double's exact wording, and AC7 is about routing/policy fidelity, not verbatim text.
- Task 3's bounded live suite (`LiveSuiteBudgetV1`, `run_bounded_live_multi_turn_suite`, `LiveReadinessExceptionV1`, `generate_bounded_live_multi_turn_report`) and Decision 6's diagnostics redaction (`_safe_diagnostic_record`, `_classify_reason`) are additive; `generate_live_diagnostics`'s existing byte-for-byte test was updated to the new safe shape (an intended behavior change, not a regression — see mutation/test notes).

**Live run against the pinned model (this session, by explicit user instruction) — findings, not application defects:**
Ran the actual bounded live suite against the configured `anthropic:claude-haiku-4-5-20251001` (key mirrored from `.env` into the test subprocess only; never read or printed directly). First run surfaced two real, distinct things:
1. A genuine classification bug in `_classify_reason`: a compound multi-turn reason string can legitimately contain the word "matched" in an early PASSING segment while a later segment is the actual failure, so checking "matched" first misclassified failing verdicts as `"matched"`. Fixed by reordering the classification table (specific failure needles first, "matched" only as the final fallback) and by rewording `_evaluate_turn`'s own `visible_reason`/`results_reason` strings to consistently say "differed" on failure / "matched" on success, mirroring `evaluators.py`'s existing style. Regression-tested (`test_live_diagnostics_flushes_one_result_per_case` caught this immediately).
2. Prompt under-specification in the `dependent-call-success` case: the initial phrasing ("Which worker is assigned to the pick task on Wednesday?" / "Cap that worker's hours...") let the real model explore (wrong filter key guess, then a correct retry; format cleanup on the draft call) rather than route in exactly one call — the same shape of issue Story 5.5's own history records for its single-turn dataset before it reached 26–30/30. Retuned to the single-turn dataset's own successful style (near-literal, explicit tool-shaped prompts, e.g. `evals/golden/scheduling_inspect/wednesday-assignments.json` / `evals/golden/scheduling_draft/valid.json`). Verified: after retuning, `dependent-call-success` and `dependent-call-missing-antecedent` pass live outright — including turn 2 correctly citing the worker id it was never told in its own prompt, extracted by the REAL model from the replayed raw resume transcript (not the double's `HistoryLookupV1`, which is deterministic-only machinery; this is the actual product mechanism working end-to-end against a real provider).

Remaining live variance (`stale-antecedent`, `truncated-antecedent`, `unauthorized-antecedent`, `long-history-window` did not reach 100% routing match in this run) is genuine **provider variability / prompt ambiguity** per Task 5's own instruction to classify honestly rather than mislabel as an application defect: `stale`/`truncated`'s turn-2 prompts were intentionally left unretuned (their point is the double's fail-closed guard, not a live pass), and the remaining cases hit ordinary LLM non-determinism (occasional extra self-correction) that `ToolRoutingEvaluator`'s exact-match oracle is designed to catch and that Decision 7 explicitly forbids loosening to hide. This is the expected, disclosed shape of a FIRST live run of a brand-new dataset — matching Story 5.5's own retro precedent — not a defect in this story's application code, and it does not gate story completion: the deterministic suite (`generate_multi_turn_demonstration_report`, `run_multi_turn_case` on all six cases) remains the authoritative evidence and is 100% green. Further live-prompt tuning toward Gate B eligibility is left as follow-up, exactly as the story's own "Origin, outcome, and scope" section anticipates ("does not decide the unresolved 50-case dataset floor").

### Mutation Table

One row per new guard, per Task 4's requirement: the guard was green, made to fail by mutating already-FINISHED product code/data (never a first-draft or import-error red), observed failing for the stated reason, then restored and re-proven green. All four are executable as pytest tests in `TestMultiTurnMutationGuards` (`backend/tests/test_evaluation_harness.py`).

| # | Guard | Mutation applied to real code/data | Before (green) | After (red) — reason | Restored |
| - | ----- | ----------------------------------- | --------------- | --------------------- | -------- |
| 1 | `HistoryLookupV1`/`_resolve_history_lookup` actually extracts the antecedent, not a hardcoded literal | Monkeypatched `evals.doubles._resolve_history_lookup` to return the turn unchanged (pretend nothing was ever observed), on `multi-turn-dependent-call-success` | `passed=True` | `passed=False`; turn 2 reason: `"tool arguments differed"` (actual `record_id: null` vs. expected `"w1"`) | `monkeypatch.undo()`; re-run green |
| 2 | `execute_turn`'s `HISTORY_MESSAGE_BOUND` slice is genuinely enforced on the `raw_turn` (already-owned `AgentTurnV1`) branch, not just the `rehydrate_history` one | Monkeypatched `application.use_cases.execute_turn.HISTORY_MESSAGE_BOUND` from 100 to 1000, on `multi-turn-dependent-call-truncated-antecedent` | `passed=True` (antecedent correctly absent post-truncation, case fails closed as designed) | `passed=False`; turn 2 reason: `"tool-call count differed"` — the antecedent SURVIVES the widened window and the call wrongly succeeds | `monkeypatch.undo()`; re-run green |
| 3 | The capability-grant boundary (installed-but-ungranted) actually blocks execution, not just the routing evaluator's attempt-match | Constructed a case variant granting BOTH `scheduling_inspect` and `scheduling_draft` on turn 2 (no monkeypatch — a separate case object; original untouched), on `multi-turn-dependent-call-unauthorized-antecedent` | `passed=True` (call attempted, `expected_tool_result_names: []` — no result produced) | `passed=False`; turn 2 reason: `"tool results differed"` (expected `()`, actual `('scheduling_draft',)` — the capability actually EXECUTED once wrongly granted) | No undo needed (separate object); original case re-run green |
| 4 | The `require_field` staleness consistency check is what makes `stale-antecedent` fail closed, not incidental absence | Monkeypatched `evals.doubles._resolve_history_lookup` to strip `require_field` before delegating to the real implementation, on `multi-turn-dependent-call-stale-antecedent` | `passed=True` | `passed=False` (the stale value is now accepted and the draft is wrongly created) | `monkeypatch.undo()`; re-run green |

No guard in this story was found impossible to mutate; none required an honest-gap row.

### Verification Evidence

- Focused: `uv run pytest tests/test_evaluation_harness.py tests/test_execute_turn_use_case.py tests/test_agent_runtime_adapter.py` → 169 passed, 2 deselected (`live`).
- Full default suite: `uv run pytest` → **1584 passed, 161 skipped (no local Postgres in this environment), 11 deselected (`live` marker), 0 regressions.** One additional failure exists on `main`/baseline and is unrelated (see Debug Log References): `test_conversations_api.py::test_execute_turn_emits_claim_to_finalize_telemetry`.
- Live (opt-in, this session): `uv run pytest -m live tests/test_evaluation_harness.py::test_golden_cases_against_live_agent_are_non_authoritative` → PASSED (single-turn dataset, unaffected by this story). The new `test_live_multi_turn_suite_is_bounded_and_non_authoritative` ran for real against the pinned model; see the live-run findings above — 2/6 cases pass outright, 4/6 show disclosed provider variability, so `readiness` correctly reports `"blocked"` (not `"eligible"`) on this run, which is the honest, correct signal per AC7 rather than a defect to paper over.

### File List

- `_bmad-output/implementation-artifacts/5-6-evaluate-real-provider-multi-turn-history-and-tool-continuity.md`
- `backend/evals/cases.py` — `HistoryLookupV1`, `GoldenTurn`, `MultiTurnGoldenCase`, loaders, strict field validation (additive; single-turn `GoldenCase` schema unchanged).
- `backend/evals/doubles.py` — `HistoryLookupV1` resolution, `history_response_offset_for`, `build_scripted_double`/`build_multi_turn_double` (additive; `build_model_double`'s single-turn behavior unchanged).
- `backend/evals/report.py` — `run_multi_turn_case`, `_trim_outcome_to_current_turn`, `_evaluate_turn`, `build_multi_turn_evaluation_report`, `write_multi_turn_evaluation_report`, `generate_multi_turn_demonstration_report`, `LiveSuiteBudgetV1`, `LiveReadinessExceptionV1`, `run_bounded_live_multi_turn_suite`, `generate_bounded_live_multi_turn_report`, `_safe_diagnostic_record`, `_classify_reason`; `generate_live_diagnostics` rewritten to persist only redacted metadata (Decision 6).
- `backend/evals/golden_multi_turn/history_and_tools/dependent-call-success.json` (added)
- `backend/evals/golden_multi_turn/history_and_tools/dependent-call-missing-antecedent.json` (added)
- `backend/evals/golden_multi_turn/history_and_tools/dependent-call-stale-antecedent.json` (added)
- `backend/evals/golden_multi_turn/history_and_tools/dependent-call-truncated-antecedent.json` (added)
- `backend/evals/golden_multi_turn/history_and_tools/dependent-call-unauthorized-antecedent.json` (added)
- `backend/evals/golden_multi_turn/history_and_tools/long-history-window.json` (added)
- `backend/tests/test_evaluation_harness.py` — new multi-turn schema/double/harness/mutation/redaction/budget/live-suite test coverage; one pre-existing test (`test_live_diagnostics_flushes_one_result_per_case`) updated to the new redacted diagnostics shape.
- `backend/tests/test_execute_turn_use_case.py` — one new focused test for the previously-untested `raw_turn` (already-owned `AgentTurnV1`) truncation branch.
- `backend/tests/test_agent_runtime_adapter.py` — inspected, no change needed (`agent/runtime.py`/`agent/translate.py` were not touched by this story).
- `docs/TESTING.md` — new "Agent evaluation harness" section documenting both dataset shapes, the deterministic/live commands, budgets, and diagnostic redaction.
