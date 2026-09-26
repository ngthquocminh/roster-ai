---
title: 'Grounding 2b: record handles and <claim> fact tags with deterministic ID + content checks'
type: 'feature'
created: '2026-09-27'
status: 'ready-for-dev'
review_loop_iteration: 0
depends_on: 'spec-grounding-2a-value-placeholders.md'
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-grounded-answers-claim-evidence-attribution-research-2026-09-26.md'
  - '{project-root}/docs/DOMAIN-MODEL.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After 2a, record facts ("Ana is qualified for T1", "that lock covers Wednesday") are untagged prose the planner cannot tell apart from invention, and nothing verifies them.

**Approach:** `scheduling_inspect` rows get registry handles (`w3`, `t12`, …). The model wraps a record fact as `<claim ev='w3' field='qualifications' value='T1'>Ana is qualified for T1</claim>`. The gate checks the handle AND the content (D1): the handle was issued this turn, the field exists on that record, and the value matches the record's trusted field content. The fact persists as a new segment kind the UI shows as verified or unverified.

## Boundaries & Constraints

**Always:** The check runs against the trusted inspect result captured this turn, never against model-visible text. A failed or malformed fact is shown flagged as unverified — never as verified, never stripped, never blocking. Tag syntax arriving inside tool data needs no escaping: a copied tag is still checked against the record. Tier 0 checks attributes, not the wrapped wording (the model sees IDs such as `T1` while prose may use names); wording is tier 1's job (phase 3). Because wording is unchecked until then, the verified marker always displays the checked `field: value`, so the planner sees exactly what was verified.

**Ask First:** Handles for capabilities other than `scheduling_inspect`; a value-in-text check.

**Never:** Model-based checking (phase 3); changing `{{r}}` values (2a).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Supported fact | `ev='w3' field='qualifications' value='T1'`, w3 has T1 | Fact segment `supported`, evidence ref to w3; UI shows `qualifications: T1` on the marker | N/A |
| Value mismatch | value `'T9'` | Fact `failed`, `value_mismatch`, text shown flagged | No retry |
| Unknown field | `field='salary'` | `failed`, `unknown_field` | No retry |
| Unknown handle, inspect ran | `ev='w99'` | `failed`, `missing_evidence` | No retry |
| Handle, no inspect this turn | `ev='w1'` | One corrective retry | Then `failed` |
| Numeric field | `field='contracted_hours' value='40'`, record 40.0 | `supported` (numeric equality) | N/A |
| Nested value | qualifications is a list of `{task_id, rate}` | Matches any element's scalar | N/A |
| Malformed / nested tags | unclosed, missing attribute | Inner text shown as plain prose; tag syntax not shown | No retry |

</frozen-after-approval>

## Code Map

- `backend/application/grounding/evidence_registry.py` -- (phase 1) add record handles with group prefixes: w workers, t work-areas-and-tasks, d demand, a baseline-assignments, l locks, c constraints-and-objectives
- `backend/application/capabilities/scheduling_inspect.py` -- trusted `SchedulingInspectResultV1.items` (row dicts); model view is identity
- `backend/application/contracts/grounding.py` -- add `GroundedFactV1` to `GroundedResponseSegmentV1`
- `backend/application/grounding/gate.py`, `resolvers.py`, `calculators.py` -- locator building/resolution to reuse for the fact's `EvidenceRefV1`
- `backend/agent/runtime.py` -- validator for the no-inspect retry
- `backend/agent/scheduling_instructions.py` -- tag guidance
- `frontend/src/features/chat/ActivityTimeline.tsx` -- `ClaimSegment` rendering pattern to mirror; `frontend/src/api/schema.d.ts` regenerated

## Tasks & Acceptance

**Execution:**
- [ ] `backend/application/grounding/evidence_registry.py` -- `handle_for_record(group, record_id)`, resolve handle → (group, record_id)
- [ ] `backend/application/capabilities/scheduling_inspect.py` -- each trusted row gains an `ev` handle; model sees it
- [ ] `backend/application/grounding/claim_tags.py` -- pure parser over the prose parts from 2a: fact tags, malformed handling
- [ ] `backend/application/contracts/grounding.py` -- `GroundedFactV1(text, field, value, evidence_refs, verdict, failure)`; failures `missing_evidence | unknown_field | value_mismatch | version_mismatch | unauthorized_evidence`
- [ ] `backend/application/grounding/gate.py` -- fact check per the matrix; build and resolve the fact's `EvidenceRefV1` with the existing locator path
- [ ] `backend/agent/runtime.py` -- one corrective retry when a fact cites a record handle and no inspect ran this turn
- [ ] `backend/agent/scheduling_instructions.py` -- when and how to tag record facts; attributes use record field names and model-visible values
- [ ] `frontend/src/features/chat/ActivityTimeline.tsx` (+ regenerated `schema.d.ts`) -- render fact text with a verified marker and evidence link, or an "unverified" marker when failed
- [ ] `backend/evals/golden/scheduling_inspect/` -- cases: supported fact, value mismatch, unknown handle
- [ ] tests -- every matrix row (backend) and both fact states (frontend)

**Acceptance Criteria:**
- Given a supported fact, when the planner views the reply, then the fact shows as verified with a link to its record.
- Given a failed fact, when the planner views the reply, then its text shows with an unverified marker and the rest of the answer is unaffected.

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: all pass
- `cd frontend && npm run typecheck && npm test` -- expected: all pass
