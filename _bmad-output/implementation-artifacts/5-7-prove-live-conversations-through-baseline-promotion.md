# Story 5.7: Prove Live Conversations Through Baseline Promotion
---
baseline_commit: 80e62422b68a9c121697fada6287f4fa3a311532
---

Status: in-progress

Date: 2026-09-15
Origin: Minh's reported natural-conversation failure and approval to correct course.
Priority: Epic 5 release blocker; before the next Gate B assessment.

## Story

As a planner,
I want natural conversations to remain useful through investigation, proposal revision, real
optimization, and explicit baseline approval,
so that the demonstrated AI workflow works beyond isolated tool-routing prompts.

[Source: `_bmad-output/planning-artifacts/epics.md` — Story 5.7]

## Outcome

As a planner, I can hold a natural conversation with ShiftMind, create and revise a persisted proposal, run the real solver, review its schedule, and propose and explicitly approve that candidate as the operational baseline without losing context or receiving invalid output.

The reported failure is NOT yet reproduced or fixed by this planning change. Story 5.6's six two-user-turn cases remain historical evidence for their narrow scope, not proof of this outcome.

## Facts this story depends on

Named here because each is either the reason a scenario turn is expected to behave a certain way, or a boundary the implementation must not cross without a separate decision. Re-verify each at Task 1 rather than trusting the date below.

