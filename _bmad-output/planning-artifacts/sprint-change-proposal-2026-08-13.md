---
title: "Sprint Change Proposal: Story 2.7 Grounding Mechanism — Cite, Do Not Recompute"
status: proposed
created: 2026-08-13
supersedes_scope: none
related: 2-7-ground-schedule-claims-in-exact-evidence.md
---

# Sprint Change Proposal: Story 2.7 Grounding Mechanism — Cite, Do Not Recompute

## 1. Issue Summary

Story 2.7 (`2-7-ground-schedule-claims-in-exact-evidence.md`) is `ready-for-dev`,
committed at `87126c4` on branch
`story/2-7-ground-schedule-claims-in-exact-evidence`, with **zero code written** —
`backend/application/contracts/grounding.py`,
`backend/application/grounding/`, and
`backend/application/use_cases/execute_turn.py` do not exist.

Its Decision 2 specifies the grounding mechanism as **assert-and-compare**: the
model reads raw scenario rows through `scheduling_inspect`, performs its own
arithmetic, and emits a `ClaimProposalV1` carrying an asserted value; the gate
then independently recomputes the same quantity with an application calculator,
compares the two, and treats a mismatch as a failed claim.

Review before implementation found that this mechanism manufactures failures and
promotes an ungoverned fourth failure type. Issue type: **failed approach
requiring a different solution**, caught at the cheapest possible moment.

The story's seven creation decisions are marked *"do not re-litigate"*. That
marking is why this is a correct-course run rather than an annotation: a
dissenting note left beside a locked decision would be read by the dev agent as
commentary on a decision it has been instructed to follow, and the flawed design
would be built anyway.

## 2. Root-Cause Findings

### Finding 1 — The model is asked to compute from data it cannot fully see

`backend/application/capabilities/scheduling_inspect.py:4` states the capability
*"never computes a metric"*; it returns paged raw records. `GroupQueryV1.limit`
defaults to **50** (`application/ports/scenario_projection.py:35`) and
`scheduling_inspect_row_limit` caps at **200** (`settings.py:75`).

Decision 4 of the same story devotes a full section to forbidding calculators
from computing a total from one page, calling it *"the quietest trap in the
story."* Under Decision 2 the **model** performs that same arithmetic, over the
same paged reader, with none of Decision 4's protections. The story builds a
guard rail for the calculator and then hands the identical computation to the
one actor that has no guard rail.

Consequence: mismatch is not an occasional event but the **expected** outcome, and
the grounding gate degrades from a rarely-triggered safety net into a rejection
engine.

### Finding 2 — A mismatch discards a number that is fully supported

When the calculator computes 90 from the pinned immutable version with locators
attached, that value satisfies every definition of "supported" the architecture
uses. Under assert-and-compare, a model guess of 120 causes the **claim** to fail
— so the artefact discarded is not the model's guess (which was always destined
to be discarded) but the calculator's correct, evidenced, version-pinned result.

The design can therefore turn a correct grounded answer into a rendered failure
state, on the basis of a computation the architecture already declares
untrustworthy.

### Finding 3 — `unsupported_value` is a fourth failure type the spine does not name

Both governing statements name exactly three distinct failures:

- AD-11 (`ARCHITECTURE-SPINE.md:154`): *"Missing, unauthorized, and
  version-mismatched evidence are distinct failures; no fallback may target
  another version or row."*
- AR11 (`epics.md:157`): *"missing, unauthorized, and version-mismatched evidence
  are distinct failures and never retarget."*

Stated twice, in two artefacts, as three. Story 2.7's Task 2 introduces
`unsupported_value` — *"the model's discarded arithmetic disagreed"* — as a
fourth, and it is the only one of the five that can fire against correct data.

### Finding 4 — AD-11 sanctions both branches; the story took the worse one

AD-11 reads *"Application calculators **produce or verify** every numerical claim
… against immutable snapshots."* The disjunction is real: the architecture
permits the calculator to **produce** the value or to **verify** a value produced
elsewhere.

Decision 2 took the `verify` branch. Nothing required it. The `produce` branch is
named first, satisfies the same rule, and does not require the model to compute
anything.

