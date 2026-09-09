# ShiftMind portfolio walkthrough

ShiftMind demonstrates a governed workforce-planning workflow: the model proposes typed intent, application code owns identity, authorization, policy, versions, approvals, state, and audit, and CP-SAT alone constructs or validates an accepted schedule.

## Run it

From a clean clone, run `docker compose up -d --build`, open `http://localhost:8080`, and sign in through the local fake identity provider. The default deterministic agent is keyless. The complete reproducible proof is `backend/tests/compose_proof.py`.

## Architecture boundary

ShiftMind is a hexagonal modular monolith: dependencies point inward, so domain and application code stay free of framework and concrete-provider types. The boundary is mechanically enforced — `backend/tests/architecture/` sweeps the packages for forbidden imports — with named exceptions carried in that suite's `ALLOWED_LEAKS` rather than waived silently. Three ports under `backend/application/ports/` currently import SQLAlchemy's `Connection` and are recorded there; closing them is tracked in the deferred-work ledger. The adopted invariants are in the [architecture spine](../_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md).

## The governed loop, end to end over real HTTP — captured 2026-09-09

Captured at commit `bb5b8ef5f744bc3785b3cc731df3392108d150ec` on a host with 16 logical CPUs, using the composed local stack and deterministic runtime.

1. Sign in and select `sample_tiny_input`.
2. Create conversation `83b846e8-eba8-4968-86c9-44da1f97dd16`.
3. Send the request and execute agent run `03e0d1bc-8346-48a2-a1f6-c37300c57745`.
4. Persist draft proposal `73047261-8bd2-417a-b30c-5a179bfb4e93`. The model turn in step 3 completed through the public HTTP loop; draft persistence is a **separate governed boundary**, driven here through the same capability and repository an agent turn uses rather than through the agent turn itself.
5. Start schedule run `bf53e121-f410-4d6e-a232-9b94f43ba138`.
6. The solver completed and produced candidate version `d7b7273c-3105-4085-a05e-d3542b5f6284` with 76 assignments.
7. Request approval `6bd6d275-d5bf-407c-9ab4-6bf13db86616` and approve it; the binding became `consumed` and promoted that candidate as the baseline.
8. Open the Provenance timeline for the run. It is site-scoped and read-only, joining committed run, conversation, approval and audit facts without recomputing them. The captured timeline carries the approval request, the decision, and the baseline promotion with its before and after versions — those three are what the anchored proof asserts; the timeline's evidence, draft and run-progress entries are read from the same committed records but are not pinned by that assertion.

The candidate recorded 1,993 overtime minutes and total cost 11,549.69. Coverage required/served minutes were Despatch 4,162.45/7,088; Pick 15,929.71/17,314; Putaways 4,104.88/6,592; and Receiving 988.98/656.

Read those figures with three things in mind, because the dimensional model behind them is not obvious and getting it wrong is this repository's most expensive recurring mistake:

- **They are recomputed from the candidate's assignments and the source facts, not read off the solver.** `backend/application/scheduling/candidate_metrics.py` accepts no solver objective or variable.
- **The required side for `outbound`/`inbound` demand *is* a conversion of volume into time.** Those families are measured in volume, so minutes are derived at the average rate across every worker qualified for the task — a fixed, candidate-independent conversion, deliberately not the per-worker rate that [`DOMAIN-MODEL.md`](DOMAIN-MODEL.md) §4 reserves for a later milestone. For this fixture 1,541 of 1,547 demand rows are volume, so Despatch, Pick and Receiving are entirely conversion output; Putaways additionally carries six `indirect` headcount rows, which are exact worker-minutes needing no conversion.
- **The run's `unmet_minutes` is 0, and that is a netted total, not per-function coverage.** It is `max(0, total_required − total_served)` across all intervals: 25,186 required against 31,650 served. Receiving is under-served by roughly 333 minutes and the surpluses elsewhere absorb it. Do not read 0 as "every function covered".

### What this run does not exercise

The capture above is the composed proof, which drives the loop through real HTTP but is not a browser walk. Three steps of the product's primary journey ([`EXPERIENCE.md`](../_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md) Flow 1) are therefore not shown here: the Scenario Data viewer, the agent reply carrying adjacent evidence links and its clarification path, and the Results surface with its baseline deltas and objective trade-offs. Those are covered by the frontend and API suites and by the evidence artifacts linked below, not by this transcript.

