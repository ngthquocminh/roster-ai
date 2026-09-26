---
title: 'Per-turn evidence registry with short citation handles'
type: 'feature'
created: '2026-09-27'
status: 'ready-for-dev'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-grounded-answers-claim-evidence-attribution-research-2026-09-26.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A claim cites a calculation by copying its 64-character content-addressed `result_id`. Live models mis-copy it (observed 63 and 68 characters), which needed a dedicated fuzzy-match retry rule, and the hash gives the planner-facing model nothing readable. Phase 2 of the grounding redesign (inline `<claim ev=…>` tags) also needs one place that issues and resolves citation identifiers per turn.

**Approach:** Add a per-turn, application-owned evidence registry that mints short handles (`r1`, `r2`, … in first-seen order) for citable calculation results. The model sees and cites the handle; the gate resolves it to the trusted result; persisted claims keep the canonical content-addressed `result_id`. Phase 1 of the G′ roadmap (research doc, decisions D1–D3).

## Boundaries & Constraints

**Always:** The application mints handles; the model never does, and an unknown handle stays the gate's `missing_evidence` state. Handles are turn-scoped and deterministic for a given call order. The persisted `GroundedClaimV1.result_id` of a resolved claim is the canonical content-addressed id, so stored history, provenance and the UI are unchanged. A citation of a full `result_id` returned in this turn still resolves. `application/**` stays framework-free (AD-19); the adapter stays shape-agnostic (no per-capability field rewriting in `agent/capability_tools.py`).

**Ask First:** Minting handles for anything other than calculation results (records, drafts, runs); changing the persisted claim schema or the frontend.

**Never:** No `<claim>` tags, `{{r}}` placeholders, or record handles (phase 2). No change to the numeral rule, the draft citation path (`draft_id`), or claim verification logic beyond handle resolution.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First calculation in a turn | `scheduling_compute` returns | Model view shows `result_id: "r1"` | N/A |
| Same calculation repeated | identical request twice in one turn | Both views show `r1` | N/A |
| Two calculations | different requests | `r1`, then `r2` | N/A |
| Claim cites a handle | `result_id: "r2"` | Claim grounded against the `r2` result; persisted `result_id` is the 64-hex id | N/A |
| Claim cites a full id returned this turn | 64-hex id | Resolves as today | N/A |
| Claim cites unknown handle | `"r9"` | `missing_evidence`, cited `"r9"` kept on the failed claim | Gate state, not an exception |
| New turn | fresh deps | Handles restart at `r1` | N/A |

</frozen-after-approval>

## Code Map

- `backend/application/capabilities/deps.py` -- `AgentDepsV1`, built fresh per turn in both routes and the eval harness
- `backend/application/capabilities/scheduling_compute.py` -- trusted `SchedulingComputeResultV1`, `_model_view`, handler
- `backend/application/use_cases/execute_turn.py:109` -- builds the `result_id → result` map the gate receives
- `backend/application/grounding/gate.py` -- `_ground_claim` copies `proposal.result_id` onto the grounded claim
- `backend/evals/grounding.py:50`, `backend/evals/report.py:396` -- duplicate the same map for goldens
- `backend/agent/runtime.py:192,505-519` -- `_mistyped_result_id` and the `result_id_mistyped` retry rule
- `backend/agent/scheduling_instructions.py:179` -- tells the model the id "is a long hash"
- `backend/evals/golden/scheduling_compute/*.json` -- scripted claims cite the literal hash

## Tasks & Acceptance

**Execution:**
- [ ] `backend/application/grounding/evidence_registry.py` -- new, import-free: `EvidenceRegistry` (`handle_for(result_id)` idempotent minting, `result_id_for(handle)`), plus `trusted_results_by_citation(results, registry)` returning full-id and handle keys -- one issuer/resolver for all call sites
- [ ] `backend/application/capabilities/deps.py` -- `evidence_registry` field, `default_factory`, excluded from compare/repr -- per-turn by construction, no route wiring
- [ ] `backend/application/capabilities/scheduling_compute.py` -- handler records the handle on the trusted result (new defaulted field); `_model_view` shows it as `result_id` -- the capability, not the adapter, decides what the model sees
- [ ] `backend/application/use_cases/execute_turn.py`, `backend/evals/grounding.py`, `backend/evals/report.py` -- use `trusted_results_by_citation` instead of the three hand-built maps -- removes duplicated resolution
- [ ] `backend/application/grounding/gate.py` -- a claim resolved to a result carries `result.result_id`; unresolved keeps the cited value -- persisted ids stay canonical
- [ ] `backend/agent/runtime.py` -- remove `_mistyped_result_id` and the `result_id_mistyped` rule; `backend/tests/test_agent_runtime_adapter.py` -- delete its test -- unreachable with handles
- [ ] `backend/agent/scheduling_instructions.py` -- describe the id as a short handle such as `r1`, copied exactly
- [ ] `backend/evals/golden/scheduling_compute/{supported,argument-mismatch,version-mismatch}.json` -- cite `r1`, bump `case_version`
- [ ] `backend/tests/` -- tests for every I/O matrix row (registry unit tests; compute view; `execute_turn` resolution and persisted id)

**Acceptance Criteria:**
- Given the golden suite, when it runs with the deterministic doubles, then every case passes with the scripted claims citing `r1`.
- Given a completed turn with a supported claim, when its grounded response is persisted, then the stored `result_id` equals `derive_result_id(...)` for that calculation.

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: all pass
