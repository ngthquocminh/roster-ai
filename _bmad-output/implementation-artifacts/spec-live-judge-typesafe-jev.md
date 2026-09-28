---
title: 'Live-eval judge on TypeSafe Jev'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: '8932cc8f2eaf9a925566580442014f7a481cd59b'
review_loop_iteration: 0
context:
  - '{project-root}/docs/EVIDENCE-CONVENTION.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The live conversation suite's judge is a free-text OpenRouter chat model that emits JSON. We parse it leniently (string, double-encoded string, content block), retry when it comes back malformed, and gate it on invented citations. Its verdict is untyped text that we coerce into a schema.

**Approach:** Add a TypeSafe System One (Jev) judge. Each turn is one `POST /v1/systemone` call with one typed `score` question per applicable dimension. Code turns the returned level probabilities into the `pass`/`fail`/`uncertain` verdict. The judge model's provider prefix picks the judge: `typesafe:` goes to Jev and becomes the default. `openrouter:` keeps the existing judge exactly as it is, as the revert switch. The runner also trims the facts it gives either judge to what the reply can be graded against. Today's Scenario B inputs run 22k–141k tokens, which exceeds Jev's 32k context and wastes spend on the old judge.

## Boundaries & Constraints

**Always:**
- Record the judge model provider-prefixed. The default is pinned: `typesafe:jev-1.13.0`, because thresholds are tuned against a version and an alias moves. `--judge-model` and `LIVE_CONVERSATION_JUDGE_MODEL` still override it.
- The Jev key is `TYPESAFE_API_KEY`, read from `backend/.env` and then the environment. A `typesafe:` judge without that key is refused at startup, like today's missing-key exit.
- The judge still never sees future turns or reasoning. `grading_rules` in state carries the rubric's domain carve-outs (demand families, soft constraints, the preserve-set rule, coverage caveats, the draft activity rule, "or" alternatives, permitted clarification). The citation and JSON-output instructions are dropped.
- Both judges receive the same trimmed `verified` facts. (1) `candidate_assignments` keeps only candidate rows whose worker or task (name or record id) appears in the reply text, each with `start_minute`/`end_minute`. `candidate_assignment_count` and `candidate_assignments_truncated` stay unchanged. (2) The judge-facing `approve` effect replaces the full `provenance` payload with a compact summary (item count, `baseline_promotion` count, promoted `after_version`). `report['command_observations']` keeps the full effect for diagnostics. All harness fact/effect checks still run on the full data.
- Jev state omits `required_judgment_schema`.
- Charge the budget `input_tokens × $0.042/Mtok`. Missing `usage.input_tokens` is a failure, the same as missing usage today.
- Retry-once semantics match `judge.py`. Transport errors, 429, 5xx and malformed answers retry once. Other 4xx (for example state over Jev's context limit) fail at once. Both end as `IncompleteConversationRun` with a closed code and never provider content.
- A judge pass never overrides a fact or effect failure (`turn_verdict` unchanged).

**Ask First:**
- Changing authored obligations, scenarios, `drop_check`, or the baseline file.
- Running any paid live suite, including a smoke run.

**Never:**
- Remove or change the OpenRouter judge code in `judge.py`. Its inputs shrinking through the runner is intended.
- Use OpenRouter's Decisions endpoint for the judge, or edit the production grounding checker (`adapters/grounding/**`).
- Hand-edit evidence or baseline JSON (re-deriving them is a separate live run under EVIDENCE-CONVENTION).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| All applicable pass | P(level 2) ≥ 0.70 on every applicable dimension | verdict `pass`; each dimension's `score` = argmax level (2) | N/A |
| One clear miss | any applicable dimension has P(2) < 0.30 | verdict `fail` | N/A |
| Contested | no dimension < 0.30, but some dimension < 0.70 | verdict `uncertain` → turn `needs_review` | N/A |
| Not applicable | `clarification_refusal` in `not_applicable` | question not sent; that dimension `score: null`, ignored by `passes()` | N/A |
| Oversized state | Jev returns 400/413 | no retry | `IncompleteConversationRun('judge_unavailable_http_4xx')`; turn `incomplete` |
| Reply names assignments | candidate has 76 rows; the reply names 2 workers | `verified.candidate_assignments` holds only those workers' rows, with minutes; count is still 76 | N/A |
| Reply names nothing | an aggregate reply with no worker or task named | `candidate_assignments: []`; count and truncation flag still present | N/A |
| Bad answer shape | answer missing, wrong `type`, a probability outside [0,1], or a level key missing | retry once, then give up | `judge_malformed_<category>`; both attempts charged |

</frozen-after-approval>

## Code Map

- `backend/evals/live_conversations/judge.py` -- existing OpenRouter judge. `RUBRIC` is the source for `grading_rules`. Retry pattern to mirror.
- `backend/evals/live_conversations/protocol.py` -- `ConversationJudgment`, `DimensionGrade`, `turn_verdict`. The citation gate lives in `passes()`.
- `backend/evals/live_conversations/runner.py:90-132` -- `relevant_entities()`: the reply-text name matching to reuse for candidate rows.
- `backend/evals/live_conversations/runner.py:255-283` -- `approve` stores the full provenance (~156k chars on B:9) in the effect shared by `command_observations` and `effects_after_reply`.
- `backend/evals/live_conversations/runner.py:285-322` -- `candidate_assignments` (every row, ~20k chars) and the judge call site. It records `judgment.model_dump()` and `unknown_citations`.
- `backend/evals/live_conversations/suite.py:73-90` -- judge model/key resolution and `measured_configuration`.
- `backend/evals/live_conversations/configuration.py` -- records `JUDGE_ENDPOINT`. `judge_model` feeds both digests.
- `backend/evals/live_conversations/evidence.py:283-287` -- the evaluator binding text names the RUBRIC judge.
- `backend/evals/live_conversations/publication.py:149-169` -- `_judge_scores` accepts `reason: None`. It needs no change and must stay compatible.
- `backend/adapters/grounding/jev_checker.py` -- reference only: direct `httpx` Jev call and answer validation.
- `docs/TESTING.md:13` -- documents the `--judge-model` example.

## Tasks & Acceptance

**Execution:**
- [x] `backend/evals/live_conversations/protocol.py` -- add `JevDimensionGrade` (`score: 0|1|2|None`, `probabilities`, `confidence`, `reason: None`) and `JevConversationJudgment`. Its `passes()` means verdict pass with every applicable score 2, and its `unknown_citations()` returns `[]`. `turn_verdict` accepts either judgment -- keeps runner/publication shapes intact without a citation gate Jev cannot satisfy.
- [x] `backend/evals/live_conversations/jev_judge.py` -- new: `TYPESAFE_JUDGE_ENDPOINT`, `DEFAULT_JUDGE_MODEL`, `GRADING_RULES`, level criteria, thresholds `PASS_P=0.70`/`FAIL_P=0.30`, and `judge_turn_jev(...)` with the same keyword signature and return `(judgment, usage)` as `judge_turn`.
- [x] `backend/evals/live_conversations/runner.py` -- dispatch on the judge model's prefix (`typesafe:` → `judge_turn_jev`, else `judge_turn`). Narrow `candidate_assignments` to reply-named rows, and give the judge a compact `approve` effect. The rest of the row recording is unchanged.
- [x] `backend/evals/live_conversations/suite.py` + `configuration.py` -- default judge model, key by provider, and the recorded judge endpoint by provider.
- [x] `backend/evals/live_conversations/evidence.py` -- make the evaluator binding text name the provider-selected judge.
- [x] `backend/.env.example`, `docs/TESTING.md` -- document the Jev default and the `openrouter:` revert.
- [x] `backend/tests/test_live_conversation_jev_judge.py` -- new: the payload shape (no future turns, `effects_after_reply` or schema; N/A dims unsent), every I/O-matrix row, and budget charging. Extend the configuration/runner/execute-prefix tests for prefix dispatch, the endpoint, candidate-row narrowing, and the compact approve effect.

**Acceptance Criteria:**
- Given no judge model is configured, when the suite starts, then the report records `judge_model: typesafe:jev-1.13.0` and the TypeSafe endpoint. It passes `span_policy.validate_model_id`.
- Given `--judge-model openrouter:<m>`, when a turn is judged, then `judge.judge_turn` is called unchanged and all existing judge tests pass untouched.
- Given an `approve` action, when the turn is recorded, then `command_observations` holds the full provenance while `verified.effects_after_reply` holds only the summary. Provenance-based failures (`baseline_promotion_provenance_not_exactly_once`) are still detected.
- Given the judge model changed, when `drop_check` compares against the committed baseline, then it refuses on `behavioral_digest` (fail closed, no code change needed).

## Design Notes

State and question shape (one request per turn):

```json
{"model": "jev-1.13.0",
 "state": {"grading_rules": [...], "transcript_so_far": [...],
           "current_obligation": {"id": "...", "text": "..."},
           "verified_facts": {...}},
 "questions": {"completeness": {"type": "score",
   "instructions": "Does the reply in the last entry of `transcript_so_far` meet `current_obligation`, applying `grading_rules`?",
   "criteria": ["wrong, missing, or contradictory", "partial or ambiguous", "fully meets the obligation"]}}}
```

The verdict is policy in code, so the raw probabilities stay in the report. Thresholds can be retuned against recorded answers without re-running inference.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/test_live_conversation_jev_judge.py tests/test_live_conversation_clients.py tests/test_live_conversation_configuration.py tests/test_live_conversation_runner.py tests/test_live_conversation_execute_prefix.py tests/test_live_conversation_suite.py tests/test_live_eval_publication.py -q` -- expected: all pass
- `cd backend && uv run pytest -q` -- expected: no new failures

## Suggested Review Order

**Jev judge: typed scores, verdict in code**

- Entry point: one request, a `score` question per applicable dimension, retry-once semantics.
  [`jev_judge.py:185`](../../backend/evals/live_conversations/jev_judge.py#L185)

- The verdict is explicit policy over P(level 2); nothing judged is never a pass.
  [`jev_judge.py:148`](../../backend/evals/live_conversations/jev_judge.py#L148)

- Answer validation: every level present, in range, summing to about 1.
  [`jev_judge.py:124`](../../backend/evals/live_conversations/jev_judge.py#L124)

- The state (rubric carve-outs as `grading_rules`) and the questions sent.
  [`jev_judge.py:106`](../../backend/evals/live_conversations/jev_judge.py#L106)

- Only 429 and 5xx retry; any other status (e.g. over context) is final.
  [`jev_judge.py:205`](../../backend/evals/live_conversations/jev_judge.py#L205)

**Typed judgment in the protocol**

- No citations, so `passes()` depends on the verdict and the argmax levels only.
  [`protocol.py:179`](../../backend/evals/live_conversations/protocol.py#L179)

**Selection and revert switch**

- The judge model's prefix picks the judge; `openrouter:` keeps `judge.py` untouched.
  [`runner.py:356`](../../backend/evals/live_conversations/runner.py#L356)

- The pinned default and a per-provider key; no key for `typesafe:` is refused.
  [`suite.py:78`](../../backend/evals/live_conversations/suite.py#L78)

- The recorded endpoint follows the prefix, so both digests move on a judge swap.
  [`configuration.py:102`](../../backend/evals/live_conversations/configuration.py#L102)

**Trimmed judge facts (both judges)**

- Only reply-named candidate rows, with minutes; whole-token match over the visible reply.
  [`runner.py:99`](../../backend/evals/live_conversations/runner.py#L99)

- The judge sees a provenance summary; the report and harness checks keep the full payload.
  [`runner.py:336`](../../backend/evals/live_conversations/runner.py#L336)

- The summary itself: item count, promotion count, promoted version.
  [`runner.py:130`](../../backend/evals/live_conversations/runner.py#L130)

**Peripherals**

- The evidence evaluator text names whichever judge the runs used.
  [`evidence.py:30`](../../backend/evals/live_conversations/evidence.py#L30)

- Jev payload shape and the I/O-matrix tests.
  [`test_live_conversation_jev_judge.py:59`](../../backend/tests/test_live_conversation_jev_judge.py#L59)

- Candidate-row narrowing and compact-provenance tests.
  [`test_live_conversation_execute_prefix.py:371`](../../backend/tests/test_live_conversation_execute_prefix.py#L371)

- The default-judge suite test.
  [`test_live_conversation_suite.py:181`](../../backend/tests/test_live_conversation_suite.py#L181)