### Finding 5 — The provenance argument for recomputing does not hold

Decision 2's supporting argument is that trusting a capability result would
require durable provenance, which AD-12 assigns to `EvidenceSnapshot` /
`AuditEnvelopeV1` in Epic 4.

Verifying a citation **within a single turn** requires only that turn's
capability results, held in memory for the duration of the request — already
available to the runtime through `result.all_messages()`. Durable provenance is
needed for Story 2.8's later read-back, and that need is already met by the
`EvidenceRefV1` locators this story persists in the `agent_response` payload.

### Finding 6 — No prior art for assert-and-compare; strong prior art for the alternative

"LLM selects the metric, the engine computes it" is the established semantic-layer
pattern (dbt Semantic Layer, Cube, LookML), and "do not let the model perform
arithmetic" is the conclusion of the PAL / Program-of-Thoughts line of work. The
story's own alternative — asking a model for a number that will be discarded, and
using the disagreement as a signal — has no known production precedent and is
argued in the story from first principles rather than from prior art.

## 3. Impact Analysis

### Epic impact — none

Epic 2 completes as planned. No epic scope change, no new epic, no epic removed,
no resequencing.

### Story impact

| Story | Impact |
|---|---|
| **2.7** | Decision 2, Tasks 2/3/4/6, traps list, Change Log |
| 2.8 | **None.** It reads persisted `EvidenceRefV1` locators; the locator shape is unchanged and they are still persisted in the `agent_response` payload |
| 2.9 | **None.** Clarification/refusal variants are untouched |
| Epic 3+ | **None** |

### Artifact conflicts — none requiring edit

| Artifact | Finding |
|---|---|
| **PRD** | No conflict. FR-7's testable consequence (*"every displayed KPI can be recomputed from saved evidence"*) is satisfied. §4.8 item 1 already names **coverage** — a derived quantity — and permits *"combine read operations internally"*. §6.4 *"100% verified against saved evidence"* satisfied. MVP unchanged |
| **Architecture** | No conflict. AD-11's `produce` branch is taken as written. AR11's three failures are preserved and no fourth is added. The new capability uses the existing `inspect` risk class, so **AR5 is untouched** |
| **UX** | No conflict. Claim nodes remain, so UX-DR8's adjacency requirement is still met; UX-DR5 and UX-DR32 are unaffected |
| **Acceptance Criteria** | **AC1, AC2, AC3 unchanged.** AC1 requires application calculators to produce the value against immutable versions and attach locators — which the new design does, once, instead of twice |

### Technical impact

| Change | Cost |
|---|---|
| `backend/application/capabilities/scheduling_compute.py` | New module, in `scheduling_inspect.py`'s established shape |
| `backend/application/capabilities/installed.py` | **+1 line** in `_INSTALLED_FACTORIES` |
| `backend/tests/test_evaluation_harness.py:316` | **+1 entry** in `MVP_PRODUCT_CAPABILITIES` |
| NFR28 *"≥4 cases per allowed capability"* | Met exactly by the four golden cases the ACs already required |
| `backend/application/capabilities/scheduling_inspect.py` | **Zero-line diff** |
| Migration / infra / CI | **No change** |

## 4. Recommended Approach

**Option 1 — Direct Adjustment. Selected.** Effort **Low**, risk **Low**.

Amend Story 2.7 in place before implementation begins. No rollback is available
or needed (nothing is built). No PRD MVP review is warranted (the MVP is
unaffected).

### The amended mechanism

1. The model calls `scheduling_compute` with a metric from the closed vocabulary
   and its arguments.
2. The capability computes against the pinned immutable scenario version, paging
   to exhaustion, and returns
   `{value, unit, evidence_refs, scenario_version_id, result_id}`.
3. The model composes its answer; each claim carries a cited `result_id` and **no
   value**.
4. The gate **verifies the citation** — the `result_id` is among this turn's
   results, the claim's arguments match the originating call's, the version
   matches the pin — and attaches the locators the capability returned.

Exactly one calculation occurs per metric. The rendered number is still the
application's, still from an immutable version, still locator-bound.

### Why this is cheaper now than later

