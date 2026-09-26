---
title: 'Grounding 3: tier-1 claim-support checker port with Jev adapter, shadow mode'
type: 'feature'
created: '2026-09-27'
status: 'ready-for-dev'
review_loop_iteration: 0
depends_on: 'spec-grounding-2b-fact-claim-tags.md'
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-grounded-answers-claim-evidence-attribution-research-2026-09-26.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Tier 0 verifies a fact's attributes but not its wording: `<claim ev='w3' field='qualifications' value='T1'>Ana is not qualified for T1</claim>` passes.

**Approach:** A `ClaimSupportChecker` port judges whether each supported fact's wrapped text is supported by its record, verbalised deterministically. The first adapter is TypeSafe Jev through OpenRouter's Decisions API, one batched request per turn. This phase runs in **shadow**: verdicts are recorded and reported, never shown or enforced. Promotion to flag/strip is a later human decision on measured data.

## Boundaries & Constraints

**Always:** Checker behind a port in `application/ports`; adapters under `adapters/`; deterministic double for keyless CI. Mode is configuration: `off | shadow`, default `off`. A checker error, timeout or missing key never changes the grounded response and never fails the turn. Telemetry carries counts, probability buckets, latency and error codes — never claim or record content (AD-12/AD-15). Only facts that passed tier 0 are sent.

**Ask First:** Any enforcing mode (flag/strip); sending anything beyond the fact text and its own record; a provider other than Jev via OpenRouter.

**Never:** Checking `{{r}}` values (tier 0 renders them); checking untagged prose (phase 4); a pydantic-ai upgrade for this.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Shadow, two supported facts | mode `shadow` | One Decisions request with two yes/no questions; each fact persists `support_probability`; UI unchanged | N/A |
| Mode off | default | No request; field stays null | N/A |
| No supported facts | only prose/values | No request | N/A |
| Checker timeout / HTTP error | provider down | Response unchanged; telemetry error code | Swallowed, turn completes |
| Missing API key | mode `shadow`, no key | Checker disabled at start-up with one warning | Turn completes |
| Oversized state | > configured token budget | Batch split or excess facts skipped and counted | Turn completes |

</frozen-after-approval>

## Code Map

- `backend/application/ports/` -- existing Protocol ports (pattern to follow)
- `backend/application/use_cases/execute_turn.py` -- post-gate hook point
- `backend/application/contracts/grounding.py` -- `GroundedFactV1` (2b) gains `support_probability: float | None`
- `backend/evals/live_conversations/judge.py` -- existing direct-`httpx` OpenRouter client pattern
- `backend/settings.py` -- configuration and existing OpenRouter key setting
- `backend/tests/architecture/` -- egress/boundary guards to satisfy
- `backend/evals/live_conversations/reporting.py` -- live-eval report

## Tasks & Acceptance

**Execution:**
- [ ] `backend/application/ports/claim_support.py` -- `ClaimSupportChecker` Protocol: batch of (id, claim text, evidence text) → per-id probability or error
- [ ] `backend/application/grounding/verbalize.py` -- deterministic record → text per evidence group
- [ ] `backend/adapters/grounding/jev_checker.py` -- `POST https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13` (configurable), `noul` question per fact, timeout
- [ ] `backend/adapters/grounding/stub_checker.py` -- deterministic double
- [ ] `backend/settings.py` + factory -- `GROUNDING_TIER1_MODE`, model, timeout, token budget; reuse the OpenRouter key
- [ ] `backend/application/use_cases/execute_turn.py` -- in shadow, check supported facts and attach `support_probability`
- [ ] `backend/evals/live_conversations/` -- run the live stack in shadow; report per-fact probabilities and the low-probability list for review
- [ ] tests -- every matrix row with the double; adapter request/response mapping against a recorded Jev response

**Acceptance Criteria:**
- Given the keyless CI suite, when it runs, then no network call is made and all tests pass.
- Given a live-eval run in shadow, when it finishes, then the report lists each checked fact's probability without altering any grounded response.

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: all pass
- Live check: STOP before running `live_conversations` and wait for Minh's explicit permission (and key). Then one live-eval run in shadow -- expected: report contains tier-1 probabilities
