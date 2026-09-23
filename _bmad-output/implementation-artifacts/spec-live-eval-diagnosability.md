---
title: 'Make live-eval failures judgeable and diagnosable'
type: 'bugfix'
created: '2026-09-23'
status: 'done'
baseline_commit: '9598de8cec8a45e70661adec6ff4f0d6ed6e6577'
review_loop_iteration: 2
context:
  - '{project-root}/docs/EVIDENCE-CONVENTION.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Two of the three failures accepted into the Story 5.7 live baseline cannot be explained from their records. (1) B:8 rep1: the runner gives the judge `candidate_assignment_count = candidate.get('assignment_count')`, but the `/schedule-runs/{id}/result` candidate (`ScheduleVersionOut`) carries the count only at `metrics.assignment_count`, so the key is always `None`. The judge counted the 76-row list itself, got 50, and failed a correct "76 assignments" reply. `candidate_assignments_truncated` is always `None` for the same reason. (2) B:5 rep3 failed with `invalid_output` but no `retry_rule` label. Retry-rule telemetry already exists (`a241091`), but `_last_retry_rule` is only set by our own output validators. A failure where the framework's retries ran out (output schema validation, tool-argument validation, an unknown tool, a capability `ModelRetry`) is reported with no cause at all.

**Approach:** The runner computes the candidate count in code from the real payload shape, cross-checks it against `metrics.assignment_count`, and reports truncation as the assistant saw it (its snapshot preview is capped). A payload the harness cannot trust is an infrastructure fault that stops the report, not a model failure. When the framework's retries run out, the runtime records the reason PydanticAI actually raised, read from the structured parts of the exception's cause, as a new `retry_cause` label; nothing is reconstructed or guessed.

## Boundaries & Constraints

**Always:** `retry_cause` is built only from the cause's class name, a `ValidationError`'s `.title` (our schema name) and its first error's `type` code, formatted `Class[:Schema:code]`. Never the error message, input, or location (a location can hold a model-invented key); never branch on message text (AD-12/AD-15). `retry_rule` keeps its original meaning (our own validators only) and behaviour. The candidate is validated as soon as the run result is read, before any action or fact uses its rows; on failure the turn's factual failures are recorded first, then the report stops with `IncompleteConversationRun`.

**Ask First:** Any change to the judge rubric, `scenarios.json`, the committed baseline, or `behavioral_digest` inputs.

**Never:** No TypeSafe, no judge-prompt edits, no re-measurement or evidence files. Don't change retry limits or validators' behaviour. No reconstruction of PydanticAI's retry counters from messages.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Large candidate | 76 rows, `metrics.assignment_count` 76 | facts: count 76, truncated `True` | N/A |
| Preview boundary | 5 rows / 6 rows | truncated `False` / `True` | N/A |
| Count mismatch | row count differs from `metrics.assignment_count` | turn failures recorded, report stops | `incomplete_reason` `candidate_assignment_count_mismatch` |
| Malformed payload | candidate/`metrics` not objects, `assignments` missing/not a list of objects, incl. before an `approve` action | no crash; turn failures recorded, report stops | `incomplete_reason` `candidate_payload_malformed` |
| Bad answer structure | output-tool args fail `GroundedAnswerV1` | `retry_cause="ValidationError:GroundedAnswerV1:<code>"` | N/A |
| Bad tool input | capability request fails its schema | `retry_cause="ValidationError:SchedulingComputeRequestV1:<code>"` | N/A |
| Tool/unknown-tool retry | cause is `ModelRetry` | `retry_cause="ModelRetry"` | N/A |
| Empty or text-path rejection | cause is `ToolRetryError` | `retry_cause="ToolRetryError"`; `retry_rule` set iff our rule fired | N/A |
| No cause | exhaustion error with no `__cause__` | `retry_cause` unset | N/A |

</frozen-after-approval>

## Code Map

- `backend/evals/live_conversations/runner.py` -- `execute_prefix`: run actions read `app.wait_for_run`; facts built after actions
- `backend/application/use_cases/conversation_workflow_context.py:62` -- assistant's candidate preview
- `backend/agent/scheduling_instructions.py:60` -- prompt text "at most the first 5 assignments"
- `backend/agent/runtime.py` -- `UnexpectedModelBehavior` branch sets `failure.retry_rule`
- `backend/application/contracts/agent_runtime.py`, `application/use_cases/execute_turn.py:301`, `application/contracts/telemetry.py`, `api/routers/conversations.py:208` -- `retry_rule` path to telemetry; `retry_cause` follows it

## Tasks & Acceptance

**Execution:**
- [x] `backend/application/use_cases/conversation_workflow_context.py`, `backend/agent/scheduling_instructions.py` -- one `CANDIDATE_ASSIGNMENT_PREVIEW` constant; the prompt interpolates it (text unchanged)
- [x] `backend/evals/live_conversations/runner.py` -- validate the candidate right after `wait_for_run`; record `factual_failures` on the row, then raise; facts use count and `count > preview`
- [x] `backend/agent/runtime.py` -- `_retry_cause(exc)`; set `failure.retry_cause` beside `retry_rule`
- [x] `backend/application/contracts/agent_runtime.py`, `backend/application/use_cases/execute_turn.py`, `backend/application/contracts/telemetry.py`, `backend/api/routers/conversations.py` -- carry and emit `retry_cause`
- [x] tests -- runner matrix rows (incl. malformed + `approve`, 5/6 boundary); one real-run test per cause row; a marker in the rejected output never appears in any label; `retry_cause` is an allowed label key

