---
title: 'Grounding 3: tier-1 claim-support checker port with Jev adapter, shadow mode'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: '023661c6f94ee9b97fdbcfb36f74e0b6dd838c71'
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
- [x] `backend/application/ports/claim_support.py` -- `ClaimSupportChecker` Protocol: batch of (id, claim text, evidence text) → per-id probability or error
- [x] `backend/application/grounding/verbalize.py` -- deterministic record → text per evidence group
- [x] `backend/adapters/grounding/jev_checker.py` -- `POST https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13` (configurable), `noul` question per fact, timeout
- [x] `backend/adapters/grounding/stub_checker.py` -- deterministic double
- [x] `backend/settings.py` + factory -- `GROUNDING_TIER1_MODE`, model, timeout, token budget; reuse the OpenRouter key
- [x] `backend/application/use_cases/execute_turn.py` -- in shadow, check supported facts and attach `support_probability`
- [x] `backend/evals/live_conversations/` -- run the live stack in shadow; report per-fact probabilities and the low-probability list for review
- [x] tests -- every matrix row with the double; adapter request/response mapping against a recorded Jev response

**Acceptance Criteria:**
- Given the keyless CI suite, when it runs, then no network call is made and all tests pass.
- Given a live-eval run in shadow, when it finishes, then the report lists each checked fact's probability without altering any grounded response.

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: all pass
- Live check: STOP before running `live_conversations` and wait for Minh's explicit permission (and key). Then one live-eval run in shadow -- expected: report contains tier-1 probabilities

## Spec Change Log

- 2026-09-27 -- Human-renegotiated (Minh): the Jev adapter may call TypeSafe DIRECTLY
  (`POST https://api.typesafe.ai/v1/systemone`, own `TYPESAFE_API_KEY`) as well as through
  OpenRouter's Decisions API. Both take the same body (`model`, `state`, `questions`) and return
  `answers[id].noul`, so one adapter serves both. Selection is configuration:
  `GROUNDING_TIER1_PROVIDER = auto | typesafe | openrouter` (default `auto`: TypeSafe when its key
  is set, else OpenRouter with the existing OpenRouter key, else disabled with one warning).
  Supersedes the frozen "Jev through OpenRouter" / "reuse the OpenRouter key" wording; the
  "provider other than Jev via OpenRouter" Ask-First item is answered for TypeSafe-direct only.

## Suggested Review Order

- Entry point: shadow hook after the gate; never raises, never changes a reply.
  [`execute_turn.py`](../../backend/application/use_cases/execute_turn.py) -- `shadow_check_facts`
- One Jev adapter for TypeSafe-direct and OpenRouter; per-turn deadline, atomic batches.
  [`jev_checker.py`](../../backend/adapters/grounding/jev_checker.py)
- Provider selection (`auto | typesafe | openrouter`) and key fallback.
  [`factory.py`](../../backend/adapters/grounding/factory.py)
- Port, verbaliser, settings, telemetry event, live-eval report section.
  [`claim_support.py`](../../backend/application/ports/claim_support.py) ·
  [`verbalize.py`](../../backend/application/grounding/verbalize.py) ·
  [`reporting.py`](../../backend/evals/live_conversations/reporting.py)
- Tests: [`test_tier1_checker.py`](../../backend/tests/test_tier1_checker.py)

**Live shadow run (2026-09-27, with Minh's permission):** one repetition of A/B/C, agent
`openrouter:openai/gpt-5.6-luna`, judge `openrouter:google/gemini-2.5-flash`. 30/30 turns passed;
38 facts reached tier 0 `supported` and all 38 got a tier-1 probability (0 unchecked, no checker
errors); no grounded response changed. Below 0.5: three facts, all the same bare task name
`C Fork | Grid P 8GR` (0.43, 0.37, 0.17) whose text equals the record's `name` exactly -- a
checker false negative on a name-only "claim", not a wrong fact. Evidence for any later
flag/strip decision: bare-name facts need a different question (or exclusion) before tier 1
can enforce.

**Follow-up (2026-09-27, agreed with Minh):** facts whose text only restates the checked value
skip tier 1 (tier 0 proved them); the checker's provider and latency are now telemetry and the
live report records them per turn. Wording probe `evals/tier1_probe.py` (TypeSafe direct,
`jev-latest`): 12/12 cases on the right side of 0.5 -- supported 0.84-0.98; negated, wrong
task/hours/function/area and inverted constraint 0.02-0.08; one batched call, 579 ms. Next gate
decision: flag mode (never strip/retry) once more live runs confirm no false alarms remain.

**Flag mode (2026-09-27, Minh's explicit decision -- the spec's Ask-First on enforcing modes):**
second live shadow run first: 30/30 turns, 77 facts (68 bare values skipped as tier-0-only,
9 checked at 0.87-0.94, none below 0.5), one TypeSafe call in 1,023 ms. Then
`GROUNDING_TIER1_MODE=off|shadow|flag` with **`flag` as the default** and
`GROUNDING_TIER1_FLAG_THRESHOLD` (default 0.5): a tier-0-supported fact scoring below it gets
`wording_flagged` and the UI marker "Wording not supported by the record · field: value" beside
its evidence link. Never stripped, retried or blocked; no key or a checker failure flags nothing.
The keyless test suite pins the mode `off` (conftest) so a local key never reaches the network.
