---
title: 'Agent turn routing (scheduling / direct / out_of_scope)'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: 'f44d122'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-agent-turn-routing/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-agent-turn-routing/routing-paths.md'
  - '{project-root}/_bmad-output/specs/spec-agent-turn-routing/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** FR-6 requires refusing out-of-scope requests, but the live agent sang a song and wrote Python (conversation `f0cdeca6`). And every turn, even "hi", pays for the full prompt and every tool.

**Approach:** Before each new planner turn, one Jev `choice` call routes the message to `scheduling` (today's full path plus a Scope section), `direct` (short prompt, no tools, answer only) or `out_of_scope` (refusal only). The router fails open to `scheduling` and is switched off by `AGENT_ROUTER_MODE=off`. The contract is SPEC.md plus its companions.

## Boundaries & Constraints

**Always:** fail open to `scheduling` on error, timeout, a probability below the threshold (default 0.85), no key, or mode `off`, so the router never fails a turn. Special paths grant zero tools and get no workflow snapshot. Jev receives message text only: the latest message, the last 2 planner messages and the last 2 agent replies, each truncated. Reuse the tier-1 provider, endpoint and key resolution. Approval-resume stays on the full path with no router call. Every route goes through `execute_turn` and the grounding gate. The keyless suite pins the router off. The route label, probability and error code go on the execute request's span, never message text.

**Ask First:** running the paid live-eval rerun or refreshing the Story 5.8 baseline. Any DB migration, new activity type, or frontend change.

**Never:** SPEC non-goals (escalating `direct`, pre-rules, caching, parallel Jev, shadow mode, circuit breaker, extra routes, multilingual evals, provider disclosure). Changing any section text of today's prompt.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error Handling |
|---|---|---|---|
| Off-topic | "sing a song", p=0.97 | `refused` terminal outcome, reason `out_of_scope` | model plain text → fixed out-of-scope refusal; the model's refusal reason is forced to `out_of_scope` |
| Greeting | "hi", p=0.95 | short grounded answer, 0 tools, direct prompt | — |
| Mixed / scheduling | "how many workers, and write Python" | `scheduling` path, same as today plus Scope | — |
| Low confidence | `direct` at p=0.6 | `scheduling` | — |
| Router failure | timeout / HTTP 5xx / bad JSON / no key / `off` | `scheduling`; span carries the closed error code | never raises |

</frozen-after-approval>

## Code Map

- `backend/agent/scheduling_instructions.py` -- master prompt as one f-string; splits along its `##` headings.
- `backend/agent/runtime.py` -- `AgentRuntimeConfig.instructions` (268), output set (351-372), `create_agent_runtime` (955).
- `backend/api/routers/conversations.py:367-393` -- per-turn build; the hook point before `runtime_factory`.
- `backend/adapters/grounding/{jev_checker,factory}.py` -- Jev HTTP plus provider/key resolution to reuse.
- `backend/application/ports/claim_support.py` -- the port pattern (never raises, closed error code).
- `backend/settings.py:179-209,~618` -- `grounding_tier1_*` settings pattern and env parsing.
- `backend/adapters/telemetry/{spans.py:521,span_policy.py:324}` -- request-span annotator and HTTP_SERVER allow-list.
- `backend/conftest.py:59-60` -- keyless pins.

## Tasks & Acceptance

**Execution:**
- [x] `backend/agent/scheduling_instructions.py` -- split into named section constants in today's order, add `SCOPE`, `DIRECT_RULE` and `REFUSAL_RULE`, and expose `instructions_for(route)` per the routing-paths.md section table. `SCHEDULING_ASSISTANT_INSTRUCTIONS` becomes the full path (Core + Scope + the rest) -- lossless split.
- [x] `backend/application/ports/turn_router.py` -- `TurnRoute` literal, `TurnRouteStateV1` (the message texts), `TurnRouteResultV1(probabilities, error)`, `TurnRouter` Protocol (never raises).
- [x] `backend/application/use_cases/route_turn.py` -- `decide_route(router, prompt, history, threshold) -> TurnRouteDecisionV1(route, probability, error)`: builds the truncated state from `PlannerMessageActivityV1` and agent-reply activities, applies the threshold, and fails open; a raising router is swallowed.
- [x] `backend/adapters/grounding/jev_router.py` -- `JevTurnRouter`: one `choice` question with the three criteria, the same POST/auth/closed error codes as the checker, and probabilities validated.
- [x] `backend/adapters/grounding/factory.py` -- extract shared provider/key resolution and add `create_turn_router(settings)`: `None` when off or keyless, with one warning. Tier-1 behaviour and warnings unchanged.
- [x] `backend/settings.py` -- `agent_router_mode: Literal["on","off"]="on"`, `agent_router_threshold=0.85`, `agent_router_timeout_seconds=2.0`, parsed via `_choice` / `_probability` / `_positive_float`.
- [x] `backend/agent/runtime.py` -- `route` kwarg on `create_agent_runtime` and `PydanticAIAgentRuntime`. `direct`: `instructions_for("direct")` with output limited to the answer tool plus prose text. `out_of_scope`: refusal tool plus a `TextOutput` that converts to a fixed out-of-scope refusal, and a validator forcing `reason="out_of_scope"`. `scheduling` is unchanged.
- [x] `backend/api/routers/conversations.py` -- call `decide_route` before `runtime_factory` and annotate the span. For special routes: `capabilities=()`, `route=...`, `workflow_context=None`. For `scheduling`, the factory call is byte-for-byte today's.
- [x] `backend/adapters/telemetry/{spans.py,span_policy.py}` -- `annotate_turn_route(...)`. HTTP_SERVER validates `shiftmind.turn.route` (closed), `.route_probability` (number) and `.route_error` (closed).
- [x] `backend/conftest.py` -- `AGENT_ROUTER_MODE=off`.
- [x] ~~`backend/evals/live_conversations/scenarios.json` + `cases.py` -- author scenario D~~ -- DEFERRED to the paid-rerun step: `REQUIRED_SCENARIOS` and `test_catalogue_is_three_full_conversations` pin A/B/C, so adding D edits an existing test (breaking "existing tests pass unchanged"), and D has no baseline until the rerun. `test_turn_routing.py` replays the `f0cdeca6` messages deterministically instead.
- [x] `backend/tests/test_turn_routing.py` -- prompt pin (full minus Scope → sha256 `ac3d83962b98ed01811ac931127cd4be1f78262abf282fca975453a8a58bdd33`), I/O matrix, factory/provider/keyless, adapter via `httpx.MockTransport`, runtime output sets with a scripted model, API test with a scripted router (0 tools; `out_of_scope` → `refused`), mode `off` makes no request.

**Acceptance Criteria:**
- Given default test settings, when the existing suite runs, then it passes unchanged and no router request is made.
- Given `AGENT_ROUTER_MODE=off` and a key, when a turn runs, then `create_turn_router` returns `None` and the turn takes `scheduling`.
- Given an approval resume, when it runs, then no router is created and the full prompt is used.

## Design Notes

The route drives the whole runtime variant (prompt plus output set), so one `route` kwarg replaces separate `instructions` and output knobs. The scheduling call site passes no new kwarg, so test factories and fakes stay untouched. Revert by setting `AGENT_ROUTER_MODE=off`; the Scope section is the only change that remains on the full path.

Deterministic golden-case harness wiring for a scripted router is deferred; pytest API tests cover the routes.

Also changed: `docker-compose.yml` and `backend/.env.example` expose `AGENT_ROUTER_MODE`, because the operator switch must reach the container. `evals/live_conversations/compose.override.yml` is deliberately untouched: it feeds the committed baseline's `behavioral_digest`, and the live stack inherits the default (`on`).

Review fixes: every `out_of_scope` refusal is the fixed `OUT_OF_SCOPE_REFUSAL`, since the model's own `detail` could carry the off-topic answer (CAP-2). Router state now includes draft and approval summaries as agent replies, and the latest message is truncated at 2,000 characters instead of 500. A response missing a route or not summing to about 1 is `bad_response`. Ties go to `scheduling`. A special route requires `answer_type=GroundedAnswerV2`. The router criteria send mixed messages to `scheduling`. Compose passes the threshold and timeout through.

## Verification

**Commands:**
- `cd backend && uv run pytest -q -x` -- expected: all pass.
- `cd backend && uv run pytest -q tests/test_turn_routing.py` -- expected: all pass.
- `cd backend && uv run pytest -q tests/test_live_conversation_cases.py` -- expected: pass, unchanged.

## Live Eval (2026-09-28, sandbox, not evidence-grade)

Paid run on `openai/gpt-5.6-luna` with the `google/gemini-2.5-flash` judge, run from the cloud sandbox. The images came from the sandbox fallback build plus a proxy layer, and the suite ran with `--skip-image-build`, so `evals.live_conversations.evidence` refuses the report. The committed evidence and baseline must be refreshed from a local run.

- **Full matrix (3 repetitions):** 83/90 turns passed, against the baseline's 87/90. No turn dropped to 0/3.
  - Five misses were judge outages (`judge_malformed_JSONDecodeError_at_root`), not agent failures.
  - B:5 missed once on judge completeness, which predates routing (2/3 in the baseline too).
  - C:10 was a routing miss: the demonstration request went to `out_of_scope`. Fixed in `7781f25` by naming the app's features in the router question (Jev: 0.84-0.95 out_of_scope -> 0.97-0.99 scheduling).
- **Scenario C rerun after the fix (3 repetitions):** C:10 passed in all 3. The misses were one judge outage and two completeness scores on the scheduling path (C:3, which was 2/3 in the baseline; C:4).
- **`f0cdeca6` replay on a live stack:** the five small-talk messages got short replies with no tools. The song and quadratic-Python requests were refused as `out_of_scope`. The mixed message stayed on scheduling: it answered the worker count and declined the Python.

## Suggested Review Order

**Where the route is decided**

- Entry point: route before building the runtime; special routes get no tools and no snapshot.
  [`conversations.py:370`](../../backend/api/routers/conversations.py#L370)

- Scheduling keeps today's exact factory call; special routes add `route=`.
  [`conversations.py:392`](../../backend/api/routers/conversations.py#L392)

- Fail-open decision: only a confident special route leaves scheduling; ties go to scheduling.
  [`route_turn.py:57`](../../backend/application/use_cases/route_turn.py#L57)

- Router state: conversation text only, including draft and approval summaries.
  [`route_turn.py:37`](../../backend/application/use_cases/route_turn.py#L37)

**Prompt split**

- Lossless split along `##` headings; composition per route.
  [`scheduling_instructions.py:299`](../../backend/agent/scheduling_instructions.py#L299)

- The only full-path change: the new Scope section.
  [`scheduling_instructions.py:281`](../../backend/agent/scheduling_instructions.py#L281)

- Full path = Core + Scope + today's sections, in order.
  [`scheduling_instructions.py:318`](../../backend/agent/scheduling_instructions.py#L318)

**Runtime output sets**

- Narrowed output per route; a misroute cannot add capability.
  [`runtime.py:368`](../../backend/agent/runtime.py#L368)

- Every out-of-scope refusal is the fixed one, so off-topic text never reaches the planner.
  [`runtime.py:424`](../../backend/agent/runtime.py#L424)

- The fixed refusal text.
  [`runtime.py:253`](../../backend/agent/runtime.py#L253)

**Jev router and wiring**

- One `choice` question; mixed messages count as scheduling.
  [`jev_router.py:19`](../../backend/adapters/grounding/jev_router.py#L19)

- Strict parse: all three routes present, summing to about 1, else `bad_response`.
  [`jev_router.py:50`](../../backend/adapters/grounding/jev_router.py#L50)

- Provider and key resolution shared with the tier-1 checker.
  [`factory.py:44`](../../backend/adapters/grounding/factory.py#L44)

- Off or keyless means no router, with one warning.
  [`factory.py:74`](../../backend/adapters/grounding/factory.py#L74)

**Settings and telemetry**

- Mode, threshold and timeout, validated at start.
  [`settings.py:204`](../../backend/settings.py#L204)

- Route, probability and error on the request span; no message text.
  [`spans.py:530`](../../backend/adapters/telemetry/spans.py#L530)

- Allow-list entries for the export sanitizer.
  [`span_policy.py:337`](../../backend/adapters/telemetry/span_policy.py#L337)

**Peripherals**

- Keyless suite pins the router off.
  [`conftest.py:63`](../../backend/conftest.py#L63)

- Operator switch passed through to the container.
  [`docker-compose.yml:57`](../../docker-compose.yml#L57)

- Prompt sha256 pin.
  [`test_turn_routing.py:53`](../../backend/tests/test_turn_routing.py#L53)

- `f0cdeca6` replay through the execute route.
  [`test_turn_routing.py:369`](../../backend/tests/test_turn_routing.py#L369)

- Router off: no request is made.
  [`test_turn_routing.py:403`](../../backend/tests/test_turn_routing.py#L403)