<!-- behavioral-claims:start -->
The composed journey reaches `solver_completed`, creates and consumes an approval, promotes the candidate baseline to a new version, and returns a provenance timeline carrying the approval request, the decision and the promotion. Anchor: `backend/tests/compose_proof.py::test_one_command_stack_serves_real_oidc_and_worker`.
The domain and application packages are swept for forbidden framework and persistence imports, and every recorded exception is itself asserted to still exist and still leak. Anchor: `backend/tests/architecture/test_conversation_boundaries.py::test_every_allowed_leak_still_exists_and_still_leaks`.
The evaluation harness is demonstrated by `evidence/story-2.2/evaluation-harness-demonstration.json`. Anchor: `evidence/story-2.2/evaluation-harness-demonstration.json`.
Automated accessibility coverage is recorded in `evidence/story-4.6/state-semantics-and-accessibility.json`. Anchor: `evidence/story-4.6/state-semantics-and-accessibility.json`.
<!-- behavioral-claims:end -->

## Illustrative live-provider output — not captured

No live provider or model was configured for this run, so no illustrative
model prose is quoted. The behavioral proof above ran under
`AGENT_RUNTIME_MODEL=deterministic` — the keyless model double — and that is the
release-relevant result. Live-provider output is optional here and is never
release evidence.

## Evidence and gates

Fourteen bound evidence artifacts exist. Each was generated through `backend/scripts/evidence_binding.py` against a measured run, per [`EVIDENCE-CONVENTION.md`](EVIDENCE-CONVENTION.md) — none was hand-written.

**Gate A**

- [Viewer parity and mutation denial](../evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json)
- [Gate A readiness report](../evidence/story-1.11/gate-a-readiness-report.json)

**Evaluation**

- [Evaluation harness demonstration](../evidence/story-2.2/evaluation-harness-demonstration.json) — a demonstration of the machinery; it records `release_gate_eligible: false` and deliberately does not evaluate the aggregate thresholds

**Correctness, recovery and repair**

- [Repair correctness](../evidence/story-3.10/repair-correctness.json)
- [Recovery idempotency](../evidence/story-3.11/recovery-idempotency.json)
- [Repair browser journey](../evidence/story-3.12/repair-browser-journey.json)
- [Approval and audit invariants](../evidence/story-4.5/approval-audit-invariants.json)

**Performance thresholds (NFR35, internal acceptance only)**

- [Scenario data load](../evidence/story-1.4/nfr35-scenario-data-load.json)
- [Evidence target resolution](../evidence/story-1.5/nfr35-evidence-target-resolution.json)
- [SSE reconnect and replay](../evidence/story-2.4/nfr35-sse-reconnect-replay.json)
- [First run event](../evidence/story-3.5/nfr35-first-run-event.json)

**Accessibility and content (automated coverage only)**

- [Scenario data accessibility and responsiveness](../evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json)
- [State semantics and accessibility](../evidence/story-4.6/state-semantics-and-accessibility.json)
- [Content minimization report](../evidence/story-5.2/content-minimization-report.json)

Gate B's checklist is in [`epics.md`](../_bmad-output/planning-artifacts/epics.md). The aggregate release report is specified as `evidence/epic-5/release-gate-report.json`, but it is an Evaluation/QA-owner step after this story: the dataset currently has 30 cases against its 50-case floor, which requires recorded owner rationale rather than a fabricated report. **Gate B has not passed.**

## Limitations

### Single-planner scope and self-approval

The planner who requests an approval can decide it. No separation-of-duties rule exists and none is planned at this milestone. Revisit this when activating a second user or during a customer security review.

### Fixture-only source data

The journey uses immutable fixtures. There is no scenario-source mutation command, route, tool, or UI control in this portfolio scope.

### Retention

There is no data-retention or purge policy. Conversations, audit records, snapshots, and local database records have no configured expiry; container logs are bounded only by Docker defaults. Session and approval expiries are workflow lifetimes, not retention settings.

### No hosted deployment

There is no hosted deployment at this milestone; the documented path is the local composed stack.

### Non-customer status

This is a portfolio artifact, not a customer service.

### No enterprise promise

No claim here is a customer promise for latency, availability, recovery, concurrency, or cost. The recorded measurements are local acceptance evidence.
