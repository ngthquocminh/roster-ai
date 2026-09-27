---
title: 'Grounding 2a: text answers with {{handle}} value placeholders; numeral rule removed'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: '4afaeee447fb5ae278a92e6a84853ae732493898'
review_loop_iteration: 0
depends_on: 'spec-grounding-1-evidence-registry-short-handles.md'
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-grounded-answers-claim-evidence-attribution-research-2026-09-26.md'
  - '{project-root}/docs/DOMAIN-MODEL.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The model answers as a segment array and must split every sentence around a claim segment; a lexical rule then rejects any numeral in prose it cannot trace, retrying and finally blocking the turn on false positives (numbered lists, times) while invented names pass unchecked (D2).

**Approach:** The model answers as one text in which every calculated value is a placeholder `{{r1}}` naming a registry handle. The gate parses the text into the existing persisted `GroundedResponseV1` segments: prose, and a claim synthesised from the resolved calculation result. The numeral rule is deleted (D2); untagged prose is plain, unverified text. No grounding failure blocks the turn.

## Boundaries & Constraints

**Always:** A rendered number comes only from a trusted calculation result resolved through the registry; the model never supplies it. Persisted `GroundedResponseV1` shape is unchanged, so the frontend is untouched. Every existing claim verification that does not depend on model-supplied arguments (version pinning, locator resolution, empty-set proof) still runs. Keep `application/**` framework-free (AD-19).

**Ask First:** Retaining any lexical check on untagged prose; changing `retries_limit`.

**Never:** `<claim>` fact tags or record handles (2b); tier-1 checking (3); frontend changes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Value placeholder | `"Wednesday outbound needs {{r1}}."`, r1 returned | prose + supported claim (value 2160 minutes) + prose | N/A |
| Numbered list, times, names | `"1. Draft\n2. Run at 06:00 for Forklift C01"` | One prose segment, no retry | N/A |
| Unknown handle, calculation ran | `{{r9}}` | Failed claim `missing_evidence`, answer still delivered | Not a turn failure |
| Placeholder, no calculation this turn | `{{r1}}` | One corrective retry (`claim_without_calculation`) | After retries: failed claim, answer delivered |
| Malformed placeholder | `{{}}`, `{{ value }}` | One corrective retry (`claim_gap`) | After retries: literal text shown as prose |
| "How many" with no placeholder | prompt asks a quantity | One corrective retry (`quantity_without_claim`) | Unchanged rule |
| Plain-text answer | model returns text, no output tool | Parsed exactly like the output-tool answer | N/A |

</frozen-after-approval>

## Code Map

- `backend/application/contracts/grounding.py` -- `GroundedAnswerV1` (model output) → new `GroundedAnswerV2(text)`; persisted `GroundedResponseV1` unchanged
- `backend/application/grounding/gate.py` -- `ground_answer`, `_ground_claim`, `numeric_prose_violation`, `trusted_numeric_words`, `UncitedNumericProseError`, `SCOPE_CONTROLS`
- `backend/agent/runtime.py` -- output types (`ToolOutput(answer_type)`, `TextOutput(_prose_answer)`), `_reject_numeric_prose`, `_reject_uncited_claim`, `_CLAIM_PLACEHOLDERS`, `_trusted_texts`
- `backend/application/use_cases/execute_turn.py` -- `_trusted_texts`, gate call
- `backend/agent/scheduling_instructions.py` -- "Numbers in replies" and claim-citation sections
- `backend/evals/golden/**`, `backend/evals/golden_multi_turn/**` -- 16 scripted answers in segment form
- `_bmad-output/planning-artifacts/epics.md:37,97` -- FR7, NFR12

## Tasks & Acceptance

**Execution:**
- [x] `backend/application/contracts/grounding.py` -- add `GroundedAnswerV2(text: str)`; remove `GroundedAnswerV1`/`ClaimProposalV1` once unused -- one answer shape
- [x] `backend/application/grounding/placeholders.py` -- pure parser: text → ordered prose/placeholder parts; handle syntax `[A-Za-z0-9_-]+`
- [x] `backend/application/grounding/gate.py` -- ground a `GroundedAnswerV2`: placeholder → claim built from the resolved result (metric, arguments, value, unit, refs) with existing version/locator/empty-set checks; unresolved → failed claim; delete the numeral rule and its `SCOPE_CONTROLS` entry, add one for placeholders
- [x] `backend/agent/runtime.py` -- answer type V2 for both output tool and plain text; delete `_reject_numeric_prose` and `_trusted_texts`; adapt `_reject_uncited_claim` rules to placeholders per the matrix; drop `<claim` from `_CLAIM_PLACEHOLDERS`
- [x] `backend/application/use_cases/execute_turn.py` -- drop trusted-text collection
- [x] `backend/agent/scheduling_instructions.py` -- rewrite the numbers/claims guidance for `{{handle}}`; values read from records are ordinary prose
- [x] `backend/evals/**` golden answers -- convert to V2 text; retire `argument-mismatch` (impossible by construction) with a note in the case index
- [x] `_bmad-output/planning-artifacts/epics.md` -- FR7/NFR12 apply to numbers presented as verified; untagged text is presented as unverified (D2)
- [x] `backend/tests/**` -- matrix rows; delete tests of the removed numeral rule

**Acceptance Criteria:**
- Given the reported incident answer (four numbered stages, no tools), when the turn runs, then it completes on the first attempt with one prose segment.
- Given any grounding failure, when the turn ends, then the answer is delivered with the failure inspectable on its claim; no `UncitedNumericProseError` path remains.
- Given the golden and full backend suites, when run, then all pass.

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: all pass
- `cd frontend && npm test` -- expected: all pass (no frontend change intended)

## Suggested Review Order

**Answer contract and parsing**

- Entry point: the model answers with one text; values are `{{handle}}` placeholders.
  [`grounding.py:87`](../../backend/application/contracts/grounding.py#L87)
- Pure parser; malformed syntax (incl. stray braces) stays literal prose.
  [`placeholders.py:33`](../../backend/application/grounding/placeholders.py#L33)

**Gate: claims from trusted results only**

- Placeholder becomes a claim whose metric, arguments, value come from the result.
  [`gate.py:176`](../../backend/application/grounding/gate.py#L176)
- Unresolved handle is a failed claim with contract-default metric.
  [`gate.py:75`](../../backend/application/grounding/gate.py#L75)
- Numeral rule deleted; new scope control states what text is unverified.
  [`gate.py:52`](../../backend/application/grounding/gate.py#L52)

**Runtime retries**

- Placeholder slips retry, but the last attempt delivers the answer (matrix).
  [`runtime.py:400`](../../backend/agent/runtime.py#L400)
- Prompt: f-string, so braces are doubled in source.
  [`scheduling_instructions.py:156`](../../backend/agent/scheduling_instructions.py#L156)

**Evals and requirements**

- argument_mismatch retired; untagged-numerals keeps the four-case floor.
  [`cases.py:19`](../../backend/evals/cases.py#L19)
- FR7/NFR12 reworded for D2.
  [`epics.md:37`](../planning-artifacts/epics.md#L37)

**Tests**

- Parser, gate matrix, first-attempt incident answer, delivered-after-retries.
  [`test_placeholders.py:1`](../../backend/tests/test_placeholders.py#L1)
  [`test_agent_runtime_adapter.py:899`](../../backend/tests/test_agent_runtime_adapter.py#L899)