**Acceptance Criteria:**
- Given a completed run, when facts are built, then count is an int equal to the row count and truncation equals the assistant's snapshot flag.
- Given any `invalid_output` failure whose exhaustion has a cause, when telemetry is emitted, then `agent.run.completed` carries `retry_cause` and no model text.

## Spec Change Log

- **Loop 1 (review of first implementation).** Triggers: Blind #8 (truncated hard-coded `False` although the assistant sees at most 5 rows); Blind #1-3 / Edge #1-5 (labels from tool names in the final response blamed the wrong tool, a stale named rule survived an empty-response exhaustion, our own handler's `ValidationError` was labelled as the model's argument error, non-retry failures got invented labels, a resume turn read the previous turn). Amended (human-approved, frozen): truncation semantics, label vocabulary (`capability_retries`, `unknown_tool`, `output_schema`, `empty_response`), history-scoped classification, turn-level incompleteness. Known-bad states avoided: judge told the full list was visible; telemetry pointing diagnosis at prompts for a server bug. KEEP: `candidate_assignment_count` helper shape and docstring citing B:8; the `ScheduleVersionOut`-shaped fixture with its comment; the FunctionModel `_repeating`/`_call` test helpers; the probe finding that PydanticAI raises exhaustion before appending the final retry part (the cause is the only record of it).

- **Loop 2 (second review).** Triggers: both reviewers probed the per-tool retry counting wrong four ways (counter resets on success, same-step double count, history-merge offset, provider `ValidationError`); turn-level incompleteness blanked later turns, hid factual failures, scored harness drift as model failure, and `approve` crashed on malformed rows before the check. Human reviewed B's root cause: the reason exists in the exception and was being discarded. Amended (human-approved, frozen): record the raised cause structurally as `retry_cause`, drop label reconstruction entirely; candidate faults stop the report as infrastructure faults, validated at read time. KEEP: runner `candidate_assignment_count` helper and its B:8 docstring; `ScheduleVersionOut`-shaped fixture; `CANDIDATE_ASSIGNMENT_PREVIEW`; `_repeating`/`_calls` test helpers; the reset test.

## Design Notes

Probe (pydantic-ai 2.27.0): the exhaustion `UnexpectedModelBehavior`'s `__cause__` is `ValidationError` (title `GroundedAnswerV1` for the answer, `SchedulingComputeRequestV1` for the tool, codes such as `tuple_type`, `missing`), `ModelRetry` (capability retry, unknown tool), or `ToolRetryError` (empty reply, and our text-path validators; `retry_rule` tells those apart).

## Verification

**Commands:**
- `cd backend && uv run --frozen pytest tests/test_agent_runtime_adapter.py tests/test_live_conversation_execute_prefix.py tests/test_live_conversation_runner.py tests/test_telemetry_contracts.py -q` -- expected: all pass
- `cd backend && uv run --frozen pytest -q` -- expected: no new failures

## Suggested Review Order

**Candidate facts for the judge (B:8)**

- Entry point: count from the real payload shape; untrusted payload raises before use.
  [`runner.py:53`](../../backend/evals/live_conversations/runner.py#L53)

- Validated the moment the run result is read, before approval touches rows.
  [`runner.py:235`](../../backend/evals/live_conversations/runner.py#L235)

- Judge gets the computed count and the assistant's truncation, not absent keys.
  [`runner.py:298`](../../backend/evals/live_conversations/runner.py#L298)

- One preview constant shared by snapshot, prompt and harness.
  [`conversation_workflow_context.py:21`](../../backend/application/use_cases/conversation_workflow_context.py#L21)

- Prompt interpolates it; rendered text is byte-identical.
  [`scheduling_instructions.py:62`](../../backend/agent/scheduling_instructions.py#L62)

**Framework give-up cause (B:5)**

- Cause read from exception structure only: class, schema title, error code.
  [`runtime.py:246`](../../backend/agent/runtime.py#L246)

- Set beside the existing named rule on invalid-output failures.
  [`runtime.py:704`](../../backend/agent/runtime.py#L704)

- Contract field; `retry_rule` doc clarified as last rule fired.
  [`agent_runtime.py:238`](../../backend/application/contracts/agent_runtime.py#L238)

- Carried into the failed outcome like `retry_rule`.
  [`execute_turn.py:302`](../../backend/application/use_cases/execute_turn.py#L302)

- Emitted on the first-turn and approval-resume routes; key allow-listed.
  [`conversations.py:210`](../../backend/api/routers/conversations.py#L210)
  [`approvals.py:320`](../../backend/api/routers/approvals.py#L320)
  [`telemetry.py:47`](../../backend/application/contracts/telemetry.py#L47)

**Tests**

- Count, 5/6 boundary, and infrastructure stop for every untrusted shape.
  [`test_live_conversation_execute_prefix.py:200`](../../backend/tests/test_live_conversation_execute_prefix.py#L200)

- One real-run case per cause, plus a model-text leak check.
  [`test_agent_runtime_adapter.py:1408`](../../backend/tests/test_agent_runtime_adapter.py#L1408)

- Labels reach `agent.run.completed` and stay allow-listed.
  [`test_agent_run_completed_labels.py:1`](../../backend/tests/test_agent_run_completed_labels.py#L1)