| Fact | Citable source / anchor | Consequence |
| --- | --- | --- |
| The installed-tool inventory is a literal, statically reviewed tuple of exactly six capability modules — `scheduling_compute`, `scheduling_draft`, `scheduling_inspect`, `scheduling_optimize`, `scheduling_baseline`, `demonstration` — composed by a function, never discovered at runtime. | `application/capabilities/installed.py::_INSTALLED_FACTORIES` / `installed_modules()` | AC3's inventory denominator is these six modules' manifests plus their supported operations; a seventh module or a changed operation is a source change this story's binding must re-detect, not assume. |
| **LOAD-BEARING FINDING, measured at creation.** The HTTP execute-turn endpoint's suspended→approval-request bridge hardcodes acceptance of exactly one capability. `execute_agent_turn`'s `_finish()` (`api/routers/conversations.py:365-366`) raises a bare `RuntimeError("suspended turn requested an unsupported approval capability")` for any suspended tool call whose name is not `SCHEDULING_BASELINE_CAPABILITY`. `demonstrate()`'s own test (`tests/test_demonstration_capability.py::test_an_unapproved_repetition_suspends_the_run_through_the_real_runtime`) proves the runtime legitimately suspends on `shiftmind_demonstration` with `repeat > 1` — so Scenario G turn 4 ("Now repeat the same label twice"), driven through the real HTTP path, is measured to hit this `RuntimeError` today, not a graceful refusal. | `api/routers/conversations.py:358-427`; `application/capabilities/demonstration.py::demonstrate` (approval branch); `tests/test_demonstration_capability.py` | This is exactly the gap AC3/Scenario G already named ("If the installed demonstration capability has no end-to-end execution path, report it as a coverage/product gap; a refusal-only trace cannot prove its successful operation") — it is not a new discovery to make during dev, it is confirmed. See Decision 1 below for the scoping call this does NOT make for you. |
| `RequestApprovalCommandV1` and the whole `ApprovalBindingV1`/`approval_request` persistence path are schedule-run-shaped by contract, not generic: `schedule_run_id: UUID` (non-nullable) and `expected_baseline_schedule_version` are load-bearing fields with no capability-agnostic equivalent. | `application/use_cases/request_approval.py::RequestApprovalCommandV1`; `application/contracts/approval_binding.py` | Making the suspend→approval bridge capability-agnostic is an AD-20 contract change (compatibility evidence required), not a narrow bug fix — weigh this before choosing to fix vs. document Scenario G's gap (Decision 1). |
| A real, production-shaped composed stack already exists and already proves the exact draft → real solver → candidate → approval → baseline-promotion journey end to end over real HTTP, once — `backend/tests/compose_proof.py::test_one_command_stack_serves_real_oidc_and_worker`. It drives one live-agent-eligible conversational turn through the deterministic model, then the rest of the journey (draft persistence, `POST /api/v1/schedule-runs`, terminal-status poll, `POST /api/v1/approvals`, `POST /api/v1/approvals/{id}/decision`, `GET /api/v1/approvals/provenance`) through direct authenticated HTTP commands with `Idempotency-Key`/`X-CSRF-Token` headers, against a real `docker compose up --build` stack it starts and tears down itself. | `backend/tests/compose_proof.py` (pytest marker `compose`; file name does not match `test_*.py`, so it is never auto-collected — run it by its explicit path) | This is the load-bearing precedent for AC4/AC5's "real stack" journey: extend/parallel this shape for conversational turns rather than reinventing composed-stack orchestration. It also hands you the exact route sequence, header requirements, and terminal-status polling pattern already proven to work. |
| The composed stack already ships a real production worker runtime factory (`SHIFTMIND_WORKER_RUNTIME_FACTORY: worker.composition:create_runtime`, `docker-compose.yml`) and already passes `AGENT_RUNTIME_MODEL`/`AGENT_RUNTIME_API_KEY` (or `ANTHROPIC_API_KEY`) through from the host environment to both `api` and `worker`. The default is the keyless `deterministic` model; `docs/GETTING-STARTED.md` documents the exact override: `AGENT_RUNTIME_MODEL=anthropic:claude-haiku-4-5-20251001 ANTHROPIC_API_KEY=… docker compose up -d --build`. | `docker-compose.yml`; `docs/GETTING-STARTED.md:28-39`; `backend/settings.py:29` (`_ANTHROPIC_DEFAULT_MODEL = "claude-haiku-4-5-20251001"`) | No new deployment composition is owed. AC5's "configured deployment provider/model" and "do not silently substitute the previously pinned Haiku model" mean: read the pin from settings/`.env.example` at Task 1 rather than hardcoding `claude-haiku-4-5-20251001` from this note — confirm it is still current. |
| **Every existing Playwright spec runs against a stubbed backend.** `frontend/playwright.config.ts`'s `webServer` always starts `vite preview` (a static build with no API), and `frontend/e2e/support/apiStubs.ts` intercepts every `**/api/v1/**` call. No existing spec (including `repair-journey.spec.ts`) ever visits a real API, worker, database, or LLM provider. | `frontend/playwright.config.ts`; `frontend/e2e/support/apiStubs.ts` | AC5's "no API stubs" real-browser requirement needs NEW browser-test infrastructure pointed at the composed stack (mirroring `compose_proof.py`'s docker-compose lifecycle, not `vite preview`) — it cannot reuse the existing `playwright.config.ts` webServer as-is. Decide the shape (separate config vs. per-spec override) during implementation; this is an infrastructure gap, not a defect. |
| Gate B has no code-level aggregator. Unlike Gate A (`backend/scripts/gate_a_checks.py`, `backend/tests/test_gate_a_readiness.py`), there is no `gate_b_checks.py` and no script generates `evidence/epic-5/release-gate-report.json` today — `backend/scripts/evidence_binding.py`'s own docstring names that path only as a documented FUTURE consumer. | `backend/scripts/evidence_binding.py:1-8`; repo-wide grep for `release_gate_report`/`gate_b_checks` (zero `.py` hits outside `evals/report.py`'s per-report fields and this file's own tests) | "Wire a required `live_conversation_journeys` verdict into the existing Gate B assessment" (implementation task 9) means: emit a versioned, bound evidence report under `evidence/story-5.7/` whose `readiness`/verdict field a FUTURE, separate Gate B assessment step will read — it does NOT mean building a new `gate_b_checks.py` aggregator, which is out of this story's scope. |
| The existing eval harness (`backend/evals/report.py`/`cases.py`/`doubles.py`, Stories 5.5/5.6) drives conversations by calling `execute_turn(runtime, deps, ...)` directly, in-process, against ad hoc `AgentDepsV1`/`AgentTurnV1` values it constructs. It does not go through `ConversationRepository`, session auth, CSRF, or the `/execute` HTTP endpoint's claim/finalize transaction boundary. | `backend/evals/report.py::run_multi_turn_case`; `api/routers/conversations.py::execute_agent_turn` | AC5 requires the "authenticated application conversation path" — the eval harness's in-process shape and `compose_proof.py`'s HTTP-driven shape are two different seams with different reuse costs. Decide which one Story 5.7's assertions actually drive through at Task 1; do not assume the eval harness's existing runner already satisfies AC1/AC2/AC4/AC5 just because it is the newest multi-turn mechanism. |
| Demand/unit dimensional rules are fixed and documented, not derivable from adapter code: `outbound`/`inbound` demand is `volume` (read via `required_demand_volume`), `indirect` is `headcount` (read via `required_headcount_minutes`), staffed time comes from assignments (`staffed_minutes`, family-agnostic — passing `family` to it is a caller error), and a headcount/staffing question about `outbound`/`inbound` work is answered from assignments, not demand — it is NOT an invalid question. | `docs/DOMAIN-MODEL.md` (normative; do not re-derive) | Governs every Scenario C oracle/grounding check (turns 2-12: units, worker-minutes, staffed minutes, qualified-worker counts, "can these be added together") and Scenario A turn 3's `how many worker are therre?` clarification (workers vs. tasks, not a family question). |
| Measured at creation (`80e6242`, clean tree except two untracked, unrelated artifacts — `.1devtool/`, `rosterai-schema.sql`): backend default `1780 passed, 1 failed, 2 skipped, 10 deselected` (`live` marker); `-m postgres` `160 passed, 1633 deselected` — both total 1793, confirming Postgres-marked tests run inside the default suite; `test_evidence_convention.py` 99 passed; `tests/architecture/` 79 passed; `test_gate_a_readiness.py` 44 passed; frontend Vitest 85 files/648 tests; Playwright 80 tests/10 files. The one backend failure (`test_conversations_api.py::test_execute_turn_emits_claim_to_finalize_telemetry`) is the SAME pre-existing, unrelated local `.env` `AGENT_RUNTIME_MODEL` leak Stories 5.5/5.6 already documented and deferred — do not attribute it to this story. | This session's measurement; `_bmad-output/implementation-artifacts/sprint-status.yaml` (5.7 creation note) | Re-derive before attributing any red test to this story; these numbers are a floor to diff against, not a target. |

## Acceptance criteria

1. **Reproduce first.** Run the exact opening `HI my name is Minh` → `how can you help me?` → `how many work are therre?` through the configured real provider and authenticated application conversation path. Capture visible output, terminal state, and safe error/validation metadata at each turn. The supplied example fails at the third user message; the report also describes failures at four or more turns. Investigate both rather than assuming a turn-count threshold. Clarifying whether “work” means workers or tasks is acceptable; invalid output, fabricated counts, an empty answer, or irrelevant generic help is not. If it does not reproduce, retain the attempted runs and continue deeper variants; do not claim a fix.
2. **Progressive real conversations.** Implement at least eight distinct scenarios from `live-conversation-scenarios-5-7.md`, with varied lengths of 6, 7, 8, 10, 12, 14, 16, and 20 USER turns, including at least one full 20-turn conversation, and five scenario-specific independent prefix tests each. This is at least 40 tests and 273 user-turn executions per full run. Each prefix starts from a fresh conversation and isolated fixture state and actually sends every preceding user message. Assistant responses, tool results, and history are generated by the real application during that execution. No canned assistant history, synthetic activity padding, direct history insertion, forced tool-choice, or prompts containing schema instructions to make routing pass. Scenario branches can use names and choices actually exposed to the planner; never inject hidden tool IDs into user prose.
3. **Complete tool coverage.** Generate an inventory from `installed_modules()`, current manifests, contracts, and production grant composition. Cover every installed tool and its supported operations, not just capability families. Bind the inventory digest to the report; a newly installed or changed uncovered operation fails coverage. Record availability, attempted calls, successful results, and verified effects separately. Disabled/unreachable tools remain explicit gaps, never disappear from the denominator. Exercise them in an isolated configuration through legitimate application grants; if no supported path exists, report a blocking implementation gap rather than bypassing authority. Include application commands and UI actions as separate coverage rows so a manual command cannot masquerade as an LLM tool call.
4. **Primary successful journey.** Through a natural conversation, inspect the scenario, resolve a worker/task, create and revise a real persisted draft, explicitly run optimization through the supported application action, wait for the real worker/CP-SAT result, inspect a feasible candidate and its assignments/evidence, compare it with the current baseline, and have the agent propose baseline approval. Use the authenticated approval control to approve in an isolated test environment. Verify the exact candidate becomes the baseline, its version changes once, its assignments can be read after reload, and provenance joins the conversation, proposal, run, candidate, approval, and audit. Before approval, verify that the baseline has not moved. Cover both initial promotion and replacement of an existing baseline through scenario variants. A queued job, draft card, or text saying “done” is insufficient.
5. **Real stack and browser evidence.** Use the configured deployment provider/model, application-owned persisted history, production capability registration, real database adapters, API, worker, and solver. Run the full matrix through the authenticated application path. Additionally drive the reproduction and primary journey in a real browser against that stack, with no API stubs or fabricated stream events; verify displayed replies/cards, reload continuity, and no “Invalid output” state. API tests alone cannot establish the browser result. Record provider, model, endpoint identity without credentials, configuration digest, and deployed image/code versions; do not silently substitute the previously pinned Haiku model for the current configuration.
6. **Meaningful per-turn verdicts.** Evaluate relevant, nonempty answers or appropriate clarification/refusal; grounded numerical facts and units; remembered in-window user context; correct entity references; actual calls and results; persisted draft contents; and durable workflow effects. Compare facts and effects with independent application/fixture reads. Evaluate semantic obligations rather than exact assistant wording or one brittle call sequence. Record allowed alternatives before running. A missing required answer, fabricated schedule, generic completion, swallowed invalid output, or false claim that an action succeeded fails. A separately configured LLM-as-judge must assess conversational quality using the rubric below, but cannot override factual/effect checks; uncertain judgments require explicit review and are not automatic passes.
7. **Live failures block completion and release.** Require three consecutive complete runs of the full matrix on the same code/configuration/dataset after fixes, plus the live browser journeys. At the minimum size this is 120 prefix executions / 819 user turns, before browser runs, extensions, and reruns. All required tests must pass; no skipped, missing, budget-truncated, or unreachable required coverage counts as green. Preserve first-attempt failures and configured automatic retries; report recovered turns separately. Record all run IDs, including unsuccessful runs, rather than selecting three successes. A failing run restarts the consecutive-success count. Three clean runs are bounded acceptance evidence, not a statistical reliability guarantee. No existing release-exception mechanism may mark this story complete or the required live-conversation gate passed.
8. **Evidence and runnable handoff.** Provide one documented explicit command/configuration to run the matrix and browser journeys, and a version-bound report under `evidence/story-5.7/`. Enforce finite per-turn and aggregate request/tool/token/time/spend budgets and stop as incomplete at exhaustion. Report scenario, prefix, repetition, first failed turn, expected semantic outcome, safe actual outcome, tool/operation coverage, first-attempt/retry results, and verified resource/effect identifiers. Persist only sanitized planner-visible transcripts of these authored test scenarios and necessary assertions in dedicated local test evidence; never provider payloads, hidden reasoning, credentials, or unrelated conversations. Keep production telemetry content-disabled. Version/redact transcript artifacts and bind their digests. Fix discovered product defects at their owning layer and rerun the failing live scenario and complete live matrix. Existing deterministic checks remain useful regression safeguards, but cannot satisfy any missing live criterion.

## How answers are judged

Use two required layers on the actual live trace. Assertions verify the live result; they do not replace the live model with a double.

| Layer | Inputs and checks | Verdict |
| --- | --- | --- |
| Facts and effects | Independently read selected fixture/version, computed metrics and units, actual tool events, persisted proposal constraints, solver result/assignments, approval state, baseline pointer and audit. Compare these with the assistant's claims. | Any incorrect number/unit/entity/version, unsupported claim, missing required effect, false completion claim or unauthorized effect fails. A judge cannot override it. |
| LLM-as-judge | Give a separate configured judge the user-visible conversation so far, current request/reply, expected semantic obligations, and sanitized verified facts/effects. Grade relevance, context continuity, completeness and appropriate clarification/refusal. Do not expose future messages or an ideal scripted assistant answer. | Return per-dimension scores, cited message/evidence IDs, concise reasons, and pass/fail/uncertain. Missing or malformed judgment is incomplete, not pass. |

Grade each applicable semantic dimension 0–2: **0** wrong/missing/contradictory; **1** partial or ambiguous; **2** meets the stated obligation. Relevance means addressing this request; continuity means using the correct preceding entity and decisions; completeness means supplying the requested information/action or explaining a legitimate blocker; clarification/refusal means resolving material ambiguity without unnecessary questions or invented authority. Mark a dimension not applicable only when the predeclared turn rubric permits it. Automatic semantic pass requires 2 in every applicable dimension; an average cannot hide a failed dimension. Human review may resolve an uncertain/contested semantic grade with a recorded reason, but cannot override a factual/effect failure.

Examples:

- “There are 24 workers” when the selected fixture has 18: fail regardless of fluency or judge score.
- “The draft is saved” without a persisted proposal: fail even if the tool was attempted.
- “Do you mean workers or tasks?” after “how many work are therre?”: acceptable clarification, provided no incorrect count/action is asserted.
- A valid response that repeats the welcome message instead of answering a clear follow-up: semantic failure.
- A tool error accurately explained is not a hallucinated success, but still fails a scenario that requires successful draft/solver/baseline completion.

Judge reliability is itself an implementation obligation. Pin a judge model separately from the application model, preferably from a different model family; record provider/model, rubric/prompt versions, settings, usage and budget. Treat transcript text as quoted untrusted data, not instructions to the evaluator. Before relying on automatic semantic passes, calibrate on a human-reviewed set drawn from these scenarios containing good answers, wrong facts, wrong antecedents, irrelevant replies, misleading completion claims and unnecessary refusals. Publish judge/human disagreements and false passes; review all critical failures and uncertain cases, plus a sample of passes. Until calibration is reviewed, automatic grades remain provisional. Do not claim that a different judge model alone guarantees independence or correctness.

Report a final turn pass only when required factual/effect checks AND semantic review pass. A conversation passes only if every required turn and its final persisted outcome pass. Include final journey-level review so individually plausible replies cannot hide failure to complete the requested workflow. Judge cost/time belongs in the explicit suite budget, reported separately from the agent's usage.

This design accounts for known judge limitations such as verbosity and self-enhancement bias; see [Zheng et al., Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685). It is a proposed implementation protocol, not a claim that the judge has already been calibrated.

## Inventory known at planning time

Re-derive this list during implementation; it is not a frozen coverage denominator.

| Installed capability | Required coverage |
| --- | --- |
| `scheduling_inspect` | Every supported fact group plus filtering, sorting, bounded pagination/counts and applicable empty/invalid-query behavior. |
| `scheduling_compute` | `required_headcount_minutes`, `required_demand_volume`, `staffed_minutes`, `qualified_worker_count`; relevant family/unit/filter combinations and unsupported-dimension handling. |
| `scheduling_draft` | `set_min_workers_per_task`, `scale_demand`, `lock_worker_shift`, `exclude_worker_from_task`, `set_max_hours`; creation, revision, entity clarification, and invalid/stale requests. |
| `scheduling_optimize` | Explicitly authorized start, actual successful candidate, invalid/stale input and idempotent replay; tool invocation and UI/API run command are distinct evidence. |
| `scheduling_baseline` | Agent-proposed exact approval, initial/replacement promotion, rejection and stale/reused request behavior through real approval commands. |
| `shiftmind_demonstration` | Its label/repeat behavior, bounds, grant and approval behavior in a legitimate isolated test configuration. Its presence in the installed set must not be silently ignored. |

Run status/results, comparison, approval decisions, cancellation/retry, and provenance may be application operations rather than separately registered tools. Map their actual implementation before assigning coverage; do not invent tool names or count direct commands as tool executions.

## Decisions and developer guardrails

1. **Scenario G's repeat-twice turn is a reported coverage gap, not a silent skip or an invented fix — unless reproduction changes this call.** The Facts table's demonstration/`RuntimeError` finding is measured, not assumed. AC3 already provides the escape hatch for exactly this shape ("if no supported path exists, report a blocking implementation gap rather than bypassing authority"). This does NOT cover the alternative of widening `ApprovalBindingV1`/`request_approval` to a generic capability-agnostic shape — per AD-20, that is a durable-contract change requiring compatibility evidence, and Story 5.6's own Decision 1 set the applicable precedent ("out of scope unless an existing deterministic test proves the contract cannot represent the approved case"); this story's Boundaries section separately forbids unrelated scope expansion (new model authority, production baseline mutation) that a naive fix could drift into. If reproduction shows a cheaper, non-contract-changing fix at the `_finish()` dispatch site (e.g., a narrow allow-list extension that still writes through the existing `schedule_run`-shaped table only for the baseline capability and returns a safe refusal for every other suspended capability instead of raising `RuntimeError`), that is in scope; a new approval table or contract is not.
2. **Drive the required-live-conversation matrix through the authenticated HTTP conversation path, not the `evals/` in-process harness.** AC1/AC2/AC4/AC5 all specify "authenticated application conversation path" / "application-owned persisted history" / production capability registration — properties the existing `run_multi_turn_case`/`execute_turn(runtime, deps, ...)` in-process shape does not exercise (no session, no CSRF, no `ConversationRepository`, no HTTP claim/finalize transaction). This does NOT mean `backend/evals/` is irrelevant: its `GoldenCase`/answer-type/evaluator machinery, budget accounting shape (`LiveSuiteBudgetV1`), and redaction discipline (`_safe_diagnostic_record`) are still the right patterns to reuse for scoring and reporting — only the turn-execution seam changes, from calling `execute_turn` directly to calling it through `POST /conversations/{id}/messages` + `POST /conversations/{id}/agent-runs/{id}/execute` (or the compose_proof.py HTTP-client shape) against a real, authenticated session.
3. **The real-browser requirement needs new Playwright infrastructure pointed at the composed stack; it cannot reuse `playwright.config.ts` as committed.** The existing config's `webServer` always launches `vite preview` with no backend, and every spec imports `apiStubs.ts`. This does NOT cover replacing the existing stubbed suite (3.12's `repair-journey.spec.ts` and friends remain valid, fast, stub-based regression coverage) — add a separate, explicitly-invoked browser-test path (own Playwright project/config or a dedicated spec with its own `webServer`/`baseURL`) that drives `docker compose up` (mirroring `compose_proof.py`'s lifecycle) and never imports `apiStubs.ts`.
4. **Gate B verdict wiring means an evidence field, not a new aggregator.** Emit `readiness`/`live_conversation_journeys`-shaped fields inside this story's own `evidence/story-5.7/**` report(s), following the `release_gate_eligible`/`release_gate_status` shape Story 5.6 already established in `evals/report.py`. This does NOT cover building `gate_b_checks.py` or generating `evidence/epic-5/release-gate-report.json` — no code produces that file today, and doing so is a future, separate Gate B assessment exercise this story only precedes.
5. **Budgets are per-suite-run, not per-story-lifetime.** Reuse Story 5.6's per-turn accounting shape (`LiveSuiteBudgetV1`: case count, total requests, total tool calls, total tokens, elapsed seconds, spend USD, all required-positive-finite, checked after every turn) for the new matrix runner. This does NOT cover reusing the exact same class unmodified — the new runner drives roughly 3-7x more turns per full run (273 vs. 12) and adds real solver wait time and browser actions, so the ceilings themselves need re-deriving for this story's shape, not copied verbatim from 5.6's values.
6. **Fixture and fixture-entity selection must be real, not synthesized.** Every worker/task/schedule name a scenario references (Scenario B/E/F/H's "that worker", "the first task you listed") must resolve against `sample_tiny_input` or the repository's other immutable fixture through a real inspect turn or real projection read — never a hand-typed UUID or invented name. This does NOT cover requiring the SAME fixture across all eight scenarios; different scenarios may use different fixture entities as long as each is real and the selection is recorded.
7. **Tool/operation coverage completeness is a programmatic assertion, not a manual checklist.** AC3's "bind the inventory digest to the report; a newly installed or changed uncovered operation fails coverage" only has teeth if something computable enforces it. Write a check (a test, or a report-generation step that raises) that derives the full capability+operation inventory fresh from `installed_modules()` — the same way the evidence report does, never a hand-copied list — and fails if any inventory entry has zero coverage rows in the report. This does NOT mean every row must show a *successful* result: Decision 1's demonstration-repeat-twice finding is a valid terminal state for its row (an explicitly reported gap, per AC3's own escape hatch) — the check fails on an ABSENT row (no attempt recorded at all, or a capability silently missing from the report), not on an honestly reported gap. It also does NOT replace AC7's live-run pass/fail gate — a coverage-complete report can still fail on facts, effects, or semantics; this check only prevents a report from claiming completeness while silently omitting an installed capability or operation.

## Implementation tasks

- [ ] Discover current startup/configuration and browser/authentication paths; record baseline commit and tool/operation inventory without printing secrets. (AC: 1, 3, 5 — per Facts: re-derive the pinned model, the six-module inventory, and the measured test baseline rather than trusting this file's numbers.)
- [ ] Reproduce the supplied conversation live and preserve the first failing observation; inspect validation/history/translation/runtime/UI only as evidence directs. (AC: 1)
- [ ] Turn the scenario catalogue into versioned executable user-message sequences and explicit semantic/effect expectations. Select valid fixture entities and feasible parameters; add variants until every inventory row is exercised. (AC: 2, 3, 6 — per Decision 6 on fixture-entity selection.)
- [ ] Extend the existing evaluation/report infrastructure for persisted application conversations and independent prefixes. Share version bindings and budget accounting; do not force real journeys through doubles or introduce a competing definition of readiness. (AC: 1, 2, 4, 5, 8 — per Decisions 2 and 5.)
- [ ] Implement per-turn assertions and actual tool/operation coverage, and the priority draft/solver/baseline journey with isolated database state. (AC: 3, 4, 6)
- [ ] Write the coverage-completeness guardrail: derive the capability+operation inventory fresh from `installed_modules()` and fail (not warn) if any entry has zero coverage rows in the report. Demonstrate it failing first — drop one scenario's coverage of a real operation, observe the guardrail catch it, restore. (AC: 3 — per Decision 7; this is the mechanism that makes AC3's "a newly installed or changed uncovered operation fails coverage" true rather than aspirational.)
- [ ] Add live browser reproduction and full journey with reload; exercise explicit Run optimization and Approve as baseline controls. (AC: 5 — per Decision 3; reuse `compose_proof.py`'s lifecycle, not `playwright.config.ts`'s stubbed one.)
- [ ] Diagnose and fix product failures, retaining meaningful focused regression checks where useful. Preserve observed failures; do not weaken the scenario to make a report green. (AC: 1, 6, 8 — per Decision 1 for the demonstration-approval finding specifically.)
- [ ] Execute three complete consecutive live matrix runs plus browser evidence after the final relevant change. Aggregate failures and partial results honestly. (AC: 7)
- [ ] Wire a required `live_conversation_journeys` verdict into the existing Gate B assessment. Missing/currently stale evidence blocks it. Publish the exact runnable command and measured results in `docs/TESTING.md`. (AC: 8 — per Decision 4; also correct `docs/GETTING-STARTED.md:28`'s now-false "Live-provider output is optional and never required release evidence" line, per AD-16's 2026-09-15 correction.)

## File plan

Investigation map, not a diagnosis — locate the actual files during implementation and correct this table in the Dev Agent Record if it is wrong.

| Area | Likely action | Why |
| --- | --- | --- |
| `backend/evals/` (`report.py`, `cases.py`, `doubles.py`, `evaluators.py`) | Extend | Reuse budget/redaction/report shape per Decision 5; the turn-execution seam changes per Decision 2. |
| `backend/tests/` (new coverage-completeness test) | Add | Fresh-derives the inventory from `installed_modules()` and fails on any zero-coverage entry (Decision 7); needs a demonstrated-red proof per this repo's standing red-then-green guard convention. |
| `backend/tests/compose_proof.py` or a sibling | Extend or add | The measured precedent for a real-composed-stack, real-HTTP journey (Facts table). |
| `api/routers/conversations.py` | Inspect; narrow fix possible | The `_finish()` suspend-approval dispatch (Decision 1). |
| `application/capabilities/demonstration.py` | Inspect only, unless Decision 1's narrow fix is taken | Confirm the approval-required branch's actual behavior before deciding. |
| `frontend/e2e/` (new file(s), NOT `apiStubs.ts`-based) | Add | Real-browser, no-stub journey (Decision 3). |
| `frontend/playwright.config.ts` | Inspect; likely a new project/config, not an edit to the stubbed default | Preserve existing stubbed regression coverage. |
| `docs/TESTING.md` | Update | Currently states the live-conversation matrix is "planned, not implemented" — must change once implemented. |
| `docs/GETTING-STARTED.md` | Correct | Line 28's "optional and never required" claim is false after this story ships (AD-16 2026-09-15 correction). |
| `evidence/story-5.7/**` | Add | Version-bound matrix + browser evidence (AC8), following `docs/EVIDENCE-CONVENTION.md`: commit code, then measure, then generate via `backend/scripts/evidence_binding.py`, then commit evidence separately. |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | Update | Story status transitions; Gate B remains a separate future assessment. |

No change to `backend/domain/**`, `backend/engine/**`, `backend/store/**` (legacy), migrations, or durable public contracts is authorized by this story unless a deterministic regression proves an owning defect there (Boundaries section).

### Project Structure Notes

- Backend tests are named `test_*.py` under `backend/tests/` per `docs/TESTING.md`'s own convention — a new "drive real HTTP conversations against the composed stack" test module belongs there, named for what it proves (not for the story number).
- `backend/tests/compose_proof.py` is a deliberate, established EXCEPTION to that naming convention: it does not match `test_*.py` on purpose, so `pytest`'s default collection never picks it up and it must be invoked by its explicit path (`pytest tests/compose_proof.py -m compose`). Any sibling this story adds for the same "opt-in, builds and runs the full stack" shape should follow the same non-`test_*.py` naming for the same reason, not be renamed into default collection.
- `backend/evals/golden_multi_turn/<family>/*.json` is the established location/shape for versioned multi-turn case data (Story 5.6). If the new work is expressed as golden cases rather than ad hoc scripts, a new sibling directory under `backend/evals/` (not `golden/` or `golden_multi_turn/`, whose loaders are strict and reject unrecognized shapes) is the precedent to follow, per Story 5.6's own recorded deviation.
- Frontend e2e specs are flat under `frontend/e2e/*.spec.ts` with shared helpers in `frontend/e2e/support/`. A new real-backend spec belongs in the same `e2e/` directory (for `npx playwright test --list` to still enumerate it) but must not import `e2e/support/apiStubs.ts`; if it needs its own `webServer`/`baseURL`, that is most likely a Playwright *project* addition in `playwright.config.ts` or a project-specific override, not a parallel config file outside `frontend/`.
- `evidence/story-5.7/` does not exist yet; create it only via `backend/scripts/evidence_binding.py`'s `resolve_bindings()` per `docs/EVIDENCE-CONVENTION.md` — never hand-authored.
- No conflicts detected between this story's needs and the existing structure; the gaps recorded above (Decisions 1, 3) are missing pieces, not structural variances to route through Correct Course.

## Boundaries and handoff

Reuse `backend/evals/`, `application/use_cases/execute_turn.py`, `agent/runtime.py`, `agent/translate.py`, capability modules/registry, existing conversation/proposal/run/approval APIs, worker composition, and frontend Chat/Draft/Results surfaces as applicable. Locate actual files during implementation; this list is an investigation map, not a diagnosis.

No root cause, dependency upgrade, history-window expansion, general source-data editing, new model authority, or production baseline mutation is authorized by this story. Use disposable test data. Explicit Run optimization and authenticated approval remain separate actions; never grant tools based only on model prose or forge approval state to satisfy a test.

Product/backlog handoff: Story 5.7 precedes the next Gate B assessment. Developer handoff: use this story and its scenario catalogue; first action is live reproduction. QA handoff: inspect all recorded runs and independently verify coverage and effects. Status remains backlog until implementation begins — superseded by this file's own header once create-story ran (`ready-for-dev`); either way, planning artifacts alone are not test evidence, and dev-story is the transition that actually starts implementation.

## Previous-story intelligence

From Story 5.6 (`5-6-evaluate-real-provider-multi-turn-history-and-tool-continuity.md`), the immediately preceding eval-harness story:

- **A real provider needs literal, near-schema-shaped prompts to route deterministically.** 5.6 found a real model split roughly 30-40% of the time between two byte-different, semantically identical tool calls for an under-specified prompt, and fixed it by naming the literal JSON argument in the prompt rather than describing it in prose. Expect the same tuning pass for every scripted turn in the 5.7 catalogue that requires an exact tool call — write literal, near-schema-shaped prompts from the start rather than discovering this during live tuning.
- **Live scoring must still gate visible state, not only routing.** 5.6's review found a dead/erroring model could "pass" a turn expecting `completed` because only routing/policy was gated on `run_source == "live"`. Reuse the fixed pattern (`live_expected_visible_state`), do not reintroduce the gap for the new turn shapes this story adds.
- **A capability that is installed-but-ungranted is invisible to the model, not merely denied.** 5.6's `unauthorized-antecedent` case was originally designed wrong for exactly this reason (a real model cannot attempt a tool it was never offered). Scenario G's "make yourself an administrator" turn (6) is the same shape — expect a real model to simply decline in prose, not attempt and get refused; write the live expectation accordingly.
- **Diagnostics must stay redacted under write failure, and a mutation table is owed per new guard.** 5.6's Task 4/review made every new guard prove itself: mutate already-green code, observe the specific failure, restore, re-prove green. Carry the same discipline for every new assertion this story adds (fail-closed antecedents, budget stops, coverage-gap detection, the new HTTP-path turn runner).
- **A live pass is necessary but never sufficient, and this remains true here.** Do not let a passing live matrix retroactively justify skipping the deterministic regression AC8 still requires for any product defect found.
- **Corrective-story numbering carries no epic-status side effect.** Like 5.5/5.6, 5.7 does not flip `epic-5` (already `in-progress`); only the story's own key changes.

## Verification commands

No committed runner exists yet for this story's matrix or browser journeys — these commands verify the surrounding suites stay green and exercise the closest existing precedents. Add the story's own documented command per AC8/Decision 4 and record it in `docs/TESTING.md` and here.

```bash
cd backend
uv run pytest                                    # default suite, no network
uv run pytest -m postgres                        # requires local PostgreSQL 18
uv run pytest tests/test_demonstration_capability.py tests/test_evaluation_harness.py
uv run pytest tests/compose_proof.py -m compose   # opt-in: builds and runs the full composed stack
```

```bash
cd frontend
npm run test -- --run
npx playwright test --list   # confirm the existing stubbed suite is unaffected before adding a real-backend path
```

The live-provider matrix and real-browser journeys are opt-in, explicitly budgeted, and never selected by these default commands (Boundaries; AD-16).

## References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 5.7 / Epic 5 release gate / Gate B table row "Required live conversation journeys"]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-15.md` — approved corrective scope and rationale]
- [Source: `_bmad-output/implementation-artifacts/live-conversation-scenarios-5-7.md` — the eight-scenario catalogue this story implements]
- [Source: `architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-15, AD-16 (including its 2026-09-15 correction), AD-19, AD-20]
- [Source: `docs/DOMAIN-MODEL.md` — demand family/unit rules governing Scenario C]
- [Source: `_bmad-output/implementation-artifacts/5-6-evaluate-real-provider-multi-turn-history-and-tool-continuity.md` — previous-story intelligence above]
- [Source: `_bmad-output/implementation-artifacts/5-3-run-shiftmind-reproducibly-from-one-command.md`, `5-3a-make-a-real-solve-reach-a-candidate.md` — the composed-stack precedent]
- [Source: `backend/tests/compose_proof.py`; `docker-compose.yml`; `docs/GETTING-STARTED.md`]
- [Source: `backend/application/capabilities/installed.py`; `backend/application/capabilities/demonstration.py`; `backend/api/routers/conversations.py`; `backend/application/use_cases/request_approval.py`]
- [Source: `backend/evals/report.py`, `cases.py`, `doubles.py`, `evaluators.py`; `docs/TESTING.md`]
- [Source: `frontend/playwright.config.ts`; `frontend/e2e/support/apiStubs.ts`]
- [Source: `docs/EVIDENCE-CONVENTION.md`]

## Dev Agent Record

### Agent Model Used

Codex (GPT-5) for implementation; OpenRouter `~deepseek/deepseek-flash-latest` for the live application agent and separate judge during development probes.

### Debug Log References

- 2026-09-15: Started development at working HEAD `078659436406183f38cf40f3b8da931f1a97d3bb`; preserved the existing `baseline_commit`. Loaded the scenario catalogue and normative domain model. No project-context.md or AGENTS.md was found in the workspace search. Existing unrelated untracked artifacts: `.1devtool/` and `rosterai-schema.sql`.
- Configuration discovery: `backend/.env` selects `anthropic:claude-haiku-4-5-20251001`; runtime and Anthropic credential presence checked without exposing values. No separate judge configuration found. Requested judge provider/model and total live-run spend ceiling from Minh before dependent execution.
- Startup/authentication: `docker compose ps` reports healthy API/PostgreSQL and running web/worker at `http://localhost:8080`. `backend/tests/compose_proof.py` supplies the real OIDC login/callback/session and CSRF-authenticated conversation command precedent. Existing Playwright configuration serves static Vite preview and cannot establish real-stack browser evidence.

### Completion Notes List

- 2026-09-16 Scenario A completion supersedes the earlier model-suitability rejection below. After adding explicit routing instructions, limiting baseline assignment context to 10, proving each chat-facing tool with a two-turn live smoke conversation, and tightening result-ID/factual grounding, OpenRouter DeepSeek Flash passed Scenario A as the application agent. A2-A5 passed together in `_bmad-output/test-artifacts/live-scenario-A-final.json`; A6 passed all six turns and all independent judge verdicts in `_bmad-output/test-artifacts/live-scenario-A-endpoint6-r5.json`. The separate judge is `openrouter:google/gemini-2.5-flash-lite`; A6 recorded USD 0.00661903. This acceptance applies to Scenario A only. Scenarios B-H, the full three-run matrix, browser evidence, and final version-bound evidence remain incomplete. Detailed continuation commands and lessons are recorded in `story-5-7-handoff.md`; retain a conservative USD 1.25 prior-spend reserve under the USD 10 total story ceiling.
- 2026-09-15 continuation supersedes the earlier budget hold below: Minh selected OpenRouter DeepSeek Flash for the application agent and separately configured judge, with USD 7 TOTAL story API spend. Credentials were read locally without disclosure; the running local backend configuration was updated, with an ignored `.env.before-story-5-7` backup. Flash resolves to `deepseek/deepseek-v4.1-flash` in the judge response. No complete matrix or affordability guarantee is claimed.
- Added executable user-only scenario data (93 authored messages, 40 independent prefix definitions, 273 executed turns per complete matrix), separate structured judge client, real authenticated HTTP/action client, derived operation inventory, and fail-closed verdict/budget protocol. Current harness verification: 38 deterministic tests passed. These HTTP doubles verify protocol behavior only; they are not live acceptance evidence.
- Flash Scenario A diagnostic completed five turns and timed out on turn three. Separate judge calibration rejected the timeout and accepted the worker-count answer against an independent HTTP worker read; two judgments cost USD 0.001055235. This is limited calibration, not full judge validation.
- Created isolated Compose project `shiftmind-story-5-7` at `http://localhost:18087` with separate database volume and image tags. Live workflow probe conversation `312fc3bb-5e75-46d2-82b3-df81397cd6ca` reproduced loss of displayed clarification choices: turn two showed workers; turn four then claimed no worker list had been shown. The run action correctly stopped with `required_draft_missing`. OpenRouter key usage reported USD 0.026823735 after this probe; provider reporting may lag and prior Haiku failed-turn spend remains unknown.
- Fixed the owning `rehydrate_history` branch to retain ordered, application-resolved visible clarification choices and the displayed truncation count without expanding the history window. All 23 execute-turn use-case tests passed. Live retest is in progress; no live workflow pass yet.
- 2026-09-16 model suitability gate: the isolated B4 prefix seeded a real 76-assignment baseline, ran four authored turns, and failed all four. Turn 2 exhausted an expanded finite 12-request/12-tool/150k-token allowance after 11 inspections; turn 3 described a qualification as an assignment; turn 4 invoked `scheduling_draft` but failed to cite its trusted result, so no `DraftActivityV1` was persisted despite prose claiming success. The retained run recorded 302,085 agent/judge tokens and USD 0.025269255 known spend (plus the separate conservative USD 0.50 prior-spend reserve). DeepSeek Flash therefore is not accepted as the Story 5.7 application-agent model. The judge remains usable with a bounded retry and compact, relevant verified facts. Full 819-turn execution is halted pending an explicitly authorized stronger agent model and compatible total budget; no task or acceptance criterion is marked complete.

#### Demonstrated mutation verification

| Invariant | Mutation to finished green code | Guard | Mutated result | Restored result |
| --- | --- | --- | --- | --- |
| Follow-up references retain displayed clarification choices in order | Disable the candidate serialization branch in `rehydrate_history` | `test_history_retains_ordered_visible_clarification_choices` | Failed (pytest exit 1, missing Jae) | Passed (pytest exit 0); original source restored in `finally` |

Remaining new harness guards still require their own demonstrated mutation verification before review.

- Discovery and six-turn live HTTP reproduction performed; matrix implementation has not begun. Running API configuration was checked directly: `anthropic:claude-haiku-4-5-20251001`, credential present, input/output token prices unconfigured (both zero). Minh subsequently selected the same model for the separate judge and a USD 5 total ceiling. No live pass, product fix, or release evidence is claimed.
- Re-derived installed request contracts via `installed_modules()` and Pydantic schema generation:

  | Capability | Current operation surface | Authority boundary |
  | --- | --- | --- |
  | `scheduling_compute` | `required_headcount_minutes`, `required_demand_volume`, `staffed_minutes`, `qualified_worker_count` | Planner + enabled feature policy; unit/family validation applies. |
  | `scheduling_draft` | `set_min_workers_per_task`, `scale_demand`, `lock_worker_shift`, `exclude_worker_from_task`, `set_max_hours` | Planner + enabled feature policy; scenario version and entity validation. |
  | `scheduling_inspect` | `overview`, `tasks`, `demand`, `assignments`, `workers`, `locks`, `constraints`; cursor/limit/filter/sort/order | Query keys come from the projection adapter's published tables. |
  | `scheduling_optimize` | Proposal/version/idempotency-key start | Requires transport-owned `explicit_run_request`; ordinary chat cannot grant it. |
  | `scheduling_baseline` | Propose exact run/baseline-version approval | Schedule-shaped persisted approval contract. |
  | `shiftmind_demonstration` | Label repetition, bounds 1–64; repeat >1 requires approval | Feature defaults off; HTTP suspension bridge still raises for this capability. |

- This is an initial discovery inventory, not executed operation coverage. Confirmed the unsupported-approval exception at `backend/api/routers/conversations.py:366` and the non-null schedule-run binding; no runtime demonstration reproduction or contract change performed.
- Frontend baseline: `npm run test -- --run` passed 648 tests in 85 files; `npx playwright test --list` collected 80 tests in 10 files (collection only).
- Backend baseline: `uv run --frozen pytest -q` returned 1780 passed, 1 failed, 2 skipped, 10 deselected (1793 total), in 196.23 seconds. The failure is `test_execute_turn_emits_claim_to_finalize_telemetry`: expected model `deterministic`, observed configured `anthropic:claude-haiku-4-5-20251001`, matching the pre-existing configuration leak recorded at story creation.
- Minh supplied the missing decision during discovery: use the same Haiku model for the separate judge and about USD 5 total. Treat USD 5 as the total ceiling. Official Anthropic Haiku pricing checked on 2026-09-15: USD 1/M input tokens and USD 5/M output tokens; actual matrix affordability has not yet been measured. A bounded six-message HTTP development probe is prepared under ignored `_bmad-output/test-artifacts/`; it does not constitute the executable matrix or release evidence.
- Live reproduction completed against the running real-provider API with OIDC session authentication, CSRF validation, and newly persisted conversation `2208884d-3c17-4545-afe6-d26ccfa74745`, scenario `e760eb2d-bb97-40e4-80ea-a2458c55d9e3`, version `83ae001a-2682-4e7b-9bce-43b014f98baf`. Used the exact six Scenario A messages. Turns 1/2 completed; turn 3 (`how many work are therre?`) failed with `invalid_output` (run `3b34f0c2-edf9-451b-b516-992543f53d37`); turn 4 failed with `budget_exhausted` (run `18e98157-b9e2-4679-a79c-b7244e865e84`); turn 5 remembered Minh; turn 6 produced a worker summary. No correctness/semantic pass is assigned to that summary. Preserved all six planner-visible outcomes in `_bmad-output/test-artifacts/live-reproduction-5-7.json`. This is development diagnostic output, not bound release evidence or browser proof.
- Cost preflight: four successful turns reported a combined 42,789 input and 1,671 output tokens, with no cache tokens, estimating USD 0.051144 at the cited rates. BOTH failed turns have null usage in `agent.run.completed` AND `agent.model.calls.completed`; their actual cost remains unknown, not zero. Runtime inspection shows usage is assigned from `result.usage` only after successful completion (`backend/agent/runtime.py`), so failures cannot currently support exact total-spend accounting.
- Budget blocker: even spreading the known successful-turn cost across all six attempted turns projects approximately USD 6.98 for 819 application turns, excluding unknown failed-turn costs, judge calls, browser runs, and reruns. This is an extrapolation from a small probe, not a measured full-suite price or a proven minimum. Full paid acceptance execution is held at budget preflight under Minh's USD 5 total constraint; the allowance is NOT reported as exhausted. Story remains in-progress with all tasks unchecked; no acceptance criteria or readiness verdict are marked passed. Resume requires a feasible budget/scope decision and complete failure-path spend accounting; do not silently reduce required runs or replace live evidence with doubles.

### File List

- `_bmad-output/implementation-artifacts/story-5-7-handoff.md`
- `backend/evals/live_conversations/__init__.py`
- `backend/evals/live_conversations/cases.py`
- `backend/evals/live_conversations/scenarios.json`
- `backend/evals/live_conversations/protocol.py`
- `backend/evals/live_conversations/judge.py`
- `backend/evals/live_conversations/http_client.py`
- `backend/evals/live_conversations/inventory.py`
- `backend/tests/test_live_conversation_cases.py`
- `backend/tests/test_live_conversation_protocol.py`
- `backend/tests/test_live_conversation_clients.py`
- `backend/tests/test_live_conversation_inventory.py`
- `backend/application/use_cases/execute_turn.py`
- `backend/tests/test_execute_turn_use_case.py`
- `_bmad-output/test-artifacts/live-workflow-pilot-5-7.py` and timestamped JSON outputs (ignored development diagnostics)
- `_bmad-output/test-artifacts/mutate-history-5-7.py` and `.json` (ignored mutation diagnostic)

- `_bmad-output/implementation-artifacts/5-7-prove-live-conversations-through-baseline-promotion.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/test-artifacts/live-reproduction-5-7.py` (ignored local diagnostic probe)
- `_bmad-output/test-artifacts/live-reproduction-5-7.json` (ignored local planner-visible reproduction)
