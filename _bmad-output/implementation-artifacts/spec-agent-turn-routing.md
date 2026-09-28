---
title: 'Agent turn routing (scheduling / direct / out_of_scope)'
type: 'feature'
created: '2026-09-28'
status: 'in-review'
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

## Verification

**Commands:**
- `cd backend && uv run pytest -q -x` -- expected: all pass.
- `cd backend && uv run pytest -q tests/test_turn_routing.py` -- expected: all pass.
- `cd backend && uv run pytest -q tests/test_live_conversation_cases.py` -- expected: pass, unchanged.
