---
title: 'Live eval: per-turn expectations for Scenario B'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: '778b318'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-live-judge-typesafe-jev.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The live judge grades each reply on four generic dimensions. To do that it reads the whole conversation and a dozen global carve-out rules, and has to infer what "that run" or "the preceding approval" means. The Jev smoke run (`live-jev-smoke-B.json`) false-failed B:7, B:8 and B:10 and flagged B:1 and B:12. Ablations traced the causes to question wording, rule overload, and facts missing from the judge's input.

**Approach:** Scenario B turns get an authored `expect` list. Code checks handle anything exact: mentions, activity type, saved-draft contents. Narrow yes/no Jev questions handle only what code can't. Expected values come from **bindings** the harness captures from real application state as the conversation runs. Each judge question sees only the user message, the reply, and the few facts it names. Design approved in-conversation on 2026-09-29.

## Boundaries & Constraints

**Always:**
- **Bindings** are captured from app state only, never from the agent's words, and each is set once (the first value wins):
  - `baseline_id`, `scenario_name`, `task_names` at the start
  - `excluded_worker(_id)` and `excluded_task(_id)` from the first saved `exclude_worker_from_task` constraint
  - `candidate_id`, `solver_status`, `assignment_count` from a completed run
  - `promoted_baseline_id`, `approval_id` from an approve action
- `events` is the harness's own list of what happened (the draft constraint descriptions, the run result, the approval), used as judge facts.
- A turn's expectations are evaluated with the bindings **as of its reply**, i.e. before its `actions_after` run.
- An expectation whose binding is unset makes the turn `incomplete`, never `fail`.
- **Verdict:**
  - `fail` if any existing factual failure, any failed code check, or any judge check with P(the wanted answer) < 0.30
  - `needs_review` if any judge check is below 0.70
  - `pass` otherwise
- All existing harness checks still run. The verdict vocabulary is unchanged.
- The expectation path applies only when a turn has `expect` **and** the judge is `typesafe:`. Otherwise the turn uses the existing holistic judge, so `openrouter:` remains a full revert.
- Each turn with `expect` has at least one positive expectation. A turn with only "must not" checks is refused at load time.
- Text matching is whole-token, casefolded and whitespace-collapsed, over the reply's visible text (all string values of `visible_activity`). This replaces `json.dumps` matching, which glued `\n` onto names.

**Ask First:** Converting scenarios A, C or D; changing any B `user` text or harness action; running any paid live run beyond one B smoke.

**Never:** Give a judge question the transcript or global rules; derive a binding from reply text; change the `openrouter:` judge path.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| All checks met | B:8 names FEASIBLE and the candidate; judge nouls clear | `pass`; `checks` lists every check with its outcome | N/A |
| Code miss | B:8 reply omits the solver status | `fail`; `checks[names_status].outcome = fail` | N/A |
| Contested judge | a judge check with P(wanted) = 0.5 | `needs_review` | N/A |
| Unbound | B:4 saved no exclusion, then B:5 expects `{excluded_worker}` | B:5 `incomplete`, reason `unbound_excluded_worker` | no judge call |
| No judge checks | B:3, B:4, B:6 | graded by code alone; no Jev request | N/A |
| Jev down | request fails twice | `incomplete`, as today | `judge_unavailable_*` |

</frozen-after-approval>

## Code Map

- `backend/evals/live_conversations/cases.py` -- `ConversationTurn`; add `expect` loading and validation.
- `backend/evals/live_conversations/scenarios.json:44-112` -- Scenario B turns.
- `backend/evals/live_conversations/runner.py:149-380` -- `execute_prefix`: the draft read, `actions_after`, the judge call, the row verdict.
- `backend/evals/live_conversations/jev_judge.py` -- add a yes/no batch call that reuses `judge_turn_jev`'s retry, usage and charging.
- `backend/api/schemas.py:675` -- `ScenarioOverviewOut` (`before`) carries `scenario_name` and `baseline_schedule_version`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/evals/live_conversations/expectations.py` -- new: `Bindings` (set-once, `events`), `visible_text`, the code-check kinds (`mentions`, `mentions_all`, `mentions_any`, `activity_is`, `activity_field_equals`, `draft_has`, `names_assigned_pair`, `draft_matches_turn`), judge-question building from `facts` names, and `verdict_from_checks`.
- [x] `backend/evals/live_conversations/jev_judge.py` -- `ask_yes_no(...)`: one request of `noul` questions, same retry, usage and budget rules; returns P(yes) per question id.
- [x] `backend/evals/live_conversations/cases.py` -- `Expectation` type, `expect` on a turn, validation (known kinds and binding names, at least one positive expectation).
- [x] `backend/evals/live_conversations/runner.py` -- capture bindings at start, on draft save, run completion and approval; take the expectation path for `expect` turns under a `typesafe:` judge; record `checks`; switch `named_candidate_rows` to `visible_text`.
- [x] `backend/evals/live_conversations/scenarios.json` -- add the `expect` lists to B's 12 turns, as designed in-conversation.
- [x] `backend/tests/test_live_conversation_expectations.py` -- new: every check kind, set-once bindings, unbound → incomplete, the verdict thresholds, validation refusals. Also the runner path: an `expect` turn under `typesafe:` versus `openrouter:`.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- log the agent gap (reuse the B:9 approval ID; know that the decision record lives under Results → Debug details → Decision provenance).

**Acceptance Criteria:**
- Given the recorded smoke replies, when B's expectations are evaluated offline, then B:7 and B:8 pass, and B:10 is `needs_review` or `fail` for lacking a record location or approval ID.
- Given `--judge-model openrouter:<m>`, when B runs, then every B turn is graded by the holistic judge exactly as before.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/test_live_conversation_*.py tests/test_live_eval_publication.py -q` -- expected: all pass
