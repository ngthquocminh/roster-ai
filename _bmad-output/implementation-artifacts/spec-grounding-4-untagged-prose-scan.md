---
title: 'Grounding 4: flag-only tier-1 scan of untagged prose'
type: 'feature'
created: '2026-09-27'
status: 'draft'
review_loop_iteration: 0
depends_on: 'spec-grounding-3-tier1-checker-shadow.md'
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-grounded-answers-claim-evidence-attribution-research-2026-09-26.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Under D2 untagged prose is unchecked: an invented number or name written as plain text reaches the planner looking like any other sentence.

**Approach:** Reuse the phase-3 checker on untagged prose. Each untagged sentence gets two yes/no questions in the same batched request: does it state a fact about this scenario, and is that fact supported by this turn's evidence (verbalised tool results plus the workflow snapshot)? A sentence judged factual and unsupported is flagged. Modes `off | shadow | flag`, default `off`; the UI shows a flag only in `flag` mode.

## Boundaries & Constraints

**Always:** Flag-only: never strip, rewrite, retry or block. Meta-talk (what the assistant can do, questions to the planner, greetings) must not be flagged — that is what the "states a scenario fact" question is for. Evidence is only this turn's trusted results and the workflow snapshot. Checker failure leaves the response unflagged. Telemetry excludes content (AD-12/AD-15).

**Ask First:** Turning on `flag` in any deployed configuration; widening evidence to earlier turns.

**Never:** Scanning tagged facts or `{{r}}` values; any lexical numeral or name heuristic (D2).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Invented count in prose | "There are 12 workers on Monday." (not in evidence) | factual + unsupported → flagged (in `flag` mode) | N/A |
| Supported prose fact | sentence restates an inspected row | not flagged | N/A |
| Meta-talk | "I can draft soft constraints for you." | not factual → not flagged | N/A |
| Numbered capability list | the reported incident answer | not flagged | N/A |
| Shadow mode | any | probabilities persisted, nothing rendered | N/A |
| Too many sentences | above configured cap | first N checked, rest counted as skipped | N/A |
| Checker error | timeout | no flags | Turn completes |

</frozen-after-approval>

## Code Map

- `backend/application/ports/claim_support.py`, `backend/adapters/grounding/jev_checker.py` -- phase-3 port and adapter (add the second question type)
- `backend/application/grounding/verbalize.py` -- phase-3 verbaliser, extended to calculation results and the workflow snapshot
- `backend/application/contracts/grounding.py` -- `GroundedProseSegmentV1` gains `scan: {factual_probability, support_probability, flagged} | None`
- `backend/application/use_cases/execute_turn.py` -- post-gate hook from phase 3
- `frontend/src/features/chat/ActivityTimeline.tsx` -- prose rendering

## Tasks & Acceptance

**Execution:**
- [ ] `backend/application/grounding/sentences.py` -- deterministic sentence splitter over untagged prose segments; list items and line breaks are boundaries
- [ ] `backend/application/ports/claim_support.py` + adapters -- batch two questions per sentence; the double supports both
- [ ] `backend/application/use_cases/execute_turn.py` -- scan per mode; attach `scan` to prose segments; `flagged` only in `flag` mode
- [ ] `backend/settings.py` -- `GROUNDING_UNTAGGED_SCAN_MODE`, sentence cap, flag thresholds
- [ ] `frontend/src/features/chat/ActivityTimeline.tsx` (+ `schema.d.ts`) -- subtle "unverified" marker on a flagged sentence's segment
- [ ] `backend/evals/live_conversations/` -- report flagged and near-threshold sentences in shadow for review
- [ ] tests -- every matrix row with the double (backend), flagged vs unflagged rendering (frontend)

**Acceptance Criteria:**
- Given mode `shadow`, when a turn completes, then the planner-visible reply is identical to mode `off`.
- Given mode `flag` and a factual unsupported sentence, when the reply renders, then only that segment carries the marker.

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: all pass
- `cd frontend && npm run typecheck && npm test` -- expected: all pass
