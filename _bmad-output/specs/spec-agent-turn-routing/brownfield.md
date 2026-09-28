# Brownfield Notes

## Hook points

- `backend/api/routers/conversations.py:367-393` — per-turn runtime build: `compose_capabilities` → `runtime_factory(settings, capabilities, deps, answer_type=GroundedAnswerV2)` → `execute_turn`. The route is decided here, before `runtime_factory`; special paths pass no capabilities and their own instructions and output types. `claimed.prompt` and `claimed.history` supply the router state.
- `backend/api/routers/approvals.py:260-276` — approval-resume runtime build. Unchanged: always the full path.
- `backend/agent/runtime.py` — `AgentRuntimeConfig.instructions` (line 268) defaults to the master prompt; `create_agent_runtime` (955) builds the config from settings; output types are assembled at 351-372 from `answer_type`. Needs a way to pass per-path instructions and a refusal-only output set.
- `backend/agent/runtime.py:360-370` — plain text is accepted because a tool-choice-required request made gpt-5.6-luna loop. On `out_of_scope`, plain text must not reach the planner: convert it to a fixed refusal rather than failing the turn.
- `backend/agent/scheduling_instructions.py` — the master prompt, an f-string using `CANDIDATE_ASSIGNMENT_PREVIEW`; split along its `##` headings.
- `backend/application/contracts/dialogue.py:13-17, 104-110` — `RefusalReasonV1` already includes `out_of_scope`; `RefusalV1(reason, detail, next_step)`.
- `frontend/src/features/chat/ActivityTimeline.tsx:347` — already renders `out_of_scope` as "Out of scope". No frontend change.

## Reused Jev plumbing

- `backend/adapters/grounding/jev_checker.py` — HTTP post, auth header, closed error codes, never raises. `backend/adapters/grounding/factory.py` — provider choice (`typesafe` / `openrouter` / `auto`) and key resolution (`TYPESAFE_API_KEY`, else `OPENROUTER_API_KEY`, else the agent's own key when it runs on OpenRouter).
- Follow the `ClaimSupportChecker` pattern: an application port (Protocol, never raises, closed error code on the result), a Jev adapter, a factory returning `None` when disabled.
- Settings follow `grounding_tier1_*` in `backend/settings.py:179-209`: validated mode, threshold, timeout.

## Jev `choice` shape (TypeSafe docs, verified 2026-09-28)

Request: `{"model", "state", "questions": {"route": {"type": "choice", "instructions": "...", "criteria": {"scheduling": "...", "direct": "...", "out_of_scope": "..."}}}}`.
Response: `answers.route` = `{"type": "choice", "choice": "<top option>", "probabilities": {option: p, ...}, "confidence": 0..1}`; probabilities sum to 1.

## Telemetry

Span attributes follow `_RunCorrelation` in `runtime.py:272-292` (`shiftmind.*` keys): route label, probability, closed error code. No message text on the span (content-minimization boundary, `adapters/telemetry/spans.py`).

## Evals

- Deterministic golden cases: `backend/evals/golden/<capability>/*.json`; drive them with a scripted router.
- Live conversations: `backend/evals/live_conversations/scenarios.json`; add the `f0cdeca6` transcript (hi, hello, yo, nice to meet you, how are you, sing a song, python quadratic) and one mixed case. The Story 5.8 committed baseline needs a paid rerun once the full prompt gains the Scope section.