Deferring the change means `ClaimProposalV1` with `asserted_value` reaches the
persisted `agent_response` payload (Task 10), which Story 2.8 then reads back.
Reversing it afterwards costs a contract `schema_version` bump, possible payload
migration, a rewritten gate, re-authored golden cases, a Gate A re-run with the
documented two-commit dance (`deferred-work.md:97`), and a re-check of Story 2.8.
Today it costs edits to one uncommitted-in-substance markdown file.

## 5. Detailed Change Proposals

All six edits below were reviewed and approved individually in incremental mode.

### 5.1 Decision 2 — rewritten

Retitled to *"The model never supplies a number that renders. **Application
calculators produce the value through a governed tool**, and the gate verifies the
citation."* Opens by quoting AD-11's `produce or verify` disjunction and stating
that this story takes the **produce** branch. Replaces the recompute/compare
sequence with the four-step flow in §4. The VERIFIED table on
pydantic-ai-slim 2.27.0 output-tool behaviour (`info.output_tools`,
`allow_text_output`) is retained unchanged — `GroundedAnswerV1` is still the
strict output type.

Two new paragraphs replace *"Why the model still asserts a value"*:

- **"Why the model does not assert its own value"** — records the paging trap
  turned on the model, the resulting common-case mismatch, the discarding of a
  correct evidenced number, and the three-failure rule stated in both AD-11 and
  AR11.
- **"What the gate still falsifies"** — answers the original decision's claim
  that AC1's failure clause would become *"unprovable by construction"*, by
  naming four still-falsifiable conditions: a fabricated `result_id`; a
  `result_id` whose arguments do not match the claim; a result whose
  `scenario_version_id` differs from the pin; and a claim with no citation.

### 5.2 Task 2 — grounding contracts

- `ClaimProposalV1` carries metric, arguments, and the cited `result_id`, and
  **no value field**. A field the model could fill with a number is a field that
  will eventually render one.
- Its docstring still declares untrusted model output; the untrusted part is now
  the citation.
- `MetricV1` lives in `contracts/`, imported by the capability, preserving the
  *capabilities → contracts* dependency direction fixed by
  `capability_manifest.py`'s docstring.
- `GroundingFailureV1` becomes `missing_evidence`, `unauthorized_evidence`,
  `version_mismatch`, `calculation_failed`, `uncited_claim`. The last two are
  mechanical, not evaluative; **no failure type means "the model's arithmetic
  disagreed"**, because the model performs no arithmetic.

### 5.3 Task 3 — calculators, exposed as `scheduling_compute`

Retitled. Page-to-exhaustion, unit discipline, half-open interval boundary tests,
and the projection-contracts-only rule are **retained verbatim** — Decision 4 now
protects the single path to every number.

Added:

- New capability module in `scheduling_inspect.py`'s exact shape (typed errors
  with `code`, module-level `ERROR_CODES`, `SCOPE_CONTROLS`, deferred settings
  import inside the manifest factory). The handler delegates to the calculators.
- `risk_class="inspect"`, **not `"compute"`** — AR5's `compute` class is the
  solver (PRD §4.8 item 3), and a read that derives a total must not claim
  solver-grade authority.
- Registration in `installed.py` (one line).
- `scheduling_inspect` shows a **zero-line diff**.
- **`result_id` is derived, not random**: RFC 8785 canonical-JSON SHA-256 over
  `(metric, canonical arguments, scenario_version_id)`, the hashing convention
  AR20 already fixes. This is load-bearing: golden cases drive an authored
  `ScriptedModelTurn`, so a scripted turn must be able to cite a `result_id`
  written into the case file. A per-call UUID would make every grounded case
  unwritable.
- `SchedulingComputeResultV1` is a capability result and must not be shaped or
  named as AR20's `MetricSetV1`, which Epic 3 owns.

### 5.4 Task 4 — the grounding gate

- Input gains this turn's capability results keyed by `result_id`. **The gate
  performs no computation.**
- Ordered per-claim verification: citation present and found → arguments match
  the originating call → version equals the pin → attach the capability's
  locators. The gate never derives a locator.
- **Deleted:** the comparison-tolerance bullet. There is no longer a second value
  to compare against, and leaving the bullet would invite a reviewer to rebuild
  the compare step.
- **Added:** a prose segment containing a decimal digit fails the answer.
  Without it the tier-1 invariant is not total — the model could write *"you're
  short about two hours"* in prose and bypass every claim node. The rule is
  deliberately blunt (reject any Unicode decimal digit, fail-closed); any
  relaxation must be a declared allow-list with its own test, recorded in
  `SCOPE_CONTROLS`.
- Retained: never-retarget test, one-failed-of-three test, `SCOPE_CONTROLS` with
  the schedule/run-version gap.

### 5.5 Task 6 — evaluator and golden cases

- The fourth case changes from *unsupported-value (asserted-vs-computed
  mismatch)* to **argument-mismatch**: a real result cited on a claim whose
  window or metric differs from the originating call. This is the only remaining
  way a fully grounded response can be false.
- Cases are tagged `capability="scheduling_compute"`, and that name is added to
  `MVP_PRODUCT_CAPABILITIES` as a **product** capability (PRD §4.8 item 1), not
  an exemption. `test_every_capability_meets_the_nfr28_four_case_floor` is
  designed to fail on an unclassified capability; classifying it is the intended
  path.
- NFR28's four-case floor is met **exactly**, deliberately; `epics.md:1527`
  forbids padding.
- The new manifest's `evaluation_fixtures` names the four case files, as
  `scheduling_inspect`'s does.
- `GroundingEvaluator` remains the single second evaluator Story 2.2 authorised.

### 5.6 Dev Notes and Change Log

- Scope summary becomes *"One migration. One new route. **One new capability.**
  No new dependency."*
- In-scope row 1 names the capability.
- **Trap 3 replaced**: *"Accepting a citation without checking its arguments"* —
  a genuine value with genuine locators paired to the wrong question, which the
  planner would verify successfully.
- **Trap 11 added**: *"Re-adding a recompute-and-compare step 'to be safe'"* —
  it reads as defence in depth and restores the manufactured-failure mode.
- Change Log entry dated 2026-08-13 recording the amendment and that no AC, PRD,
  epic, architecture, or UX change was required.

## 6. Out of Scope — Recorded Separately

The **tier-2 evaluation gap** is real, is not caused by this change, and is not
fixed by it. It belongs in `deferred-work.md` with an owner and a revisit
trigger, not in Story 2.7:

- `RunSource = Literal["double", "live"]` (`evals/evaluators.py:12`) — `"live"`
  appears **only** in the type definition and is used nowhere.
- No evaluator anywhere assesses whether prose is faithful to the computed
  claims.
- `GoldenCase.expected_visible_text` is a **required** field
  (`evals/cases.py:66`, in `CASE_FIELDS`, no default) that **no `Evaluator`
  reads**. Its only assertion is `test_evaluation_harness.py:287`, inside a
  harness self-test, comparing an authored scripted response to itself.
- NFR28's *"≥90% overall tool routing"* is measured over deterministic doubles
  whose turns are authored, so it currently describes the dataset rather than
  the model.

A required field that nothing verifies is the most dangerous shape here: it reads
as covered.

## 7. Implementation Handoff

**Scope classification: Minor.** One artefact changes — the Story 2.7 file. No
backlog reorganisation, no replan, no PM/Architect escalation.

| Recipient | Responsibility |
|---|---|
| **Developer agent** | Apply the six edits to `2-7-ground-schedule-claims-in-exact-evidence.md`; commit on the existing story branch |
| **Developer agent** | Add the tier-2 evaluation gap to `deferred-work.md` with owner and revisit trigger |
| **Developer agent** | Then proceed with `bmad-dev-story` against the amended story |

`sprint-status.yaml` needs **no change**: no epic or story was added, removed, or
renumbered, and Story 2.7 remains `ready-for-dev`.

### Success criteria

1. Story 2.7 contains no `asserted_value`, no comparison step, and no
   `unsupported_value` failure type.
2. `scheduling_inspect` is specified to show a zero-line diff.
3. AC1, AC2, and AC3 are byte-identical to `epics.md:769-790`.
4. The tier-2 gap is recorded in `deferred-work.md` with an owner.
